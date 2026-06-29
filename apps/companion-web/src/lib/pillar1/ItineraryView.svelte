<script lang="ts">
  import type { Bundle, Station } from 'companion-core';
  import { appState } from '$lib/core/AppState.svelte';

  // ── Station classification ───────────────────────────────────────────────────

  /**
   * Classify a station relative to current position as past/current/upcoming.
   * "Current" = the train is at or just passed this station but hasn't left the dwell window.
   * We use a dwell_min + 1 mile buffer: if within dwell miles of the station, classify as current.
   */
  export function classifyStation(
    station: Station,
    currentMile: number,
  ): 'past' | 'current' | 'upcoming' {
    const dwellBuffer = Math.max(station.dwell_min / 60 * 30, 1); // ~30 mph, min 1 mile
    if (station.mile < currentMile - dwellBuffer) return 'past';
    if (station.mile <= currentMile + 2) return 'current';
    return 'upcoming';
  }

  function fmt(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  // ── Leg ID helpers ───────────────────────────────────────────────────────────

  // Real Amtrak California Zephyr leg IDs are numeric strings
  // matching the bundle's "leg" field (e.g., "3", "58").
  // ItineraryView shows the current leg's stations.
  $: bundle = appState.bundle;
  $: currentMile = appState.position?.mile ?? 0;
  $: stations = bundle?.stations ?? [];
</script>

<div class="itinerary" role="list" aria-label="Trip itinerary — {bundle?.leg ?? 'current leg'}">
  {#if !bundle}
    <div class="itinerary__empty">No bundle loaded.</div>
  {:else}
    <div class="itinerary__leg-header">
      Leg {bundle.leg}
      {#if bundle.schedule_basis.kind === 'generic-scheduled'}
        <span class="itinerary__basis-badge">Scheduled</span>
      {:else}
        <span class="itinerary__basis-badge itinerary__basis-badge--actual">Trip actual</span>
      {/if}
    </div>

    {#each stations as station}
      {@const cls = classifyStation(station, currentMile)}
      <div
        class="itinerary__row"
        class:itinerary__row--past={cls === 'past'}
        class:itinerary__row--current={cls === 'current'}
        class:itinerary__row--upcoming={cls === 'upcoming'}
        role="listitem"
        aria-label="{station.name} — {cls}"
      >
        <div class="itinerary__row-left">
          <span class="itinerary__station-name">{station.name}</span>
          <span class="itinerary__station-code">{station.code}</span>
        </div>
        <div class="itinerary__row-right">
          <div class="itinerary__time-pair">
            <span class="itinerary__time-label">Arr</span>
            <span class="itinerary__time-value">{fmt(station.sched_arr)}</span>
          </div>
          <div class="itinerary__time-pair">
            <span class="itinerary__time-label">Dep</span>
            <span class="itinerary__time-value">{fmt(station.sched_dep)}</span>
          </div>
          {#if station.dwell_min > 0}
            <span class="itinerary__dwell">≈{station.dwell_min} min</span>
          {/if}
        </div>
        {#if cls === 'current'}
          <div class="itinerary__current-indicator" aria-hidden="true">▶</div>
        {/if}
      </div>
    {/each}
  {/if}
</div>

<style>
  .itinerary {
    overflow-y: auto;
    padding: 0 0 16px;
  }

  .itinerary__empty {
    padding: 20px;
    color: #888;
    font-size: 0.875rem;
    text-align: center;
  }

  .itinerary__leg-header {
    padding: 12px 16px 8px;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #888;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid #f0f0f0;
  }

  .itinerary__basis-badge {
    font-size: 0.65rem;
    background: #f3f4f6;
    color: #6b7280;
    border-radius: 4px;
    padding: 1px 6px;
    text-transform: none;
    letter-spacing: normal;
  }

  .itinerary__basis-badge--actual {
    background: #dbeafe;
    color: #1d4ed8;
  }

  .itinerary__row {
    display: flex;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid #f5f5f5;
    gap: 10px;
    position: relative;
  }

  .itinerary__row--past {
    opacity: 0.45;
  }

  .itinerary__row--current {
    background: #eff6ff;
    border-left: 3px solid #2563eb;
  }

  .itinerary__row--upcoming {
    /* default style */
  }

  .itinerary__row-left {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .itinerary__station-name {
    font-size: 0.9375rem;
    font-weight: 600;
    color: #1a1a2e;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .itinerary__station-code {
    font-size: 0.7rem;
    color: #9ca3af;
    font-family: monospace;
  }

  .itinerary__row-right {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    flex-shrink: 0;
  }

  .itinerary__time-pair {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 1px;
  }

  .itinerary__time-label {
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #9ca3af;
  }

  .itinerary__time-value {
    font-size: 0.8125rem;
    font-weight: 600;
    color: #333;
    white-space: nowrap;
  }

  .itinerary__dwell {
    font-size: 0.7rem;
    color: #6b7280;
    align-self: center;
    background: #f3f4f6;
    border-radius: 4px;
    padding: 1px 5px;
  }

  .itinerary__current-indicator {
    position: absolute;
    left: 4px;
    color: #2563eb;
    font-size: 0.6rem;
  }
</style>
