"""
Concurrency synchronization and thread coordination primitives.
Uses threading.Event and explicit timeouts to guarantee deterministic interleaving
without risk of indefinite deadlocks or hanging processes.
"""

from contextlib import contextmanager
import threading
from typing import Callable, Generator, List, Optional
from psycopg import Connection

from database.connection import get_raw_connection


class ScenarioCoordinator:
    """
    Coordinates multi-threaded transaction scenarios with bounded timeouts.
    Ensures safe cleanup and exception propagation.
    """

    def __init__(self, default_timeout_sec: float = 8.0):
        self.default_timeout = default_timeout_sec
        self._events: dict[str, threading.Event] = {}
        self._errors: List[Exception] = []
        self._lock = threading.Lock()

    def get_event(self, name: str) -> threading.Event:
        """Retrieves or creates a named synchronization event."""
        with self._lock:
            if name not in self._events:
                self._events[name] = threading.Event()
            return self._events[name]

    def signal(self, name: str) -> None:
        """Signals that a transaction step has reached its milestone."""
        evt = self.get_event(name)
        evt.set()

    def wait_for(self, name: str, timeout: Optional[float] = None) -> bool:
        """
        Waits for a milestone with an explicit timeout to prevent hanging.
        Returns True if signaled, False if timed out.
        """
        evt = self.get_event(name)
        t = timeout if timeout is not None else self.default_timeout
        signaled = evt.wait(timeout=t)
        if not signaled:
            raise TimeoutError(f"Coordination timeout: Milestone '{name}' not reached within {t}s.")
        return True

    def record_error(self, err: Exception) -> None:
        """Records worker thread exception."""
        with self._lock:
            self._errors.append(err)

    @property
    def has_errors(self) -> bool:
        with self._lock:
            return len(self._errors) > 0

    @property
    def errors(self) -> List[Exception]:
        with self._lock:
            return list(self._errors)


def spawn_transaction_worker(
    target: Callable[..., None],
    args: tuple = (),
    name: str = "Worker",
) -> threading.Thread:
    """Spawns a named worker thread for running an isolated transaction."""
    thread = threading.Thread(target=target, args=args, name=name, daemon=True)
    thread.start()
    return thread
