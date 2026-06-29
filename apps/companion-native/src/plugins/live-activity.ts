/**
 * LiveActivity — Capacitor plugin bridge.
 *
 * Phase 2 — the Swift ActivityKit / Widget Extension implementation is deferred.
 * This file ships a JS stub so Plan 4 can import LiveActivity without crashing.
 * All methods are no-ops on web and on the current beta build.
 *
 * When Phase 2 ships, replace the registerPlugin stub impl with the real Swift plugin.
 *
 * Matches the locked Plan 0 §F contract:
 *   LiveActivity.start(state)   → Promise<void>
 *   LiveActivity.update(state)  → Promise<void>
 *   LiveActivity.end()          → Promise<void>
 *
 * LiveActivityState = { nowPlaying, nextStop, etaText, positionText }
 */
import { registerPlugin } from '@capacitor/core';

export interface LiveActivityState {
  nowPlaying: string;
  nextStop: string;
  etaText: string;
  positionText: string;
}

interface LiveActivityNativePlugin {
  start(state: LiveActivityState): Promise<void>;
  update(state: LiveActivityState): Promise<void>;
  end(): Promise<void>;
}

// Phase-2 stub: web impl is a no-op; native impl not yet wired (see BUILD_IOS.md §Phase 2).
const _plugin = registerPlugin<LiveActivityNativePlugin>('LiveActivity', {
  web: () =>
    Promise.resolve({
      start: async (_: LiveActivityState) => {},
      update: async (_: LiveActivityState) => {},
      end: async () => {},
      addListener: () => ({ remove: () => {} }),
      removeAllListeners: async () => {},
    } as unknown as LiveActivityNativePlugin),
});

export const LiveActivity = {
  /** Start a Live Activity on the Dynamic Island / Lock Screen (Phase 2; no-op in beta). */
  start(state: LiveActivityState): Promise<void> {
    return _plugin.start(state);
  },

  /** Update the Live Activity state (Phase 2; no-op in beta). */
  update(state: LiveActivityState): Promise<void> {
    return _plugin.update(state);
  },

  /** Dismiss the Live Activity (Phase 2; no-op in beta). */
  end(): Promise<void> {
    return _plugin.end();
  },
};
