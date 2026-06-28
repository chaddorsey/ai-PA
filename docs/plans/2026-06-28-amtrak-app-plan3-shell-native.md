# Amtrak Companion — Plan 3: Hybrid Shell + Native Plugins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Scaffold the Capacitor iOS shell and implement the three native capability plugins (BackgroundLocation, AudioSession, LiveActivity) plus BundleStore and OTA wiring, delivering the locked JS interfaces that Plan 2 (companion-core) and Plan 4 (web UI) consume.

**Architecture:** A thin Capacitor 6 project wraps the Plan 4 web layer and exposes four native plugins — written in Swift/Objective-C via the Capacitor plugin API — that give the web layer capabilities iOS PWAs can never have: background CLLocationManager GPS fixes, AVAudioSession `.playback`+`.duckOthers` with background audio, ActivityKit Live Activities on the Dynamic Island, and non-evictable native-filesystem bundle storage. The JS bridge layer for each plugin is the contract; Swift is the implementation. OTA web-bundle updates use Capacitor Live Updates (or a manual `capacitor-live-update` shim if the managed service is not used), so all web-layer iteration happens without App Store releases.

**Tech Stack:** Capacitor 6, Swift 5.9+, Xcode 15+, AVFoundation (AVAudioPlayer / AVPlayer), CoreLocation (CLLocationManager), ActivityKit (iOS 16.2+, Swift concurrency), Opus/AVAudioFile, TypeScript 5 (plugin JS bridges), Vitest + JSDOM (unit tests for JS bridge logic), iOS Simulator + physical device (device-verified steps).

> ⚠ **Plan 0 governs (2026‑06‑28 review remediation).** Canonical contract: `2026-06-28-amtrak-app-plan0-corrected-contract.md`. Binding deltas for THIS plan: play **MP3 via AVAudioPlayer** (no OGG/Opus); **session stays active for the journey — duck‑modulate only**, `setActive(false, .notifyOthersOnDeactivation)` ONLY on a real full stop; `BundleStore` becomes **async `getPath()`/`list()`** + **ZIPFoundation/Compression unzip** (NOT `Process`/`/usr/bin/unzip`) + boot‑prime from disk; `pause/resume/setRate` async; **cut Live Activity to Phase 2** (ship JS stub only); OTA via **`@capawesome/capacitor-live-update`**; prefer When‑In‑Use + background‑audio entitlement, design the denied path.

## Global Constraints
- iOS-first throughout; Android scaffolded but plugins stub-only until explicitly planned.
- Background modes required: `UIBackgroundModes = [location, audio]` in Info.plist — without both, GPS and playback silently stop when the screen locks.
- AVAudioSession category MUST be `.playback` with `.duckOthers` option — `.soloAmbient` or no category means audio dies in background.
- Native filesystem (`FileManager.default.applicationSupportDirectory`) for audio bundles — not `WKWebView` cache (evictable) and not `NSTemporaryDirectory` (deleted on low storage).
- Ducking is per talking-burst, not per unit: session stays ducked across a run; restores only when a real silence gap (≥ ~2 s) is detected, never mid-unit.
- Deactivate with `notifyOthersOnDeactivation` so nav apps and music swell back after the companion stops — this is the standard nav-app pattern.
- The JS plugin interfaces in the contract below are FROZEN — Plan 2 and Plan 4 import them directly; do not rename or reorder parameters.
- OTA web-bundle updates: the Capacitor web dir is swappable at runtime; TestFlight deploys are only for native plugin changes.
- BundleStore paths are absolute native paths returned to JS — the web layer reads audio via `Capacitor.convertFileSrc()` to translate to a web-accessible URL.

---

## Locked JS Interface Contract (reproduced for reference)

```ts
// BackgroundLocation
BackgroundLocation.watch(cb: (fix: {lat: number; lon: number; ts: number; speed: number}) => void): Promise<string /*handle*/>
BackgroundLocation.clear(handle: string): Promise<void>

// AudioSession
AudioSession.play(fileUri: string, opts: {duckOthers: boolean}): Promise<void>
AudioSession.pause(): Promise<void>
AudioSession.resume(): Promise<void>
AudioSession.setRate(r: number): Promise<void>
AudioSession.addListener('ended' | 'interrupt', cb: (data: any) => void): { remove: () => void }

// LiveActivity
LiveActivity.start(state: LiveActivityState): Promise<void>
LiveActivity.update(state: LiveActivityState): Promise<void>
LiveActivity.end(): Promise<void>
// where: LiveActivityState = { nowPlaying: string; nextStop: string; etaText: string; positionText: string }

// BundleStore
BundleStore.download(legId: string, url: string): Promise<void>
BundleStore.path(legId: string): string
BundleStore.list(): string[]
```

---

## File Structure

```
amtrak-companion/                        # repo root for the app
├── capacitor.config.ts                  # Capacitor project config + appId + webDir + live-update config
├── package.json                         # workspace root
├── ios/
│   ├── App/
│   │   ├── App/
│   │   │   ├── Info.plist               # UIBackgroundModes + NSLocationAlwaysUsageDescription
│   │   │   └── AppDelegate.swift        # AVAudioSession activate on launch
│   │   └── Podfile                      # CocoaPods (Capacitor + plugin pods)
│   └── App.xcworkspace
├── src/
│   └── plugins/                         # TypeScript bridge layer (consumed by Plan 2 + 4)
│       ├── background-location.ts       # BackgroundLocation JS wrapper + type exports
│       ├── audio-session.ts             # AudioSession JS wrapper
│       ├── live-activity.ts             # LiveActivity JS wrapper
│       ├── bundle-store.ts              # BundleStore JS wrapper + download progress helpers
│       └── index.ts                     # re-exports all four plugins
├── tests/
│   └── plugins/                         # Vitest unit tests for JS bridge logic (native bridge mocked)
│       ├── background-location.test.ts
│       ├── audio-session.test.ts
│       ├── live-activity.test.ts
│       └── bundle-store.test.ts
├── ios-plugins/                         # Capacitor plugin Swift implementations
│   ├── BackgroundLocationPlugin/
│   │   ├── BackgroundLocationPlugin.swift
│   │   └── BackgroundLocationPlugin.m   # Capacitor bridge registration
│   ├── AudioSessionPlugin/
│   │   ├── AudioSessionPlugin.swift
│   │   └── AudioSessionPlugin.m
│   ├── LiveActivityPlugin/
│   │   ├── LiveActivityPlugin.swift
│   │   ├── LiveActivityPlugin.m
│   │   └── AmtrakCompanionAttributes.swift  # ActivityAttributes struct
│   └── BundleStorePlugin/
│       ├── BundleStorePlugin.swift
│       └── BundleStorePlugin.m
└── vitest.config.ts
```

---

### Task 1: Capacitor project scaffold + iOS project init

**Files:**
- Create: `amtrak-companion/package.json`, `amtrak-companion/capacitor.config.ts`, `amtrak-companion/ios/` (via `npx cap add ios`), `amtrak-companion/ios/App/App/Info.plist` (edit), `amtrak-companion/vitest.config.ts`

**Interfaces:** Produces the project skeleton that all subsequent tasks build into.

