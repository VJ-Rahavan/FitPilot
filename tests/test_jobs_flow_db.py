"""End to end: a finished workout queues an insight job, the in-process worker runs it
(with a fake LLM), and get_weekly_summary then speaks the new coaching note.

Skipped without Postgres.
"""

import asyncio
import os
from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import server.app
from server.config import Settings
from server.db.seed import DEMO_TIMEZONE
from server.db.seed import run as run_seed
from tests.conftest import _serve
from tests.db_support import (
    TEST_DATABASE_URL,
    FakeLLM,
    call,
    db_reachable,
    reset_db_caches,
    text_of,
)

COACH_NOTE = (
    "You got a session in today and kept your bench press moving. "
    "Next time, add one more set on your first exercise if the last rep felt easy."
)


@pytest.fixture(scope="module")
def worker_url() -> Iterator[str]:
    if not asyncio.run(db_reachable()):
        pytest.skip("Postgres not reachable at TEST_DATABASE_URL")
    asyncio.run(
        run_seed(TEST_DATABASE_URL, reset=True, today=datetime.now(ZoneInfo(DEMO_TIMEZONE)).date())
    )
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    reset_db_caches()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server.app, "build_llm_client", lambda settings: FakeLLM(COACH_NOTE))
        settings = Settings(
            auth_mode="none",
            database_url=TEST_DATABASE_URL,
            worker_enabled=True,
            worker_poll_seconds=0.2,
        )
        try:
            yield from _serve(settings)
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous
            reset_db_caches()


async def test_end_session_leads_to_spoken_ai_insight(worker_url):
    await call(worker_url, "start_session")
    await call(worker_url, "complete_set")
    end = await call(worker_url, "end_session")
    assert text_of(end).startswith("Nice work.")

    for _ in range(50):  # the worker polls every 0.2 s
        summary = await call(worker_url, "get_weekly_summary")
        if COACH_NOTE in text_of(summary):
            break
        await asyncio.sleep(0.2)
    else:
        pytest.fail(f"insight never arrived: {text_of(summary)}")
    assert text_of(summary).endswith(f"Coach's note: {COACH_NOTE}")
