# AI Personal Assistant Ecosystem Unification - Product Requirements Document

## Executive Summary

This PRD outlines the transformation of the current fragmented AI Personal Assistant (PA) ecosystem into a unified, production-ready Docker Compose infrastructure optimized for home server deployment. The initiative consolidates multiple Docker configurations, integrates isolated components, and establishes robust operational practices for a resilient PA system.

## Current Context

### Existing System Overview
The current PA ecosystem consists of multiple interconnected services deployed across fragmented Docker configurations:

- **Core Infrastructure**: Supabase PostgreSQL, Neo4j, multiple MCP servers
- **AI Framework**: Letta agent system with separate database
- **Workflow Engine**: n8n automation platform 
- **UI Layer**: Open WebUI for agent interactions
- **Integration Layer**: Slack MCP, Gmail MCP, Graphiti knowledge graphs
- **External Access**: Cloudflare tunneling for remote connectivity

### Key Pain Points
1. **Fragmented Deployment**: 4+ separate docker-compose files creating operational complexity
2. **Network Isolation**: Components communicate via external networking instead of internal service discovery
3. **Database Redundancy**: Two PostgreSQL instances serving similar purposes
4. **Integration Gaps**: Slackbot operates outside Docker ecosystem
5. **Operational Complexity**: Inconsistent backup, monitoring, and maintenance procedures

### Strategic Value Proposition
- **Operational Efficiency**: Single deployment unit reduces complexity and maintenance overhead
- **Portability**: Unified system enables seamless migration to home server infrastructure
- **Resilience**: Consolidated monitoring, backup, and recovery procedures
- **Scalability**: Foundation for future PA capabilities and integrations

## Requirements

### Functional Requirements

#### FR1: Unified Docker Infrastructure
- **FR1.1**: All PA components must operate within a single Docker Compose configuration
- **FR1.2**: Internal service discovery must replace external network dependencies
- **FR1.3**: Consistent networking model across all services
- **FR1.4**: Standardized environment variable and secrets management

#### FR2: Database Consolidation
- **FR2.1**: Single PostgreSQL instance must support all database requirements
- **FR2.2**: pgvector extension must be available for Letta AI embeddings
- **FR2.3**: Database isolation through schema separation while maintaining shared infrastructure
- **FR2.4**: Unified backup and recovery procedures for all databases

#### FR3: MCP Server Standardization
- **FR3.1**: All MCP servers must follow consistent deployment patterns
- **FR3.2**: Centralized MCP configuration management
- **FR3.3**: Standardized health checks and monitoring for MCP services
- **FR3.4**: Internal service discovery for MCP server communications

#### FR4: Slackbot Integration
- **FR4.1**: Slackbot must be containerized and integrated into main Docker ecosystem
- **FR4.2**: Internal communication with Letta via service discovery
- **FR4.3**: Consistent deployment and lifecycle management with other services

#### FR5: Operational Excellence
- **FR5.1**: Automated backup procedures for all critical data
- **FR5.2**: Centralized logging and monitoring infrastructure
- **FR5.3**: Health checks and service dependency management
- **FR5.4**: Disaster recovery and restore procedures

#### FR6: Framework Upgrade Management
- **FR6.1**: Pinned framework versions with controlled upgrade paths for n8n, Letta, and Graphiti
- **FR6.2**: Automated staging environment for testing framework upgrades before production
- **FR6.3**: Database schema migration validation with automatic rollback capability
- **FR6.4**: Critical workflow validation during framework upgrades

#### FR7: Upgrade Safety Infrastructure
- **FR7.1**: Pre-upgrade compatibility analysis and impact assessment
- **FR7.2**: Automated backup and rollback mechanisms for failed upgrades
- **FR7.3**: Post-upgrade validation with performance monitoring
- **FR7.4**: Version lock management with upgrade audit trail

#### FR8: Extensible RAG Infrastructure
- **FR8.1**: RAG capabilities must integrate through Letta as the central agent core
- **FR8.2**: Document ingestion and semantic search using existing PostgreSQL/pgvector infrastructure
- **FR8.3**: Tool-based RAG access pattern maintaining separation between agent logic and retrieval logic
- **FR8.4**: Modular pipeline architecture supporting multiple document domains and sources

