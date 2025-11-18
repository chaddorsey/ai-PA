# Scheduling Orchestrator Configuration

## Overview

This document describes configuration options, limits, and security considerations for the scheduling orchestration tool.

## Dependencies

The tool requires the following Python packages (already added to `letta/requirements.txt`):

- `clingo>=5.6.0` - Answer Set Programming solver
- `dspy-ai>=2.4.0` - LLM pipeline framework for natural language extraction
- `pydantic>=2.0.0` - Data validation and serialization
- `pytz>=2023.3` - Timezone handling

## Configuration

### Environment Variables

The tool reads configuration from environment variables:

#### LLM API Keys (Required for DSPy)

- `OPENAI_API_KEY` - OpenAI API key (if using OpenAI models)
- `ANTHROPIC_API_KEY` - Anthropic API key (if using Claude models)

At least one LLM API key must be set for DSPy extraction to work. The tool will prefer OpenAI if available, otherwise falls back to Anthropic.

#### Letta Configuration

- `LETTA_BASE_URL` - Letta server base URL (default: `http://localhost:8283`)
- `LETTA_AGENT_ID` - Agent ID for attaching tools (required for attachment script)

### Timeouts

The tool enforces the following timeouts:

- **clingo solve timeout**: 30 seconds (default)
  - Configurable via `ClingoSolver(timeout=30)`
  - If exceeded, returns UNSAT or error

- **DSPy extraction timeout**: No explicit timeout (relies on LLM API timeouts)
  - Typical extraction time: 2-5 seconds
  - Falls back to basic parsing if DSPy fails

- **Overall tool timeout**: No explicit timeout (relies on Letta's tool execution timeout)
  - Typical execution time: 5-15 seconds for normal cases
  - Up to 60 seconds for complex scenarios with many events

### Memory Limits

The tool enforces the following limits to prevent excessive memory usage:

- **Maximum planning horizon**: 28 days (4 weeks)
  - Enforced in `orchestrate_scheduling()` bounds checking
  - Larger horizons can be supported but may impact performance

- **Maximum participants**: 10 participants
  - Enforced in `orchestrate_scheduling()` bounds checking
  - More participants increase ASP program size and solve time

- **Maximum events per participant**: 100 events
  - Enforced in `orchestrate_scheduling()` bounds checking
  - More events increase normalization and ASP fact generation time

### Performance Characteristics

Typical performance for different scenarios:

| Scenario | Horizon | Participants | Events/Person | Solve Time | Total Time |
|----------|---------|--------------|---------------|------------|------------|
| Simple | 1 week | 2-3 | 10-20 | 0.5-2s | 2-5s |
| Medium | 2 weeks | 3-5 | 20-40 | 1-5s | 5-10s |
| Complex | 4 weeks | 5-10 | 40-100 | 5-30s | 10-60s |

Performance depends on:
- Number of free slots (more free slots = faster solve)
- Number of constraints (more constraints = slower solve)
- Optimization level (lexicographic optimization adds overhead)

## Security Considerations

### Read-Only Access

The tool is **read-only** with respect to calendar data:
- Only reads events from `events_by_participant` input
- Does not write to calendars
- Does not modify existing events
- Returns proposals that must be scheduled by the Letta agent or user

### PII Handling

The tool processes calendar events which may contain:
- Participant email addresses
- Event titles and descriptions
- Meeting locations

**Current behavior**: PII is passed through in tool inputs/outputs. For production use, consider:
- Redacting PII in logs (task 21-11: Observability)
- Encrypting sensitive data in transit
- Limiting access to tool execution logs

### Sandboxed Execution

The tool runs in Letta's sandboxed environment:
- No direct network access (except LLM API calls via DSPy)
- No file system writes (except temporary files)
- Limited resource access (CPU, memory)

### API Key Security

LLM API keys are read from environment variables:
- Keys should be stored securely in Letta tool configuration
- Never commit keys to version control
- Rotate keys regularly
- Use least-privilege API keys when possible

## Best Practices

### Horizon Sizing

- **Recommended**: 1-2 weeks for typical use cases
- **Maximum**: 4 weeks (enforced limit)
- **Too large**: May cause timeouts or memory issues

### Participant Count

- **Recommended**: 2-5 participants for optimal performance
- **Maximum**: 10 participants (enforced limit)
- **Too many**: Increases solve time exponentially

### Event Density

- **Recommended**: <50 events per participant per week
- **Maximum**: 100 events per participant (enforced limit)
- **Too dense**: May cause UNSAT or slow solves

### Context JSON

Provide complete context for best results:
- Include all participants with work hours
- Specify time windows when possible
- Include policy preferences (min gaps, protected events)
- Set timezone correctly

## Troubleshooting

### Tool Returns "bad_input"

- Check that `events_by_participant` is not empty
- Verify horizon size is ≤ 28 days
- Verify participant count is ≤ 10
- Verify events per participant is ≤ 100

### Tool Returns "unsat"

- Review relaxation suggestions in response
- Try widening time window
- Try relaxing minimum gap requirements
- Try extending planning horizon
- Check if all participants have work hours defined

### Tool Times Out

- Reduce planning horizon
- Reduce number of participants
- Reduce number of events
- Increase clingo timeout (if needed)

### DSPy Extraction Fails

- Verify LLM API key is set (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)
- Check API key is valid and has credits
- Tool will fall back to basic parsing if DSPy fails
- Check utterance is clear and contains required information (duration, participants)

## Example Configuration

```bash
# Set LLM API key
export OPENAI_API_KEY="sk-..."

# Set Letta configuration
export LETTA_BASE_URL="http://localhost:8283"
export LETTA_AGENT_ID="your-agent-id"

# Register tool
python3 letta/register_scheduling_tool.py

# Attach to agent
python3 letta/attach_scheduling_tool_to_agent.py
```

