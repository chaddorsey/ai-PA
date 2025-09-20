# PBI-13: Extensible RAG Infrastructure - Tool-Based Integration

[View in Backlog](../backlog.md#user-content-13)

## Overview

Implement extensible RAG (Retrieval Augmented Generation) infrastructure integrated through Letta using the proven HayHooks/Haystack approach, enabling the personal assistant to access and search through technical documentation, personal notes, and domain-specific knowledge bases while maintaining the agent-centric architecture.

## Problem Statement

The current PA system lacks the ability to access and reason over document-based knowledge:
- No capability to search technical documentation or personal notes
- Cannot augment agent responses with retrieved context from documents
- Missing foundation for building domain-specific knowledge capabilities
- No extensible framework for adding new document sources and types

This limits the assistant's effectiveness for:
- Technical question answering from documentation
- Research assistance using personal knowledge bases
- Context-aware responses using domain-specific information
- Learning from and building upon accumulated knowledge

## User Stories

### Primary User Story
**As an AI Engineer**, I want extensible RAG infrastructure integrated through Letta so that the personal assistant can access and search through technical documentation, personal notes, and domain-specific knowledge bases.

### Supporting User Stories
- **As a Knowledge Worker**, I want the assistant to search my technical documentation so that I can get accurate answers from my knowledge base
- **As a Developer**, I want the assistant to access AWS documentation so that I can get contextual help with cloud services
- **As a Researcher**, I want the assistant to search across multiple document domains so that I can find relevant information quickly
- **As a System User**, I want RAG responses to include source citations so that I can verify and explore the underlying information

## Technical Approach

### Architecture Overview
```python
# Tool-based RAG integration maintaining agent-centric design
Letta Agent → RAG MCP Server → HayHooks → Haystack Pipeline → PostgreSQL/pgvector
```

### Core Components

#### 1. HayHooks Service
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
```

#### 2. RAG MCP Server
```python
# Tool-based access for Letta agents
class RAGMCPServer:
    def semantic_search(self, query: str, domain: str = "general", limit: int = 5):
        """Search documents using semantic similarity"""
        pass
        
    def query_documents(self, question: str, domain: str = "general"):
        """Get LLM response augmented with retrieved documents"""
        pass
        
    def ingest_document(self, content: str, metadata: dict):
        """Add new document to the knowledge base"""
        pass
```

### Document Organization
```
Domain Structure:
├── technical/          # Technical documentation  
│   ├── aws/           # AWS service documentation
│   ├── programming/   # Programming guides and references
│   └── systems/       # System administration docs
├── personal/          # Personal notes and knowledge
│   ├── research/      # Research notes and findings
│   ├── projects/      # Project documentation
│   └── references/    # Personal reference materials
└── general/           # General knowledge and miscellaneous
    ├── procedures/    # Standard operating procedures
    └── templates/     # Document templates and examples
```

### Integration with Unified Infrastructure
- **Database**: Uses unified PostgreSQL with rag_documents and rag_embeddings schemas
- **Networking**: Runs on pa-internal Docker network
- **Configuration**: Managed via environment variables and Docker secrets
- **Monitoring**: Integrated with Prometheus/Grafana stack

## UX/UI Considerations

### Agent Experience
- **Natural Language Interface**: Users interact with RAG via normal conversation with Letta
- **Source Attribution**: Responses include citations and source document references
- **Domain Awareness**: Can specify search domains for targeted results
- **Incremental Learning**: New documents can be added through conversation or automated ingestion

### Administrative Interface
- **Document Management**: Web interface for document upload and organization
- **Search Quality Monitoring**: Analytics on search relevance and usage patterns
- **Domain Configuration**: Tools for organizing and configuring document domains
- **Performance Monitoring**: Dashboards for query latency and accuracy metrics

## Acceptance Criteria

### Functional Requirements
- [ ] HayHooks service deployed and operational with basic document search pipeline
- [ ] RAG MCP server integrated with Letta and responding to tool calls
- [ ] Document ingestion workflow functional for text documents
- [ ] Semantic search queries return relevant results with source citations
- [ ] Tool-based access from Letta working with semantic_search and query_documents functions
- [ ] Domain-specific document organization and search capabilities
- [ ] PostgreSQL/pgvector integration for document storage and embeddings

### Non-Functional Requirements
- [ ] Document search queries complete within 10 seconds for typical queries
- [ ] System supports at least 1000 documents per domain without performance degradation  
- [ ] Semantic search accuracy maintains >80% relevance for domain-specific queries
- [ ] Document ingestion supports incremental updates without full re-indexing
- [ ] RAG infrastructure integrates with existing backup and monitoring procedures

### Integration Requirements
- [ ] RAG tools accessible via standard MCP protocol from Letta
- [ ] Document embeddings stored in unified PostgreSQL instance
- [ ] Service health monitoring integrated with existing infrastructure
- [ ] Configuration managed through environment variables
- [ ] Logs integrated with centralized logging system

## Dependencies

### Technical Dependencies
- Unified PostgreSQL database with pgvector extension (PBI-1)
- Docker Compose unification for service deployment (PBI-2) 
- Python 3.11+ environment for HayHooks (containerized)
- Haystack framework and dependencies
- Sentence-transformers embedding models
- OpenAI API access for LLM integration

### Process Dependencies
- **Upstream**:
  - PBI-1 (Database Consolidation) - required for RAG data storage
  - PBI-2 (Docker Compose Unification) - required for service deployment
- **Downstream**:
  - PBI-14 (RAG Database Integration) - builds on RAG infrastructure
- **Parallel**:
  - PBI-4 (MCP Standardization) - RAG MCP server follows standardized patterns

### External Dependencies
- Document sources for initial knowledge base population
- Embedding model downloads and caching
- OpenAI API keys and rate limits
- Document processing tools (pandoc for format conversion)

## Open Questions

1. **Document Formats**: What document formats should be supported initially (PDF, Markdown, HTML, Word)?
2. **Embedding Models**: Should we support multiple embedding models for different domains or use a single general-purpose model?
3. **Real-time Updates**: How should real-time document updates be handled (webhooks, polling, manual triggers)?
4. **Search Analytics**: What level of search analytics and user feedback should be implemented?
5. **Document Versioning**: Should document versioning be supported for tracking changes over time?
6. **Access Control**: What level of access control should be implemented for different document domains?

## Related Tasks

Tasks for this PBI will be defined in [tasks.md](./tasks.md) following the implementation approach:

1. **RAG Architecture Design and Planning**
2. **HayHooks Service Development**
3. **RAG MCP Server Implementation**
4. **Document Pipeline Creation**
5. **PostgreSQL Schema Integration**
6. **Basic Document Ingestion Workflow**
7. **Letta Tool Integration**
8. **Testing and Validation**
9. **Documentation and User Guide**

---

**Back to**: [Project Backlog](../backlog.md)
