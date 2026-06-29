/**
 * SavedList tests — pure logic (sortFavorites, hasDive) + component rendering.
 *
 * Tests:
 * - sortFavorites: sorts newest-first, non-mutating, empty array
 * - hasDive: true/false on attached/missing dive
 * - SavedList component: lists favorites with place/kind/note, shows Phase-2 dive placeholder
 * - SavedList: empty state when no captures
 * - capture(note) → list flow using real Favorites + InMemoryAdapter
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import { sortFavorites, hasDive } from '$lib/pillar3/SavedList';
import SavedList from '$lib/pillar3/SavedList.svelte';
import { Favorites, InMemoryAdapter } from 'companion-core';
import type { Favorite, Unit, Position } from 'companion-core';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const UNIT_A: Unit = {
  id: 'u-a', kind: 'squib', mile: 10, place: 'Denver Union Station',
  side: 'left', salience: 4, theme: 'history',
  text: 'Denver Union Station opened in 1881.',
  lat: 39.75, lon: -104.99, audio: 'audio/u-a.mp3', dur_s: 20,
};

const UNIT_B: Unit = {
  id: 'u-b', kind: 'squib', mile: 30, place: 'Moffat Tunnel',
  side: 'left', salience: 5, theme: 'geology',
  text: 'Bored through the Continental Divide.',
  lat: 39.9, lon: -105.7, audio: 'audio/u-b.mp3', dur_s: 35,
};

const POSITION: Position = {
  mile: 5, lat: 39.7, lon: -104.9,
  source: 'gps', direction: 1, leg: '58', stopped: false,
};

function makeFav(
  id: string,
  createdAt: number,
  kind: 'star' | 'tellmore' = 'star',
  note?: string,
  hasDiveCard = false,
): Favorite {
  const fav: Favorite = {
    id,
    leg: '58',
    unitSnapshot: UNIT_A,
    position: POSITION,
    kind,
    createdAt,
  };
  if (note) fav.note = note;
  if (hasDiveCard) {
    fav.dive = { body: 'Dive body.', sources: ['https://example.com'], createdAt };
  }
  return fav;
}

// ── sortFavorites ─────────────────────────────────────────────────────────────

describe('sortFavorites', () => {
  it('sorts favorites by createdAt descending (newest first)', () => {
    const favs = [makeFav('a', 100), makeFav('b', 300), makeFav('c', 200)];
    const sorted = sortFavorites(favs);
    expect(sorted[0].id).toBe('b');
    expect(sorted[1].id).toBe('c');
    expect(sorted[2].id).toBe('a');
  });

  it('returns empty array for empty input', () => {
    expect(sortFavorites([])).toEqual([]);
  });

  it('does not mutate the original array', () => {
    const favs = [makeFav('x', 500), makeFav('y', 100)];
    const first = favs[0].id;
    sortFavorites(favs);
    expect(favs[0].id).toBe(first);
  });

  it('handles single-element array', () => {
    const favs = [makeFav('only', 999)];
    expect(sortFavorites(favs)).toHaveLength(1);
    expect(sortFavorites(favs)[0].id).toBe('only');
  });
});

// ── hasDive ───────────────────────────────────────────────────────────────────

describe('hasDive', () => {
  it('returns true when favorite has a dive attached', () => {
    expect(hasDive(makeFav('d', 1000, 'star', undefined, true))).toBe(true);
  });

  it('returns false when favorite has no dive', () => {
    expect(hasDive(makeFav('nd', 1000))).toBe(false);
  });

  it('returns false when dive is undefined', () => {
    const fav = makeFav('ud', 999);
    fav.dive = undefined;
    expect(hasDive(fav)).toBe(false);
  });
});

// ── SavedList component ───────────────────────────────────────────────────────

describe('SavedList component', () => {
  it('shows empty state when favorites array is empty', () => {
    render(SavedList, { props: { favorites: [] } });
    expect(screen.getByText(/no saved captures yet/i)).toBeTruthy();
  });

  it('lists favorites showing place name', () => {
    const favs = [makeFav('f1', 1000)];
    render(SavedList, { props: { favorites: favs } });
    // Place appears in both the SavedItem place span and the preview text area
    expect(screen.getAllByText(/Denver Union Station/i).length).toBeGreaterThan(0);
  });

  it('shows ★ badge for star kind', () => {
    const favs = [makeFav('f1', 1000, 'star')];
    render(SavedList, { props: { favorites: favs } });
    expect(screen.getByText('★')).toBeTruthy();
  });

  it('shows "Tell me more" badge for tellmore kind', () => {
    const favs = [makeFav('f1', 1000, 'tellmore')];
    render(SavedList, { props: { favorites: favs } });
    expect(screen.getByText('Tell me more')).toBeTruthy();
  });

  it('shows note preview for favorite with note', () => {
    const favs = [makeFav('f1', 1000, 'star', 'Great engineering feat')];
    render(SavedList, { props: { favorites: favs } });
    expect(screen.getByText(/"Great engineering feat"/i)).toBeTruthy();
  });

  it('sorts newest-first (highest createdAt first)', () => {
    const favs = [
      { ...makeFav('old', 100, 'star'), unitSnapshot: UNIT_A },
      { ...makeFav('new', 999, 'tellmore'), unitSnapshot: UNIT_B },
    ];
    render(SavedList, { props: { favorites: favs } });
    const items = screen.getAllByRole('listitem');
    // The first listitem should be Moffat Tunnel (newer) — it is inside the first SavedItem
    expect(items[0].textContent).toContain('Moffat Tunnel');
  });

  it('shows Phase-2 dive placeholder (no network) when item is tellmore and no dive', async () => {
    const favs = [makeFav('f1', 1000, 'tellmore')];
    render(SavedList, { props: { favorites: favs } });
    // Click the item to open detail
    const item = screen.getByRole('listitem');
    await fireEvent.click(item);
    // Dive placeholder should appear
    expect(screen.getByText(/available online \(coming soon\)/i)).toBeTruthy();
  });

  it('Phase-2 placeholder is shown without any network call', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const favs = [makeFav('f1', 1000, 'tellmore')];
    render(SavedList, { props: { favorites: favs } });
    const item = screen.getByRole('listitem');
    await fireEvent.click(item);
    expect(screen.getByText(/available online \(coming soon\)/i)).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

// ── capture(note) → Saved flow (real Favorites + InMemoryAdapter) ─────────────

describe('capture → Saved flow (real Favorites)', () => {
  it('add() then list() returns the item with note and kind', async () => {
    const fav = new Favorites(new InMemoryAdapter(), {
      now: () => 1000,
      genId: () => 'test-id',
    });
    await fav.add(UNIT_A, '58', POSITION, 'star', 'Loved the history');
    const items = await fav.list();
    expect(items).toHaveLength(1);
    expect(items[0].id).toBe('test-id');
    expect(items[0].kind).toBe('star');
    expect(items[0].note).toBe('Loved the history');
    expect(items[0].unitSnapshot.place).toBe('Denver Union Station');
    expect(items[0].createdAt).toBe(1000);
  });

  it('add() without note stores undefined note (no property)', async () => {
    const fav = new Favorites(new InMemoryAdapter());
    await fav.add(UNIT_B, '58', POSITION, 'tellmore');
    const items = await fav.list();
    expect(items[0].note).toBeUndefined();
    expect(items[0].kind).toBe('tellmore');
  });

  it('multiple captures list sorted newest-first in SavedList component', async () => {
    const adapter = new InMemoryAdapter();
    const fav = new Favorites(adapter, { now: (() => { let t = 0; return () => ++t * 100; })() });
    await fav.add(UNIT_A, '58', POSITION, 'star');         // createdAt=100
    await fav.add(UNIT_B, '58', POSITION, 'tellmore', 'note'); // createdAt=200
    const items = await fav.list();
    render(SavedList, { props: { favorites: items } });
    const listItems = screen.getAllByRole('listitem');
    // newest (Moffat Tunnel, createdAt=200) should be first
    expect(listItems[0].textContent).toContain('Moffat Tunnel');
  });
});
