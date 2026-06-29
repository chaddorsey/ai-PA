import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mock the Capacitor plugin bridge ──────────────────────────────────────────
// vi.hoisted() ensures the factory runs before vi.mock() hoisting resolves modules.
const mockPlugin = vi.hoisted(() => ({
  addListener: vi.fn(),
  removeAllListeners: vi.fn().mockResolvedValue(undefined),
  startWatch: vi.fn().mockResolvedValue({ handle: 'h1' }),
  clearWatch: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@capacitor/core', () => ({
  registerPlugin: vi.fn(() => mockPlugin),
  WebPlugin: class WebPlugin {},
}));

import { BackgroundLocation } from '../../src/plugins/background-location';

// ─────────────────────────────────────────────────────────────────────────────

describe('BackgroundLocation JS bridge', () => {
  beforeEach(() => vi.clearAllMocks());

  it('watch() calls startWatch and registers the location listener', async () => {
    const cb = vi.fn();
    const handle = await BackgroundLocation.watch(cb);

    expect(typeof handle).toBe('string');
    expect(mockPlugin.startWatch).toHaveBeenCalledOnce();
    expect(mockPlugin.addListener).toHaveBeenCalledWith('location', expect.any(Function));
  });

  it('watch() returns the handle string from startWatch', async () => {
    mockPlugin.startWatch.mockResolvedValueOnce({ handle: 'abc-123' });
    const cb = vi.fn();
    const handle = await BackgroundLocation.watch(cb);
    expect(handle).toBe('abc-123');
  });

  it('clear() calls clearWatch with the correct handle', async () => {
    await BackgroundLocation.clear('h1');
    expect(mockPlugin.clearWatch).toHaveBeenCalledWith({ handle: 'h1' });
  });

  it('clear() also removes all listeners after clearing', async () => {
    await BackgroundLocation.clear('h1');
    expect(mockPlugin.removeAllListeners).toHaveBeenCalledOnce();
  });

  it('fix callback receives the raw {lat, lon, ts, speed} fix from the listener', async () => {
    let registeredCb: ((fix: unknown) => void) | undefined;
    mockPlugin.addListener.mockImplementation((_evt: string, fn: (fix: unknown) => void) => {
      registeredCb = fn;
    });

    const cb = vi.fn();
    await BackgroundLocation.watch(cb);

    expect(registeredCb).toBeDefined();
    const fix = { lat: 37.5, lon: -105.2, ts: 1_234_567_890, speed: 22.5 };
    registeredCb!(fix);
    expect(cb).toHaveBeenCalledWith(fix);
  });
});
