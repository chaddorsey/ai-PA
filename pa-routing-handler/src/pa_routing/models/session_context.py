"""Session context for multi-agent orchestration (Pattern 2).

In-memory session context for tracking actions across agent interactions.
Zero extra SDK calls - all state managed locally.
"""

from dataclasses import dataclass, field
from datetime import datetime

MAX_CONTEXT_ENTRIES = 5


@dataclass
class SessionContext:
    """
    In-memory session context for multi-agent orchestration.

    Pattern 2: After each sub-agent call, append action summary.
    Before any agent call, format context and prepend to message.
    Zero extra SDK calls - all in-memory.
    """

    entries: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    def append(self, agent: str, action: str) -> None:
        """Add agent action to context after sub-agent completes."""
        self.entries.append({
            "agent": agent,
            "action": action,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.last_activity = datetime.utcnow()

    def format_for_injection(self, max_entries: int = MAX_CONTEXT_ENTRIES) -> str:
        """
        Format context as string to prepend to messages.
        Returns empty string if no context (zero overhead).
        """
        if not self.entries:
            return ""

        recent = self.entries[-max_entries:]
        lines = [f"[Session context - {len(self.entries)} prior actions:]"]
        for entry in recent:
            lines.append(f"  - {entry['agent']}: {entry['action']}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear session context (e.g., on explicit user request)."""
        self.entries.clear()
        self.last_activity = datetime.utcnow()

    @property
    def entry_count(self) -> int:
        """Number of entries in context."""
        return len(self.entries)