### Non-Functional Requirements

#### Performance Requirements
- **NFR1**: System startup time must not exceed 5 minutes from cold start
- **NFR2**: Inter-service communication latency must be under 100ms within Docker network
- **NFR3**: Database consolidation must not impact query performance beyond 10% baseline

#### Scalability Requirements
- **NFR4**: Architecture must support horizontal scaling of stateless services
- **NFR5**: Database must handle concurrent connections from all services
- **NFR6**: MCP server scaling must be independent and non-disruptive

#### Reliability Requirements
- **NFR7**: System availability target of 99.5% for home server deployment
- **NFR8**: Automated recovery from common failure scenarios
- **NFR9**: Zero data loss backup and recovery procedures
- **NFR10**: Graceful degradation when individual services are unavailable

#### Security Requirements
- **NFR11**: All inter-service communication must occur within private Docker network
- **NFR12**: Secrets and API keys must be managed via secure environment variables
- **NFR13**: External access only via Cloudflare tunnel with appropriate authentication
- **NFR14**: Database access must be restricted to authorized services only

#### Portability Requirements
- **NFR15**: Complete system must be deployable via single command on target home server
- **NFR16**: All dependencies must be containerized with no external system requirements
- **NFR17**: Configuration must be environment-agnostic with parameterized deployment

#### Framework Upgrade Requirements
- **NFR18**: Framework upgrades must complete within 15 minutes including validation
- **NFR19**: Rollback procedures must restore service within 5 minutes
- **NFR20**: Upgrade testing must validate 100% of critical workflows automatically
- **NFR21**: Version compatibility matrix must be maintained and validated

#### RAG Infrastructure Requirements
- **NFR22**: RAG document search queries must complete within 10 seconds for typical queries
- **NFR23**: Document ingestion must support incremental updates without full re-indexing
- **NFR24**: RAG system must handle at least 1000 documents per domain without performance degradation
- **NFR25**: Semantic search accuracy must maintain >80% relevance for domain-specific queries

## Design Decisions

### 1. Database Architecture: Unified PostgreSQL
**Decision**: Consolidate all PostgreSQL databases into single Supabase PostgreSQL instance

**Rationale**:
- Simplified backup and recovery procedures
- Reduced resource overhead and operational complexity
- Consistent database management and monitoring
- Supabase PostgreSQL image supports pgvector extension required by Letta

**Trade-offs Considered**:
- **Isolation**: Database consolidation reduces isolation between services
- **Migration Risk**: Requires careful data migration from Letta database
- **Single Point of Failure**: All services depend on single database instance

**Mitigation Strategies**:
- Schema-level isolation between services
- Comprehensive backup procedures before migration
- Database health monitoring and automated restart policies

### 2. Network Architecture: Single Docker Network
**Decision**: Migrate all services to unified `pa-network` Docker network

**Rationale**:
- Eliminates external network dependencies
- Enables service discovery via container names
- Improved security through network isolation
- Simplified service configuration

**Alternatives Considered**:
- **Multiple Networks**: Separate networks per service type (rejected due to complexity)
- **Host Networking**: Direct host network access (rejected due to security concerns)

### 3. MCP Server Deployment: Unified Pattern
**Decision**: Standardize all MCP servers within main docker-compose.yml

**Rationale**:
- Consistent deployment and lifecycle management
- Simplified service discovery and configuration
- Centralized monitoring and health checks
- Eliminates separate docker-compose files

**Implementation Strategy**:
- Migrate Gmail MCP from separate compose file
- Standardize configuration patterns across all MCP servers
- Implement consistent health check endpoints

### 4. Slackbot Integration: Full Containerization
**Decision**: Containerize Slackbot and integrate into main Docker ecosystem

**Rationale**:
- Eliminates external dependencies and manual deployment
- Enables internal service discovery to Letta
- Consistent lifecycle management with other services
- Simplified development and testing workflows

**Technical Approach**:
- Create Dockerfile for Python Slackbot application
- Update Letta connection to use internal service discovery
- Integrate into main docker-compose.yml with appropriate dependencies