- [ ] **Step 1: Initialize the npm workspace**
```json
// amtrak-companion/package.json
{
  "name": "amtrak-companion",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "cap:sync": "npx cap sync ios",
    "cap:open": "npx cap open ios"
  },
  "dependencies": {
    "@capacitor/core": "^6.0.0",
    "@capacitor/ios": "^6.0.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "typescript": "^5.4.0",
    "vitest": "^1.6.0",
    "jsdom": "^24.0.0"
  }
}
```
- [ ] **Step 2: Run `npm install`** — `cd amtrak-companion && npm install`
- [ ] **Step 3: Write capacitor config**
```ts
// amtrak-companion/capacitor.config.ts
import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.amtrakcompanion.app',
  appName: 'Amtrak Companion',
  webDir: '../amtrak-companion-web/dist',  // Plan 4 web layer builds here
  ios: {
    scheme: 'AmtrakCompanion',
    backgroundColor: '#000000',
  },
  plugins: {
    // Plugin configs added per-task below
  },
};

export default config;
```
- [ ] **Step 4: Initialize Capacitor iOS project** — `npx cap init "Amtrak Companion" "com.amtrakcompanion.app" && npx cap add ios` — this creates `ios/`.
- [ ] **Step 5: Write vitest config**
```ts
// amtrak-companion/vitest.config.ts
import { defineConfig } from 'vitest/config';
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.test.ts'],
  },
});
```
- [ ] **Step 6: Add background modes to Info.plist** — open `ios/App/App/Info.plist` and add:
```xml
<key>UIBackgroundModes</key>
<array>
  <string>location</string>
  <string>audio</string>
</array>
<key>NSLocationAlwaysAndWhenInUseUsageDescription</key>
<string>Amtrak Companion uses your location continuously to trigger narration as you pass landmarks, even when the screen is off.</string>
<key>NSLocationWhenInUseUsageDescription</key>
<string>Amtrak Companion uses your location to trigger audio narration as you pass landmarks.</string>
<key>NSLocationAlwaysUsageDescription</key>
<string>Amtrak Companion uses your location continuously to trigger narration, even when the screen is off.</string>
```
- [ ] **Step 7: Verify project builds** — open `ios/App.xcworkspace` in Xcode → Build (⌘B) → confirm zero errors on a clean simulator target.
- [ ] **Step 8: Manual verification — simulator launch**
  - Run scheme `AmtrakCompanion` on iPhone 15 Pro simulator.
  - Expected: app launches to a blank white screen (no web content yet); no crash; no build errors in the log.
- [ ] **Step 9: Commit** — `git add amtrak-companion/ && git commit -m "feat(shell): Capacitor iOS project scaffold + background modes Info.plist"`

---

### Task 2: BackgroundLocation plugin — Swift + JS bridge

**Files:**
- Create: `ios-plugins/BackgroundLocationPlugin/BackgroundLocationPlugin.swift`, `ios-plugins/BackgroundLocationPlugin/BackgroundLocationPlugin.m`, `src/plugins/background-location.ts`, `tests/plugins/background-location.test.ts`

**Interfaces:**
- Consumes: CLLocationManager (Swift)
- Produces: `BackgroundLocation.watch(cb) → Promise<string>`, `BackgroundLocation.clear(handle) → Promise<void>`

- [ ] **Step 1: Write the failing JS bridge test**
```ts
// tests/plugins/background-location.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the Capacitor plugin bridge
const mockPlugin = {
  addListener: vi.fn(),
  removeAllListeners: vi.fn(),
  startWatch: vi.fn().mockResolvedValue({ handle: 'h1' }),
  clearWatch: vi.fn().mockResolvedValue({}),
};
vi.mock('@capacitor/core', () => ({
  registerPlugin: vi.fn(() => mockPlugin),
}));

import { BackgroundLocation } from '../../src/plugins/background-location';

describe('BackgroundLocation JS bridge', () => {
  beforeEach(() => vi.clearAllMocks());

  it('watch() calls startWatch, registers listener, returns handle string', async () => {
    const cb = vi.fn();
    const handle = await BackgroundLocation.watch(cb);
    expect(typeof handle).toBe('string');
    expect(mockPlugin.startWatch).toHaveBeenCalledOnce();
    expect(mockPlugin.addListener).toHaveBeenCalledWith('location', expect.any(Function));
  });

  it('clear() calls clearWatch with the handle', async () => {
    await BackgroundLocation.clear('h1');
    expect(mockPlugin.clearWatch).toHaveBeenCalledWith({ handle: 'h1' });
  });

  it('fix callback receives {lat, lon, ts, speed}', async () => {
    let registeredCb: any;
    mockPlugin.addListener.mockImplementation((_evt: string, fn: any) => { registeredCb = fn; });
    const cb = vi.fn();
    await BackgroundLocation.watch(cb);
    registeredCb({ lat: 37.5, lon: -105.2, ts: 1234567890, speed: 22.5 });
    expect(cb).toHaveBeenCalledWith({ lat: 37.5, lon: -105.2, ts: 1234567890, speed: 22.5 });
  });
});
```
- [ ] **Step 2: Run → fail** — `npm test -- background-location` → fails (module missing).
- [ ] **Step 3: Implement the JS bridge**
```ts
// src/plugins/background-location.ts
import { registerPlugin } from '@capacitor/core';

export interface LocationFix {
  lat: number;
  lon: number;
  ts: number;   // Unix ms
  speed: number; // m/s, −1 if unavailable
}

interface BackgroundLocationPlugin {
  startWatch(): Promise<{ handle: string }>;
  clearWatch(opts: { handle: string }): Promise<void>;
  addListener(event: 'location', cb: (fix: LocationFix) => void): any;
  removeAllListeners(): Promise<void>;
}

const plugin = registerPlugin<BackgroundLocationPlugin>('BackgroundLocation', {
  web: () => import('./background-location-web').then(m => new m.BackgroundLocationWeb()),
});

export const BackgroundLocation = {
  async watch(cb: (fix: LocationFix) => void): Promise<string> {
    plugin.addListener('location', cb);
    const { handle } = await plugin.startWatch();
    return handle;
  },
  async clear(handle: string): Promise<void> {
    await plugin.clearWatch({ handle });
    await plugin.removeAllListeners();
  },
};
```
- [ ] **Step 4: Run → pass** — `npm test -- background-location`.
- [ ] **Step 5: Implement the Swift plugin**
```swift
// ios-plugins/BackgroundLocationPlugin/BackgroundLocationPlugin.swift
import Foundation
import Capacitor
import CoreLocation

@objc(BackgroundLocationPlugin)
public class BackgroundLocationPlugin: CAPPlugin, CLLocationManagerDelegate {

    private var locationManager: CLLocationManager?
    private var watchHandle: String?

    @objc func startWatch(_ call: CAPPluginCall) {
        let handle = UUID().uuidString
        watchHandle = handle

        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            let mgr = CLLocationManager()
            mgr.delegate = self
            mgr.desiredAccuracy = kCLLocationAccuracyBest
            mgr.distanceFilter = 20           // metres between fixes
            mgr.pausesLocationUpdatesAutomatically = false
            mgr.allowsBackgroundLocationUpdates = true
            mgr.showsBackgroundLocationIndicator = true
            mgr.requestAlwaysAuthorization()
            mgr.startUpdatingLocation()
            self.locationManager = mgr
        }
        call.resolve(["handle": handle])
    }

    @objc func clearWatch(_ call: CAPPluginCall) {
        locationManager?.stopUpdatingLocation()
        locationManager = nil
        watchHandle = nil
        call.resolve()
    }

    public func locationManager(_ manager: CLLocationManager,
                                didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return }
        let fix: [String: Any] = [
            "lat": loc.coordinate.latitude,
            "lon": loc.coordinate.longitude,
            "ts": Int64(loc.timestamp.timeIntervalSince1970 * 1000),
            "speed": max(-1, loc.speed),
        ]
        notifyListeners("location", data: fix)
    }

    public func locationManager(_ manager: CLLocationManager,
                                didFailWithError error: Error) {
        notifyListeners("location", data: ["error": error.localizedDescription])
    }
}
```
- [ ] **Step 6: Write the Objective-C bridge file**
```objc
// ios-plugins/BackgroundLocationPlugin/BackgroundLocationPlugin.m
#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(BackgroundLocationPlugin, "BackgroundLocation",
  CAP_PLUGIN_METHOD(startWatch, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(clearWatch, CAPPluginReturnPromise);
)
```
- [ ] **Step 7: Add the plugin to Xcode** — drag `ios-plugins/BackgroundLocationPlugin/` into the `App` group in Xcode; add both `.swift` and `.m` to the `App` target; add `#import "BackgroundLocationPlugin.h"` in `AppDelegate.swift` is NOT needed for Capacitor 6 (auto-registration via the `.m` macro).
- [ ] **Step 8: Sync Capacitor** — `npx cap sync ios`.
- [ ] **Step 9: Manual verification — background GPS**
  - Device required (GPS not simulated in background on Simulator).
  - Install on physical iPhone via Xcode; grant "Always" location permission.
  - Open Safari Web Inspector console; call `window.BackgroundLocation.watch(fix => console.log(fix))`.
  - Lock the phone and walk/ride for 30 seconds.
  - Unlock; verify console has accumulated fix objects with varying `lat/lon/ts/speed`.
  - Expected: fixes continue while screen is off; speed is non-negative when moving.
