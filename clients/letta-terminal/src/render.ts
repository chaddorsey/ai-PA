/**
 * render.ts — turn client-core events into terminal output.
 *
 * Deliberately PURE: it takes events and returns the text to write, holding no handle on
 * stdout, readline, or the core. That is what makes the render loop testable without a TTY
 * (Unit 5's "render loop against a stubbed core") and keeps the ANSI/formatting decisions in
 * one place.
 *
 * Streaming means output arrives as fragments, not lines: an assistant delta must append to
 * the current line, while a status change must start its own. `Renderer` tracks just enough
 * state (am I mid-stream? whose turn is this?) to insert newlines correctly.
 */

import { type ConnectionState, type RenderEvent, protocol } from "@ai-pa/letta-continuity-core";
import { indentContinuation, sanitize } from "./sanitize.js";

const { DeltaMessageTypes, StopReasons } = protocol;

export interface RendererOptions {
  /** Emit ANSI colour. Callers should pass `stdout.isTTY`. */
  color?: boolean;
  /** Show the model's reasoning deltas. Off by default — they dominate the transcript. */
  showReasoning?: boolean;
  /** Label for turns this client started. */
  selfLabel?: string;
  /** Label for turns another surface started — the visible proof of cross-surface continuity. */
  peerLabel?: string;
  /** Label for a turn we could not attribute; see TurnOrigin. */
  unknownLabel?: string;
}

const ANSI = {
  reset: "\x1b[0m",
  dim: "\x1b[2m",
  bold: "\x1b[1m",
  cyan: "\x1b[36m",
  magenta: "\x1b[35m",
  yellow: "\x1b[33m",
  red: "\x1b[31m",
};

/** Notices are status lines, not content, so they are bounded harder than delta text. */
const NOTICE_MAX_LENGTH = 512;

/**
 * Upper bound on remembered turn origins; see evictOldOrigins.
 *
 * Exported because session.ts used to declare its own copy with a comment saying it must match
 * this one — a constraint enforced by nothing. If the two drifted, the caches would evict at
 * different rates and the same run could render under two different origin labels depending on
 * which lookup path a delta took, and that label is a security signal on a shared conversation.
 */
export const MAX_TRACKED_ORIGINS = 512;

/** Which surface started a turn. `unknown` means it began before we could attribute it. */
/**
 * Which surface a turn came from.
 *
 * `unknown` is a real, expected outcome, not a defect: attribution is inferred from stream
 * position and cannot be made exact (no frame carries both our client_message_id and a run_id).
 * The renderer used to collapse it to `peer`, which asserts that another surface exists when the
 * truth is that we cannot tell — and on a shared conversation the origin label is a security
 * signal, so a confident wrong answer is worse than a hedged one.
 */
export type TurnOrigin = "self" | "peer" | "unknown";

export interface RenderContext {
  /** Did THIS client start `runId`? Backed by the core's run-ownership attribution. */
  isOwnRun(runId: string | undefined): boolean;
  /** Three-way attribution; `isOwnRun` is the collapsed form and loses the `unknown` case. */
  attributeRun(runId: string | undefined): TurnOrigin;
  queueHasMine(frame: unknown): boolean;
}

export class Renderer {
  private readonly opts: Required<RendererOptions>;
  /** True while the cursor sits mid-line inside a streamed message. */
  private streaming = false;
  /** Origin decided once per run at turn start, since ownership is released at turn end. */
  private readonly originByRun = new Map<string, TurnOrigin>();
  /**
   * Identity of the line currently streaming, as `runId|message_type`.
   *
   * NOT the message id: verified live, every delta chunk of one assistant message carries a
   * DIFFERENT `delta.id` (letta-msg-26735, -26736, …), so keying on it put each chunk on its
   * own labelled line ("agent › HE" / "agent › LL" / …). What actually stays constant across
   * a message is the run plus the message type.
   */
  private currentStreamKey: string | null = null;

  constructor(options: RendererOptions = {}) {
    this.opts = {
      color: options.color ?? false,
      showReasoning: options.showReasoning ?? false,
      selfLabel: options.selfLabel ?? "agent",
      peerLabel: options.peerLabel ?? "peer",
      unknownLabel: options.unknownLabel ?? "agent?",
    };
  }

  private paint(text: string, ...codes: string[]): string {
    if (!this.opts.color || codes.length === 0) return text;
    return `${codes.join("")}${text}${ANSI.reset}`;
  }

  /** Close an in-progress streamed line, if any. Returns the text needed to do so. */
  private closeStream(): string {
    if (!this.streaming) return "";
    this.streaming = false;
    this.currentStreamKey = null;
    return "\n";
  }

  /** A locally-typed line, echoed so the transcript reads as a conversation. */
  renderLocalInput(text: string): string {
    // Sanitized even though this is the user's OWN line. Readline consumes escapes as key events
    // only in terminal mode, and main.ts ties that mode to the colour setting — so under NO_COLOR,
    // a non-TTY stdout, or a piped session, pasted escape sequences reach this echo verbatim and
    // are written straight to the TTY (or into a session log that detonates when someone cats it).
    const safe = indentContinuation(sanitize(text, { maxLength: NOTICE_MAX_LENGTH }));
    return `${this.closeStream()}${this.paint("you ›", ANSI.bold, ANSI.cyan)} ${safe}\n`;
  }

  /** A status/system line (connection changes, errors, notices). */
  renderNotice(text: string, level: "info" | "warn" | "error" = "info"): string {
    const codes = level === "error" ? [ANSI.red] : level === "warn" ? [ANSI.yellow] : [ANSI.dim];
    // Notices routinely carry server-derived strings (error messages, stop reasons, tool names),
    // so they go through the same sanitizer as delta text — and are bounded harder, because a
    // notice is a status line, not content.
    const safe = indentContinuation(sanitize(text, { maxLength: NOTICE_MAX_LENGTH }));
    return `${this.closeStream()}${this.paint(`— ${safe}`, ...codes)}\n`;
  }

