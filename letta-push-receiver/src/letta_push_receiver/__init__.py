"""letta-push-receiver — HTTP→subprocess bridge for local-mode Letta agents.

Producers (slackbot, gmail-watch, granola-poller, enrichment scanner,
task-completion-service) POST /push with {agent, prompt, source_ref?}.
The receiver routes to the per-source owner agent's warm subprocess
and writes the prompt to its stdin. Stream-json output is logged but
the response to the producer is fire-and-forget (returns 202 Accepted
once the prompt is queued).

Architecture mirrors pa-web-ui's subprocess_pool.py but trimmed for
push-only (no SSE subscribers, no turn-lock, no fork).
"""
__version__ = "0.1.0"
