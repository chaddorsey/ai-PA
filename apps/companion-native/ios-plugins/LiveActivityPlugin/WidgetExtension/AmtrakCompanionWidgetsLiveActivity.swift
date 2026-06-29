// AmtrakCompanionWidgetsLiveActivity.swift
// Amtrak Companion — Dynamic Island / Lock Screen Widget Extension
//
// Phase 2 — this file is written but not included in the current beta build.
//
// DEVICE BUILD (Phase 2):
//   1. In Xcode: File → New → Target → Widget Extension → name "AmtrakCompanionWidgets"
//   2. Add AmtrakCompanionAttributes.swift to BOTH the App target AND AmtrakCompanionWidgets target.
//   3. Add this file to the AmtrakCompanionWidgets target only.
//   4. Set the deployment target on both targets to iOS 16.2+.
//   5. Add NSSupportsLiveActivities = YES to the main App's Info.plist.
//   6. Build and run both targets.
//
// Requires: iOS 16.2+, Xcode 15+, ActivityKit, WidgetKit, SwiftUI
// WRITTEN, NOT COMPILED HERE.

import ActivityKit
import WidgetKit
import SwiftUI

// Widget entry point — registers the Live Activity configuration.
@main
struct AmtrakCompanionWidgets: WidgetBundle {
    var body: some Widget {
        AmtrakCompanionLiveActivityWidget()
    }
}

struct AmtrakCompanionLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: AmtrakCompanionAttributes.self) { context in
            // ── Lock Screen / Notification Banner ─────────────────────────────
            HStack(spacing: 12) {
                Image(systemName: "train.side.front.car")
                    .foregroundColor(.white)
                    .font(.title2)

                VStack(alignment: .leading, spacing: 2) {
                    Text(context.state.nowPlaying)
                        .font(.headline)
                        .foregroundColor(.white)
                        .lineLimit(1)
                    Text("Next: \(context.state.nextStop) · \(context.state.etaText)")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.8))
                }

                Spacer()

                Text(context.state.positionText)
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.6))
            }
            .padding()
            .activityBackgroundTint(Color(red: 0.05, green: 0.12, blue: 0.25)) // dark navy

        } dynamicIsland: { context in
            // ── Dynamic Island ─────────────────────────────────────────────────
            DynamicIsland {
                // Expanded view (long-press or when there's room)
                DynamicIslandExpandedRegion(.leading) {
                    Label {
                        Text(context.state.nowPlaying)
                            .font(.caption)
                            .lineLimit(2)
                    } icon: {
                        Image(systemName: "train.side.front.car")
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    VStack(alignment: .trailing) {
                        Text(context.state.positionText)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text("Next: \(context.state.nextStop) · \(context.state.etaText)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            } compactLeading: {
                Image(systemName: "train.side.front.car")
                    .foregroundColor(.blue)
            } compactTrailing: {
                Text(context.state.etaText)
                    .font(.caption2)
                    .monospacedDigit()
            } minimal: {
                Image(systemName: "train.side.front.car")
            }
            .keylineTint(.blue)
        }
    }
}
