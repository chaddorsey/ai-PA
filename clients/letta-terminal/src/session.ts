/**
 * session.ts — the render loop, wired to a core but NOT to a terminal.
 *
 * `TerminalSession` takes anything shaped like the client-core and anything that accepts
 * text, so the whole loop can be driven against a stub in tests (Unit 5: "render loop against
 * a stubbed core"). main.ts supplies the real ContinuityCore and process.stdout.
 */

import type {
  ApprovalEvent,
  ConnectionState,
  ContinuityCore,
  RenderEvent,
  protocol,
} from "@ai-pa/letta-continuity-core";
import { evictOldest } from "@ai-pa/letta-continuity-core";
import {
  MAX_TRACKED_ORIGINS,
  type RenderOutput,
  Renderer,
  type RendererOptions,
  type TurnOrigin,
} from "./render.js";

/**
 * The slice of ContinuityCore this session needs — the seam a test stub implements.
 *
 * Members are declared as PROPERTIES holding function types, not with method syntax. That is the
 * whole point of the assertion below: TypeScript compares method parameters BIVARIANTLY, so a
 * core that narrowed a parameter, took a different callback shape, or dropped an argument the
 * seam promises still assigned cleanly and failed only at runtime. The conformance check was
 * therefore asserting almost nothing — it caught a missing member and nothing else. Under
 * `strictFunctionTypes`, property-held function types are checked contravariantly and the check
 * means what it says.
 */
export interface SessionCore {
  onRender: (cb: (event: RenderEvent) => void) => () => void;
  onConnectionState: (cb: (state: ConnectionState, prev: ConnectionState) => void) => () => void;
  onError: (cb: (err: Error) => void) => () => void;
  onApproval: (cb: (e: ApprovalEvent) => void) => () => void;
  ownsRun: (runId: string | undefined) => boolean;
  /** Three-way attribution. `ownsRun` collapses `foreign` and `unknown` into a single false. */
  attributeRun: (runId: string | undefined) => "mine" | "foreign" | "unknown";
  /** Whether an update_queue frame contains one of OUR queued messages. */
  queueHasMine: (frame: protocol.ServerFrame, origin?: string) => boolean;
  send: (text: string) => void;
}

/**
 * `ContinuityCore` must satisfy the seam. Without this the only check is the single
 * `new TerminalSession(core, …)` call in main.ts, which type-checks one direction of one usage.
 */
type SessionCoreConformance = ContinuityCore extends SessionCore ? true : never;
/** Use site: when the conditional above resolves to `never`, this assignment fails to compile. */
const _coreSatisfiesSeam: SessionCoreConformance = true;
void _coreSatisfiesSeam;

export interface SessionOptions extends RendererOptions {
  write: (text: string) => void;
  /**
   * Sink for diagnostics — errors, connection state, approval notices, undelivered warnings.
   *
   * Separate from `write` so a caller capturing the transcript does not also capture client
   * chatter. Everything used to share one sink wired to stdout, so an automation grepping the
   * last `agent ›` line could find `— reconnecting…` or a red error interleaved with the reply,
   * and `2>/dev/null` suppressed none of it. Defaults to `write` for callers that do not care.
   */
  writeErr?: (text: string) => void;
}

/** What a typed or piped line MEANS, decided before anything is sent or echoed. */
export type InputIntent = { kind: "ignored" } | { kind: "exit" } | { kind: "send"; text: string };

/**
 * Interpret one input line. The SINGLE place that decides what a line means.
 *
 * The `--json` one-shot re-implemented the send path so its local echo would not pollute an
 * NDJSON stdout — and in re-implementing it, it dropped the two rules that live here. `--json`
 * would send a blank message as a turn, and would send the literal text `/exit` to the agent
 * rather than leaving. Same client, same input, two different meanings, depending on an output
 * flag. The echo is what legitimately differs between the two paths; the meaning of the line is
 * not, so only the echo is duplicated now.
 */
export function classifyInput(line: string): InputIntent {
  const trimmed = line.trim();
  if (trimmed === "") return { kind: "ignored" };
  if (trimmed === "/exit" || trimmed === "/quit") return { kind: "exit" };
  return { kind: "send", text: trimmed };
}

export class TerminalSession {
  private readonly core: SessionCore;
  private readonly renderer: Renderer;
  private readonly write: (text: string) => void;
  private readonly writeErr: (text: string) => void;
  private readonly unsubscribes: Array<() => void> = [];
  /**
   * Attribution must be captured at turn START — ownership is released at turn_finished, so a
   * later lookup reports every completed turn as foreign. Cached per run for the renderer.
   */
  private readonly originCache = new Map<string, TurnOrigin>();

  constructor(core: SessionCore, options: SessionOptions) {
    this.core = core;
    this.write = options.write;
    this.writeErr = options.writeErr ?? options.write;
    this.renderer = new Renderer(options);
  }

