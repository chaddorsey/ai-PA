/**
 * scheduler.ts — Plan 2, Task 5
 *
 * Scheduler: given the current position and settings, decide what plays now
 * and what goes into the queue.
 *
 * ── Constants (all documented here) ──────────────────────────────────────────
 *
 * LOOKAHEAD_MI     = 0.15
 *   Start cueing a squib this many miles before its declared milepost.
 *   Ensures audio is ready before the visual sight passes the window.
 *
 * REENTRY_GAP_MI   = 50.0
 *   A forward jump of this many miles triggers re-entry mode. Instead of
 *   firing all skipped squibs, emit at most one orientation unit (the highest-
 *   salience eligible interstitial in the new vicinity).
 *
 * ASSUMED_SPEED_MPH = 79.0
 *   Used to convert mile gaps to seconds when no speed is known.
 *   ~79 mph = typical Chicago–New Orleans speed.
 *
 * ── Invariants ────────────────────────────────────────────────────────────────
 *  - Squibs fire at most once (tracked in playedIds).
 *  - Interstitials never overrun a squib (fit-or-skip rule).
 *  - Interstitials are packed greedily by descending salience to hit fillPct.
 *  - null-theme units PASS through an empty theme filter; are EXCLUDED by an
 *    active (non-empty) theme filter.
 *  - silenceUntilMile = -Infinity when no content is currently scheduled and
 *    no upcoming content exists.
 *  - When content IS playing or queued, silenceUntilMile indicates where it ends.
 */

import type {
  Bundle,
  Unit,
  SquibUnit,
  InterstitialUnit,
  Position,
  SchedulerSettings,
  SchedulerResult,
} from './types.js';

// ── Tuning constants ──────────────────────────────────────────────────────────

/** Start cueing a squib this many miles before its declared milepost. */
const LOOKAHEAD_MI = 0.15;

/**
 * A forward jump of more than this many miles since the last call
 * triggers re-entry mode: at most one orientation unit is emitted.
 */
const REENTRY_GAP_MI = 50.0;

/**
 * Fallback train speed (mph) for converting mile gaps to seconds when no
 * real speed is available.  ~79 mph = Chicago–New Orleans typical.
 */
const ASSUMED_SPEED_MPH = 79.0;

// ── Type guards ───────────────────────────────────────────────────────────────

function isSquib(u: Unit): u is SquibUnit {
  return u.kind === 'squib';
}

function isInterstitial(u: Unit): u is InterstitialUnit {
  return u.kind === 'interstitial';
}

// ── Filter helper ─────────────────────────────────────────────────────────────

/**
 * Returns true if the unit passes both the theme filter and the highlight filter.
 *
 * Theme filter (themes.size > 0):
 *   - Units whose theme is null are EXCLUDED.
 *   - Units whose theme is not in the set are EXCLUDED.
 *   - Units whose theme IS in the set PASS.
 *
 * Empty theme set: all non-null themes pass; null-theme units ALSO pass.
 *
 * highlightOnly: only salience >= 4 passes.
 */
function passesFilter(u: Unit, settings: SchedulerSettings): boolean {
  if (settings.highlightOnly && u.salience < 4) return false;
  if (settings.themes.size > 0) {
    // Active theme filter — null theme is excluded
    if (u.theme === null) return false;
    if (!settings.themes.has(u.theme)) return false;
  }
  return true;
}

// ── Scheduler ─────────────────────────────────────────────────────────────────

export class Scheduler {
  private readonly bundle: Bundle;
  private readonly settings: SchedulerSettings;

  /** IDs of squibs (and interstitials) already returned as nowPlaying. */
  private readonly playedIds: Set<string> = new Set();

  /** Mile at the last select() call (used for re-entry detection). */
  private lastMile: number | null = null;

  constructor(bundle: Bundle, settings: SchedulerSettings) {
    this.bundle = bundle;
    this.settings = settings;
  }

