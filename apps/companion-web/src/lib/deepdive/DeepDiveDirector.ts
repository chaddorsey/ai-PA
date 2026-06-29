/**
 * DeepDiveDirector.ts
 *
 * On each position update, finds unseen deep-dives whose trigger window
 * (trigger_mile ≤ mile < mile+5) intersects the current position.
 *
 * Behaviour driven by appState.settings.featuredStories:
 *   'offer'  → set appState.pendingDeepDive (drives the DeepDiveOffer banner)
 *   'auto'   → play narration audio + suppress regular squibs until it ends
 *   'off'    → do nothing
 *
 * Each deep-dive is offered/played at most once per session (tracked by seenIds).
 */

import type { DeepDive, Position } from 'companion-core';
import { appState } from '$lib/core/AppState.svelte';
import { getOrchestrator } from '$lib/core/PlaybackOrchestrator';
import { deepdiveState } from './deepdiveState.svelte';

export class DeepDiveDirector {
  /**
   * Call this from the layout tick on every position update.
   * No-op when the bundle has no deepdives or featuredStories is 'off'.
   */
  update(position: Position): void {
    const mode = appState.settings.featuredStories;
    if (mode === 'off') return;

    const dives = appState.bundle?.deepdives;
    if (!dives || dives.length === 0) return;

    const mile = position.mile;

    // Find the first unseen deep-dive in the trigger window
    const candidate = dives.find(
      (dd) =>
        dd.trigger_mile <= mile &&
        mile < dd.mile + 5 &&
        !deepdiveState.isSeen(dd.id),
    );

    if (!candidate) return;

    // Mark as seen immediately so we don't offer again
    deepdiveState.markSeen(candidate.id);

    if (mode === 'offer') {
      appState.pendingDeepDive = candidate;
    } else if (mode === 'auto') {
      void this.autoPlay(candidate);
    }
  }

  private async autoPlay(dd: DeepDive): Promise<void> {
    if (!dd.audio) {
      // No audio rendered yet — fall back to offering the read card
      appState.pendingDeepDive = dd;
      return;
    }

    const orch = getOrchestrator();
    if (orch) {
      // Suppress regular squib firing until past mile+5
      orch.silence(dd.mile + 5);
    }

    try {
      const { AudioSession } = await import('$lib/native/plugins');
      await AudioSession.play(dd.audio);
      deepdiveState.markListened(dd.id);
    } catch (e) {
      console.warn('[DeepDiveDirector] autoPlay failed, falling back to offer:', e);
      appState.pendingDeepDive = dd;
    }
  }
}

// Module-level singleton
let _director: DeepDiveDirector | null = null;

export function getDeepDiveDirector(): DeepDiveDirector {
  if (!_director) _director = new DeepDiveDirector();
  return _director;
}