### 5. Framework Version Management: Lean Upgrade Infrastructure
**Decision**: Implement minimal but comprehensive upgrade infrastructure focused on safety and automation

**Rationale**:
- Framework evolution (n8n, Letta, Graphiti) requires reliable upgrade paths
- Manual upgrade processes are error-prone and time-consuming
- Staging validation prevents production issues
- Automated rollback ensures system reliability

**Implementation Strategy**:
- Version pinning with controlled upgrade testing
- Lightweight staging environment for validation
- Essential workflow testing without over-engineering
- Simple rollback mechanisms for upgrade failures

**Trade-offs Considered**:
- **Complexity vs Safety**: Minimal infrastructure that covers critical upgrade scenarios
- **Automation vs Control**: Automated testing with manual approval gates
- **Resource Usage**: Lean staging environment that shares infrastructure efficiently

### 6. RAG Architecture: Tool-Based Integration via HayHooks
**Decision**: Implement RAG capabilities using Haystack/HayHooks with tool-based integration to Letta

**Rationale**:
- Proven integration pattern from existing codebase and Terse Systems methodology
- Tool-based approach maintains separation between agent logic and retrieval logic
- Leverages existing PostgreSQL/pgvector infrastructure for document storage
- Modular pipeline architecture enables gradual expansion of RAG capabilities

**Implementation Strategy**:
- HayHooks as lightweight Haystack REST API server
- Simple 4-component pipelines: embedder → retriever → prompt builder → response
- Tool-based access from Letta maintaining agent-centric architecture
- Domain-specific document stores (AWS docs, technical documentation, personal notes)

**Trade-offs Considered**:
- **Framework Choice**: Haystack vs LangChain vs custom (Haystack chosen for proven integration)
- **Integration Pattern**: Direct embedding vs tool-based (tool-based chosen for modularity)
- **Storage Strategy**: Separate vector DB vs existing PostgreSQL (PostgreSQL chosen for simplicity)
- **Complexity Management**: Monolithic vs modular RAG services (modular chosen for scalability)

## Technical Design

### 1. Core Architecture Overview

```yaml
# Unified Docker Compose Structure
version: "3.9"
services:
  # Database Layer
  supabase-db:           # Unified PostgreSQL with all databases
  
  # AI & Agent Framework
  letta:                 # Agent framework
  graphiti-mcp:          # Knowledge graph MCP server
  
  # Workflow & Automation
  n8n:                   # Workflow engine
  
  # MCP Server Ecosystem
  slack-mcp-server:      # Slack integration
  gmail-mcp:             # Gmail integration
  slackbot:              # Containerized Slack bot
  
  # Infrastructure Services
  cloudflared:           # External access tunnel
  supabase-*:            # Supabase service stack
  
  # Upgrade Infrastructure (Lean)
  version-manager:       # Framework version control and validation
  upgrade-validator:     # Pre/post upgrade testing
  
  # RAG Infrastructure (Lean)
  hayhooks:              # Haystack REST API server for RAG pipelines
  rag-mcp-server:        # MCP server for RAG tool integration
  
  # Monitoring & Operations
  prometheus:            # Metrics collection
  grafana:               # Metrics visualization

networks:
  pa-network:
    name: pa-internal
    driver: bridge
```

### 2. Database Schema Design

```sql
-- Unified PostgreSQL Database Structure
-- Database: postgres (Supabase system)
-- Database: n8n_restore (n8n workflows)
-- Database: letta (AI agents and embeddings)
-- Database: rag_store (RAG document storage and embeddings)

-- Schema isolation within databases
CREATE SCHEMA IF NOT EXISTS n8n;
CREATE SCHEMA IF NOT EXISTS letta_agents;
CREATE SCHEMA IF NOT EXISTS letta_embeddings;
CREATE SCHEMA IF NOT EXISTS rag_documents;
CREATE SCHEMA IF NOT EXISTS rag_embeddings;

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector; -- pgvector for Letta and RAG
```

### 3. Framework Version Management

