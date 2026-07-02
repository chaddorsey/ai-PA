<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import NowBar from '$lib/pillar3/NowBar.svelte';
  import TabNav from '$lib/components/TabNav.svelte';
  import StationCard from '$lib/pillar2/StationCard.svelte';
  import { ApproachCue } from '$lib/core/ApproachCue';
  import { appState } from '$lib/core/AppState.svelte';
  import { initBundle } from '$lib/core/bundleInit';
  import { BackgroundLocation, LiveActivity, AudioSession } from '$lib/native/plugins';
  import type { BackgroundLocationFix } from '$lib/native/plugins';
  import { PositionService, Eta, Scheduler } from 'companion-core';
  import type { Station, Polyline } from 'companion-core';
  import { initOrchestrator, getOrchestrator } from '$lib/core/PlaybackOrchestrator';
  import DeepDiveOffer from '$lib/deepdive/DeepDiveOffer.svelte';
  import { getDeepDiveDirector } from '$lib/deepdive/DeepDiveDirector';
  // DEV: trip simulator wiring
  import { devState } from '$lib/dev/devState';
  // end DEV

  let { children } = $props();

  // ── Runtime singletons ──────────────────────────────────────────────────────
  // PositionService is created lazily after the bundle loads (needs bundle + poly).
  // Before bundle load it remains null; position updates only start after load.

  let positionService: InstanceType<typeof PositionService> | null = null;
  const approachCue = new ApproachCue();

  // Eta instance is created after the bundle loads (requires departure time).
  let eta: InstanceType<typeof Eta> | null = null;

  // ── Local state ─────────────────────────────────────────────────────────────

  let locationHandle: string | null = null;
  let tickInterval: ReturnType<typeof setInterval> | null = null;
  let activeStationCode = $state<string | null>(null);
  let bundleInitStatus = $state<'pending' | 'first-run' | 'loaded' | 'error'>('pending');
  let firstRunMessage = $state<string>('');

  // ── Bundle initialisation ───────────────────────────────────────────────────

  async function loadBundle() {
    const legId = appState.selectedLeg;
    const bundlePath = `/bundles/leg${legId}`;
    const result = await initBundle(legId);
    if (result.status === 'first-run') {
      bundleInitStatus = 'first-run';
      firstRunMessage = result.message;
    } else if (result.status === 'loaded') {
      bundleInitStatus = 'loaded';
      const bundle = result.bundle;
      // Initialise Eta from the bundle's departure time
      const origin = bundle.stations.find((s: Station) => s.sched_dep !== null);
      const depMs = origin?.sched_dep ? new Date(origin.sched_dep).getTime() : NaN;
      eta = new Eta(bundle, depMs);
      // Initialise PositionService with the bundle's polyline (from position_table)
      const poly: Polyline = bundle.position_table.map(
        ([_elapsed, mile, lat, lon]) => [mile, lat, lon] as [number, number, number],
      );
      positionService = new PositionService(bundle, poly, bundle.leg);
      // Wire up the PlaybackOrchestrator so narration/audio fires on every tick.
      // For dev/proxy, audio lives under /bundles/leg<legId>/audio (bundleInit already rewrites URLs).
      // In production, use: await BundleStore.getPath(leg) for the native FS path.
      const scheduler = new Scheduler(bundle, appState.settings);
      initOrchestrator({ scheduler, audioSession: AudioSession, favorites: appState.favorites, bundlePath });
    } else {
      bundleInitStatus = 'error';
      firstRunMessage = result.message;
    }
  }

  // ── Lifecycle ───────────────────────────────────────────────────────────────

  onMount(async () => {
    // Load the bundle FIRST — startup must not be blocked by any native plugin call.
    await loadBundle();

    // Apply initial audio mode (best-effort; a native failure must NOT block startup).
    try {
      await AudioSession.setMode(appState.settings.audioMode);
    } catch (e) {
      console.warn('[layout] AudioSession.setMode failed (non-fatal):', e);
    }

    // Start GPS watching — best-effort (the dev sim drives position regardless).
    try {
      locationHandle = await BackgroundLocation.watch((fix: BackgroundLocationFix) => {
        positionService?.onFix(fix.lat, fix.lon, fix.ts, fix.speed);
      });
    } catch (e) {
      console.warn('[layout] BackgroundLocation.watch failed (non-fatal):', e);
    }

    // 2-second tick: dead-reckoning + scheduler updates + approach cue checks
    tickInterval = setInterval(() => {
      // DEV: if a trip simulator is active and running, use its step() instead of positionService.tick()
      const sim = devState.getSimulator();
      if (sim && devState.isRunning()) {
        const pos = sim.step(Date.now());
        appState.position = pos;
        void getOrchestrator()?.update(pos);
        getDeepDiveDirector().update(pos);
        // Approach cue still fires during simulation
        if (appState.bundle && eta) {
          const result = approachCue.check(pos, eta, appState.bundle.stations);
          if (result !== null) {
            activeStationCode = result.station.code;
          }
        }
        const nextStation = getNextStation();
        void LiveActivity.update({
          nowPlaying: appState.nowPlaying?.place ?? null,
          nextStop: nextStation?.name ?? null,
          positionText: `mi ${pos.mile.toFixed(1)} [SIM]`,
        });
        return;
      }
      // end DEV
      if (!positionService) return;
      const pos = positionService.tick(Date.now());
      if (!pos) return;

      appState.position = pos;
      void getOrchestrator()?.update(pos);
      getDeepDiveDirector().update(pos);

      // Proactive approach cue: fires once per station per trip lifecycle
      if (appState.bundle && eta) {
        const result = approachCue.check(pos, eta, appState.bundle.stations);
        if (result !== null) {
          activeStationCode = result.station.code;
        }
      }

      // Live Activity stub update (Phase 2 — no-op in web stub)
      const nextStation = getNextStation();
      void LiveActivity.update({
        nowPlaying: appState.nowPlaying?.place ?? null,
        nextStop: nextStation?.name ?? null,
        positionText: `mi ${pos.mile.toFixed(1)}`,
      });
    }, 2000);
  });

  onDestroy(() => {
    if (locationHandle !== null) {
      void BackgroundLocation.clear(locationHandle);
    }
    if (tickInterval !== null) {
      clearInterval(tickInterval);
    }
    void LiveActivity.end();
  });

  // ── Audio mode reactivity ───────────────────────────────────────────────────
  // When the user changes audioMode in Settings, propagate to AudioSession.

  $effect(() => {
    const mode = appState.settings.audioMode;
    AudioSession.setMode(mode).catch((e) => console.warn('[layout] setMode failed (non-fatal):', e));
  });

  // ── Station card auto-dismiss ───────────────────────────────────────────────

  $effect(() => {
    if (!activeStationCode || !appState.bundle || !appState.position) return;
    const station = appState.bundle.stations.find((s: Station) => s.code === activeStationCode);
    if (station && appState.position.mile > station.mile + 0.5) {
      activeStationCode = null;
    }
  });

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function getNextStation(): Station | null {
    if (!appState.bundle || !appState.position) return null;
    return appState.bundle.stations.find((s: Station) => s.mile > appState.position!.mile) ?? null;
  }

  function dismissStationCard() {
    activeStationCode = null;
  }
