-- Letta handle stopgap (Path A) — verification
-- Run after apply.sql to confirm rows landed and resolve cleanly.

\echo '=== Stopgap rows present ==='
SELECT count(*) AS active, count(*) FILTER (WHERE is_deleted = true) AS soft_deleted
FROM provider_models
WHERE display_name LIKE '%[stopgap-3205]%';

\echo ''
\echo '=== Sample stopgap handles ==='
SELECT handle, display_name, model_endpoint_type, max_context_window
FROM provider_models
WHERE display_name LIKE '%[stopgap-3205]%' AND is_deleted = false
ORDER BY handle
LIMIT 10;

\echo ''
\echo '=== Cross-check: each litellm/X has matching openai-proxy/X parent ==='
SELECT
  count(*) FILTER (WHERE litellm_count > 0 AND proxy_count > 0) AS paired,
  count(*) FILTER (WHERE litellm_count > 0 AND proxy_count = 0) AS orphan_litellm,
  count(*) FILTER (WHERE litellm_count = 0 AND proxy_count > 0) AS unmirrored_proxy
FROM (
  SELECT
    replace(handle, 'litellm/', '') AS shortname,
    sum(CASE WHEN handle LIKE 'litellm/%' THEN 1 ELSE 0 END) AS litellm_count,
    sum(CASE WHEN handle LIKE 'openai-proxy/%' THEN 1 ELSE 0 END) AS proxy_count
  FROM provider_models
  WHERE (handle LIKE 'litellm/%' OR handle LIKE 'openai-proxy/%')
    AND is_deleted = false
  GROUP BY shortname
) t;
