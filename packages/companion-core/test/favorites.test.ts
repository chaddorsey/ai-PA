import { describe, it, expect } from 'vitest';
import { Favorites, InMemoryAdapter } from '../src/favorites.js';
import type { DiveCard, Position, Unit } from '../src/types.js';

// ── Deterministic helpers ────────────────────────────────────────────────────

let idCounter = 0;
const genId = () => `test-id-${++idCounter}`;

let clock = 1_000_000;
const now = () => clock;

function makeUnit(overrides: Partial<Unit> = {}): Unit {
  return {
    id: 'u1',
    kind: 'squib',
    mile: 55.0,
    place: 'McComb, MS',
    side: 'left',
    salience: 4,
    theme: 'civil-rights',
    text: 'McComb was a focal point of 1960s civil rights organizing.',
    lat: 31.24,
    lon: -90.45,
    dur_s: 55.0,
    audio: 'audio/u1.mp3',
    ...overrides,
  } as Unit;
}

function makePosition(overrides: Partial<Position> = {}): Position {
  return {
    mile: 55.0,
    lat: 31.24,
    lon: -90.45,
    source: 'gps',
    direction: 1,
    leg: '58',
    stopped: false,
    ...overrides,
  };
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('InMemoryAdapter', () => {
  it('starts empty', async () => {
    const adapter = new InMemoryAdapter();
    expect(await adapter.loadAll()).toHaveLength(0);
  });

  it('save then loadById returns the favorite', async () => {
    const adapter = new InMemoryAdapter();
    const pos = makePosition();
    const fav = {
      id: 'x1',
      leg: '58',
      unitSnapshot: makeUnit(),
      position: pos,
      kind: 'star' as const,
      createdAt: 1_000_000,
    };
    await adapter.save(fav);
    const retrieved = await adapter.loadById('x1');
    expect(retrieved).not.toBeNull();
    expect(retrieved!.id).toBe('x1');
  });

  it('loadById returns null for unknown id', async () => {
    const adapter = new InMemoryAdapter();
    expect(await adapter.loadById('nope')).toBeNull();
  });

  it('update patches existing record', async () => {
    const adapter = new InMemoryAdapter();
    const fav = {
      id: 'x2',
      leg: '58',
      unitSnapshot: makeUnit(),
      position: makePosition(),
      kind: 'star' as const,
      createdAt: 1_000_000,
    };
    await adapter.save(fav);
    await adapter.update('x2', { note: 'patched note' });
    const retrieved = await adapter.loadById('x2');
    expect(retrieved!.note).toBe('patched note');
  });

  it('delete removes the record', async () => {
    const adapter = new InMemoryAdapter();
    const fav = {
      id: 'x3',
      leg: '58',
      unitSnapshot: makeUnit(),
      position: makePosition(),
      kind: 'star' as const,
      createdAt: 1_000_000,
    };
    await adapter.save(fav);
    await adapter.delete('x3');
    expect(await adapter.loadById('x3')).toBeNull();
    expect(await adapter.loadAll()).toHaveLength(0);
  });
});

describe('Favorites.add — star', () => {
  it('adds a star favorite with correct kind and unitSnapshot', async () => {
    idCounter = 0;
    clock = 2_000_000;
    const favs = new Favorites(new InMemoryAdapter(), { now, genId });
    const unit = makeUnit();
    const pos = makePosition();
    const fav = await favs.add(unit, '58', pos, 'star');

    expect(fav.id).toBe('test-id-1');
    expect(fav.createdAt).toBe(2_000_000);
    expect(fav.kind).toBe('star');
    expect(fav.leg).toBe('58');
    expect(fav.unitSnapshot).toEqual(unit);
    expect(fav.position).toEqual(pos);
    expect(fav.note).toBeUndefined();
    expect(fav.dive).toBeUndefined();
  });
});

describe('Favorites.add — tellmore with note', () => {
  it('adds a tellmore favorite with note', async () => {
    idCounter = 0;
    clock = 3_000_000;
    const favs = new Favorites(new InMemoryAdapter(), { now, genId });
    const unit = makeUnit({ id: 'u2', kind: 'interstitial', from_mi: 50, to_mi: 60 } as Partial<Unit>);
    const pos = makePosition({ mile: 52 });
    const fav = await favs.add(unit, '58', pos, 'tellmore', 'This region is fascinating');

    expect(fav.kind).toBe('tellmore');
    expect(fav.note).toBe('This region is fascinating');
  });
});

describe('Favorites.list', () => {
  it('returns all added favorites', async () => {
    idCounter = 0;
    clock = 4_000_000;
    const favs = new Favorites(new InMemoryAdapter(), { now, genId });
    await favs.add(makeUnit(), '58', makePosition(), 'star');
    await favs.add(makeUnit({ id: 'u2' }), '58', makePosition({ mile: 60 }), 'tellmore');
    const list = await favs.list();
    expect(list).toHaveLength(2);
    const kinds = list.map(f => f.kind).sort();
    expect(kinds).toEqual(['star', 'tellmore']);
  });
});

describe('Favorites.get', () => {
  it('returns the favorite by id', async () => {
    idCounter = 0;
    clock = 5_000_000;
    const favs = new Favorites(new InMemoryAdapter(), { now, genId });
    const added = await favs.add(makeUnit(), '58', makePosition(), 'star');
    const retrieved = await favs.get(added.id);
    expect(retrieved.id).toBe(added.id);
    expect(retrieved.kind).toBe('star');
  });

  it('throws when id is not found', async () => {
    idCounter = 0;
    const favs = new Favorites(new InMemoryAdapter(), { now, genId });
    await expect(favs.get('nonexistent')).rejects.toThrow(/not found/i);
  });
});

describe('Favorites.attachDive', () => {
  it('sets dive on the favorite and persists it', async () => {
    idCounter = 0;
    clock = 6_000_000;
    const favs = new Favorites(new InMemoryAdapter(), { now, genId });
    const added = await favs.add(makeUnit(), '58', makePosition(), 'tellmore');

    const dive: DiveCard = {
      body: 'McComb was the site of the first mass student civil rights movement.',
      sources: ['guide/mccomb.md', 'lore/civil-rights.md'],
      createdAt: 7_000_000,
    };

    await favs.attachDive(added.id, dive);

    const retrieved = await favs.get(added.id);
    expect(retrieved.dive).toBeDefined();
    expect(retrieved.dive!.body).toContain('McComb');
    expect(retrieved.dive!.sources).toHaveLength(2);
  });

  it('throws when attaching dive to nonexistent favorite', async () => {
    idCounter = 0;
    const favs = new Favorites(new InMemoryAdapter(), { now, genId });
    const dive: DiveCard = { body: 'body', sources: [], createdAt: 1 };
    await expect(favs.attachDive('nope', dive)).rejects.toThrow(/not found/i);
  });
});
