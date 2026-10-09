"""Experimental replication; incomplete until roadmap F13 is accepted."""
from tempfile import TemporaryDirectory

from coopy.base import init_persistent_system, init_system
from wiki import Wiki


def demonstrate(directory):
    master = init_persistent_system(Wiki, basedir=directory)
    replica = init_system(Wiki(), [])  # no local journal or snapshot manager
    try:
        master.create_page("Home", "Existing master state")
        master.start_master(port=0, password="local-demo-secret")
        # Port 0 lets the OS choose a free port for this local demonstration.
        host, port = master.master.server.getsockname()
        connection = replica.start_slave(host, port,
                                         password="local-demo-secret")
        if not connection.wait_until_synchronized(timeout=10):
            raise RuntimeError(connection.error or "Bootstrap timed out")
        assert replica.get_page("Home") == master.get_page("Home")
    finally:
        replica.close()
        master.shutdown()
        master.close()


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        demonstrate(directory)
