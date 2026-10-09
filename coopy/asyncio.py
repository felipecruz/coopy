"""Async callers for synchronous persistent domains, with one writer thread."""
from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
import inspect
import logging
from types import TracebackType
from typing import Any, Callable, Coroutine, cast

from .base import CoopyProxy, PathLike, init_persistent_system
from .error import ConfigurationError, LifecycleError

logger = logging.getLogger("coopy")


def _observe(future: asyncio.Future[Any]) -> None:
    # Shielded work may outlive a cancelled waiter. Retrieve its exception to
    # avoid an unhandled-future warning; other waiters still receive it normally.
    if not future.cancelled():
        future.exception()


class AsyncPersistent:
    """Use ``async with AsyncPersistent(Domain, path) as domain``.

    Opening, domain methods, snapshots and close run on one dedicated thread.
    Each instance belongs to one event loop. Domain methods remain synchronous.
    """

    def __init__(self, obj: Any, basedir: PathLike | None = None,
                 **options: Any) -> None:
        if options.get("recovery", "strict") != "strict":
            raise ConfigurationError("AsyncPersistent requires strict recovery")
        self._obj = obj
        self._basedir = basedir
        self._options = options
        self._state = "new"
        self._loop: asyncio.AbstractEventLoop | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._opening: Future[CoopyProxy] | None = None
        self._close_task: asyncio.Task[None] | None = None

    def _check_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise LifecycleError("AsyncPersistent belongs to another event loop")

    @classmethod
    async def open(cls, obj: Any, basedir: PathLike | None = None,
                   **options: Any) -> AsyncPersistent:
        """Open without a context; the caller must await ``aclose()``."""
        instance = cls(obj, basedir, **options)
        return await instance.__aenter__()

    async def __aenter__(self) -> AsyncPersistent:
        self._check_loop()
        if self._state != "new":
            raise LifecycleError("AsyncPersistent can only be opened once")
        self._loop = asyncio.get_running_loop()
        self._state = "opening"
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="coopy-writer")
        self._opening = self._executor.submit(lambda: cast(
            CoopyProxy, init_persistent_system(self._obj, self._basedir, **self._options)))
        future = asyncio.wrap_future(self._opening)
        future.add_done_callback(_observe)
        try:
            await asyncio.shield(future)
            if self._state != "opening":
                raise LifecycleError("AsyncPersistent closed during opening")
            self._state = "open"
            return self
        except BaseException:
            try:
                await self.aclose()
            except Exception:
                logger.exception("Cleanup failed while opening async persistence")
            raise

    async def __aexit__(self, exc_type: type[BaseException] | None,
                        exc: BaseException | None, traceback: TracebackType | None) -> None:
        try:
            await self.aclose()
        except Exception:
            if exc is None:
                raise
            logger.exception("Cleanup failed while propagating async context exception")

    async def _dispatch(self, operation: Callable[[CoopyProxy], Any]) -> Any:
        self._check_loop()
        if self._state != "open":
            raise LifecycleError("AsyncPersistent is not open")
        assert self._executor is not None and self._opening is not None
        opening = self._opening
        # No await between checking state and submission: close cannot overtake
        # an accepted operation on the owning event loop.
        future = asyncio.wrap_future(self._executor.submit(lambda: operation(opening.result())))
        future.add_done_callback(_observe)
        return await asyncio.shield(future)

    async def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Call a domain method, including names reserved by this facade."""
        if name.startswith("_"):
            raise AttributeError("AsyncPersistent only exposes public domain methods")

        def invoke(proxy: CoopyProxy) -> Any:
            # Lookup occurs on the writer too; descriptors must not run on the
            # event loop. Never fall through to synchronous proxy controls.
            method = getattr(proxy.obj, name)
            if not callable(method):
                raise TypeError("Use a @readonly domain method to read attributes")
            if inspect.iscoroutinefunction(method) or inspect.isasyncgenfunction(method):
                raise TypeError("Persistent domain methods must be synchronous")
            return proxy.__getattr__(name)(*args, **kwargs)

        return await self._dispatch(invoke)

    def __getattr__(self, name: str) -> Callable[..., Coroutine[Any, Any, Any]]:
        if name.startswith("_"):
            raise AttributeError(name)

        async def method(*args: Any, **kwargs: Any) -> Any:
            return await self.call(name, *args, **kwargs)

        return method

    async def take_snapshot(self) -> None:
        """Queue a blocking checkpoint on the writer thread."""
        await self._dispatch(lambda proxy: CoopyProxy.take_snapshot(proxy))

    async def aclose(self) -> None:
        """Reject new work, drain accepted calls, close storage and join writer.

        Cancelling this await does not cancel cleanup. Await it again to observe
        completion or its error before shutting down the event loop.
        """
        self._check_loop()
        if self._close_task is None:
            if self._state == "new":
                self._state = "closed"
                return
            if self._state == "closed":
                return
            self._state = "closing"
            self._close_task = asyncio.create_task(self._finish_close())
            self._close_task.add_done_callback(_observe)
        await asyncio.shield(self._close_task)

    async def _finish_close(self) -> None:
        assert self._executor is not None and self._opening is not None
        executor, opening = self._executor, self._opening

        def close() -> None:
            try:
                proxy = opening.result()
            except BaseException:
                return  # Opening's caller receives the original failure.
            CoopyProxy.close(proxy)

        try:
            await asyncio.wrap_future(executor.submit(close))
        finally:
            try:
                # Joining a worker must not block the event loop either.
                await asyncio.to_thread(executor.shutdown, wait=True)
            finally:
                self._state = "closed"
