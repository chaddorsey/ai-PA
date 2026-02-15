import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

import httpx

from app.checkpoint import CheckpointDB
from app.notifications import NotificationManager

logger = logging.getLogger(__name__)

COST_PER_DOC = 116.0 / 44353  # ~$0.00262 per doc from pilot estimate
ERROR_RATE_WINDOW = 50
ERROR_RATE_THRESHOLD = 0.10
SERVICE_RETRY_INTERVAL = 30
PAUSE_REMINDER_INTERVAL = 300  # 5 minutes
NEO4J_CACHE_TTL = 60


class BackfillRunner:
    def __init__(
        self,
        db: CheckpointDB,
        notifications: NotificationManager,
        extract_url: str = "http://drive-rag-service:8000/v1/entities/extract",
        supabase_dsn: str = "",
    ):
        self.db = db
        self.notifications = notifications
        self.extract_url = extract_url
        self.supabase_dsn = supabase_dsn

        self.state = "idle"
        self._pause_requested = False
        self._task: Optional[asyncio.Task] = None
        self._client = httpx.AsyncClient(timeout=120.0)

        # Rate tracking
        self._timings: deque[float] = deque(maxlen=100)
        self._started_at: Optional[float] = None

        # Error rate tracking
        self._recent_results: deque[str] = deque(maxlen=ERROR_RATE_WINDOW)

        # SSE event callback
        self.on_event: Optional[Callable[[dict], Awaitable[None]]] = None

        # Neo4j stats cache
        self._neo4j_stats: dict = {}
        self._neo4j_stats_at: float = 0

    async def load_queue_from_supabase(self) -> int:
        """Fetch document IDs from Supabase and load into checkpoint DB."""
        import subprocess
        result = subprocess.run(
            [
                "docker", "exec", "supabase-db", "psql",
                "-U", "postgres", "-d", "postgres", "-t", "-A", "-c",
                "SELECT drive_file_id FROM rag.document_state ORDER BY modified_time DESC;",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to query Supabase: {result.stderr}")

        file_ids = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        await self.db.load_documents(file_ids)
        return len(file_ids)

    async def start(self) -> dict:
        if self.state == "running":
            return {"status": "already_running"}

        counts = await self.db.get_counts()
        if counts["total"] == 0:
            count = await self.load_queue_from_supabase()
            logger.info(f"Loaded {count} documents from Supabase")

        self.state = "running"
        self._pause_requested = False
        self._started_at = self._started_at or time.time()
        await self.db.set_runner_state("running")

        self._task = asyncio.create_task(self._run_loop())
        return {"status": "started"}

    async def pause(self) -> dict:
        if self.state != "running":
            return {"status": "not_running"}
        self._pause_requested = True
        return {"status": "pause_requested"}

    async def resume(self) -> dict:
        return await self.start()

    async def _run_loop(self):
        try:
            while not self._pause_requested:
                file_id = await self.db.get_next_pending()
                if file_id is None:
                    self.state = "completed"
                    await self.db.set_runner_state("completed")
                    counts = await self.db.get_counts()
                    await self.notifications.send_notification(
                        "Backfill Complete",
                        f"{counts['total']} docs processed. {counts['success']} ok, {counts['skipped']} skip, {counts['error']} err.",
                    )
                    await self._emit_event("completed", counts)
                    return

                start = time.time()
                result = await self._process_one(file_id)
                elapsed = time.time() - start

                self._record_timing(elapsed)
                self._recent_results.append(result)
                self._check_error_rate()

                counts = await self.db.get_counts()
                await self._emit_event("progress", {
                    **counts,
                    "last_file_id": file_id,
                    "last_result": result,
                    "rate": self.get_rate(),
                    "elapsed": time.time() - self._started_at if self._started_at else 0,
                })

            # Pause requested
            self.state = "paused"
            await self.db.set_runner_state("paused")
            await self._emit_event("paused", await self.db.get_counts())

        except Exception as e:
            logger.error(f"Runner loop error: {e}", exc_info=True)
            self.state = "paused"
            await self.db.set_runner_state("paused")
            await self.notifications.send_notification(
                "Backfill Error", f"Runner crashed: {str(e)[:100]}"
            )

    async def _process_one(self, file_id: str) -> str:
        try:
            response = await self._client.post(f"{self.extract_url}/{file_id}")
            data = response.json()
            status = data.get("status", "error")
            if status == "ok":
                await self.db.mark_document(file_id, "success")
                return "success"
            elif status == "skipped":
                await self.db.mark_document(file_id, "skipped")
                return "skipped"
            else:
                error_msg = data.get("error", data.get("detail", str(data)))
                await self.db.mark_document(file_id, "error", error_message=error_msg)
                return "error"
        except httpx.ConnectError:
            await self.db.mark_document(file_id, "error", error_message="service unreachable")
            await self._handle_service_down()
            return "error"
        except httpx.TimeoutException:
            await self.db.mark_document(file_id, "error", error_message="timeout (120s)")
            return "error"
        except Exception as e:
            await self.db.mark_document(file_id, "error", error_message=str(e)[:200])
            return "error"

    async def _handle_service_down(self):
        self._pause_requested = True
        await self.notifications.send_notification(
            "Backfill Paused",
            "drive-rag-service unreachable. Pausing until service returns.",
        )
        logger.warning("drive-rag-service unreachable, pausing runner")

    def _check_error_rate(self):
        if len(self._recent_results) < ERROR_RATE_WINDOW:
            return
        error_count = sum(1 for r in self._recent_results if r == "error")
        rate = error_count / len(self._recent_results)
        if rate > ERROR_RATE_THRESHOLD:
            asyncio.create_task(
                self.notifications.send_notification(
                    "High Error Rate",
                    f"{rate:.0%} errors in last {ERROR_RATE_WINDOW} docs.",
                )
            )

    def _record_timing(self, elapsed: float):
        self._timings.append(elapsed)

    def get_rate(self) -> float:
        if not self._timings:
            return 0.0
        avg = sum(self._timings) / len(self._timings)
        return 1.0 / avg if avg > 0 else 0.0

    def get_eta_seconds(self, pending: int) -> float:
        rate = self.get_rate()
        if rate <= 0:
            return 0.0
        return pending / rate

    def get_cost_estimate(self, processed: int) -> float:
        return processed * COST_PER_DOC

    async def get_neo4j_stats(self) -> dict:
        now = time.time()
        if now - self._neo4j_stats_at < NEO4J_CACHE_TTL and self._neo4j_stats:
            return self._neo4j_stats

        try:
            import subprocess
            result = subprocess.run(
                [
                    "docker", "exec", "graphiti-neo4j", "cypher-shell",
                    "-u", "neo4j", "-p", "demodemo",
                    "MATCH (n) RETURN labels(n)[0] as type, count(n) as cnt ORDER BY cnt DESC;",
                ],
                capture_output=True, text=True, timeout=10,
            )
            stats = {}
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n")[1:]:  # skip header
                    parts = line.split(",")
                    if len(parts) == 2:
                        label = parts[0].strip().strip('"')
                        count = int(parts[1].strip())
                        stats[label] = count

            rel_result = subprocess.run(
                [
                    "docker", "exec", "graphiti-neo4j", "cypher-shell",
                    "-u", "neo4j", "-p", "demodemo",
                    "MATCH ()-[r]->() RETURN count(r) as cnt;",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if rel_result.returncode == 0:
                for line in rel_result.stdout.strip().split("\n")[1:]:
                    stats["relationships"] = int(line.strip())

            self._neo4j_stats = stats
            self._neo4j_stats_at = now
        except Exception as e:
            logger.warning(f"Failed to fetch Neo4j stats: {e}")

        return self._neo4j_stats

    async def _emit_event(self, event_type: str, data: dict):
        if self.on_event:
            await self.on_event({"type": event_type, **data})

    async def get_status(self) -> dict:
        counts = await self.db.get_counts()
        processed = counts["success"] + counts["skipped"] + counts["error"]
        neo4j_stats = await self.get_neo4j_stats()
        return {
            "state": self.state,
            **counts,
            "processed": processed,
            "rate": self.get_rate(),
            "eta_seconds": self.get_eta_seconds(counts["pending"]),
            "elapsed": time.time() - self._started_at if self._started_at else 0,
            "cost_estimate": self.get_cost_estimate(processed),
            "neo4j": neo4j_stats,
        }

    async def shutdown(self):
        await self._client.aclose()
