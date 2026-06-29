import { describe, it, expect, vi } from 'vitest';

// Mock each plugin module so this test doesn't need @capacitor/core
vi.mock('../../src/plugins/background-location', () => ({
  BackgroundLocation: { watch: vi.fn(), clear: vi.fn() },
}));
vi.mock('../../src/plugins/audio-session', () => ({
  AudioSession: { play: vi.fn(), pause: vi.fn(), resume: vi.fn(), setRate: vi.fn(), setMode: vi.fn(), addListener: vi.fn() },
}));
vi.mock('../../src/plugins/live-activity', () => ({
  LiveActivity: { start: vi.fn(), update: vi.fn(), end: vi.fn() },
}));
vi.mock('../../src/plugins/bundle-store', () => ({
  BundleStore: { download: vi.fn(), getPath: vi.fn(), list: vi.fn() },
}));

import {
  BackgroundLocation,
  AudioSession,
  LiveActivity,
  BundleStore,
} from '../../src/plugins/index';

describe('plugin index re-exports', () => {
  it('re-exports BackgroundLocation with watch and clear', () => {
    expect(BackgroundLocation).toBeDefined();
    expect(typeof BackgroundLocation.watch).toBe('function');
    expect(typeof BackgroundLocation.clear).toBe('function');
  });

  it('re-exports AudioSession with all methods', () => {
    expect(AudioSession).toBeDefined();
    expect(typeof AudioSession.play).toBe('function');
    expect(typeof AudioSession.pause).toBe('function');
    expect(typeof AudioSession.resume).toBe('function');
    expect(typeof AudioSession.setRate).toBe('function');
    expect(typeof AudioSession.setMode).toBe('function');
    expect(typeof AudioSession.addListener).toBe('function');
  });

  it('re-exports LiveActivity with start, update, end', () => {
    expect(LiveActivity).toBeDefined();
    expect(typeof LiveActivity.start).toBe('function');
    expect(typeof LiveActivity.update).toBe('function');
    expect(typeof LiveActivity.end).toBe('function');
  });

  it('re-exports BundleStore with download, getPath, list', () => {
    expect(BundleStore).toBeDefined();
    expect(typeof BundleStore.download).toBe('function');
    expect(typeof BundleStore.getPath).toBe('function');
    expect(typeof BundleStore.list).toBe('function');
  });
});
