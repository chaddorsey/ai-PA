"""Static schema registry mapping group.action keys to NotebookLM method metadata.

Method names correspond to the actual async methods on the notebooklm-py sub-API
objects (client.notebooks, client.sources, client.artifacts, client.chat,
client.research, client.notes).
"""

from __future__ import annotations

SCHEMAS: dict[str, dict] = {
    # ── notebook (7) — NotebooksAPI ──
    "notebook.create": {
        "method": "create",
        "description": "Create a new notebook",
        "params": {
            "title": {"type": "string", "required": True, "description": "Notebook title"},
        },
    },
    "notebook.list": {
        "method": "list",
        "description": "List all notebooks",
        "params": {},
    },
    "notebook.get": {
        "method": "get",
        "description": "Get notebook details",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "notebook.delete": {
        "method": "delete",
        "description": "Delete a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "notebook.rename": {
        "method": "rename",
        "description": "Rename a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "newTitle": {"type": "string", "required": True, "description": "New title for the notebook"},
        },
    },
    "notebook.describe": {
        "method": "get_description",
        "description": "Get AI-generated summary and suggested topics for a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "notebook.topics": {
        "method": "get_summary",
        "description": "Get raw summary text for a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    # ── source (12) ──
    "source.add-url": {
        "method": "add_url",
        "description": "Add a URL source to a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "url": {"type": "string", "required": True, "description": "URL to add"},
            "wait": {"type": "boolean", "required": False, "description": "Wait for processing to complete"},
        },
    },
    "source.add-text": {
        "method": "add_text",
        "description": "Add a text source (copied text) to a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "title": {"type": "string", "required": True, "description": "Title for the source"},
            "content": {"type": "string", "required": True, "description": "Text content"},
            "wait": {"type": "boolean", "required": False, "description": "Wait for source processing to complete"},
        },
    },
    "source.add-file": {
        "method": "add_file",
        "description": "Add a file source (PDF, DOCX, MD, audio, video, images)",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "filePath": {"type": "string", "required": True, "description": "Path to file"},
            "wait": {"type": "boolean", "required": False, "description": "Wait for processing"},
        },
    },
    "source.add-youtube": {
        "method": "add_url",
        "description": "Add a YouTube video as a source",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "url": {"type": "string", "required": True, "description": "YouTube URL"},
            "wait": {"type": "boolean", "required": False, "description": "Wait for processing"},
        },
    },
    "source.add-drive": {
        "method": "add_drive",
        "description": "Add a Google Drive document as a source",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "fileId": {"type": "string", "required": True, "description": "Google Drive file ID"},
            "title": {"type": "string", "required": True, "description": "Display title for the source"},
            "mimeType": {"type": "string", "required": False, "description": "MIME type of the Drive document"},
            "wait": {"type": "boolean", "required": False, "description": "Wait for source processing to complete"},
        },
    },
    "source.list": {
        "method": "list",
        "description": "List sources in a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "source.get": {
        "method": "get",
        "description": "Get source details",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "sourceId": {"type": "string", "required": True, "description": "Source ID"},
        },
    },
    "source.delete": {
        "method": "delete",
        "description": "Delete a source from a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "sourceId": {"type": "string", "required": True, "description": "Source ID"},
        },
    },
    "source.rename": {
        "method": "rename",
        "description": "Rename a source",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "sourceId": {"type": "string", "required": True, "description": "Source ID"},
            "newTitle": {"type": "string", "required": True, "description": "New title for the source"},
        },
    },
    "source.refresh": {
        "method": "refresh",
        "description": "Refresh a source to pick up changes",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "sourceId": {"type": "string", "required": True, "description": "Source ID"},
        },
    },
    "source.guide": {
        "method": "get_guide",
        "description": "Get the AI-generated source guide/summary",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "sourceId": {"type": "string", "required": True, "description": "Source ID"},
        },
    },
    "source.fulltext": {
        "method": "check_freshness",
        "description": "Get source full text / freshness check",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "sourceId": {"type": "string", "required": True, "description": "Source ID"},
        },
    },
    # ── artifact (8) — ArtifactsAPI ──
    "artifact.generate": {
        "method": "generate_audio",
        "description": "Generate an artifact (audio overview by default)",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "type": {"type": "string", "required": False, "description": "Artifact type: audio, video, report, quiz, flashcards, infographic, slide-deck, data-table, mind-map"},
            "sourceIds": {"type": "array[string]", "required": False, "description": "Source IDs to include (default: all)"},
            "language": {"type": "string", "required": False, "description": "Language code (default: en)"},
            "instructions": {"type": "string", "required": False, "description": "Custom generation instructions"},
        },
    },
    "artifact.list": {
        "method": "list",
        "description": "List artifacts in a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "artifact.get": {
        "method": "get",
        "description": "Get artifact details",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "artifactId": {"type": "string", "required": True, "description": "Artifact ID"},
        },
    },
    "artifact.delete": {
        "method": "delete",
        "description": "Delete an artifact",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "artifactId": {"type": "string", "required": True, "description": "Artifact ID"},
        },
    },
    "artifact.rename": {
        "method": "rename",
        "description": "Rename an artifact",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "artifactId": {"type": "string", "required": True, "description": "Artifact ID"},
            "newTitle": {"type": "string", "required": True, "description": "New title for the artifact"},
        },
    },
    "artifact.download": {
        "method": "download_audio",
        "description": "Download an artifact to a local file",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "outputPath": {"type": "string", "required": True, "description": "Path to save the downloaded file"},
            "artifactId": {"type": "string", "required": False, "description": "Artifact ID (default: first completed)"},
            "type": {"type": "string", "required": False, "description": "Artifact type: audio, video, infographic, slide-deck"},
        },
    },
    "artifact.status": {
        "method": "poll_status",
        "description": "Poll the status of a generation task",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "taskId": {"type": "string", "required": True, "description": "Task/artifact ID to check"},
        },
    },
    "artifact.wait": {
        "method": "wait_for_completion",
        "description": "Wait for artifact generation to complete",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "taskId": {"type": "string", "required": True, "description": "Generation task ID"},
            "timeout": {"type": "integer", "required": False, "description": "Timeout in seconds (default 300)"},
        },
    },
    # ── chat (4) ──
    "chat.ask": {
        "method": "ask",
        "description": "Ask the notebook a question",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "question": {"type": "string", "required": True, "description": "Question to ask"},
            "sourceIds": {"type": "array[string]", "required": False, "description": "Limit to specific source IDs"},
            "conversationId": {"type": "string", "required": False, "description": "Continue a conversation"},
        },
    },
    "chat.history": {
        "method": "get_history",
        "description": "Get conversation history",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "chat.clear": {
        "method": "clear_cache",
        "description": "Clear local conversation cache",
        "params": {
            "conversationId": {"type": "string", "required": False, "description": "Clear specific conversation, or all if omitted"},
        },
    },
    "chat.save": {
        "method": "configure",
        "description": "Configure chat persona and response settings for a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "goal": {"type": "string", "required": False, "description": "Chat persona: DEFAULT, CUSTOM, LEARNING_GUIDE"},
            "responseLength": {"type": "string", "required": False, "description": "Response verbosity: DEFAULT, SHORTER, LONGER"},
            "customPrompt": {"type": "string", "required": False, "description": "Custom instructions (required if goal is CUSTOM)"},
        },
    },
    # ── research (3) ──
    "research.start": {
        "method": "start",
        "description": "Start a web or Drive research session",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "query": {"type": "string", "required": True, "description": "Research query"},
            "source": {"type": "string", "required": False, "description": "web or drive (default: web)"},
            "mode": {"type": "string", "required": False, "description": "fast or deep (default: fast)"},
        },
    },
    "research.poll": {
        "method": "poll",
        "description": "Check research session status and results",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "research.import": {
        "method": "import_sources",
        "description": "Import selected research sources into the notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "taskId": {"type": "string", "required": True, "description": "Research task ID"},
            "sources": {"type": "array[string]", "required": True, "description": "Sources to import (each with url and title)"},
        },
    },
    # ── note (4) ──
    "note.create": {
        "method": "create",
        "description": "Create a new note in the notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "title": {"type": "string", "required": False, "description": "Note title (default: New Note)"},
            "content": {"type": "string", "required": False, "description": "Note content"},
        },
    },
    "note.list": {
        "method": "list",
        "description": "List notes in a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "note.update": {
        "method": "update",
        "description": "Update a note's content and title",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "noteId": {"type": "string", "required": True, "description": "Note ID"},
            "content": {"type": "string", "required": True, "description": "New content"},
            "title": {"type": "string", "required": True, "description": "New title"},
        },
    },
    "note.delete": {
        "method": "delete",
        "description": "Delete a note",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "noteId": {"type": "string", "required": True, "description": "Note ID"},
        },
    },
}


def get_schema(key: str) -> dict | None:
    """Return the schema for a given group.action key, or None if not found."""
    return SCHEMAS.get(key)


def list_schemas() -> list[str]:
    """Return a sorted list of all registered schema keys."""
    return sorted(SCHEMAS.keys())
