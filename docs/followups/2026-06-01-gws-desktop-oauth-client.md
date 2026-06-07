---
date: 2026-06-01
resolved: 2026-06-07
status: RESOLVED
component: gws CLI
trigger_to_act: refresh token expiry, manual revocation, or anything that
  requires a fresh `gws auth login` — see "Recurring maintenance" below
---

# gws — replace Web-app OAuth client with Desktop-app type

> **RESOLVED 2026-06-07.** The Desktop-client swap + `gws auth login` was
> completed on the host, and the Dockerized gws credential was
> regenerated to match. Calendar/Drive/Gmail now work both on the host
> (`letta-mc` local MC) and across all dependent containers. The
> original problem statement and root-cause analysis are preserved below
> for history; see **Resolution** and **Recurring maintenance** for the
> live state.

## Resolution (2026-06-07)

### Host

1. A new **Desktop-app** OAuth client was created in GCP project
   `n8n-personal-assistant-469200` (client_id ends `...a7j`).
2. `~/.config/gws/client_secret.json` was replaced with the Desktop
   client (old Web-app client backed up to
   `client_secret.json.web-app-backup`).
3. `gws auth login` was run and **granted full scope** — not just Gmail.
   `gws auth status` now reports `auth_method: oauth2`,
   `user_email: cdorsey@concord.org`, 12 scopes incl. calendar, drive,
   gmail.modify, documents, presentations, spreadsheets.
4. Verified: `gws calendar +agenda`, `gws drive files list`, and
   `gws gmail +triage` all succeed on the host.

### Containers (the non-obvious second half)

The host fix does **not** propagate into Docker. Every Dockerized gws
consumer reads a **single bind-mounted file**,
`gws-bridge/credentials.json` → `/root/.gws/credentials.json`, via the
env var `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`. That file was the old
broken credential (wrong format — Python `google-auth` `to_json()`,
missing `type: authorized_user` — and Gmail-only scopes).

Fix: regenerate it from the now-working host credential:

```bash
cd gws-bridge
cp -p credentials.json "credentials.json.bak.$(date +%s)"   # backup
gws auth export --unmasked > credentials.json               # host -> file
chmod 600 credentials.json
```

`gws auth export` emits the correct `authorized_user` format
(`type`, `client_id`, `client_secret`, `refresh_token`) and the
refresh_token carries all host-granted scopes. Containers read the
bind-mount live, so **no rebuild/restart is needed**.

### Containers that depend on this credential

| Service | Capability | Depended on by | Verified 2026-06-07 |
|---|---|---|---|
| `scheduling-orchestrator-api` | `gws calendar` (`google_calendar_client.py`) — slot eval, propose/validate meeting times | **slackbot** (`direct_scheduler.py`, `agent_bridge.py`, `proposal_formatter.py`) | ✅ |
| `gws-bridge` | `gws` Gmail drafts/messages/send + Drive replies (HTTP shim) | **pa-web-ui** email/draft flows | ✅ (CLI + `/health`) |
| `ai-pa-letta-1` | `gws calendar` etc. for Docker MC's `run_gws` | **pa-web-ui** Docker-MC subprocess path | ✅ |
| `scheduler-service` | — | — (has the mount/env but **no gws code**; vestigial) | n/a |

## Recurring maintenance (this WILL recur)

The host refresh token persists indefinitely under normal conditions
but is invalidated by: Google revocation (security event, scope change,
~6 months non-use), token rotation, keychain corruption, or
`gws auth logout`. When that happens:

1. Re-run `gws auth login` on the host (now works — Desktop client
   accepts any loopback port).
2. **Re-sync the container credential** with the `gws auth export`
   step above — otherwise the host recovers but Slack scheduling,
   pa-web-ui email drafts, and the Docker-MC web path stay broken.

> The host and the containers do NOT share a credential store. Step 2
> is the easy one to forget; it's why MC kept "complaining about
> calendar auth" on 2026-06-07 even after the host had been fixed.

## Security note

`gws-bridge/credentials.json` holds a plaintext refresh token (by gws
design when using the file backend). It is git-ignored. The timestamped
backups (`credentials.json.bak.*`) also hold refresh tokens — a
gitignore rule `**/credentials.json.bak.*` was added 2026-06-07 so they
can't be accidentally committed. Prune old backups periodically.

---

## Original problem statement (historical — pre-fix)

`gws auth login` failed with HTTP 400 `redirect_uri_mismatch`. gws
constructs the OAuth flow with a random ephemeral loopback port each run
(e.g. `http://localhost:57273`), and the OAuth client in Google Cloud
Console was **Web application** type — which requires every exact URI to
be pre-registered. The random port was never registered, so Google
rejected it.

**Note on a stale assumption:** an earlier version of this doc claimed
day-to-day ops were unaffected because gws held a valid refresh token in
the macOS keychain and only the interactive `auth login` was broken.
That turned out to be **wrong** by 2026-06-07 — `gws auth status`
reported `auth_method: none`, and both the keychain/token-cache path and
the env-var path (`gws-bridge/credentials.json`, which is Gmail-only and
the wrong format) failed. Every gws pathway was dead until the
resolution above. The "phantom file" claim was also wrong — the file
existed; it was just unusable by gws.

## Root cause detail (historical)

Old OAuth client (in `~/.config/gws/client_secret.json`):
- client_id: `958840789786-...` (Web application type)
- registered redirect URIs: `http://localhost:{3000,3001,8765,9876}/`,
  `http://localhost:3000/oauth2callback`, `http://127.0.0.1:3000/oauth2callback`

gws (v0.22.5) picked a fresh ephemeral port on every `auth login` and
constructed `redirect_uri=http://localhost:<ephemeral>`. Setting
`GOOGLE_WORKSPACE_CLI_OAUTH_PORT=8765` was ignored. Google's OAuth 2.0
for installed apps doc says **Desktop / Installed app** clients accept
any loopback port automatically; Web app clients do not. Hence the
Desktop-client swap in the resolution.

## What the old client should become

The old Web-app client (`958840789786-...`) may still be used by n8n or
other services on the same GCP project. **Do not delete it** without a
grep across the repo first. The new Desktop client lives alongside it.
