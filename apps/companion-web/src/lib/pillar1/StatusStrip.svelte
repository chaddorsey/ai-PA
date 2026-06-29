<script lang="ts">
  import type { Bundle, EtaResult, Position, Station } from 'companion-core';
  import { Eta } from 'companion-core';
  import { appState } from '$lib/core/AppState.svelte';
  import { getTimes as suncalcGetTimes } from 'suncalc';

  // ── ETA honesty helpers ──────────────────────────────────────────────────────

  /**
   * Format a trip-actual EtaResult (estimated:false) as "HH:MM (HH:MM–HH:MM)".
   * Only call this when estimated===false.
   */
  export function formatEtaTripActual(result: EtaResult): string {
    const fmt = (ms: number) =>
      new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${fmt(result.p50)} (${fmt(result.p10)}–${fmt(result.p90)})`;
  }

  /**
   * Format a generic EtaResult (estimated:true) as "HH:MM est."
   * Only call this when estimated===true.
   */
  export function formatEtaGeneric(result: EtaResult): string {
    const fmt = (ms: number) =>
      new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${fmt(result.p50)} est.`;
  }

  // ── On-time status ───────────────────────────────────────────────────────────

  /**
   * Derive a status string honoring ETA honesty rules:
   * - Only show "On time" / "N min late" when schedule_basis.kind === 'trip-actual'
   *   AND today is in valid_dates AND we have real eta_table data.
   * - For generic-scheduled: "Estimated · scheduled".
   * - trip-actual but wrong date: "Estimated · scheduled".
   */
  function deriveStatus(bundle: Bundle | null): string {
    if (!bundle) return 'Loading…';

    const basis = bundle.schedule_basis;

    if (basis.kind !== 'trip-actual') {
      return 'Estimated · scheduled';
    }

    // trip-actual: check whether today is in valid_dates
    const today = new Date().toISOString().slice(0, 10);
    const validToday = basis.valid_dates.includes(today);
    if (!validToday) {
      return 'Estimated · scheduled';
    }

    // We have a real trip-actual for today — derive delay from eta_table
    if (!bundle.eta_table || bundle.eta_table.length === 0) {
      return 'On time';
    }

    // Use the first eta_table entry vs its corresponding sched_arr
    const firstEtaRow = bundle.eta_table[0];
    const origin = bundle.stations.find(s => s.sched_dep !== null);
    if (!origin || !origin.sched_dep) return 'On time';

    const refStation = bundle.stations.find(s => s.code === firstEtaRow.station_code);
    if (!refStation || !refStation.sched_arr) return 'On time';

    try {
      const originDepMs = new Date(origin.sched_dep).getTime();
      const schedArrMs = new Date(refStation.sched_arr).getTime();
      const etaP50Ms = originDepMs + firstEtaRow.p50_min * 60_000;
      const delayMin = Math.round((etaP50Ms - schedArrMs) / 60_000);

      if (delayMin > 1) return `${delayMin} min late`;
      if (delayMin < -1) return `${Math.abs(delayMin)} min early`;
      return 'On time';
    } catch {
      return 'On time';
    }
  }

  // ── Sunrise/sunset via suncalc ───────────────────────────────────────────────

  function getSunTimes(lat: number, lon: number): { sunrise: string; sunset: string } | null {
    try {
      const times = suncalcGetTimes(new Date(), lat, lon);
      const sunrise = times.sunrise;
      const sunset = times.sunset;
      if (!sunrise || !sunset || isNaN(sunrise.getTime()) || isNaN(sunset.getTime())) {
        return null;
      }
      const fmt = (d: Date) =>
        d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return { sunrise: fmt(sunrise), sunset: fmt(sunset) };
    } catch {
      return null;
    }
  }

  // ── Derived values ───────────────────────────────────────────────────────────

  $: bundle = appState.bundle;
  $: pos = appState.position;

  // Build an Eta instance from the bundle when it's loaded.
  $: eta = (() => {
    if (!bundle) return null;
    const origin = bundle.stations.find(s => s.sched_dep !== null);
    const depMs = origin?.sched_dep ? new Date(origin.sched_dep).getTime() : NaN;
    return new Eta(bundle, depMs);
  })();

  $: statusText = deriveStatus(bundle);

  $: isTripActual = bundle?.schedule_basis?.kind === 'trip-actual';

  // Next upcoming station (first station with mile > current mile)
  $: nextStation = (() => {
    if (!bundle || !pos) return null;
    return bundle.stations.find(s => s.mile > pos!.mile) ?? null;
  })();

  $: nextStationEta = (() => {
    if (!eta || !nextStation || !pos) return null;
    try {
      return eta.toStation(nextStation.code, pos);
    } catch {
      return null;
    }
  })();

  $: sun = pos ? getSunTimes(pos.lat, pos.lon) : null;

  // "near {place}" text — handle null place gracefully
  $: nearText = (() => {
    if (!pos) return null;
    if (!bundle || bundle.units.length === 0) return `mi ${pos.mile.toFixed(1)}`;
    const closest = bundle.units.reduce<{ place: string | null; delta: number }>(
      (best, u) => {
        const uMile = 'mile' in u ? u.mile : (u.from_mi + u.to_mi) / 2;
        const delta = Math.abs(uMile - pos!.mile);
        if (delta < best.delta && u.place !== null) return { place: u.place, delta };
        return best;
      },
      { place: null, delta: Infinity },
    );
    const placeStr = closest.place ?? '';
    const mileStr = `mi ${pos.mile.toFixed(1)}`;
    return placeStr ? `near ${placeStr}, ${mileStr}` : mileStr;
  })();
