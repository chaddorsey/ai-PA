# Amtrak Companion — iOS Build Runbook

**Prerequisites:** Mac with Xcode 15+, iOS device running iOS 16+, Apple Developer account (free account works for device testing; paid account required for TestFlight).

This runbook covers: npm setup → Capacitor scaffold → Info.plist edits → plugin sources → Xcode build → device verification checklist.

**Note:** The Swift sources for AudioSessionPlugin are now delivered as a Capacitor Pod (`packages/capacitor-audio-session/`). The loose file at `ios-plugins/AudioSessionPlugin/` remains for reference but must NOT be added to the Xcode target — the Pod provides the registered plugin. All native capabilities are verified on a physical device (not the Simulator — background audio and location require hardware).

---

## Step 1: Install npm dependencies

```bash
# Install companion-native deps (picks up capacitor-audio-session file: dep)
cd apps/companion-native
npm install

# Install companion-web deps (also has the file: dep)
cd ../companion-web
npm install
```

---

## Step 2: Build the web layer

```bash
cd apps/companion-web
npm run build
# Outputs to apps/companion-web/build/ (referenced by capacitor.config.ts webDir)
```

---

## Step 3: Initialize Capacitor and add iOS platform

```bash
cd apps/companion-native
npx cap init "Amtrak Companion" "com.amtrakcompanion.app"
npx cap add ios
```

This creates `apps/companion-native/ios/` (Xcode project + workspace).

---

## Step 4: Edit Info.plist

Open `apps/companion-native/ios/App/App/Info.plist` and add the keys from `ios-app/Info.plist.additions.xml`:

```xml
<key>UIBackgroundModes</key>
<array>
    <string>location</string>
    <string>audio</string>
</array>
<key>NSLocationAlwaysAndWhenInUseUsageDescription</key>
<string>Amtrak Companion uses your location continuously to trigger audio narration as you pass landmarks — even when the screen is off. Your location is never sent off your device.</string>
<key>NSLocationWhenInUseUsageDescription</key>
<string>Amtrak Companion uses your location to trigger audio narration as you pass landmarks. For narration to continue when the screen is locked, grant Always access.</string>
<key>NSLocationAlwaysUsageDescription</key>
<string>Amtrak Companion uses your location continuously to trigger narration, even when the screen is off.</string>
<key>NSSupportsLiveActivities</key>
<true/>
```

**Tip:** In Xcode, open `ios/App/App/Info.plist`, right-click → Open As → Source Code to paste directly.

---

## Step 5: Replace AppDelegate.swift

Replace the generated `ios/App/App/AppDelegate.swift` with the contents of `ios-app/AppDelegate.swift`. This adds early AVAudioSession activation and OTA bundle redirection.

---

## Step 6: Sync Capacitor (registers the AudioSession Pod)

```bash
cd apps/companion-native
npx cap sync ios
```

`cap sync` reads the `capacitor` field in `package.json` of the `capacitor-audio-session` package (which points to `ios/`), runs `pod install`, and registers the `CapacitorAudioSession` Pod. The `AudioSession` plugin will now resolve natively on Capacitor 8 instead of returning UNIMPLEMENTED.

**Important:** Do NOT manually add `ios-plugins/AudioSessionPlugin/` files to the Xcode target. The Pod now owns those sources. Adding them again would cause duplicate symbol errors.

---

## Step 7: Add remaining plugin Swift sources to the Xcode project

Open the Xcode workspace:
```bash
npx cap open ios
```

In Xcode, for **each remaining** plugin directory under `ios-plugins/` (NOT AudioSessionPlugin — that is now a Pod):

1. Right-click on the `App` group in the Project Navigator (not the project root — the nested `App` group containing `AppDelegate.swift`).
2. Select **Add Files to "App"**.
3. Navigate to the plugin directory.
4. Select both files (`.swift` + `.m`).
5. Ensure **"Add to targets: App"** is checked.
6. Click **Add**.

Plugins to add manually:
- `ios-plugins/BackgroundLocationPlugin/` — `BackgroundLocationPlugin.swift` + `BackgroundLocationPlugin.m`
- `ios-plugins/BundleStorePlugin/` — `BundleStorePlugin.swift` + `BundleStorePlugin.m`
- **Phase 2 only** — `ios-plugins/LiveActivityPlugin/` — see Phase 2 section below

