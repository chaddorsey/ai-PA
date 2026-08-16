#!/usr/bin/env tsx
/**
 * main.ts — process entry for the Continuity Controller.
 *
 *   continuity-controller worker            # the feature-rich daemon (default)
 *   continuity-controller anchor            # the subscribe-only crash-overlap daemon
 *   continuity-controller registry list
 *   continuity-controller registry add --agent <id> [--label <s>] [--temp hot|cold]
 *   continuity-controller registry set-temp --agent <id> --conversation <id> --temp hot|cold
 *
 * `registry add` CREATES the conversation over WS (`conversation_create`) and registers the
 * returned real id — never the `default` alias (C1 S3: the alias is unresolvable by
 * `conversation_messages_list`, which C4's reconciliation depends on).
 *
 * Exit codes: 0 clean stop · 75 (EX_TEMPFAIL) reconnect budget exhausted or state missing —
 * launchd's KeepAlive+ThrottleInterval is the outer retry loop, visible in Console.
 */

import { Outbound, buildConversationCreate } from "@ai-pa/letta-continuity-core/protocol";
import { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { AnchorDaemon } from "./anchor.js";
import { loadConfig } from "./config.js";
import { TurnJournal } from "./journal.js";
import { ReadOnlyRegistry, Registry } from "./registry.js";
import { openStateDb, openStateDbReadOnly } from "./state/db.js";
import { Journal } from "./state/journal.js";
import { enqueueDurable } from "./turns.js";
import { WorkerDaemon } from "./worker.js";

const EX_TEMPFAIL = 75;

function log(msg: string): void {
  console.error(`${new Date().toISOString()} ${msg}`);
}

function flag(args: string[], name: string): string | undefined {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : undefined;
}

function installSignalStop(stop: () => void): void {
  for (const sig of ["SIGINT", "SIGTERM"] as const) {
    process.on(sig, () => {
      log(`${sig} — stopping`);
      stop();
      process.exit(0);
    });
  }
}

async function runWorker(): Promise<void> {
  const config = loadConfig();
  const { db, degraded } = openStateDb(config.stateDir);
  const worker = new WorkerDaemon({
    url: config.wsUrl,
    db,
    registry: new Registry(db),
    journal: new Journal(db),
    livenessFile: config.livenessFile,
    livenessIntervalMs: config.livenessIntervalMs,
    livenessDeadlineMs: config.livenessDeadlineMs,
    hotsetPollMs: config.hotsetPollMs,
    queuePollMs: config.queuePollMs,
    turnTimeoutMs: config.turnTimeoutMs,
    abortConfirmMs: config.abortConfirmMs,
    surfacePort: config.surfacePort,
    // Fail CLOSED: without a secret the Docker-wide-reachable ingress must not exist at all.
    ...(config.ingressSecret
      ? { ingressPort: config.ingressPort, ingressSecret: config.ingressSecret }
      : {}),
    stateDir: config.stateDir,
    runtimeMode: process.env.CONTINUITY_RUNTIME_MODE,
    degraded,
    onWarn: log,
    onExhausted: () => {
      log("reconnect budget exhausted — exiting for launchd to restart");
      process.exit(EX_TEMPFAIL);
    },
  });
  installSignalStop(() => worker.stop());
  if (!config.ingressSecret)
    log("ingress DISABLED (set CONTINUITY_INGRESS_SECRET to serve the scheduler dialect)");
  log(`worker starting: ws=${config.wsUrl} state=${config.stateDir}`);
  await worker.start();
}

async function runAnchor(): Promise<void> {
  const config = loadConfig();
  let registry: ReadOnlyRegistry;
  try {
    registry = new ReadOnlyRegistry(openStateDbReadOnly(config.stateDir));
  } catch (e) {
    log(e instanceof Error ? e.message : String(e));
    process.exit(EX_TEMPFAIL);
  }
  const anchor = new AnchorDaemon({
    url: config.wsUrl,
    registry,
    hotsetPollMs: config.hotsetPollMs,
    onWarn: log,
    onExhausted: () => {
      log("reconnect budget exhausted — exiting for launchd to restart");
      process.exit(EX_TEMPFAIL);
    },
  });
  installSignalStop(() => anchor.stop());
  log(`anchor starting: ws=${config.wsUrl} state=${config.stateDir} (read-only)`);
  await anchor.start();
}

async function runRegistry(args: string[]): Promise<void> {
  const config = loadConfig();
  const command = args[0];
  const { db, degraded } = openStateDb(config.stateDir);
  if (degraded) log(`WARNING — state db degraded: ${degraded}`);
  const registry = new Registry(db);
  const journal = new Journal(db);

  if (command === "list") {
    for (const row of registry.list()) {
      const broken = row.broken ? `  BROKEN: ${row.broken}` : "";
      console.log(
        `${row.temp.padEnd(4)} ${row.agent_id} ${row.conversation_id} [${row.label}]${broken}`,
      );
    }
    console.log(`hotset_version=${registry.hotsetVersion()}`);
    return;
  }

  if (command === "add") {
    const agentId = flag(args, "agent");
    if (!agentId) throw new Error("registry add requires --agent <id>");
    const label = flag(args, "label") ?? "";
    const temp = (flag(args, "temp") ?? "hot") as "hot" | "cold";
    const isDefault = args.includes("--default");
    const conn = new WsConnection({ url: config.wsUrl, versionPolicy: "warn", onWarn: log });
    await conn.connectBare();
    try {
      const created = await conn.request(
        (rid) => buildConversationCreate(rid, agentId, label || "continuity"),
        Outbound.conversationCreate,
      );
      if (created.success !== true) {
        throw new Error(`conversation_create failed: ${String(created.error ?? "refused")}`);
      }
      const conversationId = (created.conversation as { id?: string } | null)?.id;
      if (typeof conversationId !== "string") throw new Error("no conversation id in response");
      registry.upsert({
        agent_id: agentId,
        conversation_id: conversationId,
        label,
        temp,
        origin: isDefault ? { default: true } : {},
      });
      journal.append("registry_upsert", {
        agent_id: agentId,
        conversation_id: conversationId,
        label,
        temp,
        via: "cli",
      });
      console.log(`${agentId} ${conversationId} [${label}] ${temp}`);
    } finally {
      conn.close();
    }
    return;
  }

  if (command === "set-temp") {
    const agentId = flag(args, "agent");
    const conversationId = flag(args, "conversation");
    const temp = flag(args, "temp") as "hot" | "cold" | undefined;
    if (!agentId || !conversationId || !temp) {
      throw new Error("registry set-temp requires --agent, --conversation, --temp");
    }
    registry.setTemp({ agent_id: agentId, conversation_id: conversationId }, temp);
    journal.append("registry_set_temp", {
      agent_id: agentId,
      conversation_id: conversationId,
      temp,
      via: "cli",
    });
    console.log(`ok hotset_version=${registry.hotsetVersion()}`);
    return;
  }

  throw new Error(`unknown registry command: ${String(command)}`);
}

/** Operator route authoring (C8). Same table the running worker reads; mutations journaled. */
async function runRoutes(args: string[]): Promise<void> {
  const config = loadConfig();
  const { db } = openStateDb(config.stateDir);
  const registry = new Registry(db);
  const journal = new TurnJournal(db);
  const { RouteTable } = await import("./routing/routes.js");
  const routes = new RouteTable(db, registry, journal);
  const command = args[0];
  if (command === "list") {
    for (const r of routes.list())
      console.log(`@${r.alias} → ${r.agent_id}/${r.conversation_id} (by ${r.author})`);
    return;
  }
  if (command === "set") {
    const alias = flag(args, "alias");
    const agentId = flag(args, "agent");
    if (!alias || !agentId) throw new Error("routes set requires --alias and --agent");
    const route = routes.set(alias, agentId, flag(args, "conversation"), "operator-cli");
    console.log(`@${route.alias} → ${route.agent_id}/${route.conversation_id}`);
    return;
  }
  if (command === "delete") {
    const alias = flag(args, "alias");
    if (!alias) throw new Error("routes delete requires --alias");
    console.log(routes.delete(alias, "operator-cli") ? "deleted" : "no such route");
    return;
  }
  throw new Error(`unknown routes command: ${String(command)}`);
}

/** Durable enqueue from OUTSIDE the worker (tests, cron, ops). The worker's poll picks it up. */
async function runEnqueue(args: string[]): Promise<void> {
  const config = loadConfig();
  const agentId = flag(args, "agent");
  const conversationId = flag(args, "conversation");
  const text = flag(args, "text");
  if (!agentId || !conversationId || !text) {
    throw new Error("enqueue requires --agent, --conversation, --text");
  }
  const { db, degraded } = openStateDb(config.stateDir);
  if (degraded) log(`WARNING — state db degraded: ${degraded}`);
  const clientMessageId = enqueueDurable(
    db,
    new TurnJournal(db),
    { agent_id: agentId, conversation_id: conversationId },
    text,
    { via: "cli" },
  );
  console.log(clientMessageId);
}

/** Inspect the turn queue (state + outcome — the FAILED-VISIBLE surface until C5 renders it). */
async function runQueue(args: string[]): Promise<void> {
  const config = loadConfig();
  const { db } = openStateDb(config.stateDir);
  const cm = flag(args, "cm");
  const rows = db
    .prepare(
      cm
        ? "SELECT * FROM turn_queue WHERE client_message_id = ?"
        : "SELECT * FROM turn_queue ORDER BY id DESC LIMIT 20",
    )
    .all(...(cm ? [cm] : [])) as Array<Record<string, unknown>>;
  for (const r of rows) {
    console.log(
      `${String(r.state).padEnd(10)} ${String(r.outcome ?? "-").padEnd(28)} ${r.client_message_id} ${r.agent_id}/${r.conversation_id}`,
    );
  }
}

async function main(): Promise<void> {
  const [role = "worker", ...rest] = process.argv.slice(2);
  if (role === "worker") return runWorker();
  if (role === "anchor") return runAnchor();
  if (role === "registry") return runRegistry(rest);
  if (role === "enqueue") return runEnqueue(rest);
  if (role === "routes") return runRoutes(rest);
  if (role === "queue") return runQueue(rest);
  console.error(`usage: continuity-controller <worker|anchor|registry> …  (got: ${role})`);
  process.exit(2);
}

main().catch((e) => {
  log(e instanceof Error ? (e.stack ?? e.message) : String(e));
  process.exit(1);
});
