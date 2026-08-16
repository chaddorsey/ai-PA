/**
 * A minimal raw-WS surface client for the C5 tests: connects to the controller's /surface
 * endpoint, collects every frame, and offers promise-shaped attach/send/rpc helpers. Not a
 * production client — the terminal (C6) is that.
 */

import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { WebSocket } = require("ws") as typeof import("ws");

export type SurfaceFrame = { type: string } & Record<string, unknown>;

export class TestSurface {
  readonly frames: SurfaceFrame[] = [];
  private socket: import("ws").WebSocket | null = null;

  async connect(port: number): Promise<void> {
    const socket = new WebSocket(`ws://127.0.0.1:${port}/surface`);
    this.socket = socket;
    socket.on("message", (d) => {
      const frame = JSON.parse(d.toString()) as SurfaceFrame;
      this.frames.push(frame);
      socket.emit("surface-frame", frame);
    });
    await new Promise<void>((resolve, reject) => {
      socket.once("open", () => resolve());
      socket.once("error", (e: Error) => reject(e));
    });
  }

  send(frame: Record<string, unknown>): void {
    this.socket?.send(JSON.stringify(frame));
  }

  /** Send and await the first frame matching the predicate. */
  request(
    frame: Record<string, unknown>,
    match: (f: SurfaceFrame) => boolean,
    ms = 5000,
  ): Promise<SurfaceFrame> {
    return new Promise((resolve, reject) => {
      const socket = this.socket;
      if (!socket) return reject(new Error("not connected"));
      const timer = setTimeout(() => {
        socket.off("surface-frame", onFrame);
        reject(new Error("timeout waiting for surface frame"));
      }, ms);
      const onFrame = (f: SurfaceFrame) => {
        if (!match(f)) return;
        clearTimeout(timer);
        socket.off("surface-frame", onFrame);
        resolve(f);
      };
      socket.on("surface-frame", onFrame);
      this.send(frame);
    });
  }

  waitFrame(match: (f: SurfaceFrame) => boolean, ms = 5000): Promise<SurfaceFrame | null> {
    const existing = this.frames.find(match);
    if (existing) return Promise.resolve(existing);
    return new Promise((resolve) => {
      const socket = this.socket;
      if (!socket) return resolve(null);
      const timer = setTimeout(() => {
        socket.off("surface-frame", onFrame);
        resolve(null);
      }, ms);
      const onFrame = (f: SurfaceFrame) => {
        if (!match(f)) return;
        clearTimeout(timer);
        socket.off("surface-frame", onFrame);
        resolve(f);
      };
      socket.on("surface-frame", onFrame);
    });
  }

  attach(options: {
    token: string;
    runtime: { agent_id: string; conversation_id: string };
    capabilities?: string[];
    cursor?: number | null;
    protocolVersion?: number;
  }): Promise<SurfaceFrame> {
    return this.request(
      {
        type: "attach",
        token: options.token,
        protocol_version: options.protocolVersion ?? 1,
        capabilities: options.capabilities ?? ["core"],
        runtime: options.runtime,
        cursor: options.cursor ?? null,
      },
      (f) => f.type === "attach_ok" || f.type === "attach_denied",
    );
  }

  close(): void {
    this.socket?.close();
    this.socket = null;
  }
}
