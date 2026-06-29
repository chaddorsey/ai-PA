/**
 * StationCard tests — dwell hint, step-off hint, predicted vs estimated labeling.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import StationCard from '$lib/pillar2/StationCard.svelte';
import type { Bundle, Position } from 'companion-core';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const TODAY = new Date().toISOString().slice(0, 10);

const BASE_BUNDLE: Bundle = {
  leg: '58',
  schedule_basis: { kind: 'trip-actual', valid_dates: [TODAY] },
  stations: [
    {
      code: 'NOL', name: 'New Orleans, LA', mile: 0,
      lat: 29.94609, lon: -90.07829,
      sched_arr: null, sched_dep: `${TODAY}T15:45:00-05:00`, dwell_min: 0,
    },
    {
      code: 'MCB', name: 'McComb', mile: 98,
      lat: 31.24, lon: -90.45,
      sched_arr: `${TODAY}T18:07:00-06:00`, sched_dep: `${TODAY}T18:15:00-06:00`,
      dwell_min: 8,
    },
    {
      code: 'HAT', name: 'Hattiesburg', mile: 148,
      lat: 31.32, lon: -89.29,
      sched_arr: `${TODAY}T19:07:00-06:00`, sched_dep: `${TODAY}T19:09:00-06:00`,
      dwell_min: 2,
    },
  ],
  geometry: { type: 'LineString', coordinates: [[-90.07829, 29.94609]] },
  units: [],
  layers: {
    guide: {
      MCB: { amenities: ['Food', 'Wifi'] },
    },
    lore: {
      MCB: { summary: 'McComb was a railroad hub since the 1870s.' },
    },
    science: {},
    connections: {},
    themes: {},
  },
  position_table: [[0, 0, 29.94609, -90.07829], [120, 98, 31.24, -90.45]],
  eta_table: [
    { station_code: 'MCB', p10_min: 138, p50_min: 143, p90_min: 152 },
    { station_code: 'HAT', p10_min: 195, p50_min: 200, p90_min: 210 },
  ],
};

const GENERIC_BUNDLE: Bundle = {
  ...BASE_BUNDLE,
  schedule_basis: { kind: 'generic-scheduled', valid_dates: [] },
  eta_table: [],
};

const POSITION: Position = {
  mile: 50, lat: 30.5, lon: -90.3,
  source: 'gps', direction: 1, leg: '58', stopped: false,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('StationCard — dwell hint', () => {
  it('shows dwell time when dwell_min > 0', async () => {
    render(StationCard, { props: { bundle: BASE_BUNDLE, stationCode: 'MCB', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('8 min');
  });

  it('does not show dwell row when dwell_min is 0', async () => {
    render(StationCard, { props: { bundle: BASE_BUNDLE, stationCode: 'NOL', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).not.toContain('min here');
  });
});

describe('StationCard — step-off hint', () => {
  it('shows "Step off ✓" when dwell_min >= 5', async () => {
    // MCB has dwell_min=8 → step off allowed
    render(StationCard, { props: { bundle: BASE_BUNDLE, stationCode: 'MCB', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('Step off');
    expect(dialog.textContent).toContain('✓');
  });

  it('shows "Stay on" when dwell_min < 5', async () => {
    // HAT has dwell_min=2 → not enough time
    render(StationCard, { props: { bundle: BASE_BUNDLE, stationCode: 'HAT', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('Stay on');
  });
});

describe('StationCard — predicted vs estimated labeling', () => {
  it('shows "Predicted arrival" label for trip-actual bundle', async () => {
    render(StationCard, { props: { bundle: BASE_BUNDLE, stationCode: 'MCB', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('Predicted arrival');
  });

  it('shows p10–p90 range for trip-actual', async () => {
    render(StationCard, { props: { bundle: BASE_BUNDLE, stationCode: 'MCB', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    // p10–p90 range is shown with parentheses like "(HH:MM–HH:MM)"
    expect(dialog.textContent).toMatch(/\([\d:]+\s*[AP]M–[\d:]+\s*[AP]M\)|(\d{1,2}:\d{2}.+–.+\d{1,2}:\d{2})/);
  });

  it('shows "Estimated arrival" label for generic-scheduled bundle', async () => {
    render(StationCard, { props: { bundle: GENERIC_BUNDLE, stationCode: 'MCB', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('Estimated arrival');
  });

  it('shows "est." suffix for generic ETA', async () => {
    render(StationCard, { props: { bundle: GENERIC_BUNDLE, stationCode: 'MCB', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('est.');
  });

  it('does NOT show p10–p90 range for generic bundle', async () => {
    render(StationCard, { props: { bundle: GENERIC_BUNDLE, stationCode: 'MCB', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    // No parenthesised range
    expect(dialog.textContent).not.toMatch(/\(\d{1,2}:\d{2}.*–.*\d{1,2}:\d{2}\)/);
  });
});

describe('StationCard — amenities and lore', () => {
  it('renders amenities from layers.guide when present', async () => {
    render(StationCard, { props: { bundle: BASE_BUNDLE, stationCode: 'MCB', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('Food');
    expect(dialog.textContent).toContain('Wifi');
  });

  it('renders lore summary from layers.lore when present', async () => {
    render(StationCard, { props: { bundle: BASE_BUNDLE, stationCode: 'MCB', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('railroad hub');
  });

  it('gracefully renders when no lore/amenities', async () => {
    // HAT has no guide/lore entry
    render(StationCard, { props: { bundle: BASE_BUNDLE, stationCode: 'HAT', position: POSITION } });
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('Hattiesburg');
  });
});

describe('StationCard — null place and theme handling', () => {
  it('renders nothing when stationCode is not in bundle.stations', async () => {
    const { container } = render(StationCard, {
      props: { bundle: BASE_BUNDLE, stationCode: 'UNKNOWN', position: POSITION },
    });
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
