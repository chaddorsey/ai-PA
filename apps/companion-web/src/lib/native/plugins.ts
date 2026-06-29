/**
 * Native plugin interfaces and web stubs.
 * On device, Capacitor registerPlugin() bridges JS → native (iOS plugins in
 * apps/companion-native/ios-plugins/). In the browser/test environment the web
 * fallback objects (identical to the former stubs) are used instead, so no
 * caller changes are needed and vitest continues to work as-is.
 *
 * NATIVE ARG KEYS are kept internal to this file — callers use the same
 * positional / typed signatures they always have.
 */

import { registerPlugin } from '@capacitor/core';

// ── Shared types ──────────────────────────────────────────────────────────────

export interface BackgroundLocationFix {
  lat: number;
  lon: number;
  ts: number;
  speed?: number;
}

// ── Public facade interfaces (unchanged from original) ────────────────────────

export interface AudioSessionPlugin {
  setMode(mode: 'duck' | 'pause' | 'interrupt-spoken'): Promise<void>;
  play(fileUri: string): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  setRate(r: number): Promise<void>;
  addListener(event: 'ended' | 'interrupt', cb: () => void): { remove(): void };
}

export interface BackgroundLocationPlugin {
  watch(cb: (fix: BackgroundLocationFix) => void): Promise<string>;
  clear(handle: string): Promise<void>;
}

export interface LiveActivityPlugin {
  // Phase 2 — stub only for update/end; start is native-only
  update(data: Record<string, unknown>): Promise<void>;
  end(): Promise<void>;
}

export interface BundleStorePlugin {
  download(legId: string, url: string): Promise<void>;
  getPath(legId: string): Promise<string>;
  list(): Promise<string[]>;
}

// ── Native Capacitor interfaces (single options-object per Capacitor convention) ─

interface NativeAudioSession {
  setMode(opts: { mode: string }): Promise<void>;
  play(opts: { fileUri: string }): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  setRate(opts: { rate: number }): Promise<void>;
  addListener(
    event: string,
    cb: (data: Record<string, unknown>) => void
  ): Promise<{ remove(): void }>;
}

interface NativeBackgroundLocation {
  startWatch(): Promise<{ handle: string }>;
  clearWatch(): Promise<void>;
  addListener(
    event: string,
    cb: (data: Record<string, unknown>) => void
  ): Promise<{ remove(): void }>;
}

interface NativeLiveActivity {
  update(opts: {
    nowPlaying?: string;
    nextStop?: string;
    etaText?: string;
    positionText?: string;
    [key: string]: unknown;
  }): Promise<void>;
  end(): Promise<void>;
}

interface NativeBundleStore {
  download(opts: { legId: string; url: string }): Promise<void>;
  getPath(opts: { legId: string }): Promise<{ path: string }>;
  list(): Promise<{ legs: string[] }>;
}

// ── Web fallbacks (identical to former stubs) ─────────────────────────────────

const audioSessionWebFallback: NativeAudioSession = {
  async setMode(_opts) {},
  async play(_opts) {},
  async pause() {},
  async resume() {},
  async setRate(_opts) {},
  async addListener(_event, _cb) {
    return { remove() {} };
  },
};

const backgroundLocationWebFallback: NativeBackgroundLocation = {
  async startWatch() {
    return { handle: 'stub-handle' };
  },
  async clearWatch() {},
  async addListener(_event, _cb) {
    return { remove() {} };
  },
};

const liveActivityWebFallback: NativeLiveActivity = {
  async update(_opts) {},
  async end() {},
};

const bundleStoreWebFallback: NativeBundleStore = {
  async download(_opts) {},
  async getPath(opts) {
    return { path: `/bundles/${opts.legId}` };
  },
  async list() {
    return { legs: [] };
  },
};

// ── Registered Capacitor plugins ──────────────────────────────────────────────

const _AudioSession = registerPlugin<NativeAudioSession>('AudioSession', {
  web: () => audioSessionWebFallback,
});

const _BackgroundLocation = registerPlugin<NativeBackgroundLocation>('BackgroundLocation', {
  web: () => backgroundLocationWebFallback,
});

const _LiveActivity = registerPlugin<NativeLiveActivity>('LiveActivity', {
  web: () => liveActivityWebFallback,
});

const _BundleStore = registerPlugin<NativeBundleStore>('BundleStore', {
  web: () => bundleStoreWebFallback,
});

// ── Public facades — same interface as before, internally adapts to native ────

export const AudioSession: AudioSessionPlugin = {
  setMode(mode) {
    return _AudioSession.setMode({ mode });
  },
  play(fileUri) {
    return _AudioSession.play({ fileUri });
  },
  pause() {
    return _AudioSession.pause();
  },
  resume() {
    return _AudioSession.resume();
  },
  setRate(r) {
    return _AudioSession.setRate({ rate: r });
  },
  addListener(event, cb) {
    // registerPlugin's addListener is async; return a sync handle immediately
    // and complete the async registration in the background.
    let removeRef: (() => void) | null = null;
    _AudioSession.addListener(event, cb).then((handle) => {
      removeRef = handle.remove.bind(handle);
    });
    return {
      remove() {
        removeRef?.();
      },
    };
  },
};

// Internal map: watch-handle string → listener remove handle.
const _locationListeners = new Map<string, { remove(): void }>();

export const BackgroundLocation: BackgroundLocationPlugin = {
  async watch(cb) {
    // Attach the location event listener before calling startWatch so no
    // fixes are lost between the native start and listener registration.
    const listenerHandle = await _BackgroundLocation.addListener('location', (data) => {
      const fix = data as unknown as BackgroundLocationFix;
      if (fix.lat !== undefined && fix.lon !== undefined) {
        cb(fix);
      }
    });

    const { handle } = await _BackgroundLocation.startWatch();
    _locationListeners.set(handle, listenerHandle);
    return handle;
  },

  async clear(handle) {
    await _BackgroundLocation.clearWatch();
    const listenerHandle = _locationListeners.get(handle);
    if (listenerHandle) {
      listenerHandle.remove();
      _locationListeners.delete(handle);
    }
  },
};

export const LiveActivity: LiveActivityPlugin = {
  async update(data) {
    await _LiveActivity.update(data as Parameters<NativeLiveActivity['update']>[0]);
  },
  async end() {
    return _LiveActivity.end();
  },
};

export const BundleStore: BundleStorePlugin = {
  async download(legId, url) {
    return _BundleStore.download({ legId, url });
  },
  async getPath(legId) {
    const { path } = await _BundleStore.getPath({ legId });
    return path;
  },
  async list() {
    const { legs } = await _BundleStore.list();
    return legs;
  },
};
