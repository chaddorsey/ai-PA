# Programmatic Tool Calling: Implications for PA Ecosystem

**Date**: 2025-01-21  
**Reference**: [Letta Blog: Programmatic Tool Calling with any LLM](https://www.letta.com/blog/programmatic-tool-calling-with-any-llm)  
**Letta Version**: 0.14.0 (supports programmatic tool calling)

## Overview

Programmatic tool calling allows Letta agents to write and execute Python scripts that dynamically invoke other tools attached to the agent. This enables agents to define their own workflows, chain tools together, and process data programmatically rather than relying solely on sequential LLM-driven tool selection.

## Current Use Cases Analysis

### 1. Scheduling Orchestrator (`orchestrate_scheduling`)

**Current Pattern:**
- Agent extracts participant IDs from user request
- Agent calls `orchestrate_scheduling` with `participant_ids`
- Tool internally fetches calendar events via MCP `Core_Event_Data`
- Tool returns optimized meeting proposals

**Implications with Programmatic Tool Calling:**

#### ✅ **Potential Benefits**

1. **Parallel Calendar Fetching**
   - Currently: Tool fetches calendars sequentially
   - With programmatic: Agent could write script to fetch all participant calendars in parallel before calling orchestrator
   - Benefit: Faster execution for meetings with many participants

2. **Pre-processing Calendar Data**
   - Agent could write script to:
     - Filter events by type/importance before passing to orchestrator
     - Aggregate availability across multiple calendars
     - Transform event data format if needed
   - Benefit: Cleaner data, better optimization results

3. **Multi-Step Scheduling Workflows**
   - Agent could write script that:
     - Finds optimal time slots
     - Checks Calendly availability for external participants
     - Creates multiple meeting options with different constraints
     - Validates proposals against additional rules
   - Benefit: More sophisticated scheduling logic

4. **Batch Operations**
   - Agent could create multiple meetings in one script:
     ```python
     # Pseudo-code example
     for meeting in meeting_requests:
         result = orchestrate_scheduling(...)
         if result.status == "ok":
             create_calendar_event(result.proposals[0])
     ```
   - Benefit: Efficient batch scheduling

#### ⚠️ **Considerations**

1. **Tool Complexity**
   - `orchestrate_scheduling` already handles complex logic internally
   - Programmatic calling might add unnecessary complexity
   - Risk: Over-engineering simple scheduling requests

2. **Error Handling**
   - Current tool has comprehensive error handling
   - Programmatic scripts would need their own error handling
   - Risk: Less robust error recovery

3. **Context Window Efficiency**
   - Current: Tool returns clean, structured proposals
   - Programmatic: Scripts might generate verbose intermediate outputs
   - Risk: Increased token usage

### 2. MCP Tool Integration

**Current MCP Servers:**
- `gmail-tools` - Email operations
- `slack-tools` - Slack operations  
- `graphiti-tools` - Knowledge graph operations
- `rag-tools` - Document search
- `calendly-tools` - Availability checking
- `scheduler-tools` - Job scheduling

**Implications with Programmatic Tool Calling:**

#### ✅ **Major Opportunities**

1. **Cross-Service Workflows**
   - Agent could write scripts that combine multiple MCP tools:
     ```python
     # Example: Find email, search knowledge base, schedule follow-up
     email = get_email(email_id)
     context = search_rag(email.subject)
     schedule_meeting(participants=[email.sender], context=context)
     ```
   - Benefit: Powerful multi-step workflows without LLM overhead

2. **Data Transformation Pipelines**
   - Agent could process data between tool calls:
     ```python
     # Example: Process Slack analytics, store in knowledge base
     analytics = trigger_slack_analytics_export()
     processed = transform_analytics(analytics)
     store_in_rag(processed)
     ```
   - Benefit: Clean data processing without context pollution

3. **Parallel MCP Operations**
   - Agent could fetch from multiple MCP servers simultaneously:
     ```python
     # Example: Fetch calendar + check Calendly + search RAG in parallel
     calendar_events = get_calendar_events(...)
     calendly_slots = check_calendly_availability(...)
     relevant_docs = search_rag(query)
     # Process all results together
     ```
   - Benefit: Faster execution, better user experience

4. **Conditional Workflows**
   - Agent could implement branching logic:
     ```python
     # Example: Different actions based on email content
     email = get_email(id)
     if email.urgent:
         notify_slack(email)
         schedule_meeting(email.sender)
     else:
         store_in_rag(email)
     ```
   - Benefit: Smarter, context-aware automation

### 3. Analytics Tools (Drive & Slack)

**Current Pattern:**
- Agent calls individual analytics tools
- Each tool returns data
- Agent processes results in conversation

**Implications:**

#### ✅ **Benefits**

1. **Batch Analytics Collection**
   - Agent could write script to collect multiple analytics in one go:
     ```python
     # Collect all analytics, process, and summarize
     drive_data = collect_daily_workspace_activity()
     slack_data = trigger_slack_analytics_export()
     summary = generate_analytics_summary(drive_data, slack_data)
     ```
   - Benefit: More efficient data collection

2. **Data Aggregation**
   - Scripts could combine analytics from multiple sources
   - Benefit: Richer insights, better reporting

3. **Automated Reporting**
   - Scripts could generate reports automatically
   - Benefit: Consistent, timely reporting

### 4. RAG and Knowledge Graph Integration

**Current Pattern:**
- Agent calls RAG search or Graphiti query
- Uses results in conversation

**Implications:**

#### ✅ **Benefits**

1. **Multi-Source Knowledge Retrieval**
   - Scripts could search RAG, query Graphiti, and check memory blocks:
     ```python
     # Comprehensive knowledge retrieval
     rag_results = search_rag(query)
     graph_results = query_graphiti(query)
     memory_blocks = get_relevant_memory_blocks(query)
     combined = merge_knowledge_sources(rag_results, graph_results, memory_blocks)
     ```
   - Benefit: More comprehensive knowledge access

2. **Knowledge Synthesis**
   - Scripts could synthesize information from multiple sources
   - Benefit: Better answers, more context

## Specific Use Case Scenarios

### Scenario 1: Enhanced Scheduling Workflow

**Current:**
```
User: "Schedule a meeting with Alex and Priya next week"
Agent: 
  1. Extract participants
  2. Call orchestrate_scheduling
  3. Present results
```

**With Programmatic Tool Calling:**
```python
# Agent writes script:
participants = ["alex@example.com", "priya@example.com"]

# Check Calendly for external participants
calendly_availability = check_calendly_availability(participants)

# Find optimal times
proposals = orchestrate_scheduling(
    utterance="Find 45 minutes next week",
    participant_ids=participants,
    context_json=...
)

# Validate against Calendly
validated_proposals = filter_by_calendly(proposals, calendly_availability)

# Create meeting with best option
create_calendar_event(validated_proposals[0])
```

**Benefits:**
- Integrates multiple data sources
- Validates proposals against external constraints
- Automates meeting creation

### Scenario 2: Email-to-Meeting Pipeline

**With Programmatic Tool Calling:**
```python
# Agent writes script:
# 1. Get email
email = get_email(email_id)

# 2. Extract meeting request from email
request = extract_scheduling_request(email.body)

# 3. Search knowledge base for context
context = search_rag(f"meeting with {request.participants}")

# 4. Find optimal time
proposals = orchestrate_scheduling(
    utterance=request.text,
    participant_ids=request.participants,
    context_json=context
)

# 5. Create meeting
meeting = create_calendar_event(proposals[0])

# 6. Reply to email with confirmation
send_email_reply(email, meeting)
```

**Benefits:**
- End-to-end automation
- Context-aware scheduling
- Automated follow-up

### Scenario 3: Analytics Dashboard Generation

**With Programmatic Tool Calling:**
```python
# Agent writes script:
# Collect all analytics in parallel
drive_activity = collect_daily_workspace_activity()
slack_mentions = collect_daily_mentions()
slack_files = list_recent_slack_files()

# Process and aggregate
dashboard = create_dashboard(
    drive=drive_activity,
    slack_mentions=slack_mentions,
    slack_files=slack_files
)

# Store in knowledge base for future reference
store_in_rag(dashboard, tags=["analytics", "dashboard"])
```

**Benefits:**
- Automated reporting
- Historical tracking
- Knowledge base integration

## Implementation Considerations

### 1. When to Use Programmatic Tool Calling

**Good Use Cases:**
- ✅ Multi-step workflows that combine multiple tools
- ✅ Data processing/transformation between tool calls
- ✅ Parallel operations (fetching multiple calendars, etc.)
- ✅ Conditional logic based on tool outputs
- ✅ Batch operations (multiple meetings, multiple analytics)

**Not Recommended:**
- ❌ Simple single-tool operations (use direct tool calling)
- ❌ Operations that current tools already handle well
- ❌ When tool has built-in optimization (like `orchestrate_scheduling`)

### 2. Migration Strategy

**Phase 1: Identify Opportunities**
- Review current tool usage patterns
- Identify workflows that involve multiple sequential tool calls
- Document pain points in current workflows

**Phase 2: Pilot Implementation**
- Start with one high-value use case
- Test programmatic tool calling with `run_code_with_tools`
- Measure improvements (speed, accuracy, token usage)

**Phase 3: Expand Usage**
- Roll out to additional use cases
- Update agent instructions/prompts
- Document new patterns

### 3. Agent Prompting Updates

**Current Instructions:**
- "Call orchestrate_scheduling with participant_ids"
- "Use Get_Events to fetch calendar data"

**Updated Instructions (if using programmatic):**
- "For complex workflows, consider using run_code_with_tools to combine multiple operations"
- "You can write scripts to process data between tool calls"
- "Use programmatic calling for parallel operations or batch processing"

### 4. Tool Design Implications

**Current Tools:**
- `orchestrate_scheduling` - Already handles complex logic internally
- MCP tools - Simple, focused operations
- Analytics tools - Return structured data

**Considerations:**
- Tools should remain focused and composable
- Programmatic calling is a layer on top, not a replacement
- Tools should return clean, structured data for script processing

## Risks and Mitigations

### 1. **Complexity Risk**
- **Risk**: Scripts become too complex, hard to debug
- **Mitigation**: Start simple, document patterns, provide examples

### 2. **Error Handling Risk**
- **Risk**: Scripts fail silently or with unclear errors
- **Mitigation**: Implement robust error handling in scripts, log failures

### 3. **Security Risk**
- **Risk**: Code execution in agent environment
- **Mitigation**: Letta handles sandboxing, but review what tools scripts can call

### 4. **Token Usage Risk**
- **Risk**: Scripts generate verbose output, increasing costs
- **Mitigation**: Design scripts to return concise results, process data efficiently

### 5. **Maintenance Risk**
- **Risk**: Scripts become part of agent behavior, hard to update
- **Mitigation**: Store scripts as skills, version control, document dependencies

## Recommendations

### Immediate Actions

1. **Enable `run_code_with_tools` on Agents**
   - Attach the tool to relevant agents
   - Test with simple workflows first

2. **Identify High-Value Use Cases**
   - Multi-calendar scheduling with Calendly validation
   - Email-to-meeting automation
   - Analytics aggregation workflows

3. **Create Example Scripts**
   - Document common patterns
   - Provide templates for agents
   - Store as skills for reuse

### Short-Term (Next Sprint)

1. **Pilot Programmatic Workflows**
   - Start with one use case (e.g., enhanced scheduling)
   - Measure improvements
   - Document learnings

2. **Update Agent Instructions**
   - Add guidance on when to use programmatic calling
   - Provide examples
   - Document best practices

3. **Create Skill Library**
   - Store reusable script patterns as skills
   - Version control scripts
   - Share across agents

### Long-Term

1. **Workflow Optimization**
   - Identify all multi-step workflows
   - Convert to programmatic where beneficial
   - Measure performance improvements

2. **Advanced Patterns**
   - Map-reduce workflows
   - Parallel processing
   - Conditional automation

3. **Integration Patterns**
   - Cross-service workflows
   - Data pipelines
   - Automated reporting

## Conclusion

Programmatic tool calling offers significant opportunities for the PA ecosystem:

1. **Scheduling**: Enhanced workflows with parallel fetching, validation, and automation
2. **MCP Integration**: Powerful cross-service workflows and data processing
3. **Analytics**: Automated collection, processing, and reporting
4. **Knowledge**: Multi-source retrieval and synthesis

The feature is particularly valuable for:
- Complex multi-step workflows
- Parallel operations
- Data processing between tool calls
- Conditional/branching logic

However, it should be used judiciously:
- Not for simple single-tool operations
- Not when current tools already handle complexity well
- With careful error handling and testing

**Next Steps**: Enable `run_code_with_tools` on agents and pilot with one high-value use case to measure impact.

