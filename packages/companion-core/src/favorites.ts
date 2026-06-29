/**
 * Favorites — bookmarked units from a journey.
 *
 * Design:
 *  - StorageAdapter is injected, so the same Favorites class works with an
 *    in-process InMemoryAdapter (tests), a SQLite adapter (Capacitor), or any
 *    other backend without modification.
 *  - `now` and `genId` are also injectable so tests run deterministically with
 *    no reliance on wall-clock time or crypto.randomUUID().
 */

import type { DiveCard, Favorite, Position, StorageAdapter, Unit } from './types.js';

// ── InMemoryAdapter ───────────────────────────────────────────────────────────

/**
 * Simple in-memory implementation of StorageAdapter.
 * Suitable for tests and as a reference implementation.
 */
export class InMemoryAdapter implements StorageAdapter {
  private readonly store = new Map<string, Favorite>();

  async save(favorite: Favorite): Promise<void> {
    this.store.set(favorite.id, { ...favorite });
  }

  async loadAll(): Promise<Favorite[]> {
    return Array.from(this.store.values());
  }

  async loadById(id: string): Promise<Favorite | null> {
    return this.store.get(id) ?? null;
  }

  async update(id: string, patch: Partial<Favorite>): Promise<void> {
    const existing = this.store.get(id);
    if (!existing) return; // silent no-op; callers check existence before update
    this.store.set(id, { ...existing, ...patch });
  }

  async delete(id: string): Promise<void> {
    this.store.delete(id);
  }
}

// ── Favorites ─────────────────────────────────────────────────────────────────

export interface FavoritesOptions {
  /** Returns current unix ms. Default: Date.now. */
  now?: () => number;
  /** Returns a new unique ID string. Default: crypto.randomUUID(). */
  genId?: () => string;
}

/**
 * Manages bookmarked units for a journey.
 */
export class Favorites {
  private readonly adapter: StorageAdapter;
  private readonly now: () => number;
  private readonly genId: () => string;

  constructor(adapter: StorageAdapter, opts: FavoritesOptions = {}) {
    this.adapter = adapter;
    this.now = opts.now ?? (() => Date.now());
    this.genId = opts.genId ?? (() => crypto.randomUUID());
  }

  /**
   * Add a new favorite for a unit at the current position.
   *
   * @param unit     The unit being favorited (full Unit object stored as snapshot).
   * @param leg      Leg ID string (e.g. "58").
   * @param position Current position at time of favoriting.
   * @param kind     'star' (quick bookmark) or 'tellmore' (requests a dive).
   * @param note     Optional user note.
   * @returns        The newly created Favorite.
   */
  async add(
    unit: Unit,
    leg: string,
    position: Position,
    kind: 'star' | 'tellmore',
    note?: string,
  ): Promise<Favorite> {
    const favorite: Favorite = {
      id: this.genId(),
      leg,
      unitSnapshot: unit,
      position,
      kind,
      createdAt: this.now(),
      ...(note !== undefined ? { note } : {}),
    };
    await this.adapter.save(favorite);
    return favorite;
  }

  /**
   * Return all favorites in insertion order.
   */
  async list(): Promise<Favorite[]> {
    return this.adapter.loadAll();
  }

  /**
   * Return a favorite by ID.
   * @throws Error if not found.
   */
  async get(id: string): Promise<Favorite> {
    const fav = await this.adapter.loadById(id);
    if (!fav) {
      throw new Error(`Favorites.get: favorite "${id}" not found`);
    }
    return fav;
  }

  /**
   * Attach a DiveCard to an existing favorite.
   *
   * @param id   ID of the favorite to update.
   * @param dive The DiveCard to attach.
   * @throws Error if the favorite is not found.
   */
  async attachDive(id: string, dive: DiveCard): Promise<void> {
    // Verify existence first so we throw a clear error rather than a silent no-op.
    const existing = await this.adapter.loadById(id);
    if (!existing) {
      throw new Error(`Favorites.attachDive: favorite "${id}" not found`);
    }
    await this.adapter.update(id, { dive });
  }
}
