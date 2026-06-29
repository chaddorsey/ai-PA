/**
 * SavedList.ts — pure logic functions for the Saved tab.
 * Exported for unit tests; imported by SavedList.svelte and SavedItem.svelte.
 */
import type { Favorite } from 'companion-core';

/**
 * Sort favorites newest-first (by createdAt timestamp, descending).
 * Does NOT mutate the input array.
 */
export function sortFavorites(favs: Favorite[]): Favorite[] {
  return [...favs].sort((a, b) => b.createdAt - a.createdAt);
}

/**
 * Returns true when a favorite has an attached DiveCard (Phase 2).
 */
export function hasDive(fav: Favorite): boolean {
  return fav.dive !== undefined && fav.dive !== null;
}
