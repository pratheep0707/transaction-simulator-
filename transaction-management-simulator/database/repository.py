"""
Database repository for simulator operations.
Ensures strict isolation: only touches tables prefixed with 'sim_'.
"""

from datetime import timezone, timedelta
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from config.settings import get_settings
from database.connection import get_connection, get_raw_connection

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


class SimulatorRepository:
    """Repository handling all simulator data access in PostgreSQL."""

    def __init__(self):
        self.settings = get_settings()

    def initialize_schema(self) -> None:
        """Applies schema.sql safely using CREATE TABLE IF NOT EXISTS."""
        schema_file = Path(__file__).resolve().parent / "schema.sql"
        if not schema_file.exists():
            raise FileNotFoundError("schema.sql not found.")

        sql_content = schema_file.read_text(encoding="utf-8")

        with get_connection(autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_content)

    def reset_test_item(self, item_id: Optional[str] = None, initial_value: float = 100.0) -> float:
        """
        Resets only the specific simulator test row before running a scenario.
        Idempotent and isolated.
        """
        target_id = item_id or self.settings.test_item_id
        with get_connection(autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sim_test_data (item_id, item_name, value, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (item_id) DO UPDATE
                    SET value = EXCLUDED.value,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (target_id, f"Resource {target_id}", Decimal(str(initial_value))),
                )
        return float(initial_value)

    def reset_consistency_item(self, item_id: str = "SIM_CONSISTENCY_X", initial_value: float = 100.0) -> float:
        """Resets the dedicated consistency test row constrained by CHECK (value >= 0)."""
        with get_connection(autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sim_consistency_data (item_id, item_name, value, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (item_id) DO UPDATE
                    SET value = EXCLUDED.value,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (item_id, f"Resource {item_id}", Decimal(str(initial_value))),
                )
        return float(initial_value)

    def get_consistency_item_value(self, conn: Connection, item_id: str = "SIM_CONSISTENCY_X") -> Optional[float]:
        """Reads value from sim_consistency_data using an active connection."""
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM sim_consistency_data WHERE item_id = %s", (item_id,))
            row = cur.fetchone()
            if row:
                return float(row[0])
            return None

    def get_test_item_value(
        self,
        conn: Connection,
        item_id: Optional[str] = None,
        for_update: bool = False,
        nowait: bool = False,
    ) -> Optional[float]:
        """
        Reads the item value using the provided active connection/transaction.
        Optionally acquires an exclusive row lock using FOR UPDATE.
        """
        target_id = item_id or self.settings.test_item_id
        sql = "SELECT value FROM sim_test_data WHERE item_id = %s"
        if for_update:
            sql += " FOR UPDATE"
            if nowait:
                sql += " NOWAIT"

        with conn.cursor() as cur:
            cur.execute(sql, (target_id,))
            row = cur.fetchone()
            if row:
                return float(row[0])
            return None

    def update_test_item_value(
        self,
        conn: Connection,
        item_id: Optional[str] = None,
        new_value: float = 0.0,
    ) -> None:
        """
        Updates the item value using the provided active transaction.
        Does NOT commit automatically; transaction boundaries remain with caller.
        """
        target_id = item_id or self.settings.test_item_id
        sql = """
            UPDATE sim_test_data
            SET value = %s, updated_at = CURRENT_TIMESTAMP
            WHERE item_id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (Decimal(str(new_value)), target_id))

    def save_run(
        self,
        run_id: str,
        scenario_name: str,
        status: str,
        initial_value: Optional[float],
        final_value: Optional[float],
        expected_value: Optional[float],
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Records metadata and outcomes of a simulation run in PostgreSQL."""
        try:
            with get_connection(autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO sim_runs (
                            run_id, scenario_name, started_at, completed_at,
                            status, initial_value, final_value, expected_value, details
                        ) VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
                        ON CONFLICT (run_id) DO UPDATE
                        SET completed_at = CURRENT_TIMESTAMP,
                            status = EXCLUDED.status,
                            final_value = EXCLUDED.final_value,
                            details = EXCLUDED.details;
                        """,
                        (
                            run_id,
                            scenario_name,
                            status,
                            Decimal(str(initial_value)) if initial_value is not None else None,
                            Decimal(str(final_value)) if final_value is not None else None,
                            Decimal(str(expected_value)) if expected_value is not None else None,
                            json.dumps(details or {}),
                        ),
                    )
        except Exception:
            # Safe ignore if DB is offline or logging fails
            pass

    def save_events(self, run_id: str, events: List[Dict[str, Any]]) -> None:
        """Persists granular timeline events for a simulation run."""
        if not events:
            return
        try:
            with get_connection(autocommit=True) as conn:
                with conn.cursor() as cur:
                    rows = [
                        (
                            e.get("event_id"),
                            run_id,
                            e.get("transaction_id"),
                            e.get("event_type"),
                            e.get("description"),
                            e.get("event_timestamp"),
                            Decimal(str(e["observed_value"])) if e.get("observed_value") is not None else None,
                            e.get("step_number", 0),
                        )
                        for e in events
                    ]
                    cur.executemany(
                        """
                        INSERT INTO sim_events (
                            event_id, run_id, transaction_id, event_type,
                            description, event_timestamp, observed_value, step_number
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (event_id) DO NOTHING;
                        """,
                        rows,
                    )
        except Exception:
            pass

    def get_recent_runs(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Retrieves recent simulation executions from PostgreSQL."""
        try:
            with get_connection(autocommit=True) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT run_id, scenario_name, started_at, completed_at,
                               status, initial_value, final_value, expected_value, details
                        FROM sim_runs
                        ORDER BY started_at DESC
                        LIMIT %s;
                        """,
                        (limit,),
                    )
                    rows = cur.fetchall()
                    # Convert Decimals to float for clean serialization
                    results = []
                    for r in rows:
                        d = dict(r)
                        for k in ["initial_value", "final_value", "expected_value"]:
                            if d[k] is not None:
                                d[k] = float(d[k])
                        if d.get("started_at") and hasattr(d["started_at"], "astimezone"):
                            d["started_at"] = d["started_at"].astimezone(IST)
                        if d.get("completed_at") and hasattr(d["completed_at"], "astimezone"):
                            d["completed_at"] = d["completed_at"].astimezone(IST)
                        results.append(d)
                    return results
        except Exception:
            return []

    def get_run_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Retrieves all chronologically ordered events for a given run."""
        try:
            with get_connection(autocommit=True) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT event_id, run_id, transaction_id, event_type,
                               description, event_timestamp, observed_value, step_number
                        FROM sim_events
                        WHERE run_id = %s
                        ORDER BY step_number ASC, event_timestamp ASC;
                        """,
                        (run_id,),
                    )
                    rows = cur.fetchall()
                    results = []
                    for r in rows:
                        d = dict(r)
                        if d["observed_value"] is not None:
                            d["observed_value"] = float(d["observed_value"])
                        if d.get("event_timestamp") and hasattr(d["event_timestamp"], "astimezone"):
                            d["event_timestamp"] = d["event_timestamp"].astimezone(IST)
                        results.append(d)
                    return results
        except Exception:
            return []

    def get_live_test_items(self) -> List[Dict[str, Any]]:
        """Retrieves current live state of test items from sim_test_data in PostgreSQL."""
        try:
            with get_connection(autocommit=True) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT item_id, item_name, value, updated_at
                        FROM sim_test_data
                        ORDER BY item_id ASC;
                        """
                    )
                    rows = cur.fetchall()
                    res = []
                    for r in rows:
                        d = dict(r)
                        d["value"] = float(d["value"])
                        if d.get("updated_at") and hasattr(d["updated_at"], "astimezone"):
                            d["updated_at"] = d["updated_at"].astimezone(IST)
                        res.append(d)
                    return res
        except Exception:
            return []

    def get_latest_live_events(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Retrieves most recent global events stream from PostgreSQL."""
        try:
            with get_connection(autocommit=True) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT event_id, run_id, transaction_id, event_type,
                               description, event_timestamp, observed_value, step_number
                        FROM sim_events
                        ORDER BY event_timestamp DESC, step_number DESC
                        LIMIT %s;
                        """,
                        (limit,),
                    )
                    rows = cur.fetchall()
                    res = []
                    for r in rows:
                        d = dict(r)
                        if d["observed_value"] is not None:
                            d["observed_value"] = float(d["observed_value"])
                        if d.get("event_timestamp") and hasattr(d["event_timestamp"], "astimezone"):
                            d["event_timestamp"] = d["event_timestamp"].astimezone(IST)
                        res.append(d)
                    return res
        except Exception:
            return []

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Queries pg_stat_activity for active PostgreSQL client connections and queries."""
        try:
            with get_connection(autocommit=True) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT pid, usename, client_addr, state, query,
                               backend_start, state_change
                        FROM pg_stat_activity
                        WHERE datname = 'postgres' AND usename = 'postgres'
                          AND pid <> pg_backend_pid()
                        ORDER BY state_change DESC
                        LIMIT 10;
                        """
                    )
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
        except Exception:
            return []

    def get_active_locks(self) -> List[Dict[str, Any]]:
        """Queries pg_locks for real-time active row or relation locks on simulator tables."""
        try:
            with get_connection(autocommit=True) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT l.locktype,
                               c.relname AS target_table,
                               l.mode,
                               l.granted,
                               l.pid,
                               a.state,
                               a.query
                        FROM pg_locks l
                        JOIN pg_class c ON l.relation = c.oid
                        JOIN pg_stat_activity a ON l.pid = a.pid
                        WHERE a.datname = 'postgres'
                          AND c.relname LIKE 'sim_%'
                        ORDER BY l.granted DESC, l.pid ASC;
                        """
                    )
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
        except Exception:
            return []
