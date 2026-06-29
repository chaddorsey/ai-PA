# Deep-Dive Featured Stories — Feature Design

**Date:** 2026-06-29
**Status:** design (for build) — content set identified in parallel (`2026-06-29-deepdive-stories-candidates.*`)

## Concept
Occasional **extended stories** (~3–5 min, true narrative arcs) that get a **featured card**: hero
photo + formatted text. Each is available two ways:
1. **Read** — open the card and read it as formatted long-form text, anytime.
2. **Listen** — the voice-rendered version, offered/interspersed in the regular narration as the
   train nears the story's place.

~16 per leg (4 per theme), ~1 per 60–90 min. They are NOT scheduler squibs/interstitials — they are a
separate, opt-in layer that rides alongside the position-driven narration.

## Data model (companion-core)
Add `DeepDive` and make it an optional top-level bundle array (keeps the scheduler untouched):

```ts
export interface DeepDiveImage { url: string; caption: string; credit: string; license: string; }
export interface DeepDiveSource { title: string; url: string; }
export interface DeepDive {
  id: string;
  theme: string;
  title: string;
  mile: number;            // placement along route
  trigger_mile: number;    // where it becomes "available" (default: mile - 8)
  nearest_place: string;
  hook: string;            // 1–2 sentence teaser (shown on the offer + card header)
  body_md: string;         // formatted markdown — the READ version
  narration_text: string;  // the SPOKEN version (may differ slightly from body)
  est_listen_min: number;
  audio: string | null;    // rendered audio path; null until rendered (offer still shows "Read")
  images: DeepDiveImage[];
  sources: DeepDiveSource[];
  salience: number;
}
// Bundle gains:  deepdives?: DeepDive[]
```
`validateBundle` treats `deepdives` as optional (older bundles without it still validate).

## Settings
New setting `featuredStories: 'offer' | 'auto' | 'off'` (default **'offer'**), in `SchedulerSettings`
or a sibling app-settings field. Settings UI: a select "Featured stories" →
- **Offer (recommended)** — a gentle banner when one becomes available; you choose Listen/Read/Later.
- **Auto-play** — plays the narration automatically in the next gap.
- **Off** — no offers; still browsable in the Stories tab.

## UI components
1. **`FeaturedCard.svelte`** — full reading view: hero image (first `images[]`), theme chip, title,
   hook, `body_md` rendered to HTML, inline image captions+credits, a sources footer, and a
   **Listen** button (plays `narration_text` audio via the orchestrator if `audio` present; disabled
   with "Audio coming soon" when null). Favorite/Saved + "Mark read". Scrollable long-form layout,
   ~20px body to match the HTML-review font preference.
2. **`DeepDiveOffer.svelte`** — a slim banner (sits with the NowBar) shown when a deep-dive becomes
   available and not yet seen: theme chip + title + hook + [Listen] [Read] [Later]. Auto-dismiss when
   the train passes `mile + 5` or on Later. In `auto` mode, skip the banner and play.
3. **Stories surface** — a new **Stories** tab (add to `TabNav`, follow existing tab pattern):
   the leg's deep-dives as a list (theme chip, title, hook, mile, image thumb, "read"/"listened"
   state). Tapping opens `FeaturedCard`. All are readable anytime; the one nearest current position is
   highlighted ("Now near you").

## Orchestrator / position integration
- A small `DeepDiveDirector` (in `PlaybackOrchestrator` or alongside it): on each position update, find
  any unseen deep-dive whose `trigger_mile <= mile < mile+5` and that the scheduler isn't about to
  fire a squib over. If `featuredStories==='off'` do nothing. If `'offer'`, set
  `appState.pendingDeepDive = dd` (drives the banner). If `'auto'`, play its narration (duck regular
  flow) and mark seen. Mark `seenIds` so each offers once.
- Listening uses the same `AudioSession.play()` path; while a deep-dive plays, regular squib firing is
  suppressed until it ends (it's long). On end/skip, resume normal scheduling.

## Proxy content (so the feature is demoable before the real render)
Until the identified set is approved + rendered, embed **2–3 proxy deep-dives** in
`static/bundles/leg58/bundle.json` under `deepdives` — real titles/hooks/placements from the candidate
set, a real Wikimedia hero image URL, `body_md` = the candidate summary (clearly a draft), `audio:null`.
This lets the user see the card, the offer banner, and the Stories tab working end-to-end. Real bodies
+ audio land after the user approves the set and we render.

## Markdown
Render `body_md` with a tiny dependency (`marked`) — content is first-party/trusted. Add to
companion-web only.

## Build order (tasks)
1. companion-core: `DeepDive` types + bundle field + `validateBundle` optional handling + unit tests.
2. Proxy `deepdives` in the leg58 static bundle (2–3 entries) + bundleInit passes them through.
3. `FeaturedCard.svelte` + markdown render + tests (renders title/body/sources, Listen disabled when audio null).
4. Stories tab (`TabNav` + `/stories` route + list) + tests.
5. `DeepDiveOffer` banner + `appState.pendingDeepDive` + `DeepDiveDirector` position logic + setting + tests.
6. Browser verify end-to-end (sim to a trigger mile → offer appears → Read opens card → Stories tab lists).

## Open questions for the user (saved, not blocking)
- **Surface:** new bottom **Stories tab** (chosen default) vs a section inside Trip — confirm.
- **Default mode:** `offer` (chosen) vs `auto-play` for the interspersed listen.
- **Card layout:** confirm hero-image-on-top long-form layout (mock in the app to react to).
- Story SET approval (titles/placement/intrigue) — from the candidates doc.
