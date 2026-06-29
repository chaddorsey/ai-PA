import { WebPlugin } from '@capacitor/core';
import type { BundleStorePlugin } from './definitions';

export class BundleStoreWeb extends WebPlugin implements BundleStorePlugin {
  async download(_options: { legId: string; url: string }): Promise<void> {
    throw this.unimplemented('BundleStore.download is not available on web. Use the native implementation.');
  }

  async getPath(_options: { legId: string }): Promise<{ path: string }> {
    throw this.unimplemented('BundleStore.getPath is not available on web. Use the native implementation.');
  }

  async list(): Promise<{ legs: string[] }> {
    return { legs: [] };
  }
}