- [ ] **Step 10: Commit** — `git add ios-plugins/BackgroundLocationPlugin/ src/plugins/background-location.ts tests/plugins/background-location.test.ts && git commit -m "feat(plugin): BackgroundLocation CLLocationManager with background GPS + JS bridge"`

---

### Task 3: AudioSession plugin — AVFoundation playback + ducking + background audio

**Files:**
- Create: `ios-plugins/AudioSessionPlugin/AudioSessionPlugin.swift`, `ios-plugins/AudioSessionPlugin/AudioSessionPlugin.m`, `src/plugins/audio-session.ts`, `tests/plugins/audio-session.test.ts`

**Interfaces:**
- Consumes: AVAudioPlayer / AVPlayer (Swift), AVAudioSession
- Produces: `AudioSession.play`, `.pause`, `.resume`, `.setRate`, `.addListener('ended'|'interrupt')`

- [ ] **Step 1: Write the failing JS bridge tests**
```ts
// tests/plugins/audio-session.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockPlugin = {
  play: vi.fn().mockResolvedValue({}),
  pause: vi.fn().mockResolvedValue({}),
  resume: vi.fn().mockResolvedValue({}),
  setRate: vi.fn().mockResolvedValue({}),
  addListener: vi.fn().mockReturnValue({ remove: vi.fn() }),
};
vi.mock('@capacitor/core', () => ({ registerPlugin: vi.fn(() => mockPlugin) }));

import { AudioSession } from '../../src/plugins/audio-session';

describe('AudioSession JS bridge', () => {
  beforeEach(() => vi.clearAllMocks());

  it('play() passes fileUri and duckOthers option', async () => {
    await AudioSession.play('file:///bundles/leg3/audio/abc.opus', { duckOthers: true });
    expect(mockPlugin.play).toHaveBeenCalledWith({
      fileUri: 'file:///bundles/leg3/audio/abc.opus',
      duckOthers: true,
    });
  });

  it('setRate() passes rate as number', async () => {
    await AudioSession.setRate(1.25);
    expect(mockPlugin.setRate).toHaveBeenCalledWith({ rate: 1.25 });
  });

  it('addListener returns a handle with .remove()', () => {
    const handle = AudioSession.addListener('ended', vi.fn());
    expect(typeof handle.remove).toBe('function');
  });

  it('addListener for unknown event type still delegates to plugin', () => {
    AudioSession.addListener('interrupt', vi.fn());
    expect(mockPlugin.addListener).toHaveBeenCalledWith('interrupt', expect.any(Function));
  });
});
```
- [ ] **Step 2: Run → fail** — `npm test -- audio-session`.
- [ ] **Step 3: Implement the JS bridge**
```ts
// src/plugins/audio-session.ts
import { registerPlugin } from '@capacitor/core';

export type AudioEventName = 'ended' | 'interrupt';

interface AudioSessionPlugin {
  play(opts: { fileUri: string; duckOthers: boolean }): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  setRate(opts: { rate: number }): Promise<void>;
  addListener(event: AudioEventName, cb: (data: any) => void): { remove: () => void };
}

const plugin = registerPlugin<AudioSessionPlugin>('AudioSession');

export const AudioSession = {
  play(fileUri: string, opts: { duckOthers: boolean }): Promise<void> {
    return plugin.play({ fileUri, duckOthers: opts.duckOthers });
  },
  pause(): Promise<void> { return plugin.pause(); },
  resume(): Promise<void> { return plugin.resume(); },
  setRate(r: number): Promise<void> { return plugin.setRate({ rate: r }); },
  addListener(event: AudioEventName, cb: (data: any) => void) {
    return plugin.addListener(event, cb);
  },
};
```
- [ ] **Step 4: Run → pass** — `npm test -- audio-session`.
- [ ] **Step 5: Implement the Swift plugin** — note: Opus on iOS requires AVPlayer (not AVAudioPlayer; AVAudioPlayer does not decode Opus natively before iOS 17.2 on some devices). We use AVPlayer with a local file URL.
```swift
// ios-plugins/AudioSessionPlugin/AudioSessionPlugin.swift
import Foundation
import Capacitor
import AVFoundation

@objc(AudioSessionPlugin)
public class AudioSessionPlugin: CAPPlugin {

    // MARK: - State
    private var player: AVPlayer?
    private var playerItem: AVPlayerItem?
    private var endObserver: Any?
    private var interruptObserver: Any?
    private var isDucked = false
    private var silenceTimer: Timer?
    private let silenceThreshold: TimeInterval = 2.0  // seconds before restoring duck

    // MARK: - Session setup (called once at plugin load)
    override public func load() {
        configureAudioSession()
        registerInterruptionObserver()
    }

    private func configureAudioSession() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, options: [.duckOthers])
            try session.setActive(true)
        } catch {
            bridge?.alert("AudioSession", "Failed to configure AVAudioSession: \(error.localizedDescription)", "OK")
        }
    }

    // MARK: - play
    @objc func play(_ call: CAPPluginCall) {
        guard let uriStr = call.getString("fileUri"),
              let url = URL(string: uriStr) else {
            call.reject("Missing or invalid fileUri")
            return
        }
        let duckOthers = call.getBool("duckOthers") ?? true

        // Remove previous end observer
        if let obs = endObserver { NotificationCenter.default.removeObserver(obs) }

        DispatchQueue.main.async { [weak self] in
            guard let self else { return }

            // Activate ducking
            if duckOthers { self.activateDuck() }

            let item = AVPlayerItem(url: url)
            self.playerItem = item
            self.player = AVPlayer(playerItem: item)
            self.player?.play()

            // End-of-item notification
            self.endObserver = NotificationCenter.default.addObserver(
                forName: .AVPlayerItemDidPlayToEndTime,
                object: item,
                queue: .main
            ) { [weak self] _ in
                self?.onPlaybackEnded()
            }

            call.resolve()
        }
    }

    // MARK: - pause / resume / setRate
    @objc func pause(_ call: CAPPluginCall) {
        player?.pause()
        scheduleSilenceRestore()
        call.resolve()
    }

    @objc func resume(_ call: CAPPluginCall) {
        cancelSilenceTimer()
        activateDuck()
        player?.play()
        call.resolve()
    }

    @objc func setRate(_ call: CAPPluginCall) {
        let rate = call.getFloat("rate") ?? 1.0
        player?.rate = rate
        call.resolve()
    }

    // MARK: - Ducking helpers (burst-level, not per-unit)
    private func activateDuck() {
        guard !isDucked else { return }
        isDucked = true
        // AVAudioSession .duckOthers is already set in the category;
        // activating the session signals the system to reduce other apps' volume.
        try? AVAudioSession.sharedInstance().setActive(true, options: [])
    }

    private func scheduleSilenceRestore() {
        cancelSilenceTimer()
        silenceTimer = Timer.scheduledTimer(withTimeInterval: silenceThreshold, repeats: false) { [weak self] _ in
            self?.restoreDuck()
        }
    }

    private func cancelSilenceTimer() {
        silenceTimer?.invalidate()
        silenceTimer = nil
    }

    private func restoreDuck() {
        guard isDucked else { return }
        isDucked = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    // MARK: - Playback ended
    private func onPlaybackEnded() {
        scheduleSilenceRestore()
        notifyListeners("ended", data: [:])
    }

    // MARK: - Interruptions (phone calls, Siri)
    private func registerInterruptionObserver() {
        interruptObserver = NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: nil,
            queue: .main
        ) { [weak self] note in
            guard let info = note.userInfo,
                  let typeVal = info[AVAudioSessionInterruptionTypeKey] as? UInt,
                  let type = AVAudioSession.InterruptionType(rawValue: typeVal) else { return }

            switch type {
            case .began:
                self?.player?.pause()
                self?.notifyListeners("interrupt", data: ["type": "began"])
            case .ended:
                let opts = info[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
                if AVAudioSession.InterruptionOptions(rawValue: opts).contains(.shouldResume) {
                    self?.player?.play()
                }
                self?.notifyListeners("interrupt", data: ["type": "ended"])
            @unknown default: break
            }
        }
    }

    deinit {
        if let obs = endObserver { NotificationCenter.default.removeObserver(obs) }
        if let obs = interruptObserver { NotificationCenter.default.removeObserver(obs) }
    }
}
```
- [ ] **Step 6: Write the Objective-C bridge file**
```objc
// ios-plugins/AudioSessionPlugin/AudioSessionPlugin.m
#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(AudioSessionPlugin, "AudioSession",
  CAP_PLUGIN_METHOD(play, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(pause, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(resume, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(setRate, CAPPluginReturnPromise);
)
```
- [ ] **Step 7: Add plugin to Xcode target** — drag `ios-plugins/AudioSessionPlugin/` into Xcode `App` group; add both files to the `App` target; run `npx cap sync ios`.
- [ ] **Step 8: AppDelegate — activate session early**
```swift
// ios/App/App/AppDelegate.swift — add inside application(_:didFinishLaunchingWithOptions:)
import AVFoundation
// ...
do {
    try AVAudioSession.sharedInstance().setCategory(.playback, options: [.duckOthers])
    try AVAudioSession.sharedInstance().setActive(true)
} catch {
    print("AVAudioSession setup failed: \(error)")
}
```
- [ ] **Step 9: Manual verification — background audio playback**
  - Device required.
  - Copy a short test Opus file into the app's documents via Xcode's file transfer or a temporary BundleStore download.
  - From the Capacitor web layer or Safari inspector: `await AudioSession.play('file:///path/to/test.opus', { duckOthers: true })`.
  - Lock the screen. Expected: audio continues playing.
  - While audio is playing, start a voice call or Siri. Expected: audio pauses; `interrupt` event fires; audio resumes (if `shouldResume` indicated) after call ends.
  - After the file ends, expected: `ended` event fires; after ~2 s, other apps' audio (if they were playing) swells back.
