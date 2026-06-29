<script lang="ts">
  import { marked } from 'marked';
  import type { DeepDive } from 'companion-core';
  import { appState } from '$lib/core/AppState.svelte';
  import { getOrchestrator } from '$lib/core/PlaybackOrchestrator';

  // ── Props ────────────────────────────────────────────────────────────────────

  interface Props {
    deepdive: DeepDive;
    onClose?: () => void;
  }

  let { deepdive, onClose }: Props = $props();

  // ── Theme gradient map ────────────────────────────────────────────────────────
  // Each theme maps to a gradient fallback when no hero image is available.

  const THEME_GRADIENTS: Record<string, string> = {
    'Corridor of Movement': 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
    'Written in Silt':      'linear-gradient(135deg, #3d2b1f 0%, #5c3d2e 50%, #7a5c3f 100%)',
    "The Migration's Spine": 'linear-gradient(135deg, #1a2e1a 0%, #2e4a2e 50%, #1f3a2a 100%)',
    'Haunted Ground':       'linear-gradient(135deg, #2a1a2e 0%, #3d2440 50%, #4a2a3f 100%)',
  };

  const DEFAULT_GRADIENT = 'linear-gradient(135deg, #1a1a2e 0%, #374151 100%)';

  function heroGradient(theme: string): string {
    return THEME_GRADIENTS[theme] ?? DEFAULT_GRADIENT;
  }

  // ── Markdown rendering ────────────────────────────────────────────────────────

  let bodyHtml = $derived(marked.parse(deepdive.body_md) as string);

  // ── Read/listen state ─────────────────────────────────────────────────────────

  let isRead = $state(false);
  let isListened = $state(false);

  function handleMarkRead() {
    isRead = true;
  }

  async function handleListen() {
    if (!deepdive.audio) return;
    const orch = getOrchestrator();
    if (!orch) return;
    // Silence regular narration and play deep-dive audio
    orch.silence(deepdive.mile + 5);
    // Play audio directly via the audio session plugin
    const { AudioSession } = await import('$lib/native/plugins');
    await AudioSession.play(deepdive.audio);
    isListened = true;
  }

  async function handleStar() {
    // Favorites for deep-dives: store as a note in the favorites list.
    // Since DeepDive is not a Unit, we piggyback via a minimal squib-shaped record.
    // This is best-effort; the favorites system is primarily for regular units.
    // Future: first-class DeepDive favorites path.
    const fav = appState.favorites;
    const pos = appState.position;
    if (!pos || !appState.bundle) return;
    // Create a synthetic squib unit representing the deep-dive so we can store it.
    const syntheticUnit = {
      id: deepdive.id,
      kind: 'squib' as const,
      mile: deepdive.mile,
      place: deepdive.nearest_place,
      side: null as null,
      salience: deepdive.salience as 1 | 2 | 3 | 4 | 5,
      theme: deepdive.theme,
      text: deepdive.hook,
      lat: pos.lat,
      lon: pos.lon,
      audio: deepdive.audio ?? '',
      dur_s: deepdive.est_listen_min * 60,
    };
    await fav.add(syntheticUnit, appState.bundle.leg, pos, 'star', `Deep-dive: ${deepdive.title}`);
    starred = true;
  }

  let starred = $state(false);
</script>

