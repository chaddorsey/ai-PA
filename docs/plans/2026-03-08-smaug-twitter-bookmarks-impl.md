# Smaug Twitter Bookmarks Archival Service — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Install and configure Smaug to archive Twitter/X bookmarks to markdown, run a backfill, and set up ongoing capture via launchd.

**Architecture:** bird CLI (Twitter GraphQL wrapper) fetches bookmarks, Smaug processes them with Claude Code for AI categorization, outputs structured markdown to `/Volumes/main-drive/ai-PA/smaug-data/`. launchd runs every 6 hours.

**Tech Stack:** Node.js (Smaug), pnpm (bird CLI build), Claude Code (AI categorization), launchd (scheduling)

**Design doc:** [2026-03-08-smaug-twitter-bookmarks-design.md](2026-03-08-smaug-twitter-bookmarks-design.md)

---

### Task 1: Install bird CLI from git

bird CLI must be built from source (not npm) to get pagination support for fetching all bookmarks.

**Step 1: Clone and build bird CLI**

```bash
cd /tmp
git clone https://github.com/steipete/bird.git
cd bird
pnpm install
pnpm run build:dist
```

**Step 2: Link globally**

```bash
npm link --force
```

**Step 3: Verify installation**

```bash
bird --version
bird bookmarks --help
```

Expected: Version prints, bookmarks help shows `--all` flag.

**Step 4: Commit nothing** — bird CLI is a global tool, not part of the repo.

---

### Task 2: Clone and install Smaug

**Step 1: Clone Smaug**

```bash
cd /Volumes/main-drive/ai-PA
git clone https://github.com/alexknowshtml/smaug.git smaug
cd smaug
npm install
```

**Step 2: Create data directory**

```bash
mkdir -p /Volumes/main-drive/ai-PA/smaug-data/knowledge/tools
mkdir -p /Volumes/main-drive/ai-PA/smaug-data/knowledge/articles
mkdir -p /Volumes/main-drive/ai-PA/smaug-data/.state
```

**Step 3: Run setup wizard**

```bash
npx smaug setup
```

Follow the wizard prompts. When asked for Twitter credentials, you'll need `auth_token` and `ct0` from your browser (Task 3).

**Step 4: Verify Smaug is installed**

```bash
npx smaug --help
```

Expected: Shows available commands (fetch, process, run, setup).

---

### Task 3: Configure Twitter credentials and output paths

**Step 1: Get Twitter cookies**

1. Open https://x.com in your browser
2. Open Developer Tools (F12 / Cmd+Option+I)
3. Go to Application → Cookies → https://x.com
4. Find and copy: `auth_token` and `ct0`

**Step 2: Edit config file**

Edit `smaug/smaug.config.json` (created by setup wizard, or copy from example):

```bash
cp smaug.config.example.json smaug.config.json
```

Set these fields:

```json
{
  "source": "bookmarks",
  "archiveFile": "/Volumes/main-drive/ai-PA/smaug-data/bookmarks.md",
  "pendingFile": "/Volumes/main-drive/ai-PA/smaug-data/.state/pending-bookmarks.json",
  "stateFile": "/Volumes/main-drive/ai-PA/smaug-data/.state/bookmarks-state.json",
  "timezone": "America/New_York",
  "twitter": {
    "authToken": "<your auth_token>",
    "ct0": "<your ct0>"
  },
  "autoInvokeClaude": true,
  "claudeModel": "haiku",
  "claudeTimeout": 900000
}
```

Notes:
- `claudeModel: "haiku"` — half the cost of sonnet, same speed, good enough for categorization
- All output paths point to `smaug-data/` (outside the smaug repo clone)
- The `knowledge/` output directory also needs to be configured or symlinked — check if Smaug uses a config key for this or defaults to `./knowledge/`. If it defaults, create a symlink:

```bash
cd /Volumes/main-drive/ai-PA/smaug
ln -s /Volumes/main-drive/ai-PA/smaug-data/knowledge knowledge
```

**Step 3: Verify credentials work**

```bash
cd /Volumes/main-drive/ai-PA/smaug
npx smaug fetch 5
```

Expected: Fetches 5 bookmarks without 403 errors. Check `.state/pending-bookmarks.json` for fetched data.

**Step 4: Verify processing works**

```bash
npx smaug process --limit 2 -t
```

Expected: Processes 2 bookmarks, shows token usage, creates entries in bookmarks.md and/or knowledge files.

---

### Task 4: Run backfill

**Step 1: Fetch all bookmarks**

```bash
cd /Volumes/main-drive/ai-PA/smaug
npx smaug fetch --all --max-pages 50
```

This may take a few minutes depending on bookmark count. Check progress:

```bash
node -e "const d=require('/Volumes/main-drive/ai-PA/smaug-data/.state/pending-bookmarks.json'); console.log('Pending:', d.count || Object.keys(d).length)"
```

