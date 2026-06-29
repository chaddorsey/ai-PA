import { WebPlugin } from '@capacitor/core';
import type { AudioSessionPlugin } from './definitions';

export class AudioSessionWeb extends WebPlugin implements AudioSessionPlugin {
  private audio: HTMLAudioElement | null = null;
  private _unlocked = false;

  /** Unlock AudioContext on first user gesture (iOS Safari requirement) */
  private _ensureUnlocked(): void {
    if (this._unlocked) return;
    this._unlocked = true;
    // create and immediately discard a silent audio element to satisfy Safari's gesture requirement
    const a = new Audio();
    a.play().catch(() => {/* expected to fail silently */});
  }

  async setMode(_options: { mode: 'duck' | 'pause' | 'interrupt-spoken' }): Promise<void> {
    // No-op in browser; mode is handled natively
  }

  async play(options: { fileUri: string }): Promise<void> {
    this._ensureUnlocked();
    if (this.audio) {
      this.audio.pause();
      this.audio.onended = null;
    }
    this.audio = new Audio(options.fileUri);
    this.audio.onended = () => {
      this.notifyListeners('ended', {});
    };
    await this.audio.play();
  }

  async pause(): Promise<void> {
    this.audio?.pause();
  }

  async resume(): Promise<void> {
    await this.audio?.play();
  }

  async setRate(options: { rate: number }): Promise<void> {
    if (this.audio) {
      this.audio.playbackRate = options.rate;
    }
  }
}
