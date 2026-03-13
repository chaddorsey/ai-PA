---
name: recipe-notebooklm-research-project
version: 1.0.0
description: "Multi-step research workflow: create notebook, add sources, ask questions, generate reports."
metadata:
  openclaw:
    category: "recipe"
    domain: "research"
    requires:
      bins: ["notebooklm-cli"]
      skills: ["notebooklm-shared", "notebooklm-notebooks", "notebooklm-sources", "notebooklm-chat", "notebooklm-artifacts"]
---

# Research Project

> **PREREQUISITE:** Load the following skills to execute this recipe: `notebooklm-shared`, `notebooklm-notebooks`, `notebooklm-sources`, `notebooklm-chat`, `notebooklm-artifacts`

Build a curated research notebook from multiple sources, then extract insights and generate deliverables.

## Steps

1. **Create the notebook:**
   ```bash
   notebooklm-cli --body '{"title": "NSF CAMEL Proposal Research"}' notebook create
   ```
   Save the returned `id` for all subsequent steps.

2. **Add sources** — mix of URLs, files, and Drive documents:
   ```bash
   # Research papers
   notebooklm-cli --body '{"notebookId": "NB_ID", "filePath": "/path/to/paper.pdf"}' source add-file

   # Web articles
   notebooklm-cli --body '{"notebookId": "NB_ID", "url": "https://..."}' source add-url

   # Google Drive docs
   notebooklm-cli --body '{"notebookId": "NB_ID", "fileId": "1abc...", "title": "Draft"}' source add-drive
   ```

3. **Verify sources loaded:**
   ```bash
   notebooklm-cli --fields id,title --body '{"notebookId": "NB_ID"}' source list
   ```

4. **Explore with questions:**
   ```bash
   notebooklm-cli --body '{"notebookId": "NB_ID", "question": "What are the key methodological gaps across these papers?"}' chat ask
   ```
   Use `conversationId` from the response for follow-up questions.

5. **Optional: Web research to discover more sources:**
   ```bash
   notebooklm-cli --body '{"notebookId": "NB_ID", "query": "AI-assisted science education", "source": "web"}' research start
   notebooklm-cli --body '{"notebookId": "NB_ID"}' research poll
   # Import selected discoveries
   notebooklm-cli --body '{"notebookId": "NB_ID", "taskId": "TASK_ID", "sources": [...]}' research import
   ```

6. **Generate deliverables:**
   ```bash
   # Executive summary report
   notebooklm-cli --body '{"notebookId": "NB_ID", "type": "report", "instructions": "Executive summary for grant reviewers"}' artifact generate
   notebooklm-cli --body '{"notebookId": "NB_ID", "taskId": "TASK_ID", "timeout": 300}' artifact wait

   # Audio overview for the commute
   notebooklm-cli --body '{"notebookId": "NB_ID", "type": "audio", "instructions": "Focus on the research gap and proposed approach"}' artifact generate
   ```

7. **Save key insights as notes:**
   ```bash
   notebooklm-cli --body '{"notebookId": "NB_ID", "title": "Key Findings", "content": "..."}' note create
   ```
