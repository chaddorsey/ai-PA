/**
 * e2e-smoke.test.ts — proxy bundle integration smoke test.
 *
 * Uses the REAL proxy bundle from tools/amtrak-position-engine/bundles/leg58/bundle.json
 * and real companion-core APIs (Scheduler, Eta, Favorites, PositionService, ApproachCue).
 * No network calls. Native plugins are mocked.
 */

import { describe, it, expect, beforeAll, vi } from 'vitest';
import { Scheduler, Eta, PositionService, Favorites, InMemoryAdapter } from 'companion-core';
import type { Polyline } from 'companion-core';
import { ApproachCue } from './ApproachCue';
import type { Bundle, Position, Station } from 'companion-core';

// ── Mock native plugins (not called in this test) ────────────────────────────

vi.mock('$lib/native/plugins', () => ({
  BackgroundLocation: {
    watch: vi.fn().mockResolvedValue('handle'),
    clear: vi.fn().mockResolvedValue(undefined),
  },
  AudioSession: {
    setMode: vi.fn().mockResolvedValue(undefined),
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn().mockResolvedValue(undefined),
    resume: vi.fn().mockResolvedValue(undefined),
    setRate: vi.fn().mockResolvedValue(undefined),
    addListener: vi.fn().mockReturnValue({ remove: vi.fn() }),
  },
  LiveActivity: {
    update: vi.fn().mockResolvedValue(undefined),
    end: vi.fn().mockResolvedValue(undefined),
  },
  BundleStore: {
    download: vi.fn().mockResolvedValue(undefined),
    getPath: vi.fn().mockResolvedValue('/bundles/58'),
    list: vi.fn().mockResolvedValue([]),
  },
}));

// ── Real proxy bundle (no network, direct JSON import) ───────────────────────

import bundleJson from '/Volumes/main-drive/ai-PA/tools/amtrak-position-engine/bundles/leg58/bundle.json' with { type: 'json' };

// ── Test suite ───────────────────────────────────────────────────────────────

