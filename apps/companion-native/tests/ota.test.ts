import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mock @capawesome/capacitor-live-update ────────────────────────────────────
vi.mock('@capawesome/capacitor-live-update', () => ({
  LiveUpdate: {
    reload: vi.fn().mockResolvedValue(undefined),
  },
}));

// ── Mock global fetch ─────────────────────────────────────────────────────────
global.fetch = vi.fn() as typeof fetch;

import { OTA } from '../src/ota';
import { LiveUpdate } from '@capawesome/capacitor-live-update';

// ─────────────────────────────────────────────────────────────────────────────

describe('OTA.checkForUpdate()', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns available=true when remote version differs from local', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ version: '1.0.1', url: 'https://cdn.example.com/web-1.0.1.zip' }),
    });

    const result = await OTA.checkForUpdate('1.0.0', 'https://cdn.example.com/version.json');

    expect(result.available).toBe(true);
    expect(result.version).toBe('1.0.1');
    expect(result.url).toBe('https://cdn.example.com/web-1.0.1.zip');
  });

  it('returns available=false when versions match', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ version: '1.0.0', url: '' }),
    });

    const result = await OTA.checkForUpdate('1.0.0', 'https://cdn.example.com/version.json');

    expect(result.available).toBe(false);
    expect(result.version).toBe('1.0.0');
    expect(result.url).toBeUndefined();
  });

  it('returns available=false on non-OK HTTP response (server error)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 503,
    });

    const result = await OTA.checkForUpdate('1.0.0', 'https://cdn.example.com/version.json');

    expect(result.available).toBe(false);
    expect(result.version).toBe('1.0.0');
  });

  it('returns available=false on network error (graceful offline)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));

    const result = await OTA.checkForUpdate('1.0.0', 'https://cdn.example.com/version.json');

    expect(result.available).toBe(false);
    expect(result.version).toBe('1.0.0');
  });

  it('requests the versionUrl with cache: no-store to bypass CDN cache', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ version: '1.0.0', url: '' }),
    });

    await OTA.checkForUpdate('1.0.0', 'https://cdn.example.com/version.json');

    expect(global.fetch).toHaveBeenCalledWith(
      'https://cdn.example.com/version.json',
      { cache: 'no-store' },
    );
  });
});

describe('OTA.apply()', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls LiveUpdate.reload()', async () => {
    await OTA.apply();
    expect(LiveUpdate.reload).toHaveBeenCalledOnce();
  });

  it('resolves without error even if LiveUpdate.reload throws (plugin not registered in browser)', async () => {
    (LiveUpdate.reload as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Plugin not registered'));
    await expect(OTA.apply()).resolves.toBeUndefined();
  });
});
