/**
 * BundleStore — Capacitor plugin bridge.
 *
 * On iOS: delegates to BundleStorePlugin.swift which:
 *   - Downloads a ZIP to applicationSupportDirectory (non-evictable on low storage)
 *   - Unzips using ZIPFoundation / Apple Compression framework (NOT /usr/bin/unzip)
 *   - Caches unzipped bundles across app launches (idempotent: skips if bundle.json exists)
 *   - Scans disk on boot so getPath/list work immediately after restart
 *
 * Matches the locked Plan 0 §F contract (all async):
 *   BundleStore.download(legId, url)  → Promise<void>
 *   BundleStore.getPath(legId)        → Promise<string>   (absolute native path)
 *   BundleStore.list()                → Promise<string[]> (legIds present on disk)
 *
 * Web/simulator stub: paths under /bundles/<legId> (served by Vite dev proxy).
 * On device: paths are absolute file:// paths; use Capacitor.convertFileSrc() to
 * translate them to a WKWebView-accessible cap:// URL for media elements.
 */
import { registerPlugin } from '@capacitor/core';

interface BundleStoreNativePlugin {
  download(opts: { legId: string; url: string }): Promise<void>;
  getPath(opts: { legId: string }): Promise<{ path: string }>;
  list(): Promise<{ legs: string[] }>;
}

const _plugin = registerPlugin<BundleStoreNativePlugin>('BundleStore', {
  web: () => import('./bundle-store-web').then((m) => new m.BundleStoreWeb()),
});

export const BundleStore = {
  /**
   * Download and unzip a leg bundle from the given URL.
   * Idempotent: resolves immediately if the bundle is already present on disk.
   * Must be awaited before calling getPath() for the same legId.
   */
  download(legId: string, url: string): Promise<void> {
    return _plugin.download({ legId, url });
  },

  /**
   * Get the absolute native filesystem path to an already-downloaded leg bundle directory.
   * Returns a path like /var/mobile/…/Application Support/amtrak-bundles/<legId>/
   * Call Capacitor.convertFileSrc(path) to get a WKWebView-accessible URL for audio.
   * Throws if the bundle has not been downloaded yet.
   */
  async getPath(legId: string): Promise<string> {
    const { path } = await _plugin.getPath({ legId });
    return path;
  },

  /**
   * List all leg IDs whose bundles are present on disk.
   * Safe to call immediately on boot — the Swift plugin scans applicationSupportDirectory
   * during plugin load() and populates its internal registry before any JS calls.
   */
  async list(): Promise<string[]> {
    const { legs } = await _plugin.list();
    return legs;
  },
};
