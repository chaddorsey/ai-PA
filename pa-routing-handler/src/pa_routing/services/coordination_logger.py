"""Coordination logging utility for pattern analysis and refinement.

Logs all coordination events to Supabase for:
- Tracking agent contribution rates
- Measuring coordination efficiency
- Enabling guided refinement
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger()


class CoordinationLogger:
    """Logs coordination events to Supabase."""

    def __init__(self, supabase_client: Any):
        """Initialize with Supabase client.

        Args:
            supabase_client: Supabase client instance
        """
        self._supabase = supabase_client

    def log_event(
        self,
        event_type: str,
        task_id: str,
        identity_id: str,
        task_type: str,
        task_version: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        elapsed_ms: Optional[int] = None
    ) -> None:
        """Log a coordination event.

        Args:
            event_type: Type of event (start, agent_dispatch, agent_contributed, etc.)
            task_id: Unique task identifier
            identity_id: User identity
            task_type: Name of task type (e.g., meeting_prep)
            task_version: Version from task type YAML
            data: Event-specific data
            elapsed_ms: Elapsed time in milliseconds
        """
        record = {
            "event_type": event_type,
            "task_id": task_id,
            "identity_id": identity_id,
            "task_type": task_type,
            "task_version": task_version,
            "data": data or {},
            "elapsed_ms": elapsed_ms,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        try:
            self._supabase.table("coordination_logs").insert(record).execute()
            logger.debug(
                "coordination_event_logged",
                event_type=event_type,
                task_id=task_id,
                task_type=task_type
            )
        except Exception as e:
            logger.warning(
                "coordination_log_failed",
                event_type=event_type,
                task_id=task_id,
                error=str(e)
            )

    def query_by_task_type(
        self,
        task_type: str,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query logs for a specific task type.

        Args:
            task_type: Task type to query
            event_type: Optional filter by event type
            limit: Maximum records to return

        Returns:
            List of log records
        """
        try:
            query = (
                self._supabase.table("coordination_logs")
                .select("*")
                .eq("task_type", task_type)
            )

            if event_type:
                query = query.eq("event_type", event_type)

            result = query.order("timestamp", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.warning("coordination_query_failed", error=str(e))
            return []

    def get_agent_contribution_stats(
        self,
        task_type: str,
        since_days: int = 30
    ) -> Dict[str, Dict[str, int]]:
        """Get agent contribution statistics for refinement.

        Args:
            task_type: Task type to analyze
            since_days: Look back period in days

        Returns:
            Dict mapping agent name to {dispatches, contributions, timeouts, errors}
        """
        try:
            from datetime import timedelta

            # Calculate cutoff timestamp
            cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

            # Get all dispatch and contribution events within time window
            result = (
                self._supabase.table("coordination_logs")
                .select("event_type, data")
                .eq("task_type", task_type)
                .gte("timestamp", cutoff.isoformat())
                .in_("event_type", ["agent_dispatch", "agent_contributed", "agent_timeout", "agent_error"])
                .execute()
            )

            stats: Dict[str, Dict[str, int]] = {}

            for record in result.data or []:
                data = record.get("data") or {}
                agent = data.get("agent")
                if not agent:
                    continue

                if agent not in stats:
                    stats[agent] = {
                        "dispatches": 0,
                        "contributions": 0,
                        "timeouts": 0,
                        "errors": 0
                    }

                event_type = record["event_type"]
                if event_type == "agent_dispatch":
                    stats[agent]["dispatches"] += 1
                elif event_type == "agent_contributed":
                    stats[agent]["contributions"] += 1
                elif event_type == "agent_timeout":
                    stats[agent]["timeouts"] += 1
                elif event_type == "agent_error":
                    stats[agent]["errors"] += 1

            return stats
        except Exception as e:
            logger.warning("contribution_stats_failed", error=str(e))
            return {}
