// LiveActivityPlugin.swift
// Amtrak Companion — Plan 3: LiveActivity Capacitor plugin
//
// Phase 2 — this Swift file is written but NOT wired into the Xcode project
// in the current beta build. The JS stub in live-activity.ts handles the
// no-op path so the app doesn't crash.
//
// When Phase 2 ships:
//   1. Add LiveActivityPlugin.swift + .m to the App Xcode target.
//   2. Add LiveActivityPlugin.m registration.
//   3. Add AmtrakCompanionAttributes.swift to BOTH App target AND Widget Extension target.
//   4. Add NSSupportsLiveActivities = YES to Info.plist.
//   5. Build the Widget Extension target (AmtrakCompanionWidgets).
//
// Requires: iOS 16.2+, Swift concurrency (async/await), ActivityKit framework.
// WRITTEN, NOT COMPILED HERE. User must build on Mac with Xcode 15+.

import Foundation
import Capacitor
import ActivityKit

@objc(LiveActivityPlugin)
@available(iOS 16.2, *)
public class LiveActivityPlugin: CAPPlugin {

    // The currently running activity (nil if none started or already ended).
    private var currentActivity: Activity<AmtrakCompanionAttributes>?

    // MARK: - start

    @objc func start(_ call: CAPPluginCall) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            call.reject("Live Activities are disabled by the user in Settings → Face ID & Passcode")
            return
        }

        let attrs = AmtrakCompanionAttributes(trainName: call.getString("trainName") ?? "Amtrak")
        let state = contentState(from: call)

        Task {
            do {
                let activity = try Activity<AmtrakCompanionAttributes>.request(
                    attributes: attrs,
                    content: .init(state: state, staleDate: nil)
                )
                await MainActor.run { self.currentActivity = activity }
                call.resolve()
            } catch {
                call.reject("Activity.request failed: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - update

    @objc func update(_ call: CAPPluginCall) {
        guard let activity = currentActivity else {
            // No active activity; resolve silently (the companion may call update before start
            // during an edge-case restart; ignore rather than crash).
            call.resolve()
            return
        }
        let state = contentState(from: call)
        Task {
            await activity.update(.init(state: state, staleDate: nil))
            call.resolve()
        }
    }

    // MARK: - end

    @objc func end(_ call: CAPPluginCall) {
        guard let activity = currentActivity else {
            call.resolve()
            return
        }
        Task {
            await activity.end(.init(state: activity.content.state, staleDate: nil),
                               dismissalPolicy: .immediate)
            await MainActor.run { self.currentActivity = nil }
            call.resolve()
        }
    }

    // MARK: - Helpers

    private func contentState(from call: CAPPluginCall) -> AmtrakCompanionAttributes.ContentState {
        AmtrakCompanionAttributes.ContentState(
            nowPlaying:    call.getString("nowPlaying")    ?? "",
            nextStop:      call.getString("nextStop")      ?? "",
            etaText:       call.getString("etaText")       ?? "",
            positionText:  call.getString("positionText")  ?? ""
        )
    }
}
