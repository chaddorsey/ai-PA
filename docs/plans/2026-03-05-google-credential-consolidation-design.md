# Google OAuth Credential Consolidation

**Created:** 2026-03-05
**Status:** Not started — design only
**Depends on:** Item 16 (gws CLI experiment)
**Risk:** Low (OAuth re-auth is non-destructive; old tokens continue working until revoked)
**Estimated effort:** 1-2 hours

## Problem

The system has **2 GCP projects** and **4 OAuth clients** producing **5+ separate token files**, each with narrow scopes. This creates:

- **Maintenance burden:** Each token expires independently, requiring separate refresh logic
- **Credential sprawl:** 7 files in `~/.gmail-mcp/` with overlapping purposes
- **gws CLI limitation:** Currently only has Gmail scopes; can't be used for Calendar, Drive, or Admin operations
- **n8n dependency:** Calendar events were fetched through n8n MCP because the orchestrator lacked its own calendar credentials (now fixed with direct API, but credentials are still fragmented)

## Current State

### GCP Projects

| Project | Client ID Prefix | Purpose |
|---------|-----------------|---------|
| `n8n-personal-assistant-469200` | `958840789786` | Gmail, Admin Reports |
| `letta-calendar-tools` | `389544848122` | Calendar, Drive, Admin Reports |

### OAuth Clients & Token Files

| Client ID | Type | Token File(s) | Current Scopes |
|-----------|------|---------------|----------------|
| `958840789786-ftu5...` | Desktop app | `gcp-oauth.keys.json` (client config only, tokens via other files) | gmail.modify, gmail.settings.basic |
| `958840789786-2co3...` | Authorized user | `gws-bridge/credentials.json`, `gmail-watch-service/credentials/credentials.json` | gmail.modify, gmail.settings.basic |
| `389544848122-23eq...` | Desktop app | `calendar.credentials.json` | calendar |
| `389544848122-23eq...` | Desktop app | `admin-reports.credentials.json` | admin.reports.audit.readonly, drive, drive.activity.readonly |
| `389544848122-23eq...` | Desktop app | `drive-docs-token.json` | drive, documents.readonly, drive.activity.readonly |

Note: The `letta-calendar-tools` client (`389544848122`) already has **3 separate tokens** — calendar, admin-reports, and drive — each authorized with different scope sets. This happened because each tool did its own OAuth flow requesting only the scopes it needed.

### Services Using Each Token

| Token File | Services |
|------------|----------|
| `calendar.credentials.json` | Letta calendar tools, scheduling-orchestrator-api |
| `admin-reports.credentials.json` | Letta admin-reports tools |
| `drive-docs-token.json` | drive-rag-service |
| `gws-bridge/credentials.json` | gws-bridge (Gmail drafts sidebar) |
| `gmail-watch-service/credentials/credentials.json` | gmail-watch-service |

## Consolidation Strategy

### Option A: Merge into `letta-calendar-tools` client (Recommended)

The `389544848122` client already covers calendar, drive, and admin scopes across its 3 tokens. Adding Gmail scopes would create a single client that handles everything.

**Steps:**

1. **Run incremental OAuth on the `letta-calendar-tools` client** with all desired scopes:
   ```
   calendar, gmail.modify, gmail.settings.basic, drive, documents.readonly,
   drive.activity.readonly, admin.reports.audit.readonly
   ```
   Google's `include_granted_scopes=true` flag means existing grants are preserved — the user only sees a consent screen for the NEW scopes (gmail).

2. **Save the unified token** as `~/.gmail-mcp/unified-credentials.json`

3. **Generate a gws-compatible credentials.json** from the unified token:
   ```json
   {
     "client_id": "389544848122-23eq...",
     "client_secret": "GOCSPX-...",
     "refresh_token": "<from unified token>",
     "token_type": "Bearer",
     "type": "authorized_user"
   }
   ```

