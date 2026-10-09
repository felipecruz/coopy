import pytest

import coopy
from coopy.decorators import readonly


class Collisions:
    def __init__(self):
        self.events = []

    def close(self, value: str) -> int:
        self.events.append(value)
        return len(self.events)

    def shutdown(self, value: str) -> None:
        self.events.append(value)

    def take_snapshot(self, value: str) -> None:
        self.events.append(value)

    @readonly
    def count(self) -> int:
        return len(self.events)


def test_domain_controls_and_replay(tmp_path):
    system = coopy.init_persistent_system(Collisions, str(tmp_path))
    assert system.close("domain") == 1
    system.shutdown("shutdown")
    system.take_snapshot("snapshot")
    coopy.control(system).take_snapshot()
    system.close("after")
    coopy.control(system).close()
    restored = coopy.init_persistent_system(Collisions(), str(tmp_path))
    assert restored.count() == 4
    coopy.control(restored).close()


def test_timer_uses_control_even_with_domain_collision(tmp_path):
    system = coopy.init_persistent_system(Collisions, str(tmp_path))
    handle = coopy.control(system)
    handle.start_snapshot_manager(30)
    timer = system.snapshot_timer
    timer.proxy.take_snapshot()
    assert system.events == []
    handle.close()
    assert not timer.is_alive()


def test_salvage_has_no_writable_control(tmp_path):
    system = coopy.init_persistent_system(Collisions, str(tmp_path))
    coopy.control(system).close()
    result = coopy.init_persistent_system(Collisions, str(tmp_path), recovery="salvage")
    with pytest.raises(TypeError):
        coopy.control(result)
