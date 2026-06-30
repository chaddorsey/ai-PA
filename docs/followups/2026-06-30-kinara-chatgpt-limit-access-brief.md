# Access Brief — kinara "ChatGPT limit" exchange (for another Claude instance)

**Date:** 2026-06-30
**Purpose:** Locate the recent exchange where the user's main **kinara** instance hit a ChatGPT/OpenAI
usage limit, plus the associated context, so another Claude instance (one with live DB/API access) can
retrieve and analyze it. The authoring instance could not query the live DB (prod-read blocked) or
reach the Letta API from its shell.

## The agent
- **kinara** = `agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a` — 3rd in the MC lineage:
  `companion-original (53566e17) → companion (63353ba0) → kinara (b1574f99) → MC → MC-local`.
- Live **MC** (current head of the lineage): `agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef`.
- ⚠️ **Confirm the target.** kinara is a *predecessor* in the lineage. If the user's "main kinara
  instance" is a separately-running thing (a letta-code subprocess, a pa-web conversation, a revived
  agent), the ID above may not be it — ask the user how they invoke kinara (Telegram / pa-web /
  CLI / which model backend) before assuming. The ID above is the canonical lineage kinara.

## Where the conversation lives (most-complete → least)
1. **Live Letta messages DB — the only complete + current source.**
   - Postgres container `supabase-db`; database `postgres`; schema `letta`; table `messages`.
   - **Direct prod-DB queries require explicit user authorization** — name the DB target when asking.
   - Query sketch (adjust columns to the live schema):
     ```sql
     select id, role, created_at, left(text, 500) as snippet
     from letta.messages
     where agent_id = 'agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a'
     order by created_at desc
     limit 80;
     ```
   - The Letta **message API caps at 1000 and ignores `before`** — use the DB for full/older retrieval.
2. **Letta message API** (recent ≤1000 only):
   `GET http://localhost:8283/v1/agents/agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a/messages?limit=1000`
   (trailing slash or `-L`; no auth inside the Docker network, 401 from outside).
3. **Provider-side error (where the actual limit text usually appears, more explicit than the stored
   message):** `docker logs ai-pa-letta-1 --since 2h` and the **litellm proxy** logs/container
   (kinara's OpenAI/ChatGPT calls route through litellm; `litellm/config.yaml` in the repo). A 429 /
   quota error shows here even when the stored assistant turn looks blank.
4. **Historical archive (≤ 2026-06-09 only — will NOT contain today's turn):**
   `/Volumes/main-filestore/ai-PA-backups/conversation-archives/2026-06-09/conversation-history/mc-lineage/3-kinara-b1574f99-be7c-4772-8db2-ea2b35b18d1a/`
   → `messages.jsonl` (16 MB, full per-message export) + `transcript.md` (446 KB, readable).
   Sibling dirs: the two companion predecessors + `README.md`.
5. **Recall (qmd, plane-2 working set):** `~/.letta/history-archive/raw/mc/` is qmd-searchable.

## The "ChatGPT limit" signal — what to search for
The exchange is recent (~2026-06-30). Search DB rows / logs / the JSONL case-insensitively for:
- HTTP **429**, `rate_limit_exceeded`, "Rate limit reached"
- `insufficient_quota`, "exceeded your current quota", "usage limit", "usage cap"
- ChatGPT-oauth phrasing: "You've reached your usage limit", "try again later", "Plus limit"
- Letta-side: a message row with a non-null `error`, an empty/failed assistant turn, or a
  `stop_reason` indicating a provider error.
- Quick greps once you have the JSONL/transcript:
  `grep -iE "rate.?limit|quota|usage limit|usage cap|429|reached.*limit|try again later"`

## Associated context worth carrying
- kinara runs on a **ChatGPT/OpenAI-backed model**; the limit is OpenAI's, surfaced via **litellm**.
- **Silent-stall #99** (see memory `feedback_letta_silent_stall_global`): chatgpt_oauth (and others)
  can *freeze* a conversation rather than error cleanly — a provider limit may present as a stall,
  not an obvious error message. Keep `letta-bg-fix-sidecar` on `LETTA_SUBPROCESS_BASE_URL`.
- **cross_provider_compat** litellm hook scrubs reasoning fields on provider swaps — relevant if the
  fix is to fail kinara over to another provider when the ChatGPT limit hits.
- If kinara and live MC share a provider/key, a limit on one can implicate the other.

## What the user actually wants (the broader goal)
They want to **identify these provider-limit signals in conversations** generally — i.e. a detector.
The patterns above are the seed for that. A durable approach: watch litellm/Letta logs (or a message
post-hook) for the 429/quota signatures and the silent-stall shape, and surface/alert on them.
