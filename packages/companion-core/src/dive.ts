/**
 * diveGrounding — Phase 2 stub.
 *
 * The DiveGrounding type is the context payload assembled from bundle layers and
 * passed to the dive backend to generate a DiveCard. Full assembly logic is
 * deferred to Phase 2.
 *
 * The stub is exported so Plan 4 can import the type and reference the function
 * signature without a runtime dep on Phase 2 infra.
 */

import type { Bundle, DiveGrounding } from './types.js';

export type { DiveGrounding };

/**
 * Assemble dive-grounding context for a unit from a loaded bundle.
 *
 * @param bundle   The loaded leg bundle.
 * @param unitId   ID of the unit to ground.
 * @param focus    Optional free-text focus hint to narrow the grounding scope.
 * @returns        DiveGrounding context payload.
 *
 * @throws Error   Always — implementation deferred to Phase 2.
 *
 * @phase2
 */
export function diveGrounding(
  _bundle: Bundle,
  _unitId: string,
  _focus?: string,
): DiveGrounding {
  throw new Error('diveGrounding: Phase 2');
}
