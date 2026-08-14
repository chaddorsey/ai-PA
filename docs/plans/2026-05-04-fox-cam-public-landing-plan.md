---
title: Our Foxes — public landing page + login + admin role
date: 2026-05-04
status: planned (not started)
related:
  - fox-cam-public/app/main.py (CF Access middleware)
  - frigate-curator/frigate_curator/main.py (highlights API)
  - frigate-curator/frigate_curator/db.py
  - docs/plans/2026-05-03-fox-cam-pwa-plan.md
---

# Our Foxes — public landing + login + admin role

## Goals

1. **Public landing page** at `https://ourfoxes.com/` that displays a small
   curated set of highlight clips. No login required to view — anyone with the
   URL sees the curated set.
2. **Login button** on the landing page that promotes any visitor to the
   full family-private experience (live cams, all highlights, favorites,
   remixes, etc.) via the existing Cloudflare Access flow.
3. **Admin role** — single user (or small allowlist) — who can promote /
   unpromote highlight clips to the landing page, set an optional caption,
   and pin/order them.

This is the first time the site exposes anything to anonymous traffic. The
plan is conservative: bypass CF Access for a small, explicit set of paths;
everything else stays gated.

## URL structure decision

**One public route, three private routes, one admin route. `/` is auth-aware.**

