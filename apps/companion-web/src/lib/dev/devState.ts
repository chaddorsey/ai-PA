// DEV-ONLY: shared module-level state for development affordances.
// Both the layout tick and SettingsView read/write this module.
// The simulator instance lives here so the layout can call step() on every tick.

import type { TripSimulator } from './tripSimulator';

// ── DEV state singleton ───────────────────────────────────────────────────────

/** The active TripSimulator, or null if not running. */
let _simulator: TripSimulator | null = null;

export const devState = {
  /** Returns the simulator if it is active and running, else null. */
  getSimulator(): TripSimulator | null {
    return _simulator?.running ? _simulator : null;
  },

  /** Set (or clear) the active simulator. Called by SettingsView. */
  setSimulator(sim: TripSimulator | null): void {
    _simulator = sim;
  },
};
// ── end DEV ──────────────────────────────────────────────────────────────────
