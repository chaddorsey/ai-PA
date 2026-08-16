/**
 * routing/landing.ts — where an agent-addressed message LANDS (R13, first and last clauses).
 *
 * Precedence, exactly as decided: explicit tag → the registry row whose label matches; else
 * the agent's DEFAULT thread (a registry row stamped `origin.default`); else the agent's first
 * healthy row. Relevance-inferred landing (R13's middle clause) is deliberately out of this
 * plan. No row → null, and the caller must answer with a VISIBLE rejection (G5), never a
 * silent drop.
 */

import type { Registry, RegistryRow } from "../registry.js";

export function resolveLanding(
  registry: Registry,
  agentId: string,
  tag: string | undefined,
): RegistryRow | null {
  const rows = registry.list().filter((r) => r.agent_id === agentId && r.broken === null);
  if (rows.length === 0) return null;
  if (tag) {
    const byLabel = rows.find((r) => r.label === tag);
    if (byLabel) return byLabel;
    // An explicit tag that matches nothing is a MISS, not a shrug: falling through to the
    // default thread would land the message somewhere the sender did not name.
    return null;
  }
  const dflt = rows.find((r) => r.origin.default === true);
  if (dflt) return dflt;
  const hot = rows.find((r) => r.temp === "hot");
  return hot ?? rows[0] ?? null;
}
