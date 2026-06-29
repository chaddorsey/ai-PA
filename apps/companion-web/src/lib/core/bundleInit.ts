import { loadBundle } from 'companion-core';
import { BundleStore } from '$lib/native/plugins';
import { appState } from './AppState.svelte';

export type BundleInitResult =
  | { status: 'first-run'; message: string }
  | { status: 'loaded'; bundle: import('companion-core').Bundle }
  | { status: 'error'; message: string };

export async function initBundle(legId: string): Promise<BundleInitResult> {
  try {
    const available = await BundleStore.list();
    if (!available.includes(legId)) {
      return { status: 'first-run', message: 'Download your trip' };
    }

    const bundlePath = await BundleStore.getPath(legId);
    const bundle = await loadBundle(legId, async (_id) => {
      const res = await fetch(`${bundlePath}/bundle.json`);
      if (!res.ok) throw new Error(`Failed to fetch bundle: ${res.status}`);
      return res.json();
    });

    appState.bundle = bundle;
    return { status: 'loaded', bundle };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { status: 'error', message };
  }
}
