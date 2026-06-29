import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PlaybackOrchestrator } from './PlaybackOrchestrator';
import type { Unit, Position, Bundle } from 'companion-core';

// Load real proxy bundle as fixture
import proxyBundle from '../../../../../tools/amtrak-position-engine/bundles/leg58/bundle.json' with { type: 'json' };

// Mock appState
vi.mock('./AppState.svelte', () => {
  const state = {
    bundle: null as Bundle | null,
    position: null as Position | null,
    nowPlaying: null as Unit | null,
    settings: { fillPct: 0.6, themes: new Set<string>(), highlightOnly: false, audioMode: 'interrupt-spoken' as const },
    favorites: { add: vi.fn() },
  };
  return { appState: state };
});

import { appState } from './AppState.svelte';

const UNIT_A: Unit = {
  id: 'u-a', kind: 'squib', mile: 10, place: 'Test Place', side: 'left',
  salience: 4 as const, theme: 'history', text: 'Test text.', lat: 30.0,
  lon: -90.1, audio: 'audio/u-a.mp3', dur_s: 18,
};

const MOCK_POSITION: Position = {
  mile: 9, lat: 30.0, lon: -90.1, source: 'gps', direction: 1, leg: '58', stopped: false,
};

const mockScheduler = {
  select: vi.fn(),
};

const mockAudioSession = {
  setMode: vi.fn().mockResolvedValue(undefined),
  play: vi.fn().mockResolvedValue(undefined),
  pause: vi.fn().mockResolvedValue(undefined),
  resume: vi.fn().mockResolvedValue(undefined),
  setRate: vi.fn().mockResolvedValue(undefined),
  addListener: vi.fn().mockReturnValue({ remove: vi.fn() }),
};

const mockFavorites = {
  add: vi.fn().mockResolvedValue({ id: 'fav-1', leg: '58', unitSnapshot: UNIT_A, position: MOCK_POSITION, kind: 'star', createdAt: Date.now() }),
  list: vi.fn().mockResolvedValue([]),
  get: vi.fn(),
  attachDive: vi.fn(),
};

function makeOrch() {
  return new PlaybackOrchestrator({
    scheduler: mockScheduler as never,
    audioSession: mockAudioSession as never,
    favorites: mockFavorites as never,
    bundlePath: '/bundles/58',
  });
}

