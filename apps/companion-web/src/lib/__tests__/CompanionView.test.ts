/**
 * CompanionView tests — companion pillar
 *
 * Tests:
 * - Renders now-playing place and text
 * - Pause button calls orchestrator.pause
 * - Skip button calls orchestrator.skip
 * - ★ Star button calls orchestrator.capture(unit, 'star', undefined) when note is empty
 * - Tell me more calls orchestrator.capture(unit, 'tellmore', note) with typed note
 * - fillPct slider updates appState.settings.fillPct
 * - Theme toggle adds/removes from settings.themes
 * - Highlight toggle flips settings.highlightOnly
 * - Idle message when nowPlaying is null
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import CompanionView from '$lib/pillar3/CompanionView.svelte';
import { appState } from '$lib/core/AppState.svelte';
import type { Unit } from 'companion-core';

// ── Mock orchestrator ─────────────────────────────────────────────────────────

const mockOrch = {
  pause: vi.fn().mockResolvedValue(undefined),
  resume: vi.fn().mockResolvedValue(undefined),
  skip: vi.fn().mockResolvedValue(undefined),
  silence: vi.fn(),
  capture: vi.fn().mockResolvedValue(undefined),
};

vi.mock('$lib/core/PlaybackOrchestrator', () => ({
  getOrchestrator: () => mockOrch,
  PlaybackOrchestrator: vi.fn(),
  initOrchestrator: vi.fn(),
}));

// ── Fixture ───────────────────────────────────────────────────────────────────

const MOCK_UNIT: Unit = {
  id: 'u-cv-1',
  kind: 'squib',
  mile: 30,
  place: 'Moffat Tunnel',
  side: 'left',
  salience: 5,
  theme: 'geology',
  text: 'Bored through the Continental Divide at 9,239 feet, the Moffat Tunnel opened in 1928.',
  lat: 39.9,
  lon: -105.7,
  audio: 'audio/u-cv-1.mp3',
  dur_s: 42,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('CompanionView', () => {
  beforeEach(() => {
    appState.nowPlaying = MOCK_UNIT;
    appState.settings.fillPct = 0.6;
    appState.settings.themes = new Set();
    appState.settings.highlightOnly = false;
    vi.clearAllMocks();
  });

  it('renders the now-playing place name', async () => {
    render(CompanionView);
    // StoryCard may also mention the place; use getAllByText to handle duplicates
    expect(screen.getAllByText(/Moffat Tunnel/i).length).toBeGreaterThan(0);
  });

  it('renders the now-playing text', async () => {
    render(CompanionView);
    expect(screen.getByText(/Continental Divide/i)).toBeTruthy();
  });

  it('pause button calls orchestrator.pause', async () => {
    render(CompanionView);
    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    await fireEvent.click(pauseBtn);
    expect(mockOrch.pause).toHaveBeenCalledOnce();
  });

  it('skip button calls orchestrator.skip', async () => {
    render(CompanionView);
    const skipBtn = screen.getByRole('button', { name: /skip/i });
    await fireEvent.click(skipBtn);
    expect(mockOrch.skip).toHaveBeenCalledOnce();
  });

  it('★ Star button calls capture(unit, "star", undefined) when note is empty', async () => {
    render(CompanionView);
    const starBtn = screen.getByRole('button', { name: /^star$/i });
    await fireEvent.click(starBtn);
    expect(mockOrch.capture).toHaveBeenCalledWith(MOCK_UNIT, 'star', undefined);
  });

  it('"Tell me more" calls capture(unit, "tellmore", note) with typed note', async () => {
    render(CompanionView);
    const noteInput = screen.getByRole('textbox', { name: /capture note/i });
    await fireEvent.input(noteInput, { target: { value: 'Love the engineering history' } });
    const tellMoreBtn = screen.getByRole('button', { name: /tell me more/i });
    await fireEvent.click(tellMoreBtn);
    expect(mockOrch.capture).toHaveBeenCalledWith(MOCK_UNIT, 'tellmore', 'Love the engineering history');
  });

  it('"Tell me more" passes undefined note when input is whitespace only', async () => {
    render(CompanionView);
    const noteInput = screen.getByRole('textbox', { name: /capture note/i });
    await fireEvent.input(noteInput, { target: { value: '   ' } });
    const tellMoreBtn = screen.getByRole('button', { name: /tell me more/i });
    await fireEvent.click(tellMoreBtn);
    expect(mockOrch.capture).toHaveBeenCalledWith(MOCK_UNIT, 'tellmore', undefined);
  });

  it('fill slider updates appState.settings.fillPct', async () => {
    render(CompanionView);
    const slider = screen.getByRole('slider', { name: /fill/i });
    await fireEvent.input(slider, { target: { value: '0.8' } });
    expect(appState.settings.fillPct).toBeCloseTo(0.8);
  });

  it('theme toggle button adds theme to settings.themes', async () => {
    render(CompanionView);
    const historyBtn = screen.getByRole('button', { name: /toggle history theme/i });
    await fireEvent.click(historyBtn);
    expect(appState.settings.themes.has('history')).toBe(true);
  });

  it('clicking active theme removes it from settings.themes', async () => {
    appState.settings.themes = new Set(['history']);
    render(CompanionView);
    const historyBtn = screen.getByRole('button', { name: /toggle history theme/i });
    await fireEvent.click(historyBtn);
    expect(appState.settings.themes.has('history')).toBe(false);
  });

  it('highlight toggle flips highlightOnly', async () => {
    render(CompanionView);
    // The checkbox has role='switch' (overrides checkbox role in ARIA)
    const toggle = screen.getByRole('switch', { name: /highlights only/i });
    await fireEvent.change(toggle);
    expect(appState.settings.highlightOnly).toBe(true);
  });

  it('shows idle message when nowPlaying is null', async () => {
    appState.nowPlaying = null;
    render(CompanionView);
    expect(screen.getByText(/no narration playing/i)).toBeTruthy();
  });
});
