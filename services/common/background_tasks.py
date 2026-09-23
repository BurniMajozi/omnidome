"""Shared background-task scheduler working around a systemic, silent bug:
FastAPI's `BackgroundTasks` (`response.background`) never executes in any
service using `configure_production()` (services/common/middleware.py).

Root cause: `RequestLoggingMiddleware` (a `starlette.middleware.base.
BaseHTTPMiddleware` subclass) runs the endpoint in a separate task and
relays its response back through an internal streaming wrapper, which drops
`response.background` in the Starlette version installed here.
`background_tasks.add_task(fn, *args)` schedules work that then silently
never runs -- no exception, no log line, nothing. Confirmed by direct live
testing in services/fno_intelligence (2026-09-23): an import's status sat at
"uploaded" forever with zero error output, until this was tracked down.
Audited the rest of the fleet the same day and found six more services with
the identical dead-on-arrival pattern (voicebox, sales, journey_engine,
network x4, inventory) -- see the memory note this session wrote for the
full list.

`asyncio.create_task()` schedules straight onto the running event loop and
never touches the ASGI response object, sidestepping the bug entirely. This
was NOT fixed at the middleware level (a single fix there would cover every
service at once, but touches every service's request/response pipeline --
higher blast radius than patching each call site) -- see the memory note.

Usage: replace

    background_tasks.add_task(some_async_fn, arg1, arg2)

(FastAPI's BackgroundTasks -- silently drops the work) with

    schedule_background(some_async_fn(arg1, arg2))

(schedule_background takes the awaited coroutine object itself, not a
function + args pair -- call the function to get the coroutine, don't pass
it unevaluated).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger("omnidome.background_tasks")

# Kept alive here so a task isn't garbage-collected mid-run (asyncio only
# holds a weak reference to a task once nothing else references it).
_BACKGROUND_TASKS: "set[asyncio.Task]" = set()


def schedule_background(coro: Coroutine) -> "asyncio.Task":
    """Schedule a coroutine to run on the current event loop, independent of
    the HTTP response. Any exception it raises is logged (never silently
    swallowed) rather than left as an unretrieved Task exception."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)

    def _on_done(t: "asyncio.Task") -> None:
        _BACKGROUND_TASKS.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("Background task %r crashed: %r", coro, exc, exc_info=exc)

    task.add_done_callback(_on_done)
    return task
