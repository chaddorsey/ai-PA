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

/**
 * Server versions this protocol has been contract-test-verified against, oldest first.
 *
 * It is a SET, not a single string, because the running server and the on-disk binary drift
 * apart routinely: a package bump leaves the live process on the old code until it restarts,
 * so both versions are legitimately in play at once. Only add a version here after
 * `test/live.contract.test.ts` passes against it on a CLONE backend.
 *
 *  - 0.30.19 — original Unit 4 capture (live :4577)
 *  - 0.30.20 — verified 2026-08-13 on a clone: protocol_version still 1, capabilities
 *    identical, all frames round-trip, real streamed turn completes without error.
 */
export const VALIDATED_SERVER_VERSIONS = ["0.30.19", "0.30.20"] as const;

/** The newest validated version — what a restart of the App Server brings up today. */
export const PINNED_SERVER_VERSION =
  VALIDATED_SERVER_VERSIONS[VALIDATED_SERVER_VERSIONS.length - 1];

/**
 * The pinned App Server protocol version (`app_server_info_response.protocol_version`).
 * This is the server's OWN declared contract version — a bump here is a first-class
 * drift signal that does not depend on us recognising a binary version string.
 */
export const PINNED_PROTOCOL_VERSION = 1;

/**
 * Server capabilities this client-core structurally requires. `runtime_start` is the hello;
 * `conversation_management` backs the `conversation_*` RPCs, including the
 * `conversation_messages_list` snapshot that reconnect catch-up dedup depends on.
 * A server advertising either as false cannot serve this client at all.
 */
export const REQUIRED_CAPABILITIES = ["runtime_start", "conversation_management"] as const;

