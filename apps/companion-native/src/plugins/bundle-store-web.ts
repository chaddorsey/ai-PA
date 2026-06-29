/**
 * BundleStore web implementation (browser / Vite dev server).
 * Paths returned are relative to the Vite dev proxy — no real unzip occurs.
 */
import { WebPlugin } from '@capacitor/core';

export class BundleStoreWeb extends WebPlugin {
  private downloaded = new Set<string>();

  async download(opts: { legId: string; url: string }): Promise<void> {
    // In the browser we just mark it as "downloaded" — no actual fetch.
    this.downloaded.add(opts.legId);
  }

  async getPath(opts: { legId: string }): Promise<{ path: string }> {
    return { path: `/bundles/${opts.legId}` };
  }

  async list(): Promise<{ legs: string[] }> {
    return { legs: Array.from(this.downloaded) };
  }
}
