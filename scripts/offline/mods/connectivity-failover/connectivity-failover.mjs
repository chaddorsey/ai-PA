/**
 * connectivity-failover — Spike B proof mod (laptop spoke #1)
 *
 * Reads the conn-probe link state (~/.letta/offline-bus/link.json) and surfaces it
 * in the Letta Code statusline, refreshing on every `tick` event. Registers a
 * `/connectivity` command that reports the current link state and the model the
 * failover spine *intends* to run.
 *
 * Verified mod API (from the bundled letta-code source, see spike-findings §B):
 *   - mod export: `export default function activate(letta)` (or `export function activate`)
 *   - events:    letta.events.on('tick', fn)            // periodic refresh hook
 *   - statusline: letta.ui.setStatus(key, text)          // string value
 *   - commands:  letta.commands.register({ id, ... })
 *
 * KNOWN GAP (do NOT treat the model swap below as proven): a *mod-facing* model-swap
 * trigger was not found in the bundle. Model changes go through an `update_model`
 * WsProtocol command (protocol_v2.d.ts: UpdateModelCommand), applied at the app/runtime
 * layer — not via a `letta.setModel(...)` mod method. The auto-swap therefore needs the
 * in-harness `creating-mods` reference (or an in-session test) to confirm. This mod proves
 * the observability half (event + file-read + statusline + command); the swap is stubbed.
 */
import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const LINK_JSON = join(homedir(), ".letta", "offline-bus", "link.json");
const STATUS_KEY = "connectivity";

function readLink() {
  try {
    if (!existsSync(LINK_JSON)) return { online: null, reason: "no link.json" };
    return JSON.parse(readFileSync(LINK_JSON, "utf8"));
  } catch (e) {
    return { online: null, reason: String(e && e.message ? e.message : e) };
  }
}

function statusText(link) {
  if (link.online === false) return "🔴 offline · local";
  if (link.online === true) return "🟢 online · cloud";
  return "⚪ link?";
}

function targetModel(link) {
  return link.online === false ? "local (GLM-4.5-Air via oMLX)" : "cloud";
}

export default function activate(letta) {
  const refresh = () => {
    try {
      letta?.ui?.setStatus?.(STATUS_KEY, statusText(readLink()));
    } catch {
      /* statusline capability may be unavailable; ignore */
    }
  };

  // Initial paint + refresh on every tick.
  refresh();
  try {
    letta?.events?.on?.("tick", refresh);
  } catch {
    /* events capability may be unavailable; ignore */
  }

  // Manual inspection command.
  try {
    letta?.commands?.register?.({
      id: "connectivity",
      description: "Show conn-probe link state and the failover target model",
      async run() {
        const link = readLink();
        return (
          `link.online=${link.online}` +
          (link.reason ? ` (${link.reason})` : "") +
          ` → target model: ${targetModel(link)}\n` +
          `NOTE: model auto-swap is stubbed pending a verified update_model trigger (spike-findings §B).`
        );
      },
    });
  } catch {
    /* commands capability may be unavailable; ignore */
  }
}
