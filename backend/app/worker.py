"""Worker entrypoint: a claim loop with graceful shutdown.

Run with ``python -m app.worker``. On SIGINT/SIGTERM it stops claiming, releases any job it
still holds back to PENDING, and exits - so a rolling restart never strands work.
"""

import asyncio
import contextlib
import os
import signal
import uuid
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import RequestContext
from app.db.session import SessionLocal
from app.jobs.handlers import HANDLERS, system_context
from app.jobs.runner import release_claimed, run_next
from app.models.job import Job

_IDLE_SLEEP_SECONDS = 0.5


class Worker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
        *,
        worker_id: str | None = None,
        context_factory: Callable[[Job], RequestContext] = system_context,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.context_factory = context_factory
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        try:
            while not self._stop.is_set():
                outcome = await run_next(
                    self.session_factory,
                    handlers=HANDLERS,
                    worker_id=self.worker_id,
                    context_factory=self.context_factory,
                )
                if not outcome.ran:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._stop.wait(), timeout=_IDLE_SLEEP_SECONDS)
        finally:
            # Graceful shutdown: hand any still-held job back to the queue.
            await release_claimed(self.session_factory, worker_id=self.worker_id)


async def _main() -> None:
    worker = Worker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, worker.request_stop)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
