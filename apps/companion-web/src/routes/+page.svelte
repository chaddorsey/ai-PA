<script lang="ts">
  import { appState } from '$lib/core/AppState.svelte';
  import TripMap from '$lib/map/TripMap.svelte';
  import StatusStrip from '$lib/pillar1/StatusStrip.svelte';
  import ItineraryView from '$lib/pillar1/ItineraryView.svelte';
  import StationCard from '$lib/pillar2/StationCard.svelte';
  import type { Station } from 'companion-core';

  // ── Station selection state ─────────────────────────────────────────────────
  // Station pin taps on the map surface a StationCard overlay.

  let selectedStationCode = $state<string | null>(null);

  function handleStationSelect(code: string) {
    selectedStationCode = code;
  }

  function dismissStationCard() {
    selectedStationCode = null;
  }

  // Auto-dismiss when train passes the station
  $effect(() => {
    if (!selectedStationCode || !appState.bundle || !appState.position) return;
    const station = appState.bundle.stations.find(
      (s: Station) => s.code === selectedStationCode,
    );
    if (station && appState.position.mile > station.mile + 0.5) {
      selectedStationCode = null;
    }
  });
</script>

<!--
  Trip home — Pillar 1.
  Layout: full-screen map behind the status strip and itinerary overlay.
-->
<div class="trip-home">
  <!-- Full-screen map layer -->
  <div class="trip-home__map">
    <TripMap onStationSelect={handleStationSelect} />
  </div>

  <!-- Status strip: on-time, next stop ETA, sunrise/sunset, position -->
  <div class="trip-home__status">
    <StatusStrip />
  </div>

  <!-- Itinerary accordion: current leg stops -->
  <div class="trip-home__itinerary">
    <ItineraryView />
  </div>

  <!-- Station card: shown when a pin is tapped -->
  {#if selectedStationCode && appState.bundle}
    <StationCard
      bundle={appState.bundle}
      stationCode={selectedStationCode}
      position={appState.position}
      onDismiss={dismissStationCard}
    />
  {/if}
</div>

<style>
  .trip-home {
    position: relative;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .trip-home__map {
    /* Map occupies the upper ~55% of the pillar, behind status strip */
    flex: 1 0 0;
    position: relative;
    min-height: 0;
  }

  .trip-home__status {
    /* Status strip is always visible, scrolls horizontally */
    flex-shrink: 0;
    z-index: 5;
  }

  .trip-home__itinerary {
    /* Itinerary list occupies the lower portion; scrolls vertically */
    flex: 0 0 auto;
    max-height: 45%;
    overflow-y: auto;
    background: #fff;
    border-top: 1px solid #e5e7eb;
    z-index: 5;
  }
</style>