  /** Subscribe to the core. Returns a function that detaches every listener. */
  attach(): () => void {
    this.unsubscribes.push(
      this.core.onRender((event) => this.onRender(event)),
      this.core.onConnectionState((state) => this.onConnectionState(state)),
      this.core.onError((err) => this.onError(err)),
      this.core.onApproval((e) => this.onApproval(e)),
    );
    return () => {
      for (const off of this.unsubscribes) off();
      this.unsubscribes.length = 0;
    };
  }

  private onRender(event: RenderEvent): void {
    // Capture attribution AT turn_start. Ownership is released at turn_finished, so asking later
    // would report every completed turn of our own as somebody else's.
    if (event.type === "turn_start" && event.runId) {
      this.originCache.set(event.runId, this.attribute(event.runId));
    }
    const out = this.renderer.render(event, {
      queueHasMine: (frame) => this.core.queueHasMine(frame),
      attributeRun: (runId) => {
        if (runId === undefined) return "unknown";
        return this.originCache.get(runId) ?? this.attribute(runId);
      },
    });
    if (event.type === "turn_finished" && event.runId) this.originCache.delete(event.runId);
    // A turn_finished lost across a reconnect would otherwise leak an entry per interrupted turn.
    evictOldest(this.originCache, MAX_TRACKED_ORIGINS);
    this.emit(out);
  }

  /** Route a renderer result to its two sinks. */
  private emit(out: RenderOutput): void {
    if (out.transcript) this.write(out.transcript);
    if (out.notice) this.writeErr(out.notice);
  }

  /** Map the core's attribution onto the renderer's origin vocabulary. */
  private attribute(runId: string): TurnOrigin {
    const a = this.core.attributeRun(runId);
    return a === "mine" ? "self" : a === "foreign" ? "peer" : "unknown";
  }

  private onConnectionState(state: ConnectionState): void {
    this.emit(this.renderer.renderConnectionState(state));
  }

  /**
   * An approval is a security-relevant event, so it is shown even though M1 answers it
   * automatically: an auto-deny nobody sees is indistinguishable from the agent choosing not to
   * use a tool. The tool NAME is server-derived and sanitized by renderNotice; the tool ARGUMENTS
   * are deliberately never surfaced — they routinely carry file contents or credentials.
   */
  private onApproval(e: { toolName: string | undefined; outcome: string }): void {
    // Two regimes share this channel: the raw path's auto-deny backstop, and the controller
    // path's operator-answerable arbitration (C6).
    const detail =
      e.outcome === "pending"
        ? "/approve or /deny to answer"
        : `auto-${e.outcome}; no approval UI in this milestone`;
    this.emit(
      this.renderer.renderNotice(
        `tool approval requested (${e.toolName ?? "unknown tool"}) — ${detail}`,
        "warn",
      ),
    );
  }

  private onError(err: Error): void {
    this.emit(this.renderer.renderNotice(err.message, "error"));
  }

  /**
   * Handle a line typed by the user. Returns "exit" when the session should end.
   * Blank lines are ignored so a stray Enter does not start an empty turn.
   */
  handleInput(line: string): "sent" | "ignored" | "failed" | "exit" {
    const intent = classifyInput(line);
    if (intent.kind !== "send") return intent.kind;
    const trimmed = intent.text;
    // Submit FIRST, echo second. `core.send()` throws when the socket is not open, and echoing
    // before the send would print the line as though it had been delivered — the transcript would
    // claim something that never happened. A throw here also used to escape the readline handler
    // and kill the process, which is the worst possible moment: the user typing during a
    // reconnect is exactly when the client must degrade visibly instead of vanishing.
    try {
      this.core.send(trimmed);
    } catch (err) {
      this.emit(
        this.renderer.renderNotice(
          `not sent (${err instanceof Error ? err.message : String(err)}) — still reconnecting`,
          "warn",
        ),
      );
      // NOT "ignored". A turn that was never delivered and a blank line the user typed are
      // different events, and collapsing them meant the caller could not tell three swallowed
      // messages from three empty Enters — it just exited 0 either way.
      return "failed";
    }
    this.write(this.renderer.renderLocalInput(trimmed));
    return "sent";
  }

  /**
   * Remembered turn origins, across BOTH caches. The test that was supposed to cover the bound
   * asserted only that a string appeared, which held whether or not eviction ran — disabling both
   * eviction loops left the suite green.
   */
  get trackedOriginCount(): { session: number; renderer: number } {
    return { session: this.originCache.size, renderer: this.renderer.trackedOriginCount };
  }

  /** Flush any open streamed line. */
  finish(): void {
    const text = this.renderer.finish();
    if (text) this.write(text);
  }
}
