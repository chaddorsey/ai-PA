<script lang="ts">
  import { appState } from '$lib/core/AppState.svelte';
  import { AudioSession, BundleStore } from '$lib/native/plugins';

  // Available themes (static list; matches CompanionView.svelte)
  const AVAILABLE_THEMES = ['history', 'geology', 'lore', 'science', 'connections', 'culture'] as const;

  // California Zephyr legs — real numeric string IDs from the bundle
  const LEGS = [
    { id: '56', label: 'Chicago → Omaha' },
    { id: '57', label: 'Omaha → Denver' },
    { id: '58', label: 'Denver → Salt Lake City' },
    { id: '59', label: 'Salt Lake City → Reno' },
    { id: '60', label: 'Reno → Sacramento' },
    { id: '61', label: 'Sacramento → Emeryville' },
  ];

  // ── Download manager ────────────────────────────────────────────────────────

  type DownloadStatus = 'not_downloaded' | 'downloading' | 'downloaded';
  let downloadStatus = $state<Record<string, DownloadStatus>>({});
  let downloadedLegs = $state<string[]>([]);

  async function refreshDownloadedLegs() {
    try {
      downloadedLegs = await BundleStore.list();
    } catch {
      downloadedLegs = [];
    }
  }

  $effect(() => {
    void refreshDownloadedLegs();
  });

  function isDownloaded(legId: string): boolean {
    return downloadedLegs.includes(legId);
  }

  async function downloadLeg(legId: string) {
    downloadStatus[legId] = 'downloading';
    try {
      // URL comes from the bundle manifest in production.
      const url = `https://bundles.amtrak-companion.app/v1/${legId}/bundle.zip`;
      await BundleStore.download(legId, url);
      downloadStatus[legId] = 'downloaded';
      downloadedLegs = [...downloadedLegs, legId];
    } catch {
      downloadStatus[legId] = 'not_downloaded';
    }
  }

  // ── Audio mode selector ─────────────────────────────────────────────────────

  async function onAudioModeChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    const mode = target.value as 'duck' | 'pause' | 'interrupt-spoken';
    appState.settings.audioMode = mode;
    await AudioSession.setMode(mode);
  }

  // ── Fill density ────────────────────────────────────────────────────────────

  function onFillInput(event: Event) {
    const target = event.target as HTMLInputElement;
    appState.settings.fillPct = parseFloat(target.value);
  }

  // ── Theme emphasis toggles ──────────────────────────────────────────────────

  function onThemeChange(theme: string, event: Event) {
    const target = event.target as HTMLInputElement;
    if (target.checked) {
      appState.settings.themes.add(theme);
    } else {
      appState.settings.themes.delete(theme);
    }
    // Reassign to trigger Svelte 4 reactivity (Set mutation isn't tracked natively)
    appState.settings.themes = new Set(appState.settings.themes);
  }

  // ── Highlight-only toggle ───────────────────────────────────────────────────

  function onHighlightOnlyChange(event: Event) {
    const target = event.target as HTMLInputElement;
    appState.settings.highlightOnly = target.checked;
  }

  // ── DEV: Simulate trip ────────────────────────────────────────────────────
  import { TripSimulator, SIM_SPEED_OPTIONS } from '$lib/dev/tripSimulator';
  import type { SimSpeed } from '$lib/dev/tripSimulator';
  import { devState } from '$lib/dev/devState';

  // Local Svelte-reactive state for the UI; initialized from devState so checkbox
  // reflects real state after tab navigation (remount resets local $state otherwise).
  let simRunning = $state(devState.isRunning());
  let simSpeed = $state<SimSpeed>(1);
  // Current simulator instance (lazy-created when bundle is available)
  let _localSim: TripSimulator | null = null;

  function getOrCreateSim(): TripSimulator | null {
    if (!appState.bundle) return null;
    if (!_localSim) {
      _localSim = new TripSimulator(appState.bundle);
      devState.setSimulator(_localSim);
    }
    return _localSim;
  }

  function onSimToggle(event: Event) {
    const target = event.target as HTMLInputElement;
    const sim = getOrCreateSim();
    if (!sim) return;
    if (target.checked) {
      sim.start(simSpeed);
      simRunning = true;
      devState.setRunning(true);
    } else {
      sim.stop();
      simRunning = false;
      devState.setRunning(false);
    }
    // Layout tick reads devState.isRunning() to decide between sim and real GPS
  }

  function onSimSpeedChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    simSpeed = parseFloat(target.value) as SimSpeed;
    if (simRunning && _localSim) {
      // Restart at new speed from current position
      _localSim.stop();
      _localSim.start(simSpeed);
    }
  }
  // ── end DEV ───────────────────────────────────────────────────────────────