```yaml
# Version pinning and upgrade infrastructure
services:
  # Framework services with pinned versions
  n8n:
    image: docker.n8n.io/n8nio/n8n:${N8N_VERSION:-1.109.2}
    environment:
      - N8N_UPGRADE_VALIDATION=true
    volumes:
      - ./config/versions.lock:/app/versions.lock:ro
    
  letta:
    image: letta/letta:${LETTA_VERSION:-latest}
    environment:
      - LETTA_VERSION_CHECK=enabled
    
  # Lean upgrade infrastructure
  version-manager:
    build: ./infrastructure/version-manager
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./config/versions.yml:/config/versions.yml
    environment:
      - STAGING_MODE=${UPGRADE_STAGING:-false}
      
  upgrade-validator:
    build: ./infrastructure/upgrade-validator
    profiles: ["upgrade"]  # Only active during upgrades
    volumes:
      - ./tests/workflows:/tests:ro
    environment:
      - VALIDATION_TIMEOUT=300
      
  # Lean RAG infrastructure
  hayhooks:
    build: ./rag-infrastructure/hayhooks
    ports:
      - "1416:1416"
    environment:
      - LETTA_BASE_URL=http://letta:8283
      - POSTGRES_URL=postgres://postgres:${POSTGRES_PASSWORD}@supabase-db:5432/rag_store
      - HAYSTACK_LOGGING_LEVEL=INFO
    volumes:
      - ./rag-infrastructure/pipelines:/app/pipelines
      - ./rag-infrastructure/documents:/app/documents:ro
    networks: [pa-network]
    
  rag-mcp-server:
    build: ./rag-infrastructure/mcp-server
    ports:
      - "8900:8900"
    environment:
      - HAYHOOKS_URL=http://hayhooks:1416
      - MCP_SERVER_NAME=rag-tools
    volumes:
      - ./rag-infrastructure/mcp-config.json:/app/mcp-config.json:ro
    networks: [pa-network]
    depends_on: [hayhooks]
```

### 4. RAG Pipeline Architecture

```python
# Lean RAG pipeline following Terse Systems approach
class DocumentRAGPipeline(BasePipelineWrapper):
    def setup(self) -> None:
        # Simple 4-component pipeline
        text_embedder = SentenceTransformersTextEmbedder(
            model="BAAI/bge-small-en-v1.5"
        )
        retriever = PgvectorEmbeddingRetriever(
            document_store=PgvectorDocumentStore(
                connection_string="postgres://postgres:${PASSWORD}@supabase-db:5432/rag_store"
            )
        )
        prompt_builder = PromptBuilder(
            template="""
            Based on the following documents, answer the question:
            
            Documents:
            {% for doc in documents %}
            {{ doc.content }}
            {% endfor %}
            
            Question: {{ question }}
            Answer:
            """
        )
        llm = OpenAIChatGenerator(model="gpt-4o-mini")
        
        self.pipeline = Pipeline()
        self.pipeline.add_component("embedder", text_embedder)
        self.pipeline.add_component("retriever", retriever)
        self.pipeline.add_component("prompt_builder", prompt_builder)
        self.pipeline.add_component("llm", llm)
        
        # Connect components
        self.pipeline.connect("embedder.embedding", "retriever.query_embedding")
        self.pipeline.connect("retriever", "prompt_builder.documents")
        self.pipeline.connect("prompt_builder", "llm")

    def run_api(self, question: str, domain: str = "general") -> str:
        result = self.pipeline.run({
            "embedder": {"text": question},
            "prompt_builder": {"question": question},
            "retriever": {"filters": {"domain": domain}}
        })
        return result["llm"]["replies"][0].content
```

### 5. Service Discovery Configuration

```yaml
# Example service communication
letta:
  environment:
    - LETTA_PG_HOST=supabase-db
    - LETTA_PG_DATABASE=letta

slackbot:
  environment:
    - LETTA_BASE_URL=http://letta:8283
    
n8n:
  environment:
    - DB_POSTGRESDB_HOST=supabase-db
    
# RAG service integration
rag-mcp-server:
  environment:
    - HAYHOOKS_URL=http://hayhooks:1416
    - LETTA_INTEGRATION_URL=http://letta:8283
```

### 6. Integration Points

#### Letta ↔ RAG System
- Tool-based integration maintaining agent-centric architecture
- RAG queries via MCP server tools (semantic_search, query_documents)
- Response includes source citations and confidence scores
- Domain-specific search capabilities (technical, aws, general)

