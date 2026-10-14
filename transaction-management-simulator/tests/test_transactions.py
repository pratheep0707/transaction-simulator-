"""
Unit and integration tests for transaction lifecycle, state transitions, and savepoints.
Uses mock connections for offline unit tests and live connections when configured.
"""

from unittest.mock import MagicMock
import pytest

from config.settings import get_settings
from engine.event_logger import EventLogger
from engine.models import IsolationLevel, TransactionState
from engine.transaction_manager import ManagedTransaction


class MockCursor:
    """Mock database cursor for offline testing."""
    def __init__(self):
        self.executed_statements = []

    def execute(self, query, params=None):
        self.executed_statements.append((query, params))

    def fetchone(self):
        return (100.0,)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockConnection:
    """Mock database connection for offline testing."""
    def __init__(self):
        self.autocommit = True
        self.cursor_mock = MockCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_mock

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_transaction_lifecycle_begin_and_commit():
    """Tests normal successful lifecycle: BEGIN -> ACTIVE -> PARTIALLY_COMMITTED -> COMMITTED."""
    mock_conn = MockConnection()
    logger = EventLogger("test-run-1")
    tx = ManagedTransaction("TX_TEST", mock_conn, logger)

    assert tx.state is None

    # 1. BEGIN
    tx.begin(IsolationLevel.READ_COMMITTED)
    assert tx.state == TransactionState.ACTIVE
    assert mock_conn.autocommit is False

    # 2. READ
    val = tx.read()
    assert val == 100.0
    assert tx.state == TransactionState.ACTIVE

    # 3. WRITE
    tx.write(150.0)
    assert tx.state == TransactionState.ACTIVE

    # 4. COMMIT
    tx.commit()
    assert tx.state == TransactionState.COMMITTED
    assert mock_conn.commits == 1

    # Check history transitions
    history_text = " ".join(tx.history)
    assert "PARTIALLY_COMMITTED" in history_text
    assert "COMMITTED" in history_text


def test_transaction_lifecycle_rollback():
    """Tests failure and rollback lifecycle: BEGIN -> ACTIVE -> ABORTED."""
    mock_conn = MockConnection()
    logger = EventLogger("test-run-2")
    tx = ManagedTransaction("TX_TEST_ABORT", mock_conn, logger)

    tx.begin(IsolationLevel.READ_COMMITTED)
    assert tx.state == TransactionState.ACTIVE

    tx.write(999.0)
    tx.rollback()

    assert tx.state == TransactionState.ABORTED
    assert mock_conn.rollbacks == 1


def test_savepoint_and_partial_rollback():
    """Tests SAVEPOINT and ROLLBACK TO SAVEPOINT state integrity."""
    mock_conn = MockConnection()
    logger = EventLogger("test-run-3")
    tx = ManagedTransaction("TX_SP", mock_conn, logger)

    tx.begin(IsolationLevel.READ_COMMITTED)
    tx.write(120.0)

    # Establish savepoint
    tx.savepoint("sp_alpha")
    assert "sp_alpha" in tx.savepoints
    assert tx.state == TransactionState.ACTIVE

    tx.write(999.0)

    # Partial rollback to savepoint
    tx.rollback_to_savepoint("sp_alpha")
    assert tx.state == TransactionState.ACTIVE

    tx.commit()
    assert tx.state == TransactionState.COMMITTED


def test_disallowed_operations_in_invalid_state():
    """Verifies that operations cannot be executed when transaction is not ACTIVE."""
    mock_conn = MockConnection()
    logger = EventLogger("test-run-4")
    tx = ManagedTransaction("TX_INVALID", mock_conn, logger)

    # Attempting to read before BEGIN
    with pytest.raises(RuntimeError) as exc_info:
        tx.read()
    assert "Cannot perform READ" in str(exc_info.value)

    # Attempting to write before BEGIN
    with pytest.raises(RuntimeError) as exc_info:
        tx.write(50.0)
    assert "Cannot perform WRITE" in str(exc_info.value)

    # Attempting to commit before BEGIN
    with pytest.raises(RuntimeError) as exc_info:
        tx.commit()
    assert "Cannot COMMIT" in str(exc_info.value)
