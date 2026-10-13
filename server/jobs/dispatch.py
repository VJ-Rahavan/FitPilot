"""Hand newly committed jobs to the running worker's queue.

Fire-and-forget so tools don't wait on the queue. If no worker is running, jobs simply
stay queued in the database and are picked up by the next worker sweep.
"""

import asyncio
import logging

from server.jobs.queue import JobQueue

logger = logging.getLogger("fitgen.jobs")

_queue: JobQueue | None = None
_pending: set[asyncio.Task] = set()


def set_queue(queue: JobQueue | None) -> None:
    global _queue
    _queue = queue


def dispatch(job_ids: list[int]) -> None:
    if _queue is None or not job_ids:
        return
    task = asyncio.create_task(_put_all(_queue, list(dict.fromkeys(job_ids))))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _put_all(queue: JobQueue, job_ids: list[int]) -> None:
    for job_id in job_ids:
        try:
            await queue.put(job_id)
        except Exception:  # the sweep will still find the job
            logger.warning("Could not enqueue job %s; the worker sweep will pick it up", job_id)
