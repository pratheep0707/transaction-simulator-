"""
Automated Test Suite for ACID Properties.
Covers Atomicity, Consistency, Isolation, and Durability.
Includes both unit tests and live PostgreSQL integration tests.
"""

from unittest.mock import MagicMock
import pytest

from config.settings import get_settings
from database.connection import test_connection as check_db_conn
from engine.acid_scenarios import AcidScenarioRunner
from engine.event_logger import EventLogger
from engine.models import OperationType, TransactionState
from engine.transaction_manager import ManagedTransaction


# =============================================================================
# 1. ATOMICITY TESTS
# =============================================================================

def test_atomicity_success_live():
    """Live PostgreSQL test: All updates succeed and commit atomically (A: 100->80, B: 50->70)."""
    settings = get_settings()
    if not settings.is_configured:
        pytest.skip("Database not configured in .env")

    is_ok, _, _ = check_db_conn()
    if not is_ok:
        pytest.skip("Database is unreachable")

    runner = AcidScenarioRunner()
    result = runner.run_atomicity_experiment(
        initial_a=100.0,
        initial_b=50.0,
        transfer_amount=20.0,
        mode="SUCCESS",
    )

    assert result.status == "PASS"
    assert result.t1_state == "COMMITTED"
    assert result.final_value == 80.0
    assert result.expected_value == 80.0
    assert any(e.event_type == OperationType.COMMIT for e in result.events)


def test_atomicity_controlled_failure_rollback_live():
    """Live PostgreSQL test: Controlled failure triggers ROLLBACK; partial update discarded."""
    settings = get_settings()
    if not settings.is_configured:
        pytest.skip("Database not configured in .env")

    is_ok, _, _ = check_db_conn()
    if not is_ok:
        pytest.skip("Database is unreachable")

    runner = AcidScenarioRunner()
    result = runner.run_atomicity_experiment(
        initial_a=100.0,
        initial_b=50.0,
        transfer_amount=20.0,
        mode="FAILURE",
    )

    assert result.status == "PASS"
    assert result.t1_state == "ABORTED"
    assert result.final_value == 100.0
    assert result.expected_value == 100.0
    assert any(e.event_type == OperationType.ROLLBACK for e in result.events)
    assert any(e.event_type == OperationType.ERROR for e in result.events)


# =============================================================================
# 2. CONSISTENCY TESTS
# =============================================================================

def test_consistency_check_violation_rollback_live():
    """Live PostgreSQL test: CHECK constraint (value >= 0) violation triggers rollback; initial state preserved."""
    settings = get_settings()
    if not settings.is_configured:
        pytest.skip("Database not configured in .env")

    is_ok, _, _ = check_db_conn()
    if not is_ok:
        pytest.skip("Database is unreachable")

    runner = AcidScenarioRunner()
    result = runner.run_consistency_experiment(
        initial_value=100.0,
        attempted_value=-50.0,
    )

    assert result.status == "PASS"
    assert result.t1_state == "ABORTED"
    assert result.final_value == 100.0
    assert result.expected_value == 100.0
    assert result.error_message is not None
    assert "23514" in result.error_message or "check_violation" in result.error_message.lower()
    assert any(e.event_type == OperationType.ERROR for e in result.events)
    assert any(e.event_type == OperationType.ROLLBACK for e in result.events)


def test_consistency_valid_value_commit_live():
    """Live PostgreSQL test: Valid value (value >= 0) commits successfully and updates database."""
    settings = get_settings()
    if not settings.is_configured:
        pytest.skip("Database not configured in .env")

    is_ok, _, _ = check_db_conn()
    if not is_ok:
        pytest.skip("Database is unreachable")

    runner = AcidScenarioRunner()
    result = runner.run_consistency_experiment(
        initial_value=100.0,
        attempted_value=150.0,
    )

    assert result.status == "PASS"
    assert result.t1_state == "COMMITTED"
    assert result.final_value == 150.0
    assert result.expected_value == 150.0
    assert any(e.event_type == OperationType.COMMIT for e in result.events)


# =============================================================================
# 3. ISOLATION TESTS
# =============================================================================

def test_isolation_lost_update_live():
    """Live PostgreSQL test: Uncontrolled concurrent updates result in Lost Update anomaly (final = 150 instead of 130)."""
    settings = get_settings()
    if not settings.is_configured:
        pytest.skip("Database not configured in .env")

    is_ok, _, _ = check_db_conn()
    if not is_ok:
        pytest.skip("Database is unreachable")

    runner = AcidScenarioRunner()
    result = runner.run_isolation_experiment(
        initial_value=100.0,
        mode="LOST_UPDATE",
        t1_amount=50.0,
        t2_amount=20.0,
    )

    assert result.status == "PASS"
    assert result.final_value == 150.0
    assert result.expected_value == 150.0
    assert result.t1_state == "COMMITTED"
    assert result.t2_state == "COMMITTED"


def test_isolation_row_locking_live():
    """Live PostgreSQL test: SELECT ... FOR UPDATE serializes concurrent updates preventing Lost Update (final = 130)."""
    settings = get_settings()
    if not settings.is_configured:
        pytest.skip("Database not configured in .env")

    is_ok, _, _ = check_db_conn()
    if not is_ok:
        pytest.skip("Database is unreachable")

    runner = AcidScenarioRunner()
    result = runner.run_isolation_experiment(
        initial_value=100.0,
        mode="ROW_LOCKING",
        t1_amount=50.0,
        t2_amount=20.0,
    )

    assert result.status == "PASS"
    assert result.final_value == 130.0
    assert result.expected_value == 130.0
    assert any(e.event_type == OperationType.LOCK_WAIT for e in result.events)
    assert any(e.event_type == OperationType.LOCK_ACQUIRE for e in result.events)
    assert any(e.event_type == OperationType.LOCK_RELEASED for e in result.events)


# =============================================================================
# 4. DURABILITY TESTS
# =============================================================================

def test_durability_cross_connection_live():
    """Live PostgreSQL test: Committed update survives connection termination and is verified on a fresh connection."""
    settings = get_settings()
    if not settings.is_configured:
        pytest.skip("Database not configured in .env")

    is_ok, _, _ = check_db_conn()
    if not is_ok:
        pytest.skip("Database is unreachable")

    runner = AcidScenarioRunner()
    result = runner.run_durability_experiment(
        initial_value=100.0,
        commit_value=250.0,
    )

    assert result.status == "PASS"
    assert result.final_value == 250.0
    assert result.expected_value == 250.0
    assert any(e.event_type == OperationType.COMMIT for e in result.events)

