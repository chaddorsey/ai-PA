# Task Types

This directory contains multi-agent coordination task type definitions.

## Lifecycle Stages

- `draft` - Being designed, not yet executable
- `active` - Deployed and in use
- `refined` - Improved based on execution data
- `hardened` - Stable, potentially with UI shortcuts

## File Format

Each task type is a YAML file: `{task_name}.yaml`

See `docs/plans/2026-01-29-coordination-orchestration-design.md` for schema.

## Creating New Task Types

Task types are created through conversation with the Main Agent:
1. Brainstorm the task goal and which agents could help
2. Design the prompts, templates, and success criteria
3. Main Agent creates the YAML file and registers it

## Example

```yaml
name: meeting_prep
lifecycle_stage: active
goal: "Gather relevant context before meetings"
agents:
  calendar:
    prompt_template: "Find meeting matching '{meeting_identifier}'..."
```
