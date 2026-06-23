/**
 * connectivity-failover — Spike B proof mod (laptop spoke #1)
 *
 * Reads the conn-probe link state (~/.letta/offline-bus/link.json) and surfaces it
 * in the Letta Code statusline, refreshing on every `tick` event. The `/connectivity`
 * command reports link state + the intended failover model and (when ARMED) performs
 * the model swap.
 *
 * Verified mod API (from the bundled letta-code source — see spike-findings §B):
 *   - export:    `export default function activate(letta)`  (or `export function activate`)
 *   - events:    letta.events.on('tick', fn)                 // periodic hook
 *   - statusline: letta.ui.setStatus(key, text)              // string value
 *   - commands:  letta.commands.register({ id, description, run(ctx) })
 *                run(ctx) → must return { type: 'prompt' | 'output' | 'handled', ... }
 *                ctx.agent.id is the active agent id
 *   - client:    letta.getClient() → client.agents.update(agentId, { model })  // REST
 *
 * MODEL-SWAP MECHANISM (verified): a mod swaps the model via
 *   `client.agents.update(agentId, { model: <handle> })`.
 * This is a CONFIG-level (next-turn) swap. The live, conversation-scoped,
 * context-window-preserving swap is `applyModelUpdateForRuntime` behind the
 * `update_model` WsProtocol command — NOT reachable from a mod. Next-turn swap is
 * the correct/sufficient behavior for connectivity failover.
 *
 * SAFETY: the swap only runs when env `CONNECTIVITY_FAILOVER_ARM=1`. Unarmed (default),
 * `/connectivity` reports a dry-run so loading/testing never mutates a live agent.
 * The Task-6 production mod will arm it and drive the swap automatically on `tick`.
 */
import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const LINK_JSON = join(homedir(), ".letta", "offline-bus", "link.json");
const STATUS_KEY = "connectivity";
const ARMED = process.env.CONNECTIVITY_FAILOVER_ARM === "1";

// Model handles the spine swaps between (placeholders until Task 5 sets the mini-me's real cloud handle).
const LOCAL_MODEL = process.env.FAILOVER_LOCAL_MODEL || "ollama/GLM-4.5-Air-4bit";
const CLOUD_MODEL = process.env.FAILOVER_CLOUD_MODEL || "cloud";

function readLink() {
  try {
    if (!existsSync(LINK_JSON)) return { online: null, reason: "no link.json" };
    return JSON.parse(readFileSync(LINK_JSON, "utf8"));
  } catch (e) {
    return { online: null, reason: String(e && e.message ? e.message : e) };
  }
}

const statusText = (link) =>
  link.online === false ? "🔴 offline · local" : link.online === true ? "🟢 online · cloud" : "⚪ link?";

const targetModel = (link) => (link.online === false ? LOCAL_MODEL : CLOUD_MODEL);

async function swapModel(letta, agentId, handle) {
  // Verified mechanism: REST agent update with a `model` field (next-turn effect).
  const client = await letta.getClient();
  await client.agents.update(agentId, { model: handle });
}

export default function activate(letta) {
  const refresh = () => {
    try {
      letta?.ui?.setStatus?.(STATUS_KEY, statusText(readLink()));
    } catch {
      /* statusline capability may be unavailable */
    }
  };
  refresh();
  try {
    letta?.events?.on?.("tick", refresh);
  } catch {
    /* events capability may be unavailable */
  }

  try {
    letta?.commands?.register?.({
      id: "connectivity",
      description: "Show conn-probe link state and (when armed) swap the failover model",
      async run(ctx) {
        const link = readLink();
        const want = targetModel(link);
        const agentId = ctx?.agent?.id ?? null;
        let action = `DRY-RUN (set CONNECTIVITY_FAILOVER_ARM=1 to swap)`;
        if (ARMED && agentId && want && want !== "cloud") {
          try {
            await swapModel(letta, agentId, want);
            action = `swapped agent ${agentId} → model ${want}`;
          } catch (e) {
            action = `swap FAILED: ${e && e.message ? e.message : e}`;
          }
        }
        return {
          type: "output",
          output:
            `link.online=${link.online}` +
            (link.reason ? ` (${link.reason})` : "") +
            ` → target model: ${want}\n${action}`,
        };
      },
    });
  } catch {
    /* commands capability may be unavailable */
  }
}
