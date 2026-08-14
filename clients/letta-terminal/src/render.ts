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

/** Upper bound on remembered turn origins; see evictOldOrigins. */
const MAX_TRACKED_ORIGINS = 512;

/** Which surface started a turn. `unknown` means it began before we could attribute it. */
export type TurnOrigin = "self" | "peer";

export interface RenderContext {
  /** Did THIS client start `runId`? Backed by the core's run-ownership attribution. */
  isOwnRun(runId: string | undefined): boolean;
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
    return `${this.closeStream()}${this.paint("you ›", ANSI.bold, ANSI.cyan)} ${text}\n`;
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
        const origin: TurnOrigin = ctx.isOwnRun(event.runId) ? "self" : "peer";
        if (event.runId) this.originByRun.set(event.runId, origin);
        if (origin === "peer") {
          return this.renderNotice("a turn from another surface is starting");
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
        // The server queue-serializes concurrent sends; surface the wait rather than looking hung.
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
      const label = origin === "peer" ? this.opts.peerLabel : this.opts.selfLabel;
      const codes = origin === "peer" ? [ANSI.bold, ANSI.magenta] : [ANSI.bold];
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
