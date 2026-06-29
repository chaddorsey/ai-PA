/**
 * DeepDiveDirector.test.ts — Task 5
 *
 * Tests:
 * - Does nothing when featuredStories is 'off'
 * - Sets appState.pendingDeepDive when at trigger_mile with mode 'offer'
 * - Offers only once per deep-dive (seenIds guard)
 * - Does not offer a deep-dive before trigger_mile
 * - Does not offer a deep-dive past mile+5
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DeepDiveDirector } from '$lib/deepdive/DeepDiveDirector';
import { appState } from '$lib/core/AppState.svelte';
import { deepdiveState } from '$lib/deepdive/deepdiveState.svelte';
import type { DeepDive, Position } from 'companion-core';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('$lib/core/PlaybackOrchestrator', () => ({
  getOrchestrator: () => ({ silence: vi.fn() }),
}));

vi.mock('$lib/native/plugins', () => ({
  AudioSession: {
    play: vi.fn().mockResolvedValue(undefined),
    setMode: vi.fn(),
    addListener: vi.fn(() => ({ remove: vi.fn() })),
  },
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SAMPLE_DIVE: DeepDive = {
  id: 'dd-casey-jones',
  theme: 'Corridor of Movement',
  title: 'The Wreck of Casey Jones',
  mile: 200,
  trigger_mile: 192,
  nearest_place: 'Vaughan, MS',
  hook: 'A foggy April morning.',
  body_md: '## Casey\n\nStory body.',
  narration_text: 'Narration.',
  est_listen_min: 4,
  audio: null,
  images: [],
  sources: [],
  salience: 4,
};

function makePosition(mile: number): Position {
  return { mile, lat: 32.9, lon: -90.1, source: 'predicted', direction: 1, leg: '58', stopped: false };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('DeepDiveDirector', () => {
  let director: DeepDiveDirector;

  beforeEach(() => {
    director = new DeepDiveDirector();
    deepdiveState.reset();
    appState.pendingDeepDive = null;
    appState.settings.featuredStories = 'offer';
    // @ts-expect-error - minimal bundle
    appState.bundle = { leg: '58', deepdives: [SAMPLE_DIVE] };
  });

  it('does nothing when featuredStories is "off"', () => {
    appState.settings.featuredStories = 'off';
    director.update(makePosition(195));
    expect(appState.pendingDeepDive).toBeNull();
  });

  it('does nothing when bundle has no deepdives', () => {
    // @ts-expect-error - minimal bundle
    appState.bundle = { leg: '58', deepdives: [] };
    director.update(makePosition(195));
    expect(appState.pendingDeepDive).toBeNull();
  });

  it('sets pendingDeepDive when position is at trigger_mile with mode "offer"', () => {
    appState.settings.featuredStories = 'offer';
    // trigger_mile is 192; position at 195 is within window (192 ≤ 195 < 205)
    director.update(makePosition(195));
    expect(appState.pendingDeepDive).not.toBeNull();
    expect(appState.pendingDeepDive?.id).toBe('dd-casey-jones');
  });

  it('marks the deep-dive as seen after offering so it is not offered again', () => {
    director.update(makePosition(195));
    expect(appState.pendingDeepDive).not.toBeNull();

    // Clear the pending to simulate user dismissing
    appState.pendingDeepDive = null;

    // Second position update in same window — should NOT re-offer
    director.update(makePosition(197));
    expect(appState.pendingDeepDive).toBeNull();
  });

  it('does NOT offer when position is before trigger_mile', () => {
    // trigger_mile is 192; position at 190 is outside the window
    director.update(makePosition(190));
    expect(appState.pendingDeepDive).toBeNull();
  });

  it('does NOT offer when position is past mile+5 (205)', () => {
    // mile is 200; position at 206 is outside the window
    director.update(makePosition(206));
    expect(appState.pendingDeepDive).toBeNull();
  });

  it('does NOT offer when position is exactly at mile+5 (205)', () => {
    // window is trigger_mile ≤ mile < mile+5; 205 is NOT inside
    director.update(makePosition(205));
    expect(appState.pendingDeepDive).toBeNull();
  });

  it('respects the offer boundary exactly at trigger_mile (192)', () => {
    director.update(makePosition(192));
    expect(appState.pendingDeepDive?.id).toBe('dd-casey-jones');
  });

  it('does nothing when bundle is null', () => {
    appState.bundle = null;
    director.update(makePosition(195));
    expect(appState.pendingDeepDive).toBeNull();
  });
});
