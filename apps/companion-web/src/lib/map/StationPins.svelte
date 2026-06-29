<script lang="ts">
  /**
   * StationPins.svelte — Station markers on the MapLibre map.
   *
   * Reads bundle.stations (top-level, per Plan 0 contract).
   * Clicking a pin calls onStationSelect(code).
   * Handles nullable place/theme gracefully.
   */
  import { onDestroy } from 'svelte';
  import type { Map as MaplibreMap, Marker } from 'maplibre-gl';
  import maplibregl from 'maplibre-gl';
  import { appState } from '$lib/core/AppState.svelte';
  import type { Station } from 'companion-core';

  // ── Props ───────────────────────────────────────────────────────────────────

  let { map, onStationSelect = (_code: string) => {} }: {
    map: MaplibreMap;
    onStationSelect?: (code: string) => void;
  } = $props();

  // ── State ───────────────────────────────────────────────────────────────────

  const markers: Marker[] = [];

  // ── Reactive: rebuild markers when bundle changes ───────────────────────────

  $effect(() => {
    const bundle = appState.bundle;

    // Clear existing markers
    markers.forEach((m) => m.remove());
    markers.length = 0;

    if (!map || !bundle) return;

    const stations: Station[] = bundle.stations ?? [];

    for (const station of stations) {
      // Create a custom DOM element for the pin
      const el = document.createElement('div');
      el.className = 'station-pin';
      el.setAttribute('aria-label', station.name);
      el.setAttribute('data-station-code', station.code);
      el.style.cssText = [
        'width:12px',
        'height:12px',
        'border-radius:50%',
        'background:#fff',
        'border:2.5px solid #2563eb',
        'cursor:pointer',
        'box-shadow:0 1px 4px rgba(0,0,0,0.25)',
        'flex-shrink:0',
      ].join(';');

      const code = station.code; // capture for closure
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        onStationSelect(code);
      });

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([station.lon, station.lat])
        .addTo(map);

      markers.push(marker);
    }
  });

  // ── Cleanup ─────────────────────────────────────────────────────────────────

  onDestroy(() => {
    markers.forEach((m) => m.remove());
    markers.length = 0;
  });
</script>
