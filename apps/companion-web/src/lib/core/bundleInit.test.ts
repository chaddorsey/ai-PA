import { describe, it, expect, vi, beforeEach } from 'vitest';
import { initBundle } from './bundleInit';
import { appState } from './AppState.svelte';

// Mock the plugins module
vi.mock('$lib/native/plugins', () => ({
  BundleStore: {
    list: vi.fn(),
    getPath: vi.fn(),
    download: vi.fn(),
  },
  AudioSession: {
    setMode: vi.fn(),
    play: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    setRate: vi.fn(),
    addListener: vi.fn(() => ({ remove: vi.fn() })),
  },
  BackgroundLocation: {
    watch: vi.fn(),
    clear: vi.fn(),
  },
  LiveActivity: {
    update: vi.fn(),
    end: vi.fn(),
  },
}));

vi.mock('companion-core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('companion-core')>();
  return {
    ...actual,
    loadBundle: vi.fn(),
  };
});

import { loadBundle } from 'companion-core';
import { BundleStore } from '$lib/native/plugins';

// Load the real proxy bundle as fixture
import proxyBundle from '../../../../../tools/amtrak-position-engine/bundles/leg58/bundle.json' with { type: 'json' };

describe('initBundle — normal BundleStore path', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    appState.bundle = null;
    // Default: global fetch not needed for normal path
    vi.stubGlobal('fetch', vi.fn());
  });

  it('returns error when leg is not in BundleStore.list() and embedded fetch also fails', async () => {
    vi.mocked(BundleStore.list).mockResolvedValue([]);
    // With DEV_EMBEDDED_BUNDLE=true, initBundle always tries the embedded fetch first.
    // When fetch returns undefined (no-op mock), the embedded load throws a TypeError.
    // Since the leg is not in BundleStore either, the embedded error is surfaced.
    const result = await initBundle('57');
    expect(result.status).toBe('error');
    expect(appState.bundle).toBeNull();
  });

  it('returns loaded and sets appState.bundle when leg is available via BundleStore (embedded fetch fails first)', async () => {
    vi.mocked(BundleStore.list).mockResolvedValue(['58']);
    vi.mocked(BundleStore.getPath).mockResolvedValue('/bundles/58');
    vi.mocked(loadBundle).mockResolvedValue(proxyBundle as import('companion-core').Bundle);
    // fetch returns a non-ok response so embedded path fails, falls through to BundleStore
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    const result = await initBundle('58');
    expect(result.status).toBe('loaded');
    if (result.status === 'loaded') {
      expect(result.bundle.leg).toBe('58');
    }
    expect(appState.bundle).not.toBeNull();
    expect(appState.bundle?.leg).toBe('58');
  });

  it('handles loadBundle errors gracefully', async () => {
    vi.mocked(BundleStore.list).mockResolvedValue(['58']);
    vi.mocked(BundleStore.getPath).mockResolvedValue('/bundles/58');
    vi.mocked(loadBundle).mockRejectedValue(new Error('network error'));
    // embedded fetch fails → falls through to BundleStore → loadBundle throws
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    const result = await initBundle('58');
    expect(result.status).toBe('error');
    expect(appState.bundle).toBeNull();
  });
});

// ── DEV: embedded bundle fallback ─────────────────────────────────────────────

describe('DEV embedded bundle fallback (BundleStore empty, leg=58)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    appState.bundle = null;
    // BundleStore is empty — this triggers the dev fallback for leg '58'
    vi.mocked(BundleStore.list).mockResolvedValue([]);
  });

  it('fetches /bundles/leg58/bundle.json when BundleStore is empty', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => proxyBundle,
    });
    vi.stubGlobal('fetch', mockFetch);

    const result = await initBundle('58');
    expect(result.status).toBe('loaded');
    expect(mockFetch).toHaveBeenCalledWith('/bundles/leg58/bundle.json');
  });

  it('sets appState.bundle from the embedded bundle', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => proxyBundle,
    }));

    await initBundle('58');
    expect(appState.bundle).not.toBeNull();
    expect(appState.bundle?.leg).toBe('58');
  });

  it('rewrites relative audio URIs to /bundles/leg58/audio/... absolute paths', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => proxyBundle,
    }));

    const result = await initBundle('58');
    expect(result.status).toBe('loaded');
    if (result.status === 'loaded') {
      // All units that have audio should have absolute paths
      const unitsWithAudio = result.bundle.units.filter((u) => u.audio);
      expect(unitsWithAudio.length).toBeGreaterThan(0);
      for (const unit of unitsWithAudio) {
        expect(unit.audio).toMatch(/^\/bundles\/leg58\//);
        expect(unit.audio).not.toMatch(/^audio\//);
      }
    }
  });

  it('returns error when the embedded bundle fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
    }));

    const result = await initBundle('58');
    expect(result.status).toBe('error');
    expect(appState.bundle).toBeNull();
  });

  it('returns error when fetch rejects (network error)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    const result = await initBundle('58');
    expect(result.status).toBe('error');
    expect(appState.bundle).toBeNull();
  });

  it('uses BundleStore when leg is already downloaded (embedded fetch fails first)', async () => {
    // Even with DEV_EMBEDDED_BUNDLE, if the leg is already downloaded, use BundleStore
    vi.mocked(BundleStore.list).mockResolvedValue(['58']);
    vi.mocked(BundleStore.getPath).mockResolvedValue('/bundles/58');
    vi.mocked(loadBundle).mockResolvedValue(proxyBundle as import('companion-core').Bundle);

    // Embedded fetch fails (non-ok) → falls through to BundleStore
    const mockFetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });
    vi.stubGlobal('fetch', mockFetch);

    const result = await initBundle('58');
    expect(result.status).toBe('loaded');
    // The loadBundle mock was called (BundleStore path)
    expect(vi.mocked(loadBundle)).toHaveBeenCalled();
  });
});

// ── DEV: embedded fetch works for leg 3 too ──────────────────────────────────

describe('DEV embedded bundle fallback (leg=3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    appState.bundle = null;
    vi.mocked(BundleStore.list).mockResolvedValue([]);
  });

  it('fetches /bundles/leg3/bundle.json for leg 3', async () => {
    // Use a minimal bundle fixture that matches leg 3
    const leg3Bundle = { ...proxyBundle, leg: '3' };
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => leg3Bundle,
    });
    vi.stubGlobal('fetch', mockFetch);

    const result = await initBundle('3');
    expect(result.status).toBe('loaded');
    expect(mockFetch).toHaveBeenCalledWith('/bundles/leg3/bundle.json');
  });

  it('rewrites audio URIs to /bundles/leg3/audio/... for leg 3', async () => {
    const leg3Bundle = { ...proxyBundle, leg: '3' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => leg3Bundle,
    }));

    const result = await initBundle('3');
    expect(result.status).toBe('loaded');
    if (result.status === 'loaded') {
      const unitsWithAudio = result.bundle.units.filter((u) => u.audio);
      expect(unitsWithAudio.length).toBeGreaterThan(0);
      for (const unit of unitsWithAudio) {
        expect(unit.audio).toMatch(/^\/bundles\/leg3\//);
      }
    }
  });
});
