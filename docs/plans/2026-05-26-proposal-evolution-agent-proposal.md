# Proposal-Evolution Agent — Working Doc

**Status:** Hypothetical / exploration. No commitments.
**Date:** 2026-05-26
**Author:** Chad + Claude
**Audience:** Self; future PA-fleet design conversations

## What this is

A working proposal for a future Letta agent that becomes an expert in the
craft of grant-proposal writing by learning from the longitudinal corpus
of past proposals — their internal comment/revision history, the RFP
they targeted, and the post-hoc panel reviews they received.

The agent is **not** a live writing companion (that's a much harder
product). It's a **librarian + analyst + coach** that compounds
institutional memory over many proposal cycles.

## Why this is feasible now (and wasn't before)

The data we need is already in Drive. Specifically:

- Every comment on every past proposal is recoverable via Drive API
  `comments.list(includeDeleted=true)` — with author, timestamps,
  anchor, reply threads, resolved/deleted state, and the frozen
  `quotedFileContent` (the text the comment was attached to, snapshot
  at comment-creation time).
- Every revision checkpoint is enumerable via Drive API
  `revisions.list` — with timestamp + `lastModifyingUser` — and every
  historical revision is exportable as DOCX, HTML, plain text, or PDF
  via `exportLinks`. Google retains these indefinitely for Docs.
- The Drive Activity API v2 gives a timeline of edit / comment /
  share / move events to fill gaps.

So for any completed proposal sitting in Drive today — winning or
losing, recent or years old — we can reconstruct the full evolution
trace **without** having instrumented it during writing.

We deliberately exclude **suggested-edit** granularity (suggest-mode
inline insertions/deletions). That's the one surface that vanishes
post-acceptance, and capturing it would require a live snapshot
pipeline. Text-diff between revision exports tells us what changed
regardless of whether the change came in via suggest-mode or
direct-edit, which is sufficient.

## The killer capability

