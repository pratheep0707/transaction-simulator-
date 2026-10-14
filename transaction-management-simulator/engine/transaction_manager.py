"""
Database Transaction Manager and State Machine Controller.
Directly coordinates PostgreSQL transactions through psycopg Connection objects,
strictly implementing DBMS textbook transaction states:
ACTIVE -> PARTIALLY_COMMITTED -> COMMITTED
ACTIVE / FAILED -> ABORTED
"""

from typing import List, Optional, Set
from psycopg import Connection, Error as PsycopgError

from engine.event_logger import EventLogger
from engine.models import IsolationLevel, OperationType, TransactionState


class ManagedTransaction:
    """
    Manages the lifecycle, operations, and state machine of a single database transaction.
    Interacts directly with a dedicated PostgreSQL connection.
    """

    def __init__(
        self,
        tx_id: str,
        connection: Connection,
        logger: EventLogger,
        item_id: str = "SIM_DATA_ITEM_ALPHA",
    ):
        self.tx_id = tx_id
        self.conn = connection
        self.logger = logger
        self.item_id = item_id
        self.state: Optional[TransactionState] = None
        self.savepoints: Set[str] = set()
        self.last_observed_value: Optional[float] = None
        self.history: List[str] = []

    def _transition_state(self, new_state: TransactionState, reason: str = "") -> None:
        """Records state transition and logs event."""
        old_state_str = self.state.value if self.state else "NONE"
        self.state = new_state
        desc = f"State transition: {old_state_str} -> {new_state.value}"
        if reason:
            desc += f" ({reason})"
        self.history.append(desc)
        self.logger.log(
            transaction_id=self.tx_id,
            event_type=OperationType.STATE_CHANGE,
            description=desc,
            observed_value=self.last_observed_value,
        )

    def begin(self, isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED) -> None:
        """
        Initiates a transaction block with the specified SQL isolation level.
        Transitions state to ACTIVE.
        """
        try:
            self.conn.autocommit = False
            with self.conn.cursor() as cur:
                cur.execute(f"BEGIN TRANSACTION ISOLATION LEVEL {isolation_level.value};")

            self._transition_state(
                TransactionState.ACTIVE,
                reason=f"Started transaction block with isolation level {isolation_level.value}",
            )
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.BEGIN,
                description=f"BEGIN executed with isolation level {isolation_level.value}",
            )
        except PsycopgError as e:
            self._transition_state(TransactionState.FAILED, reason=str(e))
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.ERROR,
                description=f"BEGIN failed: {e}",
            )
            raise

    def read(
        self,
        item_id: Optional[str] = None,
        for_update: bool = False,
        nowait: bool = False,
    ) -> Optional[float]:
        """
        Executes a SELECT query on the target test item.
        Optionally acquires an exclusive row-level lock using FOR UPDATE.
        """
        target_id = item_id or self.item_id
        if self.state != TransactionState.ACTIVE:
            raise RuntimeError(f"Cannot perform READ: Transaction is in {self.state} state.")

        query = f"SELECT value FROM sim_test_data WHERE item_id = %s"
        if for_update:
            query += " FOR UPDATE"
            if nowait:
                query += " NOWAIT"
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.LOCK_ACQUIRE,
                description=f"Attempting to acquire row-level lock via SELECT ... FOR UPDATE on item '{target_id}'",
            )

        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (target_id,))
                row = cur.fetchone()
                val = float(row[0]) if row else None
                self.last_observed_value = val

                lock_note = " (ROW LOCK ACQUIRED)" if for_update else ""
                self.logger.log(
                    transaction_id=self.tx_id,
                    event_type=OperationType.READ,
                    description=f"Read item '{target_id}' value = {val}{lock_note}",
                    observed_value=val,
                )
                return val
        except PsycopgError as e:
            self._transition_state(TransactionState.FAILED, reason=f"Read error: {e}")
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.ERROR,
                description=f"Read failed on item '{target_id}': {e}",
            )
            raise

    def write(self, new_value: float, item_id: Optional[str] = None) -> None:
        """
        Executes an UPDATE query on the target test item within the active transaction.
        Note: Changes are staged within transaction workspace and are NOT durable until COMMIT.
        """
        target_id = item_id or self.item_id
        if self.state != TransactionState.ACTIVE:
            raise RuntimeError(f"Cannot perform WRITE: Transaction is in {self.state} state.")

        query = """
            UPDATE sim_test_data
            SET value = %s, updated_at = CURRENT_TIMESTAMP
            WHERE item_id = %s;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (new_value, target_id))
                self.last_observed_value = new_value
                self.logger.log(
                    transaction_id=self.tx_id,
                    event_type=OperationType.WRITE,
                    description=(
                        f"Wrote value {new_value} to item '{target_id}' "
                        f"[Staged uncommitted change, visible to {self.tx_id}]"
                    ),
                    observed_value=new_value,
                )
        except PsycopgError as e:
            self._transition_state(TransactionState.FAILED, reason=f"Write error: {e}")
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.ERROR,
                description=f"Write failed on item '{self.item_id}': {e}",
            )
            raise

    def savepoint(self, savepoint_name: str) -> None:
        """Establishes an internal checkpoint to allow partial rollbacks."""
        if self.state != TransactionState.ACTIVE:
            raise RuntimeError(f"Cannot create SAVEPOINT: Transaction is in {self.state} state.")

        # Sanitize savepoint identifier
        clean_name = "".join(c for c in savepoint_name if c.isalnum() or c == "_")
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SAVEPOINT {clean_name};")
            self.savepoints.add(clean_name)
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.SAVEPOINT,
                description=f"Established SAVEPOINT '{clean_name}'. Transaction remains ACTIVE.",
                observed_value=self.last_observed_value,
            )
        except PsycopgError as e:
            self._transition_state(TransactionState.FAILED, reason=f"Savepoint error: {e}")
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.ERROR,
                description=f"Failed to create SAVEPOINT '{clean_name}': {e}",
            )
            raise

    def rollback_to_savepoint(self, savepoint_name: str) -> None:
        """
        Rolls back modifications made after the specified savepoint.
        Transaction remains in ACTIVE state.
        """
        if self.state not in (TransactionState.ACTIVE, TransactionState.FAILED):
            raise RuntimeError(f"Cannot rollback to savepoint: Transaction is in {self.state} state.")

        clean_name = "".join(c for c in savepoint_name if c.isalnum() or c == "_")
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"ROLLBACK TO SAVEPOINT {clean_name};")
            # If state was temporarily FAILED due to sub-operation, restore to ACTIVE
            self.state = TransactionState.ACTIVE
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.ROLLBACK_TO_SAVEPOINT,
                description=f"Rolled back to SAVEPOINT '{clean_name}'. Transaction remains ACTIVE.",
                observed_value=self.last_observed_value,
            )
        except PsycopgError as e:
            self._transition_state(TransactionState.FAILED, reason=f"Rollback to savepoint error: {e}")
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.ERROR,
                description=f"Failed to rollback to SAVEPOINT '{clean_name}': {e}",
            )
            raise

    def commit(self) -> None:
        """
        Finalizes all modifications.
        Transitions: ACTIVE -> PARTIALLY_COMMITTED -> COMMITTED.
        Releases all held row locks and makes changes permanently durable.
        """
        if self.state != TransactionState.ACTIVE:
            raise RuntimeError(f"Cannot COMMIT: Transaction is in {self.state} state.")

        # Textbook state step: PARTIALLY_COMMITTED
        self._transition_state(
            TransactionState.PARTIALLY_COMMITTED,
            reason="All operations finished. Executing commit record write to WAL.",
        )

        try:
            self.conn.commit()
            self._transition_state(
                TransactionState.COMMITTED,
                reason="Commit acknowledged by PostgreSQL engine. Updates are durable.",
            )
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.COMMIT,
                description="COMMIT succeeded. Row locks released. Updates permanently durable in database.",
                observed_value=self.last_observed_value,
            )
        except PsycopgError as e:
            self._transition_state(TransactionState.FAILED, reason=f"Commit failure: {e}")
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.ERROR,
                description=f"Commit failed: {e}",
            )
            # Automatic rollback on failed commit
            self.rollback()
            raise

    def rollback(self) -> None:
        """
        Discards all modifications.
        Transitions: ACTIVE / FAILED -> ABORTED.
        Releases all held row locks and restores database to pre-transaction state.
        """
        prior_state = self.state
        try:
            self.conn.rollback()
            self._transition_state(
                TransactionState.ABORTED,
                reason=f"Transaction rolled back from {prior_state.value if prior_state else 'ACTIVE'}. All staged changes discarded.",
            )
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.ROLLBACK,
                description="ROLLBACK executed. Staged updates discarded. Locks released.",
                observed_value=self.last_observed_value,
            )
        except PsycopgError as e:
            self.state = TransactionState.ABORTED
            self.logger.log(
                transaction_id=self.tx_id,
                event_type=OperationType.ERROR,
                description=f"Error executing rollback: {e}",
            )
