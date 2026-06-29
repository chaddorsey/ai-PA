import { describe, it, expect } from 'vitest';
import { createAppState } from './AppState.svelte';
import type { Bundle, Unit } from 'companion-core';

// Minimal proxy bundle fixture matching real bundle schema
const PROXY_BUNDLE: Bundle = {
  leg: '58',
  schedule_basis: { kind: 'trip-actual', valid_dates: ['2026-07-11'] },
  stations: [
    { code: 'NOL', name: 'New Orleans, LA', mile: 0, lat: 29.94609, lon: -90.07829, sched_arr: null, sched_dep: '2026-07-11T15:45:00-05:00', dwell_min: 0 },
  ],
  geometry: { type: 'LineString', coordinates: [[-90.07829, 29.94609]] },
  units: [
    {
      id: 'u-001',
      kind: 'squib',
      mile: 5,
      place: 'River Bend',
      side: 'left',
      salience: 4,
      theme: 'history',
      text: 'Historic river bend.',
      lat: 29.95,
      lon: -90.08,
      audio: 'audio/u-001.mp3',
      dur_s: 22,
    } as Unit,
  ],
  layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
  position_table: [[0, 0, 29.94609, -90.07829]],
  eta_table: [],
};

describe('createAppState', () => {
  it('initializes with null bundle, position, and nowPlaying', () => {
    const state = createAppState();
    expect(state.bundle).toBeNull();
    expect(state.position).toBeNull();
    expect(state.nowPlaying).toBeNull();
  });

  it('initializes with correct default settings', () => {
    const state = createAppState();
    expect(state.settings.fillPct).toBe(0.6);
    expect(state.settings.highlightOnly).toBe(false);
    expect(state.settings.themes).toBeInstanceOf(Set);
    expect(state.settings.themes.size).toBe(0);
    expect(state.settings.audioMode).toBe('interrupt-spoken');
  });

  it('accepts a loaded bundle', () => {
    const state = createAppState();
    state.bundle = PROXY_BUNDLE;
    expect(state.bundle).toBe(PROXY_BUNDLE);
    expect(state.bundle.units).toHaveLength(1);
    expect(state.bundle.leg).toBe('58');
  });

  it('allows nowPlaying to be set to a unit', () => {
    const state = createAppState();
    state.bundle = PROXY_BUNDLE;
    state.nowPlaying = PROXY_BUNDLE.units[0];
    expect(state.nowPlaying?.place).toBe('River Bend');
  });

  it('allows nowPlaying to be cleared to null', () => {
    const state = createAppState();
    state.nowPlaying = PROXY_BUNDLE.units[0];
    state.nowPlaying = null;
    expect(state.nowPlaying).toBeNull();
  });

  it('has a favorites instance', () => {
    const state = createAppState();
    expect(state.favorites).toBeDefined();
    expect(typeof state.favorites.add).toBe('function');
  });

  it('allows settings mutation', () => {
    const state = createAppState();
    state.settings.fillPct = 0.8;
    expect(state.settings.fillPct).toBe(0.8);
    state.settings.audioMode = 'duck';
    expect(state.settings.audioMode).toBe('duck');
  });
});
