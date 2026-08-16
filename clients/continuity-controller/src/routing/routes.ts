/**
 * routing/routes.ts — the direct lane's route table (R23/R25/R26): explicit `@alias`
 * addresses, per-thread bindings, and Kinara-authored rules via `manage_routes`.
 *
 * The load-bearing property is in `resolveSend`: a route resolves BEFORE any model call —
 * address match → target `{specialist, conversation}`; bound thread → everything routes until
 * unbound; **an explicit `@address` always beats any authored route or binding**. Every
 * mutation is journaled with its author (R25's audit requirement); by the documented-risk
 * decision 2026-08-15 there are no confirmation gates or rate caps in the initial build.
 * Targets are limited to REGISTRY-KNOWN specialists — a route must point at a real runtime.
 */

import type { DatabaseSync } from "node:sqlite";
import type { TurnJournal } from "../journal.js";
import type { Registry, RuntimeRef } from "../registry.js";
import { resolveLanding } from "./landing.js";

export interface RouteRow {
  alias: string;
  agent_id: string;
  conversation_id: string;
  author: string;
}

export interface ResolvedSend {
  target: RuntimeRef;
  text: string;
  /** How the target was chosen — journaled into the turn's origin. */
  via: "address" | "binding";
  alias: string | null;
}

const ADDRESS = /^@([A-Za-z0-9_-]+)\s+(.+)$/s;

export class RouteTable {
  constructor(
    private readonly db: DatabaseSync,
    private readonly registry: Registry,
    private readonly journal: TurnJournal,
  ) {}

  /**
   * Decide where a surface-typed line goes, BEFORE any model call. Returns null for the
   * ordinary lane (the thread the surface is attached to). An `@alias` that matches no route
   * is an ERROR (`RouteMissError`) — silently sending the literal text to Kinara would turn a
   * routing miss into a model call.
   */
  resolveSend(source: RuntimeRef, line: string): ResolvedSend | null {
    const address = ADDRESS.exec(line);
    if (address) {
      const alias = address[1] ?? "";
      const route = this.get(alias);
      if (!route) throw new RouteMissError(`no route named @${alias}`);
      // R26: direct-route specialists are HOT-set members — warm on demand.
      const ref = { agent_id: route.agent_id, conversation_id: route.conversation_id };
      const row = this.registry.get(ref);
      if (!row || row.broken !== null) {
        throw new RouteMissError(`@${alias} points at an unknown or broken runtime`);
      }
      if (row.temp !== "hot") this.registry.setTemp(ref, "hot");
      return { target: ref, text: address[2] ?? "", via: "address", alias };
    }
    const binding = this.getBinding(source);
    if (binding) {
      return {
        target: {
          agent_id: binding.target_agent_id,
          conversation_id: binding.target_conversation_id,
        },
        text: line,
        via: "binding",
        alias: null,
      };
    }
    return null;
  }

  get(alias: string): RouteRow | null {
    const row = this.db.prepare("SELECT * FROM routes WHERE alias = ?").get(alias) as
      | RouteRow
      | undefined;
    return row ?? null;
  }

  list(): RouteRow[] {
    return this.db.prepare("SELECT * FROM routes ORDER BY alias").all() as unknown as RouteRow[];
  }

  /**
   * Create/update a route. `conversationId` optional: defaults to the specialist's landing
   * thread. The target must be registry-known (a route must point at a real agent).
   */
  set(
    alias: string,
    agentId: string,
    conversationId: string | undefined,
    author: string,
  ): RouteRow {
    let target: RuntimeRef | null = null;
    if (conversationId) {
      const row = this.registry.get({ agent_id: agentId, conversation_id: conversationId });
      target =
        row && row.broken === null ? { agent_id: agentId, conversation_id: conversationId } : null;
    } else {
      const landed = resolveLanding(this.registry, agentId, undefined);
      target = landed
        ? { agent_id: landed.agent_id, conversation_id: landed.conversation_id }
        : null;
    }
    if (!target) {
      throw new RouteMissError(
        `route @${alias} must point at a registry-known specialist (agent ${agentId}${conversationId ? `, conversation ${conversationId}` : ""})`,
      );
    }
    const now = new Date().toISOString();
    this.db
      .prepare(
        `INSERT INTO routes (alias, agent_id, conversation_id, author, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT (alias) DO UPDATE SET
           agent_id = excluded.agent_id, conversation_id = excluded.conversation_id,
           author = excluded.author, updated_at = excluded.updated_at`,
      )
      .run(alias, target.agent_id, target.conversation_id, author, now, now);
    // R25: every route mutation is journaled with its author — the audit trail IS the control.
    this.journal.record({
      runtime: target,
      kind: "route_mutation",
      payload: { op: "set", alias, author },
    });
    return { alias, agent_id: target.agent_id, conversation_id: target.conversation_id, author };
  }

  delete(alias: string, author: string): boolean {
    const existing = this.get(alias);
    if (!existing) return false;
    this.db.prepare("DELETE FROM routes WHERE alias = ?").run(alias);
    this.journal.record({
      runtime: { agent_id: existing.agent_id, conversation_id: existing.conversation_id },
      kind: "route_mutation",
      payload: { op: "delete", alias, author },
    });
    return true;
  }

  /** Bind a source thread: until unbound, its plain messages route to the alias's target. */
  bind(source: RuntimeRef, alias: string, author: string): RouteRow {
    const route = this.get(alias);
    if (!route) throw new RouteMissError(`no route named @${alias}`);
    const now = new Date().toISOString();
    this.db
      .prepare(
        `INSERT INTO bindings
           (source_agent_id, source_conversation_id, target_agent_id, target_conversation_id, author, created_at)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT (source_agent_id, source_conversation_id) DO UPDATE SET
           target_agent_id = excluded.target_agent_id,
           target_conversation_id = excluded.target_conversation_id,
           author = excluded.author, created_at = excluded.created_at`,
      )
      .run(
        source.agent_id,
        source.conversation_id,
        route.agent_id,
        route.conversation_id,
        author,
        now,
      );
    this.journal.record({
      runtime: source,
      kind: "route_mutation",
      payload: { op: "bind", alias, author },
    });
    return route;
  }

  unbind(source: RuntimeRef, author: string): boolean {
    const existing = this.getBinding(source);
    if (!existing) return false;
    this.db
      .prepare("DELETE FROM bindings WHERE source_agent_id = ? AND source_conversation_id = ?")
      .run(source.agent_id, source.conversation_id);
    this.journal.record({
      runtime: source,
      kind: "route_mutation",
      payload: { op: "unbind", author },
    });
    return true;
  }

  getBinding(source: RuntimeRef): {
    target_agent_id: string;
    target_conversation_id: string;
  } | null {
    const row = this.db
      .prepare("SELECT * FROM bindings WHERE source_agent_id = ? AND source_conversation_id = ?")
      .get(source.agent_id, source.conversation_id) as
      | { target_agent_id: string; target_conversation_id: string }
      | undefined;
    return row ?? null;
  }
}

export class RouteMissError extends Error {
  override name = "RouteMissError";
}
