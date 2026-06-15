# Work-Packet → OmniFocus Note Fidelity — Fix Plan

> **For agentic workers:** execute with superpowers:executing-plans; TDD where tests are specified. Checkbox steps.

**Goal:** OmniFocus task notes carry the **full richness** of the backtrace/PACKET INFO (all three context nodes, brief, knowns/unknowns, resources-as-clickable-links, related tasks, suggested subtasks, agent notes, mismatch warnings) — correctly encoded, correctly formatted, from one canonical store, with failures visible. Establish an evaluation set so the result can be judged.

**Diagnosis basis (verified 2026-06-15 on real tasks 19e93fe4 / 3d69358e-a / meeting-not_jlLav4yZFqNMBh-chad-3):** first-pass rich note IS written and packet_info IS real, but: (1) all non-ASCII chars corrupted; (2) double bullets; (3) literal `\n`; (4) `enrichment` column empty — packet_info lives in archival `task_body`; (5) resources empty (gws fetch failed); (6) the enrich→re-render loop is severed; (7) two redundant writers, failures swallowed.

---

## Phase 1 — Encoding (root cause; do first, unblocks everything)

**Root cause:** `omnifocus-mcp-letta/host-bridge-service.js:42` `B64_DECODE_JS` decodes base64 to a per-byte Latin-1 string (`String.fromCharCode`), never UTF-8-decoding → multibyte chars corrupted before storage. Affects ALL bridge calls.

- [ ] **Step 1 — Failing test (round-trip through the live bridge).** Create `omnifocus-mcp-letta/tests/test_encoding_roundtrip.sh` that creates a temp OF task, `setRichText` a note containing `• "smart" — em‑dash ✓ café`, reads it back via `getTask`, and asserts the bytes are clean UTF-8 (no `\xef\xbf\xbd`, contains real `•`). Run → FAILS today.

- [ ] **Step 2 — Fix the decoder.** In `host-bridge-service.js`, append a UTF-8 reassembly to `B64_DECODE_JS` so `r` becomes a proper UTF-8 string before `JSON.parse`:
```js
// after the decode loop, add:
"r=decodeURIComponent(escape(r));"
```
If OmniJS lacks `escape`/`decodeURIComponent` (verify in Step 3), fall back to manual UTF-8 reassembly over the byte values. Prefer the one-liner.

- [ ] **Step 3 — Restart bridge + verify support.** `launchctl kickstart -k gui/$(id -u)/com.ai-pa.omnifocus-bridge` (or unload/load the plist). Re-run Step 1 test → PASSES (clean `•`, no U+FFFD). If `escape` is unavailable in OmniJS, the test reveals it; implement the manual fallback and re-verify.

- [ ] **Step 4 — Re-render the 3 corrupted eval notes** (after Phase 2 renderer is also fixed, or now to confirm encoding alone): hit `/api/tasks/<ref_id>/reassemble-work-packet` for each; confirm bytes are clean.

- [ ] **Step 5 — Commit** (`fix(omnifocus-bridge): UTF-8-decode base64 params (was Latin-1 per-byte → mojibake in all notes)`). NOTE: bridge is host launchd, not Docker — no image rebuild; the restart in Step 3 is the deploy.

---

## Phase 2 — Render fidelity (full richness + formatting)

**Where:** `pa-web-ui/app.py` `_build_work_packet_segments` (~3232). Current note shows only Context / Knowns-Unknowns / Resources and double-bullets / literal `\n`.

- [ ] **Step 1 — Audit packet_info schema → segment coverage.** Confirm the full field set rendered: `direct_action`, `artifact_provenance`, `intent_genesis` (the THREE-NODE model — currently under-rendered), `context_brief`, `knowns`, `unknowns`, `resources` (clickable, incl `openfile://`), `related_tasks`, `suggested_subtasks`, `agent_notes`, `mismatch_warning` (red/bold). Add a fixture `pa-web-ui/tests/fixtures/packet_info_full.json` exercising every field incl. `\n`-containing strings and `"• "`-prefixed strings.

- [ ] **Step 2 — Failing tests** (`pa-web-ui/tests/test_work_packet_segments.py`): assert (a) every field renders a section; (b) no doubled bullets (content `"• x"` → single bullet); (c) `\n` inside a value becomes separate lines/segments, never literal `\n`; (d) resources render as URL segments (Slack→"Permalink", openfile→label); (e) three nodes each get a labeled section. Run → FAILS.

- [ ] **Step 3 — Implement.** One owner for list markers (renderer adds bullets; strip a leading `"• "`/`"- "` from content). Split values on `\n` into separate line segments. Add the missing three-node + related_tasks + suggested_subtasks + agent_notes sections. Run → PASSES.

- [ ] **Step 4 — Commit** (`feat(pa-web-ui): render full packet_info richness in OF note; fix double-bullets and literal \n`).

### ⚠️ OmniFocus rich-text rendering is quirky — verify DISPLAY, not just write-success
OmniFocus notes are **attributed strings** set via OmniJS `Text`/`Style` (`applyStyles` → `Style.Attribute.Link`, FontWeight, Size, FontFillColor, UnderlineStyle). Known quirks to design/verify against (user-flagged 2026-06-15):
- **`setRichText` returning `{success:true}` does NOT prove correct display.** Verification must read the note **back as attributed runs** (and/or eyeball it in the OmniFocus UI), not just trust the write.
- **Links / clickability:** clickable links need the `Link` attribute on the run via `URL.fromString(...)`; plain URL text may or may not auto-linkify. **Custom schemes (`openfile://`) must be confirmed clickable in the actual OF UI** — OmniFocus may reject/strip non-standard schemes. Test a real `openfile://` link end-to-end (click it).
- **Newlines/paragraphs:** line breaks must be real `\n` inside the `Text` content; OmniFocus paragraph handling can collapse/alter runs.
- **Display surfaces differ:** the note inspector vs. the row preview vs. iOS may render attributes differently; styles can change on **Omni sync round-trip**. Don't assume Mac-inspector appearance == everywhere.
- **Color/size may be overridden** by the note's own display settings — don't rely on color alone to convey meaning (e.g. mismatch warning should also be labeled in text, not just red).