<!-- FeaturedCard: full-screen scrollable reading/listening view -->
<div class="featured-card" role="article" aria-label={deepdive.title}>
  <!-- Header: hero image or theme gradient -->
  <div
    class="featured-card__hero"
    style={deepdive.images.length > 0
      ? `background-image: url(${deepdive.images[0].url}); background-size: cover; background-position: center;`
      : `background: ${heroGradient(deepdive.theme)};`}
    aria-hidden="true"
  >
    <!-- Close button -->
    {#if onClose}
      <button class="featured-card__close" onclick={onClose} aria-label="Close story">
        ✕
      </button>
    {/if}
    <!-- Theme chip overlaid on hero -->
    <div class="featured-card__hero-overlay">
      <span class="featured-card__theme-chip">{deepdive.theme}</span>
      <span class="featured-card__mile">mi {deepdive.mile}</span>
    </div>
  </div>

  <!-- Hero image credit (shown only when image present) -->
  {#if deepdive.images.length > 0}
    <p class="featured-card__hero-credit">
      {deepdive.images[0].caption}
      {#if deepdive.images[0].credit}
        · <span class="featured-card__hero-credit-author">{deepdive.images[0].credit}</span>
      {/if}
    </p>
  {/if}

  <!-- Title + hook -->
  <div class="featured-card__header">
    <h1 class="featured-card__title">{deepdive.title}</h1>
    <p class="featured-card__hook">{deepdive.hook}</p>
  </div>

  <!-- Action bar -->
  <div class="featured-card__actions">
    <!-- Listen button -->
    {#if deepdive.audio}
      <button
        class="featured-card__btn featured-card__btn--listen"
        onclick={handleListen}
        aria-label="Listen to {deepdive.title}"
      >
        🎧 Listen · {deepdive.est_listen_min} min
      </button>
    {:else}
      <button
        class="featured-card__btn featured-card__btn--listen featured-card__btn--disabled"
        disabled
        aria-label="Audio coming soon"
        aria-disabled="true"
      >
        🎧 Audio coming soon
      </button>
    {/if}

    <!-- Star / favorite -->
    <button
      class="featured-card__btn featured-card__btn--icon"
      class:featured-card__btn--starred={starred}
      onclick={handleStar}
      aria-label={starred ? 'Saved' : 'Save story'}
      aria-pressed={starred}
    >
      {starred ? '★' : '☆'}
    </button>

    <!-- Mark read -->
    {#if !isRead}
      <button
        class="featured-card__btn featured-card__btn--secondary"
        onclick={handleMarkRead}
        aria-label="Mark as read"
      >
        ✓ Mark read
      </button>
    {:else}
      <span class="featured-card__read-badge" aria-label="Read">✓ Read</span>
    {/if}
  </div>

  <!-- Body: markdown-rendered long-form text -->
  <div class="featured-card__body prose">
    <!-- eslint-disable-next-line svelte/no-at-html-tags -->
    {@html bodyHtml}
  </div>

  <!-- Inline images (skip first which is the hero) -->
  {#if deepdive.images.length > 1}
    <div class="featured-card__inline-images">
      {#each deepdive.images.slice(1) as img}
        <figure class="featured-card__figure">
          <img
            src={img.url}
            alt={img.caption}
            class="featured-card__inline-img"
            loading="lazy"
          />
          <figcaption class="featured-card__figcaption">
            {img.caption}
            {#if img.credit}
              · <cite>{img.credit}</cite>
            {/if}
          </figcaption>
        </figure>
      {/each}
    </div>
  {/if}

  <!-- Sources footer -->
  {#if deepdive.sources.length > 0}
    <footer class="featured-card__sources">
      <h2 class="featured-card__sources-heading">Sources</h2>
      <ul class="featured-card__sources-list">
        {#each deepdive.sources as src}
          <li>
            <a
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              class="featured-card__source-link"
            >
              {src.title}
            </a>
          </li>
        {/each}
      </ul>
    </footer>
  {/if}
</div>

<style>
  .featured-card {
    overflow-y: auto;
    height: 100%;
    background: #fff;
    display: flex;
    flex-direction: column;
  }

  /* ── Hero ──────────────────────────────────────────────────────────────── */
  .featured-card__hero {
    position: relative;
    width: 100%;
    height: 220px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
  }

  .featured-card__close {
    position: absolute;
    top: 12px;
    right: 12px;
    background: rgba(0, 0, 0, 0.45);
    border: none;
    border-radius: 50%;
    color: #fff;
    font-size: 1rem;
    width: 34px;
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    line-height: 1;
  }

  .featured-card__hero-overlay {
    padding: 12px 16px;
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .featured-card__theme-chip {
    background: rgba(255, 255, 255, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.35);
    color: #fff;
    font-size: 0.6875rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 3px 8px;
    border-radius: 12px;
    backdrop-filter: blur(4px);
  }

  .featured-card__mile {
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.75);
    font-weight: 600;
  }

  /* ── Hero credit ────────────────────────────────────────────────────────── */
  .featured-card__hero-credit {
    font-size: 0.6875rem;
    color: #9ca3af;
    padding: 4px 16px 0;
    margin: 0;
    line-height: 1.4;
  }

  .featured-card__hero-credit-author { font-style: italic; }

  /* ── Header ─────────────────────────────────────────────────────────────── */
  .featured-card__header {
    padding: 20px 20px 0;
  }

  .featured-card__title {
    font-size: 1.625rem;
    font-weight: 900;
    color: #1a1a2e;
    line-height: 1.2;
    margin: 0 0 10px;
  }

  .featured-card__hook {
    font-size: 1.0625rem;
    color: #4b5563;
    line-height: 1.55;
    margin: 0;
    font-style: italic;
  }

  /* ── Actions ────────────────────────────────────────────────────────────── */
  .featured-card__actions {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 16px 20px;
    flex-wrap: wrap;
  }

  .featured-card__btn {
    border: none;
    border-radius: 10px;
    font-size: 0.9375rem;
    font-weight: 700;
    font-family: inherit;
    cursor: pointer;
    padding: 10px 18px;
    transition: opacity 0.12s;
  }

  .featured-card__btn:active { opacity: 0.8; }

  .featured-card__btn--listen {
    background: #2563eb;
    color: #fff;
    flex: 1;
    min-width: 0;
  }

  .featured-card__btn--disabled {
    background: #e5e7eb;
    color: #9ca3af;
    cursor: default;
  }

  .featured-card__btn--icon {
    background: #f9fafb;
    border: 1.5px solid #e5e7eb;
    color: #6b7280;
    font-size: 1.25rem;
    padding: 8px 14px;
    flex-shrink: 0;
  }

  .featured-card__btn--starred {
    color: #fbbf24;
    border-color: #fbbf24;
  }

  .featured-card__btn--secondary {
    background: #f3f4f6;
    color: #374151;
    font-size: 0.875rem;
    padding: 9px 14px;
    flex-shrink: 0;
  }

  .featured-card__read-badge {
    font-size: 0.875rem;
    font-weight: 700;
    color: #16a34a;
    padding: 9px 4px;
    flex-shrink: 0;
  }

  /* ── Body (markdown prose) ──────────────────────────────────────────────── */
  .featured-card__body {
    padding: 4px 20px 24px;
    flex: 1;
  }

  /* Prose styles — applied via :global because marked generates plain HTML */
  :global(.featured-card__body h1),
  :global(.featured-card__body h2),
  :global(.featured-card__body h3) {
    font-size: 1.125rem;
    font-weight: 800;
    color: #1a1a2e;
    margin: 20px 0 8px;
    line-height: 1.3;
  }

  :global(.featured-card__body p) {
    font-size: 1.25rem;
    line-height: 1.7;
    color: #1f2937;
    margin: 0 0 16px;
  }

  :global(.featured-card__body em) { font-style: italic; }
  :global(.featured-card__body strong) { font-weight: 700; }

  :global(.featured-card__body a) {
    color: #2563eb;
    text-decoration: underline;
  }

  /* ── Inline images ──────────────────────────────────────────────────────── */
  .featured-card__inline-images {
    padding: 0 20px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .featured-card__figure {
    margin: 0;
  }

  .featured-card__inline-img {
    width: 100%;
    border-radius: 10px;
    display: block;
  }

  .featured-card__figcaption {
    font-size: 0.75rem;
    color: #9ca3af;
    margin-top: 6px;
    line-height: 1.4;
  }

  /* ── Sources footer ─────────────────────────────────────────────────────── */
  .featured-card__sources {
    padding: 20px 20px 80px; /* bottom padding for tab nav */
    border-top: 1px solid #f3f4f6;
    margin-top: 12px;
  }

  .featured-card__sources-heading {
    font-size: 0.8125rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #888;
    font-weight: 700;
    margin: 0 0 10px;
  }

  .featured-card__sources-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 0;
    margin: 0;
  }

  .featured-card__source-link {
    font-size: 0.875rem;
    color: #2563eb;
    text-decoration: underline;
    word-break: break-all;
  }
</style>
