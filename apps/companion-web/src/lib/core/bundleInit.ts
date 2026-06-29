import { loadBundle } from 'companion-core';
import { BundleStore } from '$lib/native/plugins';
import { appState } from './AppState.svelte';

// ── DEV: embedded bundle fallback ─────────────────────────────────────────────
// When true AND BundleStore.list() is empty, the app auto-loads the static
// proxy bundle served at /bundles/leg58/bundle.json. Audio URIs of the form
// "audio/<file>" resolve to /bundles/leg58/audio/<file> — playable from the
// browser/device without a downloaded bundle.
// Set to false (or remove) to disable the dev shortcut.
const DEV_EMBEDDED_BUNDLE = true;

/** The leg ID of the embedded static bundle. */
const DEV_EMBEDDED_LEG_ID = '58';

/** Base URL for the embedded static bundle assets. */
const DEV_EMBEDDED_BASE_URL = '/bundles/leg58';
// ── end DEV ──────────────────────────────────────────────────────────────────

export type BundleInitResult =
  | { status: 'first-run'; message: string }
  | { status: 'loaded'; bundle: import('companion-core').Bundle }
  | { status: 'error'; message: string };

export async function initBundle(legId: string): Promise<BundleInitResult> {
  try {
    // BundleStore.list() may reject on device (native plugin unavailable/erroring,
    // e.g. the dev build). Treat any failure as "no downloaded legs" so the dev
    // embedded fallback can still fire instead of erroring out.
    let available: string[] = [];
    try {
      available = await BundleStore.list();
    } catch {
      available = [];
    }
    if (!available.includes(legId)) {
      // DEV: if the store is empty and the dev flag is set, load the embedded bundle
      if (DEV_EMBEDDED_BUNDLE && legId === DEV_EMBEDDED_LEG_ID && available.length === 0) {
        return loadEmbeddedBundle();
      }
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

// ── DEV: embedded bundle loader ───────────────────────────────────────────────
/**
 * DEV: Fetch the statically-served proxy bundle from /bundles/leg58/bundle.json.
 * Audio URIs in the bundle are of the form "audio/58-N.mp3"; they resolve to
 * /bundles/leg58/audio/58-N.mp3 when prefixed with DEV_EMBEDDED_BASE_URL.
 * The bundle data is not transformed — AudioSession.play() receives the full
 * /bundles/leg58/audio/... URL, which is a playable path in a browser/Capacitor webview.
 */
async function loadEmbeddedBundle(): Promise<BundleInitResult> {
  try {
    const res = await fetch(`${DEV_EMBEDDED_BASE_URL}/bundle.json`);
    if (!res.ok) {
      throw new Error(`DEV embedded bundle fetch failed: ${res.status}`);
    }
    const rawBundle = await res.json();

    // Rewrite audio URIs: "audio/58-N.mp3" → "/bundles/leg58/audio/58-N.mp3"
    // so AudioSession.play() gets a device-playable absolute path.
    const bundle = rewriteAudioUris(rawBundle, DEV_EMBEDDED_BASE_URL);

    appState.bundle = bundle;
    return { status: 'loaded', bundle };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { status: 'error', message: `DEV bundle load failed: ${message}` };
  }
}

/**
 * DEV: Rewrite each unit's audio field from a relative path ("audio/58-N.mp3")
 * to an absolute URL ("/bundles/leg58/audio/58-N.mp3") that a browser/webview
 * can play without a native file resolver.
 */
function rewriteAudioUris(
  bundle: import('companion-core').Bundle,
  baseUrl: string,
): import('companion-core').Bundle {
  return {
    ...bundle,
    units: bundle.units.map((unit) => {
      if (!unit.audio) return unit;
      // If already absolute (starts with '/'), leave it alone
      const audio = unit.audio.startsWith('/')
        ? unit.audio
        : `${baseUrl}/${unit.audio}`;
      return { ...unit, audio };
    }),
  };
}
// ── end DEV ──────────────────────────────────────────────────────────────────
