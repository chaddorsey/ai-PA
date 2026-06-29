/**
 * AudioSession — Capacitor plugin bridge.
 *
 * On iOS: delegates to AudioSessionPlugin.swift (AVAudioPlayer + AVAudioSession).
 *
 * THREE SESSION MODES (Plan 0 §F):
 *   'duck'             — .playback + .duckOthers; session stays ACTIVE the whole journey;
 *                        music drops to system-fixed low level while narrating, restores between bursts.
 *   'pause'            — .playback (no mix); setActive(false, .notifyOthersOnDeactivation) after each
 *                        talking burst; music fully pauses/resumes each burst (the churn tradeoff).
 *   'interrupt-spoken' — .duckOthers + .interruptSpokenAudioAndMixWithOthers; ducks music but
 *                        pauses other spoken audio (podcasts/audiobooks).
 *
 *   DEFAULT = duck music + interrupt spoken (smart combo). The session is only fully deactivated
 *   on a real full stop (silence/quit). The Swift plugin's interruptionNotification handler
 *   automatically resumes on .ended with .shouldResume.
 *
 * Matches the locked Plan 0 §F contract:
 *   AudioSession.setMode(mode)  → Promise<void>
 *   AudioSession.play(fileUri)  → Promise<void>
 *   AudioSession.pause()        → Promise<void>
 *   AudioSession.resume()       → Promise<void>
 *   AudioSession.setRate(r)     → Promise<void>
 *   AudioSession.addListener('ended'|'interrupt', cb) → { remove() }
 */
import { registerPlugin } from '@capacitor/core';

export type AudioMode = 'duck' | 'pause' | 'interrupt-spoken';
export type AudioEventName = 'ended' | 'interrupt';

interface AudioSessionNativePlugin {
  setMode(opts: { mode: AudioMode }): Promise<void>;
  play(opts: { fileUri: string }): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  setRate(opts: { rate: number }): Promise<void>;
  addListener(event: AudioEventName, cb: (data: Record<string, unknown>) => void): { remove(): void };
}

const _plugin = registerPlugin<AudioSessionNativePlugin>('AudioSession');

export const AudioSession = {
  /**
   * Set the audio session interaction mode.
   * Call before or after play(); the Swift side applies the appropriate AVAudioSession
   * category options and re-activates if needed.
   */
  setMode(mode: AudioMode): Promise<void> {
    return _plugin.setMode({ mode });
  },

  /**
   * Play an MP3 file by its native absolute URI.
   * Obtain the URI via BundleStore.getPath(legId) then Capacitor.convertFileSrc().
   * The current session mode (set via setMode) governs ducking behaviour.
   */
  play(fileUri: string): Promise<void> {
    return _plugin.play({ fileUri });
  },

  pause(): Promise<void> {
    return _plugin.pause();
  },

  resume(): Promise<void> {
    return _plugin.resume();
  },

  /**
   * Set playback rate (0.5–2.0 typical range; 1.0 = normal speed).
   * Applied immediately to the current AVAudioPlayer.
   */
  setRate(r: number): Promise<void> {
    return _plugin.setRate({ rate: r });
  },

  /**
   * Subscribe to 'ended' (file played to completion) or 'interrupt' (phone call / Siri).
   * The 'interrupt' callback receives { type: 'began' | 'ended' }.
   * Returns a handle with .remove() to unsubscribe.
   */
  addListener(
    event: AudioEventName,
    cb: (data: Record<string, unknown>) => void,
  ): { remove(): void } {
    return _plugin.addListener(event, cb);
  },
};
