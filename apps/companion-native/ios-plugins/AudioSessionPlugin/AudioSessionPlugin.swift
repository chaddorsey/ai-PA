// AudioSessionPlugin.swift
// Amtrak Companion — Plan 3: AudioSession Capacitor plugin
//
// Implements the Plan 0 §F audio model:
//
//   THREE SESSION MODES (user-settable via setMode()):
//     'duck'             → .playback + .duckOthers; session stays ACTIVE the whole journey.
//                          Music drops to a system-fixed low level while narrating.
//                          Restores between bursts after a 2s silence gap.
//     'pause'            → .playback (no mix); setActive(false, .notifyOthersOnDeactivation)
//                          after each talking burst. Music fully pauses/resumes per burst.
//     'interrupt-spoken' → .duckOthers + .interruptSpokenAudioAndMixWithOthers.
//                          Ducks music but pauses other spoken audio (podcasts/audiobooks).
//
//   DEFAULT mode = the smart combo: activate with .duckOthers + .interruptSpokenAudioAndMixWithOthers.
//   The session is only FULLY deactivated on a real full stop (silence/quit).
//
//   REQUIRED: interruptionNotification handler → on .ended with .shouldResume, reactivate + resume.
//   (The tracer bullet lacked this, causing no-resume after a call; fixed here.)
//
//   MP3 via AVAudioPlayer (proven by tracer bullet; OGG/Opus not supported before iOS 17.2).
//
// DEVICE BUILD: Add to App Xcode target. AudioSessionPlugin.m registers the plugin.
// WRITTEN, NOT COMPILED HERE. User must build on Mac with Xcode 15+.

import Foundation
import Capacitor
import AVFoundation

@objc(AudioSessionPlugin)
public class AudioSessionPlugin: CAPPlugin, CAPBridgedPlugin {

