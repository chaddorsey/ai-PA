<script lang="ts">
  import { appState } from '$lib/core/AppState.svelte';
  import { getOrchestrator } from '$lib/core/PlaybackOrchestrator';
  import StoryCard from './StoryCard.svelte';

  // ── Local state ───────────────────────────────────────────────────────────────

  let note = '';
  let paused = false;
  let captureConfirmed = false;

  // ── Control handlers ─────────────────────────────────────────────────────────

  function handlePause() {
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

  async function handleSkip() {
    const orch = getOrchestrator();
    if (!orch) return;
    await orch.skip();
  }

  function handleSilence() {
    const orch = getOrchestrator();
    if (!orch) return;
    const mile = appState.position?.mile ?? 0;
    orch.silence(mile + 5);
  }

  async function handleStar() {
    const orch = getOrchestrator();
    const unit = appState.nowPlaying;
    if (!orch || !unit) return;
    const noteVal = note.trim() || undefined;
    await orch.capture(unit, 'star', noteVal);
    note = '';
    captureConfirmed = true;
    setTimeout(() => { captureConfirmed = false; }, 1500);
  }

  async function handleTellMore() {
    const orch = getOrchestrator();
    const unit = appState.nowPlaying;
    if (!orch || !unit) return;
    const noteVal = note.trim() || undefined;
    await orch.capture(unit, 'tellmore', noteVal);
    note = '';
    captureConfirmed = true;
    setTimeout(() => { captureConfirmed = false; }, 1500);
  }

  // ── Settings handlers ────────────────────────────────────────────────────────

  function onFillChange(event: Event) {
    const target = event.target as HTMLInputElement;
    appState.settings.fillPct = parseFloat(target.value);
  }

  function onThemeToggle(theme: string) {
    const themes = appState.settings.themes;
    if (themes.has(theme)) {
      themes.delete(theme);
    } else {
      themes.add(theme);
    }
    // Trigger reactivity by reassigning (Svelte 4 reactive $: picks up mutation)
    appState.settings.themes = new Set(themes);
  }

  function onHighlightToggle() {
    appState.settings.highlightOnly = !appState.settings.highlightOnly;
  }

  // ── Constants ────────────────────────────────────────────────────────────────

  const AVAILABLE_THEMES = ['history', 'geology', 'lore', 'science', 'connections', 'culture'] as const;
</script>

<!--
  CompanionView — full companion pillar.
  Shows now-playing unit text, controls (pause/skip/silence/★/Tell me more),
  fill slider, theme filter, highlight toggle, and StoryCard.
-->
<div class="companion-view">
  {#if appState.nowPlaying}
    {@const unit = appState.nowPlaying}

    <!-- Now-playing content -->
    <div class="companion-view__now-playing">
      {#if unit.theme}
        <span class="companion-view__theme-badge">{unit.theme}</span>
      {/if}
      <h2 class="companion-view__place">
        {unit.place ?? 'Unknown location'}
      </h2>
      <p class="companion-view__text">{unit.text}</p>

      <!-- StoryCard: shows lore/image for squib units -->
      <StoryCard {unit} bundle={appState.bundle} />
    </div>

    <!-- Playback controls -->
    <div class="companion-view__controls" role="group" aria-label="Playback controls">
      <button
        class="companion-view__btn companion-view__btn--pause"
        on:click={handlePause}
        aria-label={paused ? 'Resume' : 'Pause'}
        aria-pressed={paused}
      >
        {paused ? '▶' : '⏸'}
      </button>
      <button
        class="companion-view__btn"
        on:click={handleSkip}
        aria-label="Skip"
      >
        ⏭
      </button>
      <button
        class="companion-view__btn companion-view__btn--silence"
        on:click={handleSilence}
        aria-label="Silence for 5 miles"
      >
        🔇
      </button>
    </div>

    <!-- Capture sheet: note + ★ / Tell me more -->
    <div class="companion-view__capture">
      <input
        class="companion-view__note-input"
        type="text"
        bind:value={note}
        placeholder="Add a note (optional)…"
        aria-label="Capture note"
      />
      <div class="companion-view__capture-buttons">
        <button
          class="companion-view__capture-btn companion-view__capture-btn--star"
          on:click={handleStar}
          aria-label="Star"
        >
          ★ Star
        </button>
        <button
          class="companion-view__capture-btn companion-view__capture-btn--tellmore"
          on:click={handleTellMore}
          aria-label="Tell me more"
        >
          Tell me more
        </button>
      </div>
      {#if captureConfirmed}
        <p class="companion-view__capture-confirmation" role="status">Saved!</p>
      {/if}
    </div>

    <!-- Settings: fill slider + theme filter + highlight toggle -->
    <div class="companion-view__settings">
      <!-- Fill slider: 0–1 range -->
      <div class="companion-view__fill-row">
        <label class="companion-view__label" for="fill-slider">
          Fill: {Math.round(appState.settings.fillPct * 100)}%
        </label>
        <input
          id="fill-slider"
          class="companion-view__slider"
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={appState.settings.fillPct}
          on:input={onFillChange}
          aria-label="Content fill percentage"
        />
      </div>

      <!-- Theme filter toggles -->
      <div class="companion-view__themes" role="group" aria-label="Theme filters">
        {#each AVAILABLE_THEMES as theme}
          <button
            class="companion-view__theme-toggle"
            class:companion-view__theme-toggle--active={appState.settings.themes.has(theme)}
            on:click={() => onThemeToggle(theme)}
            aria-pressed={appState.settings.themes.has(theme)}
            aria-label="Toggle {theme} theme"
          >
            {theme}
          </button>
        {/each}
      </div>

      <!-- Highlight-only toggle -->
      <label class="companion-view__highlight-toggle">
        <input
          type="checkbox"
          checked={appState.settings.highlightOnly}
          on:change={onHighlightToggle}
          role="switch"
          aria-checked={appState.settings.highlightOnly}
          aria-label="Highlights only (salience ≥ 4)"
        />
        <span>Highlights only</span>
      </label>
    </div>

  {:else}
    <!-- Idle state: nothing playing -->
    <div class="companion-view__idle">
      <span class="companion-view__idle-icon" aria-hidden="true">🎧</span>
      <p class="companion-view__idle-text">No narration playing</p>
      <p class="companion-view__idle-hint">
        The companion begins when the train enters a narrated section.
      </p>
    </div>
  {/if}
</div>

<style>
  .companion-view {
    padding: 20px 20px 100px;
    overflow-y: auto;
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 20px;
    box-sizing: border-box;
  }

  .companion-view__theme-badge {
    display: inline-block;
    background: #eff6ff;
    color: #1d4ed8;
    border-radius: 6px;
    padding: 2px 10px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: capitalize;
    margin-bottom: 8px;
  }

  .companion-view__place {
    font-size: 1.375rem;
    font-weight: 800;
    color: #1a1a2e;
    margin: 0 0 10px;
  }

  .companion-view__text {
    font-size: 1rem;
    color: #333;
    line-height: 1.65;
    margin: 0;
  }

  .companion-view__controls {
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .companion-view__btn {
    background: #f3f4f6;
    border: none;
    border-radius: 12px;
    font-size: 1.375rem;
    width: 52px;
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background 0.12s;
  }

  .companion-view__btn--pause { background: #1a1a2e; color: #fff; }
  .companion-view__btn--silence { background: #fef9c3; }

  .companion-view__capture {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .companion-view__note-input {
    border: 1.5px solid #d1d5db;
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 0.9375rem;
    font-family: inherit;
    color: #1a1a2e;
    width: 100%;
    box-sizing: border-box;
  }

  .companion-view__capture-buttons {
    display: flex;
    gap: 10px;
  }

  .companion-view__capture-btn {
    flex: 1;
    padding: 12px;
    border: none;
    border-radius: 12px;
    font-size: 0.9375rem;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.12s;
  }

  .companion-view__capture-btn--star { background: #fef9c3; color: #92400e; }
  .companion-view__capture-btn--tellmore { background: #ede9fe; color: #5b21b6; }

  .companion-view__capture-confirmation {
    font-size: 0.875rem;
    color: #16a34a;
    font-weight: 600;
    text-align: center;
    margin: 0;
  }

  .companion-view__settings {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .companion-view__fill-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .companion-view__label {
    font-size: 0.875rem;
    font-weight: 600;
    color: #555;
  }

  .companion-view__slider {
    width: 100%;
    accent-color: #2563eb;
  }

  .companion-view__themes {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .companion-view__theme-toggle {
    background: #f3f4f6;
    border: 1.5px solid transparent;
    border-radius: 8px;
    padding: 5px 12px;
    font-size: 0.8125rem;
    font-weight: 600;
    cursor: pointer;
    color: #555;
    transition: all 0.12s;
    text-transform: capitalize;
  }

  .companion-view__theme-toggle--active {
    background: #dbeafe;
    border-color: #2563eb;
    color: #1d4ed8;
  }

  .companion-view__highlight-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.9rem;
    color: #333;
    cursor: pointer;
  }

  .companion-view__idle {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1;
    text-align: center;
    padding: 24px;
    gap: 12px;
  }

  .companion-view__idle-icon { font-size: 2.5rem; }

  .companion-view__idle-text {
    font-size: 1.125rem;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0;
  }

  .companion-view__idle-hint {
    font-size: 0.875rem;
    color: #888;
    margin: 0;
    line-height: 1.5;
  }
</style>
