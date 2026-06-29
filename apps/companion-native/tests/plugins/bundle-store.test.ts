import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mock the Capacitor plugin bridge ──────────────────────────────────────────
const mockPlugin = vi.hoisted(() => ({
  download: vi.fn().mockResolvedValue(undefined),
  getPath: vi.fn().mockResolvedValue({ path: '/native/bundles/leg3' }),
  list: vi.fn().mockResolvedValue({ legs: ['leg3', 'leg4'] }),
}));

vi.mock('@capacitor/core', () => ({
  registerPlugin: vi.fn(() => mockPlugin),
  WebPlugin: class WebPlugin {},
}));

import { BundleStore } from '../../src/plugins/bundle-store';

// ─────────────────────────────────────────────────────────────────────────────

describe('BundleStore JS bridge', () => {
  beforeEach(() => vi.clearAllMocks());

  // ── download ───────────────────────────────────────────────────────────────

  it('download() passes legId and url to native plugin', async () => {
    await BundleStore.download('leg3', 'https://cdn.example.com/leg3.zip');
    expect(mockPlugin.download).toHaveBeenCalledWith({
      legId: 'leg3',
      url: 'https://cdn.example.com/leg3.zip',
    });
  });

  it('download() resolves without error on success', async () => {
    await expect(
      BundleStore.download('leg58', 'https://cdn.example.com/leg58.zip'),
    ).resolves.toBeUndefined();
  });

  // ── getPath ────────────────────────────────────────────────────────────────

  it('getPath() returns the native path string from the plugin', async () => {
    const path = await BundleStore.getPath('leg3');
    expect(typeof path).toBe('string');
    expect(path).toBe('/native/bundles/leg3');
    expect(mockPlugin.getPath).toHaveBeenCalledWith({ legId: 'leg3' });
  });

  it('getPath() unwraps the { path } envelope from the native call', async () => {
    mockPlugin.getPath.mockResolvedValueOnce({ path: '/var/mobile/leg58' });
    const path = await BundleStore.getPath('leg58');
    expect(path).toBe('/var/mobile/leg58');
  });

  // ── list ───────────────────────────────────────────────────────────────────

  it('list() returns an array of legId strings', async () => {
    const legs = await BundleStore.list();
    expect(Array.isArray(legs)).toBe(true);
    expect(legs).toContain('leg3');
    expect(legs).toContain('leg4');
  });

  it('list() unwraps the { legs } envelope from the native call', async () => {
    mockPlugin.list.mockResolvedValueOnce({ legs: ['3', '58'] });
    const legs = await BundleStore.list();
    expect(legs).toEqual(['3', '58']);
  });

  it('list() returns empty array when no bundles present', async () => {
    mockPlugin.list.mockResolvedValueOnce({ legs: [] });
    const legs = await BundleStore.list();
    expect(legs).toEqual([]);
  });
});