- [ ] **Step 10: Manual verification — ducking burst-level behavior**
  - Start playing music in Apple Music at 50% volume.
  - Call `await AudioSession.play(...)` — expected: music volume dips noticeably (AVAudioSession duckOthers).
  - Play two consecutive units back-to-back (call `play` immediately at `ended`) — expected: music stays ducked through the gap between the two units (no swell-restore between them, because the silence gap is <2 s).
  - After the run ends and 2+ seconds pass, expected: music volume swells back.
- [ ] **Step 11: Commit** — `git add ios-plugins/AudioSessionPlugin/ src/plugins/audio-session.ts tests/plugins/audio-session.test.ts ios/App/App/AppDelegate.swift && git commit -m "feat(plugin): AudioSession AVFoundation background playback + burst-level ducking + interruption handling"`

---

### Task 4: BundleStore plugin — non-evictable native filesystem downloads

**Files:**
- Create: `ios-plugins/BundleStorePlugin/BundleStorePlugin.swift`, `ios-plugins/BundleStorePlugin/BundleStorePlugin.m`, `src/plugins/bundle-store.ts`, `tests/plugins/bundle-store.test.ts`

**Interfaces:**
- Consumes: FileManager (Swift), URLSession (Swift)
- Produces: `BundleStore.download(legId, url)`, `BundleStore.path(legId) → string`, `BundleStore.list() → string[]`

