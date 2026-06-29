import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mock the Capacitor plugin bridge ──────────────────────────────────────────
const mockPlugin = vi.hoisted(() => ({
  start: vi.fn().mockResolvedValue(undefined),
  update: vi.fn().mockResolvedValue(undefined),
  end: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@capacitor/core', () => ({
  registerPlugin: vi.fn(() => mockPlugin),
  WebPlugin: class WebPlugin {},
}));

import { LiveActivity } from '../../src/plugins/live-activity';
import type { LiveActivityState } from '../../src/plugins/live-activity';

// ─────────────────────────────────────────────────────────────────────────────

const exampleState: LiveActivityState = {
  nowPlaying: 'Raton Pass',
  nextStop: 'Trinidad',
  etaText: '14 min',
  positionText: 'MP 1087',
};

describe('LiveActivity JS bridge (Phase-2 stub)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('start() passes all four state fields to the native plugin', async () => {
    await LiveActivity.start(exampleState);
    expect(mockPlugin.start).toHaveBeenCalledWith(exampleState);
  });

  it('update() passes updated state to the native plugin', async () => {
    const updated: LiveActivityState = {
      ...exampleState,
      etaText: '12 min',
      positionText: 'MP 1085',
    };
    await LiveActivity.update(updated);
    expect(mockPlugin.update).toHaveBeenCalledWith(updated);
  });

  it('end() calls plugin.end() with no arguments', async () => {
    await LiveActivity.end();
    expect(mockPlugin.end).toHaveBeenCalledWith();
    expect(mockPlugin.end).toHaveBeenCalledOnce();
  });

  it('all three methods return Promises that resolve', async () => {
    await expect(LiveActivity.start(exampleState)).resolves.toBeUndefined();
    await expect(LiveActivity.update(exampleState)).resolves.toBeUndefined();
    await expect(LiveActivity.end()).resolves.toBeUndefined();
  });
});
