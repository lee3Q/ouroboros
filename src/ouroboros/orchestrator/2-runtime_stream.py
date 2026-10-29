"""Keep provider iterator scopes out of the leaf consumer's task."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager, suppress

import anyio

from ouroboros.orchestrator.adapter import AgentMessage


@asynccontextmanager
async def isolated_runtime_stream(
    source: AsyncIterator[AgentMessage],
) -> AsyncIterator[AsyncIterator[AgentMessage]]:
    """Own one bounded producer and join it before leaving the dispatch.

    Provider generators may hold AnyIO scopes across yields. Running them in
    the consumer task lets those scopes shield the dispatcher's stall timeout.
    A per-message acknowledgement preserves the original pull protocol: the
    provider cannot advance until the consumer finishes processing its message.
    Context variables are copied by create_task; the consumer retains its own
    dispatch authority and deadline. No runtime result is synthesized here.
    """
    queue: asyncio.Queue[AgentMessage] = asyncio.Queue(maxsize=1)
    processed = asyncio.Event()

    async def produce() -> None:
        try:
            async for message in source:
                # Provider scopes may be suspended across this yield. Their
                # deadlines belong to provider advancement, not queue handoff.
                with anyio.CancelScope(shield=True):
                    await queue.put(message)
                    await processed.wait()
                    processed.clear()
        finally:
            close = getattr(source, "aclose", None)
            if close is not None:
                await close()

    producer = asyncio.create_task(produce(), name="ouroboros-leaf-runtime-stream")

    async def consume() -> AsyncGenerator[AgentMessage, None]:
        while True:
            if not queue.empty():
                yield queue.get_nowait()
                processed.set()
                continue
            if producer.done():
                await producer
                return
            incoming = asyncio.create_task(queue.get())
            try:
                await asyncio.wait((incoming, producer), return_when=asyncio.FIRST_COMPLETED)
                if incoming.done():
                    yield incoming.result()
                    processed.set()
            finally:
                if not incoming.done():
                    incoming.cancel()
                with suppress(asyncio.CancelledError):
                    await incoming

    body_error: BaseException | None = None
    try:
        async with aclosing(consume()) as messages:
            yield messages
    except BaseException as error:
        body_error = error
        raise
    finally:
        # Direct task cancellation reaches a provider shield; inherited AnyIO
        # level cancellation must not interrupt the matching cleanup/join.
        with anyio.CancelScope(shield=True):
            if not producer.done():
                producer.cancel()
            consumer_task = asyncio.current_task()
            cancel_count = consumer_task.cancelling() if consumer_task is not None else 0
            cleanup_cancel: asyncio.CancelledError | None = None
            while not producer.done():
                try:
                    await asyncio.shield(producer)
                except asyncio.CancelledError as error:
                    if consumer_task is not None and consumer_task.cancelling() > cancel_count:
                        cleanup_cancel = error
                except BaseException:
                    break
            try:
                producer.result()
            except asyncio.CancelledError:
                pass
            except BaseException:
                if body_error is None and cleanup_cancel is None:
                    raise
            if cleanup_cancel is not None and body_error is None:
                raise cleanup_cancel