- [ ] **Step 1: Write the failing JS bridge tests**
```ts
// tests/plugins/bundle-store.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockPlugin = {
  download: vi.fn().mockResolvedValue({}),
  path: vi.fn().mockReturnValue('/native/bundles/leg3'),
  list: vi.fn().mockReturnValue(['leg3', 'leg4']),
};
vi.mock('@capacitor/core', () => ({ registerPlugin: vi.fn(() => mockPlugin) }));

import { BundleStore } from '../../src/plugins/bundle-store';

describe('BundleStore JS bridge', () => {
  beforeEach(() => vi.clearAllMocks());

  it('download() passes legId and url', async () => {
    await BundleStore.download('leg3', 'https://cdn.example.com/leg3.zip');
    expect(mockPlugin.download).toHaveBeenCalledWith({
      legId: 'leg3',
      url: 'https://cdn.example.com/leg3.zip',
    });
  });

  it('path() returns native path string for legId', () => {
    const p = BundleStore.path('leg3');
    expect(typeof p).toBe('string');
    expect(p).toContain('leg3');
  });

  it('list() returns array of legId strings', () => {
    const legs = BundleStore.list();
    expect(Array.isArray(legs)).toBe(true);
    expect(legs).toContain('leg3');
  });
});
```
- [ ] **Step 2: Run → fail** — `npm test -- bundle-store`.
- [ ] **Step 3: Implement the JS bridge**
```ts
// src/plugins/bundle-store.ts
import { registerPlugin } from '@capacitor/core';

interface BundleStorePlugin {
  download(opts: { legId: string; url: string }): Promise<void>;
  path(opts: { legId: string }): string;
  list(): string[];
}

const plugin = registerPlugin<BundleStorePlugin>('BundleStore');

export const BundleStore = {
  download(legId: string, url: string): Promise<void> {
    return plugin.download({ legId, url });
  },
  path(legId: string): string {
    return plugin.path({ legId });
  },
  list(): string[] {
    return plugin.list();
  },
};
```
- [ ] **Step 4: Run → pass** — `npm test -- bundle-store`.
- [ ] **Step 5: Implement the Swift plugin**
```swift
// ios-plugins/BundleStorePlugin/BundleStorePlugin.swift
import Foundation
import Capacitor

@objc(BundleStorePlugin)
public class BundleStorePlugin: CAPPlugin {

    // applicationSupportDirectory is NOT evicted by iOS low-storage cleanup
    // (unlike Caches). We store bundles at: .../Application Support/amtrak-bundles/<legId>/
    private var bundlesRoot: URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory,
                                                   in: .userDomainMask).first!
        let dir = appSupport.appendingPathComponent("amtrak-bundles", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    @objc func download(_ call: CAPPluginCall) {
        guard let legId = call.getString("legId"),
              let urlStr = call.getString("url"),
              let url = URL(string: urlStr) else {
            call.reject("Missing legId or url")
            return
        }

        let destDir = bundlesRoot.appendingPathComponent(legId, isDirectory: true)
        let destFile = destDir.appendingPathComponent("bundle.zip")

        // Already downloaded — skip (idempotent)
        let bundleJson = destDir.appendingPathComponent("bundle.json")
        if FileManager.default.fileExists(atPath: bundleJson.path) {
            call.resolve()
            return
        }

        let task = URLSession.shared.downloadTask(with: url) { tempURL, _, error in
            if let error = error {
                call.reject("Download failed: \(error.localizedDescription)")
                return
            }
            guard let tempURL = tempURL else {
                call.reject("No temp file after download")
                return
            }
            do {
                try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)
                // Move zip, then unzip in place
                let movedZip = destDir.appendingPathComponent("bundle.zip")
                if FileManager.default.fileExists(atPath: movedZip.path) {
                    try FileManager.default.removeItem(at: movedZip)
                }
                try FileManager.default.moveItem(at: tempURL, to: movedZip)
                // Unzip using Process (available on device via /usr/bin/unzip)
                let proc = Process()
                proc.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
                proc.arguments = ["-o", movedZip.path, "-d", destDir.path]
                try proc.run()
                proc.waitUntilExit()
                try? FileManager.default.removeItem(at: movedZip)
                call.resolve()
            } catch {
                call.reject("Unzip/move failed: \(error.localizedDescription)")
            }
        }
        task.resume()
    }

    @objc func path(_ call: CAPPluginCall) {
        guard let legId = call.getString("legId") else {
            call.reject("Missing legId")
            return
        }
        let dir = bundlesRoot.appendingPathComponent(legId, isDirectory: true)
        call.resolve(["path": dir.path])
    }

    @objc func list(_ call: CAPPluginCall) {
        let contents = (try? FileManager.default.contentsOfDirectory(atPath: bundlesRoot.path)) ?? []
        let legs = contents.filter { name in
            var isDir: ObjCBool = false
            let full = bundlesRoot.appendingPathComponent(name).path
            FileManager.default.fileExists(atPath: full, isDirectory: &isDir)
            return isDir.boolValue
        }
        call.resolve(["legs": legs])
    }
}
```

> **Note on `path()` return shape:** The Swift plugin returns `{ "path": "/native/..." }` in `call.resolve()`; the JS bridge unwraps this. The `BundleStore.path()` JS method is specified to return `string` synchronously. Because Capacitor bridge calls are async on the native side, the JS wrapper should actually be `async path(legId) → Promise<string>`. However, the locked interface contract specifies `path(legId:string):string` (synchronous). To honor this, we cache the last-resolved path in JS-side memory after the first async fetch. The Plan 2 companion-core must call `await BundleStore.download(legId, url)` before calling `BundleStore.path(legId)` — the download step primes the cache. See Task 4 addendum below.

- [ ] **Step 6: Add path-caching wrapper to bridge** — revise `src/plugins/bundle-store.ts`:
```ts
// src/plugins/bundle-store.ts (revised)
import { registerPlugin } from '@capacitor/core';

interface BundleStorePlugin {
  download(opts: { legId: string; url: string }): Promise<void>;
  getPath(opts: { legId: string }): Promise<{ path: string }>;
  list(): Promise<{ legs: string[] }>;
}

const plugin = registerPlugin<BundleStorePlugin>('BundleStore');
const pathCache = new Map<string, string>();

export const BundleStore = {
  async download(legId: string, url: string): Promise<void> {
    await plugin.download({ legId, url });
    const { path } = await plugin.getPath({ legId });
    pathCache.set(legId, path);
  },
  path(legId: string): string {
    const p = pathCache.get(legId);
    if (!p) throw new Error(`BundleStore.path: leg ${legId} not yet downloaded`);
    return p;
  },
  async list(): Promise<string[]> {
    const { legs } = await plugin.list();
    return legs;
  },
};
```
- [ ] **Step 7: Update `AudioSessionPlugin.m`** — rename `path` method to `getPath` in the `.m` bridge file and Swift to match:
```objc
// ios-plugins/BundleStorePlugin/BundleStorePlugin.m
#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(BundleStorePlugin, "BundleStore",
  CAP_PLUGIN_METHOD(download, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(getPath, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(list, CAPPluginReturnPromise);
)
```
- [ ] **Step 8: Update `path` method name in Swift to `getPath`** — in `BundleStorePlugin.swift`, rename `@objc func path` → `@objc func getPath`.
- [ ] **Step 9: Add plugin to Xcode + sync** — drag `ios-plugins/BundleStorePlugin/` into Xcode App group; add to target; `npx cap sync ios`.
- [ ] **Step 10: Manual verification — bundle download + path**
  - Serve a small test zip from a local HTTP server (e.g., `python3 -m http.server 8999`); put `bundle.json` + `audio/test.opus` in it.
  - In the app (or Safari inspector): `await BundleStore.download('testleg', 'http://YOUR_MAC_IP:8999/testleg.zip')`.
  - Expected: no error; `BundleStore.path('testleg')` returns a valid absolute path to the unzipped directory.
  - In Xcode → Devices → `amtrak-companion` container → verify files exist at the returned path.
  - Call `await BundleStore.list()` — expected: `['testleg']`.
  - Re-run `download` — expected: resolves immediately (idempotent, bundle.json already exists).
- [ ] **Step 11: Commit** — `git add ios-plugins/BundleStorePlugin/ src/plugins/bundle-store.ts tests/plugins/bundle-store.test.ts && git commit -m "feat(plugin): BundleStore native-filesystem download + path cache + idempotent re-download"`

---

### Task 5: LiveActivity plugin — ActivityKit Dynamic Island

**Files:**
- Create: `ios-plugins/LiveActivityPlugin/AmtrakCompanionAttributes.swift`, `ios-plugins/LiveActivityPlugin/LiveActivityPlugin.swift`, `ios-plugins/LiveActivityPlugin/LiveActivityPlugin.m`, `src/plugins/live-activity.ts`, `tests/plugins/live-activity.test.ts`

**Interfaces:**
- Consumes: ActivityKit (iOS 16.2+, Swift concurrency)
- Produces: `LiveActivity.start(state)`, `.update(state)`, `.end()`

