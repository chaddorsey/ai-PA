/**
 * connectivity-failover — laptop spoke #1 (Option C: LiteLLM proxy failover)
 *
 * OBSERVABILITY-ONLY. The mini-me always points at the local LiteLLM proxy
 * (model "mc-brain"); the proxy transparently fails over primary=server-LiteLLM
 * (cloud, over the tailnet) -> fallback=local GLM (oMLX). There is NO model swap to
 * perform here — so this mod only *surfaces* link state and records it for other
 * components (routing reads `mode.json`).
 *
 * Resolved Step 0 (see spike-findings §B): a mod can't issue the live `update_model`
 * WS command, and a config swap doesn't re-model a running conversation — but with the
 * proxy the agent's handle never changes, so no swap is needed. The watcher/app-server
 * path was dropped per the Option C decision.
 *
 * Behavior:
 *   - on `tick`: read conn-probe `~/.letta/offline-bus/link.json`, set the statusline,
 *     and write `~/.letta/offline-bus/mode.json` ({link, brain, at}) for action-routing.
 *   - `/connectivity`: report link state + which brain the proxy will serve.
 *
 * Verified mod API: `export default function activate(letta)`;
 *   letta.events.on('tick', fn); letta.ui.setStatus(key, text);
 *   letta.commands.register({ id, description, run(ctx) -> {type:'output'|'prompt'|'handled'} }).
 */
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const BUS = join(homedir(), ".letta", "offline-bus");
const LINK_JSON = join(BUS, "link.json");
const MODE_JSON = join(BUS, "mode.json");
const STATUS_KEY = "connectivity";

function readLink() {
  try {
    if (!existsSync(LINK_JSON)) return { online: null, reason: "no link.json" };
    return JSON.parse(readFileSync(LINK_JSON, "utf8"));
  } catch (e) {
    return { online: null, reason: String(e && e.message ? e.message : e) };
  }
}

const linkOf = (l) => (l.online === false ? "offline" : l.online === true ? "online" : "unknown");
const brainOf = (l) =>
  l.online === false ? "local GLM (proxy fallback)" : l.online === true ? "cloud (proxy primary)" : "unknown";
const statusText = (l) =>
  l.online === false ? "🔴 offline · local" : l.online === true ? "🟢 online · cloud" : "⚪ link?";

function publish(link) {
  // mode.json is the contract the action-routing (routing.py) reads.
  try {
    const mode = { link: linkOf(link), brain: brainOf(link), online: link.online };
    writeFileSync(MODE_JSON, JSON.stringify(mode, null, 2));
  } catch {
    /* bus dir may be unavailable; ignore */
  }
}

export default function activate(letta) {
  const refresh = () => {
    const link = readLink();
    try {
      letta?.ui?.setStatus?.(STATUS_KEY, statusText(link));
    } catch {
      /* statusline capability unavailable */
    }
    publish(link);
  };

  refresh();
  try {
    letta?.events?.on?.("tick", refresh);
  } catch {
    /* events capability unavailable */
  }

  try {
    letta?.commands?.register?.({
      id: "connectivity",
      description: "Show conn-probe link state and which brain the proxy will serve",
      async run() {
        const link = readLink();
        return {
          type: "output",
          output:
            `link=${linkOf(link)}` +
            (link.reason ? ` (${link.reason})` : "") +
            ` → brain: ${brainOf(link)}\n` +
            `(Option C: the mini-me points at the LiteLLM proxy; failover is the proxy's job — no model swap.)`,
        };
      },
    });
  } catch {
    /* commands capability unavailable */
  }
}
