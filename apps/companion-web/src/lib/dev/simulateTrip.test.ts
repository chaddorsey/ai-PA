/**
 * DEV: Simulate-trip toggle integration test.
 * Covers the start/stop toggle behavior and that the simulator
 * produces on-route positions when active.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { TripSimulator } from './tripSimulator';
import type { Bundle } from 'companion-core';

const BASE_NOW = 2_000_000_000_000;

// Minimal leg-58 bundle with two position_table rows
const BUNDLE: Bundle = {
  leg: '58',
  schedule_basis: { kind: 'trip-actual', valid_dates: ['2026-07-11'] },
  stations: [
    {
      code: 'NOL', name: 'New Orleans, LA', mile: 0,
      lat: 29.94609, lon: -90.07829,
      sched_arr: null, sched_dep: '2026-07-11T15:45:00-05:00', dwell_min: 0,
    },
  ],
  geometry: { type: 'LineString', coordinates: [[-90.07829, 29.94609]] },
  units: [],
  layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
  eta_table: [],
  position_table: [
    [0,  0.0, 29.94609, -90.07829],
    [60, 100.0, 30.50718, -90.46217],
  ],
};

describe('Simulate trip toggle', () => {
  let sim: TripSimulator;

  beforeEach(() => {
    sim = new TripSimulator(BUNDLE);
    vi.useFakeTimers();
    vi.setSystemTime(BASE_NOW);
  });

  it('toggle ON: start() sets running=true', () => {
    expect(sim.running).toBe(false);
    sim.start(1);
    expect(sim.running).toBe(true);
  });

  it('toggle OFF: stop() sets running=false', () => {
    sim.start(1);
    sim.stop();
    expect(sim.running).toBe(false);
  });

  it('toggle ON then OFF then ON resumes from last position (not start)', () => {
    sim.start(1);
    // Advance 30 real minutes at 1x = 30 sim minutes = 50 miles
    vi.setSystemTime(BASE_NOW + 30 * 60_000);
    const midPos = sim.step(BASE_NOW + 30 * 60_000);
    expect(midPos.mile).toBeCloseTo(50.0, 0);

    // Stop at 30 min
    sim.stop();

    // Resume at 2x speed
    vi.setSystemTime(BASE_NOW + 30 * 60_000);
    sim.start(2);

    // After 5 more real minutes at 2x = 10 sim minutes from 50-mile mark
    vi.setSystemTime(BASE_NOW + 35 * 60_000);
    const laterPos = sim.step(BASE_NOW + 35 * 60_000);

    // Should be at ~50 + 10/60 * 100 = ~50 + 16.67 = ~66.67 miles
    expect(laterPos.mile).toBeGreaterThan(midPos.mile);
    expect(laterPos.mile).toBeCloseTo(66.67, 0);
  });

  it('simulator produces on-route lat/lon (within leg-58 bounding box)', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW + 30 * 60_000); // halfway
    // lat should be between 29.94 and 30.51 (the two table rows)
    expect(pos.lat).toBeGreaterThan(29.94);
    expect(pos.lat).toBeLessThan(30.52);
    // lon should be between -90.47 and -90.07
    expect(pos.lon).toBeLessThan(-90.07);
    expect(pos.lon).toBeGreaterThan(-90.47);
  });

  it('speed control: at 4x, sim advances 4x faster than real time', () => {
    sim.start(4);
    // 10 real minutes at 4x = 40 sim minutes
    const pos = sim.step(BASE_NOW + 10 * 60_000);
    // 40 sim minutes / 60 total * 100 miles = ~66.67 miles
    expect(pos.mile).toBeCloseTo(66.67, 0);
  });

  it('speed control: at 0.5x, sim advances half as fast as real time', () => {
    sim.start(0.5);
    // 60 real minutes at 0.5x = 30 sim minutes
    const pos = sim.step(BASE_NOW + 60 * 60_000);
    // 30 sim minutes / 60 total * 100 miles = 50 miles
    expect(pos.mile).toBeCloseTo(50.0, 0);
  });

  it('position.leg matches the bundle leg', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW);
    expect(pos.leg).toBe('58');
  });

  it('position.source is "predicted" (not live GPS)', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW + 10 * 60_000);
    expect(pos.source).toBe('predicted');
  });
});