**Step 2: Process in batches**

```bash
npx smaug run --limit 50 -t
```

Review the token cost. If acceptable, continue processing:

```bash
npx smaug run --limit 50 -t   # repeat until "No new bookmarks to process"
```

**Step 3: Verify output**

```bash
wc -l /Volumes/main-drive/ai-PA/smaug-data/bookmarks.md
ls /Volumes/main-drive/ai-PA/smaug-data/knowledge/tools/ | head -10
ls /Volumes/main-drive/ai-PA/smaug-data/knowledge/articles/ | head -10
```

Expected: bookmarks.md has content, knowledge dirs have markdown files.

---

### Task 5: Create launchd service

**Step 1: Create the plist**

Create `~/Library/LaunchAgents/com.ai-pa.smaug.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai-pa.smaug</string>
    <key>WorkingDirectory</key>
    <string>/Volumes/main-drive/ai-PA/smaug</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/npx</string>
        <string>smaug</string>
        <string>run</string>
    </array>
    <key>StartInterval</key>
    <integer>21600</integer>
    <key>StandardOutPath</key>
    <string>/Volumes/main-drive/ai-PA/smaug-data/smaug.log</string>
    <key>StandardErrorPath</key>
    <string>/Volumes/main-drive/ai-PA/smaug-data/smaug-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
```

Note: Verify the path to `npx` with `which npx` — it may be `/opt/homebrew/bin/npx` on Apple Silicon.

**Step 2: Load the service**

```bash
launchctl load ~/Library/LaunchAgents/com.ai-pa.smaug.plist
```

**Step 3: Verify it's loaded**

```bash
launchctl list | grep smaug
```

Expected: Shows `com.ai-pa.smaug` in the list.

**Step 4: Test a manual trigger**

```bash
launchctl start com.ai-pa.smaug
```

Wait a moment, then check logs:

```bash
tail -20 /Volumes/main-drive/ai-PA/smaug-data/smaug.log
tail -20 /Volumes/main-drive/ai-PA/smaug-data/smaug-error.log
```

Expected: Log shows successful run (or "No new bookmarks to process" if backfill is complete).

---

### Task 6: Add to backup

**Step 1: Add smaug-data to backup script**

Edit `deployment/scripts/backup.sh` and add `smaug-data/` to the host data backup paths, alongside existing entries like `analytics/` and `letta/`.

Look for the section that backs up host data directories and add:

```bash
/Volumes/main-drive/ai-PA/smaug-data
```

**Step 2: Verify with dry run**

```bash
./deployment/scripts/backup.sh --dry-run 2>&1 | grep smaug
```

Expected: Shows smaug-data in the backup plan.

**Step 3: Commit**

```bash
git add deployment/scripts/backup.sh
git commit -m "chore: add smaug-data to nightly backup paths"
```

---

### Task 7: Add to WIP tracker and gitignore

**Step 1: Add smaug to .gitignore**

The cloned smaug repo and smaug-data directory should not be tracked in the main repo:

```
# Smaug (Twitter bookmarks archival)
smaug/
smaug-data/
```

**Step 2: Add entry to WIP tracker**

Add a new item to `docs/plans/2026-02-23-wip-system-updates.md` for Smaug:

```markdown
## 23. Smaug — Twitter/X Bookmarks Archival (ACTIVE)

**Status:** Deployed, running every 6 hours via launchd
**Design:** [2026-03-08-smaug-twitter-bookmarks-design.md](2026-03-08-smaug-twitter-bookmarks-design.md)
**Upstream:** [github.com/alexknowshtml/smaug](https://github.com/alexknowshtml/smaug)
**Risk:** Low (standalone host tool, no internal service dependencies)

**What:** Archives Twitter/X bookmarks to structured markdown with AI categorization (Claude Code). bird CLI fetches via Twitter's GraphQL API using browser cookies. Output: `bookmarks.md` master archive + `knowledge/tools/` and `knowledge/articles/` with YAML frontmatter.

**Components:**
- bird CLI (from git, global install) — Twitter GraphQL wrapper with pagination
- Smaug (Node.js) — `/Volumes/main-drive/ai-PA/smaug/`
- Output — `/Volumes/main-drive/ai-PA/smaug-data/`
- launchd — `com.ai-pa.smaug`, every 6 hours

**Future enrichment:** Fetch likers list per bookmarked tweet via Twitter Favoriters GraphQL endpoint, cross-reference with Curator Radar (Item 22) GitHub stargazer data for multi-platform curator discovery.
```

**Step 3: Commit**

```bash
git add .gitignore docs/plans/2026-02-23-wip-system-updates.md
git commit -m "docs: add Smaug to WIP tracker and gitignore"
```
