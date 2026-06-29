/**
 * NowBar tests — persistent now-playing strip
 *
 * Tests:
 * - Renders "Quiet · next soon" idle text when nowPlaying is null
 * - Shows place name when a unit is playing
 * - ★ button calls orchestrator.capture with the unit and 'star'
 * - Pause button calls orchestrator.pause
 * - Star + pause buttons are hidden when nowPlaying is null
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import NowBar from '$lib/pillar3/NowBar.svelte';
import { appState } from '$lib/core/AppState.svelte';
import type { Unit } from 'companion-core';

// ── Mock orchestrator ─────────────────────────────────────────────────────────

const mockOrch = {
  pause: vi.fn().mockResolvedValue(undefined),
  resume: vi.fn().mockResolvedValue(undefined),
  capture: vi.fn().mockResolvedValue(undefined),
  skip: vi.fn().mockResolvedValue(undefined),
  silence: vi.fn(),
};

vi.mock('$lib/core/PlaybackOrchestrator', () => ({
  getOrchestrator: () => mockOrch,
  PlaybackOrchestrator: vi.fn(),
  initOrchestrator: vi.fn(),
}));

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

// ── Fixture ───────────────────────────────────────────────────────────────────

const MOCK_UNIT: Unit = {
  id: 'u-nb-1',
  kind: 'squib',
  mile: 20,
  place: 'Rocky Mountain Arsenal',
  side: 'right',
  salience: 4,
  theme: 'history',
  text: 'Arsenal history text here.',
  lat: 39.8,
  lon: -104.8,
  audio: 'audio/u-nb-1.mp3',
  dur_s: 30,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('NowBar', () => {
  beforeEach(() => {
    appState.nowPlaying = null;
    vi.clearAllMocks();
  });

  it('renders idle text when nowPlaying is null', () => {
    render(NowBar);
    const aside = screen.getByRole('complementary');
    expect(aside.textContent).toContain('Quiet · next soon');
  });

  it('shows place name when a unit is playing', async () => {
    appState.nowPlaying = MOCK_UNIT;
    render(NowBar);
    expect(screen.getByText(/Rocky Mountain Arsenal/i)).toBeTruthy();
  });

  it('shows "Unknown location" for a unit with null place', async () => {
    appState.nowPlaying = { ...MOCK_UNIT, place: null };
    render(NowBar);
    expect(screen.getByText(/Unknown location/i)).toBeTruthy();
  });

  it('star and pause buttons are NOT rendered when nowPlaying is null', () => {
    appState.nowPlaying = null;
    render(NowBar);
    expect(screen.queryByRole('button', { name: /pause/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /star/i })).toBeNull();
  });

  it('star button calls orchestrator.capture with unit and "star"', async () => {
    appState.nowPlaying = MOCK_UNIT;
    render(NowBar);
    const starBtn = screen.getByRole('button', { name: /star/i });
    await fireEvent.click(starBtn);
    expect(mockOrch.capture).toHaveBeenCalledWith(MOCK_UNIT, 'star');
  });

  it('pause button calls orchestrator.pause', async () => {
    appState.nowPlaying = MOCK_UNIT;
    render(NowBar);
    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    await fireEvent.click(pauseBtn);
    expect(mockOrch.pause).toHaveBeenCalledOnce();
  });

  it('pause toggles to resume after first click', async () => {
    appState.nowPlaying = MOCK_UNIT;
    render(NowBar);
    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    await fireEvent.click(pauseBtn);
    // Now it should say "Resume"
    const resumeBtn = screen.getByRole('button', { name: /resume/i });
    await fireEvent.click(resumeBtn);
    expect(mockOrch.resume).toHaveBeenCalledOnce();
  });
});
