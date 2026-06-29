<script lang="ts">
  /**
   * PositionLayer.svelte — Live/predicted position marker + P10–P90 uncertainty band.
   *
   * Plan 0 constraints:
   * - P10–P90 band is drawn as a REAL on-route segment via milepostToLatLon,
   *   NOT a horizontal ±lon offset.
   * - Band endpoints come from p10Mile and p90Mile derived from position mile.
   * - Style differs by position.source: gps=solid blue, predicted=lighter,
   *   off-route=muted/locating style.
   * - Nullable place/theme handled gracefully.
   * - position_table rows are [elapsed_min, mile, lat, lon];
   *   milepostToLatLon needs Polyline = [[mile, lat, lon], ...].
   */
  import { onDestroy } from 'svelte';
  import type { Map as MaplibreMap, GeoJSONSource } from 'maplibre-gl';
  import { milepostToLatLon } from 'companion-core';
  import { appState } from '$lib/core/AppState.svelte';
  import type { Polyline } from 'companion-core';

  // ── Props ───────────────────────────────────────────────────────────────────

  let { map }: { map: MaplibreMap } = $props();

  // ── Constants ───────────────────────────────────────────────────────────────

  const POSITION_SOURCE = 'position-source';
  const BAND_SOURCE = 'position-band-source';
  const POSITION_LAYER = 'position-layer';
  const BAND_LAYER = 'position-band-layer';

  /** Half-spread in miles used when no ETA band is available (fallback). */
  const FALLBACK_BAND_HALF_MI = 5.0;

  // ── State ───────────────────────────────────────────────────────────────────

  let initialized = false;

  // ── Helpers ─────────────────────────────────────────────────────────────────

  /**
   * Build the Polyline format required by milepostToLatLon from position_table.
   * position_table rows: [elapsed_min, mile, lat, lon]
   * Polyline format:    [[mile, lat, lon], ...]
   */
  function buildPolyline(): Polyline | null {
    const bundle = appState.bundle;
    if (!bundle || bundle.position_table.length === 0) return null;
    return bundle.position_table.map(([_elapsed, mile, lat, lon]) => [mile, lat, lon] as [number, number, number]);
  }

  function initLayers(): void {
    if (!map || initialized) return;
    initialized = true;

    map.addSource(POSITION_SOURCE, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    map.addSource(BAND_SOURCE, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    // P10–P90 uncertainty band — semi-transparent blue line on the route
    map.addLayer({
      id: BAND_LAYER,
      type: 'line',
      source: BAND_SOURCE,
      paint: {
        'line-color': '#60a5fa',
        'line-width': 10,
        'line-opacity': 0.30,
      },
    });

    // Position marker — circle styled by source
    map.addLayer({
      id: POSITION_LAYER,
      type: 'circle',
      source: POSITION_SOURCE,
      paint: {
        'circle-radius': 10,
        // Color varies by source: gps=blue, predicted=cyan, off-route=gray
        'circle-color': [
          'match',
          ['get', 'source'],
          'gps',        '#2563eb',
          'live',       '#16a34a',
          'deadreckon', '#7c3aed',
          'predicted',  '#0891b2',
          'off-route',  '#9ca3af',
          /* default */ '#2563eb',
        ],
        'circle-stroke-color': '#fff',
        'circle-stroke-width': 3,
        'circle-opacity': [
          'match',
          ['get', 'source'],
          'off-route', 0.5,
          /* default */ 1.0,
        ],
      },
    });
  }

  // ── Reactive update ─────────────────────────────────────────────────────────

  $effect(() => {
    const pos = appState.position;
    if (!map || !pos) return;

    if (!initialized) initLayers();

    // ── Position marker ──────────────────────────────────────────────────────
    const posSource = map.getSource(POSITION_SOURCE) as GeoJSONSource | undefined;
    if (posSource) {
      posSource.setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [pos.lon, pos.lat] },
            properties: { mile: pos.mile, source: pos.source },
          },
        ],
      });
    }

    // ── P10–P90 band ─────────────────────────────────────────────────────────
    // Build the band as a real on-route segment using milepostToLatLon.
    // This ensures the band follows the track geometry, not a lat/lon offset.
    const poly = buildPolyline();
    const bandSource = map.getSource(BAND_SOURCE) as GeoJSONSource | undefined;

    if (poly && bandSource) {
      let p10Mile: number;
      let p90Mile: number;

      // Derive mile range from ETA if available, else use fallback spread
      if (appState.bundle && appState.bundle.eta_table.length > 0) {
        // Find the spread from the nearest eta_table entry
        const nearestRow = appState.bundle.eta_table.reduce((prev, cur) => {
          const prevStation = appState.bundle!.stations.find(s => s.code === prev.station_code);
          const curStation = appState.bundle!.stations.find(s => s.code === cur.station_code);
          const prevDist = prevStation ? Math.abs(prevStation.mile - pos.mile) : Infinity;
          const curDist = curStation ? Math.abs(curStation.mile - pos.mile) : Infinity;
          return curDist < prevDist ? cur : prev;
        });

        // Spread in minutes; convert to approximate miles using average speed
        // from position_table (simple heuristic for band width)
        const totalMile = poly[poly.length - 1][0] - poly[0][0];
        const totalMin = appState.bundle.position_table[appState.bundle.position_table.length - 1][0];
        const avgSpeedMiPerMin = totalMin > 0 ? totalMile / totalMin : 0.8; // fallback 48mph

        const spreadLowMin = nearestRow.p50_min - nearestRow.p10_min;
        const spreadHighMin = nearestRow.p90_min - nearestRow.p50_min;
        p10Mile = Math.max(poly[0][0], pos.mile - spreadLowMin * avgSpeedMiPerMin);
        p90Mile = Math.min(poly[poly.length - 1][0], pos.mile + spreadHighMin * avgSpeedMiPerMin);
      } else {
        // Fallback: ±FALLBACK_BAND_HALF_MI around current position
        const minMile = poly[0][0];
        const maxMile = poly[poly.length - 1][0];
        p10Mile = Math.max(minMile, pos.mile - FALLBACK_BAND_HALF_MI);
        p90Mile = Math.min(maxMile, pos.mile + FALLBACK_BAND_HALF_MI);
      }

      // Get on-route lat/lon for the band endpoints via milepostToLatLon
      const p10LatLon = milepostToLatLon(poly, p10Mile);
      const p90LatLon = milepostToLatLon(poly, p90Mile);

      // Build a dense segment along the route between p10 and p90
      // by sampling milepostToLatLon at intervals for a smooth band
      const SAMPLE_COUNT = 10;
      const bandCoords: [number, number][] = [];
      for (let i = 0; i <= SAMPLE_COUNT; i++) {
        const m = p10Mile + (i / SAMPLE_COUNT) * (p90Mile - p10Mile);
        const ll = milepostToLatLon(poly, m);
        bandCoords.push([ll.lon, ll.lat]);
      }

      // Ensure we use the exact endpoints (p10 and p90 directly from milepostToLatLon)
      bandCoords[0] = [p10LatLon.lon, p10LatLon.lat];
      bandCoords[SAMPLE_COUNT] = [p90LatLon.lon, p90LatLon.lat];

      bandSource.setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: {
              type: 'LineString',
              coordinates: bandCoords,
            },
            properties: { source: pos.source },
          },
        ],
      });
    }
  });

  // ── Cleanup ─────────────────────────────────────────────────────────────────

  onDestroy(() => {
    if (!map) return;
    [POSITION_LAYER, BAND_LAYER].forEach((id) => {
      if (map.getLayer(id)) map.removeLayer(id);
    });
    [POSITION_SOURCE, BAND_SOURCE].forEach((id) => {
      if (map.getSource(id)) map.removeSource(id);
    });
  });
</script>
