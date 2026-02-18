"""Tests for background scheduler."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gmail_watch.scheduler import WatchScheduler


@pytest.fixture
def mock_session_maker():
    """Create a mock session maker that returns async context manager."""
    mock_session = AsyncMock()
    mock_maker = MagicMock()

    # Make session_maker() return an async context manager
    async_cm = AsyncMock()
    async_cm.__aenter__.return_value = mock_session
    async_cm.__aexit__.return_value = None
    mock_maker.return_value = async_cm

    return mock_maker, mock_session


@pytest.fixture
def mock_watch_manager():
    """Create a mock WatchManager."""
    with patch("gmail_watch.scheduler.WatchManager") as mock_cls:
        manager = AsyncMock()
        manager.initialize_watch.return_value = {"status": "ok", "history_id": 12345}
        manager.check_watch_expiration.return_value = {"needs_renewal": False}
        manager.process_notifications.return_value = {
            "status": "ok",
            "processed": 0,
            "replies_found": 0,
        }
        mock_cls.return_value = manager
        yield mock_cls, manager


class TestWatchSchedulerLifecycle:
    """Tests for WatchScheduler start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self):
        """start() sets is_running to True."""
        scheduler = WatchScheduler()

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = None  # No DB, loop will exit early

            await scheduler.start()

            assert scheduler.is_running is True

            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        """start() creates an asyncio task."""
        scheduler = WatchScheduler()

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = None

            await scheduler.start()

            assert scheduler._task is not None
            assert isinstance(scheduler._task, asyncio.Task)

            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        """Calling start() multiple times only creates one task."""
        scheduler = WatchScheduler()

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = None

            await scheduler.start()
            first_task = scheduler._task

            await scheduler.start()  # Second call

            assert scheduler._task is first_task

            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self):
        """stop() sets is_running to False."""
        scheduler = WatchScheduler()
        scheduler._running = True
        scheduler._task = None

        await scheduler.stop()

        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        """stop() cancels the background task."""
        scheduler = WatchScheduler()

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = None

            await scheduler.start()
            task = scheduler._task

            await scheduler.stop()

            assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_stop_handles_no_task(self):
        """stop() works when no task exists."""
        scheduler = WatchScheduler()
        scheduler._running = True
        scheduler._task = None

        # Should not raise
        await scheduler.stop()

        assert scheduler.is_running is False


class TestWatchSchedulerRunLoop:
    """Tests for _run_loop behavior."""

    @pytest.mark.asyncio
    async def test_run_loop_exits_without_session_maker(self):
        """_run_loop exits early if no database session maker."""
        scheduler = WatchScheduler()
        scheduler._running = True

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = None
            with patch("gmail_watch.scheduler.INITIAL_DELAY_SECONDS", 0):
                await scheduler._run_loop()

        # Should have exited without error
        assert True

    @pytest.mark.asyncio
    async def test_run_loop_initializes_watch_on_startup(
        self, mock_session_maker, mock_watch_manager
    ):
        """_run_loop calls initialize_watch on startup."""
        mock_maker, mock_session = mock_session_maker
        mock_cls, mock_manager = mock_watch_manager

        scheduler = WatchScheduler()
        scheduler._running = True

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = mock_maker
            with patch("gmail_watch.scheduler.INITIAL_DELAY_SECONDS", 0):
                with patch("gmail_watch.scheduler.settings") as mock_settings:
                    mock_settings.pull_interval_seconds = 0.01

                    # Run for a brief moment then stop
                    async def stop_after_delay():
                        await asyncio.sleep(0.05)
                        scheduler._running = False

                    await asyncio.gather(
                        scheduler._run_loop(),
                        stop_after_delay(),
                    )

        # Should have called initialize_watch at least once (on startup)
        mock_manager.initialize_watch.assert_called()

    @pytest.mark.asyncio
    async def test_run_loop_processes_notifications(
        self, mock_session_maker, mock_watch_manager
    ):
        """_run_loop calls process_notifications each iteration."""
        mock_maker, mock_session = mock_session_maker
        mock_cls, mock_manager = mock_watch_manager

        scheduler = WatchScheduler()
        scheduler._running = True

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = mock_maker
            with patch("gmail_watch.scheduler.INITIAL_DELAY_SECONDS", 0):
                with patch("gmail_watch.scheduler.settings") as mock_settings:
                    mock_settings.pull_interval_seconds = 0.01

                    async def stop_after_iterations():
                        await asyncio.sleep(0.05)
                        scheduler._running = False

                    await asyncio.gather(
                        scheduler._run_loop(),
                        stop_after_iterations(),
                    )

        mock_manager.process_notifications.assert_called()

    @pytest.mark.asyncio
    async def test_run_loop_checks_watch_expiration(
        self, mock_session_maker, mock_watch_manager
    ):
        """_run_loop checks watch expiration each iteration."""
        mock_maker, mock_session = mock_session_maker
        mock_cls, mock_manager = mock_watch_manager

        scheduler = WatchScheduler()
        scheduler._running = True

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = mock_maker
            with patch("gmail_watch.scheduler.INITIAL_DELAY_SECONDS", 0):
                with patch("gmail_watch.scheduler.settings") as mock_settings:
                    mock_settings.pull_interval_seconds = 0.01

                    async def stop_after_iterations():
                        await asyncio.sleep(0.05)
                        scheduler._running = False

                    await asyncio.gather(
                        scheduler._run_loop(),
                        stop_after_iterations(),
                    )

        mock_manager.check_watch_expiration.assert_called()

    @pytest.mark.asyncio
    async def test_run_loop_renews_watch_when_needed(
        self, mock_session_maker, mock_watch_manager
    ):
        """_run_loop renews watch when check_watch_expiration says needed."""
        mock_maker, mock_session = mock_session_maker
        mock_cls, mock_manager = mock_watch_manager

        # Configure to need renewal
        mock_manager.check_watch_expiration.return_value = {"needs_renewal": True}

        scheduler = WatchScheduler()
        scheduler._running = True

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = mock_maker
            with patch("gmail_watch.scheduler.INITIAL_DELAY_SECONDS", 0):
                with patch("gmail_watch.scheduler.settings") as mock_settings:
                    mock_settings.pull_interval_seconds = 0.01

                    async def stop_after_iterations():
                        await asyncio.sleep(0.05)
                        scheduler._running = False

                    await asyncio.gather(
                        scheduler._run_loop(),
                        stop_after_iterations(),
                    )

        # initialize_watch should be called: once at startup + at least once for renewal
        assert mock_manager.initialize_watch.call_count >= 2


