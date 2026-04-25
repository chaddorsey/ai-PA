-- Letta handle stopgap (Path A) — ROLLBACK
-- Removes only rows tagged with "[stopgap-3205]" in display_name.
-- Hard-deletes (not soft-delete) since these were synthetic.

BEGIN;

DELETE FROM provider_models
WHERE display_name LIKE '%[stopgap-3205]%';

-- Verify
SELECT count(*) AS remaining_stopgap_rows
FROM provider_models
WHERE display_name LIKE '%[stopgap-3205]%';

COMMIT;
