# Activating `capacitor-bundle-store`

The package lives at `packages/capacitor-bundle-store/` and is **built but not yet wired into the apps**.
Follow these steps to activate it.

---

## 1. Add the dependency to both apps

In `apps/companion-web/package.json`, add to `dependencies`:
```json
"capacitor-bundle-store": "file:../../packages/capacitor-bundle-store"
```

In `apps/companion-native/package.json`, add to `dependencies`:
```json
"capacitor-bundle-store": "file:../../packages/capacitor-bundle-store"
```

Then run `npm install` in each app directory.

---

## 2. Update the native plugin import in companion-web

In `apps/companion-web/src/lib/native/plugins.ts`, change any loose inline BundleStore
definition to import from the package:

```typescript
import { BundleStore } from 'capacitor-bundle-store';
export { BundleStore };
```

Remove any local `registerPlugin('BundleStore', ...)` call that was standing in for the package.

---

## 3. Vite alias (if needed)

If Vite resolves the `file:` path incorrectly or you see module-not-found errors, add an
alias in `apps/companion-web/vite.config.ts`:

```typescript
resolve: {
  alias: {
    'capacitor-bundle-store': path.resolve(__dirname, '../../packages/capacitor-bundle-store/dist/esm/index.js'),
  },
},
```

This is a last resort — the standard `file:` link should work without it.

---

## 4. Sync Capacitor

From `apps/companion-native/`:
```bash
npx cap sync ios
```

This copies the JS bundle and registers the plugin with the iOS project.

---

## 5. CocoaPods (if the iOS project uses pods)

If `apps/companion-native/ios/App/Podfile` exists, add:
```ruby
pod 'CapacitorBundleStore', :path => '../../../packages/capacitor-bundle-store'
pod 'ZIPFoundation', '~> 0.9'
```

Then from `apps/companion-native/ios/App/`:
```bash
pod install
```

If using Swift Package Manager instead, `Package.swift` already declares the ZIPFoundation
dependency — Xcode will resolve it automatically after `cap sync`.

---

## 6. Verify `getPath` URL serving on device

**This step is mandatory before shipping.**

The `getPath` implementation returns a URL of the form:
```
capacitor://localhost/_capacitor_file_/path/to/Documents/bundles/<legId>/bundle.json
```

This URL form is the documented Capacitor 5/6 fallback. However, the exact scheme and path
prefix that Capacitor's `WKURLSchemeHandler` accepts varies by version.

**Preferred approach (Capacitor 5+):** If `bridge?.portablePath(fromLocalURL:)` is available
in the installed Capacitor version, replace the manual string construction in `getPath` with:

```swift
if let portablePath = bridge?.portablePath(fromLocalURL: bundleJson) {
    call.resolve(["path": portablePath])
} else {
    let filePath = bundleJson.path
    call.resolve(["path": "capacitor://localhost/_capacitor_file_\(filePath)"])
}
```

**Verification:** On a real device or simulator, call `BundleStore.getPath({ legId: 'test' })`
after downloading a bundle, then attempt `fetch(path)` or `new XMLHttpRequest()` from inside
the WebView. If the fetch fails with a CORS or scheme error, inspect the URL returned and
compare with what `bridge.portablePath` produces.