  /**
   * Select what plays at the current position.
   *
   * Returns:
   *   nowPlaying  — the unit that starts playing right now (or null for silence)
   *   queue       — upcoming units to pre-load (may be empty)
   *   silenceUntilMile — sentinel -Infinity when there is no scheduled future content;
   *                      otherwise the mile at which the next content starts/continues
   */
  select(position: Position): SchedulerResult {
    const mile = position.mile;

    // ── Re-entry detection ────────────────────────────────────────────────────
    const gap = this.lastMile !== null ? mile - this.lastMile : 0;
    const isReEntry = this.lastMile !== null && gap > REENTRY_GAP_MI;
    this.lastMile = mile;

    // ── Re-entry mode: skip the backlog, emit at most one orientation unit ────
    if (isReEntry) {
      return this.handleReEntry(mile);
    }

    // ── 1. Check for a due squib ──────────────────────────────────────────────
    // A squib is "due" when mile >= squib.mile - LOOKAHEAD_MI and it hasn't fired yet.
    const dueSquib = this.findDueSquib(mile);

    if (dueSquib !== null) {
      this.playedIds.add(dueSquib.id);
      const silenceUntilMile = dueSquib.mile +
        (dueSquib.dur_s / 3600) * ASSUMED_SPEED_MPH;
      return {
        nowPlaying: dueSquib,
        queue: [],
        silenceUntilMile,
      };
    }

    // ── 2. Find next squib to compute gap ────────────────────────────────────
    const nextSquib = this.findNextSquib(mile);
    // Pack interstitials up until LOOKAHEAD_MI before the next squib triggers
    const gapEndMile = nextSquib != null
      ? nextSquib.mile - LOOKAHEAD_MI
      : this.legEndMile();
    const gapMi = Math.max(0, gapEndMile - mile);
    // Time available in seconds for interstitial fill
    const gapSec = (gapMi / ASSUMED_SPEED_MPH) * 3600;
    const fillBudgetSec = gapSec * this.settings.fillPct;

    // ── 3. Pack interstitials into the gap ────────────────────────────────────
    const { nowPlaying, queue } = this.packInterstitials(mile, fillBudgetSec, gapEndMile);

    // ── 4. Compute silenceUntilMile ───────────────────────────────────────────
    let silenceUntilMile: number;
    if (nowPlaying !== null) {
      // Content starts now — silence ends when content ends
      const nowDurMi = (nowPlaying.dur_s / 3600) * ASSUMED_SPEED_MPH;
      silenceUntilMile = mile + nowDurMi;
    } else if (nextSquib !== null) {
      // Next scheduled event is a squib
      silenceUntilMile = nextSquib.mile - LOOKAHEAD_MI;
    } else {
      // No content scheduled at all
      silenceUntilMile = -Infinity;
    }

    return { nowPlaying, queue, silenceUntilMile };
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  /**
   * Find the highest-priority squib that is due at this mile:
   *   - not yet played
   *   - passes filters
   *   - mile is within [squib.mile - LOOKAHEAD_MI, squib.mile + LOOKAHEAD_MI]
   *     (backward tolerance handles large step sizes without re-triggering far-past squibs)
   *
   * Returns the earliest (lowest mile) due squib, or null.
   */
  private findDueSquib(mile: number): SquibUnit | null {
    let best: SquibUnit | null = null;
    for (const unit of this.bundle.units) {
      if (!isSquib(unit)) continue;
      if (this.playedIds.has(unit.id)) continue;
      if (!passesFilter(unit, this.settings)) continue;
      // Due window: train has reached or just passed the squib milepost
      if (
        mile >= unit.mile - LOOKAHEAD_MI &&
        mile <= unit.mile + LOOKAHEAD_MI
      ) {
        if (best === null || unit.mile < best.mile) {
          best = unit;
        }
      }
    }
    return best;
  }

  /**
   * Find the next unplayed squib ahead of the current mile.
   * Returns the squib with the lowest mile > (current mile - LOOKAHEAD_MI), or null.
   */
  private findNextSquib(mile: number): SquibUnit | null {
    let best: SquibUnit | null = null;
    for (const unit of this.bundle.units) {
      if (!isSquib(unit)) continue;
      if (this.playedIds.has(unit.id)) continue;
      if (!passesFilter(unit, this.settings)) continue;
      // A future squib: its milepost is far enough ahead that it hasn't triggered yet
      if (unit.mile > mile + LOOKAHEAD_MI) {
        if (best === null || unit.mile < best.mile) {
          best = unit;
        }
      }
    }
    return best;
  }

  /**
   * Greedy pack interstitials into the gap.
   * - Considers interstitials whose range covers territory ahead of us
   *   (to_mi > mile): the train will enter that range during the gap.
   * - Sorted by descending salience.
   * - Fit-or-skip: an interstitial is skipped if it can't complete before gapEndMile.
   * - Budget (fillBudgetSec) limits total duration.
   *
   * Returns { nowPlaying, queue }.
   */
  private packInterstitials(
    mile: number,
    fillBudgetSec: number,
    gapEndMile: number,
  ): { nowPlaying: Unit | null; queue: Unit[] } {
    if (fillBudgetSec <= 0) {
      return { nowPlaying: null, queue: [] };
    }

    // Candidates: unplayed interstitials with territory ahead of us in the gap
    const candidates: InterstitialUnit[] = [];
    for (const unit of this.bundle.units) {
      if (!isInterstitial(unit)) continue;
      if (this.playedIds.has(unit.id)) continue;
      if (!passesFilter(unit, this.settings)) continue;
      // The interstitial must have territory that overlaps with the gap ahead
      // Condition: to_mi > mile AND from_mi < gapEndMile
      if (unit.to_mi > mile && unit.from_mi < gapEndMile) {
        candidates.push(unit);
      }
    }

    // Sort by descending salience (ties broken by id for determinism)
    candidates.sort((a, b) =>
      b.salience !== a.salience
        ? b.salience - a.salience
        : a.id.localeCompare(b.id),
    );

    const selected: Unit[] = [];
    let usedSec = 0;

    for (const unit of candidates) {
      if (this.playedIds.has(unit.id)) continue;

      // Fit-or-skip: this interstitial + all already-selected must finish before gapEndMile
      const endSec = usedSec + unit.dur_s;
      const completionMile = mile + (endSec / 3600) * ASSUMED_SPEED_MPH;
      if (completionMile > gapEndMile) continue;

      // Budget check
      if (endSec > fillBudgetSec) continue;

      selected.push(unit);
      this.playedIds.add(unit.id);
      usedSec += unit.dur_s;
    }

    if (selected.length === 0) {
      return { nowPlaying: null, queue: [] };
    }

    return { nowPlaying: selected[0], queue: selected.slice(1) };
  }

  /**
   * Handle re-entry after a large forward jump.
   * Emits at most ONE orientation unit (highest-salience eligible interstitial
   * in the new vicinity). Does NOT fire skipped squibs.
   */
  private handleReEntry(mile: number): SchedulerResult {
    // Mark all squibs behind the new position as played (skip them silently)
    for (const unit of this.bundle.units) {
      if (!isSquib(unit)) continue;
      // Skip squibs that are behind the new position
      if (unit.mile < mile - LOOKAHEAD_MI && !this.playedIds.has(unit.id)) {
        this.playedIds.add(unit.id);
      }
    }

    // Check if a squib is immediately due at the new position
    const dueSquib = this.findDueSquib(mile);
    if (dueSquib !== null) {
      this.playedIds.add(dueSquib.id);
      return {
        nowPlaying: dueSquib,
        queue: [],
        silenceUntilMile: dueSquib.mile + (dueSquib.dur_s / 3600) * ASSUMED_SPEED_MPH,
      };
    }

    // Find next squib and gap
    const nextSquib = this.findNextSquib(mile);
    const gapEndMile = nextSquib != null
      ? nextSquib.mile - LOOKAHEAD_MI
      : this.legEndMile();
    const gapMi = Math.max(0, gapEndMile - mile);
    const gapSec = (gapMi / ASSUMED_SPEED_MPH) * 3600;
    const fillBudgetSec = gapSec * this.settings.fillPct;

    if (fillBudgetSec <= 0) {
      const silenceUntilMile = nextSquib != null
        ? nextSquib.mile - LOOKAHEAD_MI
        : -Infinity;
      return { nowPlaying: null, queue: [], silenceUntilMile };
    }

    // Find candidates for orientation unit
    const candidates: InterstitialUnit[] = [];
    for (const unit of this.bundle.units) {
      if (!isInterstitial(unit)) continue;
      if (this.playedIds.has(unit.id)) continue;
      if (!passesFilter(unit, this.settings)) continue;
      if (unit.to_mi > mile && unit.from_mi < gapEndMile) {
        candidates.push(unit);
      }
    }

    candidates.sort((a, b) =>
      b.salience !== a.salience ? b.salience - a.salience : a.id.localeCompare(b.id),
    );

    // Emit at most ONE orientation unit
    for (const orient of candidates) {
      const completionMile = mile + (orient.dur_s / 3600) * ASSUMED_SPEED_MPH;
      if (completionMile > gapEndMile) continue;
      if (orient.dur_s > fillBudgetSec) continue;

      this.playedIds.add(orient.id);
      return {
        nowPlaying: orient,
        queue: [],
        silenceUntilMile: mile + (orient.dur_s / 3600) * ASSUMED_SPEED_MPH,
      };
    }

    const silenceUntilMile = nextSquib != null
      ? nextSquib.mile - LOOKAHEAD_MI
      : -Infinity;
    return { nowPlaying: null, queue: [], silenceUntilMile };
  }

  /** The mile at the end of the leg's position table (or a large default). */
  private legEndMile(): number {
    const table = this.bundle.position_table;
    if (table.length > 0) return table[table.length - 1][1];
    // Fallback: last squib mile
    let max = 0;
    for (const u of this.bundle.units) {
      if (isSquib(u) && u.mile > max) max = u.mile;
    }
    return max > 0 ? max : 1000;
  }
}
