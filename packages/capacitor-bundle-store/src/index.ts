import { registerPlugin } from '@capacitor/core';
import type { BundleStorePlugin } from './definitions';

const BundleStore = registerPlugin<BundleStorePlugin>('BundleStore', {
  web: () => import('./web').then((m) => new m.BundleStoreWeb()),
});

export * from './definitions';
export { BundleStore };