</script>

<div class="layout-shell">
  <!-- Persistent NowBar above the page content on all routes -->
  <NowBar />

  <!-- Deep-dive offer banner: shown when a story is available and not yet seen -->
  {#if appState.pendingDeepDive}
    <DeepDiveOffer
      deepdive={appState.pendingDeepDive}
      onDismiss={() => { appState.pendingDeepDive = null; }}
    />
  {/if}

  <!-- Page slot -->
  <main class="layout-main" id="main-content">
    {#if bundleInitStatus === 'first-run'}
      <!-- First-run: no bundle downloaded yet -->
      <div class="layout-first-run">
        <span class="layout-first-run__icon" aria-hidden="true">🚂</span>
        <h2 class="layout-first-run__heading">Download your trip</h2>
        <p class="layout-first-run__hint">
          {firstRunMessage || 'Go to Settings to download your trip bundle.'}
        </p>
      </div>
    {:else if bundleInitStatus === 'error'}
      <!-- Bundle load failed — surface the reason so we can diagnose on device -->
      <div class="layout-first-run">
        <span class="layout-first-run__icon" aria-hidden="true">⚠️</span>
        <h2 class="layout-first-run__heading">Couldn't load the trip</h2>
        <p class="layout-first-run__hint">{firstRunMessage}</p>
      </div>
    {:else}
      {@render children()}
    {/if}
  </main>

  <!-- Persistent TabNav below the page content on all routes -->
  <TabNav />

  <!-- Contextual StationCard overlay: triggered by ApproachCue or map pin tap -->
  {#if activeStationCode && appState.bundle}
    <StationCard
      bundle={appState.bundle}
      stationCode={activeStationCode}
      position={appState.position}
      onDismiss={dismissStationCard}
    />
  {/if}
</div>

<style>
  :global(*, *::before, *::after) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f9fafb;
    overscroll-behavior: none;
  }

  .layout-shell {
    display: flex;
    flex-direction: column;
    height: 100dvh;
    overflow: hidden;
    position: relative;
  }

  .layout-main {
    flex: 1;
    overflow: hidden;
    position: relative;
  }

  .layout-first-run {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 12px;
    padding: 24px;
    text-align: center;
  }

  .layout-first-run__icon {
    font-size: 3rem;
  }

  .layout-first-run__heading {
    font-size: 1.375rem;
    font-weight: 800;
    color: #1a1a2e;
  }

  .layout-first-run__hint {
    font-size: 0.9375rem;
    color: #888;
    line-height: 1.5;
  }
</style>
