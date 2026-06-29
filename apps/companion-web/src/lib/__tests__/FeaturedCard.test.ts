/**
 * FeaturedCard.test.ts — Task 3
 *
 * Tests:
 * - Renders title, hook, and body text
 * - Listen button is disabled with "Audio coming soon" when audio is null
 * - Listen button is enabled when audio is present
 * - Renders a gradient background (not a <img>) when images array is empty
 * - Theme chip is displayed
 * - Sources section is rendered when sources are present
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import FeaturedCard from '$lib/deepdive/FeaturedCard.svelte';
import type { DeepDive } from 'companion-core';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('$lib/core/AppState.svelte', () => ({
  appState: {
    position: { mile: 195, lat: 32.9, lon: -90.1, source: 'predicted', direction: 1, leg: '58', stopped: false },
    bundle: { leg: '58' },
    favorites: { add: vi.fn().mockResolvedValue(undefined) },
  },
}));

vi.mock('$lib/core/PlaybackOrchestrator', () => ({
  getOrchestrator: () => ({
    silence: vi.fn(),
    pause: vi.fn().mockResolvedValue(undefined),
    resume: vi.fn().mockResolvedValue(undefined),
  }),
}));

vi.mock('$lib/native/plugins', () => ({
  AudioSession: {
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn().mockResolvedValue(undefined),
    resume: vi.fn().mockResolvedValue(undefined),
    setMode: vi.fn().mockResolvedValue(undefined),
    setRate: vi.fn().mockResolvedValue(undefined),
    addListener: vi.fn(() => ({ remove: vi.fn() })),
  },
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const BASE_DEEPDIVE: DeepDive = {
  id: 'dd-casey-jones',
  theme: 'Corridor of Movement',
  title: 'The Wreck of Casey Jones',
  mile: 200,
  trigger_mile: 192,
  nearest_place: 'Vaughan, MS',
  hook: 'On a foggy April morning in 1900, engineer John Luther Jones held his throttle wide open.',
  body_md: '## The Wreck of Casey Jones\n\nA foggy April morning in 1900.\n\n*(Draft placeholder — full story pending review.)*',
  narration_text: 'On a foggy April morning...',
  est_listen_min: 4,
  audio: null,
  images: [],
  sources: [],
  salience: 4,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('FeaturedCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the story title in an h1 heading', () => {
    render(FeaturedCard, { props: { deepdive: BASE_DEEPDIVE } });
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1.textContent).toContain('The Wreck of Casey Jones');
  });

  it('renders the hook text in the hook element', () => {
    const { container } = render(FeaturedCard, { props: { deepdive: BASE_DEEPDIVE } });
    const hook = container.querySelector('.featured-card__hook');
    expect(hook).toBeTruthy();
    expect(hook!.textContent).toMatch(/foggy April morning/i);
  });

  it('renders the markdown body as HTML (h2 heading from ## becomes visible)', () => {
    render(FeaturedCard, { props: { deepdive: BASE_DEEPDIVE } });
    // marked converts "## The Wreck..." to an <h2>
    const h2 = screen.getByRole('heading', { level: 2 });
    expect(h2.textContent).toContain('The Wreck of Casey Jones');
  });

  it('renders "Draft placeholder" text from the body', () => {
    render(FeaturedCard, { props: { deepdive: BASE_DEEPDIVE } });
    expect(screen.getByText(/Draft placeholder/i)).toBeTruthy();
  });

  it('Listen button is disabled with "Audio coming soon" when audio is null', () => {
    render(FeaturedCard, { props: { deepdive: BASE_DEEPDIVE } });
    const btn = screen.getByRole('button', { name: /audio coming soon/i });
    expect(btn).toBeTruthy();
    expect(btn.hasAttribute('disabled')).toBe(true);
  });

  it('Listen button is enabled and playable when audio is present', () => {
    const dd: DeepDive = { ...BASE_DEEPDIVE, audio: 'audio/dd-casey.mp3' };
    render(FeaturedCard, { props: { deepdive: dd } });
    const btn = screen.getByRole('button', { name: /listen/i });
    expect(btn).toBeTruthy();
    expect(btn.hasAttribute('disabled')).toBe(false);
  });

  it('renders theme chip with theme name', () => {
    render(FeaturedCard, { props: { deepdive: BASE_DEEPDIVE } });
    expect(screen.getByText('Corridor of Movement')).toBeTruthy();
  });

  it('renders a gradient header (no img src) when images array is empty', () => {
    const { container } = render(FeaturedCard, { props: { deepdive: BASE_DEEPDIVE } });
    // Hero div should use inline background style (gradient), not a url()
    const hero = container.querySelector('.featured-card__hero') as HTMLElement;
    expect(hero).toBeTruthy();
    // The inline style attribute must contain "gradient" (set via style="background: gradient...")
    const styleAttr = hero.getAttribute('style') ?? '';
    expect(styleAttr).toContain('gradient');
    // No <img> element should be inside the hero for the no-image case
    const imgInHero = hero.querySelector('img');
    expect(imgInHero).toBeNull();
  });

  it('shows source links when sources are present', () => {
    const dd: DeepDive = {
      ...BASE_DEEPDIVE,
      sources: [
        { title: 'Casey Jones Museum', url: 'https://www.caseyjones.com' },
        { title: 'Illinois Central History', url: 'https://example.com' },
      ],
    };
    render(FeaturedCard, { props: { deepdive: dd } });
    expect(screen.getByText('Casey Jones Museum')).toBeTruthy();
    expect(screen.getByText('Illinois Central History')).toBeTruthy();
    // Should be links
    const links = screen.getAllByRole('link');
    expect(links.length).toBeGreaterThanOrEqual(2);
  });

  it('does NOT render sources section when sources are empty', () => {
    render(FeaturedCard, { props: { deepdive: BASE_DEEPDIVE } });
    expect(screen.queryByText('Sources')).toBeNull();
  });

  it('shows mile marker in hero overlay', () => {
    render(FeaturedCard, { props: { deepdive: BASE_DEEPDIVE } });
    expect(screen.getByText('mi 200')).toBeTruthy();
  });
});
