import { describe, it, expect, beforeEach } from 'vitest';
import { ApproachCue, APPROACH_ETA_THRESHOLD_MS, APPROACH_DISTANCE_THRESHOLD_MI } from '$lib/core/ApproachCue';
import type { Position, Station, EtaResult } from 'companion-core';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const NOW = Date.now();

// ETA mock: within threshold for FPK, beyond threshold for GJT
const FOUR_MIN_MS = 4 * 60 * 1000;   // within 15-min threshold
const TWENTY_MIN_MS = 20 * 60 * 1000; // beyond 15-min threshold

function makeEtaMock(overrides?: Record<string, number>) {
  return {
    toStation: (code: string, _pos: Position): EtaResult => {
      const etaMs = overrides?.[code] ?? (NOW + TWENTY_MIN_MS);
      const estimated = false;
      return { p10: etaMs - 30_000, p50: etaMs, p90: etaMs + 30_000, estimated };
    },
  };
}

const STATIONS: Station[] = [
  { code: 'FPK', name: 'Fraser/Winter Park', mile: 56, lat: 39.9, lon: -105.8, sched_arr: null, sched_dep: '2026-07-12T10:00:00-06:00', dwell_min: 4 },
  { code: 'GJT', name: 'Grand Junction', mile: 245, lat: 39.06, lon: -108.55, sched_arr: '2026-07-12T15:00:00-07:00', sched_dep: '2026-07-12T15:10:00-07:00', dwell_min: 10 },
];

const POSITION_BEFORE_FPK: Position = {
  mile: 52, lat: 39.85, lon: -105.75, source: 'gps', direction: 1, leg: '58', stopped: false,
};

const POSITION_PAST_FPK: Position = {
  mile: 60, lat: 39.9, lon: -105.9, source: 'gps', direction: 1, leg: '58', stopped: false,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ApproachCue (class)', () => {

  it('is a class — separate instances have independent state', () => {
    const cue1 = new ApproachCue();
    const cue2 = new ApproachCue();
    const eta = makeEtaMock({ FPK: NOW + FOUR_MIN_MS });

    const r1 = cue1.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(r1).not.toBeNull();
    expect(r1!.station.code).toBe('FPK');

    // cue2 has not fired yet — it should also fire
    const r2 = cue2.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(r2).not.toBeNull();
    expect(r2!.station.code).toBe('FPK');

    // cue1 should not fire again (already fired)
    const r1b = cue1.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(r1b).toBeNull();

    // cue2 should not fire again either
    const r2b = cue2.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(r2b).toBeNull();
  });

  it('fires when ETA p50 is within threshold', () => {
    const cue = new ApproachCue();
    const eta = makeEtaMock({ FPK: NOW + FOUR_MIN_MS });
    const result = cue.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(result).not.toBeNull();
    expect(result!.station.code).toBe('FPK');
  });

  it('does NOT fire when ETA p50 exceeds threshold and distance exceeds threshold', () => {
    const cue = new ApproachCue();
    // GJT is at mile 245, position at mile 52 — far beyond distance threshold too
    const eta = makeEtaMock({ FPK: NOW + TWENTY_MIN_MS, GJT: NOW + TWENTY_MIN_MS });
    // Use only GJT in the station list (far away)
    const result = cue.check(POSITION_BEFORE_FPK, eta, [STATIONS[1]]);
    expect(result).toBeNull();
  });

  it('fires at most once per station per instance lifecycle (no double-fire)', () => {
    const cue = new ApproachCue();
    const eta = makeEtaMock({ FPK: NOW + FOUR_MIN_MS });
    const r1 = cue.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(r1).not.toBeNull();
    const r2 = cue.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(r2).toBeNull(); // must not fire again
  });

  it('does NOT fire for a station the train has already passed', () => {
    const cue = new ApproachCue();
    const eta = makeEtaMock({ FPK: NOW + FOUR_MIN_MS });
    // position is past FPK (mile 60 > mile 56)
    const result = cue.check(POSITION_PAST_FPK, eta, STATIONS);
    // FPK is behind us, GJT is 185 miles ahead with 20-min eta (beyond threshold)
    expect(result).toBeNull();
  });

  it('reset() clears fired history — same station can fire again', () => {
    const cue = new ApproachCue();
    const eta = makeEtaMock({ FPK: NOW + FOUR_MIN_MS });

    const r1 = cue.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(r1).not.toBeNull();

    // Would not fire again
    expect(cue.check(POSITION_BEFORE_FPK, eta, STATIONS)).toBeNull();

    // After reset, it should fire again
    cue.reset();
    const r2 = cue.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(r2).not.toBeNull();
    expect(r2!.station.code).toBe('FPK');
  });

  it('returns null when position.source is "off-route"', () => {
    const cue = new ApproachCue();
    const eta = makeEtaMock({ FPK: NOW + FOUR_MIN_MS });
    const offRoute: Position = { ...POSITION_BEFORE_FPK, source: 'off-route' };
    const result = cue.check(offRoute, eta, STATIONS);
    expect(result).toBeNull();
  });

  it('fires based on distance threshold when ETA throws', () => {
    const cue = new ApproachCue();
    // ETA always throws
    const throwingEta = {
      toStation: (_code: string, _pos: Position): EtaResult => {
        throw new Error('no ETA');
      },
    };
    // Station within distance threshold (mile 55, position at mile 52 → 3 miles ahead)
    const nearStation: Station = {
      code: 'NEAR', name: 'Near Station', mile: 55, lat: 39.9, lon: -105.79,
      sched_arr: null, sched_dep: null, dwell_min: 2,
    };
    const result = cue.check(POSITION_BEFORE_FPK, throwingEta, [nearStation]);
    expect(result).not.toBeNull();
    expect(result!.station.code).toBe('NEAR');
  });

  it('etaMs in the result matches the p50 from the ETA mock', () => {
    const cue = new ApproachCue();
    const expectedEta = NOW + FOUR_MIN_MS;
    const eta = makeEtaMock({ FPK: expectedEta });
    const result = cue.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(result).not.toBeNull();
    expect(result!.etaMs).toBe(expectedEta);
  });

  it('no state leakage between separate instances', () => {
    const cueA = new ApproachCue();
    const cueB = new ApproachCue();
    const eta = makeEtaMock({ FPK: NOW + FOUR_MIN_MS });

    // Fire on A
    cueA.check(POSITION_BEFORE_FPK, eta, STATIONS);
    cueA.reset();

    // B is completely fresh — reset of A must not affect B's state
    // Fire on B then reset B
    const b1 = cueB.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(b1).not.toBeNull();
    cueB.reset();

    // Both fire again independently after their own reset
    const a2 = cueA.check(POSITION_BEFORE_FPK, eta, STATIONS);
    const b2 = cueB.check(POSITION_BEFORE_FPK, eta, STATIONS);
    expect(a2).not.toBeNull();
    expect(b2).not.toBeNull();
  });
});
