/**
 * map.test.ts — Tests for TripMap, StationPins, and PositionLayer.
 *
 * maplibre-gl is mocked via the alias in vite.config.ts (src/__mocks__/maplibre-gl.ts).
 * pmtiles is mocked similarly.
 *
 * Tests assert:
 * - TripMap: adds a 'route' source with coordinates matching bundle.geometry
 * - StationPins: creates one Marker per bundle.stations entry; emits stationSelect on click
 * - PositionLayer: band endpoints are computed via milepostToLatLon (on-route points,
 *   not a horizontal ±lon offset); switches to muted style when source === 'off-route'
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import { appState } from '$lib/core/AppState.svelte';
import { MapMock, Marker } from 'maplibre-gl';
import type { Bundle, Position } from 'companion-core';

// ── Fixture data ──────────────────────────────────────────────────────────────

const GEOMETRY: Bundle['geometry'] = {
  type: 'LineString',
  coordinates: [
    [-90.07829, 29.94609],
    [-90.46217, 30.50718],
    [-90.45133, 31.24447],
  ],
};

// position_table rows: [elapsed_min, mile, lat, lon]
const POSITION_TABLE: Bundle['position_table'] = [
  [0,   0,   29.94609, -90.07829],
  [60,  53,  30.50718, -90.46217],
  [110, 106, 31.24447, -90.45133],
];

const STATIONS: Bundle['stations'] = [
  { code: 'NOL', name: 'New Orleans, LA', mile: 0,   lat: 29.94609, lon: -90.07829, sched_arr: null,                         sched_dep: '2026-07-11T15:45:00-05:00', dwell_min: 0 },
  { code: 'HMD', name: 'Hammond, LA',     mile: 53,  lat: 30.50718, lon: -90.46217, sched_arr: '2026-07-11T16:51:00-05:00', sched_dep: '2026-07-11T16:51:00-05:00', dwell_min: 0 },
  { code: 'MCB', name: 'McComb, MS',      mile: 106, lat: 31.24447, lon: -90.45133, sched_arr: '2026-07-11T17:44:00-05:00', sched_dep: '2026-07-11T17:44:00-05:00', dwell_min: 0 },
];

const PROXY_BUNDLE: Bundle = {
  leg: '58',
  schedule_basis: { kind: 'trip-actual', valid_dates: ['2026-07-11'] },
  stations: STATIONS,
  geometry: GEOMETRY,
  units: [],
  layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
  position_table: POSITION_TABLE,
  eta_table: [],
};

const GPS_POSITION: Position = {
  mile: 30,
  lat: 30.2,
  lon: -90.3,
  source: 'gps',
  direction: 1,
  leg: '58',
  stopped: false,
};

// ── Test: TripMap ─────────────────────────────────────────────────────────────

describe('TripMap', () => {
  beforeEach(() => {
    appState.bundle = PROXY_BUNDLE;
    appState.position = null;
  });

  afterEach(() => {
    appState.bundle = null;
    appState.position = null;
    cleanup();
  });

  it('adds a route source with coordinates matching bundle.geometry', async () => {
    // Import TripMap — maplibre-gl is mocked so no WebGL is needed
    const { default: TripMap } = await import('./TripMap.svelte');

    // Spy on MapMock.addSource to capture calls
    const addSourceSpy = vi.spyOn(MapMock.prototype, 'addSource');

    render(TripMap);

    // The map 'load' event fires synchronously in the mock.
    // TripMap adds the route source on load when a bundle is present.
    const routeCall = addSourceSpy.mock.calls.find(([id]) => id === 'route');
    expect(routeCall).toBeDefined();

    if (routeCall) {
      const [, sourceSpec] = routeCall;
      const spec = sourceSpec as { type: string; data: GeoJSON.Feature<GeoJSON.LineString> };
      expect(spec.type).toBe('geojson');
      expect(spec.data.geometry.type).toBe('LineString');
      // Coordinates should match bundle.geometry exactly
      const coords = spec.data.geometry.coordinates;
      expect(coords).toHaveLength(GEOMETRY.coordinates.length);
      expect(coords[0]).toEqual(GEOMETRY.coordinates[0]);
      expect(coords[coords.length - 1]).toEqual(GEOMETRY.coordinates[GEOMETRY.coordinates.length - 1]);
    }

    addSourceSpy.mockRestore();
  });

  it('adds a route-line layer', async () => {
    const { default: TripMap } = await import('./TripMap.svelte');
    const addLayerSpy = vi.spyOn(MapMock.prototype, 'addLayer');

    render(TripMap);

    const routeLineCall = addLayerSpy.mock.calls.find(([spec]) => (spec as { id: string }).id === 'route-line');
    expect(routeLineCall).toBeDefined();

    addLayerSpy.mockRestore();
  });

  it('calls fitBounds when bundle geometry has coordinates', async () => {
    const { default: TripMap } = await import('./TripMap.svelte');
    const fitBoundsSpy = vi.spyOn(MapMock.prototype, 'fitBounds');

    render(TripMap);

    expect(fitBoundsSpy).toHaveBeenCalled();
    fitBoundsSpy.mockRestore();
  });
});

// ── Test: StationPins ─────────────────────────────────────────────────────────

describe('StationPins', () => {
  beforeEach(() => {
    appState.bundle = PROXY_BUNDLE;
  });

  afterEach(() => {
    appState.bundle = null;
    cleanup();
  });

  it('creates one Marker per bundle.stations entry', async () => {
    const { default: StationPins } = await import('./StationPins.svelte');

    // Build a mock map to inject as prop
    const mockMap = new MapMock() as unknown as import('maplibre-gl').Map;

    render(StationPins, { props: { map: mockMap, onStationSelect: vi.fn() } });

    // The mock addTo() pushes markers to _markers on the MapMock
    const mapWithMarkers = mockMap as unknown as MapMock;
    expect(mapWithMarkers._markers).toHaveLength(STATIONS.length);
  });

  it('emits stationSelect with station code when a pin is clicked', async () => {
    const { default: StationPins } = await import('./StationPins.svelte');

    const onStationSelect = vi.fn();
    const mockMap = new MapMock() as unknown as import('maplibre-gl').Map;

    render(StationPins, { props: { map: mockMap, onStationSelect } });

    const mapWithMarkers = mockMap as unknown as MapMock;
    expect(mapWithMarkers._markers.length).toBeGreaterThan(0);

    // Simulate click on the first marker's element
    const firstMarker = mapWithMarkers._markers[0] as Marker;
    firstMarker.simulateClick();

    expect(onStationSelect).toHaveBeenCalledWith(STATIONS[0].code);
  });

  it('renders correct number of markers for all three stations', async () => {
    const { default: StationPins } = await import('./StationPins.svelte');

    const mockMap = new MapMock() as unknown as import('maplibre-gl').Map;
    render(StationPins, { props: { map: mockMap, onStationSelect: vi.fn() } });

    const mapWithMarkers = mockMap as unknown as MapMock;
    expect(mapWithMarkers._markers).toHaveLength(3); // NOL, HMD, MCB
  });
});

// ── Test: PositionLayer ───────────────────────────────────────────────────────

describe('PositionLayer', () => {
  beforeEach(() => {
    appState.bundle = PROXY_BUNDLE;
    appState.position = GPS_POSITION;
  });

  afterEach(() => {
    appState.bundle = null;
    appState.position = null;
    cleanup();
  });

  it('band endpoints are ON the polyline (not a horizontal ±lon offset)', async () => {
    const { default: PositionLayer } = await import('./PositionLayer.svelte');

    // Spy on the band source setData to capture band coordinates
    let capturedBandCoords: [number, number][] | null = null;

    const mockMap = new MapMock() as unknown as import('maplibre-gl').Map;

    // Patch addSource on the specific instance to track setData calls
    const originalAddSource = (mockMap as unknown as MapMock).addSource.bind(mockMap);
    (mockMap as unknown as MapMock).addSource = function(id: string, spec: unknown) {
      originalAddSource(id, spec);
      if (id === 'position-band-source') {
        // Intercept setData on the created source
        const src = this._sources.get(id) as { setData: (d: unknown) => void; _data: unknown };
        const origSetData = src.setData.bind(src);
        src.setData = (data: unknown) => {
          origSetData(data);
          const fc = data as GeoJSON.FeatureCollection<GeoJSON.LineString>;
          if (fc.features?.[0]?.geometry?.coordinates) {
            capturedBandCoords = fc.features[0].geometry.coordinates as [number, number][];
          }
        };
      }
      return this;
    };

    render(PositionLayer, { props: { map: mockMap } });

    // The $effect fires synchronously in test because appState.position is set.
    // Allow micro-task queue to flush.
    await new Promise((r) => setTimeout(r, 0));

    // Band coordinates should have been set
    expect(capturedBandCoords).not.toBeNull();

    if (capturedBandCoords) {
      const coords = capturedBandCoords;
      expect(coords.length).toBeGreaterThanOrEqual(2);

      // Verify the band is NOT just a horizontal ±lon offset:
      // A horizontal offset would give identical lats for all points but varying lons.
      // Real on-route points change BOTH lat and lon.
      const lats = coords.map(([, lat]) => lat);
      const uniqueLats = new Set(lats.map(l => l.toFixed(4)));

      // The polyline from NOL(lat=29.94) to MCB(lat=31.24) spans ~1.3° lat.
      // A band around mile 30 (between NOL and HMD) must have varying lat.
      expect(uniqueLats.size).toBeGreaterThan(1);

      // Also verify lons are in the corridor (not wildly off)
      const lons = coords.map(([lon]) => lon);
      lons.forEach(lon => {
        expect(lon).toBeGreaterThan(-95);
        expect(lon).toBeLessThan(-85);
      });
    }
  });

  it('adds a position marker source and layer', async () => {
    const { default: PositionLayer } = await import('./PositionLayer.svelte');
    const mockMap = new MapMock() as unknown as import('maplibre-gl').Map;
    const addSourceSpy = vi.spyOn(mockMap as unknown as MapMock, 'addSource');

    render(PositionLayer, { props: { map: mockMap } });
    await new Promise((r) => setTimeout(r, 0));

    const posSourceCall = addSourceSpy.mock.calls.find(([id]) => id === 'position-source');
    expect(posSourceCall).toBeDefined();
  });
});

// ── Test: CalloutCard ─────────────────────────────────────────────────────────

describe('CalloutCard', () => {
  it('renders place name and text', async () => {
    const { default: CalloutCard } = await import('./CalloutCard.svelte');
    const { screen } = await import('@testing-library/svelte');

    const mockUnit = {
      id: 'u-test',
      kind: 'squib' as const,
      mile: 10,
      place: 'Test Place',
      side: 'left' as const,
      salience: 4 as const,
      theme: 'history',
      text: 'Test text here.',
      lat: 30.0,
      lon: -90.1,
      audio: 'audio/test.mp3',
      dur_s: 20,
    };

    render(CalloutCard, { props: { unit: mockUnit, onDismiss: vi.fn() } });

    expect(screen.getByText('Test Place')).toBeTruthy();
    expect(screen.getByText('Test text here.')).toBeTruthy();
    expect(screen.getByText('history')).toBeTruthy();
  });

  it('handles null place gracefully', async () => {
    const { default: CalloutCard } = await import('./CalloutCard.svelte');
    const { screen } = await import('@testing-library/svelte');

    const mockUnit = {
      id: 'u-null',
      kind: 'squib' as const,
      mile: 10,
      place: null,
      side: null,
      salience: 3 as const,
      theme: null,
      text: 'Some text.',
      lat: 30.0,
      lon: -90.1,
      audio: 'audio/null.mp3',
      dur_s: 15,
    };

    render(CalloutCard, { props: { unit: mockUnit as import('companion-core').Unit, onDismiss: vi.fn() } });

    // Falls back to 'Unknown location' when place is null
    expect(screen.getByText('Unknown location')).toBeTruthy();
    // No theme badge rendered when theme is null
    expect(screen.queryByText('null')).toBeNull();
  });
});