#### RAG ↔ HayHooks Pipeline
- RESTful API integration for document queries
- Modular pipeline architecture for different document types
- Incremental document indexing via API endpoints
- Performance monitoring and query optimization

#### Letta ↔ Traditional MCP Servers
- Letta connects to MCP servers via internal Docker network
- Configuration managed through centralized MCP config file
- Health check dependencies ensure proper startup order

#### N8N ↔ External Services
- N8N workflows access external APIs via Cloudflare tunnel
- Internal service integrations via Docker network
- Webhook endpoints secured through network policies

#### Slackbot ↔ Letta
- Direct HTTP communication via internal network
- Shared secret authentication for secure communication
- Retry logic and circuit breaker patterns for resilience

## Implementation Plan

### Phase 1: Foundation & Database Consolidation (Weeks 1-2)
1. **Database Migration Preparation**
   - Complete backup verification
   - Install pgvector extension on Supabase PostgreSQL
   - Create target database schemas

2. **Database Consolidation Execution**
   - Migrate Letta data to Supabase PostgreSQL
   - Update Letta configuration
   - Verify data integrity and application functionality

3. **Network Infrastructure Setup**
   - Create unified `pa-network` 
   - Update service configurations for internal networking
   - Test inter-service communication

### Phase 2: Version Management & MCP Standardization (Weeks 3-4)
1. **Lean Upgrade Infrastructure**
   - Create version lock file with current working versions
   - Build minimal version-manager and upgrade-validator services
   - Implement basic staging environment for upgrade testing

2. **RAG Infrastructure Foundation**
   - Deploy HayHooks service with basic document search pipeline
   - Create RAG database schema in unified PostgreSQL
   - Implement simple document ingestion workflow
   - Build RAG MCP server for tool-based integration

3. **Gmail MCP Integration**
   - Migrate Gmail MCP from separate docker-compose
   - Update configuration for unified deployment
   - Test email functionality end-to-end

4. **MCP Configuration Centralization**
   - Standardize MCP server configuration patterns
   - Implement consistent health checks
   - Update Letta MCP client configuration
   - Integrate RAG MCP server into Letta configuration

### Phase 3: Slackbot Integration & Framework Pinning (Weeks 5-6)
1. **Slackbot Containerization**
   - Create Dockerfile for Slackbot application
   - Update service configuration for internal Letta communication
   - Integrate into main docker-compose.yml

2. **Framework Version Control**
   - Pin all framework versions (n8n, Letta, Graphiti)
   - Test upgrade workflow with staging environment
   - Validate rollback procedures

3. **RAG System Testing & Optimization**
   - Test end-to-end RAG workflows through Letta tools
   - Validate document ingestion and search accuracy
   - Optimize embedding and retrieval performance
   - Test domain-specific document search capabilities

4. **End-to-End Workflow Validation**
   - Test complete PA workflows from Slack to knowledge storage
   - Verify n8n automation integrations
   - Validate external access via Cloudflare
   - Test RAG-enhanced agent responses

### Phase 4: Production Hardening & Upgrade Testing (Weeks 7-8)
1. **Monitoring & Observability**
   - Deploy Prometheus and Grafana
   - Configure service health dashboards
   - Implement alerting for critical services

2. **Upgrade Safety Validation**
   - Test complete upgrade workflow (e.g., n8n 1.109.2 → 1.111.0)
   - Validate database migration procedures
   - Test automated rollback capabilities

3. **Security Hardening**
   - Implement proper secrets management
   - Configure network security policies
   - Audit external access points

### Phase 5: Documentation & Deployment Kit (Weeks 9-10)
1. **Home Server Deployment Kit**
   - Create production docker-compose configuration
   - Document deployment procedures
   - Create automated setup scripts

2. **Upgrade Documentation**
   - Document framework upgrade procedures
   - Create upgrade troubleshooting guides
   - Establish version compatibility matrix

3. **Final Validation**
   - End-to-end system testing
   - Performance baseline establishment
   - Complete upgrade workflow validation

## Testing Strategy

### Unit Testing
- Individual service functionality
- Database migration procedures
- Configuration validation

