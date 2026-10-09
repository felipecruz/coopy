"""Deterministic queue, cancellation and event-loop responsiveness checks."""
import asyncio
import threading

import pytest

from coopy import AsyncPersistent
from coopy.base import CoopyProxy
from coopy.decorators import readonly, abort_exception
from coopy.error import ConfigurationError, LifecycleError, PersistenceError
from coopy.journal import DiskJournal


class Todo:
    def __init__(self):
        self.items = []

    def add(self, item):
        self.items.append(item)
        return len(self.items)

    @readonly
    def read(self):
        return tuple(self.items)

    def fail(self):
        self.items.append('failed')
        raise ValueError('domain failure')

    @abort_exception
    def abort(self):
        raise ValueError('abort')

    def aclose(self, item):
        return self.add(item)

    async def invalid(self):
        self.items.append('invalid')


async def wait_event(event):
    async def wait():
        while not event.is_set():
            await asyncio.sleep(0.001)
    await asyncio.wait_for(wait(), 3)


@pytest.mark.parametrize('durability,delay', [('buffered', 0), ('sync', 0), ('sync', 0.001)])
def test_order_single_thread_and_replay(tmp_path, monkeypatch, durability, delay):
    threads = []
    receive = DiskJournal.receive

    def record(self, action):
        threads.append(threading.get_ident())
        return receive(self, action)

    monkeypatch.setattr(DiskJournal, 'receive', record)

    async def exercise():
        async with AsyncPersistent(Todo, tmp_path, durability=durability,
                                   group_commit_delay=delay) as todo:
            assert await asyncio.gather(*(todo.add(i) for i in range(40))) == list(range(1, 41))
            await todo.take_snapshot()
            assert await asyncio.gather(*(todo.add(i) for i in range(40, 80))) == list(range(41, 81))
            assert await todo.read() == tuple(range(80))
        await todo.aclose()
        with pytest.raises(LifecycleError):
            await todo.add('closed')
        async with AsyncPersistent(Todo, tmp_path) as restored:
            assert await restored.read() == tuple(range(80))

    asyncio.run(exercise())
    assert len(threads) == 80
    assert len(set(threads)) == 1
    assert threads[0] != threading.get_ident()