Every proposal has two reviews — the internal one (your collaborators'
comments) and the external one (the panel's narrative reviews). The
single most valuable thing this agent does is **compare those two**:

- Did internal review catch what the panel flagged, or miss it?
- Which internal reviewers' concerns most consistently predicted panel
  critiques? (These are the team's "best critics" — their comments
  deserve disproportionate weight in future proposals.)
- Which internal concerns turned out not to matter to the panel? (We
  may be over-revising on some axes.)
- Were there panel critiques nobody raised internally? Those are
  blind spots in the review process.

Over a dozen+ proposals this becomes a quantified profile that
ordinarily lives — fragmentarily and unreliably — in senior PIs'
heads.

## Capability categories

### 1. Per-proposal post-mortem
- Heatmap of where time went per section
- Iteration curve per section; what got rewritten in the final 48hrs
- Comment-driven vs. self-driven revisions
- Stress-vs-quality correlation: rushed sections vs. settled ones, by
  panel-review outcome
- Unresolved-comment audit: which comments were closed without being
  addressed; did the panel raise the same issues
- Author breakdown: who wrote, revised, reviewed each section

### 2. Cross-corpus pattern mining
- Section-iteration norms (winning proposals stabilize Aims 2 wks
  before submission; losing ones still moving at 3 days, etc.)
- Comment-density signatures correlated with outcome
- Revision-velocity patterns: bursty-late vs. steady
- Lexical signals: phrases or arguments that draw negative panel
  reactions; ones that survive review intact
- RFP-specific patterns (NSF DRK-12 panel tendencies vs. IES vs.
  private foundation, etc.)
- PI-team patterns: solo vs. multi-author trajectories; collaborator
  pairs that produce productive friction vs. churn

### 3. Mid-process diagnostics on the next proposal
Once the corpus is indexed, the agent can advise on a live draft:
- "At this stage of similar past proposals, comments were 60%
  structural; yours are 80% line-edit — you may be polishing while a
  conceptual hole remains"
- "Your Aims are on revision 5 with a week to go; winning proposals
  of this size had aims stable by now"
- "Tom's comment on page 7 echoes themes that panel reviewers flagged
  on Proposals A, B, and C. This is probably real."
- "Sarah hasn't commented yet. Her track record says her review is
  worth waiting for."
- "You historically run out of time on Budget Justification; it
  hasn't been touched yet."

### 4. Reviewer / collaborator profiles
For each collaborator, a craft fingerprint:
- Style: line-editor / structural / content-gap-finder / cheerleader
  / devil's-advocate
- Predictive power: comment-to-panel-critique correlation
- Section affinity: who reliably improves what
- Timing: early vs. late; which is more valuable for what

Powers "who should I invite to review this proposal" suggestions.

### 5. Strategic / portfolio-level advice
- Win/loss patterns by RFP type
- Effort-to-outcome ratio per program
- Recurring weakness across many proposals (systemic, not
  per-proposal)
- Recurring strength to lean into

### 6. The institutional-memory effect
The agent's advice gets better with every completed proposal:

> "Three years ago you tried this same theoretical framing in
> Proposal X — panel rejected it as overreach. Reviewer Sarah flagged
> it then too. Either reframe or pre-empt the critique explicitly."

## Architecture sketch

This is intentionally vague — we're at "is this worth pursuing" not
"how do we build it." But the rough shape:

### Data layer
- **Corpus index**: for each completed proposal, a record with
  `proposal_id`, `rfp_id`, Google Doc ID, submission date, outcome
  (won/lost/pending), program officer, panel review text(s),
  collaborator list.
- **Per-proposal evolution archive**: comments JSON (full thread
  state, anchors, `quotedFileContent`), revisions index (all
  checkpoints with timestamps + authors), and DOCX exports of
  strategic revision points (e.g., one per cluster boundary).
- **Derived signals**: paragraph-hash iteration counts, comment
  density by section over time, unresolved-comment lists,
  panel-vs-internal alignment scores.

### Storage
- Postgres for the structured corpus index + derived signals (joins
  well to the existing pa_web schema)
- Object store / Drive for raw exports
- Likely a small embedding index for "find similar proposals / similar
  comments / similar panel critiques"

### Agent
- A docs-and-transcripts-agent (or new sibling) with skills:
  - `proposal-corpus list/search/get`
  - `proposal-evolution analyze <proposal-id>`
  - `proposal-evolution compare-internal-vs-panel <proposal-id>`
  - `proposal-evolution diagnose <live-draft-doc-id>`
  - `proposal-reviewer-profile <person>`
  - RAG over panel-review corpus for cross-proposal queries

### Build sequence
1. **Smallest validating spike (1 week)**: 3-5 recent proposals,
   manually ingested, ask the agent to do the
   internal-vs-panel-comparison + identify "best critics" + flag
   "missed concerns." Test against team intuition.
2. If spike validates: build the corpus ingestion pipeline (Drive →
   Postgres + exports).
3. If pipeline works: build cross-corpus pattern-mining queries.
4. Last: mid-process diagnostics on live drafts (highest-value but
   needs the corpus mature to be credible).

## Risks & caveats

- **Causation vs. correlation**: comment density correlating with
  success doesn't mean *adding* comments helps; it might mean engaged
  teams write better proposals.
- **Sample size**: dozens of proposals supports directional advice,
  not statistical confidence on subtle effects.
- **Panel review variance**: same proposal scores differently with
  different panelists; agent shouldn't over-interpret single panels.
- **Selection bias**: only submitted proposals have panel outcomes;
  killed-internally proposals are missing from the outcome signal.
- **Privacy**: comments often contain candid feedback from
  collaborators. The corpus is sensitive. Treat as such.
- **The "advisor" framing matters**: agent surfaces patterns, the
  team decides. Not an oracle.

## What's needed to evaluate this seriously

Before any build:

- [ ] Confirm Drive comment + revision retention on a few oldest
      proposals — does the history actually go back as far as we'd
      want?
- [ ] Confirm panel-review text is captured somewhere queryable (not
      just PDFs in someone's email). If not, ingestion of that corpus
      is its own task.
- [ ] Pick 3-5 candidate proposals (mix of wins + losses, mix of
      recent + older) for the validating spike.
- [ ] Identify a "ground-truth" team member — someone who remembers
      these proposals well enough to validate the agent's findings.
- [ ] Decide whether this is a Concord-only tool or has broader
      utility (the architecture barely changes either way; the
      framing might).

## Not building this now

This doc exists to capture the idea while it's fresh. Active fleet
work (migration to local-mode, tasks-agent storage, skill
buildout) takes priority. Revisit when:

- The 6-agent fleet migration is complete and stable
- We have at least one capacity-free week to commit to the spike
- Or: a specific imminent proposal cycle creates a natural test case

## Letta forum agent consultation (Ezra, 2026-05-26)

Consulted Ezra (Letta team) for design guidance. Synthesized here;
his framing reshapes the architecture significantly. Key takeaways:

### Don't fine-tune. Use retrieval + memory + workflows.

> "This is better approached as retrieval + memory + workflow skills
> than fine-tuning first. Fine-tuning is probably premature unless
> you later have hundreds/thousands of examples of desired review
> comments in a consistent format."

Means: the corpus is a searchable document store + curated lesson
cards, not training data. The agent's pinned memory stays small —
rubrics, workflow, org preferences, lookup rules.

### Capability list (Ezra's framing — broader than mine was)

- **Solicitation analysis**: extract eligibility, review criteria,
  hidden constraints, required attachments, scoring emphasis.
- **Proposal strategy**: compare a new opportunity against past
  wins/losses; suggest positioning.
- **Red-team review**: simulate panel feedback against the rubric
  and prior reviewer comments.
- **Reuse guidance**: find prior language, diagrams, management
  plans, evaluation plans, biosketch themes — with citations back
  to source proposals.
- **Draft coaching**: identify weak claims, missing evidence,
  compliance risks, overused boilerplate, places reviewers may object.
- **Institutional learning**: maintain "what tends to work for us
  with agency/program X" as living memory.

My original framing was heavier on evolution-trajectory analysis
(comment-driven revisions, iteration curves). Ezra's framing is
heavier on *prospective* assistance for new proposals — the
evolution data is one input among several. Both views are
compatible; the prospective framing is probably the higher-value
direction for actual use.

### The "proposal packet" — the canonical data unit

One folder per proposal, structured as:

```
proposals/<proposal-id>/
  solicitation/             # the RFP / FOA / call
  submitted/                # the final submitted proposal
  reviews/                  # panel narrative reviews
  draft-history/            # comments + revisions (recent proposals only)
  metadata.yaml             # agency, program, year, topic, PI/team,
                            # amount, result, score/percentile, review
                            # criteria, document links
  lessons.md                # curated synthesis: reviewer objections,
                            # winning strengths, reusable language,
                            # anti-patterns, "if rewriting today..." notes
```

The `lessons.md` is the highest-leverage artifact. Ezra:

> "Run extraction passes to produce metadata + lessons cards. Have a
> human review the lessons for accuracy; this is where quality
> compounds."

So the pipeline is: raw documents → automated extraction → human
review → compounding asset. Not "agent dumps every comment into
context."

### Red-team as workflow, not standing multi-agent team

Ezra is explicit: **start with one primary advisor agent + ephemeral
subagents for bounded review passes.** Letta Teams may come later;
not first.

Five red-team personas (subagent prompts, not durable agents):

1. **Compliance reviewer** — page limits, required sections,
   attachments, font/margins, eligibility, "must/shall" language.
2. **Rubric reviewer** — scores each section against exact review
   criteria; quotes the solicitation.
3. **Skeptical panelist** — "why would I not fund this?"; flags
   unsupported claims, vague impact, weak evaluation, missing
   preliminary evidence.
4. **Program-officer lens** — fit to agency/program priorities;
   responsiveness to the funding mechanism.
5. **Internal grants editor** — clarity, narrative arc, reviewer
   cognitive load, boilerplate discipline.

The primary agent packages the relevant excerpts and calls each
reviewer for structured output. Durable knowledge lives in the
primary agent's memory/corpus, not in five long-lived agents.

This matches our existing pattern (harness-level Task/Agent calls
with agent_id; ephemeral reflection subagents). Don't build five
durable Letta agents.

### Skills the primary agent needs

- Solicitation intake
- Packet lookup
- Compliance matrix
- Red-team review (dispatches subagents)
- Rewrite suggestions
- Final submission checklist

### Models

> "Use a strong long-context writing/reasoning model for synthesis
> and review, plus vision-capable support if diagrams matter. Claude
> Sonnet-class or GPT-5.x-class models are good fits for high-stakes
> drafting/review; Gemini-class vision models can be useful for
> cheaper diagram/table interpretation."

Concrete:
- **Primary advisor**: Claude Sonnet-class (we have Anthropic API);
  long-context is essential for 15-page proposals + solicitation
  + reviews simultaneously.
- **Diagram interpretation**: Gemini vision (cheaper) for first-pass
  diagram captioning during corpus ingestion; pinned model — don't
  rely on auto-routing for diagram-heavy work without testing.
- **Subagent red-team passes**: same Sonnet-class; the work is high-
  stakes critique, not throughput.

### Evaluation set

Ezra's specific suggestion:

> "Build an evaluation set: 5-10 historical solicitations where you
> know the outcome, and test whether the agent's advice matches
> what reviewers later said."

This is the validating spike, more rigorously framed than my version.
Hold out solicitation + proposal, hide the panel reviews from the
agent, have it produce red-team critique, then compare to actual
panel feedback. The match rate is the quality signal.

### Assimilation pipeline (Ezra's full sequence)

1. Ingest raw documents into organized packets.
2. Run extraction passes to produce metadata + lessons cards.
3. **Human review** of lessons cards — this is where quality compounds.
4. Build skills (the 6 listed above).
5. Pin operating memory: how the org writes, how to search packets,
   how to cite sources, what NOT to invent.
6. Evaluate on historical proposals (the held-out set).

### Revised architecture sketch (Ezra-shaped)

**Single agent**: `grant-advisor` (new sibling to docs-and-transcripts,
not a skill on it — distinct enough domain).

**Memory**:
- Pinned memfs: org style, lookup rules, citation discipline,
  anti-hallucination guardrails
- Corpus: per-proposal packet structure on disk + searchable index

**Subagents** (ephemeral, harness-spawned via Task/Agent):
- compliance-reviewer
- rubric-reviewer
- skeptical-panelist
- program-officer-lens
- grants-editor

**Skills** (CLIs):
- `proposal-packet` — list, get, search, build
- `solicitation-intake` — extract criteria + constraints from a new FOA
- `compliance-check` — run compliance reviewer against a draft
- `red-team` — dispatch all five reviewers, aggregate output
- `reuse-find` — search corpus for reusable language/diagrams
- `lesson-extract` — pull lesson cards from a completed proposal
  (used during ingestion)
- `proposal-evolution` — the original framing; comment/revision
  analysis still valuable as an input to lesson extraction

**Data layer**:
- Filesystem packets (per Ezra) for portability + grep-ability
- Postgres index for cross-corpus queries (program, year, outcome,
  team) — joins to pa_web schema
- Embedding index for semantic search across packets
- Drive remains source of truth for raw docs; packets are derived

### What this changes vs. my original sketch

| Original framing | Ezra-revised |
|---|---|
| Skill on docs-and-transcripts-agent | New `grant-advisor` agent (distinct domain) |
| Heavy on comment/revision archaeology | One input among several; lesson cards higher leverage |
| "Mid-process diagnostics" as flagship capability | Red-team review is flagship; diagnostics are downstream |
| Cross-corpus pattern mining as main asset | Per-packet lesson cards + retrieval as main asset |
| Build sequence: spike → pipeline → patterns → diagnostics | Build sequence: packet schema → ingest → lessons → skills → red-team → eval set |
| Postgres-centric storage | Filesystem-centric (per-packet folders) + Postgres index |
| 5-7 capabilities all under one agent | Primary advisor + 5 ephemeral subagent personas |

The Ezra framing is better. It separates the durable knowledge
substrate (packets + lessons + pinned memory) from the workflows
that operate on it (intake, compliance, red-team), and it explicitly
keeps the multi-agent complexity ephemeral instead of standing up
five new long-lived agents.

### Unknowns Ezra flagged

- Security constraints (private organizational documents; not SaaS)
- Document formats actually available (machine-readable vs. PDFs
  needing OCR)
- Whether the agent generates full drafts or mostly reviews/advises
  (his guidance assumes review/advise; full drafting is harder)
- How much human curation time we can spend on the first 20-50
  packets (this is the bottleneck for quality)

### Updated "what's needed to evaluate this seriously"

Replaces the earlier list:

- [ ] Confirm corpus accessibility: are past proposals + solicitations
      + panel reviews all in retrievable form? PDFs needing OCR, or
      already text? Where do panel reviews live?
- [ ] Pick **5-10 proposals** for the eval set (not 3-5) — wins +
      losses, mix of agencies/programs, mix of years.
- [ ] Identify a human curator who can spend ~1 hour per packet on
      lesson-card review for the first batch.
- [ ] Decide: review/advise only, or full-draft generation? (Affects
      model choice + risk profile.)
- [ ] Verify Claude Sonnet long-context handles 15-page proposal +
      solicitation + reviews + corpus excerpts in one window
      reliably.
- [ ] Pilot diagram captioning on 2-3 proposals with figures — does
      Gemini vision produce useful summaries or does it need
      hand-tuning?

## Open questions

- Should this be a skill on docs-and-transcripts-agent or a separate
  agent? Probably skill — proposal craft fits docs-domain expertise.
- Is there a version of this that's useful for **other people's
  proposals** (peer-review obligations, manuscript reviews)? Likely
  yes; same primitives.
- Could the same primitives power a "Confluence page evolution"
  analyzer for internal documentation? Yes; lower-stakes test bed.
- Is panel-review text actually capturable in usable form? Many panels
  return PDFs or web portals; ingestion may be the bottleneck.
