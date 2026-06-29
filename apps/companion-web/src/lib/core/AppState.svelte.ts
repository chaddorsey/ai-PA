import type { Bundle, Unit, Position } from 'companion-core';
import { Favorites, InMemoryAdapter } from 'companion-core';

export interface Settings {
  fillPct: number;           // 0.0–1.0; default 0.6
  themes: Set<string>;       // empty = all themes
  highlightOnly: boolean;    // only salience >= 4
  audioMode: 'duck' | 'pause' | 'interrupt-spoken';  // default 'interrupt-spoken'
}

class AppStateImpl {
  bundle: Bundle | null = null;
  position: Position | null = null;
  nowPlaying: Unit | null = null;
  settings: Settings = {
    fillPct: 0.6,
    themes: new Set<string>(),
    highlightOnly: false,
    audioMode: 'interrupt-spoken',
  };
  favorites = new Favorites(new InMemoryAdapter());
}

export function createAppState() {
  return new AppStateImpl();
}

export const appState = createAppState();
