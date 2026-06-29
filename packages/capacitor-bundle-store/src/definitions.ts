import type { Plugin } from '@capacitor/core';

export interface BundleStorePlugin extends Plugin {
  /**
   * Download a leg bundle zip from a URL and extract it to local storage.
   * @param options.legId  Unique identifier for the leg (used as directory name)
   * @param options.url    HTTPS URL to the bundle.zip file
   */
  download(options: { legId: string; url: string }): Promise<void>;

  /**
   * Get the WebView-loadable URL for a previously downloaded leg bundle.
   * Returns the path to bundle.json inside the leg directory, served via
   * Capacitor's local file-serving scheme.
   * @param options.legId  Unique identifier for the leg
   */
  getPath(options: { legId: string }): Promise<{ path: string }>;

  /**
   * List all downloaded leg IDs.
   */
  list(): Promise<{ legs: string[] }>;
}
