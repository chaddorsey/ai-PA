/**
 * session.ts — the render loop, wired to a core but NOT to a terminal.
 *
 * `TerminalSession` takes anything shaped like the client-core and anything that accepts
 * text, so the whole loop can be driven against a stub in tests (Unit 5: "render loop against
 * a stubbed core"). main.ts supplies the real ContinuityCore and process.stdout.
 */

import type { ConnectionState, ContinuityCore, RenderEvent } from "@ai-pa/letta-continuity-core";
import { MAX_TRACKED_ORIGINS, Renderer, type RendererOptions, type TurnOrigin } from "./render.js";

/**
 * `ContinuityCore` must satisfy this seam. Without an explicit assertion the only check is the
 * single `new TerminalSession(core, …)` call in main.ts — and because the members are declared
 * with method syntax, TypeScript compares their parameters BIVARIANTLY, so a core that narrowed
 * a parameter type would still assign cleanly and fail only at runtime. This makes the
 * conformance a compile error at the point the seam is defined.
 */
type SessionCoreConformance = ContinuityCore extends SessionCore ? true : never;
/** Use site: when the conditional above resolves to `never`, this assignment fails to compile. */
const _coreSatisfiesSeam: SessionCoreConformance = true;
void _coreSatisfiesSeam;

/** The slice of ContinuityCore this session needs — the seam a test stub implements. */
export interface SessionCore {
  onRender(cb: (event: RenderEvent) => void): () => void;
  onConnectionState(cb: (state: ConnectionState) => void): () => void;
  onError(cb: (err: Error) => void): () => void;
  onApproval(cb: (e: { toolName: string | undefined; outcome: string }) => void): () => void;
  ownsRun(runId: string | undefined): boolean;
  /** Three-way attribution. `ownsRun` collapses `foreign` and `unknown` into a single false. */
  attributeRun(runId: string | undefined): "mine" | "foreign" | "unknown";
  /** Whether an update_queue frame contains one of OUR queued messages. */
  queueHasMine(frame: unknown): boolean;
  send(text: string): void;
}

export interface SessionOptions extends RendererOptions {
  write: (text: string) => void;
}

export class TerminalSession {
  private readonly core: SessionCore;
  private readonly renderer: Renderer;
  private readonly write: (text: string) => void;
  private readonly unsubscribes: Array<() => void> = [];
  /**
   * Attribution must be captured at turn START — ownership is released at turn_finished, so a
   * later lookup reports every completed turn as foreign. Cached per run for the renderer.
   */
  private readonly originCache = new Map<string, TurnOrigin>();

  constructor(core: SessionCore, options: SessionOptions) {
    this.core = core;
    this.write = options.write;
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
    const text = this.renderer.render(event, {
      queueHasMine: (frame) => this.core.queueHasMine(frame),
      attributeRun: (runId) => {
        if (runId === undefined) return "self";
        return this.originCache.get(runId) ?? this.attribute(runId);
      },
      isOwnRun: (runId) => {
        if (runId === undefined) return true;
        return (this.originCache.get(runId) ?? this.attribute(runId)) === "self";
      },
    });
    if (event.type === "turn_finished" && event.runId) this.originCache.delete(event.runId);
    // A turn_finished lost across a reconnect would otherwise leak an entry per interrupted turn.
    while (this.originCache.size > MAX_TRACKED_ORIGINS) {
      const oldest = this.originCache.keys().next().value;
      if (oldest === undefined) break;
      this.originCache.delete(oldest);
    }
    if (text) this.write(text);
  }

  /** Map the core's attribution onto the renderer's origin vocabulary. */
  private attribute(runId: string): TurnOrigin {
    const a = this.core.attributeRun(runId);
    return a === "mine" ? "self" : a === "foreign" ? "peer" : "unknown";
  }

  private onConnectionState(state: ConnectionState): void {
    const text = this.renderer.renderConnectionState(state);
    if (text) this.write(text);
  }

  /**
   * An approval is a security-relevant event, so it is shown even though M1 answers it
   * automatically: an auto-deny nobody sees is indistinguishable from the agent choosing not to
   * use a tool. The tool NAME is server-derived and sanitized by renderNotice; the tool ARGUMENTS
   * are deliberately never surfaced — they routinely carry file contents or credentials.
   */
  private onApproval(e: { toolName: string | undefined; outcome: string }): void {
    this.write(
      this.renderer.renderNotice(
        `tool approval requested (${e.toolName ?? "unknown tool"}) — auto-${e.outcome}; no approval UI in this milestone`,
        "warn",
      ),
    );
  }

  private onError(err: Error): void {
    this.write(this.renderer.renderNotice(err.message, "error"));
  }

  /**
   * Handle a line typed by the user. Returns "exit" when the session should end.
   * Blank lines are ignored so a stray Enter does not start an empty turn.
   */
  handleInput(line: string): "sent" | "ignored" | "exit" {
    const trimmed = line.trim();
    if (trimmed === "") return "ignored";
    if (trimmed === "/exit" || trimmed === "/quit") return "exit";
    // Submit FIRST, echo second. `core.send()` throws when the socket is not open, and echoing
    // before the send would print the line as though it had been delivered — the transcript would
    // claim something that never happened. A throw here also used to escape the readline handler
    // and kill the process, which is the worst possible moment: the user typing during a
    // reconnect is exactly when the client must degrade visibly instead of vanishing.
    try {
      this.core.send(trimmed);
    } catch (err) {
      this.write(
        this.renderer.renderNotice(
          `not sent (${err instanceof Error ? err.message : String(err)}) — still reconnecting`,
          "warn",
        ),
      );
      return "ignored";
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
