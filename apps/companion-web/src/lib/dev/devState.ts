// DEV-ONLY: shared module-level state for development affordances.
// Both the layout tick and SettingsView read/write this module.
// The simulator instance lives here so the layout can call step() on every tick.

import type { TripSimulator } from './tripSimulator';

// ── DEV state singleton ───────────────────────────────────────────────────────

/** The active TripSimulator, or null if not yet created. */
let _simulator: TripSimulator | null = null;

/**
 * Whether simulation is currently running.
 * Tracked separately so SettingsView can initialize its checkbox from this
 * value after tab navigation (the local `simRunning` $state resets on remount).
 */
let _running = false;

export const devState = {
  /** Returns the simulator if it exists, regardless of running state. */
  getSimulator(): TripSimulator | null {
    return _simulator;
  },

  /** Returns true when simulation is active. */
  isRunning(): boolean {
    return _running;
  },

  /** Set (or clear) the active simulator. Called by SettingsView. */
  setSimulator(sim: TripSimulator | null): void {
    _simulator = sim;
  },

  /** Update the running flag. Called by SettingsView on toggle. */
  setRunning(running: boolean): void {
    _running = running;
  },
};
// ── end DEV ──────────────────────────────────────────────────────────────────
