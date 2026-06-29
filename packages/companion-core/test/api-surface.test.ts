/**
 * api-surface.test.ts
 *
 * Verifies that every named export in the public API surface is present and
 * has the right kind (function/class/etc.).  This is a compile-time + runtime
 * guard against accidental omissions in index.ts.
 *
 * Type exports are verified implicitly by the TypeScript compiler; this file
 * focuses on runtime-callable values.
 */

import { describe, it, expect } from 'vitest';

// Import the full public API from the package entry point.
import {
  // Value exports (functions + classes)
  loadBundle,
  validateBundle,
  milepostToLatLon,
  projectToLeg,
  PositionService,
  Scheduler,
  Eta,
  diveGrounding,
  Favorites,
  InMemoryAdapter,
} from '../src/index.js';

// Type-only imports — if these compile, the types are exported correctly.
import type {
  Unit,
  SquibUnit,
  InterstitialUnit,
  UnitSide,
  Salience,
  Bundle,
  BundleLayers,
  ScheduleBasis,
  Station,
  LineStringGeometry,
  PositionTableRow,
  EtaTableRow,
  Polyline,
  PolyVertex,
  LatLon,
  ProjectionResult,
  Position,
  SchedulerSettings,
  SchedulerResult,
  EtaResult,
  Favorite,
  DiveCard,
  StorageAdapter,
  DiveGrounding,
} from '../src/index.js';

describe('API surface — value exports are defined', () => {
  it('loadBundle is a function', () => {
    expect(typeof loadBundle).toBe('function');
  });

  it('validateBundle is a function', () => {
    expect(typeof validateBundle).toBe('function');
  });

  it('milepostToLatLon is a function', () => {
    expect(typeof milepostToLatLon).toBe('function');
  });

  it('projectToLeg is a function', () => {
    expect(typeof projectToLeg).toBe('function');
  });

  it('PositionService is a constructor', () => {
    expect(typeof PositionService).toBe('function');
    expect(PositionService.prototype).toBeDefined();
  });

  it('Scheduler is a constructor', () => {
    expect(typeof Scheduler).toBe('function');
    expect(Scheduler.prototype).toBeDefined();
  });

  it('Eta is a constructor', () => {
    expect(typeof Eta).toBe('function');
    expect(Eta.prototype).toBeDefined();
  });

  it('diveGrounding is a function (Phase 2 stub)', () => {
    expect(typeof diveGrounding).toBe('function');
  });

  it('Favorites is a constructor', () => {
    expect(typeof Favorites).toBe('function');
    expect(Favorites.prototype).toBeDefined();
  });

  it('InMemoryAdapter is a constructor', () => {
    expect(typeof InMemoryAdapter).toBe('function');
    expect(InMemoryAdapter.prototype).toBeDefined();
  });
});

describe('API surface — type exports compile cleanly', () => {
  it('type exports are usable at compile time (compile-time assertion)', () => {
    // If any type import above fails to resolve, tsc will catch it.
    // At runtime we just assert this test file was reached.
    const _typeCheck: {
      unit: Unit | null;
      squib: SquibUnit | null;
      interstitial: InterstitialUnit | null;
      side: UnitSide;
      salience: Salience;
      bundle: Bundle | null;
      layers: BundleLayers | null;
      basis: ScheduleBasis | null;
      station: Station | null;
      geometry: LineStringGeometry | null;
      ptRow: PositionTableRow | null;
      etaRow: EtaTableRow | null;
      poly: Polyline | null;
      vertex: PolyVertex | null;
      latLon: LatLon | null;
      proj: ProjectionResult | null;
      pos: Position | null;
      settings: SchedulerSettings | null;
      result: SchedulerResult | null;
      etaResult: EtaResult | null;
      fav: Favorite | null;
      dive: DiveCard | null;
      adapter: StorageAdapter | null;
      grounding: DiveGrounding | null;
    } = {
      unit: null, squib: null, interstitial: null, side: null, salience: 1,
      bundle: null, layers: null, basis: null, station: null, geometry: null,
      ptRow: null, etaRow: null, poly: null, vertex: null, latLon: null,
      proj: null, pos: null, settings: null, result: null, etaResult: null,
      fav: null, dive: null, adapter: null, grounding: null,
    };
    // Silence unused variable warning
    expect(_typeCheck.salience).toBe(1);
  });
});

describe('API surface — Favorites + InMemoryAdapter smoke test', () => {
  it('creates a favorite end-to-end using the public API', async () => {
    const adapter = new InMemoryAdapter();
    const favs = new Favorites(adapter, {
      now: () => 999_999,
      genId: () => 'smoke-id-1',
    });

    const unit: SquibUnit = {
      id: 'sq1', kind: 'squib', mile: 55,
      place: 'McComb, MS', side: 'left', salience: 4,
      theme: 'civil-rights',
      text: 'McComb was a civil rights focal point.',
      lat: 31.24, lon: -90.45,
      dur_s: 55, audio: 'audio/sq1.mp3',
    };

    const pos: Position = {
      mile: 55, lat: 31.24, lon: -90.45,
      source: 'gps', direction: 1, leg: '58', stopped: false,
    };

    const fav = await favs.add(unit, '58', pos, 'star', 'Great spot');
    expect(fav.id).toBe('smoke-id-1');
    expect(fav.createdAt).toBe(999_999);
    expect(fav.kind).toBe('star');
    expect(fav.note).toBe('Great spot');

    const list = await favs.list();
    expect(list).toHaveLength(1);

    const retrieved = await favs.get(fav.id);
    expect(retrieved.unitSnapshot).toEqual(unit);

    const diveCard: DiveCard = {
      body: 'Civil rights history context.',
      sources: ['lore/civil-rights.md'],
      createdAt: 1_000_000,
    };
    await favs.attachDive(fav.id, diveCard);
    const withDive = await favs.get(fav.id);
    expect(withDive.dive!.body).toContain('Civil rights');
  });
});
