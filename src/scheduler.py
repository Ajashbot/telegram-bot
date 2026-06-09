import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

from src.database import DB

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._publish_callback: Optional[Callable] = None

    def set_publish_callback(self, callback: Callable):
        self._publish_callback = callback

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _loop(self):
        while self._running:
            try:
                await self._check_schedules()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            await asyncio.sleep(60)

    async def _check_schedules(self):
        schedules = DB.get_schedules(active_only=True)
        now = datetime.now(timezone.utc)

        for sched in schedules:
            try:
                next_run_str = sched.get("next_run")
                if not next_run_str:
                    continue

                try:
                    next_run = datetime.fromisoformat(next_run_str.replace(" ", "T"))
                    if next_run.tzinfo is None:
                        next_run = next_run.replace(tzinfo=timezone.utc)
                except Exception:
                    continue

                if now >= next_run:
                    logger.info(f"Running schedule: {sched['name']} (ID:{sched['id']})")
                    if self._publish_callback:
                        asyncio.create_task(
                            self._run_schedule(sched)
                        )
                    DB.update_schedule_run(sched["id"])
            except Exception as e:
                logger.error(f"Error processing schedule {sched.get('id')}: {e}")

    async def _run_schedule(self, sched: dict):
        try:
            if self._publish_callback:
                await self._publish_callback(
                    ad_id=sched["ad_id"],
                    target_type=sched["target_type"],
                    account_id=sched.get("account_id")
                )
        except Exception as e:
            logger.error(f"Schedule execution error {sched['id']}: {e}")


scheduler = SchedulerService()
