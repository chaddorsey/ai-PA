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
/** The newest validated version — what a restart of the App Server brings up today. */
export const PINNED_SERVER_VERSION = "0.30.20";

/**
 * Derived FROM the pin rather than the other way round. Indexing a tuple under
 * `noUncheckedIndexedAccess` made the pin `string | undefined`, which the mock then papered over
 * with `??` — so a refactor of this list could have made the mock omit the version field entirely
 * and silently downgrade the whole drift gate to a no-op.
 */
export const VALIDATED_SERVER_VERSIONS = ["0.30.19", PINNED_SERVER_VERSION] as const;

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

/**
 * `stream_delta` message types that carry no `delta.id`.
 *
 * A turn's stream is not only content: it ends with control deltas. Verified live on 0.30.19,
 * one turn emits `reasoning_message` + `assistant_message` (both id-bearing) and then
 * `usage_statistics` (id-bearing) and `stop_reason` (NO id). Requiring `delta.id` on every
 * stream_delta therefore rejected one legitimate frame on EVERY turn.
 *
 * This is an allowlist rather than "id is optional everywhere" on purpose: the id is the
 * catch-up watermark, so a content delta that lost its id is real drift and must still fail
 * loudly. A future control type not listed here will fail too — which is the intended
 * upgrade-gate behaviour, not an oversight.
 */
export const CONTROL_DELTA_TYPES: ReadonlySet<string> = new Set(["stop_reason", "error_message"]);

/**
 * `stream_delta.delta.message_type` values consumers switch on.
 *
 * These are WIRE STRINGS and therefore belong here, not in the consumer. When `render.ts` kept
 * its own copies, a server-side rename would pass `validateInboundFrame` (which only checks that
 * message_type is a string), the contract test would stay green, and the terminal would silently
 * render nothing at all — connected, accepting input, streaming no output, reporting no error.
 * That is precisely the silent mis-parse this file exists to make impossible.
 */
export const DeltaMessageTypes = {
  assistant: "assistant_message",
  reasoning: "reasoning_message",
  approvalRequest: "approval_request_message",
  usage: "usage_statistics",
  stopReason: "stop_reason",
  /**
   * A tool call. Emitted on the run our send starts, which is then suspended and never closed —
   * see `broadcastToolUsingTurn`. Previously a bare literal in the test double ONLY, so drifting
   * it there left the whole suite green while the double stopped resembling the server.
   */
  toolCall: "tool_call_message",
  /**
   * The two deltas an ERRORED turn is carried on. Both were on the wire and both were dropped by
   * `renderDelta`, so a provider outage — the commonest real fault there is — rendered as an empty
   * SUCCESSFUL turn and exited 0.
   *
   * THEY HAVE OPPOSITE ID RULES, and getting that backwards silently undoes the fix:
   *
   * - `loop_error` is `LoopErrorMessage extends UmiLifecycleMessageBase`, so `id` is REQUIRED.
   *   It also carries `message`, `stop_reason` and — worth knowing — `is_terminal`.
   * - `error_message` is the SDK's `LettaErrorMessage`, whose fields are `error_type`, `message`,
   *   `run_id`, and optional `detail`/`seq_id`. There is **no `id`**, so it must be a CONTROL
   *   delta or `validateInboundFrame` rejects it as drift and the renderer never sees it.
   *
   * Both were first assumed the other way round from a live capture summary; the shipped type
   * declarations (`@letta-ai/letta-code/dist/types/types/protocol_v2.d.ts` and the
   * `@letta-ai/letta-client` SDK) settle it. Read those before changing either.
   */
  loopError: "loop_error",
  errorMessage: "error_message",
} as const;

/**
 * Delta types that mean "this turn failed", for consumers that must show it and exit nonzero.
 *
 * A set rather than two comparisons because an errored turn emits BOTH — a machine-readable
 * `loop_error` and a human-readable `error_message` — and a consumer that handles one and not the
 * other still blacks out half the failures.
 */
export const ERROR_DELTA_TYPES: ReadonlySet<string> = new Set([
  DeltaMessageTypes.loopError,
  DeltaMessageTypes.errorMessage,
]);

/** `turn_finished.stop_reason` values with behavioural meaning. */
export const StopReasons = {
  endTurn: "end_turn",
  requiresApproval: "requires_approval",
  error: "error",
} as const;

/**
 * `input_accepted.disposition` values. These decide whether a claim arms now or waits for its
 * dequeue notice, so they are behaviour, not decoration — and they were the last wire strings
 * still living as bare literals in ownership.ts, where a rename would compile silently.
 *
 * `submitting` is absent from the server's published typedef but is emitted by the bundle.
 */
