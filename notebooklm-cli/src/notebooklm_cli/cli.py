"""Click CLI for NotebookLM."""
from __future__ import annotations

import json
import sys

import click

from notebooklm_cli.bridge import call
from notebooklm_cli.fields import apply_field_mask
from notebooklm_cli.formatters import output_error, output_result, should_use_json
from notebooklm_cli.schema import get_schema, list_schemas
from notebooklm_cli.validate import validate_body


@click.group()
@click.option("--format", "format_flag", type=click.Choice(["json", "text"]), default=None)
@click.option("--body", "body_json", default=None, help="Raw JSON input (agent-first path)")
@click.option("--dry-run", is_flag=True, default=False, help="Validate + preview, no execution")
@click.option("--fields", default=None, help="Comma-separated output fields")
@click.option("--storage", default=None, help="Path to storage_state.json")
@click.pass_context
def cli(ctx, format_flag, body_json, dry_run, fields, storage):
    """NotebookLM CLI — manage notebooks, sources, and AI-generated content."""
    ctx.ensure_object(dict)
    ctx.obj["format"] = format_flag
    ctx.obj["body"] = body_json
    ctx.obj["dry_run"] = dry_run
    ctx.obj["fields"] = fields.split(",") if fields else None
    if storage:
        import os
        os.environ["NOTEBOOKLM_STORAGE"] = storage


def _run(ctx, schema_key: str, params: dict, had_convenience_flags: bool = False):
    """Core execution: parse --body, validate, dry-run, call bridge, output."""
    body_json = ctx.obj.get("body")
    dry_run = ctx.obj.get("dry_run", False)
    use_json = should_use_json(ctx.obj.get("format"))
    field_list = ctx.obj.get("fields")

    if body_json is not None:
        # Agent path: parse --body JSON
        try:
            parsed_body = json.loads(body_json)
        except json.JSONDecodeError as exc:
            click.echo(json.dumps({"error": "invalid_json", "detail": str(exc)}), nl=True)
            ctx.exit(2)
            return

        if had_convenience_flags:
            click.echo("Warning: --body provided; ignoring convenience flags", err=True)

        # Validate against schema
        errors = validate_body(schema_key, parsed_body)
        if errors:
            if dry_run:
                click.echo(json.dumps({
                    "dry_run": True,
                    "schema": schema_key,
                    "validation_errors": errors,
                }, indent=2))
                ctx.exit(2)
                return
            click.echo(json.dumps({
                "error": "validation_failed",
                "errors": errors,
            }, indent=2))
            ctx.exit(2)
            return

        final_params = parsed_body
    else:
        # Convenience-flag path: use params as-is
        final_params = params

    if dry_run:
        click.echo(json.dumps({
            "dry_run": True,
            "schema": schema_key,
            "params": final_params,
            "validation": "passed",
        }, indent=2))
        ctx.exit(0)
        return

    # Execute via bridge
    result = call(schema_key, final_params)
    if result.get("status") == "error":
        output_error(result.get("error_message", "Unknown error"), json_output=use_json)
        sys.exit(1)

    data = result.get("result", {})
    if field_list:
        data = apply_field_mask(data, field_list)
    output_result(data, json_output=use_json)


# ── schema command ──────────────────────────────────────────────────


@cli.command("schema")
@click.argument("method", required=False)
@click.option("--list", "list_all", is_flag=True, help="List all available methods")
@click.pass_context
def schema_cmd(ctx, method, list_all):
    """Show schema for a method, or list all methods."""
    if list_all:
        print("\n".join(list_schemas()))
        ctx.exit(0)
        return
    if not method:
        click.echo("Usage: notebooklm-cli schema <method> or --list", err=True)
        ctx.exit(2)
        return
    s = get_schema(method)
    if s is None:
        click.echo(f"Unknown method: {method}", err=True)
        ctx.exit(1)
        return
    print(json.dumps(s, indent=2))


# ── health command ──────────────────────────────────────────────────


