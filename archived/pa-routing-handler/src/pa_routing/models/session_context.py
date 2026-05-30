"""Session context for multi-agent orchestration (Pattern 2).

In-memory session context for tracking actions across agent interactions.
Zero extra SDK calls - all state managed locally.

Enhanced with:
- Conversation thread tracking for contextual routing
- Actionable refs for follow-up operations (e.g., updating just-created events)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pa_routing.models.conversation_thread import ConversationThread, ThreadStatus

MAX_CONTEXT_ENTRIES = 5
MAX_THREADS = 20  # Keep last N threads for context
MAX_REFS_IN_INJECTION = 3  # Only include refs from last N entries


@dataclass
class SessionContext:
    """
    In-memory session context for multi-agent orchestration.

    Pattern 2: After each sub-agent call, append action summary.
    Before any agent call, format context and prepend to message.
    Zero extra SDK calls - all in-memory.

    Enhanced with:
    - Thread tracking for contextual routing and threaded UI
    - Actionable refs for follow-up operations (IDs, titles, etc.)
    """

    entries: list[dict] = field(default_factory=list)
    threads: list[ConversationThread] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    # Track the most recent completed response for contextual routing
    last_responding_agent_id: Optional[str] = None
    last_responding_agent_name: Optional[str] = None
    last_response_time: Optional[datetime] = None

    def append(self, agent: str, action: str, refs: dict | None = None) -> None:
        """
        Add agent action to context after sub-agent completes.

        Args:
            agent: Name of the responding agent
            action: Summary of the action taken
            refs: Optional dict of actionable references (IDs, titles, etc.)
        """
        entry = {
            "agent": agent,
            "action": action,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if refs:
            entry["refs"] = refs
        self.entries.append(entry)
        self.last_activity = datetime.utcnow()

    def format_for_injection(self, max_entries: int = MAX_CONTEXT_ENTRIES) -> str:
        """
        Format context as string to prepend to messages.
        Returns empty string if no context (zero overhead).

        Includes:
        - Recent action summaries for context awareness
        - Recent refs for actionable follow-ups (IDs, titles, etc.)
        """
        if not self.entries:
            return ""

        recent = self.entries[-max_entries:]
        lines = [f"[Session context - {len(self.entries)} prior actions:]"]
        for entry in recent:
            lines.append(f"  - {entry['agent']}: {entry['action']}")

        # Add recent refs for actionable follow-ups
        refs_lines = self._format_recent_refs()
        if refs_lines:
            lines.append(refs_lines)

        return "\n".join(lines)

    def get_recent_refs(self, max_entries: int = MAX_REFS_IN_INJECTION) -> list[dict]:
        """
        Get refs from the most recent entries that have them.

        Args:
            max_entries: Maximum number of ref entries to return

        Returns:
            List of dicts with agent, refs, and timestamp
        """
        refs_entries = []
        # Walk backwards through entries to get most recent refs
        for entry in reversed(self.entries):
            if entry.get("refs"):
                refs_entries.append({
                    "agent": entry["agent"],
                    "refs": entry["refs"],
                    "timestamp": entry["timestamp"],
                })
                if len(refs_entries) >= max_entries:
                    break
        # Return in chronological order
        return list(reversed(refs_entries))

    def _format_recent_refs(self) -> str:
        """Format recent refs as injection string."""
        refs_entries = self.get_recent_refs()
        if not refs_entries:
            return ""

        lines = ["[Recent actionable refs:]"]
        for entry in refs_entries:
            agent = entry["agent"]
            refs = entry["refs"]
            # Format refs as key=value pairs for readability
            ref_parts = [f"{k}={v}" for k, v in refs.items()]
            lines.append(f"  - {agent}: {', '.join(ref_parts)}")

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear session context (e.g., on explicit user request)."""
        self.entries.clear()
        self.threads.clear()
        self.last_responding_agent_id = None
        self.last_responding_agent_name = None
        self.last_response_time = None
        self.last_activity = datetime.utcnow()

    @property
    def entry_count(self) -> int:
        """Number of entries in context."""
        return len(self.entries)

    # ========== Thread Management ==========

    def create_thread(self, user_message: str, request_id: Optional[str] = None) -> ConversationThread:
        """
        Create a new conversation thread for a user request.

        Returns the thread so caller can update it as response streams.
        """
        thread = ConversationThread(user_message=user_message)
        if request_id:
            thread.request_id = request_id

        self.threads.append(thread)
        self.last_activity = datetime.utcnow()

        # Trim old threads if we have too many
        if len(self.threads) > MAX_THREADS:
            self.threads = self.threads[-MAX_THREADS:]

        return thread

    def get_thread(self, request_id: str) -> Optional[ConversationThread]:
        """Get a thread by its request ID."""
        for thread in self.threads:
            if thread.request_id == request_id:
                return thread
        return None

    def get_active_threads(self) -> list[ConversationThread]:
        """Get all threads that are still pending or streaming."""
        return [t for t in self.threads if t.is_active]

    def get_last_completed_thread(self) -> Optional[ConversationThread]:
        """Get the most recently completed thread."""
        completed = [t for t in self.threads if t.status == ThreadStatus.COMPLETE]
        if not completed:
            return None
        return max(completed, key=lambda t: t.completed_at or t.updated_at)

    def complete_thread(
        self,
        request_id: str,
        agent_id: str,
        agent_name: str,
        response_content: str = ""
    ) -> Optional[ConversationThread]:
        """
        Mark a thread as complete and update last-responding agent.

        Called when an agent finishes responding to a request.
        """
        thread = self.get_thread(request_id)
        if thread:
            thread.agent_id = agent_id
            thread.agent_name = agent_name
            thread.complete(response_content)

            # Update last-responding agent for contextual routing
            self.last_responding_agent_id = agent_id
            self.last_responding_agent_name = agent_name
            self.last_response_time = datetime.utcnow()
            self.last_activity = datetime.utcnow()

        return thread

    def get_contextual_agent(self) -> Optional[tuple[str, str]]:
        """
        Get the agent that should handle contextual follow-ups.

        Returns (agent_id, agent_name) if there's a recent response,
        None otherwise.
        """
        if self.last_responding_agent_id and self.last_response_time:
            return (self.last_responding_agent_id, self.last_responding_agent_name or "Unknown")
        return None

    def get_recent_threads(self, limit: int = 10) -> list[dict]:
        """Get recent threads as dictionaries for API response."""
        recent = self.threads[-limit:]
        return [t.to_dict() for t in recent]
