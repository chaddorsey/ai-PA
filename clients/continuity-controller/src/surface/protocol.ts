/**
 * surface/protocol.ts — the tiered controller↔surface contract (R28), versioned from day one.
 *
 * The capability-set taxonomy pinned by plan C5 (the origin deferred it here):
 *   core      — mandatory: attach · replay · send · presence
 *   abort     — operator-initiated turn kill
 *   approvals — receive approval requests, answer them (arbitrated first-answer-wins)
 *   rail      — conversation CRUD (C9)
 *   notify    — awareness rendering (C7)
 *   direct    — direct-lane addressing (C8)
 *   subagent  — subagent-state rendering
 *
 * Degradation rules (R28 — degrade, never drop): approvals → another capable surface or
 * held-pending + unseen marker; notify → unseen markers; everything else — the feature is
 * simply absent for that surface. An UNKNOWN capability string is ignored with a warning in
 * `attach_ok.warnings`, never a rejection: an older controller must not lock out a newer
 * surface.
 */

export const SURFACE_PROTOCOL_VERSION = 1;

export const CAPABILITIES = [
  "core",
  "abort",
  "approvals",
  "rail",
  "notify",
  "direct",
  "subagent",
] as const;
export type Capability = (typeof CAPABILITIES)[number];

export interface RuntimeAddress {
  agent_id: string;
  conversation_id: string;
}

/** surface → controller */
export interface AttachFrame {
  type: "attach";
  token: string;
  protocol_version: number;
  capabilities: string[];
  runtime: RuntimeAddress;
  /** Last journal row id this surface has seen for the runtime; null = tail only. */
  cursor: number | null;
}
export interface SendFrame {
  type: "send";
  request_id: string;
  text: string;
}
export interface PresenceFrame {
  type: "presence";
  state: "focused" | "background" | "gone";
}
export interface AbortFrame {
  type: "abort";
  request_id: string;
}
export interface ApprovalAnswerFrame {
  type: "approval_answer";
  approval_id: string;
  decision: { behavior: "allow" | "deny"; message?: string };
}
export interface BindFrame {
  type: "bind";
  request_id: string;
  alias: string;
}
export interface UnbindFrame {
  type: "unbind";
  request_id: string;
}
export type SurfaceCommand =
  | AttachFrame
  | SendFrame
  | PresenceFrame
  | AbortFrame
  | ApprovalAnswerFrame
  | BindFrame
  | UnbindFrame;

/** controller → surface */
export interface AttachOkFrame {
  type: "attach_ok";
  session_id: string;
  protocol_version: number;
  runtime: RuntimeAddress;
  /** Journal rows the surface missed, oldest first; cursor advances to `cursor`. */
  replay: SurfaceEvent[];
  cursor: number;
  warnings: string[];
}
export interface AttachDeniedFrame {
  type: "attach_denied";
  reason: string;
}
export interface SurfaceEvent {
  type: "event";
  /** Journal row id — the replay cursor. Strictly increasing per runtime. */
  id: number;
  kind: string;
  client_message_id: string | null;
  payload: Record<string, unknown>;
  at: string;
}
export interface SendOkFrame {
  type: "send_ok";
  request_id: string;
  client_message_id: string;
}
export interface AbortOkFrame {
  type: "abort_ok";
  request_id: string;
  aborted: boolean;
}
export interface ApprovalRequestFrame {
  type: "approval_request";
  approval_id: string;
  runtime: RuntimeAddress;
  request: Record<string, unknown>;
}
export interface ApprovalResolvedFrame {
  type: "approval_resolved";
  approval_id: string;
  decision: { behavior: "allow" | "deny" };
  /** Which session's answer won; "controller" for internally-resolved. */
  by: string;
}
export interface SurfaceErrorFrame {
  type: "error";
  request_id?: string;
  message: string;
}

export class SurfaceProtocolError extends Error {
  override name = "SurfaceProtocolError";
}

/** Parse + validate one surface→controller frame. Throws SurfaceProtocolError on junk. */
export function parseSurfaceCommand(raw: string): SurfaceCommand {
  let frame: Record<string, unknown>;
  try {
    frame = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    throw new SurfaceProtocolError("not JSON");
  }
  const type = frame.type;
  if (type === "attach") {
    if (typeof frame.token !== "string") throw new SurfaceProtocolError("attach: missing token");
    if (typeof frame.protocol_version !== "number")
      throw new SurfaceProtocolError("attach: missing protocol_version");
    if (!Array.isArray(frame.capabilities))
      throw new SurfaceProtocolError("attach: missing capabilities");
    const runtime = frame.runtime as RuntimeAddress | undefined;
    if (
      !runtime ||
      typeof runtime.agent_id !== "string" ||
      typeof runtime.conversation_id !== "string"
    )
      throw new SurfaceProtocolError("attach: missing runtime address");
    if (frame.cursor !== null && typeof frame.cursor !== "number")
      throw new SurfaceProtocolError("attach: cursor must be a number or null");
    return frame as unknown as AttachFrame;
  }
  if (type === "send") {
    if (typeof frame.request_id !== "string" || typeof frame.text !== "string")
      throw new SurfaceProtocolError("send: request_id and text required");
    return frame as unknown as SendFrame;
  }
  if (type === "presence") {
    if (frame.state !== "focused" && frame.state !== "background" && frame.state !== "gone")
      throw new SurfaceProtocolError("presence: bad state");
    return frame as unknown as PresenceFrame;
  }
  if (type === "abort") {
    if (typeof frame.request_id !== "string")
      throw new SurfaceProtocolError("abort: request_id required");
    return frame as unknown as AbortFrame;
  }
  if (type === "bind") {
    if (typeof frame.request_id !== "string" || typeof frame.alias !== "string")
      throw new SurfaceProtocolError("bind: request_id and alias required");
    return frame as unknown as BindFrame;
  }
  if (type === "unbind") {
    if (typeof frame.request_id !== "string")
      throw new SurfaceProtocolError("unbind: request_id required");
    return frame as unknown as UnbindFrame;
  }
  if (type === "approval_answer") {
    if (typeof frame.approval_id !== "string")
      throw new SurfaceProtocolError("approval_answer: approval_id required");
    const decision = frame.decision as { behavior?: string } | undefined;
    if (!decision || (decision.behavior !== "allow" && decision.behavior !== "deny"))
      throw new SurfaceProtocolError("approval_answer: decision.behavior must be allow|deny");
    return frame as unknown as ApprovalAnswerFrame;
  }
  throw new SurfaceProtocolError(`unknown surface command: ${String(type)}`);
}