@cli.command("health")
@click.pass_context
def health(ctx):
    """Check NotebookLM authentication status."""
    import os
    from pathlib import Path

    fmt = ctx.obj.get("format")
    use_json = should_use_json(fmt)

    storage = os.environ.get("NOTEBOOKLM_STORAGE") or os.environ.get("NOTEBOOKLM_HOME")
    if storage:
        state_path = Path(storage) if storage.endswith(".json") else Path(storage) / "storage_state.json"
    else:
        state_path = Path.home() / ".notebooklm" / "storage_state.json"

    if not state_path.exists():
        output_result(
            {"status": "error", "error_message": f"Storage not found: {state_path}. Run 'notebooklm login'"},
            json_output=use_json,
        )
        return

    try:
        data = json.loads(state_path.read_text())
        cookies = {
            c["name"]
            for c in data.get("cookies", [])
            if c.get("domain", "").endswith("google.com")
        }
        has_sid = "SID" in cookies
    except Exception as e:
        output_result(
            {"status": "error", "error_message": f"Cannot read storage: {e}"},
            json_output=use_json,
        )
        return

    if not has_sid:
        output_result(
            {"status": "error", "error_message": "SID cookie missing. Run 'notebooklm login'"},
            json_output=use_json,
        )
        return

    output_result(
        {"status": "ok", "auth": "valid", "storagePath": str(state_path), "cookieCount": len(cookies)},
        json_output=use_json,
    )


# ── notebook group ──────────────────────────────────────────────────


@cli.group()
def notebook():
    """Manage notebooks."""


@notebook.command("create")
@click.option("--title", default=None, help="Notebook title")
@click.pass_context
def notebook_create(ctx, title):
    """Create a new notebook."""
    params, had = _collect(title=title)
    _run(ctx, "notebook.create", params, had_convenience_flags=had)


@notebook.command("list")
@click.pass_context
def notebook_list(ctx):
    """List all notebooks."""
    _run(ctx, "notebook.list", {})


@notebook.command("get")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.pass_context
def notebook_get(ctx, notebook_id):
    """Get notebook details."""
    params, had = _collect(notebookId=notebook_id)
    _run(ctx, "notebook.get", params, had_convenience_flags=had)


@notebook.command("delete")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.pass_context
def notebook_delete(ctx, notebook_id):
    """Delete a notebook."""
    params, had = _collect(notebookId=notebook_id)
    _run(ctx, "notebook.delete", params, had_convenience_flags=had)


@notebook.command("rename")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--new-title", default=None, help="New title")
@click.pass_context
def notebook_rename(ctx, notebook_id, new_title):
    """Rename a notebook."""
    params, had = _collect(notebookId=notebook_id, newTitle=new_title)
    _run(ctx, "notebook.rename", params, had_convenience_flags=had)


@notebook.command("describe")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.pass_context
def notebook_describe(ctx, notebook_id):
    """Get AI-generated notebook description."""
    params, had = _collect(notebookId=notebook_id)
    _run(ctx, "notebook.describe", params, had_convenience_flags=had)


@notebook.command("topics")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.pass_context
def notebook_topics(ctx, notebook_id):
    """Get suggested topics for a notebook."""
    params, had = _collect(notebookId=notebook_id)
    _run(ctx, "notebook.topics", params, had_convenience_flags=had)


# ── source group ────────────────────────────────────────────────────


@cli.group()
def source():
    """Manage notebook sources."""


@source.command("add-url")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--url", default=None, help="URL to add")
@click.option("--wait/--no-wait", default=False, help="Wait for processing")
@click.pass_context
def source_add_url(ctx, notebook_id, url, wait):
    """Add a URL source to a notebook."""
    params, had = _collect(notebookId=notebook_id, url=url)
    if wait:
        params["wait"] = True
        had = True
    _run(ctx, "source.add-url", params, had_convenience_flags=had)


@source.command("add-text")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--title", default=None, help="Source title")
@click.option("--content", default=None, help="Text content")
@click.option("--wait/--no-wait", default=False, help="Wait for processing")
@click.pass_context
def source_add_text(ctx, notebook_id, title, content, wait):
    """Add a text source to a notebook."""
    params, had = _collect(notebookId=notebook_id, title=title, content=content)
    if wait:
        params["wait"] = True
        had = True
    _run(ctx, "source.add-text", params, had_convenience_flags=had)


