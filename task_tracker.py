
from __future__ import annotations

import asyncio

from logger_setup import logger


# schedule_tracked_task
def schedule_tracked_task(coro, task_set: set, name: str) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    task_set.add(task)

    # _finish
    def _finish(done_task: asyncio.Task) -> None:
        task_set.discard(done_task)
        if done_task.cancelled():
            return
        try:
            error = done_task.exception()
        except asyncio.CancelledError:
            return
        if error is not None:
            logger.error("❌ Telegram ingress task lỗi: %s", error)

    task.add_done_callback(_finish)
    return task
