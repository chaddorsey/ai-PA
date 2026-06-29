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
