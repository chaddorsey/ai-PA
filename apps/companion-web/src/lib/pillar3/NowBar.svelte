<script lang="ts">
  import { goto } from '$app/navigation';
  import { appState } from '$lib/core/AppState.svelte';
  import { getOrchestrator } from '$lib/core/PlaybackOrchestrator';

  // ── Pause/resume local state ─────────────────────────────────────────────────

  let paused = false;

  function handlePauseResume() {
    const orch = getOrchestrator();
    if (!orch) return;
    if (paused) {
      void orch.resume();
      paused = false;
    } else {
      void orch.pause();
      paused = true;
    }
  }

  async function handleStar() {
    const orch = getOrchestrator();
    const unit = appState.nowPlaying;
    if (!orch || !unit) return;
    await orch.capture(unit, 'star');
  }

  function handleBarTap() {
    void goto('/companion');
  }

  function placeLabel(unit: typeof appState.nowPlaying): string {
    if (!unit) return '';
    if (unit.place) return unit.place;
    // null place (many interstitials/squibs) → lead with the theme instead of "Unknown location"
    return unit.theme ? unit.theme.charAt(0).toUpperCase() + unit.theme.slice(1) : 'On the route';
  }
</script>

<!--
  NowBar — persistent top strip.
  Shows now-playing place or "Quiet · next soon" when idle.
  ★ button → orchestrator.capture(nowPlaying, 'star')
  ⏸/▶ → pause/resume toggle
  Tap bar → goto('/companion')
-->
<aside class="now-bar" aria-label="Now playing">
  <button
    class="now-bar__content"
    onclick={handleBarTap}
    aria-label="Open companion view"
  >
    {#if appState.nowPlaying}
      <span class="now-bar__icon" aria-hidden="true">🎧</span>
      <span class="now-bar__place">{placeLabel(appState.nowPlaying)}</span>
      <span class="now-bar__text-preview">
        {appState.nowPlaying.text.length > 52
          ? appState.nowPlaying.text.slice(0, 52) + '…'
          : appState.nowPlaying.text}
      </span>
    {:else}
      <span class="now-bar__icon" aria-hidden="true">🎧</span>
      <span class="now-bar__idle">Quiet · next soon</span>
    {/if}
  </button>

  {#if appState.nowPlaying}
    <div class="now-bar__controls">
      <button
        class="now-bar__btn"
        onclick={(e) => { e.stopPropagation(); handlePauseResume(); }}
        aria-label={paused ? 'Resume' : 'Pause'}
        aria-pressed={paused}
      >
        {paused ? '▶' : '⏸'}
      </button>
      <button
        class="now-bar__btn now-bar__btn--star"
        onclick={(e) => { e.stopPropagation(); void handleStar(); }}
        aria-label="Star"
      >
        ★
      </button>
    </div>
  {/if}
</aside>

<style>
  .now-bar {
    display: flex;
    align-items: center;
    background: #1a1a2e;
    color: #fff;
    padding: env(safe-area-inset-top) 12px 0;
    height: calc(52px + env(safe-area-inset-top));
    flex-shrink: 0;
    gap: 8px;
    position: relative;
    z-index: 10;
  }

  .now-bar__content {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    text-align: left;
    padding: 0;
  }

  .now-bar__icon { font-size: 1.125rem; flex-shrink: 0; }

  .now-bar__place {
    font-size: 0.875rem;
    font-weight: 700;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 0;
    max-width: 130px;
  }

  .now-bar__text-preview {
    font-size: 0.75rem;
    color: #9ca3af;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .now-bar__idle {
    font-size: 0.875rem;
    color: #9ca3af;
    font-weight: 500;
  }

  .now-bar__controls {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
  }

  .now-bar__btn {
    background: rgba(255, 255, 255, 0.1);
    border: none;
    border-radius: 8px;
    color: #fff;
    font-size: 1.125rem;
    width: 38px;
    height: 38px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background 0.12s;
  }

  .now-bar__btn:active { background: rgba(255, 255, 255, 0.22); }

  .now-bar__btn--star { color: #fbbf24; }
</style>
