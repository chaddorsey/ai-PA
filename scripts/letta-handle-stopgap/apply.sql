-- Letta handle stopgap (Path A) — INSERT mirror rows
-- Mirrors openai-proxy/X handles into litellm/X so existing agent llm_configs resolve.
-- Idempotent: skips rows that already exist.
-- Reversible: rollback.sql removes only rows we added.
--
-- Tag in display_name: "[stopgap-3205]" for filtering on rollback.

BEGIN;

-- Pin the openai-proxy BYOK provider id (verified: provider-17a0ebb6...)
WITH proxy AS (
  SELECT id FROM providers WHERE name = 'openai-proxy' LIMIT 1
)
INSERT INTO provider_models (
  id, handle, display_name, name, provider_id, organization_id,
  model_type, enabled, model_endpoint_type, max_context_window,
  supports_token_streaming, supports_tool_calling, embedding_dim,
  is_deleted, created_at, updated_at
)
SELECT
  'pmodel-stopgap-' || replace(replace(replace(pm.handle, 'openai-proxy/', ''), '/', '-'), '.', '-'),
  'litellm/' || replace(pm.handle, 'openai-proxy/', '') AS handle_new,
  pm.display_name || ' [stopgap-3205]' AS display_name,
  pm.name,
  proxy.id,
  pm.organization_id,
  pm.model_type,
  pm.enabled,
  pm.model_endpoint_type,
  pm.max_context_window,
  pm.supports_token_streaming,
  pm.supports_tool_calling,
  pm.embedding_dim,
  false,
  now(), now()
FROM provider_models pm
CROSS JOIN proxy
WHERE pm.provider_id = proxy.id
  AND pm.handle LIKE 'openai-proxy/%'
  AND pm.is_deleted = false
  AND NOT EXISTS (
    SELECT 1 FROM provider_models pm2
    WHERE pm2.handle = 'litellm/' || replace(pm.handle, 'openai-proxy/', '')
      AND pm2.is_deleted = false
  )
ON CONFLICT ON CONSTRAINT unique_handle_per_org_and_type DO NOTHING;

-- Show what we inserted
SELECT count(*) AS inserted_rows, array_agg(handle ORDER BY handle) AS handles
FROM provider_models
WHERE display_name LIKE '%[stopgap-3205]%' AND is_deleted = false;

COMMIT;
