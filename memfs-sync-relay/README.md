# memfs-sync-relay

Receives Gitea push webhooks for agent memfs repos and triggers
`POST /v1/agents/{agent_id}/memory/sync-from-git` against Letta so the
server-side bare repo + Postgres block cache stay fresh after every push.

## Why this exists

`letta-code`'s Edit tool pushes local changes to the configured Gitea remote
automatically, but Letta's server-side bare repo and Postgres block cache do
**not** auto-refresh from the Gitea remote. Without this relay, REST
consumers of agent memory (slackbot, pa-routing-handler, pa-web-ui's task
review sidebar, etc.) see stale content until something explicitly POSTs
sync-from-git.

Per Ezra's guidance (2026-04-25): Letta Cloud closes this loop natively
because the server IS the canonical git remote; with Fimeg's external-git
pattern + a third-party remote (our self-hosted Gitea), the server has to be
told to pull. Webhook is the recommended pattern.

## Configuration

Environment variables:

| Var | Required | Default | Notes |
|---|---|---|---|
| `RELAY_PORT` | no | `8901` | Listen port |
| `LETTA_BASE_URL` | yes | `http://letta:8283` | Used inside docker-compose net |
| `GITEA_WEBHOOK_SECRET` | recommended | empty (allows all) | HMAC-SHA256 secret matching Gitea webhook config |
| `ALLOWED_GITEA_ORG` | no | `agents` | Only forwards events for this org |
| `ALLOWED_BRANCHES` | no | `main` | Comma-separated branch allowlist |

## Deployment

Add to `docker-compose.yml` on the `pa-internal` network. See companion
`memfs-sync-relay.compose.yml` snippet.

## Gitea webhook setup

For each agent repo at `agents/<agent_id>` (or org-level for all repos):

1. Settings → Webhooks → Add Webhook → Gitea
2. Target URL: `http://memfs-sync-relay:8901/webhook` (internal) or your
   external relay URL
3. Secret: same as `GITEA_WEBHOOK_SECRET`
4. Trigger: Push events on `main`
5. Save

For bulk setup across many agent repos, prefer an org-level webhook:
Org `agents` → Settings → Webhooks → same as above.

## Health check

```
curl http://localhost:8901/health
```

Returns `{"status":"ok","letta_base_url":"..."}`.

## Manual test

```bash
curl -X POST http://localhost:8901/webhook \
  -H "X-Gitea-Event: push" \
  -H "Content-Type: application/json" \
  -d '{
    "ref": "refs/heads/main",
    "repository": {
      "name": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",
      "owner": {"username": "agents"}
    },
    "commits": [{"id": "abc123"}]
  }'
```

(With `GITEA_WEBHOOK_SECRET` set, you'll need to compute and send
`X-Gitea-Signature: <sha256_hmac_hex>`.)
