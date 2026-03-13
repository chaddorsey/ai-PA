---
name: notebooklm-artifacts
version: 1.0.0
description: "NotebookLM: Generate audio overviews, reports, quizzes, slides, and other AI artifacts."
metadata:
  openclaw:
    category: "research"
    requires:
      bins: ["notebooklm-cli"]
    cliHelp: "notebooklm-cli artifact --help"
---

# artifact

> **PREREQUISITE:** Read `../notebooklm-shared/SKILL.md` for installation, auth, global flags, and security rules.

```bash
notebooklm-cli [global-flags] artifact <action> [flags]
```

## Actions

| Action | Description |
|--------|-------------|
| `generate` | Generate an artifact (audio, video, report, quiz, etc.) |
| `list` | List artifacts in a notebook |
| `get` | Get artifact details |
| `delete` | Delete an artifact |
| `rename` | Rename an artifact |
| `download` | Download artifact to a local file |
| `status` | Check generation status |
| `wait` | Wait for generation to complete |

Run `notebooklm-cli schema artifact.<action>` to see all parameters for any action.

## Artifact Types

The `generate` command's `type` parameter accepts: `audio`, `video`, `report`, `quiz`, `flashcards`, `infographic`, `slide-deck`, `data-table`, `mind-map`.

## Generation Lifecycle

Artifact generation is asynchronous — follow this pattern:

```bash
# 1. Start generation (returns taskId)
notebooklm-cli --body '{"notebookId": "nb123", "type": "audio", "instructions": "Focus on methodology"}' artifact generate

# 2. Wait for completion (may take 30-120s)
notebooklm-cli --body '{"notebookId": "nb123", "taskId": "task789", "timeout": 300}' artifact wait

# 3. Download the result
notebooklm-cli --body '{"notebookId": "nb123", "type": "audio", "outputPath": "./podcast.mp3"}' artifact download
```

## Common Patterns

```bash
# Generate an audio overview (podcast-style)
notebooklm-cli --body '{"notebookId": "nb123"}' artifact generate

# Generate a report
notebooklm-cli --body '{"notebookId": "nb123", "type": "report", "instructions": "Executive summary format"}' artifact generate

# Generate a quiz from sources
notebooklm-cli --body '{"notebookId": "nb123", "type": "quiz"}' artifact generate

# List all artifacts
notebooklm-cli --fields id,title --body '{"notebookId": "nb123"}' artifact list

# Check status without blocking
notebooklm-cli --body '{"notebookId": "nb123", "taskId": "task789"}' artifact status

# Delete an artifact
notebooklm-cli --body '{"notebookId": "nb123", "artifactId": "art456"}' --dry-run artifact delete
```

## Tips

- Use `timeout=300` for `wait` when calling from Letta (default CLI timeout is 60s)
- `instructions` lets you customize the generated content's focus and style
- Audio generation typically takes 30-120 seconds
- `download` file extension should match the artifact type (.mp3 for audio, .mp4 for video, etc.)
- `sourceIds` parameter on `generate` lets you limit which sources are used
