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
import proxyBundle from '/Volumes/main-drive/ai-PA/tools/amtrak-position-engine/bundles/leg58/bundle.json' with { type: 'json' };

describe('initBundle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    appState.bundle = null;
  });

  it('returns first-run when leg is not in BundleStore.list()', async () => {
    vi.mocked(BundleStore.list).mockResolvedValue([]);
    const result = await initBundle('58');
    expect(result.status).toBe('first-run');
    if (result.status === 'first-run') {
      expect(result.message).toBe('Download your trip');
    }
    expect(appState.bundle).toBeNull();
  });

  it('returns loaded and sets appState.bundle when leg is available', async () => {
    vi.mocked(BundleStore.list).mockResolvedValue(['58']);
    vi.mocked(BundleStore.getPath).mockResolvedValue('/bundles/58');
    vi.mocked(loadBundle).mockResolvedValue(proxyBundle as import('companion-core').Bundle);

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

    const result = await initBundle('58');
    expect(result.status).toBe('error');
    expect(appState.bundle).toBeNull();
  });
});
