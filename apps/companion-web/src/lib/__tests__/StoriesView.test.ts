/**
 * StoriesView.test.ts — Task 4
 *
 * Tests:
 * - Lists all deep-dives from the bundle
 * - Shows empty state when bundle has no deepdives
 * - Shows empty state when bundle is null
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import StoriesPage from '../../routes/stories/+page.svelte';
import { appState } from '$lib/core/AppState.svelte';
import type { DeepDive } from 'companion-core';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

vi.mock('$lib/core/PlaybackOrchestrator', () => ({
  getOrchestrator: () => ({ silence: vi.fn() }),
}));

vi.mock('$lib/native/plugins', () => ({
  AudioSession: {
    play: vi.fn().mockResolvedValue(undefined),
  },
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const MOCK_DIVES: DeepDive[] = [
  {
    id: 'dd-casey-jones',
    theme: 'Corridor of Movement',
    title: 'The Wreck of Casey Jones',
    mile: 200,
    trigger_mile: 192,
    nearest_place: 'Vaughan, MS',
    hook: 'A foggy April morning in 1900.',
    body_md: '## Casey Jones\n\nBody text.',
    narration_text: 'Narration text.',
    est_listen_min: 4,
    audio: null,
    images: [],
    sources: [],
    salience: 4,
  },
  {
    id: 'dd-flood-1927',
    theme: 'Written in Silt',
    title: 'The Great Flood of 1927',
    mile: 350,
    trigger_mile: 342,
    nearest_place: 'Greenville, MS',
    hook: 'The river burst its banks.',
    body_md: '## Flood of 1927\n\nBody text.',
    narration_text: 'Narration text.',
    est_listen_min: 4,
    audio: null,
    images: [],
    sources: [],
    salience: 4,
  },
  {
    id: 'dd-train-in-song',
    theme: "The Migration's Spine",
    title: 'The Train in the Song',
    mile: 600,
    trigger_mile: 592,
    nearest_place: 'Cairo, IL',
    hook: 'The Illinois Central was a lifeline.',
    body_md: '## The Train\n\nBody text.',
    narration_text: 'Narration text.',
    est_listen_min: 4,
    audio: null,
    images: [],
    sources: [],
    salience: 4,
  },
];

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('StoriesPage — list view', () => {
  beforeEach(() => {
    appState.bundle = null;
    appState.position = null;
    vi.clearAllMocks();
  });

  it('shows empty state when bundle is null', () => {
    appState.bundle = null;
    render(StoriesPage);
    expect(screen.getByText(/No featured stories/i)).toBeTruthy();
  });

  it('shows empty state when bundle has no deepdives', () => {
    // @ts-expect-error - minimal bundle for testing
    appState.bundle = { leg: '58', deepdives: [] };
    render(StoriesPage);
    expect(screen.getByText(/No featured stories/i)).toBeTruthy();
  });

  it('shows empty state when bundle has undefined deepdives', () => {
    // @ts-expect-error - minimal bundle for testing
    appState.bundle = { leg: '58' };
    render(StoriesPage);
    expect(screen.getByText(/No featured stories/i)).toBeTruthy();
  });

  it('lists all deep-dives from the bundle', () => {
    // @ts-expect-error - minimal bundle for testing
    appState.bundle = { leg: '58', deepdives: MOCK_DIVES };
    render(StoriesPage);
    expect(screen.getByText('The Wreck of Casey Jones')).toBeTruthy();
    expect(screen.getByText('The Great Flood of 1927')).toBeTruthy();
    expect(screen.getByText('The Train in the Song')).toBeTruthy();
  });

  it('shows theme chips for each story', () => {
    // @ts-expect-error - minimal bundle for testing
    appState.bundle = { leg: '58', deepdives: MOCK_DIVES };
    render(StoriesPage);
    expect(screen.getByText('Corridor of Movement')).toBeTruthy();
    expect(screen.getByText('Written in Silt')).toBeTruthy();
    expect(screen.getByText("The Migration's Spine")).toBeTruthy();
  });

  it('shows hook text for each story', () => {
    // @ts-expect-error - minimal bundle for testing
    appState.bundle = { leg: '58', deepdives: MOCK_DIVES };
    render(StoriesPage);
    expect(screen.getByText(/foggy April morning/i)).toBeTruthy();
    expect(screen.getByText(/river burst its banks/i)).toBeTruthy();
  });

  it('shows mile markers', () => {
    // @ts-expect-error - minimal bundle for testing
    appState.bundle = { leg: '58', deepdives: MOCK_DIVES };
    render(StoriesPage);
    expect(screen.getByText('mi 200')).toBeTruthy();
    expect(screen.getByText('mi 350')).toBeTruthy();
    expect(screen.getByText('mi 600')).toBeTruthy();
  });

  it('highlights the story nearest current position with "Now near you"', () => {
    // @ts-expect-error - minimal bundle for testing
    appState.bundle = { leg: '58', deepdives: MOCK_DIVES };
    appState.position = {
      mile: 195,
      lat: 32.9, lon: -90.1,
      source: 'predicted', direction: 1, leg: '58', stopped: false,
    };
    render(StoriesPage);
    expect(screen.getByText('Now near you')).toBeTruthy();
    // Casey Jones (mi 200) is nearest to mi 195
  });

  it('renders the page title', () => {
    // @ts-expect-error - minimal bundle for testing
    appState.bundle = { leg: '58', deepdives: MOCK_DIVES };
    render(StoriesPage);
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
    expect(screen.getByText('Featured Stories')).toBeTruthy();
  });
});