@source.command("add-file")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--file-path", default=None, help="Path to file")
@click.option("--wait/--no-wait", default=False, help="Wait for processing")
@click.pass_context
def source_add_file(ctx, notebook_id, file_path, wait):
    """Add a file source (PDF, DOCX, MD, etc.)."""
    params, had = _collect(notebookId=notebook_id, filePath=file_path)
    if wait:
        params["wait"] = True
        had = True
    _run(ctx, "source.add-file", params, had_convenience_flags=had)


@source.command("add-youtube")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--url", default=None, help="YouTube URL")
@click.option("--wait/--no-wait", default=False, help="Wait for processing")
@click.pass_context
def source_add_youtube(ctx, notebook_id, url, wait):
    """Add a YouTube video as a source."""
    params, had = _collect(notebookId=notebook_id, url=url)
    if wait:
        params["wait"] = True
        had = True
    _run(ctx, "source.add-youtube", params, had_convenience_flags=had)


@source.command("add-drive")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--file-id", default=None, help="Google Drive file ID")
@click.option("--title", default=None, help="Display title")
@click.option("--mime-type", default=None, help="MIME type")
@click.option("--wait/--no-wait", default=False, help="Wait for processing")
@click.pass_context
def source_add_drive(ctx, notebook_id, file_id, title, mime_type, wait):
    """Add a Google Drive document as a source."""
    params, had = _collect(notebookId=notebook_id, fileId=file_id, title=title, mimeType=mime_type)
    if wait:
        params["wait"] = True
        had = True
    _run(ctx, "source.add-drive", params, had_convenience_flags=had)


@source.command("list")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.pass_context
def source_list(ctx, notebook_id):
    """List sources in a notebook."""
    params, had = _collect(notebookId=notebook_id)
    _run(ctx, "source.list", params, had_convenience_flags=had)


@source.command("get")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--source-id", default=None, help="Source ID")
@click.pass_context
def source_get(ctx, notebook_id, source_id):
    """Get source details."""
    params, had = _collect(notebookId=notebook_id, sourceId=source_id)
    _run(ctx, "source.get", params, had_convenience_flags=had)


@source.command("delete")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--source-id", default=None, help="Source ID")
@click.pass_context
def source_delete(ctx, notebook_id, source_id):
    """Delete a source from a notebook."""
    params, had = _collect(notebookId=notebook_id, sourceId=source_id)
    _run(ctx, "source.delete", params, had_convenience_flags=had)


@source.command("rename")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--source-id", default=None, help="Source ID")
@click.option("--new-title", default=None, help="New title")
@click.pass_context
def source_rename(ctx, notebook_id, source_id, new_title):
    """Rename a source."""
    params, had = _collect(notebookId=notebook_id, sourceId=source_id, newTitle=new_title)
    _run(ctx, "source.rename", params, had_convenience_flags=had)


@source.command("refresh")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--source-id", default=None, help="Source ID")
@click.pass_context
def source_refresh(ctx, notebook_id, source_id):
    """Refresh a source to pick up changes."""
    params, had = _collect(notebookId=notebook_id, sourceId=source_id)
    _run(ctx, "source.refresh", params, had_convenience_flags=had)


@source.command("guide")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--source-id", default=None, help="Source ID")
@click.pass_context
def source_guide(ctx, notebook_id, source_id):
    """Get the AI-generated source guide/summary."""
    params, had = _collect(notebookId=notebook_id, sourceId=source_id)
    _run(ctx, "source.guide", params, had_convenience_flags=had)


@source.command("fulltext")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--source-id", default=None, help="Source ID")
@click.pass_context
def source_fulltext(ctx, notebook_id, source_id):
    """Get source full text / freshness check."""
    params, had = _collect(notebookId=notebook_id, sourceId=source_id)
    _run(ctx, "source.fulltext", params, had_convenience_flags=had)


# ── artifact group ──────────────────────────────────────────────────


@cli.group()
def artifact():
    """Manage AI-generated artifacts."""


