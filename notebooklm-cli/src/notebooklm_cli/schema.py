"""Static schema registry mapping group.action keys to NotebookLM method metadata."""

from __future__ import annotations

SCHEMAS: dict[str, dict] = {
    "notebook.create": {
        "method": "createNotebook",
        "description": "Create a new notebook",
        "params": {
            "title": {"type": "string", "required": True, "description": "Notebook title"},
        },
    },
    "notebook.list": {
        "method": "listNotebooks",
        "description": "List all notebooks",
        "params": {},
    },
    "notebook.get": {
        "method": "getNotebook",
        "description": "Get details of a specific notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "notebook.delete": {
        "method": "deleteNotebook",
        "description": "Delete a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "source.add": {
        "method": "addSource",
        "description": "Add a source to a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "path": {"type": "string", "required": False, "description": "Local file path"},
            "url": {"type": "string", "required": False, "description": "URL to add as source"},
            "text": {"type": "string", "required": False, "description": "Raw text to add as source"},
        },
    },
    "source.list": {
        "method": "listSources",
        "description": "List sources in a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "source.delete": {
        "method": "deleteSource",
        "description": "Delete a source from a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "sourceId": {"type": "string", "required": True, "description": "Source ID"},
        },
    },
    "query": {
        "method": "query",
        "description": "Query a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "question": {"type": "string", "required": True, "description": "Question to ask"},
        },
    },
    "audio.generate": {
        "method": "generateAudio",
        "description": "Generate audio overview for a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
}


def get_schema(key: str) -> dict | None:
    """Return the schema for a given group.action key, or None if not found."""
    return SCHEMAS.get(key)


def list_schemas() -> list[str]:
    """Return a sorted list of all registered schema keys."""
    return sorted(SCHEMAS.keys())
