/**
 * SettingsWiring tests — pure logic from SettingsView.ts.
 *
 * Tests: applyVoiceRateChange, applyThemeChange, clampVoiceRate.
 * These are framework-agnostic; no DOM or Svelte runtime required.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  applyVoiceRateChange,
  applyThemeChange,
  clampVoiceRate,
} from '$lib/settings/SettingsView';

interface MockAudioSession {
  setRate: ReturnType<typeof vi.fn>;
}

function makeMockState(overrides?: { voiceRate?: number; themes?: Set<string> }) {
  return {
    settings: {
      voiceRate: overrides?.voiceRate ?? 1.0,
      themes: overrides?.themes ?? new Set<string>(['history', 'geology']),
    },
  };
}

// ── applyVoiceRateChange ─────────────────────────────────────────────────────

describe('applyVoiceRateChange', () => {
  let mockAudio: MockAudioSession;

  beforeEach(() => {
    mockAudio = { setRate: vi.fn() };
  });

  it('updates state.settings.voiceRate and calls audioSession.setRate', () => {
    const state = makeMockState();
    applyVoiceRateChange(0.8, mockAudio, state);
    expect(state.settings.voiceRate).toBe(0.8);
    expect(mockAudio.setRate).toHaveBeenCalledWith(0.8);
  });

  it('clamps values below 0.5 to 0.5', () => {
    const state = makeMockState();
    applyVoiceRateChange(0.1, mockAudio, state);
    expect(state.settings.voiceRate).toBe(0.5);
    expect(mockAudio.setRate).toHaveBeenCalledWith(0.5);
  });

  it('clamps values above 2.0 to 2.0', () => {
    const state = makeMockState();
    applyVoiceRateChange(3.5, mockAudio, state);
    expect(state.settings.voiceRate).toBe(2.0);
    expect(mockAudio.setRate).toHaveBeenCalledWith(2.0);
  });

  it('handles exactly 0.5 (lower boundary) without clamping', () => {
    const state = makeMockState();
    applyVoiceRateChange(0.5, mockAudio, state);
    expect(state.settings.voiceRate).toBe(0.5);
    expect(mockAudio.setRate).toHaveBeenCalledWith(0.5);
  });

  it('handles exactly 2.0 (upper boundary) without clamping', () => {
    const state = makeMockState();
    applyVoiceRateChange(2.0, mockAudio, state);
    expect(state.settings.voiceRate).toBe(2.0);
    expect(mockAudio.setRate).toHaveBeenCalledWith(2.0);
  });
});

// ── applyThemeChange ─────────────────────────────────────────────────────────

describe('applyThemeChange', () => {
  it('adds a theme when enabled=true and theme is not in Set', () => {
    const state = makeMockState({ themes: new Set(['history']) });
    applyThemeChange('science', true, state);
    expect(state.settings.themes.has('science')).toBe(true);
    expect(state.settings.themes.has('history')).toBe(true);
  });

  it('removes a theme when enabled=false and theme is in Set', () => {
    const state = makeMockState({ themes: new Set(['history', 'geology']) });
    applyThemeChange('geology', false, state);
    expect(state.settings.themes.has('geology')).toBe(false);
    expect(state.settings.themes.has('history')).toBe(true);
  });

  it('is idempotent: adding a theme already present does not duplicate', () => {
    const state = makeMockState({ themes: new Set(['history']) });
    applyThemeChange('history', true, state);
    expect(state.settings.themes.size).toBe(1);
  });

  it('is safe: removing a theme not in Set does not throw', () => {
    const state = makeMockState({ themes: new Set(['history']) });
    expect(() => applyThemeChange('science', false, state)).not.toThrow();
    expect(state.settings.themes.has('history')).toBe(true);
  });
});

// ── clampVoiceRate ───────────────────────────────────────────────────────────

describe('clampVoiceRate', () => {
  it('returns 0.5 for input below minimum', () => {
    expect(clampVoiceRate(0.0)).toBe(0.5);
    expect(clampVoiceRate(-1)).toBe(0.5);
  });

  it('returns 2.0 for input above maximum', () => {
    expect(clampVoiceRate(2.1)).toBe(2.0);
    expect(clampVoiceRate(100)).toBe(2.0);
  });

  it('returns the value unchanged when within [0.5, 2.0]', () => {
    expect(clampVoiceRate(1.0)).toBe(1.0);
    expect(clampVoiceRate(0.7)).toBe(0.7);
    expect(clampVoiceRate(1.5)).toBe(1.5);
  });

  it('returns 0.5 at the lower boundary', () => {
    expect(clampVoiceRate(0.5)).toBe(0.5);
  });

  it('returns 2.0 at the upper boundary', () => {
    expect(clampVoiceRate(2.0)).toBe(2.0);
  });
});
