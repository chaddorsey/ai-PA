/**
 * approvals.ts — surface-facing approval arbitration (plan C5; settled facts from
 * docs/followups/2026-08-13-continuity-remediation-closeout.md).
 *
 * The server broadcasts `control_request` to all subscribers and settles races itself, so the
 * controller answers SEND-THEN-RECORD and unconditionally — a maybe-already-answered approval
 * is answered again rather than dropped (nobody-answers is the one fatal outcome). Surface
 * arbitration is the controller's own, separate layer: first answer wins, later answers see
 * the resolution, and with NO approvals-capable surface attached the request is HELD pending
 * with an unseen marker (recovery across controller restarts rides on `recover_approvals`,
 * which re-broadcasts pending requests on runtime_start).
 */

import type { DatabaseSync } from "node:sqlite";
import type { protocol } from "@ai-pa/letta-continuity-core";
import type { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import type { TurnJournal } from "./journal.js";
import type { RuntimeRef } from "./registry.js";

type ServerFrame = protocol.ServerFrame;

export interface PendingApproval {
  approvalId: string;
  runtime: RuntimeRef;
  request: Record<string, unknown>;
}

export interface ApprovalDecision {
  behavior: "allow" | "deny";
  message?: string;
}

export interface ApprovalArbiterOptions {
  db: DatabaseSync;
  journal: TurnJournal;
  getConnection: () => WsConnection | null;
  /** Fan an approval request out to capable surfaces. Returns how many surfaces got it. */
  broadcast: (approval: PendingApproval) => number;
  /** Tell every capable surface the approval is settled. */
  broadcastResolution: (approvalId: string, decision: ApprovalDecision, by: string) => void;
  onWarn?: (msg: string) => void;
}

export class ApprovalArbiter {
  private readonly pending = new Map<string, PendingApproval>();
  /** Answers this controller already sent — cleared on reconnect (the server may re-ask). */
  private answered = new Set<string>();

  constructor(private readonly opts: ApprovalArbiterOptions) {}

  /** Wire a new connection's frames in; call on every (re)connect. */
  onReconnect(): void {
    // Settled fact: clear the answered-set on reconnect — a recovered (re-broadcast) request
    // must be answerable again, because our previous answer may have died with the socket.
    this.answered = new Set();
  }

  pendingApprovals(): PendingApproval[] {
    return [...this.pending.values()];
  }

  /** Handle one inbound frame; returns true when it consumed a control_request. */
  onFrame(frame: ServerFrame): boolean {
    if (frame.type !== "control_request") return false;
    const requestId = typeof frame.request_id === "string" ? frame.request_id : null;
    if (!requestId) return true;
    const runtime = (frame.runtime as RuntimeRef | undefined) ?? {
      agent_id: (frame.agent_id as string) ?? "",
      conversation_id: (frame.conversation_id as string) ?? "",
    };
    const approval: PendingApproval = {
      approvalId: requestId,
      runtime,
      request: (frame.request as Record<string, unknown>) ?? {},
    };
    this.pending.set(requestId, approval);
    this.opts.journal.record({
      runtime,
      kind: "approval_requested",
      payload: { approval_id: requestId, request: approval.request },
    });
    const reached = this.opts.broadcast(approval);
    if (reached === 0) {
      // Held pending + unseen marker (R28 degradation): nothing is silently lost while nobody
      // capable is attached; a later attach re-delivers via `pendingApprovals()`.
      this.opts.db
        .prepare(
          `INSERT OR IGNORE INTO unseen (agent_id, conversation_id, kind, ref, created_at)
           VALUES (?, ?, 'approval', ?, ?)`,
        )
        .run(runtime.agent_id, runtime.conversation_id, requestId, new Date().toISOString());
      this.opts.journal.record({
        runtime,
        kind: "approval_held_pending",
        payload: { approval_id: requestId },
      });
    }
    return true;
  }

  /**
   * A surface answered. First answer wins; the winner's decision goes to the server
   * SEND-THEN-RECORD; everyone else sees the resolution. Returns false when it was already
   * settled (the caller surfaces that as `approval_resolved`, not an error).
   */
  answer(approvalId: string, decision: ApprovalDecision, by: string): boolean {
    const approval = this.pending.get(approvalId);
    if (!approval || this.answered.has(approvalId)) return false;
    const conn = this.opts.getConnection();
    if (!conn) {
      this.opts.onWarn?.(`approval ${approvalId}: no connection to answer on — still pending`);
      return false;
    }
    // SEND first…
    conn.send({
      type: "input",
      request_id: `apr-${approvalId}`,
      runtime: approval.runtime,
      payload: {
        kind: "approval_response",
        request_id: approvalId,
        decision:
          decision.behavior === "allow"
            ? { behavior: "allow" }
            : { behavior: "deny", message: decision.message ?? "denied by operator" },
      },
    } as ServerFrame);
    // …THEN record. A failed send throws above and leaves the approval answerable.
    this.answered.add(approvalId);
    this.pending.delete(approvalId);
    this.opts.db.prepare("DELETE FROM unseen WHERE kind = 'approval' AND ref = ?").run(approvalId);
    this.opts.journal.record({
      runtime: approval.runtime,
      kind: "approval_answered",
      payload: { approval_id: approvalId, decision: decision.behavior, by },
    });
    this.opts.broadcastResolution(approvalId, decision, by);
    return true;
  }
}
