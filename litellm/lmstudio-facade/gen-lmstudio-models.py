#!/usr/bin/env python3
"""Generate an LM Studio native /api/v0/models response from the litellm config.

letta-code's model discovery reads context windows from `{host}/api/v0/models`
(LM Studio native format). litellm only serves `/v1/models` (no context length),
so letta-code falls back to a 128k default for every proxy model — which makes
large-conversation reasoning turns die with `max_tokens_exceeded`. The Caddy
facade (:4001) serves this generated file at /api/v0/models and reverse-proxies
everything else to litellm (:4000), so discovery sees real windows.

Run this whenever litellm/config.yaml or model-context-windows.json changes:
    python3 litellm/lmstudio-facade/gen-lmstudio-models.py

See docs/followups/2026-08-10-letta-code-byok-context-window-128k-default.md
"""
import json
import os
import re
import sys

REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
CONFIG = os.environ.get("LITELLM_CONFIG", f"{REPO}/litellm/config.yaml")
MAP = os.environ.get("MC_CONTEXT_MAP", f"{REPO}/litellm/model-context-windows.json")
OUT = os.environ.get("LMSTUDIO_MODELS_OUT", f"{REPO}/litellm/lmstudio-facade/lmstudio-models.json")

MODEL_NAME_RE = re.compile(r'^\s*-?\s*model_name:\s*["\']?([^"\'\s]+)')
EMBEDDING_HINTS = ("embedding", "rerank")


def model_names_from_config(path):
    names = []
    with open(path) as f:
        for line in f:
            m = MODEL_NAME_RE.match(line)
            if m:
                names.append(m.group(1))
    # de-dup, preserve order
    seen = set()
    return [n for n in names if not (n in seen or seen.add(n))]


def main():
    ctx = json.load(open(MAP))
    default_ctx = int(ctx.get("default", 131072))
    ctx_models = ctx.get("models", {})

    data = []
    for name in model_names_from_config(CONFIG):
        bare = name.split("/")[-1]
        is_embed = any(h in bare.lower() for h in EMBEDDING_HINTS)
        window = int(ctx_models.get(bare, ctx_models.get(name, default_ctx)))
        entry = {
            "id": name,
            "object": "model",
            "type": "embeddings" if is_embed else "llm",
            "publisher": "litellm-proxy",
            "arch": "proxy",
            "state": "loaded",
            "max_context_length": window,
            "capabilities": [] if is_embed else ["tool_use"],
        }
        if not is_embed:
            entry["loaded_context_length"] = window
        data.append(entry)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"object": "list", "data": data}, f, indent=2)
    os.replace(tmp, OUT)
    print(f"wrote {len(data)} models -> {OUT}")
    # quick visibility on the ones that matter
    for name in ("deepseek-v4-pro", "deepseek-v4-flash", "kimi-k2p6", "glm-5p2"):
        hit = next((e for e in data if e["id"] == name), None)
        if hit:
            print(f"  {name}: max_context_length={hit['max_context_length']}")


if __name__ == "__main__":
    sys.exit(main())
