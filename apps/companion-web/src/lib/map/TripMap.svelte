<script lang="ts">
  /**
   * TripMap.svelte — Full-screen MapLibre GL JS map.
   *
   * Responsibilities:
   * - Initialises a MapLibre GL map with a PMTiles corridor source
   * - Adds the route polyline from bundle.geometry
   * - Fits the map to the route bounds
   * - Hosts PositionLayer and StationPins as child components (via Svelte context)
   * - Emits station-select events when a station pin is tapped
   *
   * Plan 0 contract:
   * - PMTiles source via addProtocol from the pmtiles package
   * - Route drawn from bundle.geometry (top-level, not bundle.leg.geometry)
   * - Nullable place/theme handled by child components
   */
  import { onMount, onDestroy, setContext } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import { Protocol } from 'pmtiles';
  import PositionLayer from './PositionLayer.svelte';
  import StationPins from './StationPins.svelte';
  import { appState } from '$lib/core/AppState.svelte';
  import type { Bundle } from 'companion-core';

  // ── Props ───────────────────────────────────────────────────────────────────

  let { onStationSelect = (_code: string) => {} }: {
    onStationSelect?: (code: string) => void;
  } = $props();

  // ── State ───────────────────────────────────────────────────────────────────

  let mapContainer: HTMLDivElement;
  let map: maplibregl.Map | null = $state(null);
  let mapReady = $state(false);

  // ── PMTiles protocol ────────────────────────────────────────────────────────

  // Register the PMTiles protocol once so MapLibre can fetch pmtiles:// URLs.
  // This is a no-op if it has already been registered (idempotent).
  const protocol = new Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile.bind(protocol));

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function addRouteLayer(m: maplibregl.Map, bundle: Bundle): void {
    if (m.getSource('route')) return; // already added

    const geometry = bundle.geometry;
    if (!geometry || !geometry.coordinates || geometry.coordinates.length === 0) return;

    m.addSource('route', {
      type: 'geojson',
      data: {
        type: 'Feature',
        geometry: geometry as GeoJSON.LineString,
        properties: {},
      },
    });

    m.addLayer({
      id: 'route-line',
      type: 'line',
      source: 'route',
      paint: {
        'line-color': '#2563eb',
        'line-width': 4,
        'line-opacity': 0.85,
      },
    });

    // Fit map to the route extent
    const coords = geometry.coordinates;
    if (coords.length >= 2) {
      const lons = coords.map(([lon]) => lon);
      const lats = coords.map(([, lat]) => lat);
      const minLon = Math.min(...lons);
      const maxLon = Math.max(...lons);
      const minLat = Math.min(...lats);
      const maxLat = Math.max(...lats);
      m.fitBounds(
        [[minLon, minLat], [maxLon, maxLat]],
        { padding: 40, duration: 600 },
      );
    }
  }

  // ── Lifecycle ───────────────────────────────────────────────────────────────

  onMount(() => {
    const initialBundle = appState.bundle;
    const defaultCenter: [number, number] = initialBundle?.geometry?.coordinates?.[0]
      ? [initialBundle.geometry.coordinates[0][0], initialBundle.geometry.coordinates[0][1]]
      : [-90.07829, 29.94609]; // NOL fallback

    map = new maplibregl.Map({
      container: mapContainer,
      style: {
        version: 8,
        glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
        sources: {
          'corridor-tiles': {
            type: 'vector',
            // Placeholder PMTiles URL — real corridor file added in Plan 1 pipeline.
            // The map still renders (route line layer) even without tile data.
            url: 'pmtiles://corridor.pmtiles',
          },
        },
        layers: [
          // Base background when PMTiles data is not yet available
          {
            id: 'background',
            type: 'background',
            paint: { 'background-color': '#f8f4f0' },
          },
        ],
      },
      center: defaultCenter,
      zoom: 7,
      attributionControl: false,
    });

    map.on('load', () => {
      if (!map) return;

      // Provide the map instance to child components via Svelte context.
      // setContext must be called synchronously during component init, but we
      // can also expose it on the reactive state for children that mount after 'load'.
      setContext('maplibre-map', map);

      if (appState.bundle) {
        addRouteLayer(map, appState.bundle);
      }

      mapReady = true;
    });

    // Error handler — keeps map functional even if tiles 404
    map.on('error', (e) => {
      // Suppress PMTiles-not-found errors during dev/test with proxy bundle
      if ((e as { error?: Error }).error?.message?.includes('Not Found')) return;
      if ((e as { error?: Error }).error?.message?.includes('pmtiles')) return;
    });
  });

  // Reactively add route layer when bundle loads after map is ready
  $effect(() => {
    const bundle = appState.bundle;
    if (!map || !mapReady || !bundle) return;
    addRouteLayer(map, bundle);
  });

  // Reactively pan to current position
  $effect(() => {
    const pos = appState.position;
    if (!map || !mapReady || !pos) return;
    map.easeTo({ center: [pos.lon, pos.lat], duration: 800 });
  });

  onDestroy(() => {
    mapReady = false;
    map?.remove();
    map = null;
  });
</script>

<div class="trip-map" bind:this={mapContainer}>
  {#if mapReady && map}
    <PositionLayer {map} />
    <StationPins {map} {onStationSelect} />
  {/if}
</div>

<style>
  .trip-map {
    width: 100%;
    height: 100%;
    position: absolute;
    inset: 0;
  }
</style>
