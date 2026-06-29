<script lang="ts">
  import type { Unit, Bundle, BundleLayers } from 'companion-core';

  export let unit: Unit;
  export let bundle: Bundle | null = null;

  // ── POI image ────────────────────────────────────────────────────────────────
  // Convention: if unit has poi_lat/poi_lon, look for an image at
  // <bundleAudioDir>/../images/<unit.id>-poi.jpg (graceful if missing).
  $: hasPoi = unit.poi_lat !== undefined && unit.poi_lon !== undefined;

  // Derive the base from the audio path ("audio/hash.mp3" → base = "audio/")
  $: poiImageSrc = (() => {
    if (!hasPoi) return null;
    const audioDir = unit.audio.split('/').slice(0, -1).join('/') || 'audio';
    return `${audioDir}/../images/${unit.id}-poi.jpg`;
  })();

  // ── Lore from bundle layers ──────────────────────────────────────────────────
  $: loreSummary = (() => {
    if (!bundle || !unit.place) return '';
    const lore = (bundle.layers as BundleLayers & { lore: Record<string, { summary?: string }> }).lore;
    if (!lore || typeof lore !== 'object') return '';
    const entry = (lore as Record<string, { summary?: string }>)[unit.place] ?? null;
    return entry?.summary ?? '';
  })();

  // ── Mile info (squib vs interstitial) ───────────────────────────────────────
  $: mileLabel = (() => {
    if (unit.kind === 'squib') return `Mile ${unit.mile.toFixed(1)}`;
    return `Mile ${unit.from_mi.toFixed(1)}–${unit.to_mi.toFixed(1)}`;
  })();

  // ── Side label ───────────────────────────────────────────────────────────────
  $: sideLabel = (() => {
    if (!unit.side) return null;
    const map: Record<string, string> = {
      left: 'Left side',
      right: 'Right side',
      both: 'Both sides',
      ahead: 'Ahead',
    };
    return map[unit.side] ?? null;
  })();
</script>

<!--
  StoryCard — deeper readable card for a unit.
  Shows the unit text, optional POI image (graceful on error), lore summary,
  mile and side metadata. Appears inside CompanionView for the current now-playing unit.
-->
<div class="story-card" aria-label="Story: {unit.place ?? 'Unknown location'}">
  <!-- POI image: graceful if missing (onerror hides it) -->
  {#if poiImageSrc}
    <img
      class="story-card__image"
      src={poiImageSrc}
      alt="Historical view of {unit.place ?? 'this location'}"
      loading="lazy"
      on:error={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
    />
  {/if}

  <div class="story-card__body">
    {#if unit.theme}
      <span class="story-card__theme">{unit.theme}</span>
    {/if}
    {#if loreSummary}
      <blockquote class="story-card__lore">{loreSummary}</blockquote>
    {/if}
    <div class="story-card__meta">
      <span class="story-card__mile">{mileLabel}</span>
      {#if sideLabel}
        <span class="story-card__side">{sideLabel}</span>
      {/if}
    </div>
  </div>
</div>

<style>
  .story-card {
    background: #f9fafb;
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid #e5e7eb;
    margin-top: 4px;
  }

  .story-card__image {
    width: 100%;
    height: 180px;
    object-fit: cover;
    display: block;
  }

  .story-card__body {
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .story-card__theme {
    display: inline-block;
    background: #eff6ff;
    color: #1d4ed8;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: capitalize;
    align-self: flex-start;
  }

  .story-card__lore {
    font-size: 0.875rem;
    color: #555;
    font-style: italic;
    margin: 0;
    line-height: 1.55;
    border-left: 3px solid #e5e7eb;
    padding: 0 0 0 10px;
  }

  .story-card__meta {
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .story-card__mile,
  .story-card__side {
    font-size: 0.75rem;
    color: #9ca3af;
    font-weight: 500;
  }
</style>
