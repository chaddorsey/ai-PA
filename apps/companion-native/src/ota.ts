/**
 * OTA web-bundle update logic.
 *
 * Uses @capawesome/capacitor-live-update for the actual apply step on device.
 * This module handles the version-check logic (fetch + compare) and provides
 * the JS interface that Plan 4's Settings view calls.
 *
 * On device, the apply step triggers the Capacitor Live Update plugin to
 * download the new web bundle and restart into it.
 *
 * The check is purely JS (testable in Vitest without a device).
 */
import { LiveUpdate } from '@capawesome/capacitor-live-update';

export interface OTACheckResult {
  available: boolean;
  version: string;
  url?: string;
}

export const OTA = {
  /**
   * Check the CDN for a newer web bundle.
   * Returns { available: true, version, url } if a newer version is found,
   * or { available: false, version: currentVersion } if up-to-date or offline.
   * Never throws — network errors return available=false (graceful offline).
   */
  async checkForUpdate(
    currentVersion: string,
    versionUrl: string,
  ): Promise<OTACheckResult> {
    try {
      const resp = await fetch(versionUrl, { cache: 'no-store' });
      if (!resp.ok) return { available: false, version: currentVersion };
      const data: { version: string; url: string } = await resp.json();
      const available = data.version !== currentVersion;
      return {
        available,
        version: data.version,
        url: available ? data.url : undefined,
      };
    } catch {
      return { available: false, version: currentVersion };
    }
  },

  /**
   * Apply a previously downloaded OTA bundle and reload the app.
   * On device: calls LiveUpdate.reload() which triggers the Capacitor plugin
   * to swap the web dir and restart the WKWebView.
   * In the browser/test environment this is a no-op.
   */
  async apply(): Promise<void> {
    try {
      await LiveUpdate.reload();
    } catch {
      // Browser or plugin not registered — ignore.
    }
  },
};
