/**
 * ItineraryView tests — past/current/upcoming classification.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ItineraryView from '$lib/pillar1/ItineraryView.svelte';
import { appState } from '$lib/core/AppState.svelte';
import type { Bundle, Position } from 'companion-core';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const TODAY = new Date().toISOString().slice(0, 10);

const BUNDLE: Bundle = {
  leg: '58',
  schedule_basis: { kind: 'trip-actual', valid_dates: [TODAY] },
  stations: [
    {
      code: 'NOL', name: 'New Orleans', mile: 0,
      lat: 29.94, lon: -90.07,
      sched_arr: null, sched_dep: `${TODAY}T15:45:00-05:00`, dwell_min: 0,
    },
    {
      code: 'MCB', name: 'McComb', mile: 98,
      lat: 31.24, lon: -90.45,
      sched_arr: `${TODAY}T18:07:00-06:00`, sched_dep: `${TODAY}T18:10:00-06:00`, dwell_min: 3,
    },
    {
      code: 'HAT', name: 'Hattiesburg', mile: 148,
      lat: 31.32, lon: -89.29,
      sched_arr: `${TODAY}T19:07:00-06:00`, sched_dep: `${TODAY}T19:09:00-06:00`, dwell_min: 2,
    },
  ],
  geometry: { type: 'LineString', coordinates: [[-90.07, 29.94]] },
  units: [],
  layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
  position_table: [[0, 0, 29.94, -90.07]],
  eta_table: [],
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ItineraryView — station classification', () => {
  beforeEach(() => {
    appState.bundle = null;
    appState.position = null;
  });

  it('renders all stations when bundle is loaded', async () => {
    appState.bundle = BUNDLE;
    appState.position = { mile: 50, lat: 30.5, lon: -90.3, source: 'gps', direction: 1, leg: '58', stopped: false };
    render(ItineraryView);
    expect(screen.getByText('New Orleans')).toBeTruthy();
    expect(screen.getByText('McComb')).toBeTruthy();
    expect(screen.getByText('Hattiesburg')).toBeTruthy();
  });

  it('marks past stations with aria-label containing "past"', async () => {
    // Position at mile 130 → NOL (mile 0) and MCB (mile 98) are past
    appState.bundle = BUNDLE;
    appState.position = { mile: 130, lat: 31.2, lon: -90.0, source: 'gps', direction: 1, leg: '58', stopped: false };
    render(ItineraryView);
    const items = screen.getAllByRole('listitem');
    const nolItem = items.find(el => el.textContent?.includes('New Orleans'));
    expect(nolItem?.getAttribute('aria-label')).toContain('past');
    const mcbItem = items.find(el => el.textContent?.includes('McComb'));
    expect(mcbItem?.getAttribute('aria-label')).toContain('past');
  });

  it('marks the current station with aria-label containing "current"', async () => {
    // Position at mile 98 → MCB is current
    appState.bundle = BUNDLE;
    appState.position = { mile: 98, lat: 31.24, lon: -90.45, source: 'gps', direction: 1, leg: '58', stopped: false };
    render(ItineraryView);
    const items = screen.getAllByRole('listitem');
    const mcbItem = items.find(el => el.textContent?.includes('McComb'));
    expect(mcbItem?.getAttribute('aria-label')).toContain('current');
  });

  it('marks upcoming stations with aria-label containing "upcoming"', async () => {
    // Position at mile 10 → all except NOL are upcoming
    appState.bundle = BUNDLE;
    appState.position = { mile: 10, lat: 30.1, lon: -90.1, source: 'gps', direction: 1, leg: '58', stopped: false };
    render(ItineraryView);
    const items = screen.getAllByRole('listitem');
    const hatItem = items.find(el => el.textContent?.includes('Hattiesburg'));
    expect(hatItem?.getAttribute('aria-label')).toContain('upcoming');
  });

  it('shows the leg ID in the list aria-label', async () => {
    appState.bundle = BUNDLE;
    appState.position = { mile: 10, lat: 30.1, lon: -90.1, source: 'gps', direction: 1, leg: '58', stopped: false };
    render(ItineraryView);
    const list = screen.getByRole('list');
    expect(list.getAttribute('aria-label')).toContain('58');
  });

  it('shows empty state when no bundle loaded', async () => {
    appState.bundle = null;
    render(ItineraryView);
    expect(screen.getByText(/No bundle loaded/i)).toBeTruthy();
  });

  it('shows schedule_basis badge for generic-scheduled', async () => {
    appState.bundle = {
      ...BUNDLE,
      schedule_basis: { kind: 'generic-scheduled', valid_dates: [] },
    };
    appState.position = { mile: 10, lat: 30.1, lon: -90.1, source: 'gps', direction: 1, leg: '58', stopped: false };
    render(ItineraryView);
    expect(screen.getByText('Scheduled')).toBeTruthy();
  });

  it('shows trip-actual badge for trip-actual', async () => {
    appState.bundle = BUNDLE;
    appState.position = { mile: 10, lat: 30.1, lon: -90.1, source: 'gps', direction: 1, leg: '58', stopped: false };
    render(ItineraryView);
    expect(screen.getByText('Trip actual')).toBeTruthy();
  });
});