</script>

<div class="settings-view">
  <h1 class="settings-view__title">Settings</h1>

  <!-- Content Density (fillPct) -->
  <section class="settings-section">
    <h2 class="settings-section__heading">Content Density</h2>
    <div class="settings-row">
      <label class="settings-label" for="fill-slider">
        Fill: {Math.round(appState.settings.fillPct * 100)}%
      </label>
      <input
        id="fill-slider"
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={appState.settings.fillPct}
        oninput={onFillInput}
        class="settings-slider"
        aria-label="Content fill percentage"
      />
      <div class="settings-slider-labels">
        <span>Sparse</span><span>Dense</span>
      </div>
    </div>
  </section>

  <!-- Audio Mode -->
  <section class="settings-section">
    <h2 class="settings-section__heading">Audio Mode</h2>
    <div class="settings-row">
      <label class="settings-label" for="audio-mode">
        When narrating, other audio:
      </label>
      <select
        id="audio-mode"
        class="settings-select"
        value={appState.settings.audioMode}
        onchange={onAudioModeChange}
        aria-label="Audio session mode"
      >
        <option value="interrupt-spoken">Duck music · pause podcasts (recommended)</option>
        <option value="duck">Duck all other audio</option>
        <option value="pause">Pause all other audio</option>
      </select>
    </div>
  </section>

  <!-- Theme Emphasis -->
  <section class="settings-section">
    <h2 class="settings-section__heading">Theme Emphasis</h2>
    <p class="settings-description">
      Emphasised themes appear more often. Leave all unchecked for balanced coverage.
    </p>
    <div class="settings-checkboxes">
      {#each AVAILABLE_THEMES as theme}
        <label class="settings-checkbox-label">
          <input
            type="checkbox"
            checked={appState.settings.themes.has(theme)}
            onchange={(e) => onThemeChange(theme, e)}
            aria-label="Emphasize {theme} content"
          />
          <span>{theme.charAt(0).toUpperCase() + theme.slice(1)}</span>
        </label>
      {/each}
    </div>
  </section>

  <!-- Highlights Only -->
  <section class="settings-section">
    <h2 class="settings-section__heading">Highlights Only</h2>
    <label class="settings-toggle-label">
      <input
        type="checkbox"
        checked={appState.settings.highlightOnly}
        onchange={onHighlightOnlyChange}
        role="switch"
        aria-checked={appState.settings.highlightOnly}
        aria-label="Only play highest-salience content"
      />
      <span>Only play salience ≥ 4 units (unmissable highlights)</span>
    </label>
  </section>

  <!-- Offline Bundles / Download Manager -->
  <section class="settings-section">
    <h2 class="settings-section__heading">Offline Bundles</h2>
    <p class="settings-description">
      Download legs for offline use. Each bundle includes narration audio and map data.
    </p>
    <div class="settings-legs">
      {#each LEGS as leg}
        {@const status = downloadStatus[leg.id]}
        {@const downloaded = isDownloaded(leg.id)}
        <div class="settings-leg-row">
          <div class="settings-leg-info">
            <span class="settings-leg-label">{leg.label}</span>
            <span
              class="settings-leg-status"
              class:settings-leg-status--downloaded={downloaded}
              class:settings-leg-status--downloading={status === 'downloading'}
            >
              {status === 'downloading'
                ? 'Downloading…'
                : downloaded
                  ? 'Downloaded'
                  : 'Not downloaded'}
            </span>
          </div>
          {#if !downloaded && status !== 'downloading'}
            <button
              class="settings-download-btn"
              onclick={() => downloadLeg(leg.id)}
              aria-label="Download {leg.label}"
            >
              Download
            </button>
          {:else if status === 'downloading'}
            <span class="settings-download-progress" aria-live="polite">⏳</span>
          {:else}
            <span class="settings-downloaded-check" aria-label="Downloaded">✓</span>
          {/if}
        </div>
      {/each}
    </div>
  </section>
  <!-- DEV: Developer section — remove before shipping to App Store -->
  <section class="settings-section settings-section--dev">
    <h2 class="settings-section__heading">Developer</h2>
    <p class="settings-description settings-description--dev">
      DEV-ONLY: On-device couch testing tools. Not visible in production.
    </p>

    <!-- Simulate trip toggle -->
    <div class="settings-row" style="gap: 12px;">
      <label class="settings-toggle-label">
        <input
          type="checkbox"
          checked={simRunning}
          onchange={onSimToggle}
          disabled={!appState.bundle}
          role="switch"
          aria-checked={simRunning}
          aria-label="Simulate trip along leg 58"
        />
        <span>
          Simulate trip
          {#if !appState.bundle}
            <em style="color:#aaa;font-weight:400;">(load a bundle first)</em>
          {/if}
        </span>
      </label>

      <!-- Speed control -->
      {#if simRunning}
        <div class="settings-row" style="gap: 6px;">
          <label class="settings-label" for="sim-speed">Speed</label>
          <select
            id="sim-speed"
            class="settings-select"
            value={simSpeed}
            onchange={onSimSpeedChange}
            aria-label="Simulation speed multiplier"
          >
            {#each SIM_SPEED_OPTIONS as spd}
              <option value={spd}>{spd}x</option>
            {/each}
          </select>
        </div>
      {/if}
    </div>
  </section>
  <!-- end DEV -->

</div>

<style>
  .settings-view {
    padding: 24px 20px 100px;
    overflow-y: auto;
    height: 100%;
    box-sizing: border-box;
  }

  .settings-view__title {
    font-size: 1.5rem;
    font-weight: 800;
    color: #1a1a2e;
    margin: 0 0 24px;
  }

  .settings-section {
    margin-bottom: 32px;
  }

  .settings-section__heading {
    font-size: 0.8125rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #888;
    margin: 0 0 12px;
    font-weight: 700;
  }

  .settings-description {
    font-size: 0.8125rem;
    color: #9ca3af;
    margin: 0 0 12px;
    line-height: 1.45;
  }

  .settings-row {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .settings-label {
    font-size: 1rem;
    font-weight: 600;
    color: #1a1a2e;
  }

  .settings-slider {
    width: 100%;
    accent-color: #2563eb;
  }

  .settings-slider-labels {
    display: flex;
    justify-content: space-between;
    font-size: 0.75rem;
    color: #aaa;
  }

  .settings-select {
    width: 100%;
    padding: 10px 12px;
    border: 1.5px solid #d1d5db;
    border-radius: 10px;
    font-size: 0.9375rem;
    font-family: inherit;
    color: #1a1a2e;
    background: #fff;
    appearance: auto;
  }

  .settings-checkboxes {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .settings-checkbox-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.9375rem;
    color: #333;
    cursor: pointer;
  }

  .settings-toggle-label {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 0.9375rem;
    color: #333;
    cursor: pointer;
    line-height: 1.4;
  }

  .settings-legs {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .settings-leg-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #f9fafb;
    border-radius: 10px;
    padding: 12px 14px;
  }

  .settings-leg-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    min-width: 0;
  }

  .settings-leg-label {
    font-size: 0.9375rem;
    font-weight: 600;
    color: #1a1a2e;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .settings-leg-status {
    font-size: 0.75rem;
    color: #aaa;
  }

  .settings-leg-status--downloaded {
    color: #16a34a;
  }

  .settings-leg-status--downloading {
    color: #2563eb;
  }

  .settings-download-btn {
    background: #2563eb;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    flex-shrink: 0;
    margin-left: 12px;
  }

  .settings-downloaded-check {
    color: #16a34a;
    font-size: 1.25rem;
    margin-left: 12px;
  }

  .settings-download-progress {
    font-size: 1.125rem;
    margin-left: 12px;
  }

  /* DEV: Developer section styles */
  .settings-section--dev {
    border: 1.5px dashed #f59e0b;
    border-radius: 12px;
    padding: 14px 14px 6px;
    background: #fffbeb;
  }

  .settings-description--dev {
    color: #b45309;
    font-style: italic;
  }
  /* end DEV */

</style>
