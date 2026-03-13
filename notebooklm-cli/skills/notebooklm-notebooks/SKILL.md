---
name: notebooklm-notebooks
version: 1.0.0
description: "NotebookLM: Create, list, get, delete, rename notebooks and get AI descriptions."
metadata:
  openclaw:
    category: "research"
    requires:
      bins: ["notebooklm-cli"]
    cliHelp: "notebooklm-cli notebook --help"
---

# notebook

> **PREREQUISITE:** Read `../notebooklm-shared/SKILL.md` for installation, auth, global flags, and security rules.

```bash
notebooklm-cli [global-flags] notebook <action> [flags]
```

## Actions

| Action | Description |
|--------|-------------|
| `create` | Create a new notebook (title required) |
| `list` | List all notebooks |
| `get` | Get notebook details by ID |
| `delete` | Delete a notebook (use `--dry-run` first) |
| `rename` | Rename a notebook |
| `describe` | Get AI-generated description and suggested topics |
| `topics` | Get raw summary text |

Run `notebooklm-cli schema notebook.<action>` to see all parameters for any action.

## Common Patterns

```bash
# Create a notebook
notebooklm-cli --body '{"title": "Q2 Research"}' notebook create

# List notebooks (compact)
notebooklm-cli --fields id,title notebook list

# Get details
notebooklm-cli --body '{"notebookId": "abc123"}' notebook get

# Rename
notebooklm-cli --body '{"notebookId": "abc123", "newTitle": "Q2 Research - Final"}' notebook rename

# Delete (dry-run first)
notebooklm-cli --body '{"notebookId": "abc123"}' --dry-run notebook delete
notebooklm-cli --body '{"notebookId": "abc123"}' notebook delete

# Get AI description
notebooklm-cli --body '{"notebookId": "abc123"}' notebook describe
```

## Tips

- Always use `--fields id,title` on `list` to limit token usage
- Use `describe` after adding sources to get an AI summary of the notebook's content
- Notebook IDs are returned by `create` and `list` — save them for subsequent commands
