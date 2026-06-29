/**
 * devState tests — running-state tracking for the simulate-trip dev toggle.
 *
 * Bug 3 regression: simRunning checkbox was losing state across tab nav because
 * SettingsView's local $state initialised to `false` on remount. devState now
 * holds the canonical running flag so SettingsView can hydrate from it.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { devState } from './devState';

// Reset module-level state before each test by clearing simulator + running flag
beforeEach(() => {
  devState.setSimulator(null);
  devState.setRunning(false);
});

describe('devState running-state', () => {
  it('starts with isRunning()=false', () => {
    expect(devState.isRunning()).toBe(false);
  });

  it('setRunning(true) → isRunning() returns true', () => {
    devState.setRunning(true);
    expect(devState.isRunning()).toBe(true);
  });

  it('setRunning(false) after true → isRunning() returns false', () => {
    devState.setRunning(true);
    devState.setRunning(false);
    expect(devState.isRunning()).toBe(false);
  });

  it('getSimulator() returns null until a simulator is set', () => {
    expect(devState.getSimulator()).toBeNull();
  });

  it('getSimulator() returns the set simulator regardless of running state', () => {
    const fakeSim = { running: false } as never;
    devState.setSimulator(fakeSim);
    expect(devState.getSimulator()).toBe(fakeSim);
  });

  it('setSimulator(null) clears the simulator', () => {
    const fakeSim = { running: true } as never;
    devState.setSimulator(fakeSim);
    devState.setSimulator(null);
    expect(devState.getSimulator()).toBeNull();
  });

  it('running state is independent of whether a simulator is set', () => {
    devState.setRunning(true);
    expect(devState.isRunning()).toBe(true);
    expect(devState.getSimulator()).toBeNull(); // no sim set
  });
});

describe('devState speed persistence', () => {
  beforeEach(() => {
    devState.setRunning(false);
    devState.setSimulator(null);
    // Reset speed to default by calling setSpeed with 120 (default)
    devState.setSpeed(120);
  });

  it('getSpeed() returns 120 by default (default dev speed)', () => {
    expect(devState.getSpeed()).toBe(120);
  });

  it('setSpeed(600) persists and getSpeed() returns 600', () => {
    devState.setSpeed(600);
    expect(devState.getSpeed()).toBe(600);
  });

  it('setSpeed(4) persists and getSpeed() returns 4', () => {
    devState.setSpeed(4);
    expect(devState.getSpeed()).toBe(4);
  });

  it('speed survives a simulated remount (setRunning false + setSimulator null then re-read)', () => {
    // Set a non-default speed
    devState.setSpeed(30);
    // Simulate tab-nav remount: running and simulator are reset, but speed should persist
    devState.setRunning(false);
    devState.setSimulator(null);
    // After "remount", SettingsView reads speed from devState
    expect(devState.getSpeed()).toBe(30);
  });

  it('speed is independent of running state', () => {
    devState.setSpeed(120);
    devState.setRunning(true);
    expect(devState.getSpeed()).toBe(120);
    devState.setRunning(false);
    expect(devState.getSpeed()).toBe(120);
  });
});
