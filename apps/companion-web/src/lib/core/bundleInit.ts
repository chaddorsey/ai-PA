import { loadBundle } from 'companion-core';
import { BundleStore } from '$lib/native/plugins';
import { appState } from './AppState.svelte';

// ── DEV: embedded bundle fallback ─────────────────────────────────────────────
// When true AND BundleStore.list() is empty, the app auto-loads the static
// proxy bundle served at /bundles/leg<legId>/bundle.json. Audio URIs of the form
// "audio/<file>" resolve to /bundles/leg<legId>/audio/<file> — playable from the
// browser/device without a downloaded bundle.
// Set to false (or remove) to disable the dev shortcut.
const DEV_EMBEDDED_BUNDLE = true;
// ── end DEV ──────────────────────────────────────────────────────────────────

export type BundleInitResult =
  | { status: 'first-run'; message: string }
  | { status: 'loaded'; bundle: import('companion-core').Bundle }
  | { status: 'error'; message: string };

export async function initBundle(legId: string): Promise<BundleInitResult> {
  // DEV: derive the embedded bundle constants from the caller-supplied legId
  const devEmbeddedLegId = legId;
  const devEmbeddedBaseUrl = '/bundles/leg' + legId;

  // DEV: load the embedded static bundle FIRST, fully independent of the native
  // BundleStore (which may be unavailable/erroring on a dev device build). If the
  // embedded fetch fails, fall through to the normal BundleStore path below.
  if (DEV_EMBEDDED_BUNDLE) {
    const dev = await loadEmbeddedBundle(devEmbeddedLegId, devEmbeddedBaseUrl);
    if (dev.status === 'loaded') return dev;
    // Embedded fetch failed. Only fall through to BundleStore if a real bundle is
    // actually downloaded for this leg; otherwise surface the embedded error
    // (so a device fetch failure is visible, not hidden as "first-run").
    let downloaded: string[] = [];
    try {
      downloaded = await BundleStore.list();
    } catch {
      downloaded = [];
    }
    if (!downloaded.includes(legId)) return dev;
  }
  try {
    let available: string[] = [];
    try {
      available = await BundleStore.list();
    } catch {
      available = [];
    }
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

// ── DEV: embedded bundle loader ───────────────────────────────────────────────
/**
 * DEV: Fetch the statically-served proxy bundle from /bundles/leg<legId>/bundle.json.
 * Audio URIs in the bundle are of the form "audio/<legId>-N.mp3"; they resolve to
 * /bundles/leg<legId>/audio/<legId>-N.mp3 when prefixed with baseUrl.
 * The bundle data is not transformed — AudioSession.play() receives the full
 * /bundles/leg<legId>/audio/... URL, which is a playable path in a browser/Capacitor webview.
 */
async function loadEmbeddedBundle(legId: string, baseUrl: string): Promise<BundleInitResult> {
  try {
    const res = await fetch(`${baseUrl}/bundle.json`);
    if (!res.ok) {
      throw new Error(`DEV embedded bundle fetch failed: ${res.status}`);
    }
    const rawBundle = await res.json();

    // Rewrite audio URIs: "audio/<file>" → "/bundles/leg<legId>/audio/<file>"
    // so AudioSession.play() gets a device-playable absolute path.
    const bundle = rewriteAudioUris(rawBundle, baseUrl);

    appState.bundle = bundle;
    return { status: 'loaded', bundle };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { status: 'error', message: `DEV bundle load failed: ${message}` };
  }
}

/**
 * DEV: Rewrite each unit's audio field from a relative path ("audio/<file>")
 * to an absolute URL ("/bundles/leg<legId>/audio/<file>") that a browser/webview
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