export const InputDispositions = {
  started: "started",
  queued: "queued",
  submitting: "submitting",
} as const;

/** `update_queue.removed[].disposition` values. */
export const QueueDispositions = {
  dequeued: "dequeued",
  cancelled: "cancelled",
} as const;

/**
 * `update_loop_status.loop_status.status` values with behavioural meaning.
 *
 * `waitingOnInput` is the idle the one-shot terminates on. The other two were bare literals in
 * `mockServer.ts` and nowhere else, which is the drift hole C1 names: the double could rename a
 * status the client switches on and the whole suite would stay green, because the only other copy
 * of the vocabulary was the double's own.
 */
export const LoopStatuses = {
  waitingOnInput: "WAITING_ON_INPUT",
  sendingApiRequest: "SENDING_API_REQUEST",
  executingClientSideTool: "EXECUTING_CLIENT_SIDE_TOOL",
} as const;

/** `input.payload.kind` values the server dispatches on. */
export const InputKinds = {
  createMessage: "create_message",
  approvalResponse: "approval_response",
} as const;

/** `control_request.request.subtype` values. */
export const ControlRequestSubtypes = {
  canUseTool: "can_use_tool",
} as const;

/**
 * Single-word wire values that read as ordinary English and therefore hide in plain sight.
 *
 * They are here for the same reason as everything else in this file: the double used to be their
 * only other home, so a rename on the server could be mirrored into the double — or not — with no
 * test able to tell. A one-word string is not less of a wire contract than a snake_cased one; it
 * is merely harder to spot in a diff, which is an argument for naming it, not against.
 */
export const WireEnvelope = {
  /** `stream_delta.delta.type` and `update_queue.queue[].kind`. */
  message: "message",
} as const;

/** `update_queue.queue[].source` values. */
export const QueueSources = {
  user: "user",
} as const;

/** `app_server_info_response.backend` values. The App Server sole-owns a `local` backend. */
export const Backends = {
  local: "local",
} as const;

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
  controlRequest: "control_request",
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

/**
 * A string that came from the server and has NOT been made safe for any particular sink.
 *
 * The brand is a compile-time reminder, not a runtime wrapper: it costs nothing at runtime and
 * forces a consumer to acknowledge the boundary before rendering. Sanitization deliberately lives
 * in the CONSUMER, not here, because "safe" is sink-specific — the terminal strips ANSI and
 * control characters, while the browser client (M1 Unit 6) faces an entirely different class:
 * HTML injection, `javascript:` URLs in rendered markdown, and markdown image auto-loading, which
 * exfiltrates conversation content to a remote host on render and has no terminal analogue.
 * Sanitizing centrally would corrupt content for one sink while under-protecting the other.
 */
export type UntrustedText = string & { readonly __untrusted: unique symbol };

/** Mark a server-derived string as untrusted at the type level. Runtime no-op. */
export function untrusted(text: string): UntrustedText {
  return text as UntrustedText;
}

/** A generic parsed server frame — always has a string `type`. */
export interface ServerFrame {
  type: string;
  [key: string]: unknown;
}

/**
 * The message object embedded in a `stream_delta.delta`. `delta.id` (`letta-msg-NNN`)
 * is the per-chunk id used for reconnect catch-up dedup (NOT `event_seq`,
 * which is per-connection and resets on reconnect).
 */