  renderConnectionState(state: ConnectionState): string {
    switch (state) {
      case "connected":
        return this.renderNotice("connected");
      case "connecting":
        return this.renderNotice("connecting…");
      case "reconnecting":
        // R17: degrade VISIBLY, never silently.
        return this.renderNotice("reconnecting…", "warn");
      case "disconnected":
        return this.renderNotice("disconnected", "error");
      default:
        return "";
    }
  }

  /** Translate one core render event into terminal output ("" when nothing should print). */
  render(event: RenderEvent, ctx: RenderContext): string {
    switch (event.type) {
      case "turn_start": {
        // Decide origin ONCE, here: run ownership is released at turn_finished, so asking
        // later would report every finished turn as foreign.
        const origin = ctx.attributeRun(event.runId);
        if (event.runId) this.originByRun.set(event.runId, origin);
        if (origin === "peer") {
          return this.renderNotice("a turn from another surface is starting");
        }
        if (origin === "unknown") {
          // Deliberately hedged. Claiming "another surface" here would be a guess presented as
          // fact on the one label the operator uses to tell their own turn from someone else's.
          return this.renderNotice("a turn is starting (origin unknown)");
        }
        return this.closeStream();
      }

      case "delta":
        return this.renderDelta(event);

      case "subagent_state": {
        const count = subagentCount(event);
        if (count === null) return "";
        return this.renderNotice(count === 0 ? "subagents idle" : `subagents active: ${count}`);
      }

      case "queue": {
        const depth = queueDepth(event);
        if (depth === null || depth === 0) return "";
        // update_queue is BROADCAST, so a non-zero depth does not mean WE are waiting. Rendering
        // it unconditionally told the surface whose turn was actually running that it was queued
        // behind itself — and an operator reading their live turn as blocked is likely to retype
        // or Ctrl-C, which on a shared conversation makes the real depth worse.
        if (!ctx.queueHasMine(event.frame)) return "";
        return this.renderNotice(`queued behind ${depth} turn${depth === 1 ? "" : "s"}…`);
      }

      case "turn_finished": {
        const out = this.closeStream();
        if (event.runId) this.originByRun.delete(event.runId);
        this.evictOldOrigins();
        if (event.stopReason && event.stopReason !== StopReasons.endTurn) {
          return `${out}${this.renderNotice(`turn ended: ${event.stopReason}`, "warn")}`;
        }
        return out;
      }

      default:
        return "";
    }
  }

  private renderDelta(event: RenderEvent): string {
    const isReasoning = event.messageType === DeltaMessageTypes.reasoning;
    if (isReasoning && !this.opts.showReasoning) return "";
    if (event.messageType !== DeltaMessageTypes.assistant && !isReasoning) return "";
    const text = event.text ?? "";
    if (text === "") return "";

    const origin = event.runId ? this.originByRun.get(event.runId) : undefined;
    const streamKey = `${event.runId ?? ""}|${event.messageType ?? ""}`;
    let prefixOut = "";
    // Start a new labelled line only when the run or the message type changes — chunks of one
    // message must append to the line already open.
    if (!this.streaming || this.currentStreamKey !== streamKey) {
      prefixOut = this.closeStream();
      const label =
        origin === "peer"
          ? this.opts.peerLabel
          : origin === "unknown"
            ? this.opts.unknownLabel
            : this.opts.selfLabel;
      const codes =
        origin === "peer"
          ? [ANSI.bold, ANSI.magenta]
          : origin === "unknown"
            ? [ANSI.bold, ANSI.yellow]
            : [ANSI.bold];
      prefixOut += `${this.paint(`${label} ›`, ...codes)} `;
      this.streaming = true;
      this.currentStreamKey = streamKey;
    }
    // Sanitize BEFORE the client adds its own colouring, so our escapes survive and the
    // server's do not. Indent continuation lines so content cannot occupy the label column.
    const safe = indentContinuation(sanitize(text));
    return prefixOut + (isReasoning ? this.paint(safe, ANSI.dim) : safe);
  }

  /**
   * Bound the origin map.
   *
   * Entries are normally removed at turn_finished, but a turn whose finish frame is lost across
   * a reconnect — the ordinary watchdog path — leaks one. On a client meant to stay attached for
   * days that is unbounded growth, and a recycled run id would render with a stale label.
   */
  /** Number of remembered turn origins. Exposed so the bound is assertable, not merely intended. */
  get trackedOriginCount(): number {
    return this.originByRun.size;
  }

  private evictOldOrigins(): void {
    while (this.originByRun.size > MAX_TRACKED_ORIGINS) {
      const oldest = this.originByRun.keys().next().value;
      if (oldest === undefined) break;
      this.originByRun.delete(oldest);
    }
  }

  /** Flush any open streamed line (e.g. before exiting). */
  finish(): string {
    return this.closeStream();
  }
}

/**
 * Subagent count via the protocol accessor rather than a raw field read.
 *
 * Reading `event.frame.subagents` here compiled even if the server renamed the field, because
 * ServerFrame has an index signature — so the indicator would silently stop appearing.
 */
function subagentCount(event: RenderEvent): number | null {
  return protocol.isSubagentState(event.frame) ? protocol.subagentCount(event.frame) : null;
}

/** Queue depth via the protocol accessor — same reasoning as subagentCount. */
function queueDepth(event: RenderEvent): number | null {
  return protocol.isQueue(event.frame) ? protocol.queueDepth(event.frame) : null;
}
