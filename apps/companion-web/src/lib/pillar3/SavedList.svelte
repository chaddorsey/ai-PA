<script lang="ts">
  import type { Favorite } from 'companion-core';
  import SavedItem from './SavedItem.svelte';
  import { sortFavorites } from './SavedList';

  // favorites: reactive list passed in from the page/appState
  export let favorites: Favorite[] = [];

  // Selected item for detail view
  let selectedFav: Favorite | null = null;

  $: sorted = sortFavorites(favorites);

  function handleSelect(fav: Favorite) {
    selectedFav = fav;
  }

  function handleClose() {
    selectedFav = null;
  }

  function fmtDate(ts: number): string {
    return new Date(ts).toLocaleString([], {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }
</script>

<!--
  SavedList — browse ★ and Tell-me-more captures, sorted newest first.
  Selecting an item shows the saved card + a Phase-2 dive placeholder.
  No live network call is made (dives are Phase 2).
-->
<div class="saved-list">
  {#if selectedFav !== null}
    <!-- Detail view: show the saved unit + Phase-2 dive placeholder -->
    <div class="saved-detail" role="region" aria-label="Saved detail">
      <button class="saved-detail__back" on:click={handleClose} aria-label="Back to saved list">
        ← Back
      </button>

      <div class="saved-detail__card">
        {#if selectedFav.unitSnapshot.theme}
          <span class="saved-detail__theme">{selectedFav.unitSnapshot.theme}</span>
        {/if}
        <h2 class="saved-detail__place">
          {selectedFav.unitSnapshot.place ?? 'Unknown location'}
        </h2>
        <p class="saved-detail__text">{selectedFav.unitSnapshot.text}</p>

        {#if selectedFav.note}
          <blockquote class="saved-detail__note">"{selectedFav.note}"</blockquote>
        {/if}

        <div class="saved-detail__meta">
          <span class="saved-detail__date">
            Saved {fmtDate(selectedFav.createdAt)}
          </span>
          <span
            class="saved-detail__kind-badge"
            class:saved-detail__kind-badge--star={selectedFav.kind === 'star'}
            class:saved-detail__kind-badge--tellmore={selectedFav.kind === 'tellmore'}
          >
            {selectedFav.kind === 'star' ? '★ Starred' : 'Tell me more'}
          </span>
        </div>

        <!-- Phase-2 dive placeholder — no live call, no FocusingDialog -->
        {#if selectedFav.kind === 'tellmore' && !selectedFav.dive}
          <div class="saved-detail__dive-placeholder" role="region" aria-label="Dive placeholder">
            <span class="saved-detail__dive-icon" aria-hidden="true">🔭</span>
            <p class="saved-detail__dive-heading">Deeper dive — available online (coming soon)</p>
            <p class="saved-detail__dive-hint">
              A detailed dive for this capture will be available in a future update
              when you have an internet connection.
            </p>
          </div>
        {:else if selectedFav.dive}
          <!-- Dive card: offline-readable (Phase 2 data model) -->
          <div class="saved-detail__dive-card">
            <h3 class="saved-detail__dive-title">Dive</h3>
            <p class="saved-detail__dive-body">{selectedFav.dive.body}</p>
            {#if selectedFav.dive.sources.length > 0}
              <ul class="saved-detail__dive-sources">
                {#each selectedFav.dive.sources as src}
                  <li><a href={src} target="_blank" rel="noopener noreferrer">{src}</a></li>
                {/each}
              </ul>
            {/if}
          </div>
        {/if}
      </div>
    </div>

  {:else}
    <!-- List view -->
    <div class="saved-list__header">
      <h1 class="saved-list__title">Saved</h1>
      <span class="saved-list__count">{sorted.length} capture{sorted.length !== 1 ? 's' : ''}</span>
    </div>

    <div class="saved-list__items" role="list" aria-label="Saved captures">
      {#if sorted.length === 0}
        <div class="saved-list__empty">
          <span class="saved-list__empty-icon" aria-hidden="true">★</span>
          <p class="saved-list__empty-text">No saved captures yet.</p>
          <p class="saved-list__empty-hint">
            Tap ★ or "Tell me more" while the companion is narrating.
          </p>
        </div>
      {:else}
        {#each sorted as fav (fav.id)}
          <SavedItem
            favorite={fav}
            on:select={(e) => handleSelect(e.detail)}
          />
        {/each}
      {/if}
    </div>
  {/if}
</div>

<style>
  .saved-list {
    height: 100%;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  .saved-list__header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 20px 20px 10px;
    border-bottom: 1px solid #f0f0f0;
  }

  .saved-list__title {
    font-size: 1.375rem;
    font-weight: 800;
    color: #1a1a2e;
    margin: 0;
  }

  .saved-list__count {
    font-size: 0.8125rem;
    color: #9ca3af;
  }

  .saved-list__items {
    flex: 1;
    overflow-y: auto;
    padding-bottom: 80px;
  }

  .saved-list__empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 64px 24px;
    gap: 8px;
    text-align: center;
  }

  .saved-list__empty-icon { font-size: 2rem; color: #fbbf24; }

  .saved-list__empty-text {
    font-size: 1rem;
    font-weight: 600;
    color: #555;
    margin: 0;
  }

  .saved-list__empty-hint {
    font-size: 0.875rem;
    color: #aaa;
    margin: 0;
    line-height: 1.5;
  }

  /* Detail view */
  .saved-detail {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow-y: auto;
  }

  .saved-detail__back {
    background: none;
    border: none;
    color: #2563eb;
    font-size: 0.9375rem;
    font-weight: 600;
    padding: 16px 20px 8px;
    cursor: pointer;
    text-align: left;
    align-self: flex-start;
  }

  .saved-detail__card {
    padding: 8px 20px 80px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .saved-detail__theme {
    display: inline-block;
    background: #eff6ff;
    color: #1d4ed8;
    border-radius: 6px;
    padding: 2px 10px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: capitalize;
    align-self: flex-start;
  }

  .saved-detail__place {
    font-size: 1.375rem;
    font-weight: 800;
    color: #1a1a2e;
    margin: 0;
  }

  .saved-detail__text {
    font-size: 1rem;
    color: #333;
    line-height: 1.65;
    margin: 0;
  }

  .saved-detail__note {
    font-size: 0.9375rem;
    color: #555;
    font-style: italic;
    margin: 0;
    border-left: 3px solid #e5e7eb;
    padding: 4px 0 4px 12px;
  }

  .saved-detail__meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .saved-detail__date { font-size: 0.75rem; color: #9ca3af; }

  .saved-detail__kind-badge {
    font-size: 0.75rem;
    font-weight: 600;
    border-radius: 6px;
    padding: 2px 8px;
  }

  .saved-detail__kind-badge--star { background: #fef9c3; color: #92400e; }
  .saved-detail__kind-badge--tellmore { background: #ede9fe; color: #5b21b6; }

  /* Phase-2 dive placeholder */
  .saved-detail__dive-placeholder {
    background: #f8fafc;
    border: 1.5px dashed #cbd5e1;
    border-radius: 12px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    text-align: center;
  }

  .saved-detail__dive-icon { font-size: 1.75rem; }

  .saved-detail__dive-heading {
    font-size: 0.9375rem;
    font-weight: 700;
    color: #475569;
    margin: 0;
  }

  .saved-detail__dive-hint {
    font-size: 0.8125rem;
    color: #94a3b8;
    margin: 0;
    line-height: 1.5;
  }

  /* Offline dive card (Phase 2 — when dive is attached) */
  .saved-detail__dive-card {
    background: #f0f9ff;
    border-radius: 12px;
    padding: 16px;
  }

  .saved-detail__dive-title {
    font-size: 0.875rem;
    font-weight: 700;
    color: #0369a1;
    margin: 0 0 8px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .saved-detail__dive-body {
    font-size: 0.9375rem;
    color: #1e3a5f;
    line-height: 1.6;
    margin: 0 0 10px;
  }

  .saved-detail__dive-sources {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .saved-detail__dive-sources a {
    font-size: 0.75rem;
    color: #2563eb;
    text-decoration: underline;
    word-break: break-all;
  }
</style>
