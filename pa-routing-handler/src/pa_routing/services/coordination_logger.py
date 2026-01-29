"""Coordination logging utility for pattern analysis and refinement.

Logs all coordination events to PostgREST for:
- Tracking agent contribution rates
- Measuring coordination efficiency
- Enabling guided refinement
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
import structlog

logger = structlog.get_logger()


class CoordinationLogger:
    """Logs coordination events to PostgREST."""

    def __init__(self, postgrest_url: str, service_key: str):
        """Initialize with PostgREST URL.

        Args:
            postgrest_url: PostgREST base URL (e.g., http://supabase-rest:3000)
            service_key: Service key for authentication
        """
        self._base_url = postgrest_url.rstrip("/")
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

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
            with httpx.Client(timeout=5.0) as client:
                response = client.post(
                    f"{self._base_url}/coordination_logs",
                    headers=self._headers,
                    json=record
                )
                response.raise_for_status()
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
            params = {
                "task_type": f"eq.{task_type}",
                "order": "timestamp.desc",
                "limit": str(limit),
            }
            if event_type:
                params["event_type"] = f"eq.{event_type}"

            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self._base_url}/coordination_logs",
                    headers=self._headers,
                    params=params
                )
                response.raise_for_status()
                return response.json()
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

            params = {
                "task_type": f"eq.{task_type}",
                "timestamp": f"gte.{cutoff.isoformat()}",
                "event_type": "in.(agent_dispatch,agent_contributed,agent_timeout,agent_error)",
                "select": "event_type,data",
            }

            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self._base_url}/coordination_logs",
                    headers=self._headers,
                    params=params
                )
                response.raise_for_status()
                records = response.json()

            stats: Dict[str, Dict[str, int]] = {}

            for record in records:
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

                evt = record["event_type"]
                if evt == "agent_dispatch":
                    stats[agent]["dispatches"] += 1
                elif evt == "agent_contributed":
                    stats[agent]["contributions"] += 1
                elif evt == "agent_timeout":
                    stats[agent]["timeouts"] += 1
                elif evt == "agent_error":
                    stats[agent]["errors"] += 1

            return stats
        except Exception as e:
            logger.warning("contribution_stats_failed", error=str(e))
            return {}

    def get_execution_summary(
        self,
        task_type: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get execution summary for refinement review.

        Args:
            task_type: Task type to analyze
            limit: Number of recent executions to analyze

        Returns:
            Summary dict with statistics and patterns
        """
        try:
            # Get complete events
            params = {
                "task_type": f"eq.{task_type}",
                "event_type": "eq.complete",
                "order": "timestamp.desc",
                "limit": str(limit),
            }

            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self._base_url}/coordination_logs",
                    headers=self._headers,
                    params=params
                )
                response.raise_for_status()
                completions = response.json()

            if not completions:
                return {"executions": 0, "message": "No executions found"}

            # Calculate statistics
            times = [r.get("elapsed_ms", 0) for r in completions if r.get("elapsed_ms")]
            avg_time = sum(times) / len(times) if times else 0

            # Get agent stats
            agent_stats = self.get_agent_contribution_stats(task_type)

            # Get question patterns from start events
            params = {
                "task_type": f"eq.{task_type}",
                "event_type": "eq.start",
                "order": "timestamp.desc",
                "limit": str(limit),
                "select": "data",
            }

            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self._base_url}/coordination_logs",
                    headers=self._headers,
                    params=params
                )
                response.raise_for_status()
                starts = response.json()

            question_counts: Dict[str, int] = {}
            for start in starts:
                questions = start.get("data", {}).get("questions_asked", [])
                for q in questions:
                    question_counts[q] = question_counts.get(q, 0) + 1

            return {
                "executions": len(completions),
                "avg_time_ms": int(avg_time),
                "agent_stats": agent_stats,
                "question_patterns": question_counts,
                "recent_task_ids": [r.get("task_id") for r in completions[:5]]
            }

        except Exception as e:
            logger.warning("execution_summary_failed", error=str(e))
            return {"error": str(e)}