@artifact.command("generate")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--type", "artifact_type", default=None,
              type=click.Choice(["audio", "video", "report", "quiz", "flashcards",
                                 "infographic", "slide-deck", "data-table", "mind-map"]))
@click.option("--instructions", default=None, help="Generation instructions")
@click.option("--language", default=None, help="Language code (default: en)")
@click.pass_context
def artifact_generate(ctx, notebook_id, artifact_type, instructions, language):
    """Generate an artifact (audio, video, report, quiz, etc.)."""
    params, had = _collect(notebookId=notebook_id, instructions=instructions, language=language)
    if artifact_type is not None:
        params["type"] = artifact_type
        had = True
    _run(ctx, "artifact.generate", params, had_convenience_flags=had)


@artifact.command("list")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.pass_context
def artifact_list(ctx, notebook_id):
    """List artifacts in a notebook."""
    params, had = _collect(notebookId=notebook_id)
    _run(ctx, "artifact.list", params, had_convenience_flags=had)


@artifact.command("get")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--artifact-id", default=None, help="Artifact ID")
@click.pass_context
def artifact_get(ctx, notebook_id, artifact_id):
    """Get artifact details."""
    params, had = _collect(notebookId=notebook_id, artifactId=artifact_id)
    _run(ctx, "artifact.get", params, had_convenience_flags=had)


@artifact.command("delete")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--artifact-id", default=None, help="Artifact ID")
@click.pass_context
def artifact_delete(ctx, notebook_id, artifact_id):
    """Delete an artifact."""
    params, had = _collect(notebookId=notebook_id, artifactId=artifact_id)
    _run(ctx, "artifact.delete", params, had_convenience_flags=had)


@artifact.command("rename")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--artifact-id", default=None, help="Artifact ID")
@click.option("--new-title", default=None, help="New title")
@click.pass_context
def artifact_rename(ctx, notebook_id, artifact_id, new_title):
    """Rename an artifact."""
    params, had = _collect(notebookId=notebook_id, artifactId=artifact_id, newTitle=new_title)
    _run(ctx, "artifact.rename", params, had_convenience_flags=had)


@artifact.command("download")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--output-path", default=None, help="Output file path")
@click.option("--artifact-id", default=None, help="Artifact ID")
@click.option("--type", "artifact_type", default=None, help="Artifact type")
@click.pass_context
def artifact_download(ctx, notebook_id, output_path, artifact_id, artifact_type):
    """Download an artifact to a local file."""
    params, had = _collect(notebookId=notebook_id, outputPath=output_path, artifactId=artifact_id)
    if artifact_type is not None:
        params["type"] = artifact_type
        had = True
    _run(ctx, "artifact.download", params, had_convenience_flags=had)


@artifact.command("status")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--task-id", default=None, help="Task/artifact ID")
@click.pass_context
def artifact_status(ctx, notebook_id, task_id):
    """Check generation status."""
    params, had = _collect(notebookId=notebook_id, taskId=task_id)
    _run(ctx, "artifact.status", params, had_convenience_flags=had)


@artifact.command("wait")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--task-id", default=None, help="Generation task ID")
@click.option("--timeout", default=None, type=int, help="Timeout in seconds (default 300)")
@click.pass_context
def artifact_wait(ctx, notebook_id, task_id, timeout):
    """Wait for artifact generation to complete."""
    params, had = _collect(notebookId=notebook_id, taskId=task_id, timeout=timeout)
    _run(ctx, "artifact.wait", params, had_convenience_flags=had)


# ── chat group ──────────────────────────────────────────────────────


@cli.group()
def chat():
    """Chat with notebooks."""


@chat.command("ask")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--question", default=None, help="Question to ask")
@click.option("--conversation-id", default=None, help="Continue a conversation")
@click.pass_context
def chat_ask(ctx, notebook_id, question, conversation_id):
    """Ask a question about the notebook."""
    params, had = _collect(notebookId=notebook_id, question=question, conversationId=conversation_id)
    _run(ctx, "chat.ask", params, had_convenience_flags=had)


