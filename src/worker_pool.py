import asyncio
import logging
import time
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class WorkerTask:
    task_id: str
    coro: Any
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    timeout: float = 300.0
    description: str = ""


class WorkerPool:
    def __init__(self, max_workers: int = 10, default_timeout: float = 300.0):
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self._tasks: Dict[str, asyncio.Task] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._semaphore = asyncio.Semaphore(max_workers)
        self._watchdog_task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._watchdog_task = asyncio.create_task(self._watchdog())
        logger.info(f"WorkerPool started with {self.max_workers} workers")

    async def stop(self):
        self._running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
        for task_id, task in list(self._tasks.items()):
            task.cancel()
        self._tasks.clear()
        logger.info("WorkerPool stopped")

    async def submit(self, task_id: str, coro, timeout: float = None, description: str = "") -> asyncio.Task:
        timeout = timeout or self.default_timeout
        task = asyncio.create_task(self._run_with_semaphore(task_id, coro, timeout))
        self._tasks[task_id] = task
        task.add_done_callback(lambda t: self._tasks.pop(task_id, None))
        logger.info(f"Task submitted: {task_id} — {description}")
        return task

    async def _run_with_semaphore(self, task_id: str, coro, timeout: float):
        async with self._semaphore:
            try:
                await asyncio.wait_for(coro, timeout=timeout)
                logger.info(f"Task completed: {task_id}")
            except asyncio.TimeoutError:
                logger.warning(f"Task timed out: {task_id}")
            except asyncio.CancelledError:
                logger.info(f"Task cancelled: {task_id}")
            except Exception as e:
                logger.error(f"Task failed: {task_id} — {e}")

    async def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def cancel_all(self):
        for task_id, task in list(self._tasks.items()):
            task.cancel()
        self._tasks.clear()
        logger.info("All tasks cancelled")

    def get_active_tasks(self) -> Dict[str, bool]:
        return {tid: not t.done() for tid, t in self._tasks.items()}

    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    async def _watchdog(self):
        while self._running:
            try:
                await asyncio.sleep(30)
                done_ids = [tid for tid, t in self._tasks.items() if t.done()]
                for tid in done_ids:
                    self._tasks.pop(tid, None)
                logger.debug(f"Watchdog: {self.active_count()} active tasks")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}")


# Global pool instance
pool = WorkerPool(max_workers=20, default_timeout=600.0)
