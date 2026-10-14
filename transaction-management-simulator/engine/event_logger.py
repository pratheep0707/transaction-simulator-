"""
Thread-safe event logger for transaction execution timelines.
Records all operations with precise monotonic sequencing and timestamps.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional
import pandas as pd

from database.repository import SimulatorRepository
from engine.models import IST, OperationType, TransactionEvent


class EventLogger:
    """Thread-safe collector for simulation and transaction events."""

    def __init__(
        self,
        run_id: str,
        repository: Optional[SimulatorRepository] = None,
        on_event: Optional[Any] = None,
    ):
        self.run_id = run_id
        self.repository = repository
        self.on_event = on_event
        self._events: List[TransactionEvent] = []
        self._lock = threading.Lock()
        self._step_counter = 0

    def log(
        self,
        transaction_id: str,
        event_type: OperationType,
        description: str,
        observed_value: Optional[float] = None,
    ) -> TransactionEvent:
        """Appends a new atomic event to the run log."""
        with self._lock:
            self._step_counter += 1
            evt = TransactionEvent(
                run_id=self.run_id,
                transaction_id=transaction_id,
                event_type=event_type,
                description=description,
                event_timestamp=datetime.now(IST),
                observed_value=observed_value,
                step_number=self._step_counter,
            )
            self._events.append(evt)

        if self.on_event:
            try:
                self.on_event(evt)
            except Exception:
                pass

        return evt

    def get_events(self) -> List[TransactionEvent]:
        """Returns a snapshot of logged events."""
        with self._lock:
            return list(self._events)

    def to_dataframe(self) -> pd.DataFrame:
        """Converts logged events to a clean Pandas DataFrame for UI presentation."""
        with self._lock:
            data = [
                {
                    "Step": e.step_number,
                    "Timestamp": e.event_timestamp.astimezone(IST).strftime("%H:%M:%S.%f")[:-3],
                    "Transaction": e.transaction_id,
                    "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                    "Description": e.description,
                    "Observed Value": e.observed_value if e.observed_value is not None else "-",
                }
                for e in self._events
            ]
        if not data:
            return pd.DataFrame(columns=["Step", "Timestamp", "Transaction", "Operation", "Description", "Observed Value"])
        return pd.DataFrame(data)

    def persist_to_database(self) -> None:
        """Flushes recorded events to PostgreSQL via repository."""
        if not self.repository:
            return
        with self._lock:
            serialized = [e.to_dict() for e in self._events]
        try:
            self.repository.save_events(self.run_id, serialized)
        except Exception:
            pass
