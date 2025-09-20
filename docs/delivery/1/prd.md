# PBI-1: Database Consolidation - Unified PostgreSQL Instance

[View in Backlog](../backlog.md#user-content-1)

## Overview

Consolidate all PostgreSQL databases (Supabase system, n8n_restore, Letta, and RAG storage) into a unified Supabase PostgreSQL instance to simplify backup, monitoring, and maintenance procedures while ensuring all applications maintain their required functionality and performance.

## Problem Statement

The current system operates multiple PostgreSQL instances:
- Supabase PostgreSQL for system services
- Separate Letta PostgreSQL for AI agents and embeddings  
- n8n_restore database for workflow automation
- Future RAG document storage requirements

This fragmentation leads to:
- Complex backup procedures across multiple databases
- Increased resource overhead from multiple PostgreSQL instances
- Complicated monitoring and maintenance workflows
- Risk of configuration drift between database instances

## User Stories

### Primary User Story
**As a System Administrator**, I want to consolidate all PostgreSQL databases into a unified Supabase instance so that I can manage data more efficiently and reduce resource overhead.

### Supporting User Stories
- **As a Backup Administrator**, I want a single database instance to backup so that I can ensure comprehensive data protection with simpler procedures
- **As a Database Administrator**, I want unified schema management so that I can maintain consistency and apply optimizations across all data
- **As a DevOps Engineer**, I want reduced infrastructure complexity so that monitoring and troubleshooting are streamlined

## Technical Approach

### Database Architecture
```sql
-- Unified PostgreSQL Database Structure
-- Database: postgres (Supabase system + unified schemas)

-- Schema isolation for different applications
CREATE SCHEMA IF NOT EXISTS n8n;
CREATE SCHEMA IF NOT EXISTS letta_agents;
CREATE SCHEMA IF NOT EXISTS letta_embeddings;  
CREATE SCHEMA IF NOT EXISTS rag_documents;
CREATE SCHEMA IF NOT EXISTS rag_embeddings;

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector; -- pgvector for Letta and RAG
```

### Migration Strategy
1. **Pre-Migration Assessment**
   - Document current database schemas and sizes
   - Identify dependencies and connection patterns
   - Create comprehensive backup of existing databases

2. **Schema Migration**
   - Create isolated schemas in unified PostgreSQL instance
   - Migrate n8n database to `n8n` schema
   - Migrate Letta data to `letta_agents` and `letta_embeddings` schemas
   - Prepare `rag_documents` and `rag_embeddings` schemas for future use

3. **Application Configuration Updates**
   - Update Letta configuration to use new database connection
   - Update n8n configuration to use new schema
   - Update connection strings and environment variables

4. **Validation and Cutover**
   - Validate data integrity post-migration
   - Test all application functionality
   - Update backup procedures
   - Decommission old database instances

### Performance Considerations
- Maintain separate schemas to prevent cross-application interference
- Optimize connection pooling for multiple applications
- Monitor query performance during and after migration
- Implement appropriate indexing strategies per schema

## UX/UI Considerations

### Administrative Interface
- Database administration through Supabase interface
- Schema-based access control for different application data
- Unified monitoring dashboards for all schemas

### Application Impact
- **Transparent to End Users**: No visible changes to application functionality
- **Administrative Efficiency**: Single interface for database management
- **Monitoring Simplification**: Unified view of all database activity

## Acceptance Criteria

### Functional Requirements
- [ ] All applications (n8n, Letta, future RAG) connect to unified PostgreSQL instance
- [ ] Data migrated completely with 100% integrity verification
- [ ] All existing functionality preserved across applications
- [ ] Schema isolation prevents cross-application data access
- [ ] Performance equivalent to or better than current setup

### Non-Functional Requirements  
- [ ] Migration completes within 4-hour maintenance window
- [ ] Database startup time remains under 30 seconds
- [ ] Query performance maintained within 10% of baseline
- [ ] Memory usage optimized compared to multiple instance setup
- [ ] Backup procedures unified and simplified

### Operational Requirements
- [ ] Migration scripts documented and tested
- [ ] Rollback procedures validated
- [ ] Connection string updates documented
- [ ] Monitoring configured for unified instance
- [ ] Access controls implemented per schema

## Dependencies

### Technical Dependencies
- Supabase PostgreSQL instance with pgvector extension
- Access to existing database instances for migration
- Application configuration management capabilities
- Database migration tools and scripts

### Process Dependencies
- **Upstream**: None (foundational PBI)
- **Downstream**: 
  - PBI-2 (Docker Compose Unification) - depends on database configuration
  - PBI-13 (RAG Infrastructure) - depends on RAG schema preparation
  - PBI-14 (RAG Database Integration) - depends on unified database

### Risk Dependencies
- Comprehensive backup procedures before migration
- Testing environment to validate migration process
- Coordination with application teams for configuration updates

## Open Questions

1. **Connection Pooling**: Should we implement PgBouncer for connection optimization across multiple applications?
2. **Schema Permissions**: What level of cross-schema access should be permitted for administrative functions?
3. **Backup Strategy**: Should schema-level backups be implemented in addition to full database backups?
4. **Performance Monitoring**: What additional metrics should be tracked post-consolidation?
5. **Migration Timing**: Should migration be performed during a planned maintenance window or incrementally?

## Related Tasks

Tasks for this PBI will be defined in [tasks.md](./tasks.md) following the implementation approach:

1. **Database Assessment and Planning**
2. **Schema Design and Creation** 
3. **Migration Script Development**
4. **Application Configuration Updates**
5. **Data Migration Execution**
6. **Validation and Testing**
7. **Backup Procedure Updates**
8. **Documentation and Handover**

---

**Back to**: [Project Backlog](../backlog.md)
