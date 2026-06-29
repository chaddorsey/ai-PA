import { describe, it, expect } from 'vitest';
import { diveGrounding } from '../src/dive.js';
import type { DiveGrounding } from '../src/dive.js';

describe('diveGrounding — Phase 2 stub', () => {
  it('DiveGrounding type has the expected shape (compile-time check)', () => {
    // If this compiles, the type is correctly exported.
    const sample: DiveGrounding = {
      unitText: 'Raton Pass.',
      connections: null,
      lore: {},
      science: [],
      theme: 'railroad-history',
      sources: ['guide/raton.md'],
    };
    expect(sample.unitText).toBe('Raton Pass.');
    expect(sample.sources).toHaveLength(1);
  });

  it('diveGrounding stub throws Phase 2 error', () => {
    const bundle: Parameters<typeof diveGrounding>[0] = {
      leg: '58',
      schedule_basis: { kind: 'generic-scheduled', valid_dates: [] },
      stations: [],
      geometry: { type: 'LineString', coordinates: [] },
      units: [],
      layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
      position_table: [],
      eta_table: [],
    };
    expect(() => diveGrounding(bundle, 'u1')).toThrow('Phase 2');
  });

  it('diveGrounding stub throws even with optional focus arg', () => {
    const bundle: Parameters<typeof diveGrounding>[0] = {
      leg: '3',
      schedule_basis: { kind: 'trip-actual', valid_dates: ['2026-07-12'] },
      stations: [],
      geometry: { type: 'LineString', coordinates: [] },
      units: [],
      layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
      position_table: [],
      eta_table: [],
    };
    expect(() => diveGrounding(bundle, 'u2', 'geology')).toThrow('Phase 2');
  });
});