**AudioSessionPlugin** — provided by the `CapacitorAudioSession` Pod. Skip adding it manually.

---

## Step 8: Add ZIPFoundation via Swift Package Manager

BundleStorePlugin uses ZIPFoundation for unzipping (NOT /usr/bin/unzip, which is unavailable in an iOS app sandbox).

In Xcode:
1. **File → Add Package Dependencies...**
2. Enter the URL: `https://github.com/weichsel/ZIPFoundation.git`
3. Dependency Rule: **Up to Next Major Version**, `0.9.19`
4. Add to target: **App**
5. Click **Add Package**.

---

## Step 9: Enable Signing & Capabilities

1. Select the `App` target → **Signing & Capabilities** tab.
2. Set your Team (personal Apple ID works for device testing).
3. Click **+ Capability** and add:
   - **Background Modes** → check both: "Audio, AirPlay, and Picture in Picture" AND "Location updates"
4. Verify the bundle identifier is `com.amtrakcompanion.app`.

---

## Step 10: Set deployment target

Set the minimum deployment target to **iOS 16.0** (needed for some API availability; iOS 16.2 required for Live Activities in Phase 2).

In Xcode: Project → Build Settings → iOS Deployment Target → `16.0`.

---

## Step 11: Build and run

1. Connect a physical iPhone via USB.
2. In Xcode, select your device as the run target (not Simulator — background audio/location need hardware).
3. **Product → Build** (⌘B) to check for errors.
4. **Product → Run** (⌘R) to deploy and launch.

---

## Device Verification Checklist

All five checks should pass (matching the tracer bullet criteria from Plan 0 Task G0):

### Check 1: Background location, screen locked
- Open Apple Music and start playing a song.
- Launch the companion app, call `BackgroundLocation.watch(fix => console.log(fix))` from the Safari Web Inspector console.
- Grant "Always" location permission when prompted.
- Lock the screen; leave the phone in your pocket for 30+ minutes while moving (drive or walk).
- Unlock → verify the console has accumulated fix objects with varying lat/lon values.
- **Expected:** fixes continued accumulating while the screen was locked.

### Check 2: Background MP3 audio
- Call `AudioSession.play('/bundles/testleg/audio/test.mp3')` (use a path from BundleStore.getPath() or a known test file).
- Lock the screen.
- **Expected:** audio continues playing in the background.
- **Expected (NEW):** On Capacitor 8, this invokes native AVAudioPlayer — not an UNIMPLEMENTED error. The JS console should NOT show "Plugin not implemented" or similar.

### Check 3: Three audio modes + ducking
- Start Apple Music at ~50% volume.
- Default mode (interrupt-spoken): play the companion — music should duck noticeably; spoken audio (podcasts) should pause.
- Call `AudioSession.setMode('duck')`: music ducks but spoken audio continues.
- Call `AudioSession.setMode('pause')`: companion pauses/resumes Apple Music fully each burst.
- After the companion audio ends and ~2 seconds pass: music swells back to full volume.
- **Expected:** all three modes behave distinctly; music restores after silence.

### Check 4: Burst-level ducking (music stays ducked across back-to-back units)
- Play two short MP3s back-to-back (call play() immediately in the 'ended' callback).
- **Expected:** music stays ducked through the gap between the two units (no swell-restore between them).
- After the second unit ends and 2+ seconds pass: music swells back.

### Check 5: Interruption + resume after call
- While the companion is playing, make or receive a phone call.
- **Expected:** companion audio pauses; `interrupt` event fires with `{ type: 'began' }`.
- End the call.
- **Expected:** companion resumes automatically (the `interruptionNotification` handler fires with `.shouldResume`, reactivates the session, and resumes the player); `interrupt` event fires with `{ type: 'ended' }`.

### Check 6: BundleStore download + path
- From the Safari Web Inspector console:
  ```js
  await BundleStore.download('testleg', 'http://YOUR_MAC_IP:8999/testleg.zip');
  const path = await BundleStore.getPath('testleg');
  console.log(path);
  ```
