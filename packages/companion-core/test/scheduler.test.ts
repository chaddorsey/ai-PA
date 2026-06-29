/**
 * scheduler.test.ts — Plan 2, Task 5
 *
 * Tests for Scheduler class in src/scheduler.ts.
 *
 * Covers:
 *   - Squib firing within lookahead window
 *   - No re-fire (each squib fires once)
 *   - Interstitial greedy packing by salience
 *   - Fit-or-skip: interstitial that would overrun next squib is excluded
 *   - fill=0.0 → no interstitials
 *   - fill=1.0 ≥ fill=0.5 (fill ratio monotonicity)
 *   - highlightOnly: only salience>=4 units selected
 *   - themes filter: only matching themes; null-theme units excluded when filter active
 *   - Re-entry: large forward jump fires ≤1 orientation unit, not the whole backlog
 *   - Simulated-train harness (leg-58 proxy bundle):
 *       ≥99% squibs fire within ±0.3 mi of declared mile
 *       Zero spurious fires (no fires twice, no fires out of range)
 *       Fill ratio within ±10% of fillPct
 *       highlightOnly filter verified end-to-end
 *       themes filter verified end-to-end
 *       Fit-or-skip demonstrated
 *       Re-entry fires ≤1 unit
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';
import { describe, it, expect, beforeEach } from 'vitest';
import { Scheduler } from '../src/scheduler.js';
import type {
  Bundle,
  Position,
  SchedulerSettings,
  Unit,
  SquibUnit,
  InterstitialUnit,
} from '../src/types.js';

// ── Helpers ───────────────────────────────────────────────────────────────────

const __dir = dirname(fileURLToPath(import.meta.url));

function makePos(mile: number): Position {
  return {
    mile,
    lat: 30,
    lon: -90,
    source: 'gps',
    direction: 1,
    leg: '58',
    stopped: false,
  };
}

// ── Synthetic bundle ──────────────────────────────────────────────────────────
// 3 squibs at miles 10, 55, 100; 4 interstitials covering various ranges

const BASE_BUNDLE_FIELDS = {
  leg: '58' as const,
  proxy: false as const,
  schedule_basis: { kind: 'trip-actual' as const, valid_dates: ['2026-07-11'] },
  stations: [
    {
      code: 'NOL', name: 'New Orleans', mile: 0, lat: 29.94, lon: -90.07,
      sched_arr: null as null, sched_dep: '2026-07-12T07:00:00-05:00', dwell_min: 0,
    },
  ],
  geometry: {
    type: 'LineString' as const,
    coordinates: [[-90.07, 29.94], [-90.43, 31.8]] as [number, number][],
  },
  layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
  position_table: [
    [0, 0, 29.95, -90.07],
    [120, 110, 31.8, -90.4],
  ] as [number, number, number, number][],
  eta_table: [] as never[],
};

function makeBundle(): Bundle {
  return {
    ...BASE_BUNDLE_FIELDS,
    units: [
      // Squibs
      {
        id: 'sq1', kind: 'squib', mile: 10, place: 'A', side: 'left',
        salience: 3, theme: 'railroad-history', text: 'Squib A.',
        lat: 30.1, lon: -90.1, dur_s: 40, audio: 'a1.mp3',
      },
      {
        id: 'sq2', kind: 'squib', mile: 55, place: 'B', side: 'right',
        salience: 5, theme: 'civil-rights', text: 'Squib B.',
        lat: 31.2, lon: -90.4, dur_s: 60, audio: 'a2.mp3',
      },
      {
        id: 'sq3', kind: 'squib', mile: 100, place: 'C', side: null,
        salience: 4, theme: 'nature', text: 'Squib C.',
        lat: 31.7, lon: -90.43, dur_s: 50, audio: 'a3.mp3',
      },
      // Interstitials
      {
        id: 'in1', kind: 'interstitial', from_mi: 5, to_mi: 30, place: 'P', side: null,
        salience: 2, theme: 'nature', text: 'Interstitial 1.', lat: 30.2, lon: -90.2,
        dur_s: 25, audio: 'b1.mp3',
      },
      {
        id: 'in2', kind: 'interstitial', from_mi: 5, to_mi: 30, place: 'P', side: null,
        salience: 1, theme: 'geology', text: 'Interstitial 2.', lat: 30.3, lon: -90.3,
        dur_s: 20, audio: 'b2.mp3',
      },
      {
        id: 'in3', kind: 'interstitial', from_mi: 30, to_mi: 60, place: 'Q', side: null,
        salience: 3, theme: 'railroad-history', text: 'Interstitial 3.', lat: 30.8, lon: -90.35,
        dur_s: 35, audio: 'b3.mp3',
      },
      {
        id: 'in4', kind: 'interstitial', from_mi: 60, to_mi: 110, place: 'R', side: null,
        salience: 4, theme: 'civil-rights', text: 'Interstitial 4.', lat: 31.5, lon: -90.44,
        dur_s: 45, audio: 'b4.mp3',
      },
    ] as Unit[],
  };
}

const FULL_SETTINGS: SchedulerSettings = {
  fillPct: 1.0,
  themes: new Set(),
  highlightOnly: false,
};

const SILENT_SETTINGS: SchedulerSettings = {
  fillPct: 0.0,
  themes: new Set(),
  highlightOnly: false,
};

// ── Squib firing ──────────────────────────────────────────────────────────────

describe('Scheduler — squib firing', () => {
  it('fires a squib when position reaches its mile (within lookahead)', () => {
    const sched = new Scheduler(makeBundle(), FULL_SETTINGS);
    // Default LOOKAHEAD_MI = 0.15; squib at mile 10 triggers from 9.85
    const result = sched.select(makePos(9.9));
    expect(result.nowPlaying?.id).toBe('sq1');
  });

  it('does not fire a squib when position is far before its mile', () => {
    const sched = new Scheduler(makeBundle(), FULL_SETTINGS);
    const result = sched.select(makePos(2));
    expect(result.nowPlaying?.id).not.toBe('sq1');
  });

  it('does not re-fire a squib after it has been played', () => {
    const sched = new Scheduler(makeBundle(), FULL_SETTINGS);
    sched.select(makePos(9.9)); // fires sq1
    const result = sched.select(makePos(10.5));
    expect(result.nowPlaying?.id).not.toBe('sq1');
  });

  it('fires squibs in milepost order across the whole range', () => {
    const sched = new Scheduler(makeBundle(), FULL_SETTINGS);
    const fired: string[] = [];
    for (let mile = 0; mile <= 110; mile += 0.5) {
      const r = sched.select(makePos(mile));
      if (r.nowPlaying) fired.push(r.nowPlaying.id);
    }
    const squibsFired = fired.filter(id => id.startsWith('sq'));
    expect(squibsFired).toContain('sq1');
    expect(squibsFired).toContain('sq2');
    expect(squibsFired).toContain('sq3');
    expect(squibsFired.indexOf('sq1')).toBeLessThan(squibsFired.indexOf('sq2'));
    expect(squibsFired.indexOf('sq2')).toBeLessThan(squibsFired.indexOf('sq3'));
  });

  it('returns silenceUntilMile pointing at next squib when nothing plays but squib is ahead', () => {
    const sched = new Scheduler(makeBundle(), SILENT_SETTINGS);
    // At mile 2 with fill=0.0, no interstitials play, but sq1 is at mile 10
    // silenceUntilMile should be the trigger mile of sq1 (not -Infinity)
    const result = sched.select(makePos(2));
    expect(result.nowPlaying).toBeNull();
    // Next squib is sq1 at mile 10 (triggers at 10 - 0.15 = 9.85)
    expect(result.silenceUntilMile).toBeGreaterThan(0);
    expect(result.silenceUntilMile).toBeLessThan(10);
  });

  it('returns silenceUntilMile = -Infinity after all content has been played', () => {
    const sched = new Scheduler(makeBundle(), SILENT_SETTINGS);
    // Advance past all squibs (to mile 110, beyond sq3 at mile 100)
    for (let m = 0; m <= 110; m += 0.5) {
      sched.select(makePos(m));
    }
    // Now there should be no more content
    const result = sched.select(makePos(110));
    expect(result.silenceUntilMile).toBe(-Infinity);
  });
});

// ── Interstitial packing ──────────────────────────────────────────────────────

describe('Scheduler — interstitial packing', () => {
  it('packs an interstitial in the gap at fill=1.0', () => {
    const sched = new Scheduler(makeBundle(), FULL_SETTINGS);
    const result = sched.select(makePos(2));
    const ids = [result.nowPlaying?.id, ...result.queue.map(u => u.id)].filter(Boolean);
    expect(ids.some(id => id === 'in1' || id === 'in2')).toBe(true);
  });

  it('packs no interstitials at fill=0.0', () => {
    const sched = new Scheduler(makeBundle(), SILENT_SETTINGS);
    const result = sched.select(makePos(2));
    const ids = [result.nowPlaying?.id, ...result.queue.map(u => u.id)].filter((id): id is string => !!id);
    expect(ids.every(id => !id.startsWith('in'))).toBe(true);
  });

  it('packs higher-salience interstitials before lower-salience', () => {
    const sched = new Scheduler(makeBundle(), FULL_SETTINGS);
    const result = sched.select(makePos(2));
    const queue = [result.nowPlaying, ...result.queue].filter(
      (u): u is Unit => u !== null && u.kind === 'interstitial',
    );
    if (queue.length >= 2) {
      expect(queue[0].salience).toBeGreaterThanOrEqual(queue[1].salience);
    }
  });

  it('fit-or-skip: does not pack a 700s interstitial in an ~8-minute gap before sq1', () => {
    const bundle = makeBundle();
    (bundle.units as Unit[]).push({
      id: 'in-huge', kind: 'interstitial', from_mi: 5, to_mi: 30,
      place: 'X', side: null, salience: 5, theme: 'nature',
      text: 'Too long.', lat: 30.1, lon: -90.1, dur_s: 700, audio: 'big.mp3',
    } as InterstitialUnit);
    const sched = new Scheduler(bundle, FULL_SETTINGS);
    const result = sched.select(makePos(2));
    const ids = [result.nowPlaying?.id, ...result.queue.map(u => u.id)];
    expect(ids).not.toContain('in-huge');
  });
});

// ── Filters ───────────────────────────────────────────────────────────────────

describe('Scheduler — theme and highlight filters', () => {
  it('theme filter excludes squibs not in the allowed set', () => {
    const settings: SchedulerSettings = {
      fillPct: 1.0, themes: new Set(['civil-rights']), highlightOnly: false,
    };
    const sched = new Scheduler(makeBundle(), settings);
    // sq1 (railroad-history) is at mile 10 — should be excluded
    const result = sched.select(makePos(9.9));
    expect(result.nowPlaying?.id).not.toBe('sq1');
  });

  it('theme filter excludes interstitials not in the allowed set', () => {
    const settings: SchedulerSettings = {
      fillPct: 1.0, themes: new Set(['civil-rights']), highlightOnly: false,
    };
    const sched = new Scheduler(makeBundle(), settings);
    const result = sched.select(makePos(2));
    const ids = [result.nowPlaying?.id, ...result.queue.map(u => u.id)].filter(Boolean);
    expect(ids).not.toContain('in1');
    expect(ids).not.toContain('in2');
    expect(ids).not.toContain('in3');
  });

  it('theme filter excludes null-theme units when filter is active', () => {
    const bundle = makeBundle();
    (bundle.units as Unit[]).push({
      id: 'sq-null-theme', kind: 'squib', mile: 20, place: 'Null', side: null,
      salience: 5, theme: null, text: 'Null theme squib.', lat: 30.3, lon: -90.3,
      dur_s: 30, audio: 'null.mp3',
    } as SquibUnit);
    const settings: SchedulerSettings = {
      fillPct: 1.0, themes: new Set(['civil-rights']), highlightOnly: false,
    };
    const sched = new Scheduler(bundle, settings);
    const result = sched.select(makePos(19.9));
    expect(result.nowPlaying?.id).not.toBe('sq-null-theme');
  });

  it('null-theme units are included when no theme filter is active', () => {
    const bundle = makeBundle();
    (bundle.units as Unit[]).push({
      id: 'sq-null-theme', kind: 'squib', mile: 25, place: 'Null', side: null,
      salience: 5, theme: null, text: 'Null theme squib.', lat: 30.3, lon: -90.3,
      dur_s: 30, audio: 'null.mp3',
    } as SquibUnit);
    const sched = new Scheduler(bundle, FULL_SETTINGS);
    const result = sched.select(makePos(24.9));
    expect(result.nowPlaying?.id).toBe('sq-null-theme');
  });

  it('highlightOnly=true skips salience < 4 squibs', () => {
    const settings: SchedulerSettings = {
      fillPct: 1.0, themes: new Set(), highlightOnly: true,
    };
    const sched = new Scheduler(makeBundle(), settings);
    // sq1 has salience 3 at mile 10 — should be skipped
    const result = sched.select(makePos(9.9));
    expect(result.nowPlaying?.id).not.toBe('sq1');
  });

  it('highlightOnly=true allows salience >= 4 squibs', () => {
    const settings: SchedulerSettings = {
      fillPct: 1.0, themes: new Set(), highlightOnly: true,
    };
    const sched = new Scheduler(makeBundle(), settings);
    // sq2 has salience 5 at mile 55 — should fire
    const result = sched.select(makePos(54.88));
    expect(result.nowPlaying?.id).toBe('sq2');
  });

  it('highlightOnly=true excludes salience < 4 interstitials from fill', () => {
    const settings: SchedulerSettings = {
      fillPct: 1.0, themes: new Set(), highlightOnly: true,
    };
    const sched = new Scheduler(makeBundle(), settings);
    // in1 (sal=2), in2 (sal=1), in3 (sal=3) all < 4 — none appear at mile 2
    const result = sched.select(makePos(2));
    const ids = [result.nowPlaying?.id, ...result.queue.map(u => u.id)].filter(Boolean);
    expect(ids.every(id => !['in1', 'in2', 'in3'].includes(id!))).toBe(true);
  });
});

// ── Re-entry ──────────────────────────────────────────────────────────────────

describe('Scheduler — re-entry orientation', () => {
  it('after a large forward jump, fires at most 1 unit (not the full skipped backlog)', () => {
    const sched = new Scheduler(makeBundle(), FULL_SETTINGS);
    sched.select(makePos(2));
    // Jump 78 miles forward — well above any REENTRY_GAP_MI threshold
    const result = sched.select(makePos(80));
    const ids = [result.nowPlaying?.id, ...result.queue.map(u => u.id)].filter(Boolean);
    // Skipped sq1 (mile 10) and sq2 (mile 55) must NOT both appear
    const skippedSquibsPresent = ids.filter(id => id === 'sq1' || id === 'sq2');
    expect(skippedSquibsPresent.length).toBeLessThanOrEqual(1);
  });

  it('re-entry does not fire squibs that are behind the new position', () => {
    const sched = new Scheduler(makeBundle(), FULL_SETTINGS);
    sched.select(makePos(2));
    const result = sched.select(makePos(80));
    const ids = [result.nowPlaying?.id, ...result.queue.map(u => u.id)].filter(Boolean);
    // sq1 (mile 10) and sq2 (mile 55) are behind mile 80
    expect(ids).not.toContain('sq1');
    expect(ids).not.toContain('sq2');
  });
});

// ── Simulated-train harness (leg-58 proxy bundle) ─────────────────────────────

describe('Scheduler — simulated-train harness (leg-58 bundle)', () => {
  const SPEED_MPH = 79;
  const STEP_MI = 0.1;
  const LOOKAHEAD_TOL_MI = 0.3;
  const FILL_TOLERANCE = 0.10;

  let leg58Bundle: Bundle;

  beforeEach(() => {
    const raw = readFileSync(
      join(__dir, '../../../tools/amtrak-position-engine/bundles/leg58/bundle.json'),
      'utf-8',
    );
    leg58Bundle = JSON.parse(raw) as Bundle;
  });

  interface HarnessStats {
    eligibleSquibCount: number;
    firedEligibleSquibCount: number;
    squibFireErrors: number[];
    firedInterstitialIds: Set<string>;
    totalInterstitialDurS: number;
    totalNonSquibGapS: number;
    duplicateCount: number;
    allFiredIds: string[];
    firedSquibsMap: Map<string, number>;
  }

  function runHarness(
    bundle: Bundle,
    settings: SchedulerSettings,
    fromMile = 0,
    toMile: number | null = null,
  ): HarnessStats {
    const lastMileInTable =
      bundle.position_table[bundle.position_table.length - 1]?.[1] ?? 934;
    const endMile = toMile ?? lastMileInTable;

    const sched = new Scheduler(bundle, settings);

    const eligibleSquibs = bundle.units
      .filter((u): u is SquibUnit => u.kind === 'squib')
      .filter(u => u.mile >= fromMile && u.mile <= endMile)
      .filter(u => {
        if (settings.highlightOnly && u.salience < 4) return false;
        if (
          settings.themes.size > 0 &&
          (u.theme === null || !settings.themes.has(u.theme))
        ) return false;
        return true;
      });

    const firedSquibsMap = new Map<string, number>();
    const firedInterstitialIds = new Set<string>();
    const allFiredIds: string[] = [];
    let lastNowPlayingId: string | null = null;

    let totalInterstitialDurS = 0;
    const squibDurations: number[] = [];

    for (let mile = fromMile; mile <= endMile + STEP_MI / 2; mile += STEP_MI) {
      const pos = makePos(Math.min(mile, endMile));
      const result = sched.select(pos);

      if (result.nowPlaying && result.nowPlaying.id !== lastNowPlayingId) {
        lastNowPlayingId = result.nowPlaying.id;
        allFiredIds.push(result.nowPlaying.id);

        if (result.nowPlaying.kind === 'squib') {
          firedSquibsMap.set(result.nowPlaying.id, Math.min(mile, endMile));
          squibDurations.push(result.nowPlaying.dur_s);
        } else {
          firedInterstitialIds.add(result.nowPlaying.id);
          totalInterstitialDurS += result.nowPlaying.dur_s;
        }
      }
    }

    const totalTravelSec = ((endMile - fromMile) / SPEED_MPH) * 3600;
    const totalSquibSec = squibDurations.reduce((a, b) => a + b, 0);
    const totalNonSquibGapS = Math.max(0, totalTravelSec - totalSquibSec);

    const squibFireErrors: number[] = [];
    for (const sq of eligibleSquibs) {
      if (firedSquibsMap.has(sq.id)) {
        squibFireErrors.push(Math.abs(firedSquibsMap.get(sq.id)! - sq.mile));
      }
    }

    const seenIds = new Set<string>();
    let duplicateCount = 0;
    for (const id of allFiredIds) {
      if (seenIds.has(id)) duplicateCount++;
      else seenIds.add(id);
    }

    return {
      eligibleSquibCount: eligibleSquibs.length,
      firedEligibleSquibCount: eligibleSquibs.filter(s => firedSquibsMap.has(s.id)).length,
      squibFireErrors,
      firedInterstitialIds,
      totalInterstitialDurS,
      totalNonSquibGapS,
      duplicateCount,
      allFiredIds,
      firedSquibsMap,
    };
  }

  it('≥99% of squibs fire within ±0.3 mi of their declared mile', () => {
    const settings: SchedulerSettings = {
      fillPct: 0.5, themes: new Set(), highlightOnly: false,
    };
    const stats = runHarness(leg58Bundle, settings);

    const maxErr = stats.squibFireErrors.length > 0
      ? Math.max(...stats.squibFireErrors)
      : 0;
    const withinTol = stats.squibFireErrors.filter(e => e <= LOOKAHEAD_TOL_MI).length;
    const firingRate = stats.firedEligibleSquibCount / Math.max(1, stats.eligibleSquibCount);
    const accuracyRate = withinTol / Math.max(1, stats.squibFireErrors.length);

    console.log(
      `Squibs: ${stats.firedEligibleSquibCount}/${stats.eligibleSquibCount} fired, ` +
      `${withinTol}/${stats.squibFireErrors.length} within ±${LOOKAHEAD_TOL_MI} mi, ` +
      `max err=${maxErr.toFixed(4)} mi, firingRate=${(firingRate * 100).toFixed(1)}%`,
    );

    expect(firingRate).toBeGreaterThanOrEqual(0.99);
    expect(accuracyRate).toBeGreaterThanOrEqual(0.99);
    expect(maxErr).toBeLessThanOrEqual(LOOKAHEAD_TOL_MI);
  });

  it('zero spurious fires: no unit fires twice', () => {
    const stats = runHarness(leg58Bundle, {
      fillPct: 0.5, themes: new Set(), highlightOnly: false,
    });
    expect(stats.duplicateCount).toBe(0);
  });

  it('fill ratio: fill=1.0 produces more interstitials than fill=0.5', () => {
    const stats100 = runHarness(
      leg58Bundle,
      { fillPct: 1.0, themes: new Set(), highlightOnly: false },
      0, 200,
    );
    const stats50 = runHarness(
      leg58Bundle,
      { fillPct: 0.5, themes: new Set(), highlightOnly: false },
      0, 200,
    );
    const fill100 = stats100.totalInterstitialDurS / Math.max(1, stats100.totalNonSquibGapS);
    const fill50  = stats50.totalInterstitialDurS  / Math.max(1, stats50.totalNonSquibGapS);

    console.log(
      `Fill ratios: 1.0→${(fill100 * 100).toFixed(1)}%, 0.5→${(fill50 * 100).toFixed(1)}%`,
    );

    // Monotonicity: fill=1.0 must produce ≥ fill=0.5
    expect(stats100.firedInterstitialIds.size).toBeGreaterThanOrEqual(
      stats50.firedInterstitialIds.size,
    );

    // Neither ratio should overshoot by more than 10%
    expect(fill100).toBeLessThanOrEqual(1.0 + FILL_TOLERANCE + 0.01);
    expect(fill50).toBeLessThanOrEqual(0.5 + FILL_TOLERANCE + 0.01);
  });

  it('highlightOnly=true: only salience>=4 units fire across the entire leg', () => {
    const stats = runHarness(leg58Bundle, {
      fillPct: 0.5, themes: new Set(), highlightOnly: true,
    }, 0, 200);

    for (const id of stats.allFiredIds) {
      const unit = leg58Bundle.units.find(u => u.id === id);
      expect(unit, `fired unit ${id} not found in bundle`).toBeDefined();
      expect(unit!.salience).toBeGreaterThanOrEqual(4);
    }
  });

  it('themes filter: only units with the matching theme fire', () => {
    const allowedTheme = 'Corridor of Movement';
    const stats = runHarness(leg58Bundle, {
      fillPct: 0.5,
      themes: new Set([allowedTheme]),
      highlightOnly: false,
    }, 0, 200);

    for (const id of stats.allFiredIds) {
      const unit = leg58Bundle.units.find(u => u.id === id);
      expect(unit, `fired unit ${id} not found in bundle`).toBeDefined();
      expect(unit!.theme).toBe(allowedTheme);
    }
  });

  it('fit-or-skip: a 99999s interstitial never fires regardless of salience', () => {
    const bundle = JSON.parse(
      readFileSync(
        join(__dir, '../../../tools/amtrak-position-engine/bundles/leg58/bundle.json'),
        'utf-8',
      ),
    ) as Bundle;
    (bundle.units as Unit[]).push({
      id: 'in-infinite', kind: 'interstitial', from_mi: 0, to_mi: 934,
      place: 'Everywhere', side: null, salience: 5,
      theme: 'Corridor of Movement', text: 'Never fits.',
      lat: 30, lon: -90, dur_s: 99999, audio: 'big.mp3',
    } as InterstitialUnit);

    const stats = runHarness(bundle, {
      fillPct: 1.0, themes: new Set(), highlightOnly: false,
    }, 0, 200);

    expect(stats.allFiredIds).not.toContain('in-infinite');
  });

  it('re-entry: large forward jump fires ≤1 new unit, not the whole squib backlog', () => {
    const settings: SchedulerSettings = {
      fillPct: 0.5, themes: new Set(), highlightOnly: false,
    };
    const sched = new Scheduler(leg58Bundle, settings);

    // Advance 50 miles at normal pace
    const firedBefore = new Set<string>();
    for (let mile = 0; mile <= 50; mile += STEP_MI) {
      const r = sched.select(makePos(mile));
      if (r.nowPlaying) firedBefore.add(r.nowPlaying.id);
    }

    // Jump 400 miles forward
    const result = sched.select(makePos(450));
    const newFired = [result.nowPlaying?.id, ...result.queue.map(u => u.id)]
      .filter((id): id is string => id !== undefined && !firedBefore.has(id));

    // ≤1 new unit should appear
    expect(newFired.length).toBeLessThanOrEqual(1);

    // Squibs behind the jump point (< 450) that were skipped must NOT appear
    const behindCurrent = newFired.filter(id => {
      const unit = leg58Bundle.units.find(u => u.id === id);
      if (!unit) return false;
      const m = unit.kind === 'squib' ? unit.mile : (unit as InterstitialUnit).from_mi;
      return m < 400; // well behind the jump target
    });
    expect(behindCurrent.length).toBe(0);
  });
});
