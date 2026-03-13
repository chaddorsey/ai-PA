---
name: notebooklm-chat
version: 1.0.0
description: "NotebookLM: Ask questions, manage conversations, and configure chat persona."
metadata:
  openclaw:
    category: "research"
    requires:
      bins: ["notebooklm-cli"]
    cliHelp: "notebooklm-cli chat --help"
---

# chat

> **PREREQUISITE:** Read `../notebooklm-shared/SKILL.md` for installation, auth, global flags, and security rules.

```bash
notebooklm-cli [global-flags] chat <action> [flags]
```

## Actions

| Action | Description |
|--------|-------------|
| `ask` | Ask a question about the notebook's sources |
| `history` | Get conversation history |
| `clear` | Clear conversation cache |
| `save` | Configure chat persona and response settings |

Run `notebooklm-cli schema chat.<action>` to see all parameters for any action.

## Common Patterns

```bash
# Ask a question
notebooklm-cli --body '{"notebookId": "nb123", "question": "What are the key findings?"}' chat ask

# Continue a conversation (pass conversationId from previous response)
notebooklm-cli --body '{"notebookId": "nb123", "question": "Can you elaborate on point 3?", "conversationId": "conv456"}' chat ask

# Ask about specific sources only
notebooklm-cli --body '{"notebookId": "nb123", "question": "Compare these two papers", "sourceIds": ["src1", "src2"]}' chat ask

# Get conversation history
notebooklm-cli --body '{"notebookId": "nb123"}' chat history

# Clear conversation cache
notebooklm-cli chat clear

# Configure chat persona
notebooklm-cli --body '{"notebookId": "nb123", "goal": "LEARNING_GUIDE"}' chat save
```

## Conversation Threading

- `ask` returns a `conversationId` in its response
- Pass it back in subsequent `ask` calls for multi-turn conversations
- Omitting `conversationId` starts a fresh conversation
- Use `clear` to reset all cached conversations

## Tips

- Use `sourceIds` to focus answers on specific sources when the notebook has many
- The `LEARNING_GUIDE` persona gives more pedagogical, step-by-step answers
- Use `CUSTOM` goal with `customPrompt` for specialized behavior
