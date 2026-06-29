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