| URL | Auth | Renders |
|---|---|---|
| `/` | public | Landing page (hero + featured grid) **for anonymous** OR live grid **for authenticated** |
| `/live` | private | Live cameras (today's `/` content; new alias) |
| `/highlights` | private | Existing highlights gallery |
| `/clip/<event_id>` | private (mostly) — public iff featured | Clip permalink |
| `/remix/<remix_id>` | private (mostly) — public iff parent highlight is featured | Remix permalink |
| `/admin` | admin only | Admin UI to promote/unpromote highlights |

The auth-aware `/` is the cleanest solution to the PWA-start-URL question:
the manifest stays `start_url: /`, and logged-in installs land on the live
grid while public installs land on the landing page. No redirect dance, no
manifest swap.

The reason `/clip/<id>` becomes "public iff featured" is that the landing
page links to clip permalinks. If those required login, the landing would
be a list of clickable cards that all force a login wall, which defeats
the whole point of a public landing.

## What "public" actually means

| Path | Public access |
|---|---|
| `/` (landing for anonymous) | yes |
| `/static/*` (CSS, JS, icons) | yes — required for landing to render |
| `/api/featured` | yes — landing fetches featured highlight metadata |
| `/api/highlights/<id>` | yes **iff** that highlight has `featured=1` |
| `/api/highlights/<id>/clip` (MP4) | yes **iff** featured |
| `/api/highlights/<id>/thumbnail` | yes **iff** featured |
| `/clip/<id>` page | yes **iff** featured |
| `/remix/<id>` page | yes **iff** parent highlight featured |
| `/api/remixes/<id>` | yes **iff** parent highlight featured |
| `/robots.txt`, `/healthz`, `/manifest.webmanifest`, `/sw.js` | yes (already are) |
| Everything else | private |

Public read-only: a featured clip card on the landing page links to a clip
page where the video plays but action buttons (favorite, demote, ✂️ Remix)
are hidden. The "Login to do more" CTA replaces them.

## Cloudflare Access configuration (manual dashboard work)

The cleanest model is **two Access applications on the same domain**, with
path-based scoping:

1. **App 1: "Our Foxes — public surface"** (Bypass policy)
   - Path includes: `/`, `/static/*`, `/api/featured`, `/api/featured/*`,
     `/robots.txt`, `/healthz`, `/sw.js`, `/manifest.webmanifest`,
     `/favicon.*`, `/apple-touch-icon*`
   - Policy: **Bypass** — no Access challenge issued
   - Path-pattern conflicts handled at app level: a featured `/clip/<id>`
     hits this app via wildcard `/clip/*`, but our backend distinguishes
     featured vs not. Important: CF Access doesn't introspect featured-ness;
     the backend enforces.

2. **App 2: "Our Foxes — family"** (existing app, scope adjusted)
   - Path: `*` (everything else)
   - Policy: existing email-allowlist policy

Subtle: when /clip/<id> is bypassed, our backend sees no JWT — and must
itself reject if the clip isn't featured. The auth check moves from "JWT
present" to "JWT present OR (path featured AND public)." Implemented in
`require_cf_access` middleware.

Alternative path: keep one CF Access app, expand the bypass rule to cover
all path prefixes that CAN be public, and have the backend gate per-clip.
Less CF dashboard plumbing, same security model. **Probably the right
choice for v1.**

## Admin role mechanism

**App-level allowlist via env var, not CF groups, not DB-stored.** A single
admin (you) doesn't need fancier infrastructure.

```env
ADMIN_EMAILS=cdorsey@concord.org
```

In `_actor_email(request)` we already pull the CF Access JWT email. Add an
`is_admin(email)` helper that compares against the env list. Admin endpoints
return 403 if `is_admin` is false; admin UI only renders the controls when
`is_admin` is true.

If the family ever grows admins, switch to a CF Access group claim or a
small `admin` table. Don't over-engineer now.

## DB schema additions

Add four columns to `highlights`:

```sql
ALTER TABLE highlights ADD COLUMN featured INTEGER NOT NULL DEFAULT 0;
ALTER TABLE highlights ADD COLUMN featured_at REAL;
ALTER TABLE highlights ADD COLUMN featured_by TEXT;
ALTER TABLE highlights ADD COLUMN featured_caption TEXT;

CREATE INDEX IF NOT EXISTS highlights_featured ON highlights (featured, featured_at DESC);
```

Each migration is idempotent in our existing `_MIGRATIONS` array shape.

Featured ordering: `featured_at DESC` for default. If we want admin-controlled
custom ordering (drag-to-reorder), add `featured_position INT` later.

`featured_caption`: optional admin-written one-line description that appears
on the landing card and clip page. Useful for "Den emerges! 5/4 morning"-style
captions. NULL = use the auto-generated meta line.

## API endpoints

### New, public

```
GET  /api/featured?limit=12
       → list of featured highlight rows; no auth required

GET  /api/featured-clip/<event_id>
       → metadata for a single featured highlight (NOT through the regular
         /api/highlights endpoint, so we have a clear public/private split)
```

Public endpoints don't include `my_favorited`, `my_demoted`, `voters`, etc. —
those are family-only data. They include `event_id`, `start_time`, `camera`,
`label`, `species`, `species_confidence`, `clip_path`, `thumb_path`,
`duration_s`, `featured_caption`, `featured_at`.

### New, admin only

```
POST /api/highlights/<event_id>/promote
     body: { title?: string, caption?: string }
     → 403 if not admin

POST /api/highlights/<event_id>/unpromote
     → 403 if not admin

PATCH /api/highlights/<event_id>/featured
     body: { caption?: string }
     → edit caption only; 403 if not admin
```

### Existing endpoints — gating

`/api/highlights` (list), `/api/highlights/<id>`, `/api/highlights/<id>/clip`,
`/api/highlights/<id>/thumbnail`, and the actions (favorite, demote, remix)
**stay private** for now. The public read of featured clips goes through
the dedicated `/api/featured*` endpoints to keep the public surface
explicit and small.

## Frontend deliverables

### `templates/landing.html` — new

Public landing template. Branding (Our Foxes title, fox icon hero), short
description ("A small family camera setup watching foxes raise a den..."),
grid of featured cards. Each card:

- Thumbnail
- Caption (admin-written, falls back to species + camera + time)
- Click → `/clip/<event_id>` (public viewing)

Header includes a single **Login** button that hits any authenticated route
(e.g., `/live`) to trigger CF Access challenge. After auth the user lands
on the full app.

### `static/landing.js` — new

Fetches `/api/featured`, renders cards. No favorites / actions / per-user
state.

### `templates/index.html` — split

Currently `index.html` IS the live grid. We rename it to `live.html` and
make a new `index.html` that branches:

- Backend route handler for `/`:
  - if `cf-access-authenticated-user-email` header present → render
    `live.html`
  - else → render `landing.html`

`live.html` content stays unchanged. The new `index.html` template is
unused as a file; the route just picks which template to render based on
auth state.

### `templates/clip.html` — auth-aware action visibility

Already handles favorite/demote/remix display. Add a check: if user is
not authenticated AND clip is featured, render in "public read-only"
mode — no action buttons; instead a single "Login for more" CTA.

If user is not authenticated AND clip is NOT featured, the request
should never reach this template (CF Access plus backend gate together
return 401/403).

### `templates/admin.html` — new

Simple admin page. Lists ALL highlights (not just featured) with:

- Card preview
- Toggle: "Featured" checkbox
- Caption field (saves on blur)
- Sort by: most recently featured, most recent, by camera, by species

Renders only for admin users; backend returns 403 otherwise.

### Promote action on existing cards

When an admin views the regular `/highlights` gallery, each card gets an
extra small button: "★ Promote" / "★ Featured" (toggle). One click sets
`featured=1` and prompts for an optional caption.

## Cloudflared / CF dashboard tasks (manual)

(After ourfoxes.com is active, presumably already done by now.)

1. **Edit existing Cloudflare Access application** to scope it to
   authenticated paths only.
   - Domain: `ourfoxes.com` (and subdomains)
   - Application type: Self-hosted
   - Add **Bypass policy** at the top of the rule list:
     - Action: Bypass / Allow Anyone
     - Include rule: Identity > Everyone (no email match needed for bypass)
     - Path: regex matching `^/$|^/static/|^/api/featured|^/api/featured/.*|^/robots\.txt$|^/healthz$|^/sw\.js$|^/manifest\.webmanifest$|^/favicon\..*|^/apple-touch-icon.*$|^/clip/.*|^/remix/.*|^/api/highlights/[^/]+/clip$|^/api/highlights/[^/]+/thumbnail$`
   - Existing email-allowlist policy stays as the second rule, applies
     when path doesn't match bypass.
2. The clip and remix paths (`^/clip/.*`, `^/remix/.*`) are ALSO bypassed
   at CF — but our backend then enforces "must be featured to view this
   clip without auth." This is the right pattern: CF can't introspect
   featured-ness, so we need backend gating regardless.
3. Anonymous viewers hitting `/highlights` or `/admin` see the CF Access
   login wall.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Featured clip ID enumeration ("guess /clip/X for any X") leaks unfeatured clips | Backend explicitly checks `featured=1` before serving any clip data on bypassed paths |
| CF Access bypass rule misconfigured leaks family data | Test matrix: anonymous request to each path; expected status (200 / 401 / 404) documented and verified per release |
| Admin promotes a clip that contains the family or kids' faces | One-click unpromote is fast; consider a "preview as anonymous" admin button to verify what would land publicly |
| Public landing gets crawled by social sharers (Twitter/Facebook/Discord previews) | Add OpenGraph meta tags on featured clip pages so previews look good. Robots.txt still says don't index. |
| Manifest's `start_url: /` lands installed-PWA users on the landing if they're not authenticated | Acceptable — they tap Login from there. Document in PWA install instructions. |
| Cloudflare caches public clip MP4s at the edge → admin unpromotes → cached MP4 still available for hours | Set `Cache-Control: private, max-age=300` on featured clip MP4s. 5-min cache is short enough that an unpromote takes effect quickly. |
| Featured count grows unbounded as admin promotes things | Either UI-limit display to N most recent OR add a "demote oldest" rule. Probably display N=12 most recent featured on landing; admin UI shows all. |
| New admin needs to be added | Single env-var change + curator restart. Document in runbook. |

## Effort estimate

Roughly 1 day of work across:

- ~1.5h: DB migrations + admin role helper + featured promote/unpromote API
- ~2h: public `/api/featured*` endpoints + per-clip featured gating in
  middleware
- ~2.5h: landing template + landing.js + integration with existing card
  rendering
- ~1h: admin page (list + promote toggle + caption edit)
- ~1h: clip.html auth-aware action visibility
- ~1h: CF Access dashboard configuration + testing matrix

Plus ~1h "design polish" for the landing page that we'll likely want
(typography, hero treatment, "About" copy block).

## Implementation order (when picked up)

1. **DB migration + admin helper** (smallest, safest, doesn't ship anything)
2. **Promote/unpromote API + frontend toggle on existing cards**
   (admin can promote things; nothing public yet)
3. **Public `/api/featured*` endpoints + featured-gating middleware logic**
   (still no public template; can curl `/api/featured` to verify shape)
4. **Landing template + branching `/` route + landing.js** (public grid
   visible; clip pages still gated)
5. **Clip.html auth-aware action visibility** (public viewing of featured
   clips works end-to-end)
6. **Admin page** (concentrated UI for managing featured set)
7. **CF Access dashboard rule** (last so we can test backend gating
   with curl + fake JWT before exposing publicly)

Each step lands as its own commit; only the last makes anything public.

## Out of scope for v1

- Drag-to-reorder featured set (use `featured_at DESC` ordering for now)
- Featured-clip statistics dashboard ("how many anonymous views per clip")
- Custom landing-page hero/copy beyond the basic one we'll write
- OG meta tags for social embeds (queued as a follow-up; relevant when
  someone actually shares a featured clip URL externally)
- Multiple admin tiers / per-clip admin overrides
- "Rotating featured" — auto-promote based on heuristics

Each is a follow-up; the v1 above gets the core "public landing + login +
admin can promote" feature complete.

## Open questions to settle before we start

1. **Default size of featured grid on the landing.** 6? 8? 12? My pick: 8 —
   roughly four cards per row on desktop / two on mobile, fits in a viewport.
2. **Hero treatment**: photo of a fox, the fox icon at large size, or just
   typographic? My pick: the fox icon at ~140px, then a one-line tagline,
   then the grid. Avoids needing a photo and keeps loading fast.
3. **Login flow UX**: a button labeled "Login" or "Family login"? My pick:
   "Family login →" since it sets the right expectation about who has
   accounts.
4. **Featured caption max length**: enforce 80 chars? 140? My pick: 140 —
   one tweet-sized sentence, plenty for "Two kits emerged this morning,
   played for ten minutes."
5. **Show how many family favorites / remixes a featured clip has?** Could
   be a nice "this is loved by the family" social signal. My pick: yes,
   show a small "⭐ N · 🎬 N" badge — same data we already attach.

If you're fine with my picks above, no need to discuss further; I'll just
build it that way.
