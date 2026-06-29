/**
 * SettingsView.ts — pure logic functions for SettingsView.svelte.
 * Exported so they can be tested without a DOM or Svelte runtime.
 */

const VOICE_RATE_MIN = 0.5;
const VOICE_RATE_MAX = 2.0;

/** Minimal AudioSession interface needed by settings logic. */
export interface AudioSessionLike {
  setRate(r: number): unknown; // may be async; we ignore the return value
}

/** Minimal state shape that the pure functions operate on. */
export interface SettingsStateLike {
  settings: {
    voiceRate: number;
    themes: Set<string>;
    [key: string]: unknown;
  };
}

/**
 * Clamp a voice-rate value to the valid range [0.5, 2.0].
 */
export function clampVoiceRate(rate: number): number {
  return Math.min(VOICE_RATE_MAX, Math.max(VOICE_RATE_MIN, rate));
}

/**
 * Apply a voice-rate change: clamp, write to state, and delegate to AudioSession.
 */
export function applyVoiceRateChange(
  rate: number,
  audioSession: AudioSessionLike,
  state: SettingsStateLike,
): void {
  const clamped = clampVoiceRate(rate);
  state.settings.voiceRate = clamped;
  audioSession.setRate(clamped);
}

/**
 * Toggle a theme in/out of the active set.
 *
 * @param theme   Theme name string.
 * @param enabled True to add the theme; false to remove it.
 * @param state   Mutable state object whose settings.themes Set will be mutated.
 */
export function applyThemeChange(
  theme: string,
  enabled: boolean,
  state: SettingsStateLike,
): void {
  if (enabled) {
    state.settings.themes.add(theme);
  } else {
    state.settings.themes.delete(theme);
  }
}