/** Outbound (client → server) message-type strings. */
export const Outbound = {
  appServerInfo: "app_server_info",
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
  appServerInfoResponse: "app_server_info_response",
  runtimeStartResponse: "runtime_start_response",
  inputAccepted: "input_accepted",
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
  [Outbound.appServerInfo]: Inbound.appServerInfoResponse,
  [Outbound.runtimeStart]: Inbound.runtimeStartResponse,
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

/** A message waiting behind the active turn. `client_message_id` is OUR value, echoed back. */
export interface QueueItem {
  id: string;
  client_message_id: string;
  kind: string;
  source: string;
  content?: unknown;
  enqueued_at?: string;
}

/**
 * A queued message leaving the queue. `dequeued` = its turn is starting next;
 * `cancelled` = it will never run.
 */
export interface QueueRemoval {
  client_message_id: string;
  disposition: "dequeued" | "cancelled" | string;
}

export interface QueueFrame extends ServerFrame {
  type: "update_queue";
  queue: QueueItem[];
  removed: QueueRemoval[];
  runtime: Runtime;
  event_seq: number;
}

/**
 * Synchronous ack for an `input`, correlated by `request_id`. The server emits it ONLY when
 * the `input` carried a `request_id` — so a correlated send must always set one.
 *
 * Carries NO run_id: `disposition` is the correlation hook instead. `started` means this
 * client's turn is the one now beginning; `queued` means it sits behind another turn and
 * its start is announced later via `update_queue.removed` (disposition `dequeued`).
 */
export interface InputAcceptedFrame extends ServerFrame {
  type: "input_accepted";
  request_id: string;
  runtime: Runtime;
  accepted: boolean;
  disposition?: "started" | "queued" | "submitting" | string;
  error?: string;
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
  /** The hello carries NO server-version field — the version gate is `app_server_info`, not this frame. */
  agent?: { id: string; name?: string; [k: string]: unknown };
}

/** Server-declared capability flags from `app_server_info_response.capabilities`. */
export interface AppServerCapabilities {
  [capability: string]: boolean | undefined;
}

/**
 * Answer to the `app_server_info` RPC — the App Server's self-description, and the ONLY
 * place it states its own version. Verified live on 0.30.19: it answers before
 * `runtime_start`, so the version gate can run before any runtime is started.
 */
export interface AppServerInfoResponseFrame extends ServerFrame {
  type: "app_server_info_response";
  request_id: string;
  success: boolean;
  backend?: string;
  letta_code_version?: string;
  protocol_version?: number;
  capabilities?: AppServerCapabilities;
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

export function buildAppServerInfo(requestId: string): ServerFrame {
  return { type: Outbound.appServerInfo, request_id: requestId };
}

export function buildRuntimeStart(requestId: string, runtime: Runtime): ServerFrame {
  return { type: Outbound.runtimeStart, request_id: requestId, ...runtime };
}

/**
 * Build an `input` carrying BOTH correlation handles (see ownership.ts):
 *  - `request_id` — without it the server sends no `input_accepted` ack at all;
 *  - `client_message_id` — echoed verbatim in `update_queue`, so a queued turn can recognise
 *    its own dequeue. Sent on the payload AND the message, matching the server's lookup
 *    (`firstUserPayload.otid ?? firstUserPayload.client_message_id`).
 */
export function buildInput(
  runtime: Runtime,
  content: string,
  correlation: { requestId: string; clientMessageId: string },
): ServerFrame {
  return {
    type: Outbound.input,
    request_id: correlation.requestId,
    runtime,
    payload: {
      kind: "create_message",
      client_message_id: correlation.clientMessageId,
      messages: [{ role: "user", content, client_message_id: correlation.clientMessageId }],
    },
  };
}

/**
 * The `conversation_*` RPC envelopes are NOT uniform, and the server drops a malformed one
 * SILENTLY (its command guards return false and no error frame is sent — the request just
 * times out). Shapes below are read from the server's own guards and verified live:
 *   conversation_list          → optional `query` object   (a top-level agent_id is IGNORED)
 *   conversation_create        → REQUIRES a `body` object
 *   conversation_messages_list → top-level `conversation_id` + optional `query`
 */

export function buildConversationList(requestId: string, agentId: string): ServerFrame {
  // The agent filter belongs in `query` — the server passes `parsed.query` straight to
  // listConversations(), so a top-level agent_id silently returns EVERY agent's conversations.
  return { type: Outbound.conversationList, request_id: requestId, query: { agent_id: agentId } };
}

export function buildConversationCreate(
  requestId: string,
  agentId: string,
  title?: string,
): ServerFrame {
  // `body` is mandatory: the server's guard requires an object at `body` and hands it to
  // createConversation(body), which reads body.agent_id. Without it the RPC is dropped silently.
  const body: Record<string, unknown> = { agent_id: agentId };
  if (title !== undefined) body.title = title;
  return { type: Outbound.conversationCreate, request_id: requestId, body };
}

export function buildConversationMessagesList(requestId: string, runtime: Runtime): ServerFrame {
  // conversation_id stays top-level here (the guard requires it there); agent_id is not read.
  return {
    type: Outbound.conversationMessagesList,
    request_id: requestId,
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
    case Inbound.inputAccepted: {
      if (typeof frame.request_id !== "string")
        throw new ProtocolError("input_accepted: missing `request_id`");
      if (typeof frame.accepted !== "boolean")
        throw new ProtocolError("input_accepted: missing boolean `accepted`");
      return; // no event_seq: this is a control-channel ack, not a broadcast
    }
    case Inbound.appServerInfoResponse:
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
export function isInputAccepted(f: ServerFrame): f is InputAcceptedFrame {
  return f.type === Inbound.inputAccepted;
}

/** Queue removals as a typed list (defensive: the arrays are server-shaped). */
export function queueRemovals(f: QueueFrame): QueueRemoval[] {
  return (Array.isArray(f.removed) ? f.removed : []).filter(
    (r): r is QueueRemoval => isObject(r) && typeof r.client_message_id === "string",
  );
}

/**
 * The run id a frame belongs to, wherever the server puts it: `run_id` on `turn_finished`,
 * `delta.run_id` on `stream_delta`, `loop_status.active_run_ids[0]` on a status update.
 * Used to attribute frames to runs for ownership (ownership.ts).
 */
export function frameRunId(f: ServerFrame): string | undefined {
  if (typeof f.run_id === "string") return f.run_id;
  if (isStreamDelta(f) && typeof f.delta.run_id === "string") return f.delta.run_id;
  if (isLoopStatus(f)) {
    const active = f.loop_status.active_run_ids;
    if (Array.isArray(active) && typeof active[0] === "string") return active[0];
  }
  return undefined;
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
// Server-identity assertion (the upgrade gate, from `app_server_info`)
// ─────────────────────────────────────────────────────────────────────────────

export type VersionPolicy = "warn" | "refuse";

export interface ServerIdentityCheck {
  /** True only when BOTH the binary version and the protocol version match their pins. */
  verified: boolean;
  /** Reported `letta_code_version`, or null if the server did not state one. */
  actual: string | null;
  /** The validated version set this check accepted against. */
  pinned: readonly string[];
  /** Reported `protocol_version`, or null if absent. */
  protocolVersion: number | null;
  pinnedProtocolVersion: number;
  /** Required capabilities the server explicitly advertised as unavailable. */
  missingCapabilities: string[];
}

/**
 * Assert the connected App Server is the pinned build, from its `app_server_info_response`.
 *
 * This is the real client-side upgrade gate (protocol-coupling mitigation #3). The
 * `runtime_start` hello carries no version, but `app_server_info` does — it reports
 * `letta_code_version`, its own `protocol_version`, and a capability map. A launcher-side
 * check is defeated by a between-launch package bump (the running server keeps the old code
 * in memory while the on-disk binary moves), so the check has to live on the connection.
 *
 * Severity is deliberately tiered:
 *  - a **missing required capability** always throws — the client structurally cannot work;
 *  - a **protocol_version** or **letta_code_version** mismatch follows `policy`
 *    (`refuse` → throw, `warn` → `onWarn`), because a version bump only *may* mean drift;
 *  - an **absent** version/capability field never throws — older servers predate the RPC,
 *    and the committed contract test still gates those.
 */
export function assertServerIdentity(
  info: ServerFrame,
  opts: {
    /** A single version or the accepted set. Defaults to every contract-verified version. */
    pinnedVersion?: string | readonly string[];
    pinnedProtocolVersion?: number;
    requiredCapabilities?: readonly string[];
    policy?: VersionPolicy;
    onWarn?: (msg: string) => void;
  } = {},
): ServerIdentityCheck {
  const pinnedOpt = opts.pinnedVersion ?? VALIDATED_SERVER_VERSIONS;
  const pinned = typeof pinnedOpt === "string" ? [pinnedOpt] : pinnedOpt;
  const pinnedProtocol = opts.pinnedProtocolVersion ?? PINNED_PROTOCOL_VERSION;
  const required = opts.requiredCapabilities ?? REQUIRED_CAPABILITIES;
  const policy = opts.policy ?? "warn";
  const onWarn = opts.onWarn ?? (() => {});

  const actual = typeof info.letta_code_version === "string" ? info.letta_code_version : null;
  const protocolVersion = typeof info.protocol_version === "number" ? info.protocol_version : null;
  const capabilities = isObject(info.capabilities) ? info.capabilities : null;

  // Capability gate first: an explicit `false` is a hard, unambiguous incompatibility.
  const missingCapabilities = capabilities
    ? required.filter((cap) => capabilities[cap] === false)
    : [];
  if (missingCapabilities.length > 0) {
    throw new ProtocolError(
      `App Server lacks required capabilities: ${missingCapabilities.join(", ")} (letta ${actual ?? "unknown"})`,
    );
  }

  const drift: string[] = [];
  if (protocolVersion !== null && protocolVersion !== pinnedProtocol) {
    drift.push(`protocol_version ${protocolVersion} != pinned ${pinnedProtocol}`);
  }
  if (actual !== null && !pinned.includes(actual)) {
    drift.push(`letta_code_version ${actual} not in validated set [${pinned.join(", ")}]`);
  }

  if (drift.length > 0) {
    const msg = `App Server drift: ${drift.join("; ")} — re-run the contract test before trusting this connection`;
    if (policy === "refuse") throw new ProtocolError(msg);
    onWarn(msg);
    return {
      verified: false,
      actual,
      pinned,
      protocolVersion,
      pinnedProtocolVersion: pinnedProtocol,
      missingCapabilities,
    };
  }

  if (actual === null) {
    onWarn(
      "server version unverifiable (no `letta_code_version` in app_server_info); relying on the committed contract test as the upgrade gate",
    );
    return {
      verified: false,
      actual,
      pinned,
      protocolVersion,
      pinnedProtocolVersion: pinnedProtocol,
      missingCapabilities,
    };
  }

  return {
    verified: true,
    actual,
    pinned,
    protocolVersion,
    pinnedProtocolVersion: pinnedProtocol,
    missingCapabilities,
  };
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
