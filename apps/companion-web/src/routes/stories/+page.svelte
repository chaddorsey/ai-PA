<script lang="ts">
  import type { DeepDive } from 'companion-core';
  import { appState } from '$lib/core/AppState.svelte';
  import FeaturedCard from '$lib/deepdive/FeaturedCard.svelte';
  import { deepdiveState } from '$lib/deepdive/deepdiveState.svelte';

  // ── Theme gradient map (matches FeaturedCard) ─────────────────────────────────

  const THEME_GRADIENTS: Record<string, string> = {
    'Corridor of Movement': 'linear-gradient(135deg, #1a1a2e, #0f3460)',
    'Written in Silt':      'linear-gradient(135deg, #3d2b1f, #7a5c3f)',
    "The Migration's Spine": 'linear-gradient(135deg, #1a2e1a, #1f3a2a)',
  };

  const DEFAULT_GRADIENT = 'linear-gradient(135deg, #1a1a2e, #374151)';

  function thumbGradient(theme: string): string {
    return THEME_GRADIENTS[theme] ?? DEFAULT_GRADIENT;
  }

  // ── Selected deep-dive for full-screen reading ────────────────────────────────

  let selectedDive = $state<DeepDive | null>(null);

  function openDive(dd: DeepDive) {
    selectedDive = dd;
  }

  function closeDive() {
    selectedDive = null;
  }

  // ── Nearest deep-dive to current position ─────────────────────────────────────

  let nearestId = $derived.by(() => {
    const pos = appState.position;
    const dives = appState.bundle?.deepdives;
    if (!pos || !dives || dives.length === 0) return null;
    let best: DeepDive | null = null;
    let bestDist = Infinity;
    for (const dd of dives) {
      const dist = Math.abs(dd.mile - pos.mile);
      if (dist < bestDist) {
        bestDist = dist;
        best = dd;
      }
    }
    return best?.id ?? null;
  });

  // ── Deep dives list ───────────────────────────────────────────────────────────

  let deepdives = $derived(appState.bundle?.deepdives ?? []);
</script>

