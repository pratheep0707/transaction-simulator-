"""
Tests for scenario coordination, synchronization barriers, and database scenarios.
Includes offline coordination unit tests and conditional live integration tests.
"""

import threading
import time
import pytest

from config.settings import get_settings
from database.connection import clean_error_message, test_connection as check_db_connection
from engine.concurrency import ScenarioCoordinator
from engine.scenarios import ScenarioRunner


def test_scenario_coordinator_signaling():
    """Verifies that ScenarioCoordinator properly coordinates thread milestones."""
    coordinator = ScenarioCoordinator(default_timeout_sec=2.0)
    worker_reached = False

    def worker():
        nonlocal worker_reached
        coordinator.wait_for("start_step")
        worker_reached = True
        coordinator.signal("worker_done")

    t = threading.Thread(target=worker)
    t.start()

    time.sleep(0.1)
    assert worker_reached is False

    coordinator.signal("start_step")
    coordinator.wait_for("worker_done")
    t.join(timeout=1.0)

    assert worker_reached is True


def test_scenario_coordinator_timeout():
    """Verifies that coordinator raises TimeoutError on deadlocked/delayed steps."""
    coordinator = ScenarioCoordinator(default_timeout_sec=0.2)

    with pytest.raises(TimeoutError) as exc_info:
        coordinator.wait_for("non_existent_event")
    assert "Coordination timeout" in str(exc_info.value)


def test_apply_operation_logic():
    """Tests arithmetic operations and formula calculations."""
    from engine.scenarios import apply_operation
    assert apply_operation(100.0, "ADD", 50.0) == 150.0
    assert apply_operation(150.0, "SUBTRACT", 20.0) == 130.0
    assert apply_operation(100.0, "SET", 42.0) == 42.0


def test_event_logger_live_callback():
    """Verifies that EventLogger triggers live callback for stream rendering."""
    from engine.event_logger import EventLogger
    from engine.models import OperationType
    captured = []
    logger = EventLogger("test-stream", on_event=lambda e: captured.append(e))
    logger.log("T1", OperationType.READ, "Test description", observed_value=100.0)
    assert len(captured) == 1
    assert captured[0].transaction_id == "T1"
    assert captured[0].observed_value == 100.0


def test_clean_error_message_strips_passwords():
    """Ensures sensitive passwords are removed from connection error strings."""
    raw_error = Exception("FATAL: password authentication failed for user 'postgres' with password 'SuperSecret123'")
    cleaned = clean_error_message(raw_error)
    assert "SuperSecret123" not in cleaned
    assert "password" not in cleaned.lower() or "authentication failed" in cleaned.lower()


def test_connection_diagnostic_unconfigured():
    """Verifies that test_connection returns False gracefully if unconfigured."""
    is_ok, msg, meta = check_db_connection()
    if not get_settings().is_configured:
        assert is_ok is False
        assert "DATABASE_URL is missing or using placeholder" in msg
        assert meta["status"] == "UNCONFIGURED"


@pytest.mark.skipif(not get_settings().is_configured, reason="Supabase database not configured in .env")
def test_live_database_connection():
    """Tests live connection against Supabase when configured."""
    is_ok, msg, meta = check_db_connection()
    assert is_ok is True
    assert meta["status"] == "CONNECTED"


@pytest.mark.skipif(not get_settings().is_configured, reason="Supabase database not configured in .env")
def test_live_lost_update_scenario():
    """Tests live execution of Scenario A against PostgreSQL."""
    runner = ScenarioRunner()
    result = runner.run_lost_update_scenario(initial_value=100.0)
    assert result.status == "ANOMALY_DEMONSTRATED"
    assert result.final_value == 150.0
    assert result.expected_value == 130.0


@pytest.mark.skipif(not get_settings().is_configured, reason="Supabase database not configured in .env")
def test_live_pessimistic_locking_scenario():
    """Tests live execution of Scenario B against PostgreSQL."""
    runner = ScenarioRunner()
    result = runner.run_pessimistic_locking_scenario(initial_value=100.0)
    assert result.status == "PREVENTED"
    assert result.final_value == 130.0
    assert result.expected_value == 130.0