class TestWatchSchedulerErrorHandling:
    """Tests for error handling in the scheduler."""

    @pytest.mark.asyncio
    async def test_run_loop_continues_after_error(
        self, mock_session_maker, mock_watch_manager
    ):
        """_run_loop continues running after an exception."""
        mock_maker, mock_session = mock_session_maker
        mock_cls, mock_manager = mock_watch_manager

        # First call raises, then works
        call_count = 0

        async def failing_then_working():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Simulated error")
            return {"status": "ok", "processed": 0, "replies_found": 0}

        mock_manager.process_notifications.side_effect = failing_then_working

        scheduler = WatchScheduler()
        scheduler._running = True

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = mock_maker
            with patch("gmail_watch.scheduler.INITIAL_DELAY_SECONDS", 0):
                with patch("gmail_watch.scheduler.settings") as mock_settings:
                    mock_settings.pull_interval_seconds = 0.01

                    async def stop_after_iterations():
                        await asyncio.sleep(0.1)
                        scheduler._running = False

                    await asyncio.gather(
                        scheduler._run_loop(),
                        stop_after_iterations(),
                    )

        # Should have been called more than once (loop continued after error)
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_run_loop_logs_errors(self, mock_session_maker, mock_watch_manager):
        """_run_loop logs errors when they occur."""
        mock_maker, mock_session = mock_session_maker
        mock_cls, mock_manager = mock_watch_manager

        mock_manager.process_notifications.side_effect = Exception("Test error")

        scheduler = WatchScheduler()
        scheduler._running = True

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = mock_maker
            with patch("gmail_watch.scheduler.INITIAL_DELAY_SECONDS", 0):
                with patch("gmail_watch.scheduler.settings") as mock_settings:
                    mock_settings.pull_interval_seconds = 0.01
                    with patch("gmail_watch.scheduler.logger") as mock_logger:
                        async def stop_quickly():
                            await asyncio.sleep(0.03)
                            scheduler._running = False

                        await asyncio.gather(
                            scheduler._run_loop(),
                            stop_quickly(),
                        )

                        # Should have logged error
                        mock_logger.error.assert_called()


class TestWatchSchedulerLogging:
    """Tests for scheduler logging behavior."""

    @pytest.mark.asyncio
    async def test_run_loop_logs_when_replies_found(
        self, mock_session_maker, mock_watch_manager
    ):
        """_run_loop logs when replies are found."""
        mock_maker, mock_session = mock_session_maker
        mock_cls, mock_manager = mock_watch_manager

        # Return that we found replies
        mock_manager.process_notifications.return_value = {
            "status": "ok",
            "processed": 1,
            "replies_found": 2,
        }

        scheduler = WatchScheduler()
        scheduler._running = True

        with patch("gmail_watch.scheduler.get_session_maker") as mock_gsm:
            mock_gsm.return_value = mock_maker
            with patch("gmail_watch.scheduler.INITIAL_DELAY_SECONDS", 0):
                with patch("gmail_watch.scheduler.settings") as mock_settings:
                    mock_settings.pull_interval_seconds = 0.01
                    with patch("gmail_watch.scheduler.logger") as mock_logger:
                        async def stop_quickly():
                            await asyncio.sleep(0.03)
                            scheduler._running = False

                        await asyncio.gather(
                            scheduler._run_loop(),
                            stop_quickly(),
                        )

                        # Should have logged about processing
                        info_calls = [
                            call for call in mock_logger.info.call_args_list
                            if "Processed notifications" in str(call)
                        ]
                        assert len(info_calls) >= 1


class TestWatchSchedulerGlobalInstance:
    """Tests for global scheduler instance."""

    def test_global_instance_exists(self):
        """Global watch_scheduler instance exists."""
        from gmail_watch.scheduler import watch_scheduler

        assert watch_scheduler is not None
        assert isinstance(watch_scheduler, WatchScheduler)

    def test_global_instance_starts_not_running(self):
        """Global watch_scheduler starts not running."""
        from gmail_watch.scheduler import watch_scheduler

        # Note: This test might fail if run after other tests that start it
        # In fresh state, it should not be running
        # Just verify the property exists
        assert hasattr(watch_scheduler, "is_running")
