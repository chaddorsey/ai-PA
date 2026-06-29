/**
 * Native plugin interfaces and web stubs.
 * On device, these are replaced by Capacitor plugins (Plan 3).
 * In the browser/test environment, all methods are async no-ops.
 */

export interface BackgroundLocationFix {
  lat: number;
  lon: number;
  ts: number;
  speed?: number;
}

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
  // Phase 2 — stub only
  update(data: Record<string, unknown>): Promise<void>;
  end(): Promise<void>;
}

export interface BundleStorePlugin {
  download(legId: string, url: string): Promise<void>;
  getPath(legId: string): Promise<string>;
  list(): Promise<string[]>;
}

// ── Web stubs ─────────────────────────────────────────────────────────────────

export const AudioSession: AudioSessionPlugin = {
  async setMode(_mode) {},
  async play(_fileUri) {},
  async pause() {},
  async resume() {},
  async setRate(_r) {},
  addListener(_event, _cb) {
    return { remove() {} };
  },
};

export const BackgroundLocation: BackgroundLocationPlugin = {
  async watch(_cb) {
    return 'stub-handle';
  },
  async clear(_handle) {},
};

export const LiveActivity: LiveActivityPlugin = {
  async update(_data) {},
  async end() {},
};

export const BundleStore: BundleStorePlugin = {
  async download(_legId, _url) {},
  async getPath(legId) {
    // Web stub: returns a path that can be used with fetch via the dev proxy
    return `/bundles/${legId}`;
  },
  async list() {
    return [];
  },
};
