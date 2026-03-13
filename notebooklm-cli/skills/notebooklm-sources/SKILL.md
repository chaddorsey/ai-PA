---
name: notebooklm-sources
version: 1.0.0
description: "NotebookLM: Add URLs, files, text, YouTube, and Drive sources to notebooks."
metadata:
  openclaw:
    category: "research"
    requires:
      bins: ["notebooklm-cli"]
    cliHelp: "notebooklm-cli source --help"
---

# source

> **PREREQUISITE:** Read `../notebooklm-shared/SKILL.md` for installation, auth, global flags, and security rules.

```bash
notebooklm-cli [global-flags] source <action> [flags]
```

## Actions

| Action | Description |
|--------|-------------|
| `add-url` | Add a URL source (web page, article) |
| `add-text` | Add pasted text with a title |
| `add-file` | Add a file (PDF, DOCX, MD, audio, video, images) |
| `add-youtube` | Add a YouTube video |
| `add-drive` | Add a Google Drive document |
| `list` | List sources in a notebook |
| `get` | Get source details |
| `delete` | Delete a source |
| `rename` | Rename a source |
| `refresh` | Refresh a source to pick up changes |
| `guide` | Get AI-generated source guide/summary |
| `fulltext` | Get source freshness check |

Run `notebooklm-cli schema source.<action>` to see all parameters for any action.

## Common Patterns

```bash
# Add a URL
notebooklm-cli --body '{"notebookId": "nb123", "url": "https://example.com/article"}' source add-url

# Add a file (PDF, DOCX, etc.)
notebooklm-cli --body '{"notebookId": "nb123", "filePath": "/path/to/document.pdf"}' source add-file

# Add text content
notebooklm-cli --body '{"notebookId": "nb123", "title": "Meeting Notes", "content": "Key points..."}' source add-text

# Add YouTube video
notebooklm-cli --body '{"notebookId": "nb123", "url": "https://youtube.com/watch?v=..."}' source add-youtube

# Add Google Drive document
notebooklm-cli --body '{"notebookId": "nb123", "fileId": "1abc...", "title": "Proposal Draft"}' source add-drive

# List sources (compact)
notebooklm-cli --fields id,title --body '{"notebookId": "nb123"}' source list

# Get AI guide for a source
notebooklm-cli --body '{"notebookId": "nb123", "sourceId": "src456"}' source guide

# Delete (dry-run first)
notebooklm-cli --body '{"notebookId": "nb123", "sourceId": "src456"}' --dry-run source delete
```

## Tips

- Use `--wait` flag on add operations to block until processing completes (useful for pipelines)
- File paths must not contain `..` — path traversal is blocked
- `guide` returns an AI summary of a single source — useful for quick understanding
- `refresh` re-processes a URL source to pick up content changes
