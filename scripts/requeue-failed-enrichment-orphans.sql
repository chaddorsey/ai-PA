-- Requeue tasks whose enrichment FAILED during the 2026-07/08 wedge but are
-- still live (extracted, not rejected/closed). Idempotent: re-running only
-- re-selects rows currently in the failed+extracted state.
-- Run: PGPASSWORD=... /opt/homebrew/opt/libpq/bin/psql -h 127.0.0.1 -p 5433 \
--        -U postgres -d postgres -f scripts/requeue-failed-enrichment-orphans.sql
UPDATE pa_web.tasks
   SET enrichment_state = 'pending',
       enrichment       = (COALESCE(enrichment, '{}'::jsonb) - 'retry_count'),
       updated_at       = NOW()
 WHERE enrichment_state = 'failed'
   AND status           = 'extracted'
   AND closed_at IS NULL
 RETURNING ref_id, source;
