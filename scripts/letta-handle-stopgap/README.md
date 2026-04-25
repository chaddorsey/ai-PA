# Letta handle stopgap (Path A)

**Status**: Drafted, NOT executed. Path A interim — apply only if Task needs to work BEFORE the Path C letta-code patch ships.

## What this does

Inserts mirror rows into Letta's `provider_models` table so handles like `litellm/gpt-4.1-mini`, `litellm/kimi-k2p6`, etc. resolve at server-side validation time. Each mirror row:
- Has `handle = "litellm/X"` matching an existing `openai-proxy/X` row
- Points to the same `provider_id` (the `openai-proxy` BYOK provider, whose `base_url` is `http://litellm:4000/v1`)
- Has identical `name`, `model_endpoint_type`, `max_context_window`, `supports_*` fields

Result: `POST /v1/agents/` with `model: "litellm/X"` resolves successfully, and subagent inheritance works with our existing agent llm_configs.

## When to apply

Only if Path C (letta-code patch) is delayed AND Task needs to work in production immediately.

If you're just running tests or aren't blocked, prefer Path C — the SQL stopgap has a re-application footnote whenever provider refresh is triggered.

## Risks

1. **Re-sync deletes rows that LiteLLM doesn't return.** `litellm/X` handles are NOT in LiteLLM's `/v1/models` response (LiteLLM returns bare model names like `kimi-k2p6`). Letta's BYOK refresh prefixes with provider name to produce `openai-proxy/X`, not `litellm/X`. So our manual `litellm/X` rows would be soft-deleted on the next refresh.
2. **Mitigation**: don't run `PATCH /v1/providers/<id>/refresh` while these rows are needed. If you must refresh, re-run `apply.sql` afterward.
3. **Detection**: if Task suddenly stops working with `HandleNotFoundError` after some time, suspect a refresh happened. Check `is_deleted=true` on the litellm rows.

## Files

- `apply.sql` — INSERT mirror rows
- `rollback.sql` — DELETE the mirror rows we created (matches by a tag in name field)
- `verify.sql` — Show counts + sample resolved handles

## Usage

```bash
# Apply
docker exec -i supabase-db psql -h 127.0.0.1 -U letta -d letta < apply.sql

# Verify
docker exec -i supabase-db psql -h 127.0.0.1 -U letta -d letta < verify.sql

# Rollback (only removes rows this script added)
docker exec -i supabase-db psql -h 127.0.0.1 -U letta -d letta < rollback.sql
```

## Why we chose Path C over Path A as the primary fix

- Path A is a band-aid; Path C fixes the structural issue at the right layer
- Path A is operationally fragile (re-application after refresh)
- Path C is upstream-friendly (becomes a reference patch in the GitHub issue the Letta team is filing)
- Path C is reversible by switching `LETTA_CODE_BIN` env var; Path A requires SQL rollback
