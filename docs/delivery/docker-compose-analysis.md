# Docker Compose Files Analysis - Integration Status

## Executive Summary

The main `docker-compose.yml` already contains **most critical services** with some integration inconsistencies. Several individual compose files can be **deprecated or significantly de-emphasized** in the roadmap to avoid confusion during development.

## File Inventory & Status

### 📋 **Primary Configuration**
- **`/docker-compose.yml`** - ✅ **MAIN FILE** - Contains 90% of required services

### 🔍 **Secondary Compose Files Analysis**

#### 1. **`/gmail-mcp/docker-compose.yml`** - ⚠️ **REDUNDANT - CAN BE DEPRECATED**

**Status**: Already integrated in main compose but with differences

**Main Compose Integration**:
```yaml
gmail:
  build:
    context: ./gmail-mcp
  ports: ["7331:7331"]
  volumes:
    - mcp-gmail:/gmail-server
    - ./gmail-mcp/gcp-oauth.keys.json:/gcp-oauth.keys.json:ro
```

**Standalone Version**:
```yaml
gmail-mcp:
  build: { context: . }
  ports: ["8331:7331"]  # Different external port
  volumes:
    - ./gcp-oauth.keys.json:/root/.gmail-mcp/gcp-oauth.keys.json:ro  # Different path
```

**🎯 Recommendation**: **DEPRECATE** - Main compose has Gmail MCP integrated. Minor path differences to resolve.

---

#### 2. **`/graphiti/mcp_server/docker-compose.yml`** - ⚠️ **REDUNDANT - CAN BE DEPRECATED**

**Status**: Already integrated in main compose with differences

**Main Compose Integration**:
```yaml
neo4j:
  image: neo4j:5.26
  environment: ["NEO4J_AUTH=neo4j/demodemo"]
  
graphiti-mcp:
  build: { context: /Users/chaddorsey/dev/ai-PA/graphiti/mcp_server }
  ports: ["8800:8000"]
  environment:
    NEO4J_URI: bolt://neo4j:7687
    NEO4J_PASSWORD: demodemo
```

**Standalone Version**:
```yaml
neo4j:
  image: neo4j:5.26.0  # Slightly newer
  environment: ["NEO4J_AUTH=${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:-demodemo}"]
  
graphiti-mcp:
  image: zepai/knowledge-graph-mcp:latest  # Uses pre-built image
  ports: ["8000:8000"]  # Different port mapping
```

**🎯 Recommendation**: **DEPRECATE** - Main compose has Graphiti MCP integrated. Use main version with env var improvements from standalone.

---

#### 3. **`/graphiti/docker-compose.yml`** - ❌ **OBSOLETE - CAN BE IGNORED**

**Status**: Generic Graphiti service (not MCP server)

**Purpose**: Standalone Graphiti graph service, not the MCP server
- Runs generic graph service on port 8000
- No MCP server functionality
- Different service entirely from what we need

**🎯 Recommendation**: **IGNORE** - Not relevant to PA ecosystem. This is for standalone Graphiti usage.

---

#### 4. **`/graphiti/docker-compose.test.yml`** - ❌ **TEST ONLY - CAN BE IGNORED**

**Status**: Testing configuration only

**Purpose**: CI/CD testing configuration
- Uses versioned image tags (`${GITHUB_SHA}`)
- Different Neo4j version for testing
- Not relevant to production deployment

**🎯 Recommendation**: **IGNORE** - Testing infrastructure only.

---

## 🚨 **Key Integration Issues in Main Compose**

### 1. **Network Fragmentation**
```yaml
# Mixed network usage - needs unification
networks: [default]  # Some services
networks: [app-tier] # Other services (slack-mcp-server)
```

### 2. **Database Fragmentation** 
```yaml
# Multiple PostgreSQL instances
supabase-db:     # Main Supabase PostgreSQL
letta_db:        # Separate Letta PostgreSQL (should be consolidated)
```