Implication: every encoding/render test in Phases 1–2 and the eval harness must assert on **read-back attributed content** and include at least one **human visual confirmation** in the OmniFocus app for links + structure.

---

## Phase 3 — Substrate consolidation (canonical packet_info store)

**Problem:** `enrichment` column is `[]`; packet_info actually lives in archival `task_body`. Code treats `enrichment.packet_info` as canonical but silently runs on the `task_body` fallback — and this is why reassemble (which writes the column) doesn't surface.

- [ ] **Step 1 — Decide canonical = `pa_web.tasks.enrichment.packet_info` (Postgres JSONB)** — the live local-mode substrate. Document the decision.
- [ ] **Step 2 — Verify/fix `write_packet_info_tool.py`** writes packet_info to that column for the owner/worker agents on the CURRENT substrate (not archival only). Test on a real task: confirm the column populates.
- [ ] **Step 3 — Make readers consistent:** `_build_work_packet_segments` and `api_get_task_detail` prefer the column, fall back to `task_body` for legacy rows. Backfill note in plan; no destructive migration.
- [ ] **Step 4 — Commit.**

---

## Phase 4 — Reconnect enrich → re-render loop

**Problem:** `write_packet_info` does NOT trigger `/api/tasks/<ref_id>/reassemble-work-packet` (the docstring claims it does — false); the endpoint has no in-repo caller, so post-confirm deep enrichment never reaches the note.

- [ ] **Step 1 — Wire `write_packet_info_tool.py` to POST `reassemble-work-packet`** for the ref_id after a successful write (host-reachable URL; honor the runner-env lessons — no Docker-internal hostnames). Test: write packet_info → note re-renders.
- [ ] **Step 2 — Remove/repair the false "auto-triggers reassemble" claims** in `app.py:3773,3788` so docs match behavior.
- [ ] **Step 3 — Commit.** (Now meaningful because Phase 3 made the column authoritative.)

---

## Phase 5 — Source-fetch reliability (populate resources/links)

**Problem:** task 19e93fe4 `agent_notes` = "remote Gmail fetch failed (gws CLI error)" → `resources: []`, no audit URL/openfile. The gws-under-runner issue starves the packet of its key links.

- [ ] **Step 1 — Reproduce** the gws fetch failure in the dispatch/runner context (the [[feedback_ext_tools_shell_cli_runner_context]] class: PATH/creds under launchd).
- [ ] **Step 2 — Fix** so `fetch_source_content` + `stage_resource` succeed under the worker's execution context; resources populate with real URLs and `openfile://` staged paths.
- [ ] **Step 3 — Verify** a freshly-promoted email task has its source link in resources.

---

## Phase 6 — Single authoritative writer + observable failure

**Problem:** every confirm writes the note twice (browser plain `createTask`, then backend rich `setRichText`); rich-write failures are swallowed (`except: pass`, silent `False`) leaving the plain note as a silent fallback — opposite of "rich note is primary."

- [ ] **Step 1 — One writer:** the backend rich-text path is authoritative. Drop the browser `buildOFNote`→`createTask` note (create the OF task without the plain note body, or have the backend own both create + note). Avoid the immediate clobber.
- [ ] **Step 2 — Observable failure:** on rich-write failure, surface it (task detail flag + loud log), don't silently leave a degraded note.
- [ ] **Step 3 — Commit.**

---

## Evaluation set — "work packets in action"

Use these to judge the end state. Re-render each after fixes and compare against the bar.

| ref_id | source type | What a GOOD note must show |
|---|---|---|
| **19e93fe4** | Email (Kiley audit) | clean bullets/quotes; three-node (direct-action=email, provenance, intent); **the audit URL present** in resources (Phase 5); knowns/unknowns; no `â�¢`/`\n` |
| **3d69358e-a** | Check-in / calendar (Hee-Sun) | three-node incl intent genesis (APLUS/ISLAND); related coordination (Seoul Nat'l, Lee Chew); suggested subtasks if any; clean encoding |
| **meeting-not_jlLav4yZFqNMBh-chad-3** | Meeting (board update) | Granola resource as a **clickable** link; `\n`-separated bullets render as real lines; monthly-cadence context; clean encoding |

- [ ] **Eval harness:** a one-shot `scripts/dump-work-packet.sh <ref_id>` that fetches the live OF note (bridge `getTask`) + the `packet_info`, prints both, and flags any `�`, literal `\n`, or doubled bullets — so we can run it per task before/after and visually confirm richness. Capture a before/after for all 3 eval tasks.
- [ ] **Also pick one FRESH task per source after the fixes** (promote a new email, meeting, and slack task) to confirm the live pipeline (not just re-renders) produces full-richness notes end-to-end.

---

## Sequencing rationale
Phase 1 first (every note is corrupted; cheap; unblocks readable evaluation). Phase 2 (richness/format) next — the other high-visibility win. Phase 3 (substrate) before Phase 4 (reassemble) because reconnecting the loop is pointless until the column is canonical. Phase 5 (source-fetch) independent but needed for resource links. Phase 6 (single writer/observability) last — hardening so this can't silently regress.