describe('proxy bundle smoke test — leg58 (Sunset Limited / City of New Orleans)', () => {
  let bundle: Bundle;
  let scheduler: InstanceType<typeof Scheduler>;
  let eta: InstanceType<typeof Eta>;
  let positionService: InstanceType<typeof PositionService>;
  let favorites: InstanceType<typeof Favorites>;

  // The proxy bundle is a trip-actual leg with departure from NOL (New Orleans)
  const LEG58_ORIGIN_CODE = 'NOL';
  const LEG58_SECOND_STATION_CODE = 'HMD'; // Hammond, LA at mile 53

  beforeAll(() => {
    bundle = bundleJson as unknown as Bundle;

    // Departure time from origin station
    const origin = bundle.stations.find((s: Station) => s.sched_dep !== null);
    const depMs = origin?.sched_dep ? new Date(origin.sched_dep).getTime() : Date.now();

    scheduler = new Scheduler(bundle, {
      fillPct: 0.5,
      themes: new Set(),
      highlightOnly: false,
    });
    eta = new Eta(bundle, depMs);

    // Build a polyline from position_table rows: [elapsed_min, mile, lat, lon] → [mile, lat, lon]
    const poly: Polyline = bundle.position_table.map(
      ([_elapsed, mile, lat, lon]) => [mile, lat, lon] as [number, number, number],
    );
    positionService = new PositionService(bundle, poly, '58');
    favorites = new Favorites(new InMemoryAdapter());
  });

  // ── Bundle structure assertions ─────────────────────────────────────────────

  it('bundle loads with correct leg id', () => {
    expect(bundle.leg).toBe('58');
  });

  it('bundle has a non-empty units array', () => {
    expect(Array.isArray(bundle.units)).toBe(true);
    expect(bundle.units.length).toBeGreaterThan(0);
  });

  it('bundle has stations array with at least 2 entries', () => {
    expect(Array.isArray(bundle.stations)).toBe(true);
    expect(bundle.stations.length).toBeGreaterThanOrEqual(2);
  });

  it('bundle has a position_table with rows', () => {
    expect(Array.isArray(bundle.position_table)).toBe(true);
    expect(bundle.position_table.length).toBeGreaterThan(0);
  });

  it('bundle is trip-actual', () => {
    expect(bundle.schedule_basis.kind).toBe('trip-actual');
  });

  it('bundle stations all have required fields', () => {
    for (const s of bundle.stations) {
      expect(typeof s.code).toBe('string');
      expect(typeof s.name).toBe('string');
      expect(typeof s.mile).toBe('number');
      expect(typeof s.lat).toBe('number');
      expect(typeof s.lon).toBe('number');
    }
  });

  // ── Scheduler assertions ────────────────────────────────────────────────────

  it('scheduler returns a SchedulerResult with required fields', () => {
    const pos: Position = {
      mile: 5, lat: 29.95, lon: -90.1,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };
    const result = scheduler.select(pos);
    expect(typeof result.silenceUntilMile).toBe('number');
    expect(Array.isArray(result.queue)).toBe(true);
    // nowPlaying is either a Unit or null
    expect(result.nowPlaying === null || typeof result.nowPlaying === 'object').toBe(true);
  });

  it('scheduler has content available somewhere along the route', () => {
    // Step through several mileposts and check at least one returns content
    const miles = [0, 5, 10, 20, 50, 100];
    const results = miles.map((mile) =>
      scheduler.select({
        mile, lat: 30.0, lon: -90.0,
        source: 'gps', direction: 1, leg: '58', stopped: false,
      }),
    );
    const hasAnyContent = results.some(
      (r) => r.nowPlaying !== null || r.queue.length > 0,
    );
    expect(hasAnyContent).toBe(true);
  });

  it('scheduler silenceUntilMile is a number (sentinel or actual mile)', () => {
    const pos: Position = {
      mile: 0, lat: 29.94, lon: -90.08,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };
    const result = scheduler.select(pos);
    // silenceUntilMile is always a number: -Infinity (no silence) or a mile value
    expect(typeof result.silenceUntilMile).toBe('number');
    // It must be either -Infinity or a finite mile ≥ 0
    const isValid =
      result.silenceUntilMile === -Infinity || result.silenceUntilMile >= 0;
    expect(isValid).toBe(true);
  });

  // ── Eta assertions ──────────────────────────────────────────────────────────

  it('Eta.toStation returns p10 <= p50 <= p90 for the second station', () => {
    const pos: Position = {
      mile: 0, lat: 29.94, lon: -90.08,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };
    const result = eta.toStation(LEG58_SECOND_STATION_CODE, pos);
    expect(result.p10).toBeLessThanOrEqual(result.p50);
    expect(result.p50).toBeLessThanOrEqual(result.p90);
  });

  it('Eta.toStation p50 is in the future relative to departure', () => {
    const pos: Position = {
      mile: 0, lat: 29.94, lon: -90.08,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };
    const result = eta.toStation(LEG58_SECOND_STATION_CODE, pos);
    const origin = bundle.stations.find((s: Station) => s.sched_dep !== null);
    const depMs = origin?.sched_dep ? new Date(origin.sched_dep).getTime() : 0;
    // p50 should be after departure
    expect(result.p50).toBeGreaterThan(depMs);
  });

  it('Eta.toStation returns estimated:false for trip-actual bundle', () => {
    const pos: Position = {
      mile: 0, lat: 29.94, lon: -90.08,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };
    const result = eta.toStation(LEG58_SECOND_STATION_CODE, pos);
    expect(result.estimated).toBe(false);
  });

  it('Eta.toMile returns ordered p10 <= p50 <= p90 for a mid-route mile', () => {
    const pos: Position = {
      mile: 0, lat: 29.94, lon: -90.08,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };
    const result = eta.toMile(100, pos);
    expect(result.p10).toBeLessThanOrEqual(result.p50);
    expect(result.p50).toBeLessThanOrEqual(result.p90);
  });

  // ── Favorites round-trip ────────────────────────────────────────────────────

  it('favorites.add then list() round-trips a captured unit', async () => {
    const firstUnit = bundle.units[0];
    const pos: Position = {
      mile: 5, lat: 29.95, lon: -90.1,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };

    const fav = await favorites.add(firstUnit, '58', pos, 'star');

    expect(fav.id).toBeTruthy();
    expect(fav.kind).toBe('star');
    expect(fav.leg).toBe('58');
    expect(fav.unitSnapshot).toEqual(firstUnit);

    const list = await favorites.list();
    expect(list.length).toBeGreaterThanOrEqual(1);
    expect(list.some((f) => f.id === fav.id)).toBe(true);
  });

  it('favorites.add with tellmore and note stores the note', async () => {
    const unit = bundle.units[0];
    const pos: Position = {
      mile: 5, lat: 29.95, lon: -90.1,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };
    const fav = await favorites.add(unit, '58', pos, 'tellmore', 'Fascinating history!');
    expect(fav.kind).toBe('tellmore');
    expect(fav.note).toBe('Fascinating history!');
  });

  it('favorites.get retrieves a favorite by id', async () => {
    const unit = bundle.units[0];
    const pos: Position = {
      mile: 10, lat: 30.0, lon: -90.2,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };
    const added = await favorites.add(unit, '58', pos, 'star');
    const got = await favorites.get(added.id);
    expect(got.id).toBe(added.id);
    expect(got.kind).toBe('star');
  });

  // ── ApproachCue class ───────────────────────────────────────────────────────

  it('ApproachCue instances are independent (no state leakage)', () => {
    const cue1 = new ApproachCue();
    const cue2 = new ApproachCue();

    const secondStation = bundle.stations[1] as Station; // HMD at mile 53
    const posBeforeStation: Position = {
      mile: secondStation.mile - 2,
      lat: secondStation.lat,
      lon: secondStation.lon,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };

    // Use a mock eta that returns a near ETA so the approach fires
    const mockEta = {
      toStation: (_code: string, _pos: Position) => ({
        p10: Date.now() + 1 * 60 * 1000,
        p50: Date.now() + 2 * 60 * 1000,
        p90: Date.now() + 3 * 60 * 1000,
        estimated: false,
      }),
    };

    const r1 = cue1.check(posBeforeStation, mockEta, [secondStation]);
    const r2 = cue2.check(posBeforeStation, mockEta, [secondStation]);

    // Both should fire independently
    expect(r1).not.toBeNull();
    expect(r2).not.toBeNull();

    // Neither should fire again (already fired)
    expect(cue1.check(posBeforeStation, mockEta, [secondStation])).toBeNull();
    expect(cue2.check(posBeforeStation, mockEta, [secondStation])).toBeNull();
  });

  it('ApproachCue does not fire for stations the train has passed', () => {
    const cue = new ApproachCue();
    const firstStation = bundle.stations[0] as Station; // NOL at mile 0

    const posPastStation: Position = {
      mile: firstStation.mile + 10, // 10 miles past the station
      lat: firstStation.lat,
      lon: firstStation.lon,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };

    const result = cue.check(posPastStation, eta, [firstStation]);
    expect(result).toBeNull();
  });

  it('ApproachCue reset() allows the same station to fire again', () => {
    const cue = new ApproachCue();
    const secondStation = bundle.stations[1] as Station;
    const posBeforeStation: Position = {
      mile: secondStation.mile - 2,
      lat: secondStation.lat,
      lon: secondStation.lon,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };

    const mockEta = {
      toStation: (_code: string, _pos: Position) => ({
        p10: Date.now() + 1 * 60 * 1000,
        p50: Date.now() + 2 * 60 * 1000,
        p90: Date.now() + 3 * 60 * 1000,
        estimated: false,
      }),
    };

    const r1 = cue.check(posBeforeStation, mockEta, [secondStation]);
    expect(r1).not.toBeNull();

    // Would not fire again without reset
    expect(cue.check(posBeforeStation, mockEta, [secondStation])).toBeNull();

    // After reset, fires again
    cue.reset();
    const r2 = cue.check(posBeforeStation, mockEta, [secondStation]);
    expect(r2).not.toBeNull();
  });

  // ── PositionService dead-reckoning ─────────────────────────────────────────

  it('PositionService.tick advances dead-reckoning after onFix', () => {
    const poly: Polyline = bundle.position_table.map(
      ([_elapsed, mile, lat, lon]) => [mile, lat, lon] as [number, number, number],
    );
    const ps = new PositionService(bundle, poly, '58');
    const nowMs = Date.now();

    // Feed a GPS fix 5 seconds ago at 60 mph near New Orleans (leg start)
    ps.onFix(29.94, -90.08, nowMs - 5_000, 60);
    const pos = ps.tick(nowMs);

    expect(pos).not.toBeNull();
    expect(typeof pos!.mile).toBe('number');
    expect(pos!.mile).toBeGreaterThanOrEqual(0);
  });

  it('PositionService.current() returns a Position object (may use predicted baseline)', () => {
    const poly: Polyline = bundle.position_table.map(
      ([_elapsed, mile, lat, lon]) => [mile, lat, lon] as [number, number, number],
    );
    const ps = new PositionService(bundle, poly, '58');
    const pos = ps.current();
    // PositionService may return a predicted baseline position from position_table,
    // or null if no initial state is available. Either is valid.
    if (pos !== null) {
      expect(typeof pos.mile).toBe('number');
      expect(pos.mile).toBeGreaterThanOrEqual(0);
      expect(typeof pos.lat).toBe('number');
      expect(typeof pos.lon).toBe('number');
    }
    // The call should not throw
    expect(true).toBe(true);
  });

  // ── Audio mode selector wiring ─────────────────────────────────────────────
  // Verify that SettingsView's pure functions have the correct contract:
  // applyVoiceRateChange clamps and delegates; applyThemeChange mutates the Set.

  it('SettingsView.ts: clampVoiceRate handles boundary values correctly', async () => {
    const { clampVoiceRate } = await import('$lib/settings/SettingsView');
    expect(clampVoiceRate(0.0)).toBe(0.5);  // below min → 0.5
    expect(clampVoiceRate(3.0)).toBe(2.0);  // above max → 2.0
    expect(clampVoiceRate(1.0)).toBe(1.0);  // within range → unchanged
    expect(clampVoiceRate(0.5)).toBe(0.5);  // at min boundary
    expect(clampVoiceRate(2.0)).toBe(2.0);  // at max boundary
  });

  it('SettingsView.ts: applyVoiceRateChange calls setRate with clamped value', async () => {
    const { applyVoiceRateChange } = await import('$lib/settings/SettingsView');
    const mockAudio = { setRate: vi.fn() };
    const state = { settings: { voiceRate: 1.0, themes: new Set<string>() } };

    applyVoiceRateChange(1.5, mockAudio, state);
    expect(state.settings.voiceRate).toBe(1.5);
    expect(mockAudio.setRate).toHaveBeenCalledWith(1.5);
  });

  it('SettingsView.ts: applyThemeChange adds/removes themes', async () => {
    const { applyThemeChange } = await import('$lib/settings/SettingsView');
    const state = { settings: { voiceRate: 1.0, themes: new Set<string>(['history']) } };

    applyThemeChange('geology', true, state);
    expect(state.settings.themes.has('geology')).toBe(true);

    applyThemeChange('history', false, state);
    expect(state.settings.themes.has('history')).toBe(false);
  });
});
