import { CapacitorConfig } from '@capacitor/cli';

/**
 * Capacitor 6 shell configuration for Amtrak Companion.
 *
 * webDir points to the Plan 4 SvelteKit static build output.
 * After `npm run build` in apps/companion-web, dist/ is populated here.
 *
 * MAC BUILD STEPS (run on your Mac with Xcode installed):
 *   cd apps/companion-native
 *   npm install
 *   npx cap add ios        # creates ios/ directory
 *   # Edit ios/App/App/Info.plist — see BUILD_IOS.md
 *   # Add ios-plugins/ sources to Xcode target — see BUILD_IOS.md
 *   npx cap sync ios
 *   npx cap open ios       # opens Xcode
 */
const config: CapacitorConfig = {
  appId: 'com.amtrakcompanion.app',
  appName: 'Amtrak Companion',
  // Path is relative to this file; points to companion-web's static build
  webDir: '../companion-web/build',
  ios: {
    scheme: 'AmtrakCompanion',
    backgroundColor: '#000000',
    // contentInset: 'always',  // safe area insets for Dynamic Island
  },
  plugins: {
    // @capawesome/capacitor-live-update configuration.
    // Set channel to your CDN distribution channel name.
    // publicKey is the base64-encoded RSA public key for bundle signature verification.
    // Leave publicKey blank during development; set it before TestFlight submission.
    LiveUpdate: {
      appId: 'com.amtrakcompanion.app',
      channel: 'production',
      // publicKey: 'YOUR_BASE64_RSA_PUBLIC_KEY',
    },
  },
};

export default config;
