<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Favorite } from 'companion-core';
  import { hasDive } from './SavedList';

  export let favorite: Favorite;

  const dispatch = createEventDispatcher<{ select: Favorite }>();

  function truncate(text: string, max = 90): string {
    if (text.length <= max) return text;
    return text.slice(0, max).trimEnd() + '…';
  }

  function formatDate(ts: number): string {
    return new Date(ts).toLocaleDateString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  // ── Derived display values ────────────────────────────────────────────────────

  $: unit = favorite.unitSnapshot;
  $: place = unit.place ?? 'Unknown location';
  $: previewText = truncate(unit.text);
  $: notePreview = favorite.note ? truncate(favorite.note, 60) : null;
  $: dateStr = formatDate(favorite.createdAt);
  $: diveAvailable = hasDive(favorite);
  $: kindLabel = favorite.kind === 'star' ? '★' : 'Tell me more';
</script>

<!--
  SavedItem — single row in the Saved list.
  Shows place, truncated text, kind badge (★ or Tell me more), optional note
  preview, timestamp, and a "Deeper dive — available online (coming soon)"
  placeholder when the item was captured with Tell me more (Phase 2; no live dive).
-->
<div role="listitem" class="saved-item-wrapper">
<button
  class="saved-item"
  on:click={() => dispatch('select', favorite)}
  aria-label="Saved capture: {place}"
>
  <div class="saved-item__top">
    <span class="saved-item__place">{place}</span>
    <span
      class="saved-item__badge"
      class:saved-item__badge--star={favorite.kind === 'star'}
      class:saved-item__badge--tellmore={favorite.kind === 'tellmore'}
    >
      {kindLabel}
    </span>
  </div>

  <p class="saved-item__text">{previewText}</p>

  {#if notePreview}
    <p class="saved-item__note">"{notePreview}"</p>
  {/if}

  <div class="saved-item__footer">
    <span class="saved-item__date">{dateStr}</span>
    {#if diveAvailable}
      <!-- Phase 2: dive is attached and readable offline -->
      <span class="saved-item__dive-indicator" aria-label="Dive available">⬇ Dive available</span>
    {:else if favorite.kind === 'tellmore'}
      <!-- Phase 2 placeholder: no live dive yet -->
      <span class="saved-item__dive-placeholder">
        Deeper dive — available online (coming soon)
      </span>
    {/if}
  </div>
</button>
</div>

<style>
  .saved-item-wrapper {
    display: contents;
  }

  .saved-item {
    display: block;
    width: 100%;
    text-align: left;
    background: #fff;
    border: none;
    border-bottom: 1px solid #f0f0f0;
    padding: 16px 20px;
    cursor: pointer;
    transition: background 0.12s;
  }

  .saved-item:active { background: #f8f8ff; }

  .saved-item__top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
    gap: 8px;
  }

  .saved-item__place {
    font-size: 1rem;
    font-weight: 700;
    color: #1a1a2e;
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .saved-item__badge {
    font-size: 0.75rem;
    font-weight: 600;
    border-radius: 6px;
    padding: 2px 8px;
    flex-shrink: 0;
  }

  .saved-item__badge--star { background: #fef9c3; color: #92400e; }
  .saved-item__badge--tellmore { background: #ede9fe; color: #5b21b6; }

  .saved-item__text {
    font-size: 0.875rem;
    color: #444;
    margin: 0 0 6px;
    line-height: 1.45;
  }

  .saved-item__note {
    font-size: 0.8125rem;
    color: #666;
    font-style: italic;
    margin: 0 0 8px;
  }

  .saved-item__footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .saved-item__date {
    font-size: 0.75rem;
    color: #aaa;
    flex-shrink: 0;
  }

  .saved-item__dive-indicator {
    font-size: 0.75rem;
    color: #2563eb;
    font-weight: 600;
  }

  .saved-item__dive-placeholder {
    font-size: 0.7rem;
    color: #9ca3af;
    font-style: italic;
  }
</style>