describe('PlaybackOrchestrator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (appState as { nowPlaying: Unit | null }).nowPlaying = null;
    (appState as { position: Position | null }).position = MOCK_POSITION;
    (appState as { bundle: Bundle | null }).bundle = proxyBundle as Bundle;
    mockScheduler.select.mockReturnValue({ nowPlaying: UNIT_A, queue: [], silenceUntilMile: -Infinity });
  });

  it('calls AudioSession.play when update selects a new unit', async () => {
    const orch = makeOrch();
    await orch.update(MOCK_POSITION);
    expect(mockAudioSession.play).toHaveBeenCalledOnce();
    const [uri] = mockAudioSession.play.mock.calls[0];
    expect(uri).toContain('u-a.mp3');
  });

  it('sets appState.nowPlaying to the selected unit', async () => {
    const orch = makeOrch();
    await orch.update(MOCK_POSITION);
    expect(appState.nowPlaying?.id).toBe('u-a');
  });

  it('does not call play again if same unit is already playing', async () => {
    (appState as { nowPlaying: Unit | null }).nowPlaying = UNIT_A;
    const orch = makeOrch();
    await orch.update(MOCK_POSITION);
    expect(mockAudioSession.play).not.toHaveBeenCalled();
  });

  it('await on async pause works', async () => {
    const orch = makeOrch();
    await orch.pause();
    expect(mockAudioSession.pause).toHaveBeenCalledOnce();
  });

  it('await on async resume works', async () => {
    const orch = makeOrch();
    await orch.resume();
    expect(mockAudioSession.resume).toHaveBeenCalledOnce();
  });

  it('silence() clears nowPlaying and pauses', () => {
    (appState as { nowPlaying: Unit | null }).nowPlaying = UNIT_A;
    const orch = makeOrch();
    orch.silence(20);
    expect(appState.nowPlaying).toBeNull();
  });

  it('capture() calls favorites.add with full Unit, leg, and position', async () => {
    const orch = makeOrch();
    await orch.capture(UNIT_A, 'star');
    expect(mockFavorites.add).toHaveBeenCalledWith(UNIT_A, '58', MOCK_POSITION, 'star', undefined);
  });

  it('capture() passes note to favorites.add', async () => {
    const orch = makeOrch();
    await orch.capture(UNIT_A, 'tellmore', 'My note');
    expect(mockFavorites.add).toHaveBeenCalledWith(UNIT_A, '58', MOCK_POSITION, 'tellmore', 'My note');
  });

  it('uses real proxy bundle station data', () => {
    // Verify our fixture has real data
    expect((proxyBundle as Bundle).leg).toBe('58');
    expect((proxyBundle as Bundle).stations.length).toBeGreaterThan(0);
    expect((proxyBundle as Bundle).stations[0].code).toBe('NOL');
  });

  // ── BUG D: skip() must not strand narration ──────────────────────────────────

  it('skip() resets silenceUntilMile so a subsequent update can fire next unit', async () => {
    // Start with a silence lock set (simulating a stranded state)
    const orch = makeOrch();
    // Silence the orchestrator up to mile 50 (simulate it being silenced after skip)
    orch.silence(50);
    expect(mockAudioSession.pause).toHaveBeenCalledOnce();

    // Now simulate what skip() does: clear nowPlaying, reset silence lock, call update
    // The scheduler is mocked to return UNIT_A at the current position
    mockScheduler.select.mockReturnValue({ nowPlaying: UNIT_A, queue: [], silenceUntilMile: -Infinity });
    await orch.skip();

    // After skip, update should have fired and play should have been called
    expect(mockAudioSession.play).toHaveBeenCalledOnce();
    expect(appState.nowPlaying?.id).toBe('u-a');
  });

  it('skip() with no due unit does not strand: subsequent tick can fire next unit', async () => {
    const orch = makeOrch();

    // First skip: scheduler returns no unit but sets silenceUntilMile to next squib mile
    mockScheduler.select.mockReturnValueOnce({ nowPlaying: null, queue: [], silenceUntilMile: 15 });
    (appState as { nowPlaying: null }).nowPlaying = null;
    await orch.skip();

    // Play should NOT have been called (no unit due)
    expect(mockAudioSession.play).not.toHaveBeenCalled();

    // Now simulate a tick at mile 16 (past the silence lock)
    const posAt16: Position = { ...MOCK_POSITION, mile: 16 };
    (appState as { position: Position }).position = posAt16;
    mockScheduler.select.mockReturnValueOnce({ nowPlaying: UNIT_A, queue: [], silenceUntilMile: -Infinity });
    await orch.update(posAt16);

    // The subsequent tick should fire the next unit
    expect(mockAudioSession.play).toHaveBeenCalledOnce();
    expect(appState.nowPlaying?.id).toBe('u-a');
  });

  it('skip() with silenceUntilMile from scheduler: guard blocks ticks below that mile', async () => {
    const orch = makeOrch();

    // skip: scheduler returns no unit but silences until mile 15
    mockScheduler.select.mockReturnValueOnce({ nowPlaying: null, queue: [], silenceUntilMile: 15 });
    (appState as { nowPlaying: null }).nowPlaying = null;
    await orch.skip();

    // Tick at mile 10 (below silence lock) should be blocked
    const posAt10: Position = { ...MOCK_POSITION, mile: 10 };
    await orch.update(posAt10);
    expect(mockAudioSession.play).not.toHaveBeenCalled();

    // select was only called once (from skip()); the guard blocked the second call
    // select call count: 1 (from skip's internal update)
    expect(mockScheduler.select).toHaveBeenCalledTimes(1);
  });

  it('uses absolute audio URL directly when it starts with /', async () => {
    // bundleInit rewrites dev audio to /bundles/leg58/audio/... — those are absolute.
    // The orchestrator should use them as-is, not prepend bundlePath again.
    const absUnit: Unit = {
      ...UNIT_A,
      id: 'u-abs',
      audio: '/bundles/leg58/audio/u-abs.mp3',
    };
    mockScheduler.select.mockReturnValue({ nowPlaying: absUnit, queue: [], silenceUntilMile: -Infinity });
    const orch = makeOrch();
    await orch.update(MOCK_POSITION);
    const [uri] = mockAudioSession.play.mock.calls[0];
    expect(uri).toBe('/bundles/leg58/audio/u-abs.mp3');
  });

  it('reconstructs audio URI from bundlePath when audio is a relative filename', async () => {
    // When audio is just a filename like 'audio/u-a.mp3', reconstruct from bundlePath.
    const relUnit: Unit = { ...UNIT_A, id: 'u-rel', audio: 'audio/u-rel.mp3' };
    mockScheduler.select.mockReturnValue({ nowPlaying: relUnit, queue: [], silenceUntilMile: -Infinity });
    const orch = makeOrch();
    await orch.update(MOCK_POSITION);
    const [uri] = mockAudioSession.play.mock.calls[0];
    expect(uri).toBe('/bundles/58/audio/u-rel.mp3');
  });
});