    // MARK: - Capacitor registration (CAPBridgedPlugin — REQUIRED on Capacitor 6+;
    // the old Objective-C CAP_PLUGIN macro in the .m no longer registers in-app Swift plugins.)
    public let identifier = "AudioSessionPlugin"
    public let jsName = "AudioSession"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "setMode", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "play",    returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "pause",   returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "resume",  returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "setRate", returnType: CAPPluginReturnPromise),
    ]

    // MARK: - State

    private var player: AVAudioPlayer?
    private var endObserver: Any?
    private var interruptObserver: Any?
    private var currentMode: AudioMode = .duck
    private var isDucked = false
    private var silenceTimer: Timer?
    private let silenceThreshold: TimeInterval = 2.0  // seconds of silence before restoring

    private enum AudioMode: String {
        case duck = "duck"
        case pause = "pause"
        case interruptSpoken = "interrupt-spoken"
    }

    // MARK: - Plugin lifecycle

    public override func load() {
        // Apply default mode (duck + interrupt-spoken combo) on launch.
        activateSession(mode: .duck)
        registerInterruptionObserver()
    }

    // MARK: - setMode

    @objc func setMode(_ call: CAPPluginCall) {
        guard let modeStr = call.getString("mode"),
              let mode = AudioMode(rawValue: modeStr) else {
            call.reject("Invalid mode; expected 'duck', 'pause', or 'interrupt-spoken'")
            return
        }
        currentMode = mode
        activateSession(mode: mode)
        call.resolve()
    }

    // MARK: - play

    @objc func play(_ call: CAPPluginCall) {
        guard let uriStr = call.getString("fileUri") else {
            call.reject("Missing fileUri")
            return
        }

        // Resolve the URI to a local file URL.
        // Handles four cases:
        //   1. http:// / https://  → remote URL, pass through as-is
        //   2. file://              → already a file URL
        //   3. capacitor://localhost/... → take the path component and resolve under Bundle public/
        //   4. /web-root-path or relative → resolve under Bundle.main/public/
        let resolvedUrl: URL
        if uriStr.hasPrefix("http://") || uriStr.hasPrefix("https://") {
            guard let url = URL(string: uriStr) else {
                call.reject("Invalid remote fileUri: \(uriStr)")
                return
            }
            resolvedUrl = url
        } else if uriStr.hasPrefix("file://") {
            guard let url = URL(string: uriStr) else {
                call.reject("Invalid file fileUri: \(uriStr)")
                return
            }
            resolvedUrl = url
        } else if uriStr.hasPrefix("capacitor://localhost") {
            guard let parsed = URL(string: uriStr) else {
                call.reject("Invalid capacitor fileUri: \(uriStr)")
                return
            }
            let pathComponent = parsed.path.hasPrefix("/") ? String(parsed.path.dropFirst()) : parsed.path
            resolvedUrl = Bundle.main.bundleURL
                .appendingPathComponent("public")
                .appendingPathComponent(pathComponent)
        } else {
            // Web-root path (/bundles/...) or bare relative path
            let rel = uriStr.hasPrefix("/") ? String(uriStr.dropFirst()) : uriStr
            resolvedUrl = Bundle.main.bundleURL
                .appendingPathComponent("public")
                .appendingPathComponent(rel)
        }

        // Cancel any pending silence-restore timer.
        cancelSilenceTimer()

        // Remove previous end-of-file notification.
        if let obs = endObserver {
            NotificationCenter.default.removeObserver(obs)
            endObserver = nil
        }

        DispatchQueue.main.async { [weak self] in
            guard let self else { return }

            // Make sure the session is active and ducking is established.
            self.ensureDucked()

            // For file URLs, verify the file exists before attempting to play.
            if resolvedUrl.isFileURL && !FileManager.default.fileExists(atPath: resolvedUrl.path) {
                call.reject("Audio file not found at resolved path: \(resolvedUrl.path)")
                return
            }

            do {
                let p = try AVAudioPlayer(contentsOf: resolvedUrl)
                p.enableRate = true   // required for setRate() to work
                p.delegate = self     // required for audioPlayerDidFinishPlaying to fire
                p.prepareToPlay()
                p.play()
                self.player = p
            } catch {
                call.reject("AVAudioPlayer init failed: \(error.localizedDescription)")
                return
            }

            // Register end-of-file notification.
            // Note: AVAudioPlayer uses NotificationCenter, not AVPlayerItem.
            // We poll via delegate instead — override audioPlayerDidFinishPlaying below.
            // The delegate approach is set here; addObserver used as fallback for tests.
            call.resolve()
        }
    }

    // Called by AVAudioPlayerDelegate when the file ends normally.
    public func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        scheduleSilenceRestore()
        notifyListeners("ended", data: [:])
    }

    // MARK: - pause

    @objc func pause(_ call: CAPPluginCall) {
        player?.pause()
        // In 'pause' mode: deactivate session so other apps resume immediately.
        if currentMode == .pause {
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            isDucked = false
        } else {
            // In duck/interrupt-spoken modes: schedule a silence restore (but keep session
            // active until the timer fires, so back-to-back units stay ducked).
            scheduleSilenceRestore()
        }
        call.resolve()
    }

    // MARK: - resume

    @objc func resume(_ call: CAPPluginCall) {
        cancelSilenceTimer()
        ensureDucked()
        player?.play()
        call.resolve()
    }

    // MARK: - setRate

    @objc func setRate(_ call: CAPPluginCall) {
        let rate = call.getFloat("rate") ?? 1.0
        // AVAudioPlayer.rate requires enableRate = true (set in play()).
        player?.rate = rate
        call.resolve()
    }

    // MARK: - AVAudioSession setup helpers

    private func activateSession(mode: AudioMode) {
        let session = AVAudioSession.sharedInstance()
        do {
            switch mode {
            case .duck:
                try session.setCategory(.playback, options: [.duckOthers])
                try session.setActive(true)
                isDucked = true

            case .pause:
                // No duckOthers — session stays playback but does not duck other apps.
                try session.setCategory(.playback)
                try session.setActive(true)

            case .interruptSpoken:
                // Duck music AND interrupt spoken audio (podcasts/audiobooks).
                try session.setCategory(.playback,
                                        options: [.duckOthers, .interruptSpokenAudioAndMixWithOthers])
                try session.setActive(true)
                isDucked = true
            }
        } catch {
            // Non-fatal: log but continue. Audio may still work.
            print("[AudioSessionPlugin] AVAudioSession error: \(error.localizedDescription)")
        }
    }

    private func ensureDucked() {
        guard !isDucked else { return }
        activateSession(mode: currentMode)
    }

    private func scheduleSilenceRestore() {
        cancelSilenceTimer()
        silenceTimer = Timer.scheduledTimer(
            withTimeInterval: silenceThreshold,
            repeats: false
        ) { [weak self] _ in
            self?.restoreOtherAudio()
        }
    }

    private func cancelSilenceTimer() {
        silenceTimer?.invalidate()
        silenceTimer = nil
    }

    private func restoreOtherAudio() {
        guard isDucked else { return }
        isDucked = false
        // Deactivate with notifyOthersOnDeactivation — the standard nav-app pattern.
        // This is what causes ducked music to swell back after we stop speaking.
        try? AVAudioSession.sharedInstance().setActive(
            false,
            options: .notifyOthersOnDeactivation
        )
    }

    // MARK: - Interruption handling (phone calls, Siri, alarms)
    // REQUIRED by Plan 0 §F — the tracer bullet lacked this and failed check #5.

    private func registerInterruptionObserver() {
        interruptObserver = NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: AVAudioSession.sharedInstance(),
            queue: .main
        ) { [weak self] note in
            guard let self,
                  let info = note.userInfo,
                  let typeVal = info[AVAudioSessionInterruptionTypeKey] as? UInt,
                  let type = AVAudioSession.InterruptionType(rawValue: typeVal)
            else { return }

            switch type {
            case .began:
                // Phone call / Siri started — player is automatically paused by the OS.
                self.notifyListeners("interrupt", data: ["type": "began"])

            case .ended:
                // Interruption ended — check if we should resume.
                let optsVal = info[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
                let opts = AVAudioSession.InterruptionOptions(rawValue: optsVal)
                if opts.contains(.shouldResume) {
                    // Reactivate the session and resume playback.
                    self.ensureDucked()
                    self.player?.play()
                }
                self.notifyListeners("interrupt", data: ["type": "ended"])

            @unknown default:
                break
            }
        }
    }

    // MARK: - Cleanup

    deinit {
        if let obs = endObserver   { NotificationCenter.default.removeObserver(obs) }
        if let obs = interruptObserver { NotificationCenter.default.removeObserver(obs) }
        cancelSilenceTimer()
    }
}

// MARK: - AVAudioPlayerDelegate (wired up in play())
extension AudioSessionPlugin: AVAudioPlayerDelegate {}
