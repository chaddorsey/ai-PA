---
date: 2026-06-01
status: deferred (no urgency)
component: gws CLI
trigger_to_act: refresh token expiry, manual revocation, or anything that requires a fresh `gws auth login`
---

# gws — replace Web-app OAuth client with Desktop-app type

## Problem

`gws auth login` fails with HTTP 400 `redirect_uri_mismatch`. gws constructs
the OAuth flow with a random ephemeral loopback port each run (e.g.
`http://localhost:57273`), and the current OAuth client in Google Cloud
Console is **Web application** type — which requires every exact URI to
be pre-registered. The random port is never in the registered list, so
Google rejects.

## Why it's not blocking

The CLI's day-to-day operations are unaffected:

- `gws drive files list`, `gmail messages get`, etc. all succeed
- gws holds a valid `refresh_token` in the macOS keychain
- Each call refreshes a short-lived access token via the refresh path
- The refresh path does NOT go through `auth login`'s redirect flow

What's broken is *only* the interactive re-authentication flow. The
decrypt-token-cache warning that prompted this investigation is
cosmetic — MC's `mc_cli_recipes.md` now treats it as non-fatal (see
commit `90cab96` in the MC memfs repo).

## Why it WILL eventually block

The refresh token persists indefinitely under normal conditions, but
will be invalidated by any of:

- Google revoking it (manual revocation in My Account, security event,
  scope changes, ~6 months of non-use)
- Token rotation by Google's OAuth infrastructure (rare)
- macOS keychain corruption that loses the refresh token
- User explicitly running `gws auth logout`

When that happens, `gws auth login` must work — and currently it can't.

## Root cause detail

Current OAuth client (in `~/.config/gws/client_secret.json`):
- client_id: `958840789786-...`
- project: `n8n-personal-assistant-469200`
- type: **Web application** (inferred from the registered URI shape)
- registered redirect URIs: `http://localhost:{3000,3001,8765,9876}/`,
  `http://localhost:3000/oauth2callback`, `http://127.0.0.1:3000/oauth2callback`

gws (v0.22.5) picks a fresh ephemeral port on every `auth login` and
constructs `redirect_uri=http://localhost:<ephemeral>`. Tested
`GOOGLE_WORKSPACE_CLI_OAUTH_PORT=8765` — gws ignored it and still
picked `57320`. No documented way to pin the port.

Google's OAuth 2.0 for installed apps doc says **Desktop / Installed
app** clients accept any loopback port automatically. Web app clients
do not.

## Fix (when needed)

1. **Google Cloud Console** → project `n8n-personal-assistant-469200`
2. **APIs & Services → Credentials**
3. **Create Credentials → OAuth client ID**
4. **Application type: Desktop app** (NOT Web application)
5. Name it something like `gws-cli-desktop`
6. Download the resulting JSON
7. On the Mac:
   ```bash
   # Back up current
   cp ~/.config/gws/client_secret.json ~/.config/gws/client_secret.json.web-app-backup
   # Replace with downloaded Desktop-type JSON
   mv ~/Downloads/client_secret_<new-id>.apps.googleusercontent.com.json \
      ~/.config/gws/client_secret.json
   # Re-auth
   gws auth logout
   gws auth login
   ```

The Desktop client doesn't require port-specific URI registration —
Google accepts any `http://localhost:*` redirect for that client type.

## Validation after fix

- `gws auth status` shows non-null `user_email` and `client_id`
- `gws auth status` shows the new client_id (different from `958840789786-...`)
- A `gws drive files list --params '{"pageSize":1}'` call returns
  cleanly with NO `failed to decrypt token cache` warning
- MC's `mc_cli_recipes.md` recipe for "non-fatal warnings" still
  catches the original warning if it ever recurs; no edit needed

## What the old client should become

The old Web-app client (`958840789786-...`) is presumably still in use
by n8n or other services on the same GCP project. **Do not delete it.**
Just create the new Desktop-app client alongside it.

If it turns out nothing else uses the Web-app client (worth a grep
across the repo before deleting), it can be retired in a follow-up
cleanup pass.

## Related

- `~/.zshrc`: `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` env var pointing
  at the phantom `/Volumes/main-drive/ai-PA/gws-bridge/credentials.json`
  was commented out 2026-06-01 (separate fix; cleared up a confusion
  but didn't fix the redirect_uri_mismatch)
- gws-bridge container uses keychain backend for its own auth, not the
  phantom credentials file. Its docker-compose mount of that file is
  vestigial but harmless.
- MC's `mc_cli_recipes.md` "Distinguishing warnings from real failures"
  section already handles the decrypt warning as non-fatal — so the
  decrypt warning surface is solved at the agent layer even without
  this fix landing.
