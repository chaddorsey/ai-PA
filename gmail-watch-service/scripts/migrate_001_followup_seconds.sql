BEGIN;
ALTER TABLE gmail_watch.watched_threads
    ADD COLUMN IF NOT EXISTS followup_seconds INTEGER,
    ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS bcc_address VARCHAR(255);
UPDATE gmail_watch.watched_threads
SET followup_seconds = followup_days * 86400
WHERE followup_days IS NOT NULL AND followup_seconds IS NULL;
ALTER TABLE gmail_watch.watched_threads
    DROP COLUMN IF EXISTS followup_days;
DROP INDEX IF EXISTS gmail_watch.idx_watched_threads_followup;
CREATE INDEX IF NOT EXISTS idx_watched_threads_followup
    ON gmail_watch.watched_threads(followup_due_at)
    WHERE is_active = TRUE AND followup_seconds IS NOT NULL AND NOT followup_notified;
COMMIT;
