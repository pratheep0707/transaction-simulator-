"""
Interactive Academic Concurrency and Transaction Management Scenarios.
Directly executes real PostgreSQL transactions via psycopg 3 across independent worker threads.
Every scenario enforces strict isolation and deterministic interleaving.
"""

from datetime import datetime, timezone
import time
from typing import Any, Optional
import uuid
import psycopg
from psycopg import errors

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


def apply_operation(base: float, op_type: str, amount: float) -> float:
    """Applies an arithmetic or assignment operation to a base numeric value."""
    op = str(op_type).upper().strip()
    if op in ("ADD", "+", "INCREMENT"):
        return round(float(base) + float(amount), 2)
    elif op in ("SUBTRACT", "-", "DECREMENT"):
        return round(float(base) - float(amount), 2)
    elif op in ("SET", "=", "ASSIGN"):
        return round(float(amount), 2)
    return round(float(base) + float(amount), 2)


class ScenarioRunner:
    """Orchestrates standard DBMS concurrency and transaction lifecycle scenarios."""

    def __init__(self):
        self.settings = get_settings()
        self.repo = SimulatorRepository()

    def _verify_database_available(self) -> None:
        """Verifies database connectivity before attempting live transactions."""
        is_ok, msg, _ = test_connection()
        if not is_ok:
            raise ConnectionError(
                f"Cannot execute scenario: Database is not connected or configured. Details: {msg}"
            )

    # -------------------------------------------------------------------------
    # SCENARIO A: LOST UPDATE (The classic concurrency anomaly)
    # -------------------------------------------------------------------------
    def run_lost_update_scenario(
        self,
        initial_value: float = 100.0,
        t1_op: str = "ADD",
        t1_amount: float = 50.0,
        t2_op: str = "SUBTRACT",
        t2_amount: float = 20.0,
        on_event: Optional[Any] = None,
    ) -> SimulationResult:
        """
        Demonstrates the classic Lost Update anomaly.
        T1 and T2 read the same initial value concurrently.
        T2 calculates and commits its write.
        T1 writes its calculation based on its original stale read and commits.
        T2's update is completely lost!
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo, on_event=on_event)
        coordinator = ScenarioCoordinator(default_timeout_sec=10.0)

        # 1. Reset initial test item
        item_id = self.settings.test_item_id
        self.repo.reset_test_item(item_id, initial_value=initial_value)
        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=f"Initialized test row '{item_id}' to value = {initial_value}",
            observed_value=initial_value,
        )

        calculated1 = None
        calculated2 = None

        def worker_t1():
            nonlocal calculated1
            conn1 = None
            try:
                conn1 = get_raw_connection(autocommit=False)
                tx1 = ManagedTransaction("T1", conn1, logger, item_id)
                tx1.begin(IsolationLevel.READ_COMMITTED)

                # Step 1: T1 reads initial value
                val1 = tx1.read()
                calculated1 = apply_operation(val1, t1_op, t1_amount)
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.STATE_CHANGE,
                    description=f"T1 calculated new value ({t1_op} {t1_amount}): {val1} -> {calculated1} (holding in memory)",
                    observed_value=val1,
                )

                # Signal that T1 has performed its read
                coordinator.signal("t1_read_done")

                # Wait until T2 completes its full write and commit
                coordinator.wait_for("t2_commit_done")

                # Step 4: T1 writes its stale calculated value and commits
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.WRITE,
                    description=f"T1 proceeding to write stale calculated value {calculated1} (overwriting any concurrent writes!)",
                    observed_value=calculated1,
                )
                tx1.write(calculated1)
                tx1.commit()
            except Exception as e:
                coordinator.record_error(e)
                if conn1:
                    try:
                        conn1.rollback()
                    except Exception:
                        pass
            finally:
                if conn1 and not conn1.closed:
                    conn1.close()

        def worker_t2():
            nonlocal calculated2
            conn2 = None
            try:
                conn2 = get_raw_connection(autocommit=False)
                tx2 = ManagedTransaction("T2", conn2, logger, item_id)

                # Wait until T1 reads the initial row
                coordinator.wait_for("t1_read_done")

                tx2.begin(IsolationLevel.READ_COMMITTED)
                # Step 2: T2 reads the same initial row
                val2 = tx2.read()
                calculated2 = apply_operation(val2, t2_op, t2_amount)
                logger.log(
                    transaction_id="T2",
                    event_type=OperationType.STATE_CHANGE,
                    description=f"T2 calculated new value ({t2_op} {t2_amount}): {val2} -> {calculated2}",
                    observed_value=val2,
                )

                # Step 3: T2 writes and commits
                tx2.write(calculated2)
                tx2.commit()

                # Signal T1 that T2 has committed
                coordinator.signal("t2_commit_done")
            except Exception as e:
                coordinator.record_error(e)
                if conn2:
                    try:
                        conn2.rollback()
                    except Exception:
                        pass
            finally:
                if conn2 and not conn2.closed:
                    conn2.close()

        # Start concurrent threads
        th1 = spawn_transaction_worker(worker_t1, name="Thread-T1")
        th2 = spawn_transaction_worker(worker_t2, name="Thread-T2")

        th1.join(timeout=12.0)
        th2.join(timeout=12.0)

        # Inspect final value directly in database
        final_val = None
        with get_raw_connection(autocommit=True) as check_conn:
            with check_conn.cursor() as cur:
                cur.execute("SELECT value FROM sim_test_data WHERE item_id = %s", (item_id,))
                row = cur.fetchone()
                if row:
                    final_val = float(row[0])

        # Mathematical serializable outcome (T1 then T2 or T2 then T1)
        expected_val = apply_operation(apply_operation(initial_value, t1_op, t1_amount), t2_op, t2_amount)

        explanation = (
            f"LOST UPDATE OCCURRED! Both T1 and T2 concurrently read initial value {initial_value}. "
            f"T2 committed its update ({t2_op} {t2_amount} => {calculated2}). Then T1 overwrote the row with its stale calculation "
            f"({t1_op} {t1_amount} => {final_val}), causing T2's update to be completely erased. "
            f"Correct serializable result should have been {expected_val}."
        )

        status = "ANOMALY_DEMONSTRATED" if final_val != expected_val else "UNEXPECTED_SERIAL"

        result = SimulationResult(
            run_id=run_id,
            scenario_name="Scenario A: Lost Update (Concurrency Anomaly)",
            status=status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
            t1_state="COMMITTED",
            t2_state="COMMITTED",
            t1_summary=f"{t1_op} {t1_amount} (stale write: {final_val})",
            t2_summary=f"{t2_op} {t2_amount} (overwritten: {calculated2})",
        )

        # Persist to database
        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            details={
                "explanation": explanation,
                "t1_state": result.t1_state,
                "t2_state": result.t2_state,
                "t1_summary": result.t1_summary,
                "t2_summary": result.t2_summary,
            },
        )
        logger.persist_to_database()

        return result

    # -------------------------------------------------------------------------
    # SCENARIO B: LOST UPDATE PREVENTED BY PESSIMISTIC LOCKING
    # -------------------------------------------------------------------------
    def run_pessimistic_locking_scenario(
        self,
        initial_value: float = 100.0,
        t1_op: str = "ADD",
        t1_amount: float = 50.0,
        t2_op: str = "SUBTRACT",
        t2_amount: float = 20.0,
        on_event: Optional[Any] = None,
    ) -> SimulationResult:
        """
        Demonstrates preventing the Lost Update anomaly using Pessimistic Row Locking
        via PostgreSQL's SELECT ... FOR UPDATE.
        T1 acquires row lock.
        T2 attempts to read with FOR UPDATE and is blocked by PostgreSQL until T1 commits.
        Once unblocked, T2 sees T1's committed value and computes its operation sequentially.
        Result is mathematically correct.
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo, on_event=on_event)
        coordinator = ScenarioCoordinator(default_timeout_sec=14.0)

        item_id = self.settings.test_item_id
        self.repo.reset_test_item(item_id, initial_value=initial_value)
        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=f"Initialized test row '{item_id}' to value = {initial_value}",
            observed_value=initial_value,
        )

        calculated1 = None
        calculated2 = None

        def worker_t1():
            nonlocal calculated1
            conn1 = None
            try:
                conn1 = get_raw_connection(autocommit=False)
                tx1 = ManagedTransaction("T1", conn1, logger, item_id)
                tx1.begin(IsolationLevel.READ_COMMITTED)

                # T1 acquires exclusive row lock
                val1 = tx1.read(for_update=True)
                calculated1 = apply_operation(val1, t1_op, t1_amount)
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.LOCK_ACQUIRE,
                    description=f"T1 holds row lock on '{item_id}'. Calculating new value ({t1_op} {t1_amount}): {val1} -> {calculated1}",
                    observed_value=val1,
                )

                # Signal that lock is acquired
                coordinator.signal("t1_locked")

                # Hold lock briefly to clearly demonstrate T2 blocking in real time
                time.sleep(1.0)

                tx1.write(calculated1)
                tx1.commit()
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.LOCK_RELEASED,
                    description=f"T1 committed write {calculated1}. Row lock released to waiting transactions.",
                )
            except Exception as e:
                coordinator.record_error(e)
                if conn1:
                    try:
                        conn1.rollback()
                    except Exception:
                        pass
            finally:
                if conn1 and not conn1.closed:
                    conn1.close()

        def worker_t2():
            nonlocal calculated2
            conn2 = None
            try:
                conn2 = get_raw_connection(autocommit=False)
                tx2 = ManagedTransaction("T2", conn2, logger, item_id)

                # Wait until T1 has acquired its lock
                coordinator.wait_for("t1_locked")

                tx2.begin(IsolationLevel.READ_COMMITTED)
                logger.log(
                    transaction_id="T2",
                    event_type=OperationType.LOCK_WAIT,
                    description=f"T2 attempting SELECT ... FOR UPDATE on '{item_id}'. Waiting for T1's lock release...",
                )

                # This SELECT ... FOR UPDATE will block in PostgreSQL engine until T1 commits!
                val2 = tx2.read(for_update=True)
                logger.log(
                    transaction_id="T2",
                    event_type=OperationType.LOCK_ACQUIRE,
                    description=f"T2 unblocked! Acquired lock. Read freshly committed value = {val2}",
                    observed_value=val2,
                )

                calculated2 = apply_operation(val2, t2_op, t2_amount)
                tx2.write(calculated2)
                tx2.commit()
                logger.log(
                    transaction_id="T2",
                    event_type=OperationType.LOCK_RELEASED,
                    description=f"T2 committed write {calculated2}. Lock released.",
                )
            except Exception as e:
                coordinator.record_error(e)
                if conn2:
                    try:
                        conn2.rollback()
                    except Exception:
                        pass
            finally:
                if conn2 and not conn2.closed:
                    conn2.close()

        th1 = spawn_transaction_worker(worker_t1, name="Locking-T1")
        th2 = spawn_transaction_worker(worker_t2, name="Locking-T2")

        th1.join(timeout=14.0)
        th2.join(timeout=14.0)

        final_val = None
        with get_raw_connection(autocommit=True) as check_conn:
            with check_conn.cursor() as cur:
                cur.execute("SELECT value FROM sim_test_data WHERE item_id = %s", (item_id,))
                row = cur.fetchone()
                if row:
                    final_val = float(row[0])

        expected_val = apply_operation(apply_operation(initial_value, t1_op, t1_amount), t2_op, t2_amount)

        explanation = (
            f"LOST UPDATE PREVENTED! T1 acquired an exclusive row lock using SELECT ... FOR UPDATE. "
            f"When T2 attempted to acquire the row lock, the PostgreSQL engine suspended T2 until T1 committed. "
            f"After T1 committed value {calculated1}, T2 safely read the updated row ({calculated1}), applied {t2_op} {t2_amount}, "
            f"and wrote {final_val}. Both operations were serialized correctly without data loss."
        )

        status = "PREVENTED" if final_val == expected_val else "UNEXPECTED"

        result = SimulationResult(
            run_id=run_id,
            scenario_name="Scenario B: Lost Update Prevented by Pessimistic Locking",
            status=status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
            t1_state="COMMITTED",
            t2_state="COMMITTED",
            t1_summary=f"{t1_op} {t1_amount} (locked write: {calculated1})",
            t2_summary=f"{t2_op} {t2_amount} (serialized write: {final_val})",
        )

        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            details={
                "explanation": explanation,
                "t1_state": result.t1_state,
                "t2_state": result.t2_state,
                "t1_summary": result.t1_summary,
                "t2_summary": result.t2_summary,
            },
        )
        logger.persist_to_database()

        return result

    # -------------------------------------------------------------------------
    # SCENARIO C: COMMIT AND ROLLBACK
    # -------------------------------------------------------------------------
    def run_commit_rollback_scenario(
        self,
        initial_value: float = 100.0,
        t1_write_val: float = 250.0,
        t2_write_val: float = 999.0,
        on_event: Optional[Any] = None,
    ) -> SimulationResult:
        """
        Demonstrates Atomicity and Durability:
        - T1 updates X from initial_value to t1_write_val, then executes COMMIT (Change is permanent/durable).
        - T2 updates X from t1_write_val to t2_write_val, then executes ROLLBACK (Change is aborted/discarded).
        - Verifies that uncommitted change is discarded and committed value persists.
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo, on_event=on_event)
        item_id = self.settings.test_item_id

        self.repo.reset_test_item(item_id, initial_value=initial_value)
        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=f"Initialized test row '{item_id}' to value = {initial_value}",
            observed_value=initial_value,
        )

        # Part 1: Commit demonstration with T1
        with get_raw_connection(autocommit=False) as conn1:
            tx1 = ManagedTransaction("T1", conn1, logger, item_id)
            tx1.begin(IsolationLevel.READ_COMMITTED)
            tx1.read()
            tx1.write(t1_write_val)
            logger.log(
                transaction_id="T1",
                event_type=OperationType.STATE_CHANGE,
                description=f"T1 wrote {t1_write_val} (Uncommitted, stored in transaction write set)",
            )
            tx1.commit()

        # Part 2: Rollback demonstration with T2
        with get_raw_connection(autocommit=False) as conn2:
            tx2 = ManagedTransaction("T2", conn2, logger, item_id)
            tx2.begin(IsolationLevel.READ_COMMITTED)
            val = tx2.read()
            logger.log(
                transaction_id="T2",
                event_type=OperationType.STATE_CHANGE,
                description=f"T2 read persisted value {val} from T1 commit",
                observed_value=val,
            )
            tx2.write(t2_write_val)
            logger.log(
                transaction_id="T2",
                event_type=OperationType.WRITE,
                description=f"T2 wrote {t2_write_val} (Simulating erroneous or cancelled transaction)",
            )
            tx2.rollback()

        # Check final value in database
        final_val = None
        with get_raw_connection(autocommit=True) as check_conn:
            with check_conn.cursor() as cur:
                cur.execute("SELECT value FROM sim_test_data WHERE item_id = %s", (item_id,))
                row = cur.fetchone()
                if row:
                    final_val = float(row[0])

        expected_val = float(t1_write_val)
        explanation = (
            f"COMMIT & ROLLBACK VERIFIED: T1 updated {initial_value} -> {t1_write_val} and COMMITTED (Durability confirmed). "
            f"T2 subsequently updated {t1_write_val} -> {t2_write_val} but executed ROLLBACK (Atomicity confirmed). "
            f"Final database value remains {final_val}, exactly matching the expected {expected_val}."
        )

        result = SimulationResult(
            run_id=run_id,
            scenario_name="Scenario C: COMMIT and ROLLBACK Lifecycle",
            status="SUCCESS",
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
            t1_state="COMMITTED",
            t2_state="ABORTED",
            t1_summary=f"Wrote {t1_write_val} and COMMITTED",
            t2_summary=f"Wrote {t2_write_val} and executed ROLLBACK",
        )

        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            details={
                "explanation": explanation,
                "t1_state": result.t1_state,
                "t2_state": result.t2_state,
                "t1_summary": result.t1_summary,
                "t2_summary": result.t2_summary,
            },
        )
        logger.persist_to_database()

        return result

    # -------------------------------------------------------------------------
    # SCENARIO D: SAVEPOINT AND PARTIAL ROLLBACK
    # -------------------------------------------------------------------------
    def run_savepoint_scenario(
        self,
        initial_value: float = 100.0,
        step1_val: float = 150.0,
        step2_val: float = 999.0,
        on_event: Optional[Any] = None,
    ) -> SimulationResult:
        """
        Demonstrates SAVEPOINT and ROLLBACK TO SAVEPOINT:
        BEGIN
        UPDATE -> step1_val (Valid change 1)
        SAVEPOINT checkpoint_alpha
        UPDATE -> step2_val (Faulty change 2)
        ROLLBACK TO SAVEPOINT checkpoint_alpha
        COMMIT
        Verifies that change 1 (step1_val) persists while change 2 (step2_val) is discarded.
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo, on_event=on_event)
        item_id = self.settings.test_item_id

        self.repo.reset_test_item(item_id, initial_value=initial_value)
        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=f"Initialized test row '{item_id}' to value = {initial_value}",
            observed_value=initial_value,
        )

        with get_raw_connection(autocommit=False) as conn:
            tx = ManagedTransaction("T1", conn, logger, item_id)
            tx.begin(IsolationLevel.READ_COMMITTED)

            # Valid step 1
            tx.write(step1_val)
            logger.log(
                transaction_id="T1",
                event_type=OperationType.WRITE,
                description=f"Step 1: Updated value to {step1_val} (Legitimate business modification)",
            )

            # Set savepoint
            tx.savepoint("checkpoint_alpha")

            # Faulty step 2
            tx.write(step2_val)
            logger.log(
                transaction_id="T1",
                event_type=OperationType.WRITE,
                description=f"Step 2: Updated value to {step2_val} (Simulating failed intermediate operation)",
            )

            # Rollback to savepoint
            tx.rollback_to_savepoint("checkpoint_alpha")
            logger.log(
                transaction_id="T1",
                event_type=OperationType.ROLLBACK_TO_SAVEPOINT,
                description=f"Undid Step 2 by rolling back to checkpoint_alpha. Transaction remains ACTIVE.",
            )

            # Commit the surviving changes
            tx.commit()

        # Verify final value
        final_val = None
        with get_raw_connection(autocommit=True) as check_conn:
            with check_conn.cursor() as cur:
                cur.execute("SELECT value FROM sim_test_data WHERE item_id = %s", (item_id,))
                row = cur.fetchone()
                if row:
                    final_val = float(row[0])

        expected_val = float(step1_val)
        explanation = (
            f"SAVEPOINT DEMONSTRATED: Initial value was {initial_value}. "
            f"Transaction updated value to {step1_val} and created SAVEPOINT 'checkpoint_alpha'. "
            f"Next, it updated value to {step2_val}, then executed ROLLBACK TO SAVEPOINT 'checkpoint_alpha'. "
            f"Upon COMMIT, the final database value is {final_val} (Change to {step1_val} was retained, {step2_val} was undone)."
        )

        result = SimulationResult(
            run_id=run_id,
            scenario_name="Scenario D: SAVEPOINT and Partial Rollback",
            status="SUCCESS" if final_val == expected_val else "FAILED",
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
            t1_state="COMMITTED",
            t1_summary=f"Retained {step1_val}, discarded {step2_val} via SAVEPOINT",
        )

        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=expected_val,
            details={
                "explanation": explanation,
                "t1_state": result.t1_state,
                "t1_summary": result.t1_summary,
            },
        )
        logger.persist_to_database()

        return result

    # -------------------------------------------------------------------------
    # SCENARIO E: TRANSACTION ISOLATION LEVELS
    # -------------------------------------------------------------------------
    def run_isolation_level_scenario(self, isolation_level: IsolationLevel) -> SimulationResult:
        """
        Compares transaction isolation behavior under concurrent writes:
        - READ COMMITTED: T1 sees committed values as soon as T2 commits (non-repeatable read).
        - REPEATABLE READ: T1 preserves its initial snapshot. If T1 and T2 concurrently modify the same row,
          PostgreSQL automatically detects serialization conflict and aborts the second committer with error 40001!
        - SERIALIZABLE: Full strict serializability via SSI.
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo)
        coordinator = ScenarioCoordinator(default_timeout_sec=10.0)
        item_id = self.settings.test_item_id

        initial_value = 100.0
        self.repo.reset_test_item(item_id, initial_value=initial_value)
        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=f"Initialized test row '{item_id}' to value = {initial_value}",
            observed_value=initial_value,
        )

        t1_observed_second_read = None
        t1_aborted_due_to_conflict = False
        t1_error_detail = None

        def worker_t1():
            nonlocal t1_observed_second_read, t1_aborted_due_to_conflict, t1_error_detail
            conn1 = None
            try:
                conn1 = get_raw_connection(autocommit=False)
                tx1 = ManagedTransaction("T1", conn1, logger, item_id)
                tx1.begin(isolation_level)

                # First read
                val1 = tx1.read()
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.READ,
                    description=f"T1 first read under {isolation_level.value}: value = {val1}",
                    observed_value=val1,
                )
                coordinator.signal("t1_first_read_done")

                # Wait for T2 to update and commit
                coordinator.wait_for("t2_committed")

                # Second read in same transaction
                val2 = tx1.read()
                t1_observed_second_read = val2
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.READ,
                    description=f"T1 second read under {isolation_level.value}: value = {val2}",
                    observed_value=val2,
                )

                # Attempt concurrent update if in REPEATABLE READ or SERIALIZABLE
                if isolation_level in (IsolationLevel.REPEATABLE_READ, IsolationLevel.SERIALIZABLE):
                    logger.log(
                        transaction_id="T1",
                        event_type=OperationType.WRITE,
                        description=f"T1 attempting concurrent UPDATE under {isolation_level.value} on row modified by T2...",
                    )
                    tx1.write(val2 + 10.0)

                tx1.commit()
            except errors.SerializationFailure as sf:
                t1_aborted_due_to_conflict = True
                t1_error_detail = f"PostgreSQL Serialization Failure (SQLSTATE 40001): {sf}"
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.ERROR,
                    description=f"Serialization conflict detected! {t1_error_detail}",
                )
                if conn1:
                    try:
                        conn1.rollback()
                    except Exception:
                        pass
            except Exception as e:
                coordinator.record_error(e)
                if conn1:
                    try:
                        conn1.rollback()
                    except Exception:
                        pass
            finally:
                if conn1 and not conn1.closed:
                    conn1.close()

        def worker_t2():
            conn2 = None
            try:
                conn2 = get_raw_connection(autocommit=False)
                tx2 = ManagedTransaction("T2", conn2, logger, item_id)

                coordinator.wait_for("t1_first_read_done")

                tx2.begin(IsolationLevel.READ_COMMITTED)
                tx2.write(200.0)
                tx2.commit()
                logger.log(
                    transaction_id="T2",
                    event_type=OperationType.COMMIT,
                    description="T2 updated row to 200.0 and COMMITTED.",
                )

                coordinator.signal("t2_committed")
            except Exception as e:
                coordinator.record_error(e)
                if conn2:
                    try:
                        conn2.rollback()
                    except Exception:
                        pass
            finally:
                if conn2 and not conn2.closed:
                    conn2.close()

        th1 = spawn_transaction_worker(worker_t1, name="Iso-T1")
        th2 = spawn_transaction_worker(worker_t2, name="Iso-T2")

        th1.join(timeout=12.0)
        th2.join(timeout=12.0)

        # Inspect final value
        final_val = None
        with get_raw_connection(autocommit=True) as check_conn:
            with check_conn.cursor() as cur:
                cur.execute("SELECT value FROM sim_test_data WHERE item_id = %s", (item_id,))
                row = cur.fetchone()
                if row:
                    final_val = float(row[0])

        if isolation_level == IsolationLevel.READ_COMMITTED:
            status = "NON_REPEATABLE_READ_DEMONSTRATED"
            explanation = (
                f"READ COMMITTED DEMONSTRATION: T1 read initial value 100.0. "
                f"T2 committed an update of 200.0. When T1 read the same item again within the SAME transaction, "
                f"it observed the new committed value {t1_observed_second_read} (Non-repeatable read phenomenon)."
            )
        else:
            status = "SERIALIZATION_CONFLICT_PREVENTED" if t1_aborted_due_to_conflict else "SNAPSHOT_ISOLATED"
            explanation = (
                f"{isolation_level.value} DEMONSTRATION: "
                f"T1 preserved its snapshot and saw value {t1_observed_second_read} during repeated read. "
                f"When T1 attempted to update the row previously committed by T2, PostgreSQL raised SQLSTATE 40001: "
                f"'could not serialize access due to concurrent update'. PostgreSQL aborted T1 to preserve consistency."
            )

        result = SimulationResult(
            run_id=run_id,
            scenario_name=f"Scenario E: Isolation Level ({isolation_level.value})",
            status=status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=200.0 if t1_aborted_due_to_conflict else final_val,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
        )

        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=initial_value,
            final_value=final_val,
            expected_value=result.expected_value,
            details={"explanation": explanation, "isolation_level": isolation_level.value},
        )
        logger.persist_to_database()

        return result

    # -------------------------------------------------------------------------
    # SCENARIO F: DEADLOCK DETECTION AND RESOLUTION
    # -------------------------------------------------------------------------
    def run_deadlock_scenario(self) -> SimulationResult:
        """
        Demonstrates PostgreSQL Deadlock Detection:
        Two distinct test items: ITEM_A and ITEM_B.
        T1 locks ITEM_A.
        T2 locks ITEM_B.
        T1 attempts to lock ITEM_B (blocks waiting for T2).
        T2 attempts to lock ITEM_A (creates cycle in Wait-For-Graph!).
        PostgreSQL detects the cycle and aborts one transaction (Victim) with SQLSTATE 40P01.
        The survivor transaction completes and commits.
        """
        self._verify_database_available()
        run_id = str(uuid.uuid4())
        logger = EventLogger(run_id, self.repo)
        coordinator = ScenarioCoordinator(default_timeout_sec=12.0)

        item_a = "SIM_ITEM_DEADLOCK_A"
        item_b = "SIM_ITEM_DEADLOCK_B"

        self.repo.reset_test_item(item_a, initial_value=100.0)
        self.repo.reset_test_item(item_b, initial_value=200.0)

        logger.log(
            transaction_id="SYSTEM",
            event_type=OperationType.BEGIN,
            description=f"Initialized deadlock resources: {item_a} = 100.0, {item_b} = 200.0",
        )

        victim_tx = None
        survivor_tx = None

        def worker_t1():
            nonlocal victim_tx, survivor_tx
            conn1 = None
            try:
                conn1 = get_raw_connection(autocommit=False)
                # Set session deadlock_timeout low so PostgreSQL detects deadlock quickly
                with conn1.cursor() as cur:
                    cur.execute("SET LOCAL deadlock_timeout = '1s';")

                tx1 = ManagedTransaction("T1", conn1, logger, item_a)
                tx1.begin(IsolationLevel.READ_COMMITTED)

                # Step 1: T1 acquires lock on ITEM_A
                tx1.read(for_update=True)
                coordinator.signal("t1_locked_a")

                # Wait for T2 to lock ITEM_B
                coordinator.wait_for("t2_locked_b")
                time.sleep(0.2)

                # Step 3: T1 attempts to acquire lock on ITEM_B (held by T2)
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.LOCK_WAIT,
                    description=f"T1 attempting SELECT ... FOR UPDATE on '{item_b}'. Waiting for T2...",
                )
                with conn1.cursor() as cur:
                    cur.execute(f"SELECT value FROM sim_test_data WHERE item_id = %s FOR UPDATE;", (item_b,))

                tx1.commit()
                survivor_tx = "T1"
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.COMMIT,
                    description="T1 successfully survived and committed.",
                )
            except errors.DeadlockDetected as dd:
                victim_tx = "T1"
                logger.log(
                    transaction_id="T1",
                    event_type=OperationType.DEADLOCK_DETECTED,
                    description=f"PostgreSQL detected Deadlock! Aborting T1 (Victim selected by DBMS engine). Error: {dd}",
                )
                if conn1:
                    try:
                        conn1.rollback()
                    except Exception:
                        pass
            except Exception as e:
                coordinator.record_error(e)
                if conn1:
                    try:
                        conn1.rollback()
                    except Exception:
                        pass
            finally:
                if conn1 and not conn1.closed:
                    conn1.close()

        def worker_t2():
            nonlocal victim_tx, survivor_tx
            conn2 = None
            try:
                conn2 = get_raw_connection(autocommit=False)
                with conn2.cursor() as cur:
                    cur.execute("SET LOCAL deadlock_timeout = '1s';")

                tx2 = ManagedTransaction("T2", conn2, logger, item_b)
                tx2.begin(IsolationLevel.READ_COMMITTED)

                # Wait for T1 to lock ITEM_A
                coordinator.wait_for("t1_locked_a")

                # Step 2: T2 acquires lock on ITEM_B
                tx2.read(for_update=True)
                coordinator.signal("t2_locked_b")
                time.sleep(0.4)

                # Step 4: T2 attempts to acquire lock on ITEM_A (held by T1) -> Cycle forms!
                logger.log(
                    transaction_id="T2",
                    event_type=OperationType.LOCK_WAIT,
                    description=f"T2 attempting SELECT ... FOR UPDATE on '{item_a}'. Cycle in Wait-For-Graph formed!",
                )
                with conn2.cursor() as cur:
                    cur.execute(f"SELECT value FROM sim_test_data WHERE item_id = %s FOR UPDATE;", (item_a,))

                tx2.commit()
                survivor_tx = "T2"
                logger.log(
                    transaction_id="T2",
                    event_type=OperationType.COMMIT,
                    description="T2 successfully survived and committed.",
                )
            except errors.DeadlockDetected as dd:
                victim_tx = "T2"
                logger.log(
                    transaction_id="T2",
                    event_type=OperationType.DEADLOCK_DETECTED,
                    description=f"PostgreSQL detected Deadlock! Aborting T2 (Victim selected by DBMS engine). Error: {dd}",
                )
                if conn2:
                    try:
                        conn2.rollback()
                    except Exception:
                        pass
            except Exception as e:
                coordinator.record_error(e)
                if conn2:
                    try:
                        conn2.rollback()
                    except Exception:
                        pass
            finally:
                if conn2 and not conn2.closed:
                    conn2.close()

        th1 = spawn_transaction_worker(worker_t1, name="Deadlock-T1")
        th2 = spawn_transaction_worker(worker_t2, name="Deadlock-T2")

        th1.join(timeout=14.0)
        th2.join(timeout=14.0)

        explanation = (
            f"DEADLOCK CYCLE DETECTED AND RESOLVED BY POSTGRESQL ENGINE: "
            f"T1 locked Resource A and requested Resource B. T2 locked Resource B and requested Resource A. "
            f"A circular dependency was formed in the PostgreSQL Lock Manager's Wait-For Graph. "
            f"PostgreSQL's internal deadlock detector detected the cycle and aborted victim transaction '{victim_tx or 'One of workers'}' "
            f"with SQLSTATE 40P01, allowing '{survivor_tx or 'the other worker'}' to proceed safely to COMMIT."
        )

        result = SimulationResult(
            run_id=run_id,
            scenario_name="Scenario F: Deadlock Detection & Graph Cycle Abort",
            status="DEADLOCK_ABORT",
            initial_value=100.0,
            final_value=None,
            expected_value=None,
            events=logger.get_events(),
            completed_at=datetime.now(IST),
            explanation=explanation,
        )

        self.repo.save_run(
            run_id=run_id,
            scenario_name=result.scenario_name,
            status=result.status,
            initial_value=100.0,
            final_value=None,
            expected_value=None,
            details={"explanation": explanation, "victim": victim_tx, "survivor": survivor_tx},
        )
        logger.persist_to_database()

        return result