def test_responsive_cancelled_writes_and_close_drain(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    receive = DiskJournal.receive

    def blocked(self, action):
        if action.args == ('first',):
            entered.set()
            assert release.wait(5), 'event loop did not release writer'
        return receive(self, action)

    monkeypatch.setattr(DiskJournal, 'receive', blocked)

    async def exercise():
        todo = await AsyncPersistent.open(Todo, tmp_path)
        try:
            first = asyncio.create_task(todo.add('first'))
            await wait_event(entered)
            second = asyncio.create_task(todo.add('second'))
            await asyncio.sleep(0)  # Submit second while first still owns RLock.
            for task in (first, second):
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            close = asyncio.create_task(todo.aclose())
            await asyncio.sleep(0)
            with pytest.raises(LifecycleError):
                await todo.add('too late')
            close.cancel()
            with pytest.raises(asyncio.CancelledError):
                await close
            # The loop continues to schedule while the writer holds the lock.
            for _ in range(10):
                await asyncio.sleep(0.001)
            assert not release.is_set()
            assert todo._close_task is not None and not todo._close_task.done()
        finally:
            release.set()
            await todo.aclose()
        assert not any(thread.is_alive() for thread in todo._executor._threads)
        async with AsyncPersistent(Todo, tmp_path) as restored:
            assert await restored.read() == ('first', 'second')

    asyncio.run(exercise())


@pytest.mark.parametrize('cancel_open', [False, True])
def test_opening_off_loop_and_cancel_cleanup(tmp_path, monkeypatch, cancel_open):
    import importlib
    module = importlib.import_module('coopy.asyncio')
    original = module.init_persistent_system
    entered, release = threading.Event(), threading.Event()
    proxies = []

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        proxy = original(*args, **kwargs)
        proxies.append(proxy)
        return proxy

    monkeypatch.setattr(module, 'init_persistent_system', blocked)

    async def exercise():
        todo = AsyncPersistent(Todo, tmp_path)
        opening = asyncio.create_task(todo.__aenter__())
        try:
            await wait_event(entered)
            if cancel_open:
                opening.cancel()
                await asyncio.sleep(0)
            assert not opening.done()
        finally:
            release.set()
        if cancel_open:
            with pytest.raises(asyncio.CancelledError):
                await opening
        else:
            assert await opening is todo
            await todo.aclose()
        assert proxies[0]._closed
        assert not any(thread.is_alive() for thread in todo._executor._threads)

    asyncio.run(exercise())


def test_domain_errors_queries_and_reserved_names(tmp_path):
    async def exercise():
        async with AsyncPersistent(Todo, tmp_path) as todo:
            with pytest.raises(ValueError, match='domain failure'):
                await todo.fail()
            with pytest.raises(ValueError, match='abort'):
                await todo.abort()
            assert await todo.call('aclose', 'collision') == 2
            with pytest.raises(TypeError, match='readonly'):
                await todo.items()
            with pytest.raises(TypeError, match='synchronous'):
                await todo.invalid()
            with pytest.raises(AttributeError):
                await todo.missing()
            with pytest.raises(AttributeError):
                await todo.call('_clock')
            assert await todo.add('after error') == 3
        async with AsyncPersistent(Todo, tmp_path) as restored:
            assert await restored.read() == ('failed', 'collision', 'after error')
    asyncio.run(exercise())


def test_persistence_failure_propagates_and_disables_writes(tmp_path, monkeypatch):
    def fail(self, message):
        self._failed(OSError('disk failure'))

    monkeypatch.setattr(DiskJournal, 'receive', fail)

    async def exercise():
        async with AsyncPersistent(Todo, tmp_path) as todo:
            with pytest.raises(PersistenceError) as caught:
                await todo.add('changed')
            assert isinstance(caught.value.__cause__, OSError)
            with pytest.raises(PersistenceError, match='failed'):
                await todo.add('refused')
            assert await todo.read() == ('changed',)
    asyncio.run(exercise())


@pytest.mark.parametrize('body_error', [False, True])
def test_cleanup_error_and_body_exception(tmp_path, monkeypatch, body_error):
    original = CoopyProxy.close

    def fail(proxy):
        original(proxy)
        raise OSError('close failure')

    monkeypatch.setattr(CoopyProxy, 'close', fail)

    async def exercise():
        todo = AsyncPersistent(Todo, tmp_path)
        with pytest.raises(ValueError if body_error else OSError):
            async with todo:
                if body_error:
                    raise ValueError('body failure')
        with pytest.raises(OSError, match='close failure'):
            await todo.aclose()
        assert not any(thread.is_alive() for thread in todo._executor._threads)
    asyncio.run(exercise())


def test_failed_open_and_unused_close(tmp_path):
    async def exercise():
        unused = AsyncPersistent(Todo, tmp_path / 'unused')
        with pytest.raises(LifecycleError):
            await unused.add('not open')
        await unused.aclose()
        await unused.aclose()
        assert not (tmp_path / 'unused').exists()
        broken = AsyncPersistent(Todo, tmp_path, durability='bad')
        with pytest.raises(ConfigurationError):
            await broken.__aenter__()
        assert not any(thread.is_alive() for thread in broken._executor._threads)
        with pytest.raises(ConfigurationError, match='strict'):
            AsyncPersistent(Todo, tmp_path, recovery='salvage')
    asyncio.run(exercise())


def test_cross_loop_use_rejected(tmp_path):
    async def exercise():
        async with AsyncPersistent(Todo, tmp_path) as todo:
            def another_loop():
                with pytest.raises(LifecycleError, match='another event loop'):
                    asyncio.run(todo.add('wrong loop'))
                with pytest.raises(LifecycleError, match='another event loop'):
                    asyncio.run(todo.aclose())
            await asyncio.to_thread(another_loop)
            assert await todo.read() == ()
    asyncio.run(exercise())