4. **Update service configurations** to point at the unified token:
   - `docker-compose.yml`: Update `CALENDAR_CREDENTIALS_PATH`, `GMAIL_CREDENTIALS_PATH`, etc.
   - `gws-bridge`: Mount the new gws credentials
   - `drive-rag-service`: Update `GOOGLE_TOKEN_PATH`

5. **Verify each service** still works with the unified token

6. **Deprecate old token files** (keep for 7-day soak, then delete)

### Option B: Add calendar scope to gws client

Simpler but less complete — only addresses the gws limitation.

**Steps:**

1. Run `gws auth login --scopes "gmail.modify,gmail.settings.basic,calendar"` in the container (requires browser — see "Browser Access" below)
2. Copy updated credentials to `gws-bridge/credentials.json`
3. Add calendar endpoints to `gws-bridge/server.js`
4. Other services remain unchanged

### Option C: Use Google Service Account

Replace all user OAuth with a service account that has domain-wide delegation.

**Not recommended** for this use case — service accounts can't access personal calendars/Gmail without domain admin setup, and the system operates on a personal Google Workspace account, not an organizational domain with admin control.

## Browser Access for OAuth Re-Auth

The OAuth consent flow requires a browser. Options:

1. **Run authenticate script on host Mac** — The existing `letta/calendar_tools/authenticate_calendar.py` already handles this pattern. Modify it to request all scopes at once. The token is saved to `~/.gmail-mcp/` which is mounted into Docker containers.

2. **Use gws CLI on the host** — `gws` is linux/amd64 only and can't run natively on macOS (ARM). Would need to run inside Docker with a port-forwarded callback URL, or wait for ARM support.

3. **Manual token exchange** — Use Google's OAuth Playground (https://developers.google.com/oauthplayground) to manually authorize with all scopes, get a refresh token, and construct the credentials file. More tedious but works without installing anything.

**Recommended:** Option 1 — modify `authenticate_calendar.py` to accept a `--all-scopes` flag.

## Implementation Plan

### Phase 1: Create unified auth script

Modify `letta/calendar_tools/authenticate_calendar.py` (or create `scripts/google-unified-auth.py`) to:
- Accept `--scopes all` flag
- Use the `letta-calendar-tools` OAuth client (`gcp-oauth.calendar.desktop.json`)
- Request all scopes with `include_granted_scopes=true`
- Save to `~/.gmail-mcp/unified-credentials.json`
- Also generate `~/.gmail-mcp/gws-credentials.json` in gws format

### Phase 2: Migrate services

1. Update `docker-compose.yml` environment variables to point at unified token
2. Replace `gws-bridge/credentials.json` with the gws-format export
3. Add calendar endpoints to `gws-bridge/server.js` (now possible with calendar scope)
4. Test each service: calendar tools, drive-rag, gws-bridge Gmail, gws-bridge Calendar

### Phase 3: Cleanup

1. Remove deprecated individual token files after 7-day soak
2. Update `CLAUDE.md` to document the unified credential pattern
3. Remove `N8N_MCP_URL` from orchestrator config (n8n no longer needed for calendar)

## Migration Risks

| Risk | Mitigation |
|------|------------|
| Unified token refresh breaks one service | Keep old token files as fallback; services can have fallback token path logic |
| Scope mismatch after incremental auth | Verify token scopes match expected set before deploying |
| gws CLI doesn't work with different client_id | Test gws with the new credentials before removing old ones |
| Service Account approach needed later | Unified user OAuth doesn't preclude adding a service account later |

## Related

- **Item 16 in WIP tracker:** gws CLI experiment (current consumer of Gmail-only credentials)
- **Direct Google Calendar API:** Deployed 2026-03-05, uses `calendar.credentials.json` directly. Benefits from consolidation but doesn't require it.
- **drive-rag-service:** Uses `drive-docs-token.json`. Would benefit from unified token to reduce credential count.
