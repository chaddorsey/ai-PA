import type { Bundle, Unit, Position, DeepDive } from 'companion-core';
import { Favorites, InMemoryAdapter } from 'companion-core';

export interface Settings {
  fillPct: number;           // 0.0–1.0; default 0.6
  themes: Set<string>;       // empty = all themes
  highlightOnly: boolean;    // only salience >= 4
  audioMode: 'duck' | 'pause' | 'interrupt-spoken';  // default 'interrupt-spoken'
  /** Controls how featured deep-dive stories are surfaced. Default: 'offer'. */
  featuredStories: 'offer' | 'auto' | 'off';
}

// ── createAppState ─────────────────────────────────────────────────────────────
// Returns a reactive object backed by Svelte 5 $state runes.
// Each top-level field is a getter/setter pair over a rune cell so that
// components reading any field re-render automatically when it changes.

export function createAppState() {
  let bundle = $state<Bundle | null>(null);
  let position = $state<Position | null>(null);
  let nowPlaying = $state<Unit | null>(null);
  let pendingDeepDive = $state<DeepDive | null>(null);
  const settings = $state<Settings>({
    fillPct: 0.6,
    themes: new Set<string>(),
    highlightOnly: false,
    audioMode: 'interrupt-spoken',
    featuredStories: 'offer',
  });
  // favorites is not reactive via $state — it is an object with methods.
  // Components don't read it directly in templates; it is used imperatively.
  const favorites = new Favorites(new InMemoryAdapter());

  return {
    get bundle() { return bundle; },
    set bundle(v: Bundle | null) { bundle = v; },

    get position() { return position; },
    set position(v: Position | null) { position = v; },

    get nowPlaying() { return nowPlaying; },
    set nowPlaying(v: Unit | null) { nowPlaying = v; },

    /** Pending deep-dive offer — set by DeepDiveDirector; cleared on dismiss or auto-play. */
    get pendingDeepDive() { return pendingDeepDive; },
    set pendingDeepDive(v: DeepDive | null) { pendingDeepDive = v; },

    // settings is a reactive object; mutations to its fields are tracked
    get settings() { return settings; },

    // favorites instance — not reactive, used imperatively
    get favorites() { return favorites; },
  };
}

// Singleton exported for use across the app
export const appState = createAppState();
