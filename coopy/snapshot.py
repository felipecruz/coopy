import logging
import math
import os
import pickle
import signal
import sys
import tempfile
import threading
import time
from io import BytesIO
from os import path
from pathlib import Path
from pickle import Pickler, Unpickler

from coopy import fileutils as fu
from coopy.compression import MAGIC, compress, decompress, validate_compression
from coopy.error import PersistenceError
from coopy.integrity import IntegrityError

logger = logging.getLogger("coopy")


def fork_supported(fork_safe):
    """An explicit application assertion is still required for native threads/hooks."""
    return (
        fork_safe is True
        and os.name == "posix"
        and hasattr(os, "fork")
        and sys.platform != "darwin"
        and threading.current_thread() is threading.main_thread()
        and threading.active_count() == 1
    )


class SnapshotJob:
    """Parent-owned checkpoint publication. wait() reaps the child, even on error.

    A timeout kills the serialization child and keeps the old checkpoint.
    Call wait() before requesting another snapshot; proxy.close() also waits.
    """

    def __init__(self, pid, temporary, destination, manager):
        self.pid = pid
        self.temporary = temporary
        self.destination = destination
        self.manager = manager
        self.done = False
        self.error = None
        self.lock = threading.Lock()

    def wait(self, timeout: float = 60.0) -> None:
        if timeout < 0 or not math.isfinite(timeout):
            raise ValueError("timeout must be finite and nonnegative")
        with self.lock:
            if self.done:
                if self.error is not None:
                    raise self.error
                return
            reaped = False
            try:
                deadline = time.monotonic() + timeout
                while True:
                    try:
                        pid, status = os.waitpid(self.pid, os.WNOHANG)
                    except ChildProcessError:
                        # An application SIGCHLD handler may have reaped it.
                        # Never kill a potentially recycled PID in that case.
                        reaped = True
                        raise
                    if pid:
                        reaped = True
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Snapshot child timed out")
                    time.sleep(0.005)
                if status != 0:
                    raise PersistenceError(f"Snapshot child failed (wait status {status})")
                with open(self.temporary, "rb") as file:
                    os.fsync(file.fileno())
                os.replace(self.temporary, self.destination)
                if self.manager.durability == "sync":
                    fu.sync_directory(self.manager.basedir)
            except BaseException as error:
                self.error = error
                raise
            finally:
                if not reaped:
                    try:
                        os.kill(self.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.waitpid(self.pid, 0)
                self.done = True
                self.manager._cleanup(self.temporary)


class SnapshotManager(object):
    def __init__(
        self, basedir, durability="buffered", integrity=None, serializer=None, compression=None
    ):
        validate_compression(compression)
        self.compression = compression
        self.serializer = serializer
        self.integrity = integrity
        self.durability = durability
        self.basedir = Path(basedir)

    @staticmethod
    def _cleanup(temporary):
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("Unable to remove incomplete snapshot %s", temporary, exc_info=True)

    def start_fork(self, object, before_publish):
        """Called with the domain lock held and eligibility checked by the proxy."""
        destination = fu.next_snapshot_file(self.basedir)
        file = tempfile.NamedTemporaryFile(
            mode="wb", dir=self.basedir, prefix=".coopy-snapshot-", delete=False
        )
        pid = None
        try:
            # Reserve the boundary and flush inherited journal buffers before
            # fork. Only the parent will ever publish or touch journals again.
            before_publish(destination)
            pid = os.fork()
            if pid == 0:
                try:
                    self._serialize(object, file, destination)
                    file.flush()
                except BaseException:
                    os._exit(1)
                os._exit(0)  # No logging, cleanup handlers, publication or journals.
            file.close()
        except BaseException:
            if pid:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)
            try:
                file.close()
            except OSError:
                logger.warning("Unable to close incomplete snapshot %s", file.name, exc_info=True)
            self._cleanup(file.name)
            raise
        return SnapshotJob(pid, file.name, destination, self)

    def _serialize(self, object, file, destination):
        if self.integrity is None and self.compression is None:
            writer = (
                Pickler(file, pickle.HIGHEST_PROTOCOL)
                if self.serializer is None
                else self.serializer.writer(file)
            )
            writer.dump(object)
        else:
            payload = (
                pickle.dumps(object, pickle.HIGHEST_PROTOCOL)
                if self.serializer is None
                else self.serializer.dumps(object)
            )
            payload = compress(payload, self.compression)
            if self.integrity is not None:
                payload = self.integrity.encode(payload, destination)
            file.write(payload)

    def load_payload(self, payload):
        payload = decompress(payload)
        if self.serializer is not None:
            return self.serializer.loads(payload)
        file = BytesIO(payload)
        result = Unpickler(file).load()
        if file.read(1):
            raise ValueError("Trailing bytes after snapshot")
        return result

    def take_snapshot(self, object, before_publish=None):
        """Publish only a fully written, synced, and closed snapshot.

        The caller coordinates journals via before_publish while holding its
        domain lock. A failed publication must leave those journals intact.
        """
        destination = fu.next_snapshot_file(self.basedir)
        # The temporary name cannot be discovered as a checkpoint. Keep it on
        # the same filesystem so publication is a single atomic rename.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.basedir, prefix=".coopy-snapshot-", delete=False
            ) as file:
                temporary = file.name
                self._serialize(object, file, destination)
                file.flush()
                os.fsync(file.fileno())
            if before_publish:
                before_publish(destination)
            os.replace(temporary, destination)
            temporary = None
            if self.durability == "sync":
                fu.sync_directory(self.basedir)
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError:
                    # Cleanup is best effort: preserve the snapshot failure
                    # for the caller. This hidden file cannot become a checkpoint.
                    logger.warning(
                        "Unable to remove incomplete snapshot %s", temporary, exc_info=True
                    )

    def recover_snapshot(self):
        last_snapshot = fu.last_snapshot_file(self.basedir)
        if not last_snapshot:
            return None
        with open(path.join(self.basedir, last_snapshot), "rb") as file:
            logger.debug("Recovering snapshot from: " + file.name)
            if self.integrity is not None:
                payload = self.integrity.read(file, file.name)
                if file.read(1):
                    raise IntegrityError("Trailing bytes after signed snapshot")
                return self.load_payload(payload)
            if file.peek(len(MAGIC)).startswith(MAGIC):
                return self.load_payload(file.read())
            reader = Unpickler(file) if self.serializer is None else self.serializer.reader(file)
            result = reader.load()
            if file.read(1):
                raise ValueError("Trailing bytes after snapshot")
            return result


class SnapshotTimer(threading.Thread):
    def __init__(self, snapshot_time, proxy):
        threading.Thread.__init__(self, daemon=True)
        self.snapshot_time = snapshot_time
        self.proxy = proxy
        self.finished = threading.Event()

    def run(self):
        # wait first: the first snapshot happens after snapshot_time
        while not self.finished.wait(self.snapshot_time):
            try:
                self.proxy.take_snapshot()
            except Exception:
                logger.exception("Scheduled snapshot failed; retaining previous checkpoint")

    def stop(self):
        self.finished.set()
        if self is not threading.current_thread():
            self.join()
