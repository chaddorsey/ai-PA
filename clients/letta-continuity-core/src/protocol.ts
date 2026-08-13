/**
 * protocol.ts — THE SOLE HOME of every Letta App Server WS frame string + shape.
 *
 * Nothing framing-related may live outside this file. Every message-type string,
 * every field name the client reads, and every outbound frame builder is here so a
 * server-protocol drift changes exactly one file and the contract test catches it.
 *
 * Empirically pinned against `letta 0.30.19 (Letta Code)`, `ws://127.0.0.1:4577/ws`
 * (see docs/plans/2026-08-12-multi-surface-ws-spike-findings.md §C/§E and the Unit 4
 * live captures). This protocol is letta-code's INTERNAL, UNVERSIONED, UNDOCUMENTED IPC:
 * a routine binary bump can rename a field with no build-time failure — only runtime
 * mis-parse. The `validateInboundFrame` guards + the committed contract test are the
 * upgrade gate; keep them strict.
 */

/** The pinned server version this protocol was captured against. */
export const PINNED_SERVER_VERSION = "0.30.19";

/** Outbound (client → server) message-type strings. */
export const Outbound = {
  runtimeStart: "runtime_start",
  input: "input",
  conversationList: "conversation_list",
  conversationCreate: "conversation_create",
  conversationRetrieve: "conversation_retrieve",
  conversationUpdate: "conversation_update",
  conversationFork: "conversation_fork",
  conversationMessagesList: "conversation_messages_list",
  approvalSend: "approval_send",
} as const;

/** Inbound (server → client) message-type strings. */
export const Inbound = {
  runtimeStartResponse: "runtime_start_response",
  streamDelta: "stream_delta",
  updateLoopStatus: "update_loop_status",
  updateQueue: "update_queue",
  updateSubagentState: "update_subagent_state",
  updateDeviceStatus: "update_device_status",
  turnFinished: "turn_finished",
  approvalRequestMessage: "approval_request_message",
  conversationListResponse: "conversation_list_response",
  conversationCreateResponse: "conversation_create_response",
  conversationRetrieveResponse: "conversation_retrieve_response",
  conversationUpdateResponse: "conversation_update_response",
  conversationForkResponse: "conversation_fork_response",
  conversationMessagesListResponse: "conversation_messages_list_response",
} as const;

/** Map of an outbound RPC type → the inbound `*_response` type that answers it. */
export const RpcResponseFor: Record<string, string> = {
  [Outbound.conversationList]: Inbound.conversationListResponse,
  [Outbound.conversationCreate]: Inbound.conversationCreateResponse,
  [Outbound.conversationRetrieve]: Inbound.conversationRetrieveResponse,
  [Outbound.conversationUpdate]: Inbound.conversationUpdateResponse,
  [Outbound.conversationFork]: Inbound.conversationForkResponse,
  [Outbound.conversationMessagesList]: Inbound.conversationMessagesListResponse,
};

export class ProtocolError extends Error {
  override name = "ProtocolError";
}

/** Every broadcast/response carries this `{agent_id, conversation_id}` targeting object. */
export interface Runtime {
  agent_id: string;
  conversation_id: string;
}

/** A generic parsed server frame — always has a string `type`. */
export interface ServerFrame {
  type: string;
  [key: string]: unknown;
}

/**
 * The message object embedded in a `stream_delta.delta`. `delta.id` (`letta-msg-NNN`)
 * is the CONVERSATION-STABLE message id used for reconnect catch-up dedup (NOT `event_seq`,
 * which is per-connection and resets on reconnect).
 */
export interface DeltaMessage {
  id: string;
  message_type: string;
  run_id?: string;
  seq_id?: number;
  reasoning?: string;
  content?: unknown;
  text?: unknown;
  message?: unknown;
  [key: string]: unknown;
}

export interface StreamDeltaFrame extends ServerFrame {
  type: "stream_delta";
  delta: DeltaMessage;
  runtime: Runtime;
  event_seq: number;
}

export interface TurnFinishedFrame extends ServerFrame {
  type: "turn_finished";
  turn_id: string;
  stop_reason: string;
  run_id?: string;
  runtime: Runtime;
  event_seq: number;
}

