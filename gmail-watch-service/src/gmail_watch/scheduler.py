"""Background scheduler for periodic Pub/Sub polling."""

from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from gmail_watch.database import get_session_maker
from gmail_watch.services.watch_manager import WatchManager
from gmail_watch.settings import settings

logger = structlog.get_logger()

# Delay before starting the polling loop (seconds)
INITIAL_DELAY_SECONDS = 5


class WatchScheduler:
    """Runs periodic Pub/Sub polling in the background."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        """Return whether the scheduler is currently running."""
        return self._running

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Watch scheduler started", interval=settings.pull_interval_seconds)

    async def stop(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watch scheduler stopped")

    async def _run_loop(self) -> None:
        """Main polling loop."""
        # Initial delay to let services start
        await asyncio.sleep(INITIAL_DELAY_SECONDS)

        session_maker = get_session_maker()
        if session_maker is None:
            logger.error("Cannot run scheduler: no database session maker")
            return

        # Initialize watch on startup
        async with session_maker() as session:
            manager = WatchManager(session=session)
            result = await manager.initialize_watch()
            logger.info("Initial watch setup", result=result)

        while self._running:
            try:
                async with session_maker() as session:
                    manager = WatchManager(session=session)

                    # Check if watch needs renewal
                    check_result = await manager.check_watch_expiration()
                    if check_result.get("needs_renewal", False):
                        logger.info("Renewing Gmail watch subscription")
                        await manager.initialize_watch()

                    # Process notifications
                    result = await manager.process_notifications()

                    if result.get("replies_found", 0) > 0:
                        logger.info(
                            "Processed notifications",
                            replies_found=result["replies_found"],
                        )

            except Exception as e:
                logger.error("Error in polling loop", error=str(e))

            await asyncio.sleep(settings.pull_interval_seconds)


# Global scheduler instance
watch_scheduler = WatchScheduler()
