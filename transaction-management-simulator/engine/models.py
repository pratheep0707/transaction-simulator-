"""
Domain models for the Transaction Management Simulator.
Defines transaction states, isolation levels, operations, and structured event records.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


class TransactionState(str, Enum):
    """
    Standard DBMS Transaction Lifecycle States (Silberschatz / Garcia-Molina model):
    - ACTIVE: Initial state; remains active while executing operations.
    - PARTIALLY_COMMITTED: Final statement executed; awaiting durable storage.
    - COMMITTED: Transaction successfully executed; all updates durable.
    - FAILED: Normal execution interrupted (lock timeout, deadlock, error).
    - ABORTED: Transaction rolled back; database restored to prior state.
    """
    ACTIVE = "ACTIVE"
    PARTIALLY_COMMITTED = "PARTIALLY_COMMITTED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class IsolationLevel(str, Enum):
    """PostgreSQL supported Transaction Isolation Levels."""
    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"
    SERIALIZABLE = "SERIALIZABLE"


class OperationType(str, Enum):
    """Types of database operations tracked within a transaction."""
    BEGIN = "BEGIN"
    READ = "READ"
    WRITE = "WRITE"
    LOCK_ACQUIRE = "LOCK_ACQUIRE"
    LOCK_WAIT = "LOCK_WAIT"
    LOCK_RELEASED = "LOCK_RELEASED"
    SAVEPOINT = "SAVEPOINT"
    ROLLBACK_TO_SAVEPOINT = "ROLLBACK_TO_SAVEPOINT"
    COMMIT = "COMMIT"
    ROLLBACK = "ROLLBACK"
    STATE_CHANGE = "STATE_CHANGE"
    DEADLOCK_DETECTED = "DEADLOCK_DETECTED"
    ERROR = "ERROR"


@dataclass
class TransactionEvent:
    """Represents a single granular event in a simulation timeline."""
    run_id: str
    transaction_id: str
    event_type: OperationType
    description: str
    event_timestamp: datetime = field(default_factory=lambda: datetime.now(IST))
    observed_value: Optional[float] = None
    step_number: int = 0
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Serializes event to dictionary format."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "transaction_id": self.transaction_id,
            "event_type": self.event_type.value if isinstance(self.event_type, OperationType) else str(self.event_type),
            "description": self.description,
            "event_timestamp": self.event_timestamp.isoformat(),
            "observed_value": self.observed_value,
            "step_number": self.step_number,
        }


@dataclass
class SimulationResult:
    """Encapsulates the complete outcome of a simulation scenario run."""
    run_id: str
    scenario_name: str
    status: str  # "SUCCESS", "ANOMALY_DEMONSTRATED", "PREVENTED", "DEADLOCK_ABORT", "ERROR"
    initial_value: Optional[float]
    final_value: Optional[float]
    expected_value: Optional[float]
    events: List[TransactionEvent] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(IST))
    completed_at: Optional[datetime] = None
    explanation: str = ""
    error_message: Optional[str] = None
    is_live_database: bool = True
    t1_state: Optional[str] = None
    t2_state: Optional[str] = None
    t1_summary: str = ""
    t2_summary: str = ""