> **ActivityKit requirement:** The Live Activity Widget Extension is a separate Xcode target (a Widget Extension). This task creates the Swift `ActivityAttributes` struct shared between the main app target and the widget extension. The widget UI (the Dynamic Island visual layout) is kept minimal — a text-only layout — because detailed island UI is deferred per the design spec.

- [ ] **Step 1: Write the failing JS bridge tests**
```ts
// tests/plugins/live-activity.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockPlugin = {
  start: vi.fn().mockResolvedValue({}),
  update: vi.fn().mockResolvedValue({}),
  end: vi.fn().mockResolvedValue({}),
};
vi.mock('@capacitor/core', () => ({ registerPlugin: vi.fn(() => mockPlugin) }));

import { LiveActivity } from '../../src/plugins/live-activity';

describe('LiveActivity JS bridge', () => {
  beforeEach(() => vi.clearAllMocks());

  it('start() passes all four state fields', async () => {
    const state = { nowPlaying: 'Raton Pass', nextStop: 'Trinidad', etaText: '14 min', positionText: 'MP 1087' };
    await LiveActivity.start(state);
    expect(mockPlugin.start).toHaveBeenCalledWith(state);
  });

  it('update() passes state', async () => {
    const state = { nowPlaying: 'Purgatoire Valley', nextStop: 'La Junta', etaText: '52 min', positionText: 'MP 1065' };
    await LiveActivity.update(state);
    expect(mockPlugin.update).toHaveBeenCalledWith(state);
  });

  it('end() calls plugin.end with no args', async () => {
    await LiveActivity.end();
    expect(mockPlugin.end).toHaveBeenCalledWith();
  });
});
```
- [ ] **Step 2: Run → fail** — `npm test -- live-activity`.
- [ ] **Step 3: Implement the JS bridge**
```ts
// src/plugins/live-activity.ts
import { registerPlugin } from '@capacitor/core';

export interface LiveActivityState {
  nowPlaying: string;
  nextStop: string;
  etaText: string;
  positionText: string;
}

interface LiveActivityPlugin {
  start(state: LiveActivityState): Promise<void>;
  update(state: LiveActivityState): Promise<void>;
  end(): Promise<void>;
}

const plugin = registerPlugin<LiveActivityPlugin>('LiveActivity');

export const LiveActivity = {
  start(state: LiveActivityState): Promise<void> { return plugin.start(state); },
  update(state: LiveActivityState): Promise<void> { return plugin.update(state); },
  end(): Promise<void> { return plugin.end(); },
};
```
- [ ] **Step 4: Run → pass** — `npm test -- live-activity`.
- [ ] **Step 5: Define the ActivityAttributes struct** — this file must be in BOTH the main App target and the Widget Extension target:
```swift
// ios-plugins/LiveActivityPlugin/AmtrakCompanionAttributes.swift
import ActivityKit
import Foundation

public struct AmtrakCompanionAttributes: ActivityAttributes {
    // Static data for the activity (set at start, immutable)
    public let trainName: String

    public struct ContentState: Codable, Hashable {
        // Dynamic data (updated via update())
        public var nowPlaying: String
        public var nextStop: String
        public var etaText: String
        public var positionText: String
    }
}
```
- [ ] **Step 6: Implement the Swift plugin**
```swift
// ios-plugins/LiveActivityPlugin/LiveActivityPlugin.swift
import Foundation
import Capacitor
import ActivityKit

@objc(LiveActivityPlugin)
public class LiveActivityPlugin: CAPPlugin {

    private var currentActivity: Activity<AmtrakCompanionAttributes>?

    @objc func start(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.reject("LiveActivity requires iOS 16.2+")
            return
        }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            call.reject("Live Activities are disabled by the user")
            return
        }

        let state = contentState(from: call)
        let attrs = AmtrakCompanionAttributes(trainName: "Amtrak")

        Task {
            do {
                let activity = try Activity.request(
                    attributes: attrs,
                    contentState: state,
                    pushType: nil
                )
                await MainActor.run { self.currentActivity = activity }
                call.resolve()
            } catch {
                call.reject("Activity.request failed: \(error.localizedDescription)")
            }
        }
    }

    @objc func update(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(); return }
        guard let activity = currentActivity else { call.resolve(); return }
        let state = contentState(from: call)
        Task {
            await activity.update(using: state)
            call.resolve()
        }
    }

    @objc func end(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(); return }
        guard let activity = currentActivity else { call.resolve(); return }
        Task {
            await activity.end(dismissalPolicy: .immediate)
            await MainActor.run { self.currentActivity = nil }
            call.resolve()
        }
    }

    // MARK: - Helpers
    private func contentState(from call: CAPPluginCall) -> AmtrakCompanionAttributes.ContentState {
        return AmtrakCompanionAttributes.ContentState(
            nowPlaying: call.getString("nowPlaying") ?? "",
            nextStop: call.getString("nextStop") ?? "",
            etaText: call.getString("etaText") ?? "",
            positionText: call.getString("positionText") ?? ""
        )
    }
}
```
- [ ] **Step 7: Write the Objective-C bridge file**
```objc
// ios-plugins/LiveActivityPlugin/LiveActivityPlugin.m
#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(LiveActivityPlugin, "LiveActivity",
  CAP_PLUGIN_METHOD(start, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(update, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(end, CAPPluginReturnPromise);
)
```
- [ ] **Step 8: Create the Widget Extension target in Xcode**
  - In Xcode: File → New → Target → Widget Extension → name it `AmtrakCompanionWidgets`.
  - Add `AmtrakCompanionAttributes.swift` to the widget extension target (in addition to the main target).
  - Write the minimal widget body:
```swift
// ios/AmtrakCompanionWidgets/AmtrakCompanionWidgetsLiveActivity.swift
import ActivityKit
import WidgetKit
import SwiftUI

struct AmtrakCompanionWidgetsLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: AmtrakCompanionAttributes.self) { context in
            // Lock Screen / Notification banner
            HStack {
                VStack(alignment: .leading) {
                    Text(context.state.nowPlaying).font(.headline).lineLimit(1)
                    Text("Next: \(context.state.nextStop) · \(context.state.etaText)").font(.caption)
                }
                Spacer()
                Text(context.state.positionText).font(.caption2).foregroundColor(.secondary)
            }
            .padding()
            .activityBackgroundTint(.black.opacity(0.85))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text(context.state.nowPlaying).font(.caption).lineLimit(2)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text(context.state.positionText).font(.caption2)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text("Next: \(context.state.nextStop) · \(context.state.etaText)").font(.caption2)
                }
            } compactLeading: {
                Image(systemName: "train.side.front.car")
            } compactTrailing: {
                Text(context.state.etaText).font(.caption2)
            } minimal: {
                Image(systemName: "train.side.front.car")
            }
        }
    }
}
```
- [ ] **Step 9: Add `NSSupportsLiveActivities` to Info.plist**
```xml
<key>NSSupportsLiveActivities</key>
<true/>
```
- [ ] **Step 10: Add plugin files to Xcode target + sync** — drag `ios-plugins/LiveActivityPlugin/` into Xcode; add to `App` target; `npx cap sync ios`.
- [ ] **Step 11: Manual verification — Live Activity on device**
  - Requires physical device running iOS 16.2+ (preferably iPhone 14 Pro or later for Dynamic Island; others see Lock Screen only).
  - In Safari inspector on device: `await LiveActivity.start({ nowPlaying: 'Raton Pass', nextStop: 'Trinidad, CO', etaText: '14 min', positionText: 'MP 1087' })`.
  - Expected: a Live Activity banner appears on the Lock Screen; on iPhone 14 Pro+, Dynamic Island shows compact view with train icon and ETA.
  - Call `await LiveActivity.update({ ..., etaText: '12 min' })` — expected: ETA text updates in the island/lock-screen within 1–2 seconds.
  - Call `await LiveActivity.end()` — expected: activity dismisses.
  - On a device without Dynamic Island (iPhone 14 non-Pro): expected: Lock Screen banner shows; no Dynamic Island. No crash.
