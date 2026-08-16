/**
 * ingress/scheduler.ts — the R3/G3 delivery seam: the controller SPEAKS THE SCHEDULER'S
 * EXISTING DIALECT (`POST /v1/agents/{agent_id}/messages`, body
 * `{"messages":[{"role","content"}]}` — bug-compatible with actions.py), so re-pointing
 * `LETTA_CALLBACK_URL` is the only scheduler-side change.
 *
 * Security (plan, Key Technical Decisions): `host.docker.internal` makes this reachable from
 * EVERY container on the box, so the shared secret is the control, not the bind address. Two
 * presentations are accepted:
 *   - `Authorization: Bearer <secret>` — preferred; requires the sender to set a header;
 *   - a path prefix `/t/<secret>/v1/agents/…` — config-only for senders that cannot set
 *     headers (actions.py sets none). CAVEAT for the runbook: actions.py logs the full URL on
 *     info AND error paths, so the path form leaks the secret into scheduler logs — choose it
 *     only with that documented.
 *
 * Response semantics are a stated decision: **202-on-accept**. The scheduler's execution
 * records become DELIVERY records; turn outcome is controller-journal truth. Every rejection
 * is journaled (G5) — an unauthenticated POST is visible history, not a dropped packet.
 */

import { timingSafeEqual } from "node:crypto";
import { type IncomingMessage, type Server, type ServerResponse, createServer } from "node:http";
import type { TurnJournal } from "../journal.js";
import type { Registry } from "../registry.js";
import type { AwarenessManager } from "../routing/awareness.js";
import { resolveLanding } from "../routing/landing.js";
import type { TurnPipeline } from "../turns.js";

export interface IngressOptions {
  secret: string;
  registry: Registry;
  pipeline: TurnPipeline;
  journal: TurnJournal;
  awareness: AwarenessManager;
  onWarn?: (msg: string) => void;
}

const PATH_WITH_TOKEN = /^\/t\/([^/]+)\/v1\/agents\/([^/]+)\/messages$/;
const PATH_BARE = /^\/v1\/agents\/([^/]+)\/messages$/;

function secretsEqual(expected: string, presented: string): boolean {
  const a = Buffer.from(expected);
  const b = Buffer.from(presented);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

export class IngressServer {
  private http: Server | null = null;

  constructor(private readonly opts: IngressOptions) {
    if (!opts.secret) {
      // Refusing to start beats starting open: with no secret the Docker-wide-reachable
      // endpoint would accept any container's POSTs as the operator's agents.
      throw new Error("ingress requires a shared secret (CONTINUITY_INGRESS_SECRET)");
    }
  }

  /** Loopback only; port 0 = ephemeral (tests). Returns the bound port. */
  async start(port: number): Promise<number> {
    this.http = createServer((req, res) => void this.handle(req, res));
    await new Promise<void>((resolve) => this.http?.listen(port, "127.0.0.1", resolve));
    const address = this.http?.address();
    return typeof address === "object" && address !== null ? address.port : port;
  }

  async stop(): Promise<void> {
    await new Promise<void>((resolve) => {
      this.http?.close(() => resolve());
      if (!this.http) resolve();
    });
    this.http = null;
  }

  private async handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const journalReject = (status: number, reason: string, agentId?: string): void => {
      this.opts.journal.record({
        runtime: { agent_id: agentId ?? "unknown", conversation_id: "ingress" },
        kind: "ingress_rejected",
        payload: { status, reason, path: req.url ?? "", method: req.method ?? "" },
      });
      res.statusCode = status;
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify({ error: reason }));
    };

    if (req.method !== "POST") return journalReject(405, "method not allowed");
    const url = req.url ?? "";
    const withToken = PATH_WITH_TOKEN.exec(url);
    const bare = withToken ? null : PATH_BARE.exec(url);
    if (!withToken && !bare) return journalReject(404, "unknown path");

    const agentId = decodeURIComponent((withToken ? withToken[2] : bare?.[1]) ?? "");
    const pathToken = withToken ? decodeURIComponent(withToken[1] ?? "") : null;
    const header = req.headers.authorization ?? "";
    const bearer = header.startsWith("Bearer ") ? header.slice(7) : null;
    const presented = bearer ?? pathToken;
    if (!presented || !secretsEqual(this.opts.secret, presented)) {
      return journalReject(401, "missing or invalid ingress secret", agentId);
    }

    let body: { messages?: Array<{ role?: string; content?: string }>; conversation_tag?: string };
    try {
      const chunks: Buffer[] = [];
      for await (const chunk of req) chunks.push(Buffer.from(chunk));
      body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    } catch {
      return journalReject(400, "body is not JSON", agentId);
    }
    const messages = Array.isArray(body.messages) ? body.messages : [];
    const content = messages
      .map((m) => (typeof m.content === "string" ? m.content : ""))
      .filter((c) => c !== "")
      .join("\n");
    if (content === "") return journalReject(400, "no message content", agentId);

    const landing = resolveLanding(this.opts.registry, agentId, body.conversation_tag);
    if (!landing) {
      return journalReject(
        404,
        body.conversation_tag
          ? `no registry row labeled "${body.conversation_tag}" for agent ${agentId}`
          : `agent ${agentId} has no registered conversation`,
        agentId,
      );
    }

    const runtime = { agent_id: landing.agent_id, conversation_id: landing.conversation_id };
    // The turn runs through C4 exactly like a surface turn; awareness defaults to `badge`.
    const clientMessageId = this.opts.pipeline.accept(runtime, content, {
      via: "scheduler-ingress",
      tag: body.conversation_tag ?? null,
    });
    this.opts.journal.record({
      runtime,
      clientMessageId,
      kind: "ingress_accepted",
      payload: { tag: body.conversation_tag ?? null },
    });
    this.opts.awareness.signal(runtime, clientMessageId, "badge");

    // 202-on-accept: delivery acknowledged; the turn's OUTCOME is controller-journal truth.
    res.statusCode = 202;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ accepted: true, client_message_id: clientMessageId }));
  }
}
