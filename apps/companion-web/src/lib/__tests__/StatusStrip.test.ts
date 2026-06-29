/**
 * StatusStrip tests — focus on ETA-honesty and suncalc rendering.
 *
 * ETA-honesty rule (non-negotiable per Plan 0 + prompt):
 * - schedule_basis.kind === 'trip-actual' AND today in valid_dates → real on-time/late claim
 * - schedule_basis.kind === 'generic-scheduled' → "Estimated · scheduled", NO confident claim
 * - trip-actual but today NOT in valid_dates → falls back to "Estimated · scheduled"
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import StatusStrip from '$lib/pillar1/StatusStrip.svelte';
import { appState } from '$lib/core/AppState.svelte';
import type { Bundle, Position } from 'companion-core';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const TODAY = new Date().toISOString().slice(0, 10);

// sched_dep = 15:45 UTC-5. MCB sched_arr = 18:07 UTC-6 = 00:07+1 UTC = 143 min elapsed.
// To get "On time": p50_min = 143 (15:45 + 143 min = 18:08 ≈ sched_arr 18:07, within 1 min)
// Let's keep exact: dep 15:45 UTC-5, arr 18:07 UTC-6 = dep 20:45 UTC, arr 00:07 UTC+1 day
// elapsed min: 00:07 next - 20:45 = 3h22m = 202 min. Let's compute properly:
// dep "15:45:00-05:00" = 20:45 UTC; arr "18:07:00-06:00" = midnight+07 UTC = 00:07 next day = NOT THAT
// dep 15:45 local UTC-5 = 20:45 UTC
// arr 18:07 local UTC-6 = 00:07 UTC  (next day? No — same day: 18:07 + 6h = 00:07 next day)
// Actually -6 means offset -6 from UTC: local time 18:07, UTC = 18:07 + 6:00 = 24:07 = 00:07 next day
// elapsed from dep to arr = 00:07 next day UTC - 20:45 today UTC = 3h22m = 202 min
// So p50_min = 202 → arrival exactly at sched_arr → "On time"
// Let's use a simpler approach: dep and arr in the same timezone UTC-5, 2h30m apart
const TRIP_ACTUAL_BUNDLE: Bundle = {
  leg: '58',
  schedule_basis: { kind: 'trip-actual', valid_dates: [TODAY] },
  stations: [
    {
      code: 'NOL', name: 'New Orleans, LA', mile: 0,
      lat: 29.94609, lon: -90.07829,
      sched_arr: null, sched_dep: `${TODAY}T12:00:00-05:00`, dwell_min: 0,
    },
    {
      code: 'MCB', name: 'McComb, MS', mile: 98,
      lat: 31.24, lon: -90.45,
      sched_arr: `${TODAY}T14:30:00-05:00`, sched_dep: `${TODAY}T14:33:00-05:00`, dwell_min: 3,
    },
  ],
  geometry: { type: 'LineString', coordinates: [[-90.07829, 29.94609], [-90.45, 31.24]] },
  units: [],
  layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
  position_table: [[0, 0, 29.94609, -90.07829], [150, 98, 31.24, -90.45]],
  // p50_min=150 → 12:00 + 150min = 14:30 = sched_arr → "On time"
  eta_table: [
    { station_code: 'MCB', p10_min: 148, p50_min: 150, p90_min: 153 },
  ],
};

// Generic-scheduled bundle — must show neutral status, never "On time" or "N min late"
const GENERIC_BUNDLE: Bundle = {
  ...TRIP_ACTUAL_BUNDLE,
  schedule_basis: { kind: 'generic-scheduled', valid_dates: [] },
  eta_table: [],
};

// Trip-actual but today is NOT in valid_dates → should fall back to neutral
const TRIP_ACTUAL_WRONG_DATE_BUNDLE: Bundle = {
  ...TRIP_ACTUAL_BUNDLE,
  schedule_basis: { kind: 'trip-actual', valid_dates: ['2099-01-01'] },
};

// Trip-actual bundle where train is LATE (p50 arrives 30 min after sched_arr)
const TRIP_ACTUAL_LATE_BUNDLE: Bundle = {
  ...TRIP_ACTUAL_BUNDLE,
  eta_table: [
    { station_code: 'MCB', p10_min: 175, p50_min: 180, p90_min: 190 },
    // p50_min=180 → 12:00 + 180min = 15:00, sched_arr=14:30 → 30 min late
  ],
};

const POSITION_AT_MILE_10: Position = {
  mile: 10, lat: 30.1, lon: -90.2,
  source: 'gps', direction: 1, leg: '58', stopped: false,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function setAppState(bundle: Bundle | null, position: Position | null) {
  appState.bundle = bundle;
  appState.position = position;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('StatusStrip — ETA honesty', () => {
  beforeEach(() => {
    appState.bundle = null;
    appState.position = null;
  });

  it('shows "On time" for a trip-actual bundle when train is on schedule', async () => {
    setAppState(TRIP_ACTUAL_BUNDLE, POSITION_AT_MILE_10);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    expect(statusEl.textContent).toContain('On time');
  });

  it('shows N min late for a trip-actual bundle when train is late', async () => {
    setAppState(TRIP_ACTUAL_LATE_BUNDLE, POSITION_AT_MILE_10);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    expect(statusEl.textContent).toMatch(/\d+ min late/);
    expect(statusEl.textContent).not.toContain('On time');
  });

  it('shows "Estimated · scheduled" for a generic-scheduled bundle', async () => {
    setAppState(GENERIC_BUNDLE, POSITION_AT_MILE_10);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    expect(statusEl.textContent).toContain('Estimated · scheduled');
  });

  it('does NOT show "On time" or confident delay for a generic-scheduled bundle', async () => {
    setAppState(GENERIC_BUNDLE, POSITION_AT_MILE_10);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    expect(statusEl.textContent).not.toContain('On time');
    expect(statusEl.textContent).not.toMatch(/\d+ min late/);
    expect(statusEl.textContent).not.toMatch(/\d+ min early/);
  });

  it('falls back to "Estimated · scheduled" for trip-actual with wrong date', async () => {
    setAppState(TRIP_ACTUAL_WRONG_DATE_BUNDLE, POSITION_AT_MILE_10);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    expect(statusEl.textContent).toContain('Estimated · scheduled');
    expect(statusEl.textContent).not.toContain('On time');
  });

  it('shows next-stop station name when a station is ahead', async () => {
    setAppState(TRIP_ACTUAL_BUNDLE, POSITION_AT_MILE_10);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    expect(statusEl.textContent).toContain('McComb');
  });

  it('shows "est." label for generic next-stop ETA (single time, no band)', async () => {
    setAppState(GENERIC_BUNDLE, POSITION_AT_MILE_10);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    // Generic shows single time with "est." suffix
    expect(statusEl.textContent).toContain('est.');
    // No parenthesised range
    expect(statusEl.textContent).not.toMatch(/\(\d{1,2}:\d{2}.*–.*\d{1,2}:\d{2}\)/);
  });

  it('shows trip-actual ETA band (p10–p90) for next stop', async () => {
    setAppState(TRIP_ACTUAL_BUNDLE, POSITION_AT_MILE_10);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    // Should show a parenthesised range like "(HH:MM–HH:MM)"
    expect(statusEl.textContent).toMatch(/\d{1,2}:\d{2}.*–.*\d{1,2}:\d{2}/);
  });

  it('renders loading state when no bundle', async () => {
    setAppState(null, null);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    expect(statusEl.textContent).toContain('Loading');
  });
});

describe('StatusStrip — suncalc integration', () => {
  beforeEach(() => {
    appState.bundle = null;
    appState.position = null;
  });

  it('renders sunrise/sunset section when position is available', async () => {
    setAppState(TRIP_ACTUAL_BUNDLE, {
      mile: 5, lat: 39.7392, lon: -104.9903, // Denver — guaranteed sunrise/sunset
      source: 'gps', direction: 1, leg: '58', stopped: false,
    });
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    // The ☀ Rise/Set label should appear
    expect(statusEl.textContent).toContain('Rise/Set');
    // suncalc produces real times — verify a time pattern is present
    expect(statusEl.textContent).toMatch(/\d{1,2}:\d{2}/);
  });

  it('does not show Rise/Set section when no position', async () => {
    setAppState(TRIP_ACTUAL_BUNDLE, null);
    render(StatusStrip);
    const statusEl = screen.getByRole('status');
    expect(statusEl.textContent).not.toContain('Rise/Set');
  });
});
