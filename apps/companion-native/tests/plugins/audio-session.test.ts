import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mock the Capacitor plugin bridge ──────────────────────────────────────────
// vi.hoisted() ensures the mock factory runs before module resolution.
const mockPlugin = vi.hoisted(() => ({
  setMode: vi.fn().mockResolvedValue(undefined),
  play: vi.fn().mockResolvedValue(undefined),
  pause: vi.fn().mockResolvedValue(undefined),
  resume: vi.fn().mockResolvedValue(undefined),
  setRate: vi.fn().mockResolvedValue(undefined),
  addListener: vi.fn().mockReturnValue({ remove: vi.fn() }),
}));

vi.mock('@capacitor/core', () => ({
  registerPlugin: vi.fn(() => mockPlugin),
  WebPlugin: class WebPlugin {},
}));

import { AudioSession } from '../../src/plugins/audio-session';

// ─────────────────────────────────────────────────────────────────────────────

describe('AudioSession JS bridge', () => {
  beforeEach(() => vi.clearAllMocks());

  // ── setMode ────────────────────────────────────────────────────────────────

  it('setMode("duck") passes mode option to native plugin', async () => {
    await AudioSession.setMode('duck');
    expect(mockPlugin.setMode).toHaveBeenCalledWith({ mode: 'duck' });
  });

  it('setMode("pause") passes mode option to native plugin', async () => {
    await AudioSession.setMode('pause');
    expect(mockPlugin.setMode).toHaveBeenCalledWith({ mode: 'pause' });
  });

  it('setMode("interrupt-spoken") passes mode option to native plugin', async () => {
    await AudioSession.setMode('interrupt-spoken');
    expect(mockPlugin.setMode).toHaveBeenCalledWith({ mode: 'interrupt-spoken' });
  });

  // ── play ───────────────────────────────────────────────────────────────────

  it('play() passes fileUri to native plugin', async () => {
    await AudioSession.play('file:///native/bundles/leg3/audio/abc.mp3');
    expect(mockPlugin.play).toHaveBeenCalledWith({
      fileUri: 'file:///native/bundles/leg3/audio/abc.mp3',
    });
  });

  // ── pause / resume ─────────────────────────────────────────────────────────

  it('pause() delegates to plugin.pause()', async () => {
    await AudioSession.pause();
    expect(mockPlugin.pause).toHaveBeenCalledOnce();
  });

  it('resume() delegates to plugin.resume()', async () => {
    await AudioSession.resume();
    expect(mockPlugin.resume).toHaveBeenCalledOnce();
  });

  // ── setRate ────────────────────────────────────────────────────────────────

  it('setRate() passes rate as number wrapped in opts object', async () => {
    await AudioSession.setRate(1.25);
    expect(mockPlugin.setRate).toHaveBeenCalledWith({ rate: 1.25 });
  });

  it('setRate() accepts values at range boundaries', async () => {
    await AudioSession.setRate(0.5);
    expect(mockPlugin.setRate).toHaveBeenCalledWith({ rate: 0.5 });
    await AudioSession.setRate(2.0);
    expect(mockPlugin.setRate).toHaveBeenCalledWith({ rate: 2.0 });
  });

  // ── addListener ────────────────────────────────────────────────────────────

  it('addListener("ended", cb) delegates to plugin and returns a handle with .remove()', () => {
    const cb = vi.fn();
    const handle = AudioSession.addListener('ended', cb);
    expect(mockPlugin.addListener).toHaveBeenCalledWith('ended', cb);
    expect(typeof handle.remove).toBe('function');
  });

  it('addListener("interrupt", cb) delegates to plugin', () => {
    const cb = vi.fn();
    AudioSession.addListener('interrupt', cb);
    expect(mockPlugin.addListener).toHaveBeenCalledWith('interrupt', cb);
  });
});
