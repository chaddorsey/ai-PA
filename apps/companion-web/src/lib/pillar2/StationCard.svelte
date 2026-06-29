<script lang="ts">
  import type { Bundle, Station, EtaResult, Position } from 'companion-core';
  import { Eta } from 'companion-core';

  // ── Props ────────────────────────────────────────────────────────────────────

  export let bundle: Bundle;
  export let stationCode: string;
  export let position: Position | null = null;
  export let onDismiss: (() => void) | null = null;

  // ── Threshold constants ──────────────────────────────────────────────────────

  /**
   * Minimum dwell_min to show "Can you step off? Yes".
   * Documented threshold: ≥5 minutes allows a reasonable platform stop.
   */
  const STEP_OFF_DWELL_MIN = 5;

  // ── Derived values ───────────────────────────────────────────────────────────

  $: station = bundle.stations.find(s => s.code === stationCode) ?? null;

  // Build an Eta instance from the bundle
  $: eta = (() => {
    const origin = bundle.stations.find(s => s.sched_dep !== null);
    const depMs = origin?.sched_dep ? new Date(origin.sched_dep).getTime() : NaN;
    return new Eta(bundle, depMs);
  })();

  $: isTripActual = bundle.schedule_basis.kind === 'trip-actual';

  $: etaResult = (() => {
    if (!station || !position) return null;
    try {
      return eta.toStation(station.code, position);
    } catch {
      return null;
    }
  })();

  $: stepOff = station !== null && station.dwell_min >= STEP_OFF_DWELL_MIN;

  // Lore: look up from bundle.layers.lore by station code or name
  $: loreLine = (() => {
    if (!station) return '';
    const lore = bundle.layers?.lore as Record<string, { summary?: string }> | null;
    if (!lore) return '';
    const entry =
      lore[station.code] ??
      lore[station.name] ??
      lore[String(station.mile)] ??
      null;
    return entry?.summary ?? '';
  })();

  // Amenities: from layers.guide or a bundle-level amenities field
  $: amenities = (() => {
    if (!station) return [] as string[];
    const guide = bundle.layers?.guide as Record<string, { amenities?: string[] }> | null;
    if (!guide) return [] as string[];
    const entry = guide[station.code] ?? guide[station.name] ?? null;
    return (entry?.amenities ?? []) as string[];
  })();

  function fmt(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function formatEtaTripActual(result: EtaResult): string {
    const f = (ms: number) =>
      new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${f(result.p50)} (${f(result.p10)}–${f(result.p90)})`;
  }

  function formatEtaGeneric(result: EtaResult): string {
    const f = (ms: number) =>
      new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${f(result.p50)} est.`;
  }
</script>

{#if station}
  <div class="station-card-overlay" role="dialog" aria-modal="true" aria-label="Station: {station.name}">
    <div class="station-card">

      <!-- Header -->
      <div class="station-card__header">
        <div>
          <h2 class="station-card__name">{station.name}</h2>
          <p class="station-card__meta">Mile {station.mile.toFixed(1)} · {station.code}</p>
        </div>
        {#if onDismiss}
          <button class="station-card__close" on:click={onDismiss} aria-label="Close">✕</button>
        {/if}
      </div>

      <!-- Scheduled times -->
      <div class="station-card__times">
        <div class="station-card__time-row">
          <span class="station-card__label">Scheduled arr</span>
          <span class="station-card__value">{fmt(station.sched_arr)}</span>
        </div>
        <div class="station-card__time-row">
          <span class="station-card__label">Scheduled dep</span>
          <span class="station-card__value">{fmt(station.sched_dep)}</span>
        </div>

        <!-- Predicted arrival: trip-actual shows real band; generic shows "est." -->
        {#if etaResult}
          <div class="station-card__time-row station-card__time-row--predicted">
            <span class="station-card__label">
              {isTripActual ? 'Predicted arrival' : 'Estimated arrival'}
            </span>
            <span class="station-card__value station-card__value--predicted">
              {#if !etaResult.estimated}
                {formatEtaTripActual(etaResult)}
              {:else}
                {formatEtaGeneric(etaResult)}
              {/if}
            </span>
          </div>
        {/if}
      </div>

      <!-- Dwell / Step-off -->
      {#if station.dwell_min > 0}
        <div class="station-card__dwell-row">
          <span class="station-card__dwell-length" aria-label="Stop length">
            ≈{station.dwell_min} min here
          </span>
          <span
            class="station-card__stepoff"
            class:station-card__stepoff--yes={stepOff}
            class:station-card__stepoff--no={!stepOff}
            aria-label={stepOff ? 'You can step off the train' : 'Not enough time to step off'}
          >
            {stepOff ? 'Step off ✓' : 'Stay on'}
          </span>
        </div>
      {/if}

      <!-- Amenities -->
      {#if amenities.length > 0}
        <div class="station-card__section">
          <h3 class="station-card__section-label">Amenities</h3>
          <ul class="station-card__amenity-list">
            {#each amenities as a}
              <li class="station-card__amenity-chip">{a}</li>
            {/each}
          </ul>
        </div>
      {/if}

      <!-- Lore / local context -->
      {#if loreLine}
        <blockquote class="station-card__lore">{loreLine}</blockquote>
      {/if}

    </div>
  </div>
{/if}

<style>
  .station-card-overlay {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 200;
    display: flex;
    justify-content: center;
    pointer-events: none;
  }

  .station-card {
    background: #fff;
    border-radius: 16px 16px 0 0;
    box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.18);
    padding: 20px 24px 40px;
    width: 100%;
    max-width: 480px;
    pointer-events: all;
    animation: slideUp 0.26s ease-out;
  }

  @keyframes slideUp {
    from { transform: translateY(100%); }
    to { transform: translateY(0); }
  }

  .station-card__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 16px;
  }

  .station-card__name {
    font-size: 1.25rem;
    font-weight: 700;
    margin: 0 0 2px;
    color: #1a1a2e;
  }

  .station-card__meta {
    font-size: 0.8125rem;
    color: #9ca3af;
    margin: 0;
  }

  .station-card__close {
    background: none;
    border: none;
    font-size: 1.25rem;
    color: #888;
    cursor: pointer;
    padding: 4px 8px;
    line-height: 1;
    border-radius: 6px;
  }

  .station-card__close:hover { background: #f3f4f6; }

  .station-card__times {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
    padding-bottom: 16px;
    border-bottom: 1px solid #f0f0f0;
  }

  .station-card__time-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
  }

  .station-card__time-row--predicted {
    margin-top: 4px;
    padding-top: 8px;
    border-top: 1px dashed #e5e7eb;
  }

  .station-card__label {
    font-size: 0.75rem;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    flex-shrink: 0;
  }

  .station-card__value {
    font-size: 0.9375rem;
    font-weight: 600;
    color: #1a1a2e;
    text-align: right;
  }

  .station-card__value--predicted {
    color: #2563eb;
  }

  .station-card__dwell-row {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 16px;
    padding: 10px 14px;
    background: #f9fafb;
    border-radius: 10px;
  }

  .station-card__dwell-length {
    font-size: 0.9375rem;
    font-weight: 600;
    color: #333;
    flex: 1;
  }

  .station-card__stepoff {
    font-size: 0.8125rem;
    font-weight: 700;
    border-radius: 6px;
    padding: 3px 10px;
  }

  .station-card__stepoff--yes {
    background: #dcfce7;
    color: #166534;
  }

  .station-card__stepoff--no {
    background: #fee2e2;
    color: #991b1b;
  }

  .station-card__section {
    margin-bottom: 14px;
  }

  .station-card__section-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #9ca3af;
    margin: 0 0 6px;
  }

  .station-card__amenity-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .station-card__amenity-chip {
    background: #eff6ff;
    color: #1d4ed8;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 0.8125rem;
    font-weight: 500;
  }

  .station-card__lore {
    font-size: 0.875rem;
    color: #555;
    font-style: italic;
    margin: 0;
    line-height: 1.55;
    border-left: 3px solid #e5e7eb;
    padding: 0 0 0 12px;
  }
</style>