- **Expected:** no error; path is an absolute native path like `/var/mobile/.../amtrak-bundles/testleg`.
- In Xcode → Devices → app container → verify files exist at that path.
- Call `await BundleStore.list()` → expected: `['testleg']`.
- Re-run download → expected: resolves immediately (idempotent).

### Check 7: Boot persistence
- Download a bundle (Check 6).
- Fully quit and restart the app.
- Call `await BundleStore.getPath('testleg')` immediately without downloading again.
- **Expected:** path returned immediately (boot scan from disk populated the registry).

### Check 8: OTA bundle swap (optional in Phase 1)
- Serve a test `version.json` from your Mac: `{ "version": "0.0.2", "url": "http://MAC_IP:8999/web-0.0.2.zip" }`.
- Serve a `web-0.0.2.zip` with a modified `index.html` (e.g., background red).
- Call `OTA.checkForUpdate('0.0.1', 'http://MAC_IP:8999/version.json')` → expected: `{ available: true, version: '0.0.2' }`.
- Implement the download+unzip into `ota-web-bundle/` and call `OTA.apply()`.
- **Expected:** app restarts into the updated web content.

---

## Phase 2: LiveActivity / Dynamic Island

When ready to ship Phase 2:

1. In Xcode: **File → New → Target → Widget Extension** → name it `AmtrakCompanionWidgets`.
2. Add `ios-plugins/LiveActivityPlugin/AmtrakCompanionAttributes.swift` to **both** the App target and the `AmtrakCompanionWidgets` target.
3. Add `ios-plugins/LiveActivityPlugin/WidgetExtension/AmtrakCompanionWidgetsLiveActivity.swift` to the `AmtrakCompanionWidgets` target only.
4. Add `ios-plugins/LiveActivityPlugin/LiveActivityPlugin.swift` + `LiveActivityPlugin.m` to the `App` target.
5. Set the deployment target on both targets to iOS 16.2+.
6. Ensure `NSSupportsLiveActivities = YES` is in the main App's `Info.plist`.
7. Build and run both targets.

**Device verification:**
- Call `await LiveActivity.start({ nowPlaying: 'Raton Pass', nextStop: 'Trinidad', etaText: '14 min', positionText: 'MP 1087' })`.
- On iPhone 14 Pro+: Dynamic Island shows compact train icon + ETA text.
- On older iPhones: Lock Screen banner appears.
- Call `await LiveActivity.update({ ..., etaText: '12 min' })` → updates within 1–2 s.
- Call `await LiveActivity.end()` → activity dismisses.

---

## Troubleshooting

**"Plugin not found" or UNIMPLEMENTED error in the WKWebView console:**
- Ensure `npx cap sync ios` ran AFTER `npm install` (which links the `capacitor-audio-session` package).
- Verify the Podfile references `CapacitorAudioSession` — look for it in `ios/App/Podfile` after sync.
- Clean build folder (⌘⇧K) and rebuild.
- Do NOT add `ios-plugins/AudioSessionPlugin/` files manually — the Pod owns those sources.

**Audio stops when screen locks:**
- Verify `UIBackgroundModes` contains `audio` in Info.plist.
- Verify the Signing & Capabilities tab shows "Background Modes → Audio, AirPlay, and Picture in Picture" checked.
- Check that `AVAudioSession.setCategory(.playback)` runs before `setActive(true)`.

**Location stops when screen locks:**
- Verify `UIBackgroundModes` contains `location` in Info.plist.
- Verify `allowsBackgroundLocationUpdates = true` is set on the CLLocationManager.
- Verify the user granted "Always" permission (not just "When In Use").

**ZIPFoundation not found:**
- Confirm the Swift Package was added (File → Packages → show packages list).
- Clean derived data (Xcode → File → Packages → Reset Package Caches) and try again.

**pod install fails with "Unable to find a specification for CapacitorAudioSession":**
- The podspec uses a local git source. Run `npx cap sync ios` from `apps/companion-native/` — Capacitor handles the pod registration path automatically from the `capacitor.ios.src` field in `package.json`.
- If needed, manually verify `ios/App/Podfile` contains: `pod 'CapacitorAudioSession', :path => '../../../../packages/capacitor-audio-session'`