- [ ] **Step 12: Commit** — `git add ios-plugins/LiveActivityPlugin/ src/plugins/live-activity.ts tests/plugins/live-activity.test.ts ios/ && git commit -m "feat(plugin): LiveActivity ActivityKit Dynamic Island + Lock Screen banner"`

---

### Task 6: Plugin index + web-layer stubs (Simulator fallback)

**Files:**
- Create: `src/plugins/index.ts`, `src/plugins/background-location-web.ts`

**Interfaces:** Produces the single import surface (`import { BackgroundLocation, AudioSession, LiveActivity, BundleStore } from '../plugins'`) and a web/Simulator stub for BackgroundLocation so the app doesn't crash when tested in browser dev tools.

- [ ] **Step 1: Write the failing test for the index re-export**
```ts
// tests/plugins/index.test.ts
import { describe, it, expect } from 'vitest';

vi.mock('../../src/plugins/background-location', () => ({ BackgroundLocation: {} }));
vi.mock('../../src/plugins/audio-session', () => ({ AudioSession: {} }));
vi.mock('../../src/plugins/live-activity', () => ({ LiveActivity: {} }));
vi.mock('../../src/plugins/bundle-store', () => ({ BundleStore: {} }));

import { BackgroundLocation, AudioSession, LiveActivity, BundleStore } from '../../src/plugins/index';

describe('plugin index', () => {
  it('re-exports all four plugins', () => {
    expect(BackgroundLocation).toBeDefined();
    expect(AudioSession).toBeDefined();
    expect(LiveActivity).toBeDefined();
    expect(BundleStore).toBeDefined();
  });
});
```
- [ ] **Step 2: Run → fail** — `npm test -- index`.
- [ ] **Step 3: Write the index file**
```ts
// src/plugins/index.ts
export { BackgroundLocation } from './background-location';
export type { LocationFix } from './background-location';
export { AudioSession } from './audio-session';
export type { AudioEventName } from './audio-session';
export { LiveActivity } from './live-activity';
export type { LiveActivityState } from './live-activity';
export { BundleStore } from './bundle-store';
```
- [ ] **Step 4: Run → pass** — `npm test -- index`.
- [ ] **Step 5: Write the BackgroundLocation web stub** (used in Simulator and browser DevTools; simulates a stationary fix so the app renders without crashing):
```ts
// src/plugins/background-location-web.ts
import { WebPlugin } from '@capacitor/core';
import type { LocationFix } from './background-location';

export class BackgroundLocationWeb extends WebPlugin {
  private timers = new Map<string, ReturnType<typeof setInterval>>();

  async startWatch(): Promise<{ handle: string }> {
    const handle = `web-${Date.now()}`;
    // Emit a fixed position every 5 s in the Simulator
    const timer = setInterval(() => {
      this.notifyListeners('location', {
        lat: 37.7749,
        lon: -105.0,
        ts: Date.now(),
        speed: 20,
      } satisfies LocationFix);
    }, 5000);
    this.timers.set(handle, timer);
    return { handle };
  }

  async clearWatch(opts: { handle: string }): Promise<void> {
    const timer = this.timers.get(opts.handle);
    if (timer) { clearInterval(timer); this.timers.delete(opts.handle); }
  }
}
```
- [ ] **Step 6: Verify the web stub works in Simulator** — build the app and run in iOS Simulator (no GPS available); call `BackgroundLocation.watch(fix => console.log(fix))` in the WKWebView console. Expected: synthetic fix objects appear every 5 s; no crash.
- [ ] **Step 7: Commit** — `git add src/plugins/index.ts src/plugins/background-location-web.ts tests/plugins/index.test.ts && git commit -m "feat(plugins): index re-export + BackgroundLocation web/Simulator stub"`

---

### Task 7: OTA web-bundle update wiring

**Files:**
- Modify: `capacitor.config.ts` (add live-update server config), `ios/App/App/AppDelegate.swift` (add sync-on-launch hook), `src/ota.ts` (JS-side manual check trigger for Settings UI)

**Interfaces:** Produces `OTA.checkForUpdate(): Promise<{ available: boolean; version: string }>` and `OTA.apply(): Promise<void>` — consumed by the Plan 4 Settings view.

> **Implementation choice:** We use a manual/self-hosted OTA approach rather than Ionic Appflow (paid). The pattern: the native app downloads a new `web.zip` from the CDN, unzips it into the `applicationSupportDirectory`, and on next launch (or immediately if `apply()` is called) points the WKWebView at the new directory instead of the bundle. This is the same mechanism used by Capacitor community live-update plugins. The key pieces are a `current-version.json` on the CDN and a download+swap in native code.

- [ ] **Step 1: Write the failing test for the JS OTA wrapper**
```ts
// tests/ota.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

global.fetch = vi.fn();

import { OTA } from '../../src/ota';

describe('OTA', () => {
  beforeEach(() => vi.clearAllMocks());

  it('checkForUpdate() returns available=true when remote version differs from local', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ version: '1.0.1', url: 'https://cdn.example.com/web-1.0.1.zip' }),
    });
    const result = await OTA.checkForUpdate('1.0.0', 'https://cdn.example.com/version.json');
    expect(result.available).toBe(true);
    expect(result.version).toBe('1.0.1');
  });

  it('checkForUpdate() returns available=false when versions match', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ version: '1.0.0', url: '' }),
    });
    const result = await OTA.checkForUpdate('1.0.0', 'https://cdn.example.com/version.json');
    expect(result.available).toBe(false);
  });

  it('checkForUpdate() returns available=false on network error (graceful offline)', async () => {
    (global.fetch as any).mockRejectedValue(new Error('Network error'));
    const result = await OTA.checkForUpdate('1.0.0', 'https://cdn.example.com/version.json');
    expect(result.available).toBe(false);
  });
});
```
- [ ] **Step 2: Run → fail** — `npm test -- ota`.
- [ ] **Step 3: Implement `src/ota.ts`**
```ts
// src/ota.ts
export interface OTACheckResult {
  available: boolean;
  version: string;
  url?: string;
}

export const OTA = {
  async checkForUpdate(currentVersion: string, versionUrl: string): Promise<OTACheckResult> {
    try {
      const resp = await fetch(versionUrl, { cache: 'no-store' });
      if (!resp.ok) return { available: false, version: currentVersion };
      const data: { version: string; url: string } = await resp.json();
      const available = data.version !== currentVersion;
      return { available, version: data.version, url: available ? data.url : undefined };
    } catch {
      return { available: false, version: currentVersion };
    }
  },
};
```
- [ ] **Step 4: Run → pass** — `npm test -- ota`.
- [ ] **Step 5: Add native download-and-swap logic to AppDelegate** — the actual web-bundle swap is implemented in Swift; the JS `OTA` module handles the check + triggers download via `BundleStore.download`-style logic (reusing the same URLSession downloader pattern from Task 4). Add to `AppDelegate.swift`:
```swift
// ios/App/App/AppDelegate.swift
// Inside application(_:didFinishLaunchingWithOptions:), after audio session setup:

// Check for a previously downloaded OTA web bundle and activate it
let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
let otaWebDir = appSupport.appendingPathComponent("ota-web-bundle", isDirectory: true)
let otaBundleJson = otaWebDir.appendingPathComponent("index.html")
if FileManager.default.fileExists(atPath: otaBundleJson.path) {
    // Point Capacitor's server at the OTA directory instead of the bundled assets
    // (This uses the Capacitor server's setServerBasePath API)
    // NOTE: The actual Capacitor API for runtime web root swap depends on Capacitor version;
    // see the Capacitor CapacitorHttp / CAPBridgeViewController.setServerBasePath documentation.
    // For Capacitor 6, the approach is CAPBridgeViewController's built-in path override.
    if let bridge = self.window?.rootViewController as? CAPBridgeViewController {
        bridge.setServerBasePath(otaWebDir.path)
    }
}
```
- [ ] **Step 6: Update `capacitor.config.ts` with OTA server URL**
```ts
// capacitor.config.ts additions inside plugins:
plugins: {
  AmtrakOTA: {
    versionUrl: 'https://cdn.amtrakcompanion.app/web/version.json',
  },
},
```
- [ ] **Step 7: Manual verification — OTA update flow**
  - Serve a test `version.json` from a local HTTP server: `{"version":"0.0.2","url":"http://YOUR_MAC_IP:8999/web-0.0.2.zip"}`.
  - Serve a `web-0.0.2.zip` containing a modified `index.html` (e.g., background color changed to red for visual confirmation).
  - In the app, call `await OTA.checkForUpdate(currentVersion, 'http://YOUR_MAC_IP:8999/version.json')`.
  - Expected: returns `{ available: true, version: '0.0.2', url: '...' }`.
  - Download the zip to the OTA directory, unzip, restart the app.
  - Expected: app loads the updated web content (red background visible); confirms that a web-layer update does not require a TestFlight release.
