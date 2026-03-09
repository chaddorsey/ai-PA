# Smaug — Twitter/X Bookmarks Archival Service

**Date:** 2026-03-08
**Status:** Design approved
**Upstream:** [Smaug](https://github.com/alexknowshtml/smaug) by alexknowshtml

## Overview

Install Smaug on the macOS host to archive Twitter/X bookmarks to structured markdown files with AI-powered categorization. Run a one-time backfill of all existing bookmarks, then schedule ongoing capture every 6 hours via launchd.

## Architecture

```
Twitter/X GraphQL API (via bird CLI)
    ↓ browser cookies (auth_token + ct0)
bird CLI (host-installed from git, for pagination)
    ↓
Smaug (Node.js, host-installed)
    ↓ Claude Code for categorization
/Volumes/main-drive/ai-PA/smaug-data/
    ├── bookmarks.md              # master archive by date
    ├── knowledge/tools/          # GitHub repos (YAML frontmatter + content)
    ├── knowledge/articles/       # articles (YAML frontmatter + content)
    └── .state/                   # dedup state, pending queue
```

No Docker. No internal network. Pure host-level tool writing files to a dedicated volume.

## Components

1. **bird CLI** — installed from git (npm release lacks pagination). [github.com/steipete/bird](https://github.com/steipete/bird)
2. **Smaug** — cloned to `/Volumes/main-drive/ai-PA/smaug`, npm installed
3. **Config** — `smaug.config.json` with Twitter cookies, `archiveFile` and state paths pointing to `smaug-data/`
4. **launchd** — `com.ai-pa.smaug` plist, runs `npx smaug run` every 6 hours
5. **Backup** — `smaug-data/` added to nightly backup script

## Backfill

```bash
npx smaug fetch --all --max-pages 50   # grab all existing bookmarks
npx smaug run --limit 50 -t            # process in batches, track cost
```

Repeat `run --limit 50 -t` until backlog is cleared. Monitor cost per batch.

## Ongoing Service

launchd plist (`com.ai-pa.smaug`) runs every 6 hours:

```xml
<key>StartInterval</key>
<integer>21600</integer>
```

Smaug's `.state/` directory handles deduplication — only new bookmarks get processed each run.

## Authentication

Twitter cookies (`auth_token` + `ct0`) obtained from browser Developer Tools → Application → Cookies. Stored in `smaug.config.json` (gitignored).

Cookies expire periodically (bird CLI returns 403). Fix: grab fresh cookies from browser, update config file. Next launchd run picks them up automatically.

## Output Format

### bookmarks.md (master archive)

Organized by date with entries containing tweet text, expanded URLs, links to knowledge files, and AI-generated summaries.

### knowledge/tools/*.md (GitHub repos)

YAML frontmatter with title, type, date, source URL, tags, via attribution. Body contains repo description, key features, links.

### knowledge/articles/*.md (articles)

YAML frontmatter with title, type, date, source URL, tags, via attribution. Body contains extracted article content.

## Backup Integration

Add `smaug-data/` to `deployment/scripts/backup.sh` host data paths. Markdown files + state are small — negligible backup size increase.

## Future: Curator Cross-Reference Enrichment

For each bookmarked tweet, the Twitter GraphQL API exposes a `Favoriters` endpoint (list of users who liked the tweet). A future enrichment phase could:

1. For each archived bookmark, fetch the likers list via the Favoriters GraphQL endpoint
2. Store user → tweet-liked mappings
3. Cross-reference with Curator Radar's GitHub stargazer data (Item 22 in WIP tracker)
4. Users who appear in both "liked tweets I bookmark" AND "star repos I star" are high-signal curators across platforms

This requires extending bird CLI or calling the GraphQL endpoint directly — separate from Smaug itself. Natural integration point with Curator Radar.

## Out of Scope

- **Docker containerization** — no benefit; pure HTTP + file writes
- **Drive-rag ingestion** — deferred; evaluating RAG usefulness separately
- **Media extraction** — experimental in Smaug, skip for now
- **Custom categories** — use Smaug defaults, tune later if needed
- **Likes archival** — Smaug supports `--source likes`, but starting with bookmarks only
