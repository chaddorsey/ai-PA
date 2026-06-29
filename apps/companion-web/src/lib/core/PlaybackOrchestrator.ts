import type { Scheduler, Favorites, Position, Unit, Bundle } from 'companion-core';
import type { AudioSessionPlugin } from '$lib/native/plugins';
import { appState } from './AppState.svelte';

export interface PlaybackOrchestratorDeps {
  scheduler: Scheduler;
  audioSession: AudioSessionPlugin;
  favorites: Favorites;
  bundlePath: string;
}

export class PlaybackOrchestrator {
  private readonly scheduler: Scheduler;
  private readonly audioSession: AudioSessionPlugin;
  private readonly favorites: Favorites;
  private readonly bundlePath: string;
  private silenceUntilMile = -Infinity;
  private endedListener: { remove(): void } | null = null;

  constructor(deps: PlaybackOrchestratorDeps) {
    this.scheduler = deps.scheduler;
    this.audioSession = deps.audioSession;
    this.favorites = deps.favorites;
    this.bundlePath = deps.bundlePath;

    this.endedListener = deps.audioSession.addListener('ended', () => {
      const pos = appState.position;
      if (pos) void this.update(pos);
    });
  }

  async update(position: Position): Promise<void> {
    if (position.mile <= this.silenceUntilMile && this.silenceUntilMile !== -Infinity) return;

    const { nowPlaying: selected, silenceUntilMile } = this.scheduler.select(position);

    if (silenceUntilMile !== -Infinity) {
      this.silenceUntilMile = silenceUntilMile;
    }

    if (!selected) return;
    if (selected.id === appState.nowPlaying?.id) return;

    appState.nowPlaying = selected;
    const filename = selected.audio.split('/').pop()!;
    const fileUri = `${this.bundlePath}/audio/${filename}`;
    await this.audioSession.play(fileUri);
    await this.audioSession.setRate(appState.settings.fillPct > 0 ? 1.0 : 1.0); // always 1.0 for now
  }

  async pause(): Promise<void> {
    await this.audioSession.pause();
  }

  async resume(): Promise<void> {
    await this.audioSession.resume();
  }

  async setRate(r: number): Promise<void> {
    await this.audioSession.setRate(r);
  }

  silence(untilMile: number): void {
    this.silenceUntilMile = untilMile;
    appState.nowPlaying = null;
    void this.audioSession.pause();
  }

  async skip(): Promise<void> {
    appState.nowPlaying = null;
    this.silenceUntilMile = -Infinity;
    const pos = appState.position;
    if (pos) await this.update(pos);
  }

  async capture(unit: Unit, kind: 'star' | 'tellmore', note?: string): Promise<void> {
    const bundle = appState.bundle;
    const position = appState.position;
    if (!bundle || !position) return;
    await this.favorites.add(unit, bundle.leg, position, kind, note);
  }

  destroy(): void {
    this.endedListener?.remove();
  }
}

// Module-level singleton (initialized lazily once a bundle is loaded)
let _orchestrator: PlaybackOrchestrator | null = null;

export function getOrchestrator(): PlaybackOrchestrator | null {
  return _orchestrator;
}

export function initOrchestrator(deps: PlaybackOrchestratorDeps): PlaybackOrchestrator {
  _orchestrator?.destroy();
  _orchestrator = new PlaybackOrchestrator(deps);
  return _orchestrator;
}
