# Wildlife classification spike

Quick experiment to measure how accurately a VLM (Claude / GPT-4o /
Gemini) can identify wildlife species from fox-cam-style clips, before
we commit to building it as a real curator feature.

## Setup

1. **Pick clips** from Synology Surveillance Station that span a
   representative mix of cases:
   - 5–10 confirmed foxes (day + night, different distances)
   - 3–5 neighbor's dog or other domestic dog
   - 2–3 cats if any
   - 2–3 raccoons
   - 2–3 deer (if applicable)
   - 3–5 people walking past
   - 3–5 ambiguous cases (you couldn't tell at a glance — the hard ones)
   - 2–3 false positives (motion that triggered nothing identifiable)

   Aim for 25–35 clips total. More is better but cost grows linearly.

2. **Organize by ground truth** — make subdirectories named after the
   truth and put the MP4s in:

   ```
   clips/
     fox/
       2026-05-01-evening-den.mp4
       2026-05-02-night-yard.mp4
       ...
     dog/
       2026-05-02-neighbor-walking.mp4
       ...
     person/
       2026-05-01-mail-carrier.mp4
       ...
     ambiguous/
       2026-05-03-shadow-or-fox.mp4
       ...
   ```

   Recognized subdirectory names: `fox`, `dog`, `cat`, `raccoon`,
   `deer`, `person`, `ambiguous`, `none` (false positives, empty
   frames). Anything else is skipped with a warning.

3. **Choose a provider** based on what you want to test. All three are
   set up and ready:
   - `claude` (default, model: claude-haiku-4-5) — Anthropic
   - `openai` (model: gpt-4o-mini) — OpenAI
   - `gemini` (model: gemini-2.0-flash) — Google

   Roughly comparable pricing for the small models. Run multiple
   providers if you want to compare; the script's idempotent on
   frame extraction so the second run only pays for VLM calls.

## Run

From the repo root:

```bash
# Source the .env so API keys are loaded
set -a && source .env && set +a

# Dry run first — just extracts frames, no VLM calls
poetry run python scripts/classify-spike/classify_spike.py \
    --input-dir ./clips \
    --output-dir ./scripts/classify-spike/out \
    --frames 5 \
    --dry-run

# Real run with Claude
poetry run python scripts/classify-spike/classify_spike.py \
    --input-dir ./clips \
    --output-dir ./scripts/classify-spike/out \
    --provider claude \
    --frames 5

# Optional: re-run with another provider for comparison
poetry run python scripts/classify-spike/classify_spike.py \
    --input-dir ./clips \
    --output-dir ./scripts/classify-spike/out-openai \
    --provider openai \
    --frames 5
```

Frames are extracted to `out/frames/` and reused on subsequent runs;
only the VLM calls happen each time you re-run.

## What you get

- **`out/spike-results.csv`** — one row per clip with the aggregated verdict
  (`clip, ground_truth, predicted_species, predicted_confidence,
   correct, aggregation_note`).
- **`out/spike-frames.csv`** — one row per frame with the raw VLM response
  (`clip, ground_truth, frame, species, confidence, error,
   raw_response`).
- **Confusion matrix printed to stdout** — `truth\pred` table plus
  overall accuracy.

## Reading the results

Things to look for:

- **Overall accuracy**. >85% means VLMs are probably good enough; build Track 1.
  70–85% means we need better frame selection (cropping, more frames),
  or a hybrid (cloud VLM for high-confidence filter, family vote for
  rest). <70% means skip the cloud VLM path and look at local
  detectors (MegaDetector / SpeciesNet).
- **Where the errors cluster**. If foxes get classified as dogs ~30%
  of the time but dogs are nearly always right, the model has trouble
  with the specific fox-vs-dog disambiguation — adding more features
  to the prompt might help.
- **Confidence calibration**. Look at `out/spike-frames.csv` — are
  high-confidence predictions usually correct? If "high" confidence is
  90%+ accurate but "low" is ~50%, we have a usable signal: trust
  high, surface low for human review.
- **Day vs night**. Tag clips with this in their filenames if helpful
  (e.g., `night-` prefix); we expect night accuracy to be much lower.

## Cost ballpark

5 frames per clip × ~600-token prompt × 30 clips:

| Provider | Model | Approx cost |
|---|---|---|
| Claude | haiku-4-5 | $0.30–0.60 |
| OpenAI | gpt-4o-mini | $0.10–0.30 |
| Gemini | 2.0-flash | $0.05–0.15 |

Actual cost is printed in API responses' usage info if you want exact
numbers — easy to add to the script if useful.

## After running

Once you have results, the next decision is one of:

- **Build Track 1 with this provider + prompt** if accuracy is good.
- **Iterate on prompt + frame strategy** if accuracy is borderline.
- **Pivot to local model** (MegaDetector via CPU, or SpeciesNet) if
  the cloud route doesn't clear the bar.

The script is intentionally throwaway — once we know the answer, we
either lift the classifier code into the curator (Track 1) or delete
this directory.
