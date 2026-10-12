"""Background worker: runs inside the server process and consumes queued jobs.

Loop: wait for a queue message (or the poll interval), then run every due job from the
`jobs` table. Each job is claimed atomically, so duplicate messages and multiple workers
are safe. Failures retry with backoff up to `max_attempts`, then the job is marked failed.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.db import repository as repo
from server.db.models import Job
from server.jobs.insights import regenerate_weekly_insight
from server.jobs.llm import LLMClient
from server.jobs.queue import JobQueue
from server.services.workouts import INSIGHT_JOB

logger = logging.getLogger("fitgen.jobs")

Handler = Callable[..., Awaitable[str]]
DEFAULT_HANDLERS: dict[str, Handler] = {INSIGHT_JOB: regenerate_weekly_insight}
RETRY_BASE = timedelta(seconds=30)
STALE_RUNNING = timedelta(minutes=10)  # longer than any job takes


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Worker:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        queue: JobQueue,
        llm: LLMClient,
        handlers: dict[str, Handler] | None = None,
        poll_seconds: float = 5.0,
        max_attempts: int = 3,
        clock: Callable[[], datetime] = _utcnow,
    ):
        self.sessionmaker = sessionmaker
        self.queue = queue
        self.llm = llm
        self.handlers = handlers or DEFAULT_HANDLERS
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self.clock = clock

    async def run(self) -> None:
        """Run until cancelled. Database outages are logged and retried, never fatal."""
        logger.info("Job worker started (poll every %.0f s)", self.poll_seconds)
        while True:
            try:
                await self.queue.get(timeout=self.poll_seconds)
                await self.process_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Job worker loop error; retrying")
                await asyncio.sleep(self.poll_seconds)

    async def process_due(self) -> int:
        """Run every job that is due now. Returns how many were attempted."""
        async with self.sessionmaker() as db:
            job_ids = await repo.due_job_ids(db, self.clock())
        for job_id in job_ids:
            await self.process(job_id)
        return len(job_ids)

    async def process(self, job_id: int) -> None:
        async with self.sessionmaker() as db:
            job = await repo.claim_job(db, job_id, self.clock())
            await db.commit()
        if job is None:
            return  # not due, already taken, or gone

        handler = self.handlers.get(job.kind)
        start = self.clock()
        try:
            if handler is None:
                raise ValueError(f"no handler for job kind {job.kind!r}")
            outcome = await handler(
                job, sessionmaker=self.sessionmaker, llm=self.llm, now=self.clock()
            )
        except Exception as exc:
            await self._fail(job, exc)
            return
        await self._finish(job, status="done", error=None)
        ms = (self.clock() - start).total_seconds() * 1000
        logger.info("job=%s kind=%s status=done duration_ms=%.0f %s", job.id, job.kind, ms, outcome)

    async def _fail(self, job: Job, exc: Exception) -> None:
        error = f"{type(exc).__name__}: {exc}"[:1000]
        if job.attempts < self.max_attempts:
            delay = RETRY_BASE * (2 ** (job.attempts - 1))
            async with self.sessionmaker() as db:
                requeued = await repo.requeue_job(db, job.id, self.clock() + delay, error)
                await db.commit()
            if requeued:
                logger.warning(
                    "job=%s kind=%s attempt=%s failed, retrying in %s: %s",
                    job.id,
                    job.kind,
                    job.attempts,
                    delay,
                    error,
                )
            else:
                logger.info("job=%s kind=%s failed and was superseded: %s", job.id, job.kind, error)
        else:
            await self._finish(job, status="failed", error=error)
            logger.error("job=%s kind=%s failed permanently: %s", job.id, job.kind, error)

    async def _finish(self, job: Job, *, status: str, error: str | None) -> None:
        async with self.sessionmaker() as db:
            row = await db.get(Job, job.id)
            row.status = status
            row.error = error
            await db.commit()

    async def recover(self) -> int:
        """At startup: requeue jobs stuck running, and wake the worker for queued ones
        (the local queue doesn't survive a restart)."""
        async with self.sessionmaker() as db:
            await repo.requeue_stale_running(db, self.clock() - STALE_RUNNING)
            await db.commit()
            job_ids = await repo.queued_job_ids(db)
        for job_id in job_ids:
            await self.queue.put(job_id)
        return len(job_ids)
