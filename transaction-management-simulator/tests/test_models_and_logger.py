"""
Unit tests for data models, event logging, and settings security.
Executes completely offline without database requirements.
"""

import threading
import pytest
from config.settings import Settings
from engine.event_logger import EventLogger
from engine.models import (
    IsolationLevel,
    OperationType,
    TransactionEvent,
    TransactionState,
)


def test_transaction_state_enum_values():
    """Verifies all five formal textbook states are present."""
    states = [
        TransactionState.ACTIVE,
        TransactionState.PARTIALLY_COMMITTED,
        TransactionState.COMMITTED,
        TransactionState.FAILED,
        TransactionState.ABORTED,
    ]
    assert len(states) == 5
    assert TransactionState.ACTIVE.value == "ACTIVE"
    assert TransactionState.COMMITTED.value == "COMMITTED"
    assert TransactionState.ABORTED.value == "ABORTED"


def test_settings_password_masking():
    """Ensures database passwords are never exposed in masked output."""
    raw = "postgresql://postgres:SuperSecret123@db.sample.supabase.co:5432/postgres"
    s = Settings(
        database_url=raw,
        environment="test",
        default_lock_timeout_ms=5000,
        test_item_id="TEST_X",
        schema_name="public",
    )
    assert s.is_configured is True
    masked = s.masked_database_url
    assert "SuperSecret123" not in masked
    assert "******" in masked
    assert "db.sample.supabase.co" in masked


def test_settings_placeholder_detection():
    """Detects placeholder template URLs and flags as unconfigured."""
    placeholder = "postgresql://postgres:your-supabase-db-password@db.your-project-ref.supabase.co:5432/postgres"
    s = Settings(
        database_url=placeholder,
        environment="test",
        default_lock_timeout_ms=5000,
        test_item_id="TEST_X",
        schema_name="public",
    )
    assert s.is_configured is False


def test_event_logger_monotonic_steps():
    """Verifies monotonic ordering and field serialization in event logger."""
    logger = EventLogger(run_id="run-101")
    e1 = logger.log("T1", OperationType.BEGIN, "Started T1")
    e2 = logger.log("T1", OperationType.READ, "Read val", observed_value=100.0)
    e3 = logger.log("T1", OperationType.COMMIT, "Committed T1")

    events = logger.get_events()
    assert len(events) == 3
    assert [e.step_number for e in events] == [1, 2, 3]
    assert events[1].observed_value == 100.0

    df = logger.to_dataframe()
    assert len(df) == 3
    assert list(df.columns) == ["Step", "Timestamp", "Transaction", "Operation", "Description", "Observed Value"]


def test_event_logger_thread_safety():
    """Tests multi-threaded concurrent logging safety."""
    logger = EventLogger(run_id="run-multi")
    threads = []

    def worker(tx_name: str, count: int):
        for i in range(count):
            logger.log(tx_name, OperationType.WRITE, f"Write {i}", observed_value=float(i))

    for idx in range(5):
        t = threading.Thread(target=worker, args=(f"T{idx}", 20))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    events = logger.get_events()
    assert len(events) == 100
    # Every step number from 1 to 100 must be present exactly once
    steps = [e.step_number for e in events]
    assert sorted(steps) == list(range(1, 101))
