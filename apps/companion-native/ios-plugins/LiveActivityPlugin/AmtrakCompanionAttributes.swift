// AmtrakCompanionAttributes.swift
// Amtrak Companion — ActivityKit attributes struct.
//
// Phase 2 (currently a stub in the beta build).
// This file must be in BOTH the main App target AND the Widget Extension target.
//
// DEVICE BUILD: When building the Widget Extension in Xcode, add this file to both targets.
// WRITTEN, NOT COMPILED HERE. User must build on Mac with Xcode 15+ targeting iOS 16.2+.

import ActivityKit
import Foundation

public struct AmtrakCompanionAttributes: ActivityAttributes {
    // Static data set at start — does not change for the life of the activity.
    public let trainName: String

    // ContentState is the dynamic data updated via LiveActivity.update().
    public struct ContentState: Codable, Hashable {
        public var nowPlaying: String      // e.g. "Raton Pass"
        public var nextStop: String        // e.g. "Trinidad, CO"
        public var etaText: String         // e.g. "14 min"
        public var positionText: String    // e.g. "MP 1087"
    }

    public init(trainName: String) {
        self.trainName = trainName
    }
}
