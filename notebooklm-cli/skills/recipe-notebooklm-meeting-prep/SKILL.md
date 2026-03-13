---
name: recipe-notebooklm-meeting-prep
version: 1.0.0
description: "Multi-step meeting prep: create notebook from notes and docs, extract action items, generate briefing."
metadata:
  openclaw:
    category: "recipe"
    domain: "productivity"
    requires:
      bins: ["notebooklm-cli"]
      skills: ["notebooklm-shared", "notebooklm-notebooks", "notebooklm-sources", "notebooklm-chat"]
---

# Meeting Prep

> **PREREQUISITE:** Load the following skills to execute this recipe: `notebooklm-shared`, `notebooklm-notebooks`, `notebooklm-sources`, `notebooklm-chat`

Prepare for a meeting by loading prior notes and related documents, then extracting action items and talking points.

## Steps

1. **Create a meeting notebook:**
   ```bash
   notebooklm-cli --body '{"title": "Helen Meeting Prep 2026-03-14"}' notebook create
   ```

2. **Add prior meeting notes** (e.g., from Granola exports):
   ```bash
   notebooklm-cli --body '{"notebookId": "NB_ID", "filePath": "/data/exports/granolaNote--Helen.md"}' source add-file
   ```

3. **Add related documents:**
   ```bash
   # Shared Google Doc
   notebooklm-cli --body '{"notebookId": "NB_ID", "fileId": "1abc...", "title": "Project Plan"}' source add-drive

   # Relevant email thread (pasted as text)
   notebooklm-cli --body '{"notebookId": "NB_ID", "title": "Email Thread - Budget", "content": "..."}' source add-text
   ```

4. **Extract action items:**
   ```bash
   notebooklm-cli --body '{"notebookId": "NB_ID", "question": "What open action items exist from our previous meetings?"}' chat ask
   ```

5. **Generate talking points:**
   ```bash
   notebooklm-cli --body '{"notebookId": "NB_ID", "question": "What are the key topics we should discuss? Prioritize by urgency."}' chat ask
   ```

6. **Check for blockers:**
   ```bash
   notebooklm-cli --body '{"notebookId": "NB_ID", "question": "Are there any decisions or blockers mentioned that need resolution?"}' chat ask
   ```

7. **Optional: Save a prep note:**
   ```bash
   notebooklm-cli --body '{"notebookId": "NB_ID", "title": "Prep Summary", "content": "..."}' note create
   ```

## Tips

- Create the notebook the day before so sources have time to process
- Use `conversationId` to build on previous answers within the same prep session
- After the meeting, add the new meeting notes as a source for next time