### 3. **Service Discovery Issues**
- Hardcoded build context paths (absolute paths)
- Mixed service naming conventions
- Some services missing health checks

### 4. **Configuration Inconsistencies**
- Gmail MCP has different volume paths than standalone
- Graphiti MCP uses hardcoded passwords vs env vars
- Missing standardized MCP server patterns

---

## 📋 **Roadmap Simplification Recommendations**

### ✅ **Services Confirmed Integrated in Main Compose**
1. **Supabase Stack** - Complete (supabase-db, supabase-rest, supabase-auth, etc.)
2. **n8n Workflow Automation** - ✅ Integrated
3. **Letta AI Framework** - ✅ Integrated (but separate DB to consolidate)
4. **Neo4j + Graphiti MCP** - ✅ Integrated
5. **Gmail MCP Server** - ✅ Integrated (minor config differences)
6. **Slack MCP Server** - ✅ Integrated 
7. **Open WebUI** - ✅ Integrated
8. **Cloudflare Tunnel** - ✅ Integrated

### ⚠️ **Missing from Main Compose**
1. **HayHooks/RAG Infrastructure** - Not yet added (planned in PBI-13)
2. **Monitoring Stack** - Prometheus/Grafana mentioned in PRD but not implemented
3. **Backup Services** - Not yet configured

### 🗑️ **Files to Deprecate/Ignore in Roadmap**

#### **DEPRECATE** (mention once, then ignore):
- `gmail-mcp/docker-compose.yml` - Superseded by main compose
- `graphiti/mcp_server/docker-compose.yml` - Superseded by main compose

#### **IGNORE** (don't mention in roadmap):
- `graphiti/docker-compose.yml` - Not MCP server, different purpose
- `graphiti/docker-compose.test.yml` - Testing only

---

## 🎯 **Development Process Recommendations**

### 1. **Focus Exclusively on Main Compose**
- All PBI development should reference `/docker-compose.yml`
- Individual compose files should not be mentioned in task planning
- Use individual compose files only for reference during migration

### 2. **PBI Priority Adjustments**

#### **PBI-1 (Database Consolidation)** - Adjust scope:
- Focus on consolidating `letta_db` into `supabase-db`
- Individual compose files already reference same databases

#### **PBI-4 (MCP Standardization)** - Simplified scope:
- Gmail MCP already integrated (fix minor config differences)
- Graphiti MCP already integrated (standardize env vars)
- Focus on standardizing configuration patterns

### 3. **Avoid Development Confusion**
- Don't create migration tasks for already-integrated services
- Focus on configuration standardization rather than service integration
- Emphasize unification of existing integrated services

---

## 📈 **Updated Integration Status**

| Service | Main Compose | Individual Compose | Status | Action |
|---------|-------------|-------------------|--------|--------|
| Supabase Stack | ✅ Complete | N/A | ✅ Done | None |
| n8n | ✅ Complete | N/A | ✅ Done | None |
| Letta | ✅ Integrated | N/A | ⚠️ Separate DB | Consolidate DB |
| Neo4j + Graphiti MCP | ✅ Integrated | ⚠️ Redundant | ✅ Done | Standardize config |
| Gmail MCP | ✅ Integrated | ⚠️ Redundant | ✅ Done | Fix minor paths |
| Slack MCP | ✅ Integrated | N/A | ✅ Done | None |
| Open WebUI | ✅ Complete | N/A | ✅ Done | None |
| Cloudflare | ✅ Complete | N/A | ✅ Done | None |
| **RAG Infrastructure** | ❌ Missing | N/A | 🚧 TODO | PBI-13 |
| **Monitoring** | ❌ Missing | N/A | 🚧 TODO | PBI-6/10 |

**🎯 Result**: Main compose is **90% complete**. Individual compose files can be largely ignored in development roadmap.

---

*Analysis Date: 2025-09-20*
*Recommendation: Focus development exclusively on main docker-compose.yml to avoid confusion.*