export interface LoopStatusFrame extends ServerFrame {
  type: "update_loop_status";
  loop_status: { status: string; active_run_ids?: string[]; executing_tool_call_ids?: string[] };
  runtime: Runtime;
  event_seq: number;
}

export interface QueueFrame extends ServerFrame {
  type: "update_queue";
  queue: unknown[];
  removed: unknown[];
  runtime: Runtime;
  event_seq: number;
}

export interface SubagentStateFrame extends ServerFrame {
  type: "update_subagent_state";
  subagents: unknown[];
  runtime: Runtime;
  event_seq: number;
}

export interface ApprovalRequestFrame extends ServerFrame {
  type: "approval_request_message";
  runtime: Runtime;
  event_seq: number;
  /** id used to answer via `approval_send`. Field name is inferred (no live sample); kept here so drift is localized. */
  approval_request_id?: string;
  run_id?: string;
}

export interface RuntimeStartResponseFrame extends ServerFrame {
  type: "runtime_start_response";
  request_id: string;
  success: boolean;
  runtime: Runtime;
  /** Present in 0.30.19; NO server-version field exists on this frame (verified) — see assertServerVersion. */
  agent?: { id: string; name?: string; [k: string]: unknown };
}

export interface ConversationSummary {
  id: string;
  agent_id: string;
  archived: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponseFrame extends ServerFrame {
  type: "conversation_list_response";
  request_id: string;
  success: boolean;
  conversations: ConversationSummary[];
}

export interface ConversationCreateResponseFrame extends ServerFrame {
  type: "conversation_create_response";
  request_id: string;
  success: boolean;
  conversation?: { id: string; [k: string]: unknown };
}

export interface MessagesListResponseFrame extends ServerFrame {
  type: "conversation_messages_list_response";
  request_id: string;
  success: boolean;
  messages: Array<{ id?: string; [k: string]: unknown }>;
  next_before: string | null;
  has_more: boolean;
  error?: string | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Outbound frame builders (the only place outbound frames are shaped)
// ─────────────────────────────────────────────────────────────────────────────

export function buildRuntimeStart(requestId: string, runtime: Runtime): ServerFrame {
  return { type: Outbound.runtimeStart, request_id: requestId, ...runtime };
}

export function buildInput(runtime: Runtime, content: string): ServerFrame {
  return {
    type: Outbound.input,
    runtime,
    payload: { kind: "create_message", messages: [{ role: "user", content }] },
  };
}

export function buildConversationList(requestId: string, agentId: string): ServerFrame {
  return { type: Outbound.conversationList, request_id: requestId, agent_id: agentId };
}

export function buildConversationCreate(
  requestId: string,
  agentId: string,
  title?: string,
): ServerFrame {
  const frame: ServerFrame = {
    type: Outbound.conversationCreate,
    request_id: requestId,
    agent_id: agentId,
  };
  if (title !== undefined) frame.title = title;
  return frame;
}

export function buildConversationMessagesList(requestId: string, runtime: Runtime): ServerFrame {
  return {
    type: Outbound.conversationMessagesList,
    request_id: requestId,
    agent_id: runtime.agent_id,
    conversation_id: runtime.conversation_id,
  };
}

/**
 * Fail-CLOSED approval response (M1 policy). Only the injecting client sends this.
 * `decision` is "deny" for M1; "allow" is the rail/approval milestone. The exact wire
 * shape of approval_send is inferred (no live approval sample captured safely); it lives
 * here so a drift correction is one edit.
 */
export function buildApprovalSend(
  requestId: string,
  runtime: Runtime,
  approvalRequestId: string,
  decision: "deny" | "allow",
): ServerFrame {
  return {
    type: Outbound.approvalSend,
    request_id: requestId,
    runtime,
    approval_request_id: approvalRequestId,
    decision,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Parsing, validation, and field extraction (the only place inbound frames are read)
// ─────────────────────────────────────────────────────────────────────────────

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Parse a raw WS payload into a `ServerFrame`. Throws ProtocolError on malformed input. */
export function parseFrame(raw: string | Buffer | ArrayBuffer): ServerFrame {
  const text =
    typeof raw === "string"
      ? raw
      : raw instanceof ArrayBuffer
        ? Buffer.from(raw).toString("utf-8")
        : raw.toString("utf-8");
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    throw new ProtocolError(`frame is not valid JSON: ${(e as Error).message}`);
  }
  if (!isObject(parsed) || typeof parsed.type !== "string") {
    throw new ProtocolError("frame is missing a string `type` field");
  }
  return parsed as ServerFrame;
}

function isRuntime(v: unknown): v is Runtime {
  return isObject(v) && typeof v.agent_id === "string" && typeof v.conversation_id === "string";
}

/**
 * Strict field-shape validation for the inbound frames the client depends on.
 * This is the runtime drift detector — if the server renames `event_seq`, `delta.id`,
 * or `conversations`, this throws LOUDLY instead of silently mis-parsing.
 * Unknown frame types pass through (forward-compat); known ones are checked hard.
 */
export function validateInboundFrame(frame: ServerFrame): void {
  switch (frame.type) {
    case Inbound.streamDelta: {
      if (typeof frame.event_seq !== "number")
        throw new ProtocolError("stream_delta: missing numeric `event_seq`");
      if (!isRuntime(frame.runtime)) throw new ProtocolError("stream_delta: missing `runtime`");
      const delta = frame.delta;
      if (!isObject(delta) || typeof delta.id !== "string")
        throw new ProtocolError("stream_delta: missing `delta.id` (message-id watermark)");
      if (typeof delta.message_type !== "string")
        throw new ProtocolError("stream_delta: missing `delta.message_type`");
      return;
    }
    case Inbound.turnFinished: {
      if (typeof frame.event_seq !== "number")
        throw new ProtocolError("turn_finished: missing numeric `event_seq`");
      if (typeof frame.turn_id !== "string")
        throw new ProtocolError("turn_finished: missing `turn_id`");
      if (typeof frame.stop_reason !== "string")
        throw new ProtocolError("turn_finished: missing `stop_reason`");
      if (!isRuntime(frame.runtime)) throw new ProtocolError("turn_finished: missing `runtime`");
      return;
    }
    case Inbound.updateLoopStatus: {
      if (typeof frame.event_seq !== "number")
        throw new ProtocolError("update_loop_status: missing numeric `event_seq`");
      if (!isObject(frame.loop_status) || typeof frame.loop_status.status !== "string")
        throw new ProtocolError("update_loop_status: missing `loop_status.status`");
      return;
    }
    case Inbound.updateQueue:
    case Inbound.updateSubagentState:
    case Inbound.updateDeviceStatus: {
      if (typeof frame.event_seq !== "number")
        throw new ProtocolError(`${frame.type}: missing numeric \`event_seq\``);
      return;
    }
    case Inbound.approvalRequestMessage: {
      if (!isRuntime(frame.runtime))
        throw new ProtocolError("approval_request_message: missing `runtime`");
      return;
    }
    case Inbound.runtimeStartResponse:
    case Inbound.conversationListResponse:
    case Inbound.conversationCreateResponse:
    case Inbound.conversationRetrieveResponse:
    case Inbound.conversationUpdateResponse:
    case Inbound.conversationForkResponse:
    case Inbound.conversationMessagesListResponse: {
      if (typeof frame.request_id !== "string")
        throw new ProtocolError(`${frame.type}: missing \`request_id\``);
      if (typeof frame.success !== "boolean")
        throw new ProtocolError(`${frame.type}: missing boolean \`success\``);
      if (frame.type === Inbound.conversationListResponse && !Array.isArray(frame.conversations))
        throw new ProtocolError("conversation_list_response: missing `conversations` array");
      if (frame.type === Inbound.conversationMessagesListResponse && !Array.isArray(frame.messages))
        throw new ProtocolError("conversation_messages_list_response: missing `messages` array");
      return;
    }
    default:
      // Unknown/forward-compat frame types are tolerated (ignored downstream).
      return;
  }
}

// Type guards used by the stream/facade layers.
export function isStreamDelta(f: ServerFrame): f is StreamDeltaFrame {
  return f.type === Inbound.streamDelta;
}
export function isTurnFinished(f: ServerFrame): f is TurnFinishedFrame {
  return f.type === Inbound.turnFinished;
}
export function isLoopStatus(f: ServerFrame): f is LoopStatusFrame {
  return f.type === Inbound.updateLoopStatus;
}
export function isQueue(f: ServerFrame): f is QueueFrame {
  return f.type === Inbound.updateQueue;
}
export function isSubagentState(f: ServerFrame): f is SubagentStateFrame {
  return f.type === Inbound.updateSubagentState;
}
export function isApprovalRequest(f: ServerFrame): f is ApprovalRequestFrame {
  return f.type === Inbound.approvalRequestMessage;
}

/** True if the frame is a broadcast that participates in the ordered `event_seq` stream. */
export function isOrderedBroadcast(f: ServerFrame): boolean {
  return typeof (f as { event_seq?: unknown }).event_seq === "number";
}

/** Per-connection monotonic ordering key. */
export function frameEventSeq(f: ServerFrame): number | undefined {
  const s = (f as { event_seq?: unknown }).event_seq;
  return typeof s === "number" ? s : undefined;
}

/** The conversation-stable message id from a stream_delta (`letta-msg-NNN`). */
export function deltaMessageId(f: StreamDeltaFrame): string {
  return f.delta.id;
}

export function deltaMessageType(f: StreamDeltaFrame): string {
  return f.delta.message_type;
}

/** Best-effort human-visible text from a delta (reasoning/assistant/tool message shapes). */
export function deltaText(f: StreamDeltaFrame): string {
  const d = f.delta;
  if (typeof d.reasoning === "string") return d.reasoning;
  for (const key of ["content", "text", "message"] as const) {
    const v = d[key];
    if (typeof v === "string") return v;
    if (Array.isArray(v)) {
      const joined = v
        .map((c) => (isObject(c) && typeof c.text === "string" ? c.text : ""))
        .join("");
      if (joined) return joined;
    }
  }
  return "";
}

export function approvalRequestId(f: ApprovalRequestFrame): string | undefined {
  return typeof f.approval_request_id === "string" ? f.approval_request_id : undefined;
}

// ─────────────────────────────────────────────────────────────────────────────
// Server-version assertion at the WS hello
// ─────────────────────────────────────────────────────────────────────────────

export type VersionPolicy = "warn" | "refuse";

export interface VersionCheck {
  verified: boolean;
  actual: string | null;
  pinned: string;
}

/**
 * Assert the connected server is the pinned version, from the `runtime_start_response` hello.
 *
 * Reality (verified on 0.30.19): the App Server exposes NO version field on the hello,
 * on `/v1/models`, or on any `/version` route. So `actual` is `null` today and the hello
 * check cannot verify the version by itself — the COMMITTED CONTRACT TEST is the real
 * upgrade gate. This function is future-proofing: if a later build adds `server_version`/
 * `version` to the hello, a mismatch is caught here per `policy` (refuse → throw, warn → onWarn).
 * When the version is unverifiable (absent field) it never throws; it warns once so the
 * operator knows the contract test is the sole guard.
 */
export function assertServerVersion(
  hello: ServerFrame,
  opts: { pinnedVersion?: string; policy?: VersionPolicy; onWarn?: (msg: string) => void } = {},
): VersionCheck {
  const pinned = opts.pinnedVersion ?? PINNED_SERVER_VERSION;
  const policy = opts.policy ?? "warn";
  const onWarn = opts.onWarn ?? (() => {});
  const candidate =
    (typeof hello.server_version === "string" && hello.server_version) ||
    (typeof hello.version === "string" && hello.version) ||
    null;

  if (candidate === null) {
    onWarn(
      `server version unverifiable at WS hello (no version field on letta ${pinned} protocol); relying on the committed contract test as the upgrade gate`,
    );
    return { verified: false, actual: null, pinned };
  }
  if (candidate !== pinned) {
    const msg = `App Server version ${candidate} != pinned ${pinned} — protocol drift possible`;
    if (policy === "refuse") throw new ProtocolError(msg);
    onWarn(msg);
    return { verified: false, actual: candidate, pinned };
  }
  return { verified: true, actual: candidate, pinned };
}

// ─────────────────────────────────────────────────────────────────────────────
// Request-id generation (deterministic, monotonic — testable)
// ─────────────────────────────────────────────────────────────────────────────

let requestCounter = 0;

/** Monotonic, prefix-scoped request id for RPC correlation. Deterministic across a process. */
export function nextRequestId(prefix = "req"): string {
  requestCounter += 1;
  return `${prefix}-${requestCounter}`;
}

/** Test-only: reset the request-id counter for deterministic assertions. */
export function __resetRequestCounter(): void {
  requestCounter = 0;
}