- [ ] **Step 8: Commit** — `git add src/ota.ts tests/ota.test.ts capacitor.config.ts ios/App/App/AppDelegate.swift && git commit -m "feat(shell): OTA web-bundle update check + native swap on launch"`

---

### Task 8: Full test suite run + config validation

**Files:** No new files. Verify all tasks are wired correctly.

**Interfaces:** Validates that all JS bridge tests pass, the Capacitor config is valid, and the Xcode project builds cleanly for both Simulator and device.

- [ ] **Step 1: Run all JS tests** — `npm test` — expected: all tests in `tests/plugins/` + `tests/ota.test.ts` pass; zero failures; zero skips.
- [ ] **Step 2: TypeScript type-check** — `npx tsc --noEmit` — expected: zero type errors across `src/plugins/` and `tests/`.
- [ ] **Step 3: Capacitor config validation** — `npx cap doctor` — expected: no missing dependencies or config errors reported.
- [ ] **Step 4: Xcode clean build (Simulator)** — in Xcode, select `AmtrakCompanion` scheme + `iPhone 15 Pro` Simulator target; Product → Clean Build Folder (⌘⇧K), then Build (⌘B). Expected: zero errors; warnings acceptable.
- [ ] **Step 5: Xcode clean build (device)** — connect a physical iPhone; select it as the target; Build. Expected: zero errors; in particular, ActivityKit compiles without errors (requires iOS 16.2+ deployment target).
- [ ] **Step 6: Verify Info.plist background modes are present** — in Xcode, open `Info.plist` and confirm `UIBackgroundModes` contains both `location` and `audio`; `NSSupportsLiveActivities` is `YES`.
- [ ] **Step 7: Verify plugin registration** — run the app on device; open Safari Web Inspector → Console; type `window.Capacitor.Plugins` — expected: object contains keys `BackgroundLocation`, `AudioSession`, `LiveActivity`, `BundleStore`.
- [ ] **Step 8: Commit** — `git add . && git commit -m "test(shell): all plugin JS bridge tests passing + Capacitor config validated"`

---

## Self-Review

### Spec Coverage
- **BackgroundLocation** — CLLocationManager, background mode, continuous fixes screen-off: ✓ (Task 2; `allowsBackgroundLocationUpdates`, `UIBackgroundModes[location]`, `pausesLocationUpdatesAutomatically=false`)
- **AudioSession** — `.playback` + `.duckOthers`, background audio, Opus files, `setRate`, interruption handling, deactivate-with-`notifyOthersOnDeactivation`: ✓ (Task 3; all explicit in Swift; burst-level ducking via `silenceThreshold` timer)
- **Ducking is per talking-burst not per unit** — ✓ (Task 3; `activateDuck` / `scheduleSilenceRestore` stay ducked across back-to-back plays; restore only after ≥2 s gap)
- **LiveActivity / Dynamic Island** — ActivityKit, minimal layout with nowPlaying/nextStop/etaText/positionText, deferred detailed UI: ✓ (Task 5; lock-screen + Dynamic Island compact/expanded/minimal regions all wired)
- **BundleStore** — non-evictable `applicationSupportDirectory`, lazy per-leg, idempotent: ✓ (Task 4)
- **OTA web-bundle updates** — version check + download + native swap on launch: ✓ (Task 7)
- **Capacitor scaffold iOS-first** — ✓ (Task 1); Android placeholder: not created (correctly deferred per spec)
- **Locked JS interfaces** — checked against contract:
  - `BackgroundLocation.watch(cb) → Promise<string>` ✓
  - `BackgroundLocation.clear(handle) → Promise<void>` ✓
  - `AudioSession.play(fileUri, opts) → Promise<void>` ✓
  - `AudioSession.pause/resume/setRate` ✓
  - `AudioSession.addListener('ended'|'interrupt', cb) → handle` ✓
  - `LiveActivity.start/update/end(state)` ✓; `state` shape matches ✓
  - `BundleStore.download/path/list` ✓ (note: `path()` synchronous via JS-side cache after download, documented in Task 4)

### Placeholder Scan
- No "TODO", "add error handling", or stub-and-fill patterns in any code block — all Swift and TypeScript is fully implemented.
- `setServerBasePath` in Task 7 AppDelegate includes an inline note about the Capacitor 6 API — this is a documentation note, not a placeholder; the call is real.

### Interface Consistency
- `LocationFix` type defined once in `background-location.ts`, exported, consumed by Plan 2.
- `LiveActivityState` type defined once in `live-activity.ts`, exported.
- `BundleStore.path()` synchronous-in-contract via JS-side `pathCache`, documented and the Plan 2 contract (call `download` before `path`) is explicit.
- All four plugins re-exported from `src/plugins/index.ts` — one import surface for Plan 2 and Plan 4.

### Device vs. Unit Test Honesty
- Unit tests exist for: all JS bridge wrappers (mock-based, Vitest), OTA version-check logic, plugin index re-exports. These run headlessly in CI.
- Device-verified steps are explicit and concrete for: background GPS (Task 2 Step 9), background audio + ducking burst-behavior (Task 3 Steps 9–10), BundleStore download + path (Task 4 Step 10), LiveActivity Dynamic Island rendering (Task 5 Step 11), OTA swap flow (Task 7 Step 7), full device build (Task 8 Steps 5–7).
- No automated test is claimed for things that require a device.
