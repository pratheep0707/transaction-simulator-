"""
ACID Properties Demonstration Engine.
Provides interactive, deterministic experiments for the four fundamental DBMS guarantees:
- Atomicity: All-or-nothing execution with commit and rollback.
- Consistency: Integrity constraints (e.g. CHECK constraints) and invariant preservation.
- Isolation: Concurrency independence (Lost Update anomaly vs 2PL Pessimistic Locking).
- Durability: Persistence of committed updates verified across independent connections.
"""

from datetime import datetime
from decimal import Decimal
import time
from typing import Any, Dict, Optional
import uuid
import psycopg
from psycopg import errors as pg_errors

from config.settings import get_settings
from database.connection import get_raw_connection, test_connection
from database.repository import SimulatorRepository
from engine.concurrency import ScenarioCoordinator, spawn_transaction_worker
from engine.event_logger import EventLogger
from engine.models import (
    IST,
    IsolationLevel,
    OperationType,
    SimulationResult,
    TransactionState,
)
from engine.transaction_manager import ManagedTransaction


class AcidScenarioRunner:
    """Orchestrates interactive experiments verifying the 4 DBMS ACID properties."""

    def __init__(self):
        self.settings = get_settings()
        self.repo = SimulatorRepository()

    def _verify_database_available(self) -> None:
        """Verifies database connectivity before attempting live transactions."""
        is_ok, msg, _ = test_connection()
        if not is_ok:
            raise ConnectionError(
                f"Cannot execute ACID experiment: Database is not connected or configured. Details: {msg}"
            )

    # =========================================================================
    # 1. ATOMICITY: All or Nothing Execution
    # =========================================================================
    def run_atomicity_experiment(
        self,
        initial_a: float = 100.0,
        initial_b: float = 50.0,
        transfer_amount: float = 20.0,
        mode: str = "SUCCESS",  # "SUCCESS" or "FAILURE"
        on_event: Optional[Any] = None,
    ) -> SimulationResult:
        """
        Demonstrates Atomicity (All-or-Nothing):
        A transfer transaction consists of two related updates:
          1. Subtract transfer_amount from Record A.
          2. Add transfer_amount to Record B.

        MODE 'SUCCESS':
          Both updates execute within one transaction and COMMIT.
          Both changes persist: A = 80.0, B = 70.0.

        MODE 'FAILURE':
          Update 1 executes (A = 80.0 in transaction buffer).
          An injected error aborts the transaction before Update 2 can execute.
          ROLLBACK is executed.
          PostgreSQL discards the uncommitted change to A.
          Final state: A = 100.0, B = 50.0 (neither change persists).
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo, on_event=on_event)

        item_a = "SIM_ATOM_A"
        item_b = "SIM_ATOM_B"
        is_success_mode = str(mode).upper() == "SUCCESS"
        scenario_title = (
            "Atomicity: Successful Multi-Record Commit (All)"
            if is_success_mode
            else "Atomicity: Rollback on Controlled Failure (Nothing)"
        )

        # Step 0: Initialize two simulator-owned test records
        self.repo.reset_test_item(item_a, initial_value=initial_a)
        self.repo.reset_test_item(item_b, initial_value=initial_b)

        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=(
                f"Initialized simulator test records: "
                f"Record A ('{item_a}') = {initial_a:.2f}, "
                f"Record B ('{item_b}') = {initial_b:.2f}"
            ),
            observed_value=initial_a,
        )

        t1_state_final = "COMMITTED"
        error_encountered = None

        # Execute transaction on dedicated connection
        with get_raw_connection(autocommit=False) as conn:
            tx = ManagedTransaction("T1", conn, logger, item_id=item_a)
            try:
                # 1. BEGIN
                tx.begin(IsolationLevel.READ_COMMITTED)

                # 2. Read and subtract from Record A
                val_a = tx.read(item_id=item_a)
                new_a = round(float(val_a) - float(transfer_amount), 2)
                tx.write(new_a, item_id=item_a)
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.STATE_CHANGE,
                    description=(
                        f"Subtracted {transfer_amount:.2f} from Record A: {val_a:.2f} -> {new_a:.2f} "
                        f"[Uncommitted write staged in T1 buffer]"
                    ),
                    observed_value=new_a,
                )

                if is_success_mode:
                    # 3. Read and add to Record B
                    val_b = tx.read(item_id=item_b)
                    new_b = round(float(val_b) + float(transfer_amount), 2)
                    tx.write(new_b, item_id=item_b)
                    logger.log(
                        transaction_id="T1",
                        event_type=OperationType.STATE_CHANGE,
                        description=(
                            f"Added {transfer_amount:.2f} to Record B: {val_b:.2f} -> {new_b:.2f} "
                            f"[Uncommitted write staged in T1 buffer]"
                        ),
                        observed_value=new_b,
                    )

                    # 4. COMMIT
                    tx.commit()
                    t1_state_final = "COMMITTED"
                else:
                    # Controlled Failure: trigger error before updating Record B
                    logger.log(
                        transaction_id="T1",
                        event_type=OperationType.STATE_CHANGE,
                        description="Triggering injected controlled error before Record B update...",
                    )
                    try:
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1 / 0 AS controlled_error;")
                            cur.fetchone()
                    except Exception as err:
                        error_encountered = f"PostgreSQL Exception (division_by_zero): {err}"
                        logger.log(
                            transaction_id="T1",
                            event_type=OperationType.ERROR,
                            description=(
                                f"Controlled failure injected: {error_encountered}. "
                                f"PostgreSQL marked transaction as FAILED/ABORTED."
                            ),
                        )
                        tx._transition_state(
                            TransactionState.FAILED,
                            reason="Injected error interrupted execution before Record B was updated",
                        )

                    # 5. ROLLBACK to undo partial changes
                    tx.rollback()
                    t1_state_final = "ABORTED"

            except Exception as ex:
                if tx.state != TransactionState.ABORTED:
                    tx.rollback()
                t1_state_final = "ABORTED"
                if not error_encountered:
                    error_encountered = str(ex)

        # Step 6: Verify final committed values in PostgreSQL via separate independent read
        final_a = None
        final_b = None
        with get_raw_connection(autocommit=True) as check_conn:
            with check_conn.cursor() as cur:
                cur.execute("SELECT value FROM sim_test_data WHERE item_id = %s", (item_a,))
                row_a = cur.fetchone()
                if row_a:
                    final_a = float(row_a[0])

                cur.execute("SELECT value FROM sim_test_data WHERE item_id = %s", (item_b,))
                row_b = cur.fetchone()
                if row_b:
                    final_b = float(row_b[0])

        if is_success_mode:
            expected_a = round(initial_a - transfer_amount, 2)
            expected_b = round(initial_b + transfer_amount, 2)
            passed = (final_a == expected_a) and (final_b == expected_b)
            explanation = (
                f"ATOMICITY (ALL) VERIFIED: Transaction T1 successfully executed both updates "
                f"(Record A: {initial_a} -> {final_a}, Record B: {initial_b} -> {final_b}) and COMMITTED. "
                f"All changes were written atomically to PostgreSQL storage."
            )
        else:
            expected_a = round(initial_a, 2)
            expected_b = round(initial_b, 2)
            passed = (final_a == expected_a) and (final_b == expected_b)
            explanation = (
                f"ATOMICITY (NOTHING) VERIFIED: An injected failure interrupted T1 after Record A was modified to {initial_a - transfer_amount}, "
                f"but BEFORE Record B was updated. T1 executed ROLLBACK. PostgreSQL discarded the partial uncommitted change to Record A. "
                f"Database reads confirm Record A remains {final_a} and Record B remains {final_b}."
            )

        status_str = "PASS" if passed else "FAIL"

        result = SimulationResult(
            run_id=run_id,
            scenario_name=scenario_title,
            status=status_str,
            initial_value=initial_a,
            final_value=final_a,
            expected_value=expected_a,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
            error_message=error_encountered,
            t1_state=t1_state_final,
            t1_summary=(
                f"Mode: {mode} | Record A: {initial_a} -> {final_a} (exp: {expected_a}) | "
                f"Record B: {initial_b} -> {final_b} (exp: {expected_b})"
            ),
        )

        # Persist run and events to database
        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=initial_a,
            final_value=final_a,
            expected_value=expected_a,
            details={
                "mode": mode,
                "property": "Atomicity",
                "transfer_amount": transfer_amount,
                "record_a_initial": initial_a,
                "record_b_initial": initial_b,
                "record_a_final": final_a,
                "record_b_final": final_b,
                "record_a_expected": expected_a,
                "record_b_expected": expected_b,
                "explanation": explanation,
                "passed": passed,
                "t1_state": t1_state_final,
            },
        )
        logger.persist_to_database()

        return result

    # =========================================================================
    # 2. CONSISTENCY: Preservation of Valid Database Rules & Constraints
    # =========================================================================
    def run_consistency_experiment(
        self,
        initial_value: float = 100.0,
        attempted_value: float = -50.0,
        on_event: Optional[Any] = None,
    ) -> SimulationResult:
        """
        Demonstrates Consistency:
        Preserves defined database constraints and application invariants.
        Operates on dedicated table 'sim_consistency_data' with constraint:
          CHECK (value >= 0)

        If attempted_value < 0:
          PostgreSQL rejects the statement with SQLSTATE 23514 (check_violation).
          The transaction is aborted and rolled back.
          Verification confirms the committed value remains initial_value (e.g. 100.0).

        If attempted_value >= 0:
          PostgreSQL accepts the statement.
          The transaction commits.
          Verification confirms the committed value is updated to attempted_value.
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo, on_event=on_event)

        item_id = "SIM_CONSISTENCY_X"
        self.repo.reset_consistency_item(item_id, initial_value=initial_value)

        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=(
                f"Initialized constrained resource '{item_id}' in 'sim_consistency_data' "
                f"to value = {initial_value:.2f} [Table enforces CHECK (value >= 0)]"
            ),
            observed_value=initial_value,
        )

        t1_state_final = "COMMITTED"
        error_details = None
        violation_caught = False

        with get_raw_connection(autocommit=False) as conn:
            tx = ManagedTransaction("T1", conn, logger, item_id=item_id)
            try:
                # 1. BEGIN
                tx.begin(IsolationLevel.READ_COMMITTED)

                # 2. Read initial value
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM sim_consistency_data WHERE item_id = %s;", (item_id,))
                    row = cur.fetchone()
                    read_val = float(row[0]) if row else initial_value
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.READ,
                    description=f"T1 read initial value = {read_val:.2f} from 'sim_consistency_data'",
                    observed_value=read_val,
                )

                # 3. Attempt update with proposed value
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.STATE_CHANGE,
                    description=(
                        f"T1 attempting UPDATE item '{item_id}' SET value = {attempted_value:.2f} "
                        f"[Evaluating constraint: CHECK (value >= 0)]"
                    ),
                    observed_value=attempted_value,
                )

                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE sim_consistency_data SET value = %s, updated_at = CURRENT_TIMESTAMP WHERE item_id = %s;",
                            (Decimal(str(attempted_value)), item_id),
                        )
                    # If execution succeeded without exception:
                    logger.log(
                        transaction_id="T1",
                        event_type=OperationType.WRITE,
                        description=f"T1 wrote valid value {attempted_value:.2f}. Database constraint satisfied.",
                        observed_value=attempted_value,
                    )
                    tx.commit()
                    t1_state_final = "COMMITTED"

                except (psycopg.errors.CheckViolation, psycopg.Error, Exception) as err:
                    violation_caught = True
                    sqlstate = getattr(err, "sqlstate", "23514") or "23514"
                    pg_err_msg = getattr(err, "pgerror", str(err)).strip().split("\n")[0]
                    error_details = f"PostgreSQL Exception (SQLSTATE {sqlstate}: check_violation) - {pg_err_msg}"

                    logger.log(
                        transaction_id="T1",
                        event_type=OperationType.ERROR,
                        description=(
                            f"PostgreSQL Integrity Constraint Violation: {error_details}. "
                            f"Proposed value {attempted_value:.2f} violates CHECK (value >= 0)."
                        ),
                    )
                    tx._transition_state(
                        TransactionState.FAILED,
                        reason="Integrity constraint violation (CHECK value >= 0)",
                    )
                    tx.rollback()
                    t1_state_final = "ABORTED"

            except Exception as ex:
                if tx.state != TransactionState.ABORTED:
                    tx.rollback()
                t1_state_final = "ABORTED"
                if not error_details:
                    error_details = str(ex)

        # 4. Verify final database value via independent read
        final_val = None
        with get_raw_connection(autocommit=True) as check_conn:
            final_val = self.repo.get_consistency_item_value(check_conn, item_id)

        if attempted_value < 0:
            expected_val = float(initial_value)
            passed = (final_val == expected_val) and violation_caught
            explanation = (
                f"CONSISTENCY PRESERVED: Proposed value {attempted_value:.2f} violated the database integrity constraint "
                f"(CHECK value >= 0). PostgreSQL rejected the UPDATE statement with SQLSTATE 23514 (check_violation) and "
                f"aborted the transaction. Following ROLLBACK, the committed database value remains {final_val:.2f}, "
                f"preserving database consistency."
            )
        else:
            expected_val = float(attempted_value)
            passed = (final_val == expected_val)
            explanation = (
                f"CONSISTENCY PRESERVED: Proposed value {attempted_value:.2f} satisfied the database integrity constraint "
                f"(CHECK value >= 0). The transaction COMMITTED successfully and the new valid state ({final_val:.2f}) was persisted."
            )

        status_str = "PASS" if passed else "FAIL"

        result = SimulationResult(
            run_id=run_id,
            scenario_name="Consistency: Database Constraint Enforcement",
            status=status_str,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
            error_message=error_details,
            t1_state=t1_state_final,
            t1_summary=(
                f"Proposed: {attempted_value:.2f} | Constraint: CHECK (value >= 0) | "
                f"Final DB Value: {final_val:.2f} (Expected: {expected_val:.2f})"
            ),
        )

        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            details={
                "property": "Consistency",
                "table": "sim_consistency_data",
                "constraint": "CHECK (value >= 0)",
                "attempted_value": attempted_value,
                "violation_caught": violation_caught,
                "error_details": error_details,
                "passed": passed,
                "explanation": explanation,
            },
        )
        logger.persist_to_database()
        return result

    # =========================================================================
    # 3. ISOLATION: Concurrent Transaction Control
    # =========================================================================
    def run_isolation_experiment(
        self,
        initial_value: float = 100.0,
        mode: str = "LOST_UPDATE",  # "LOST_UPDATE" or "ROW_LOCKING"
        t1_amount: float = 50.0,
        t2_amount: float = 20.0,
        on_event: Optional[Any] = None,
    ) -> SimulationResult:
        """
        Demonstrates Isolation:
        Two concurrent transactions (T1 and T2) access the same item 'SIM_ISOLATION_X'.

        MODE 'LOST_UPDATE' (Unsafe Read-Modify-Write):
          T1 reads X (100).
          T2 reads X (100), writes X - 20 (80), commits.
          T1 writes previously computed X + 50 (150), commits.
          Result: Final value = 150. T2's update was lost!

        MODE 'ROW_LOCKING' (Pessimistic Concurrency Control):
          T1 executes SELECT ... FOR UPDATE on X.
          T2 executes SELECT ... FOR UPDATE on X and enters genuine lock wait.
          T1 writes X + 50 (150) and commits (releases lock).
          T2 unblocks, reads committed value (150), writes 150 - 20 (130), commits.
          Result: Final value = 130. Correct serialization!
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo, on_event=on_event)

        item_id = "SIM_ISOLATION_X"
        self.repo.reset_test_item(item_id, initial_value=initial_value)

        is_lost_update = str(mode).upper() == "LOST_UPDATE"
        scenario_title = (
            "Isolation: Lost Update (Concurrency Anomaly)"
            if is_lost_update
            else "Isolation: Lost Update Prevented by Row Locking"
        )

        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=f"Initialized isolated resource '{item_id}' to value = {initial_value:.2f}",
            observed_value=initial_value,
        )

        coordinator = ScenarioCoordinator(default_timeout_sec=12.0)

        if is_lost_update:
            # SCENARIO A: LOST UPDATE
            def worker_t1():
                with get_raw_connection(autocommit=False) as conn1:
                    tx1 = ManagedTransaction("T1", conn1, logger, item_id=item_id)
                    try:
                        tx1.begin(IsolationLevel.READ_COMMITTED)
                        val1 = tx1.read(item_id=item_id)
                        calc1 = round(float(val1) + float(t1_amount), 2)
                        logger.log(
                            transaction_id="T1",
                            event_type=OperationType.STATE_CHANGE,
                            description=f"T1 computed {val1:.2f} + {t1_amount:.2f} = {calc1:.2f} (Holding result in memory)",
                            observed_value=calc1,
                        )
                        coordinator.signal("t1_read")

                        # Wait for T2 to execute, write, and commit
                        coordinator.wait_for("t2_committed", timeout=10.0)

                        logger.log(
                            transaction_id="T1",
                            event_type=OperationType.STATE_CHANGE,
                            description=f"T1 resuming. Writing stale computed value {calc1:.2f} [Unsafe Read-Modify-Write]",
                            observed_value=calc1,
                        )
                        tx1.write(calc1, item_id=item_id)
                        tx1.commit()
                        coordinator.signal("t1_committed")
                    except Exception as ex:
                        coordinator.record_error(ex)
                        tx1.rollback()

            def worker_t2():
                with get_raw_connection(autocommit=False) as conn2:
                    tx2 = ManagedTransaction("T2", conn2, logger, item_id=item_id)
                    try:
                        coordinator.wait_for("t1_read", timeout=10.0)
                        tx2.begin(IsolationLevel.READ_COMMITTED)
                        val2 = tx2.read(item_id=item_id)
                        calc2 = round(float(val2) - float(t2_amount), 2)
                        tx2.write(calc2, item_id=item_id)
                        tx2.commit()
                        logger.log(
                            transaction_id="T2",
                            event_type=OperationType.STATE_CHANGE,
                            description=f"T2 committed value {calc2:.2f}. Signalling T1 to resume...",
                            observed_value=calc2,
                        )
                        coordinator.signal("t2_committed")
                    except Exception as ex:
                        coordinator.record_error(ex)
                        tx2.rollback()

            th1 = spawn_transaction_worker(worker_t1, name="Worker-T1")
            th2 = spawn_transaction_worker(worker_t2, name="Worker-T2")
            th1.join(timeout=14.0)
            th2.join(timeout=14.0)

        else:
            # SCENARIO B: ROW-LEVEL LOCKING (SELECT ... FOR UPDATE)
            def worker_t1_lock():
                with get_raw_connection(autocommit=False) as conn1:
                    tx1 = ManagedTransaction("T1", conn1, logger, item_id=item_id)
                    try:
                        tx1.begin(IsolationLevel.READ_COMMITTED)
                        val1 = tx1.read(item_id=item_id, for_update=True)
                        coordinator.signal("t1_locked")

                        # Hold lock briefly to ensure T2 attempts concurrent access and genuinely waits
                        time.sleep(1.0)

                        calc1 = round(float(val1) + float(t1_amount), 2)
                        tx1.write(calc1, item_id=item_id)
                        tx1.commit()
                        logger.log(
                            transaction_id="T1",
                            event_type=OperationType.LOCK_RELEASED,
                            description=f"T1 COMMIT executed. Exclusive row lock released on '{item_id}'.",
                            observed_value=calc1,
                        )
                        coordinator.signal("t1_done")
                    except Exception as ex:
                        coordinator.record_error(ex)
                        tx1.rollback()

            def worker_t2_lock():
                with get_raw_connection(autocommit=False) as conn2:
                    tx2 = ManagedTransaction("T2", conn2, logger, item_id=item_id)
                    try:
                        coordinator.wait_for("t1_locked", timeout=10.0)
                        tx2.begin(IsolationLevel.READ_COMMITTED)

                        with conn2.cursor() as cur:
                            cur.execute("SET lock_timeout = '6000ms';")

                        logger.log(
                            transaction_id="T2",
                            event_type=OperationType.LOCK_WAIT,
                            description=f"T2 executing SELECT ... FOR UPDATE. Row '{item_id}' is locked by T1; T2 enters genuine PostgreSQL lock wait...",
                        )

                        # This call blocks inside PostgreSQL until T1 commits!
                        val2 = tx2.read(item_id=item_id, for_update=True)

                        logger.log(
                            transaction_id="T2",
                            event_type=OperationType.LOCK_ACQUIRE,
                            description=f"T2 acquired lock following T1 release. Read updated committed value = {val2:.2f}",
                            observed_value=val2,
                        )

                        calc2 = round(float(val2) - float(t2_amount), 2)
                        tx2.write(calc2, item_id=item_id)
                        tx2.commit()
                        coordinator.signal("t2_done")
                    except Exception as ex:
                        coordinator.record_error(ex)
                        tx2.rollback()

            th1 = spawn_transaction_worker(worker_t1_lock, name="Worker-T1-Lock")
            th2 = spawn_transaction_worker(worker_t2_lock, name="Worker-T2-Lock")
            th1.join(timeout=14.0)
            th2.join(timeout=14.0)

        # Final verification read from PostgreSQL
        final_val = None
        with get_raw_connection(autocommit=True) as check_conn:
            final_val = self.repo.get_test_item_value(check_conn, item_id)

        if is_lost_update:
            expected_val = round(initial_value + t1_amount, 2)  # 150.0
            correct_combined = round(initial_value + t1_amount - t2_amount, 2)  # 130.0
            passed = (final_val == expected_val)
            explanation = (
                f"LOST UPDATE DEMONSTRATED: Both T1 and T2 concurrently read initial value {initial_value:.2f}. "
                f"T2 committed its update ({initial_value:.2f} - {t2_amount:.2f} = {initial_value - t2_amount:.2f}). "
                f"Then T1 overwrote the row with its stale calculation ({initial_value:.2f} + {t1_amount:.2f} = {final_val:.2f}), "
                f"silently destroying T2's update! The correct serialized value would have been {correct_combined:.2f}."
            )
        else:
            expected_val = round(initial_value + t1_amount - t2_amount, 2)  # 130.0
            passed = (final_val == expected_val)
            explanation = (
                f"LOST UPDATE PREVENTED: T1 acquired an exclusive row-level lock via SELECT ... FOR UPDATE. "
                f"When T2 attempted concurrent access, PostgreSQL's Lock Manager held T2 in a waiting state until T1 committed. "
                f"T2 then unblocked, read T1's committed value ({initial_value + t1_amount:.2f}), and applied its update. "
                f"Final value is exactly {final_val:.2f}, matching expected {expected_val:.2f}."
            )

        status_str = "PASS" if passed else "FAIL"

        result = SimulationResult(
            run_id=run_id,
            scenario_name=scenario_title,
            status=status_str,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
            t1_state="COMMITTED",
            t2_state="COMMITTED",
            t1_summary=f"T1: +{t1_amount:.2f} | T2: -{t2_amount:.2f} | Final: {final_val:.2f} (Expected: {expected_val:.2f})",
        )

        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            details={
                "property": "Isolation",
                "mode": mode,
                "t1_amount": t1_amount,
                "t2_amount": t2_amount,
                "final_value": final_val,
                "expected_value": expected_val,
                "passed": passed,
                "explanation": explanation,
            },
        )
        logger.persist_to_database()
        return result

    # =========================================================================
    # 4. DURABILITY: Persistence of Committed Data
    # =========================================================================
    def run_durability_experiment(
        self,
        initial_value: float = 100.0,
        commit_value: float = 200.0,
        on_event: Optional[Any] = None,
    ) -> SimulationResult:
        """
        Demonstrates Durability:
        Persistence and cross-connection visibility of committed updates.
        1. Connection 1 begins, updates SIM_DURABILITY_X to commit_value, and COMMITS.
        2. Connection 1 is explicitly terminated and closed.
        3. A completely separate, newly created Connection 2 reads the record.
        4. Verifies the committed value persisted and is visible.
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo, on_event=on_event)

        item_id = "SIM_DURABILITY_X"
        self.repo.reset_test_item(item_id, initial_value=initial_value)

        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=f"Initialized durability resource '{item_id}' to value = {initial_value:.2f}",
            observed_value=initial_value,
        )

        # Phase 1: Update and COMMIT on Connection 1
        conn1 = get_raw_connection(autocommit=False)
        try:
            tx1 = ManagedTransaction("T1_WRITER", conn1, logger, item_id=item_id)
            tx1.begin(IsolationLevel.READ_COMMITTED)
            tx1.read(item_id=item_id)
            tx1.write(commit_value, item_id=item_id)
            tx1.commit()
        finally:
            conn1.close()
            logger.log(
                transaction_id="T1_WRITER",
                event_type=OperationType.STATE_CHANGE,
                description="Explicitly closed and destroyed database Connection 1 (Writer session terminated).",
            )

        # Phase 2: Independent verification on Connection 2
        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.STATE_CHANGE,
            description="Opening independent database Connection 2 to verify persistence of committed data...",
        )
        read_val_conn2 = None
        conn2 = get_raw_connection(autocommit=True)
        try:
            with conn2.cursor() as cur:
                cur.execute("SELECT value FROM sim_test_data WHERE item_id = %s;", (item_id,))
                row = cur.fetchone()
                if row:
                    read_val_conn2 = float(row[0])
            logger.log(
                transaction_id="T2_READER",
                event_type=OperationType.READ,
                description=f"Independent Connection 2 read value = {read_val_conn2:.2f} from persistent PostgreSQL storage.",
                observed_value=read_val_conn2,
            )
        finally:
            conn2.close()
            logger.log(
                transaction_id="T2_READER",
                event_type=OperationType.STATE_CHANGE,
                description="Closed independent database Connection 2.",
            )

        passed = (read_val_conn2 == commit_value)
        status_str = "PASS" if passed else "FAIL"

        explanation = (
            f"DURABILITY VERIFIED: Transaction T1 updated '{item_id}' from {initial_value:.2f} to {commit_value:.2f} "
            f"and COMMITTED. Connection 1 was explicitly terminated. A fresh, independent connection (Connection 2) "
            f"subsequently queried the row and observed {read_val_conn2:.2f}. "
            f"Under normal operation, PostgreSQL guarantees that once a COMMIT is acknowledged, the transaction's "
            f"modifications are flushed to the Write-Ahead Log (WAL) and persist indefinitely."
        )

        result = SimulationResult(
            run_id=run_id,
            scenario_name="Durability: Persistence of Committed Data",
            status=status_str,
            initial_value=initial_value,
            final_value=read_val_conn2,
            expected_value=commit_value,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
            t1_state="COMMITTED",
            t1_summary=f"Wrote {commit_value:.2f} on Conn 1 (closed) | Read {read_val_conn2:.2f} on independent Conn 2",
        )

        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=initial_value,
            final_value=read_val_conn2,
            expected_value=commit_value,
            details={
                "property": "Durability",
                "initial_value": initial_value,
                "commit_value": commit_value,
                "read_value_conn2": read_val_conn2,
                "passed": passed,
                "explanation": explanation,
            },
        )
        logger.persist_to_database()
        return result

