<script lang="ts">
  /**
   * CalloutCard.svelte — Map callout card shown when a station pin or POI is tapped.
   *
   * Handles nullable place/theme fields gracefully (they may be null per Plan 0 types).
   */
  import type { Unit } from 'companion-core';

  // ── Props ───────────────────────────────────────────────────────────────────

  let { unit, onDismiss }: {
    unit: Unit;
    onDismiss: () => void;
  } = $props();

  // ── Derived ─────────────────────────────────────────────────────────────────

  // place and theme are nullable per the corrected contract
  const placeName = $derived(unit.place ?? 'Unknown location');
  const themeName = $derived(unit.theme ?? null);
</script>

<div
  class="callout-card"
  role="dialog"
  aria-label="Point of interest: {placeName}"
  aria-modal="true"
>
  <button
    class="callout-card__close"
    onclick={onDismiss}
    aria-label="Close"
  >
    ✕
  </button>

  <h3 class="callout-card__place">{placeName}</h3>
  <p class="callout-card__text">{unit.text}</p>

  {#if themeName}
    <span class="callout-card__theme">{themeName}</span>
  {/if}
</div>

<style>
  .callout-card {
    position: absolute;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    background: #fff;
    border-radius: 14px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    padding: 16px 20px;
    max-width: 320px;
    width: calc(100vw - 48px);
    z-index: 50;
  }

  .callout-card__close {
    position: absolute;
    top: 10px;
    right: 12px;
    background: none;
    border: none;
    color: #888;
    font-size: 1.1rem;
    cursor: pointer;
    padding: 4px;
    line-height: 1;
  }

  .callout-card__place {
    font-size: 1rem;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0 28px 8px 0;
  }

  .callout-card__text {
    font-size: 0.875rem;
    color: #444;
    margin: 0 0 8px;
    line-height: 1.45;
  }

  .callout-card__theme {
    display: inline-block;
    background: #eff6ff;
    color: #1d4ed8;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: capitalize;
  }
</style>
