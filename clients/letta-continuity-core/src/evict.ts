/**
 * evict.ts — the one FIFO eviction loop.
 *
 * This client is meant to sit attached to a constant-on runtime for days, so every remembered id
 * is a slow leak unless something bounds it. Five separate places bounded one — two in
 * `ownership.ts`, two in the terminal's origin caches, one helper in `index.ts` — each with its
 * own hand-rolled `while (size > max)` loop, each independently able to be wrong, and none able to
 * be fixed by fixing another.
 *
 * Sets and Maps both expose `size`, `keys()` and `delete()`, and both preserve insertion order, so
 * one function serves both. Insertion order is what makes this FIFO — the guarantee the callers
 * rely on and none of them stated.
 */

/** The part of Set/Map this needs. Structural, so neither a Set nor a Map is privileged. */
export interface BoundedCollection {
  readonly size: number;
  keys(): IterableIterator<string>;
  delete(key: string): boolean;
}

/**
 * Trim to `max`, oldest first.
 *
 * `onEvict` exists for the caller that keeps a SECOND collection keyed by the same ids
 * (`ownership.ts` holds `foreignRuns` alongside `seenRuns`): without it that site would have to
 * keep its own loop, and the duplication this file removes would grow straight back.
 */
export function evictOldest(
  collection: BoundedCollection,
  max: number,
  onEvict?: (key: string) => void,
): void {
  while (collection.size > max) {
    const oldest = collection.keys().next().value;
    // Defensive rather than reachable: a collection reporting size > 0 with no keys would spin
    // here forever, and an unbounded loop inside the frame handler is a hang, not a leak.
    if (oldest === undefined) break;
    collection.delete(oldest);
    onEvict?.(oldest);
  }
}
