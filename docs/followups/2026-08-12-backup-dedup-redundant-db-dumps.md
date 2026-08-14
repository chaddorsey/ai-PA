# Follow-up: De-duplicate the nightly backup (~1.3 TB win)

**Date:** 2026-08-12
**Priority:** Medium (cost/efficiency, not correctness — backups are complete and recoverable today)
**Owner:** unassigned
**Origin:** surfaced while verifying backup health before the multi-surface-continuity M1 work.

## Problem

Each nightly `pa-ecosystem-backup` is **~129 GB**, and the `supabase-db` Postgres instance is captured **three different ways** in every run:

| # | What | Approx size | Source |
|---|------|-------------|--------|
| 1 | `pg_dumpall` — all databases, cluster-wide | **57 G** | `deployment/scripts/backup.sh:748` |
| 2 | Individual `pg_dump` per database (`letta` alone ≈ **49 G**, + litellm/scheduler/n8n/curator) | **~50 G** | `deployment/scripts/backup.sh:193` |
| 3 | Physical `ai-pa_supabase_db` **volume** tar (the raw data dir) | **18 G** | `deployment/scripts/backup.sh:225` |

**#2 is fully redundant with #1** — the per-database dumps re-dump databases that `pg_dumpall` already contains (same instance, same data). The standalone 49 GB `letta` dump is the dominant waste.

At the current retention (26 backups; policy `daily<14d | weekly<60d | monthly<12mo` via `deployment/scripts/retention-backup.py`; ~3.0 TB total), the redundant per-DB dumps cost **~50 GB/day ≈ ~1.3 TB** across the retention window.

## Fix options (pick one)

1. **Drop the individual per-DB dumps, keep `pg_dumpall`.** Simplest. `pg_dumpall` restores the whole cluster; granular single-DB restore is still possible from the cluster dump (extract one DB, or `pg_restore` selectively if switched to custom format). Cuts ~40% off every backup.
2. **Invert:** keep individual `pg_dump` (custom/`-Fc` format for selective restore), drop `pg_dumpall`. Keeps granular restore ergonomics; loses roles/globals unless `pg_dumpall --globals-only` is added (small).
3. **Reconsider #3 vs the logical dumps.** The physical volume tar overlaps the logical dumps but has a weak justification (faster full-instance restore than replaying a 57 GB SQL dump). Keep it *or* the cluster dump, not necessarily both — evaluate restore-time vs. space.

**Recommended:** Option 1 (drop redundant per-DB dumps) + keep `pg_dumpall` + keep the physical volume tar for fast full restore. Re-evaluate whether both logical *and* physical are needed once sizes are re-measured.

## Guardrails
- Do **not** change backup config immediately before relying on a restore (e.g. right before the M1 cutover). Change, then verify a full backup + a test restore before the next risky operation.
- After trimming, confirm a restore drill still works end-to-end (esp. the `letta` DB, 49 G, and roles/globals).

## Also noted while checking (separate, smaller)
- **Aug 11 backup failed cleanly** (empty dir left behind): the run fired late (~11:24, machine likely asleep at 02:00) and `backup.sh` aborted because **Docker was not running**. Self-recovered Aug 12. Consider: (a) retry/skip-and-alert when Docker is down rather than leaving an empty dir, (b) alert on empty/undersized backups, (c) pre-create the missing `deployment/logs/` dir (a `tee` error was logged).
- Stale empty `pa-ecosystem-backup-20260811_020000/` dir can be removed.
- Dedicated `local-mode-snapshots/` are stale (newest 2026-06-03), but `lc-local-backend` is captured daily inside the main backup (`local_mode_state/lc-local-backend-core`), so this is not a data gap.