export interface DeltaMessage {
  /** Absent on CONTROL deltas (see CONTROL_DELTA_TYPES); present on content-bearing ones. */
  id?: string;
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

/**
 * The ACTIONABLE approval request. Verified against the 0.30.20 bundle
 * (`requestApprovalOverWS`): a top-level frame, **broadcast to every subscribed connection**,
 * whose `request_id` is `"perm-" + tool_call_id`.
 *
 * Do not confuse it with the `approval_request_message` DELTA, which is the transcript
 * projection of the same event. A client that watches only deltas can display an approval but
 * can never answer one — which is precisely why approvals were invisible before this change.
 */
export interface ControlRequestFrame extends ServerFrame {
  type: "control_request";
  request_id: string;
  request: {
    subtype: string;
    tool_name?: string;
    tool_call_id: string;
    input?: unknown;
    permission_suggestions?: unknown[];
    blocked_path?: string | null;
    diffs?: unknown[];
  };
  agent_id?: string;
  conversation_id?: string;
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
      kind: InputKinds.createMessage,
      client_message_id: correlation.clientMessageId,
      // Leg 1 of the M1 approval policy, enforced per-turn by the client rather than by an
      // operational precondition somebody has to remember. The server drops
      // INTERACTIVE_USER_INPUT_TOOL_NAMES (currently ["AskUserQuestion"]) from the turn's tool
      // context when this is set, so the class of tool that inherently blocks on a human answer
      // cannot be selected on a shared conversation at all. The server's own headless
      // /v1/responses path sets exactly this flag — that is the precedent being followed.
      //
      // It does NOT cover permission-gated approvals (`control_request` / `can_use_tool`), which
      // depend on the runtime's permission mode. See
      // docs/runbooks/continuity-conversation-preconditions.md.
      exclude_interactive_tools: true,
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
 * The M1 approval response: always DENY.
 *
 * Deny-only is enforced by the SIGNATURE, not by a call-site argument. The previous builder took
 * `decision: "deny" | "allow"` and relied on one call site passing the right literal — a one-word
 * edit away from auto-approving tool calls on an agent holding shell, filesystem and messaging
 * credentials. Reintroducing allow at the rail milestone now requires changing this signature,
 * which is visible in review.
 *
 * Shape from the server's own validator (`isValidApprovalResponseBody`): the response rides an
 * `input` with `kind: "approval_response"`, and a deny decision REQUIRES a string `message`.
 */
export function buildApprovalDeny(
  requestId: string,
  runtime: Runtime,
  controlRequestId: string,
  message: string,
): ServerFrame {
  return {
    type: Outbound.input,
    request_id: requestId,
    runtime,
    payload: {
      kind: InputKinds.approvalResponse,
      request_id: controlRequestId,
      decision: { behavior: "deny", message },
    },
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
/**
 * A plausible per-connection ordering counter.
 *
 * `typeof === "number"` was not enough. StreamAssembler latches its watermark to whatever arrives
 * and drops everything at or below it, so ONE frame carrying MAX_SAFE_INTEGER (or Infinity, or
 * NaN, or a sign-flipped counter) raises the watermark past every future frame — leaving the
 * client connected, accepting input, rendering nothing and reporting nothing, with no reset short
 * of a reconnect. That is precisely the silent mis-parse this file exists to make impossible, so
 * an out-of-range counter now fails loudly through the same drift path as any other bad field.
 */
function isEventSeq(v: unknown): v is number {
  return typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
}

export function validateInboundFrame(frame: ServerFrame): void {
  switch (frame.type) {
    case Inbound.streamDelta: {
      if (!isEventSeq(frame.event_seq))
        throw new ProtocolError("stream_delta: missing numeric `event_seq`");
      if (!isRuntime(frame.runtime)) throw new ProtocolError("stream_delta: missing `runtime`");
      const delta = frame.delta;
      if (!isObject(delta)) throw new ProtocolError("stream_delta: missing `delta`");
      if (typeof delta.message_type !== "string")
        throw new ProtocolError("stream_delta: missing `delta.message_type`");
      // Control deltas legitimately carry no id; content deltas must (it is the watermark).
      if (!CONTROL_DELTA_TYPES.has(delta.message_type) && typeof delta.id !== "string")
        throw new ProtocolError(
          `stream_delta (${delta.message_type}): missing \`delta.id\` (message-id watermark)`,
        );
      return;
    }
    case Inbound.turnFinished: {
      if (!isEventSeq(frame.event_seq))
        throw new ProtocolError("turn_finished: missing numeric `event_seq`");
      if (typeof frame.turn_id !== "string")
        throw new ProtocolError("turn_finished: missing `turn_id`");
      if (typeof frame.stop_reason !== "string")
        throw new ProtocolError("turn_finished: missing `stop_reason`");
      if (!isRuntime(frame.runtime)) throw new ProtocolError("turn_finished: missing `runtime`");
      return;
    }
    case Inbound.updateLoopStatus: {
      if (!isEventSeq(frame.event_seq))
        throw new ProtocolError("update_loop_status: missing numeric `event_seq`");
      if (!isObject(frame.loop_status) || typeof frame.loop_status.status !== "string")
        throw new ProtocolError("update_loop_status: missing `loop_status.status`");
      return;
    }
    case Inbound.updateQueue: {
      if (!isEventSeq(frame.event_seq))
        throw new ProtocolError("update_queue: missing numeric `event_seq`");
      // Both arrays drive run attribution, and `disposition` decides whether a claim arms or is
      // dropped. A rename here silently re-routes attribution, so it must fail loudly instead.
      if (!Array.isArray(frame.queue) || !Array.isArray(frame.removed))
        throw new ProtocolError("update_queue: missing `queue`/`removed` arrays");
      for (const removal of frame.removed) {
        if (!isObject(removal) || typeof removal.client_message_id !== "string")
          throw new ProtocolError("update_queue: removal missing `client_message_id`");
        if (typeof removal.disposition !== "string")
          throw new ProtocolError("update_queue: removal missing `disposition`");
      }
      return;
    }
    case Inbound.updateSubagentState:
    case Inbound.updateDeviceStatus: {
      if (!isEventSeq(frame.event_seq))
        throw new ProtocolError(`${frame.type}: missing numeric \`event_seq\``);
      return;
    }
    case Inbound.controlRequest: {
      if (typeof frame.request_id !== "string")
        throw new ProtocolError("control_request: missing `request_id`");
      if (!isObject(frame.request) || typeof frame.request.subtype !== "string")
        throw new ProtocolError("control_request: missing `request.subtype`");
      if (typeof frame.request.tool_call_id !== "string")
        throw new ProtocolError("control_request: missing `request.tool_call_id`");
      return; // no event_seq: this is a control-channel request, not an ordered broadcast
    }
    case Inbound.inputAccepted: {
      if (typeof frame.request_id !== "string")
        throw new ProtocolError("input_accepted: missing `request_id`");
      if (typeof frame.accepted !== "boolean")
        throw new ProtocolError("input_accepted: missing boolean `accepted`");
      // `disposition` decides whether a claim arms now or waits for its dequeue notice — but it
      // is OPTIONAL, and demanding it was wrong. It is a message-queue concept: the server's
      // typedef declares `disposition?`, and an ack for an `approval_response` (or the teleport
      // path) carries none. Requiring it rejected a frame a correct server sends on every
      // approval. A wrongly-TYPED disposition is still drift and still fails loudly.
      if (frame.disposition !== undefined && typeof frame.disposition !== "string")
        throw new ProtocolError("input_accepted: `disposition` present but not a string");
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
      // Unknown/forward-compat frame types are tolerated (ignored downstream, and excluded from
      // the ordered stream by frameEventSeq — see ORDERED_BROADCAST_TYPES).
      return;
  }
}

/**
 * Frame types that participate in the per-connection ordered stream.
 *
 * An explicit allowlist, because the watermark is a one-way latch: whatever arrives raises it and
 * everything at or below is dropped for the life of the connection. Ordering on ANY frame that
 * happened to carry an `event_seq` meant a single unknown frame — a forward-compat type this
 * client does not even render — could carry MAX_SAFE_INTEGER and silence the client permanently:
 * connected, accepting input, rendering nothing, reporting nothing, with no reset short of a
 * reconnect. Tolerating a frame we do not understand is not the same as letting it dictate the
 * ordering of the frames we do.
 */
const ORDERED_BROADCAST_TYPES: ReadonlySet<string> = new Set([
  Inbound.streamDelta,
  Inbound.turnFinished,
  Inbound.updateLoopStatus,
  Inbound.updateQueue,
  Inbound.updateSubagentState,
  Inbound.updateDeviceStatus,
]);

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

/** Number of messages waiting behind the active turn. */
export function queueDepth(f: QueueFrame): number {
  return Array.isArray(f.queue) ? f.queue.length : 0;
}

/**
 * The `client_message_id`s currently queued.
 *
 * `update_queue` is BROADCAST, so depth alone says nothing about whether the reader is the one
 * waiting — the surface whose turn is actually running was being told it was queued behind itself.
 */
export function queuedClientMessageIds(f: QueueFrame): string[] {
  if (!Array.isArray(f.queue)) return [];
  return f.queue
    .map((q) => (isObject(q) && typeof q.client_message_id === "string" ? q.client_message_id : ""))
    .filter((id) => id !== "");
}

/** Number of active subagents reported by an `update_subagent_state` frame. */
export function subagentCount(f: SubagentStateFrame): number {
  return Array.isArray(f.subagents) ? f.subagents.length : 0;
}

/** Queue removals as a typed list (defensive: the arrays are server-shaped). */
export function queueRemovals(f: QueueFrame): QueueRemoval[] {
  return (Array.isArray(f.removed) ? f.removed : []).filter(
    (r): r is QueueRemoval =>
      isObject(r) &&
      typeof r.client_message_id === "string" &&
      // Narrowing to QueueRemoval asserts `disposition` too, so it has to be checked. Without
      // this the consumer's `=== "dequeued" ? arm : drop` treated an ABSENT disposition as a
      // cancellation and destroyed the claim.
      typeof r.disposition === "string",
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
export function isControlRequest(f: ServerFrame): f is ControlRequestFrame {
  return f.type === Inbound.controlRequest;
}

/**
 * Per-connection monotonic ordering key, or undefined when this frame does not take part in the
 * ordered stream (an RPC response, a control-channel ack, or a type we do not recognise).
 *
 * Both conditions are load-bearing. The range check is the same one the validator applies, so a
 * counter that is not a counter cannot latch the watermark; the type check keeps a frame we do
 * not understand from dictating the ordering of the frames we do.
 */
export function frameEventSeq(f: ServerFrame): number | undefined {
  if (!ORDERED_BROADCAST_TYPES.has(f.type)) return undefined;
  const s = (f as { event_seq?: unknown }).event_seq;
  return isEventSeq(s) ? s : undefined;
}

/** The conversation-stable message id from a stream_delta (`letta-msg-NNN`). */
/** The catch-up watermark id, or undefined on a control delta (see CONTROL_DELTA_TYPES). */
export function deltaMessageId(f: StreamDeltaFrame): string | undefined {
  return f.delta.id;
}

export function deltaMessageType(f: StreamDeltaFrame): string {
  return f.delta.message_type;
}

/**
 * Best-effort human-visible text from a delta.
 *
 * Returns UntrustedText: this is relayed third-party content (mail bodies, fetched pages) and
 * every sink must make it safe for itself before rendering.
 */
export function deltaText(f: StreamDeltaFrame): UntrustedText {
  const d = f.delta;
  // untrusted() is the ONLY sanctioned way to mint this type. Now that the brand is required
  // rather than optional, a raw string can no longer slip into an UntrustedText slot by accident
  // — which is what made the old declaration a bidirectional alias for `string` and the whole
  // boundary decorative.
  if (typeof d.reasoning === "string") return untrusted(d.reasoning);
  // BOTH error deltas carry their body in `message` — `LoopErrorMessage.message` and
  // `LettaErrorMessage.message`, per the shipped protocol types. `message` was already in this
  // list, so no new key is needed; an earlier guess at `error` was removed once the real
  // declarations were read.
  for (const key of ["content", "text", "message"] as const) {
    const v = d[key];
    if (typeof v === "string") return untrusted(v);
    if (Array.isArray(v)) {
      const joined = v
        .map((c) => (isObject(c) && typeof c.text === "string" ? c.text : ""))
        .join("");
      if (joined) return untrusted(joined);
    }
  }
  return untrusted("");
}

/** Tool name from an approval control request, for the notice shown to the user. */
export function controlRequestToolName(f: ControlRequestFrame): string | undefined {
  return typeof f.request.tool_name === "string" ? f.request.tool_name : undefined;
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

/**
 * A per-instance nonce that makes correlation ids unique across PROCESSES.
 *
 * Without it every client emits the identical sequence — `rpc-1`, `rt-2`, `input-3`, `cm-4` —
 * because the counter is module-global and starts at zero in each process. Two surfaces on one
 * conversation (the entire point of this milestone) then mint the same `client_message_id`, and
 * since `update_queue` is broadcast, each recognises the other's dequeue notice as its own. This
 * was observed in the server's persisted state, where `otid: "cm-4"` appears twice from two
 * independent client processes.
 *
 * Injectable so tests stay deterministic.
 */
export function newClientNonce(): string {
  // 6 hex chars is ample: this disambiguates a handful of concurrent local surfaces, not a
  // distributed namespace, and short ids keep frames greppable.
  return Math.floor(Math.random() * 0xffffff)
    .toString(16)
    .padStart(6, "0");
}

/**
 * Monotonic, prefix-scoped correlation id. Monotonic *within* an instance for readability;
 * unique *across* instances via `nonce`.
 *
 * `nonce` is a parameter rather than module state because the web client is ONE core fanning out
 * to N browsers — it must be able to vary the nonce per send so each browser's turn is
 * distinguishable, which a per-process value could not express.
 */
export function nextRequestId(prefix = "req", nonce?: string): string {
  requestCounter += 1;
  return nonce ? `${prefix}-${nonce}-${requestCounter}` : `${prefix}-${requestCounter}`;
}

/** Test-only: reset the request-id counter for deterministic assertions. */
export function __resetRequestCounter(): void {
  requestCounter = 0;
}
