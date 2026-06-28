# G0 — Device Tracer Bullet (run before Plan 3)

**Purpose:** prove the hybrid premise on a real iPhone *before* we build the shell. Throwaway code — delete after. **~30–45 min.** Pass = all five checks observed.

## Setup
1. Xcode → **New Project → iOS App** (SwiftUI), name `TracerBullet`, your team for signing.
2. Drop any short **`test.mp3`** into the project (drag in, "Copy items if needed"). (Export ~30s of one narration clip, or any MP3.)
3. **Signing & Capabilities → + Capability → Background Modes** → check **Audio, AirPlay, and Picture in Picture** *and* **Location updates**.
4. **Info.plist** → add `NSLocationWhenInUseUsageDescription` and `NSLocationAlwaysAndWhenInUseUsageDescription` (any string).
5. Replace `ContentView.swift` with the code below. Run on a **real device** (not the simulator — background audio/location need hardware).

## Code (`ContentView.swift`)
```swift
import SwiftUI
import AVFoundation
import CoreLocation

final class Tracer: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var log: [String] = []
    private var player: AVAudioPlayer?
    private let loc = CLLocationManager()

    func start() {
        // --- audio: .playback + duckOthers, background-capable ---
        let s = AVAudioSession.sharedInstance()
        try? s.setCategory(.playback, options: [.duckOthers])
        try? s.setActive(true)
        if let url = Bundle.main.url(forResource: "test", withExtension: "mp3"),
           let p = try? AVAudioPlayer(contentsOf: url) {
            p.numberOfLoops = -1; p.play(); player = p
            add("AUDIO playing MP3 (looped), ducking others")
        } else { add("ERROR: test.mp3 not found / not decodable") }
        // --- location: background fixes ---
        loc.delegate = self
        loc.allowsBackgroundLocationUpdates = true
        loc.desiredAccuracy = kCLLocationAccuracyBest
        loc.requestAlwaysAuthorization()
        loc.startUpdatingLocation()
        add("LOCATION started")
    }
    func restoreOthers() {  // swell other audio back
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        add("session deactivated (others should swell back)")
    }
    func locationManager(_ m: CLLocationManager, didUpdateLocations locs: [CLLocation]) {
        if let l = locs.last { add(String(format: "FIX %.4f,%.4f", l.coordinate.latitude, l.coordinate.longitude)) }
    }
    private func add(_ s: String) {
        let t = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        DispatchQueue.main.async { self.log.insert("\(t)  \(s)", at: 0) }
    }
}

struct ContentView: View {
    @StateObject var t = Tracer()
    var body: some View {
        VStack(spacing: 12) {
            Button("START (audio + location)") { t.start() }.buttonStyle(.borderedProminent)
            Button("Restore other audio") { t.restoreOthers() }
            List(t.log, id: \.self) { Text($0).font(.caption.monospaced()) }
        }.padding()
    }
}
```

## The five checks (all must pass — Gate G0)
1. **Background location, screen locked:** start playing music in Apple Music first, then run, tap START, grant "Always," **lock the screen and pocket the phone for ≥30 min** while moving (a drive/walk). Unlock → the log shows **FIX lines continued while locked**. ✅/❌
2. **Background MP3 audio:** with the app backgrounded / screen locked, the **MP3 keeps playing**. ✅/❌
3. **Ducking + restore:** Apple Music is **ducked** (volume drops) while the tracer's MP3 plays; tap **Restore other audio** → Apple Music **swells back to full**. ✅/❌
4. **Survives 30‑min lock:** after the locked period, audio is still playing and fixes are still logging (nothing was killed). ✅/❌
5. **Call interruption:** place/receive a phone call → audio pauses; after the call, the app **resumes** (or at least isn't dead). ✅/❌

**Report back:** which of 1–5 passed. If all five pass → G0 green, Plan 3 is sound. If any fail (esp. 1–2 together), that's **bailout B1** — the hybrid premise needs rework before we build the shell; we'd reassess rather than push on.