### Integration Testing
- Inter-service communication
- MCP server protocols
- Database operations across services

### Framework Upgrade Testing
- Database schema migration validation
- Critical workflow compatibility testing
- Version rollback verification
- Performance impact assessment

### RAG System Testing
- Document ingestion accuracy and completeness
- Semantic search relevance and precision
- Query response time and performance
- Domain-specific search effectiveness
- Tool integration with Letta agents

### End-to-End Testing
- Complete PA workflows including RAG-enhanced responses
- Framework upgrade scenarios
- Disaster recovery procedures
- Home server deployment validation
- RAG system backup and restore procedures

### Performance Testing
- Service startup time validation
- Database performance under load (including RAG queries)
- Network latency measurements
- Upgrade completion time verification
- RAG query response time benchmarking

## Observability

### Logging Strategy
- Centralized logging via Docker logging drivers
- Structured JSON logging format
- Log aggregation and retention policies

### Metrics Collection
- Service health and availability metrics
- Database performance metrics (including RAG query performance)
- MCP server operation metrics
- RAG system metrics (query latency, search accuracy, document processing)
- Resource utilization monitoring

### Alerting
- Critical service failures
- Database connectivity issues
- Resource exhaustion warnings
- Backup procedure failures
- Framework upgrade failures
- Version compatibility issues

## Future Considerations

### Potential Enhancements
- Kubernetes migration for advanced orchestration
- Multi-node deployment for high availability
- Advanced AI agent capabilities
- Additional MCP server integrations

### Known Limitations
- Single database instance creates potential bottleneck
- Docker Compose limitations for complex orchestration
- Home server hardware constraints

### Areas for Future Enhancement
- Advanced security features (mTLS, RBAC)
- Automated scaling capabilities
- Enhanced monitoring and analytics
- Additional backup strategies (offsite, incremental)

## Dependencies

### Runtime Dependencies
- Docker Engine 20.10+
- Docker Compose 2.0+
- Minimum 10GB RAM for home server (12GB recommended with RAG infrastructure)
- 150GB storage for data, backups, and document storage
- Additional storage for framework version management and RAG document indexing

### External Services
- Cloudflare account and tunnel configuration
- OpenAI API access for Letta, Graphiti, and RAG processing
- Slack workspace and bot configuration
- Gmail OAuth configuration

### Upgrade Infrastructure Dependencies
- Git for framework source management (if needed)
- Basic shell scripting environment for upgrade automation
- Network access for downloading release notes and framework updates

### RAG Infrastructure Dependencies
- Python 3.11+ environment for HayHooks (containerized)
- Embedding model storage (sentence-transformers models)
- Document processing tools (pandoc for format conversion)
- Access to document sources for ingestion

## Security Considerations

### Authentication & Authorization
- Service-to-service authentication via shared secrets
- External access controlled via Cloudflare authentication
- Database access restricted to authorized services

### Data Protection
- Encryption at rest for sensitive data
- Secure secret management via environment variables
- Network isolation for internal communications

### Compliance
- Data retention policies for user interactions
- Privacy considerations for AI agent data
- Audit logging for system access

## Rollout Strategy

1. **Development Phase**: Implementation in development environment
2. **Testing Phase**: Comprehensive testing and validation
3. **Staging Deployment**: Deploy to staging environment for final validation
4. **Production Migration**: Careful migration with rollback capabilities
5. **Monitoring Period**: Extended monitoring and optimization phase

## Success Metrics

### Technical Metrics
- System startup time < 5 minutes
- Service availability > 99.5%
- Database migration with zero data loss
- All MCP servers operational with < 100ms latency

### Operational Metrics
- Single command deployment success
- Backup/restore procedures validated
- Monitoring and alerting functional
- Documentation completeness

### User Experience Metrics
- PA functionality equivalent to current system
- Response times maintained or improved
- All integration workflows functional
- Simplified deployment and maintenance

## References

- [Current System Analysis](../analysis/pa-ecosystem-analysis.md)
- [Docker Compose Best Practices](https://docs.docker.com/compose/production/)
- [Letta Documentation](https://docs.letta.com/)
- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/)
- [Supabase Self-Hosting Guide](https://supabase.com/docs/guides/self-hosting)

