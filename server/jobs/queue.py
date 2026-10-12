"""Job queue backends. The `jobs` table is the source of truth; queue messages carry only a
job id and just wake the worker. Lost or duplicate messages are harmless: the worker
claims jobs atomically and also sweeps the table for due jobs.

`QUEUE_BACKEND` picks the implementation: in-process asyncio (default) or Amazon SQS.
"""

import asyncio
import contextlib
from typing import Protocol

from server.config import Settings

SQS_MAX_DELAY_SECONDS = 900
SQS_MAX_WAIT_SECONDS = 20


class JobQueue(Protocol):
    async def put(self, job_id: int, *, delay_seconds: float = 0) -> None: ...

    async def get(self, timeout: float) -> int | None:
        """The next job id, or None after `timeout` seconds."""
        ...


class LocalQueue:
    """In-process queue for local dev. Delays are left to `jobs.run_after`."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] = asyncio.Queue()

    async def put(self, job_id: int, *, delay_seconds: float = 0) -> None:
        self._queue.put_nowait(job_id)

    async def get(self, timeout: float) -> int | None:
        with contextlib.suppress(TimeoutError):
            return await asyncio.wait_for(self._queue.get(), timeout)
        return None


class SqsQueue:
    def __init__(self, *, queue_url: str, region: str, client=None):
        if client is None:
            import boto3

            client = boto3.client("sqs", region_name=region)
        self._client = client
        self._url = queue_url

    async def put(self, job_id: int, *, delay_seconds: float = 0) -> None:
        delay = max(0, min(int(delay_seconds), SQS_MAX_DELAY_SECONDS))
        await asyncio.to_thread(
            self._client.send_message,
            QueueUrl=self._url,
            MessageBody=str(job_id),
            DelaySeconds=delay,
        )

    async def get(self, timeout: float) -> int | None:
        response = await asyncio.to_thread(
            self._client.receive_message,
            QueueUrl=self._url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=max(0, min(int(timeout), SQS_MAX_WAIT_SECONDS)),
        )
        messages = response.get("Messages", [])
        if not messages:
            return None
        message = messages[0]
        # Delete right away: the jobs table, not SQS, tracks completion and retries.
        await asyncio.to_thread(
            self._client.delete_message,
            QueueUrl=self._url,
            ReceiptHandle=message["ReceiptHandle"],
        )
        try:
            return int(message["Body"])
        except ValueError:
            return None


def build_queue(settings: Settings) -> JobQueue:
    if settings.queue_backend == "sqs":
        if not settings.sqs_queue_url:
            raise ValueError("QUEUE_BACKEND=sqs requires SQS_QUEUE_URL")
        return SqsQueue(queue_url=settings.sqs_queue_url, region=settings.aws_region)
    return LocalQueue()