@chat.command("history")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.pass_context
def chat_history(ctx, notebook_id):
    """Get conversation history."""
    params, had = _collect(notebookId=notebook_id)
    _run(ctx, "chat.history", params, had_convenience_flags=had)


@chat.command("clear")
@click.option("--conversation-id", default=None, help="Conversation to clear (all if omitted)")
@click.pass_context
def chat_clear(ctx, conversation_id):
    """Clear conversation cache."""
    params, had = _collect(conversationId=conversation_id)
    _run(ctx, "chat.clear", params, had_convenience_flags=had)


@chat.command("save")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--goal", default=None, help="Chat persona: DEFAULT, CUSTOM, LEARNING_GUIDE")
@click.option("--response-length", default=None, help="Response verbosity: DEFAULT, SHORTER, LONGER")
@click.option("--custom-prompt", default=None, help="Custom instructions (for CUSTOM goal)")
@click.pass_context
def chat_save(ctx, notebook_id, goal, response_length, custom_prompt):
    """Configure chat persona and response settings."""
    params, had = _collect(notebookId=notebook_id, goal=goal, responseLength=response_length, customPrompt=custom_prompt)
    _run(ctx, "chat.save", params, had_convenience_flags=had)


# ── research group ──────────────────────────────────────────────────


@cli.group()
def research():
    """Web and Drive research."""


@research.command("start")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--query", default=None, help="Research query")
@click.option("--source", "research_source", default=None, help="web or drive")
@click.option("--mode", default=None, help="fast or deep")
@click.pass_context
def research_start(ctx, notebook_id, query, research_source, mode):
    """Start a web or Drive research session."""
    params, had = _collect(notebookId=notebook_id, query=query, mode=mode)
    if research_source is not None:
        params["source"] = research_source
        had = True
    _run(ctx, "research.start", params, had_convenience_flags=had)


@research.command("poll")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.pass_context
def research_poll(ctx, notebook_id):
    """Check research session status."""
    params, had = _collect(notebookId=notebook_id)
    _run(ctx, "research.poll", params, had_convenience_flags=had)


@research.command("import")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--task-id", default=None, help="Research task ID")
@click.pass_context
def research_import(ctx, notebook_id, task_id):
    """Import discovered research sources into the notebook."""
    params, had = _collect(notebookId=notebook_id, taskId=task_id)
    _run(ctx, "research.import", params, had_convenience_flags=had)


# ── note group ──────────────────────────────────────────────────────


@cli.group()
def note():
    """Manage notebook notes."""


@note.command("create")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--title", default=None, help="Note title")
@click.option("--content", default=None, help="Note content")
@click.pass_context
def note_create(ctx, notebook_id, title, content):
    """Create a new note."""
    params, had = _collect(notebookId=notebook_id, title=title, content=content)
    _run(ctx, "note.create", params, had_convenience_flags=had)


@note.command("list")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.pass_context
def note_list(ctx, notebook_id):
    """List notes in a notebook."""
    params, had = _collect(notebookId=notebook_id)
    _run(ctx, "note.list", params, had_convenience_flags=had)


@note.command("update")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--note-id", default=None, help="Note ID")
@click.option("--title", default=None, help="New title")
@click.option("--content", default=None, help="New content")
@click.pass_context
def note_update(ctx, notebook_id, note_id, title, content):
    """Update a note."""
    params, had = _collect(notebookId=notebook_id, noteId=note_id, title=title, content=content)
    _run(ctx, "note.update", params, had_convenience_flags=had)


@note.command("delete")
@click.option("--notebook-id", default=None, help="Notebook ID")
@click.option("--note-id", default=None, help="Note ID")
@click.pass_context
def note_delete(ctx, notebook_id, note_id):
    """Delete a note."""
    params, had = _collect(notebookId=notebook_id, noteId=note_id)
    _run(ctx, "note.delete", params, had_convenience_flags=had)


# ── helpers ─────────────────────────────────────────────────────────


def _collect(**kwargs) -> tuple[dict, bool]:
    """Build params dict from convenience flags, stripping None values.

    Returns (params, had_convenience_flags).
    """
    cleaned = {k: v for k, v in kwargs.items() if v is not None}
    return cleaned, bool(cleaned)
