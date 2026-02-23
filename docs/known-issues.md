# Known Issues

Operational issues discovered during other work. Address when convenient.

---

## supabase-auth: fatal migration error

**Discovered:** 2026-02-20 (while adding restart policies)
**Impact:** Auth service crash-loops on restart. No features currently depend on Supabase Auth.
**Error:** `pq: type "auth.factor_type" does not exist` during GoTrue migration.
**Root cause:** Database schema is missing the `auth.factor_type` enum that the GoTrue migration expects.
**Fix direction:** Either create the missing enum manually or align the GoTrue version with the existing schema.

## supabase-realtime: unbound variable in startup script

**Discovered:** 2026-02-20 (while adding restart policies)
**Impact:** Realtime service crash-loops on restart. No features currently use Supabase Realtime.
**Error:** `run.sh: line 5: RLIMIT_NOFILE: unbound variable`
**Root cause:** The `run.sh` entrypoint references `RLIMIT_NOFILE` without a default, and the env var isn't set.
**Fix direction:** Set `RLIMIT_NOFILE` in docker-compose.yml environment, or patch the entrypoint script.
