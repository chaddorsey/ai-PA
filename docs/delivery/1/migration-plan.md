# Database Migration Plan - Letta to Unified PostgreSQL

## Executive Summary

**Migration Type**: Configuration-only (no data migration required)  
**Complexity**: Minimal  
**Risk Level**: Low  
**Estimated Downtime**: < 5 minutes  

## Current vs Target Configuration

### Current Configuration
```yaml
letta:
  environment:
    LETTA_PG_HOST: pgvector_db  # Points to separate letta_db container
    LETTA_PG_DB: letta
    LETTA_PG_USER: letta
    LETTA_PG_PASSWORD: letta
```

### Target Configuration
```yaml
letta:
  environment:
    LETTA_PG_HOST: supabase-db  # Points to unified database
    LETTA_PG_DB: postgres
    LETTA_PG_USER: postgres
    LETTA_PG_PASSWORD: ${POSTGRES_PASSWORD}
    LETTA_PG_SCHEMA: letta_agents  # Optional: specify default schema
```

## Migration Steps

### Phase 1: Preparation (0 minutes - already completed)
- [x] ✅ Verify Letta database is empty (confirmed)
- [x] ✅ Install pgvector extension in supabase-db (completed)
- [x] ✅ Create schema structure in supabase-db (completed)

### Phase 2: Configuration Update (5 minutes)

#### Step 1: Update Docker Compose Configuration
```bash
# Edit docker-compose.yml
# Change LETTA_PG_HOST from pgvector_db to supabase-db
# Change LETTA_PG_DB from letta to postgres
# Change LETTA_PG_USER from letta to postgres
# Update LETTA_PG_PASSWORD to use ${POSTGRES_PASSWORD}
```

#### Step 2: Test Configuration
```bash
# Stop Letta service
docker compose stop letta

# Start Letta with new configuration  
docker compose up letta -d

# Verify health
docker logs ai-pa-letta-1 --tail 20
curl http://localhost:8283/v1/health/
```

#### Step 3: Validate Database Connection
```sql
-- Connect to unified database and verify Letta tables are created
docker exec supabase-db psql -U postgres -d postgres -c "
\dt letta_agents.*;
\dt letta_embeddings.*;
SELECT COUNT(*) as letta_tables_created FROM information_schema.tables 
WHERE table_schema IN ('letta_agents', 'letta_embeddings');
"
```

### Phase 3: Cleanup (2 minutes)

#### Step 1: Remove Legacy Database Service
```yaml
# Remove from docker-compose.yml:
# - letta_db service definition
# - Associated volume mounts
# - pgvector_db network alias
```

#### Step 2: Clean Up Volumes
```bash
# Optional: Remove unused letta database volume
docker volume rm ai-pa_letta_db_data  # Or similar volume name
```

## Rollback Procedures

### Quick Rollback (< 2 minutes)
If issues are detected immediately:

```bash
# 1. Stop Letta service
docker compose stop letta

# 2. Revert docker-compose.yml changes
git checkout docker-compose.yml

# 3. Restart Letta with original configuration
docker compose up letta -d
```

### Full Rollback (< 5 minutes)
If issues are detected later:

```bash
# 1. Restore original docker-compose.yml
git checkout docker-compose.yml

# 2. Restart all services to ensure clean state
docker compose down
docker compose up -d

# 3. Verify Letta functionality
curl http://localhost:8283/v1/health/
```

## Validation Procedures

### Pre-Migration Validation
- [x] ✅ Confirm Letta database is empty
- [x] ✅ Confirm supabase-db is healthy and accessible
- [x] ✅ Confirm pgvector extension installed
- [x] ✅ Confirm schema structure created

### Post-Migration Validation
- [ ] Letta service starts successfully
- [ ] Letta health endpoint responds
- [ ] Letta creates tables in correct schemas
- [ ] Letta can perform basic operations (create agent, etc.)
- [ ] No errors in Letta logs
- [ ] Other services (n8n, Supabase) unaffected

### Success Criteria
1. ✅ Letta service healthy and responsive
2. ✅ Letta tables created in `letta_agents` and `letta_embeddings` schemas
3. ✅ All Letta functionality preserved
4. ✅ No impact on existing services (n8n, Supabase)
5. ✅ Unified database approach implemented

## Risk Mitigation

### Identified Risks
1. **Configuration Error**: Wrong connection parameters
   - **Mitigation**: Validate each parameter before restart
   - **Detection**: Health check failure
   - **Response**: Quick rollback procedure

2. **Permission Issues**: Letta can't access postgres database
   - **Mitigation**: Test connection manually before Letta restart
   - **Detection**: Connection errors in logs
   - **Response**: Grant necessary permissions or rollback

3. **Schema Conflicts**: Existing objects conflict with Letta
   - **Mitigation**: Used isolated schemas (letta_agents, letta_embeddings)
   - **Detection**: SQL errors during table creation
   - **Response**: Clear schemas and retry or rollback

### Contingency Planning
- Rollback procedures tested and documented
- Configuration changes tracked in git for easy reversion
- Health monitoring in place for immediate issue detection

## Timeline

| Step | Duration | Description |
|------|----------|-------------|
| Preparation | 0 min | ✅ Already completed |
| Config Update | 3 min | Edit docker-compose.yml, restart Letta |
| Validation | 2 min | Verify health and functionality |
| Cleanup | 2 min | Remove legacy service definition |
| **Total** | **7 min** | Complete migration process |

## Dependencies

### Technical Dependencies
- [x] ✅ Supabase PostgreSQL operational
- [x] ✅ pgvector extension installed
- [x] ✅ Schema structure created
- [ ] Docker Compose configuration access
- [ ] Ability to restart Letta service

### Process Dependencies
- Coordination with any active Letta users (minimal - system is in development)
- Backup of current docker-compose.yml before changes

---

**Migration Plan Prepared**: 2025-09-20  
**Ready for Execution**: ✅ Yes  
**Next Step**: Update docker-compose.yml configuration