</script>

<div class="status-strip" role="status" aria-label="Train status">
  <!-- Status: on-time/late for trip-actual; neutral for generic -->
  <div
    class="status-strip__item"
    class:status-strip__item--good={statusText === 'On time'}
    class:status-strip__item--neutral={statusText === 'Estimated · scheduled'}
  >
    <span class="status-strip__label">Status</span>
    <span class="status-strip__value">{statusText}</span>
  </div>

  <!-- Next stop + ETA -->
  {#if nextStation}
    <div class="status-strip__item">
      <span class="status-strip__label">Next stop</span>
      <span class="status-strip__value status-strip__value--eta">
        {nextStation.name}
        {#if nextStationEta}
          ·
          {#if !nextStationEta.estimated}
            {formatEtaTripActual(nextStationEta)}
          {:else}
            {formatEtaGeneric(nextStationEta)}
          {/if}
        {/if}
      </span>
    </div>
  {/if}

  <!-- Sunrise/sunset from suncalc -->
  {#if sun}
    <div class="status-strip__item">
      <span class="status-strip__label">☀ Rise/Set</span>
      <span class="status-strip__value">{sun.sunrise} / {sun.sunset}</span>
    </div>
  {/if}

  <!-- Position: near {place}, mi {mile} -->
  {#if nearText}
    <div class="status-strip__item">
      <span class="status-strip__label">Location</span>
      <span class="status-strip__value">{nearText}</span>
    </div>
  {/if}
</div>

<style>
  .status-strip {
    display: flex;
    gap: 0;
    overflow-x: auto;
    scrollbar-width: none;
    background: #1a1a2e;
    color: #fff;
    padding: 8px 16px;
  }

  .status-strip::-webkit-scrollbar { display: none; }

  .status-strip__item {
    display: flex;
    flex-direction: column;
    min-width: 120px;
    padding-right: 20px;
    flex-shrink: 0;
  }

  .status-strip__label {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #9ca3af;
    margin-bottom: 2px;
  }

  .status-strip__value {
    font-size: 0.8125rem;
    font-weight: 600;
    color: #fff;
  }

  .status-strip__value--eta {
    color: #93c5fd;
  }

  .status-strip__item--good .status-strip__value {
    color: #4ade80;
  }

  .status-strip__item--neutral .status-strip__value {
    color: #d1d5db;
  }
</style>
