/**
 * session.ts — the render loop, wired to a core but NOT to a terminal.
 *
 * `TerminalSession` takes anything shaped like the client-core and anything that accepts
 * text, so the whole loop can be driven against a stub in tests (Unit 5: "render loop against
 * a stubbed core"). main.ts supplies the real ContinuityCore and process.stdout.
 */

import type { ConnectionState, RenderEvent } from "@ai-pa/letta-continuity-core";
import { Renderer, type RendererOptions } from "./render.js";

/** The slice of ContinuityCore this session needs — the seam a test stub implements. */
export interface SessionCore {
  onRender(cb: (event: RenderEvent) => void): () => void;
  onConnectionState(cb: (state: ConnectionState) => void): () => void;
  onError(cb: (err: Error) => void): () => void;
  ownsRun(runId: string | undefined): boolean;
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
  private readonly originCache = new Map<string, boolean>();

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
    );
    return () => {
      for (const off of this.unsubscribes) off();
      this.unsubscribes.length = 0;
    };
  }

  private onRender(event: RenderEvent): void {
    if (event.type === "turn_start" && event.runId) {
      this.originCache.set(event.runId, this.core.ownsRun(event.runId));
    }
    const text = this.renderer.render(event, {
      isOwnRun: (runId) => {
        if (runId === undefined) return true;
        const cached = this.originCache.get(runId);
        return cached ?? this.core.ownsRun(runId);
      },
    });
    if (event.type === "turn_finished" && event.runId) this.originCache.delete(event.runId);
    if (text) this.write(text);
  }

  private onConnectionState(state: ConnectionState): void {
    const text = this.renderer.renderConnectionState(state);
    if (text) this.write(text);
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
    this.write(this.renderer.renderLocalInput(trimmed));
    this.core.send(trimmed);
    return "sent";
  }

  /** Flush any open streamed line. */
  finish(): void {
    const text = this.renderer.finish();
    if (text) this.write(text);
  }
}
