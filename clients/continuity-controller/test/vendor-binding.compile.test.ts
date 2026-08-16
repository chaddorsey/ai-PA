/**
 * Compile-time binding to the VENDOR protocol types (plan, Key Technical Decisions).
 *
 * `@letta-ai/letta-code` is a devDependency PINNED to the version the supervisor runs, so
 * `npm run typecheck` compiles our wire vocabulary against the shipped `app-server-protocol`
 * export — the institutional learning is that four review rounds transcribed the protocol by
 * hand while these types sat in the installed package. Two bindings:
 *
 *  1. Every string in the core's `Outbound` map must be a `WsProtocolCommandType` — a vendor
 *     rename fails `tsc`, not a 2 a.m. capture session.
 *  2. Representative frames are written as LITERALS `satisfies` the vendor command interfaces,
 *     then runtime-compared with the salvaged builders' output — if a builder drifts from the
 *     vendor shape, one of the two comparisons breaks.
 *
 * (The version-drift complement is the running-server gate: live.detach-hold + the core's
 * app_server_info pin. This file only proves the COMPILED vocabulary.)
 */

import { Outbound, buildRuntimeStart, buildSync } from "@ai-pa/letta-continuity-core/protocol";
import type {
  RuntimeStartCommand,
  SyncCommand,
  WsProtocolCommandType,
} from "@letta-ai/letta-code/app-server-protocol";
import { describe, expect, it } from "vitest";

// ── Binding 1: the outbound vocabulary is vendor-known, checked by tsc ──────────────────────
const OUTBOUND_VOCABULARY = [
  Outbound.appServerInfo,
  Outbound.runtimeStart,
  Outbound.input,
  Outbound.sync,
  Outbound.conversationList,
  Outbound.conversationCreate,
  Outbound.conversationRetrieve,
  Outbound.conversationUpdate,
  Outbound.conversationFork,
  Outbound.conversationMessagesList,
] as const satisfies readonly WsProtocolCommandType[];

describe("vendor protocol binding (0.30.20)", () => {
  it("every outbound command string is part of the vendor's WsProtocolCommandType union", () => {
    // The load-bearing assertion is the `satisfies` above, at compile time; this keeps the
    // vocabulary list itself honest at runtime.
    expect(OUTBOUND_VOCABULARY).toHaveLength(10);
  });

  it("buildRuntimeStart emits exactly the vendor RuntimeStartCommand shape", () => {
    const vendorShaped = {
      type: "runtime_start",
      request_id: "rid-1",
      agent_id: "ag-1",
      conversation_id: "local-conv-1",
      wait_for_replay: true,
    } satisfies RuntimeStartCommand;
    expect(
      buildRuntimeStart(
        "rid-1",
        { agent_id: "ag-1", conversation_id: "local-conv-1" },
        { waitForReplay: true },
      ),
    ).toEqual(vendorShaped);
  });

  it("buildSync emits exactly the vendor SyncCommand shape", () => {
    const vendorShaped = {
      type: "sync",
      request_id: "rid-2",
      runtime: { agent_id: "ag-1", conversation_id: "local-conv-1" },
      recover_approvals: false,
    } satisfies SyncCommand;
    expect(
      buildSync("rid-2", { agent_id: "ag-1", conversation_id: "local-conv-1" }, false),
    ).toEqual(vendorShaped);
  });
});
