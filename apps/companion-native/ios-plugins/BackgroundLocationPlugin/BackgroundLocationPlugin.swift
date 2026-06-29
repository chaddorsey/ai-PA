// BackgroundLocationPlugin.swift
// Amtrak Companion — Plan 3: BackgroundLocation Capacitor plugin
//
// Wraps CLLocationManager for continuous background GPS fixes.
// Proven by tracer bullet (Task G0): allowsBackgroundLocationUpdates + UIBackgroundModes[location]
// delivers fixes with the screen locked for 30+ minutes.
//
// DEVICE BUILD: Add this file to the App Xcode target (drag into App group).
// Registration: BackgroundLocationPlugin.m declares the CAP_PLUGIN macro.
//
// LOCATION ENTITLEMENT STRATEGY (Plan 0 §F):
//   - Requests "Always" permission for continuous background fixes.
//   - If the user grants "When In Use" only, fixes stop when the screen locks.
//     The denied path shows an in-app prompt (Plan 4) and falls back to
//     dead-reckoning via PositionService in companion-core.
//
// WRITTEN, NOT COMPILED HERE. User must build on Mac with Xcode 15+.

import Foundation
import Capacitor
import CoreLocation

@objc(BackgroundLocationPlugin)
public class BackgroundLocationPlugin: CAPPlugin, CLLocationManagerDelegate {

    private var locationManager: CLLocationManager?
    private var currentHandle: String?

    // MARK: - startWatch

    @objc func startWatch(_ call: CAPPluginCall) {
        let handle = UUID().uuidString
        currentHandle = handle

        DispatchQueue.main.async { [weak self] in
            guard let self else { return }

            let mgr = CLLocationManager()
            mgr.delegate = self
            mgr.desiredAccuracy = kCLLocationAccuracyBest
            mgr.distanceFilter = 20          // metres between emitted fixes (battery tradeoff)
            mgr.pausesLocationUpdatesAutomatically = false
            // REQUIRED for background fixes (tracer bullet confirmed this pattern works).
            mgr.allowsBackgroundLocationUpdates = true
            // Show the blue location indicator in the status bar when backgrounded.
            mgr.showsBackgroundLocationIndicator = true

            // Request Always — necessary for fixes when screen is locked.
            // If user denies, fixes stop when screen locks; companion-core falls back
            // to dead-reckoning. The Settings UI (Plan 4) explains the tradeoff.
            mgr.requestAlwaysAuthorization()
            mgr.startUpdatingLocation()
            self.locationManager = mgr
        }

        call.resolve(["handle": handle])
    }

    // MARK: - clearWatch

    @objc func clearWatch(_ call: CAPPluginCall) {
        locationManager?.stopUpdatingLocation()
        locationManager = nil
        currentHandle = nil
        call.resolve()
    }

    // MARK: - CLLocationManagerDelegate

    public func locationManager(
        _ manager: CLLocationManager,
        didUpdateLocations locations: [CLLocation]
    ) {
        guard let loc = locations.last else { return }
        let fix: [String: Any] = [
            "lat":   loc.coordinate.latitude,
            "lon":   loc.coordinate.longitude,
            "ts":    Int64(loc.timestamp.timeIntervalSince1970 * 1000),
            "speed": loc.speed >= 0 ? loc.speed : -1,  // -1 = unavailable
        ]
        notifyListeners("location", data: fix)
    }

    public func locationManager(
        _ manager: CLLocationManager,
        didFailWithError error: Error
    ) {
        // Surface the error so the JS layer can log or display a denied-path prompt.
        notifyListeners("location", data: [
            "error": error.localizedDescription,
        ])
    }

    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        // Notify JS when the user changes permission in Settings while the app is running.
        let status: String
        switch manager.authorizationStatus {
        case .authorizedAlways:           status = "always"
        case .authorizedWhenInUse:        status = "whenInUse"
        case .denied, .restricted:        status = "denied"
        case .notDetermined:              status = "notDetermined"
        @unknown default:                 status = "unknown"
        }
        notifyListeners("authorizationChange", data: ["status": status])
    }
}
