/**
 * DEV: TripSimulator unit tests.
 * Covers: monotonic mile advancement, interpolation, start/stop toggle,
 * speed multipliers, boundary clamping, and leg-58 on-route lat/lon.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { TripSimulator } from './tripSimulator';
import type { Bundle } from 'companion-core';

// ── Minimal bundle fixture using leg-58 geometry ──────────────────────────────
// position_table: [elapsed_min, mile, lat, lon]
// Three rows spanning 0..10 min, 0..5 miles, NOL area
const MOCK_BUNDLE: Bundle = {
  leg: '58',
  schedule_basis: { kind: 'trip-actual', valid_dates: ['2026-07-11'] },
  stations: [],
  geometry: { type: 'LineString', coordinates: [] },
  units: [],
  layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
  eta_table: [],
  position_table: [
    [0,   0.0, 29.94609, -90.07829],  // t=0 min, mile 0
    [5,   2.5, 29.96000, -90.09000],  // t=5 min, mile 2.5
    [10,  5.0, 29.97000, -90.11000],  // t=10 min, mile 5
  ],
};

// ── Helper: build a simulator and fix Date.now() ──────────────────────────────

let sim: TripSimulator;
const BASE_NOW = 1_000_000_000_000; // arbitrary epoch ms

beforeEach(() => {
  sim = new TripSimulator(MOCK_BUNDLE);
  vi.useFakeTimers();
  vi.setSystemTime(BASE_NOW);
});

// ── step() before start ──────────────────────────────────────────────────────

describe('step() before start', () => {
  it('returns mile=0 and first table lat/lon', () => {
    const pos = sim.step(BASE_NOW);
    expect(pos.mile).toBe(0);
    expect(pos.lat).toBeCloseTo(29.94609);
    expect(pos.lon).toBeCloseTo(-90.07829);
    expect(pos.leg).toBe('58');
    expect(pos.source).toBe('predicted');
  });
});

// ── start / stop ─────────────────────────────────────────────────────────────

describe('start() / stop()', () => {
  it('running is false before start()', () => {
    expect(sim.running).toBe(false);
  });

  it('running is true after start()', () => {
    sim.start(1);
    expect(sim.running).toBe(true);
  });

  it('running is false after stop()', () => {
    sim.start(1);
    sim.stop();
    expect(sim.running).toBe(false);
  });

  it('stop() snapshots elapsed so subsequent step() holds position', () => {
    sim.start(1);
    // Advance 5 real minutes = 5 sim minutes at 1x = mile 2.5
    vi.setSystemTime(BASE_NOW + 5 * 60_000);
    sim.stop();

    // After stopping, step() at any future time should still return mile ~2.5
    const pos1 = sim.step(BASE_NOW + 5 * 60_000);
    const pos2 = sim.step(BASE_NOW + 10 * 60_000);
    expect(pos1.mile).toBeCloseTo(2.5, 1);
    expect(pos2.mile).toBeCloseTo(2.5, 1); // not advancing
  });
});

// ── Monotonic advancement ────────────────────────────────────────────────────

describe('step() advances mile monotonically at 1x speed', () => {
  it('mile at t=5min is > mile at t=0', () => {
    sim.start(1);
    const pos0 = sim.step(BASE_NOW);
    vi.setSystemTime(BASE_NOW + 5 * 60_000);
    const pos5 = sim.step(BASE_NOW + 5 * 60_000);
    expect(pos5.mile).toBeGreaterThan(pos0.mile);
  });

  it('mile at t=5min equals 2.5 (midpoint of table)', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW + 5 * 60_000);
    expect(pos.mile).toBeCloseTo(2.5, 4);
  });

  it('mile at t=10min equals 5.0 (end of table)', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW + 10 * 60_000);
    expect(pos.mile).toBeCloseTo(5.0, 4);
  });
});

// ── Speed multiplier ─────────────────────────────────────────────────────────

describe('speed multiplier', () => {
  it('at 4x speed, mile at real t=2.5min equals sim t=10min', () => {
    sim.start(4);
    const pos = sim.step(BASE_NOW + 2.5 * 60_000); // 2.5 real min * 4x = 10 sim min
    expect(pos.mile).toBeCloseTo(5.0, 4);
  });

  it('at 30x speed, mile is clamped at end after short real time', () => {
    sim.start(30);
    // 1 real min * 30 = 30 sim min (past table end of 10 min)
    const pos = sim.step(BASE_NOW + 1 * 60_000);
    expect(pos.mile).toBe(5.0);
  });

  it('at 120x speed (default dev speed), mile is clamped quickly', () => {
    sim.start(120);
    // 0.1 real min * 120 = 12 sim min (past table end of 10 min)
    const pos = sim.step(BASE_NOW + 0.1 * 60_000);
    expect(pos.mile).toBe(5.0);
  });

  it('at 600x speed (max dev squib-per-second), mile is clamped very quickly', () => {
    sim.start(600);
    // 0.02 real min * 600 = 12 sim min (past table end of 10 min)
    const pos = sim.step(BASE_NOW + 0.02 * 60_000);
    expect(pos.mile).toBe(5.0);
  });
});

// ── Boundary clamping ─────────────────────────────────────────────────────────

describe('boundary clamping', () => {
  it('clamps to start when elapsed is before table start', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW - 60_000); // negative elapsed
    expect(pos.mile).toBe(0);
    expect(pos.lat).toBeCloseTo(29.94609);
  });

  it('clamps to end when elapsed is past table end', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW + 100 * 60_000); // way past table end
    expect(pos.mile).toBe(5.0);
    expect(pos.lat).toBeCloseTo(29.97000);
  });
});

// ── On-route lat/lon ─────────────────────────────────────────────────────────

describe('on-route lat/lon', () => {
  it('lat/lon at t=0 matches table row 0', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW);
    expect(pos.lat).toBeCloseTo(29.94609);
    expect(pos.lon).toBeCloseTo(-90.07829);
  });

  it('lat/lon at t=5min matches table row 1', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW + 5 * 60_000);
    expect(pos.lat).toBeCloseTo(29.96000);
    expect(pos.lon).toBeCloseTo(-90.09000);
  });

  it('lat/lon at t=2.5min is linearly interpolated', () => {
    sim.start(1);
    const pos = sim.step(BASE_NOW + 2.5 * 60_000);
    // Midpoint between row[0] and row[1]
    expect(pos.lat).toBeCloseTo((29.94609 + 29.96000) / 2, 4);
    expect(pos.lon).toBeCloseTo((-90.07829 + -90.09000) / 2, 4);
    expect(pos.mile).toBeCloseTo(1.25, 4);
  });
});

// ── reset() ──────────────────────────────────────────────────────────────────

describe('reset()', () => {
  it('resets elapsed and stops simulator', () => {
    sim.start(4);
    vi.setSystemTime(BASE_NOW + 5 * 60_000);
    sim.stop();
    sim.reset();
    expect(sim.running).toBe(false);
    const pos = sim.step(BASE_NOW + 5 * 60_000);
    expect(pos.mile).toBe(0); // back at start
  });
});