<!-- Full-screen card view when a story is selected -->
{#if selectedDive}
  <div class="stories-fullscreen">
    <FeaturedCard deepdive={selectedDive} onClose={closeDive} />
  </div>
{:else}
  <!-- Stories list view -->
  <div class="stories-view">
    <h1 class="stories-view__title">Featured Stories</h1>

    {#if deepdives.length === 0}
      <!-- Empty state -->
      <div class="stories-empty" role="status">
        <span class="stories-empty__icon" aria-hidden="true">📖</span>
        <p class="stories-empty__message">No featured stories for this leg yet.</p>
        <p class="stories-empty__hint">Stories are added as the route is enriched.</p>
      </div>
    {:else}
      <p class="stories-view__description">
        Extended stories along the route — read anytime, listen when one is near.
      </p>
      <ul class="stories-list" aria-label="Featured stories">
        {#each deepdives as dd (dd.id)}
          {@const isNearest = nearestId === dd.id}
          {@const isRead = deepdiveState.isRead(dd.id)}
          {@const isListened = deepdiveState.isListened(dd.id)}
          <li
            class="stories-item"
            class:stories-item--nearest={isNearest}
          >
            <button
              class="stories-item__btn"
              onclick={() => openDive(dd)}
              aria-label="Open story: {dd.title}"
            >
              <!-- Thumbnail: image or gradient -->
              <div
                class="stories-item__thumb"
                style={dd.images.length > 0
                  ? `background-image: url(${dd.images[0].url}); background-size: cover; background-position: center;`
                  : `background: ${thumbGradient(dd.theme)};`}
                aria-hidden="true"
              ></div>

              <!-- Content -->
              <div class="stories-item__content">
                <div class="stories-item__meta">
                  <span class="stories-item__theme-chip">{dd.theme}</span>
                  <span class="stories-item__mile">mi {dd.mile}</span>
                  {#if isNearest}
                    <span class="stories-item__now-near" aria-label="Near your current position">
                      Now near you
                    </span>
                  {/if}
                </div>
                <h2 class="stories-item__title">{dd.title}</h2>
                <p class="stories-item__hook">{dd.hook}</p>
                <div class="stories-item__badges">
                  {#if isRead}
                    <span class="stories-item__badge stories-item__badge--read" aria-label="Read">
                      ✓ Read
                    </span>
                  {/if}
                  {#if isListened}
                    <span class="stories-item__badge stories-item__badge--listened" aria-label="Listened">
                      🎧 Listened
                    </span>
                  {/if}
                  {#if !isRead && !isListened && dd.audio === null}
                    <span class="stories-item__badge stories-item__badge--no-audio" aria-label="Audio coming soon">
                      Read only
                    </span>
                  {/if}
                </div>
              </div>

              <span class="stories-item__chevron" aria-hidden="true">›</span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}

<style>
  /* ── Full-screen overlay ─────────────────────────────────────────────────── */
  .stories-fullscreen {
    position: absolute;
    inset: 0;
    z-index: 50;
    background: #fff;
    overflow: hidden;
  }

  /* ── List view ──────────────────────────────────────────────────────────── */
  .stories-view {
    padding: 24px 20px 100px;
    overflow-y: auto;
    height: 100%;
    box-sizing: border-box;
  }

  .stories-view__title {
    font-size: 1.5rem;
    font-weight: 800;
    color: #1a1a2e;
    margin: 0 0 6px;
  }

  .stories-view__description {
    font-size: 0.875rem;
    color: #9ca3af;
    margin: 0 0 20px;
    line-height: 1.4;
  }

  /* ── Empty state ──────────────────────────────────────────────────────────── */
  .stories-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 60%;
    gap: 10px;
    text-align: center;
  }

  .stories-empty__icon {
    font-size: 2.5rem;
  }

  .stories-empty__message {
    font-size: 1.125rem;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0;
  }

  .stories-empty__hint {
    font-size: 0.875rem;
    color: #9ca3af;
    margin: 0;
  }

  /* ── Stories list ─────────────────────────────────────────────────────────── */
  .stories-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .stories-item {
    border-radius: 14px;
    background: #fff;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
    overflow: hidden;
    transition: box-shadow 0.15s;
  }

  .stories-item--nearest {
    box-shadow: 0 0 0 2.5px #2563eb, 0 2px 8px rgba(37, 99, 235, 0.18);
  }

  .stories-item__btn {
    display: flex;
    align-items: stretch;
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    padding: 0;
    gap: 0;
  }

  /* ── Thumbnail ──────────────────────────────────────────────────────────── */
  .stories-item__thumb {
    width: 90px;
    flex-shrink: 0;
    min-height: 100px;
    border-radius: 0;
  }

  /* ── Content ────────────────────────────────────────────────────────────── */
  .stories-item__content {
    flex: 1;
    min-width: 0;
    padding: 12px 12px 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .stories-item__meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .stories-item__theme-chip {
    font-size: 0.625rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #2563eb;
    background: #eff6ff;
    border-radius: 8px;
    padding: 2px 7px;
  }

  .stories-item__mile {
    font-size: 0.6875rem;
    color: #9ca3af;
    font-weight: 600;
  }

  .stories-item__now-near {
    font-size: 0.6875rem;
    color: #16a34a;
    font-weight: 700;
    background: #f0fdf4;
    border-radius: 8px;
    padding: 2px 7px;
  }

  .stories-item__title {
    font-size: 1rem;
    font-weight: 800;
    color: #1a1a2e;
    margin: 0;
    line-height: 1.25;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .stories-item__hook {
    font-size: 0.8125rem;
    color: #6b7280;
    margin: 0;
    line-height: 1.45;
    /* 2-line clamp */
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
  }

  .stories-item__badges {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 2px;
  }

  .stories-item__badge {
    font-size: 0.6875rem;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 8px;
  }

  .stories-item__badge--read    { background: #f0fdf4; color: #16a34a; }
  .stories-item__badge--listened { background: #eff6ff; color: #2563eb; }
  .stories-item__badge--no-audio { background: #f9fafb; color: #9ca3af; }

  /* ── Chevron ────────────────────────────────────────────────────────────── */
  .stories-item__chevron {
    font-size: 1.5rem;
    color: #d1d5db;
    display: flex;
    align-items: center;
    padding-right: 12px;
    flex-shrink: 0;
  }
</style>
