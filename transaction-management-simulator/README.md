# Transaction Management and Concurrency Control Simulator

A comprehensive, interactive college DBMS engineering project demonstrating database transaction internals, ACID properties, transaction lifecycle state machines, concurrency anomalies, pessimistic locking, isolation levels, and deadlock detection using **Supabase PostgreSQL** and **Python (Streamlit + psycopg 3)**.

---

## 1. Abstract

Modern database management systems (DBMS) rely on rigorous transaction management and concurrency control protocols to ensure data integrity when multiple transactions execute concurrently. This engineering project is designed for computer science and database management systems (DBMS) coursework. It moves beyond abstract theory by executing real-time, multi-connection transactions against a live cloud PostgreSQL instance (Supabase). It directly illustrates the classic **Lost Update anomaly**, its mitigation through **Pessimistic Locking (`SELECT ... FOR UPDATE`)**, the mechanics of **COMMIT, ROLLBACK, and SAVEPOINT**, the behavioral distinctions among **ANSI Isolation Levels**, and engine-level **Deadlock Detection**.

---

## 2. Problem Statement

Many database concepts—such as interleaved execution schedules, non-repeatable reads, phantom anomalies, write skew, and deadlocks—are taught using abstract theoretical schedules. Students often lack hands-on experience observing how a real relational database engine (such as PostgreSQL) actually handles concurrent threads, acquires row-level locks, suspends waiting workers, generates serialization failures (SQLSTATE `40001`), and aborts deadlocked transactions (SQLSTATE `40P01`). This simulator bridges that gap by providing a visual, controlled, and verifiable laboratory for database transaction management.

---

## 3. Project Objectives

1. **Transaction Lifecycle Modeling:** Implement and visualize the textbook 5-state lifecycle model: `ACTIVE`, `PARTIALLY COMMITTED`, `COMMITTED`, `FAILED`, and `ABORTED`.
2. **ACID Properties Demonstration:** Provide verifiable proof of Atomicity (rollback), Consistency (constraints), Isolation (concurrency control), and Durability (WAL persistence).
3. **Deterministic Concurrency Control:** Coordinate multi-threaded transactions using thread synchronization primitives (`threading.Event`) rather than arbitrary sleeps.
4. **Anomaly Reproduction & Prevention:**
   - Reproduce the **Lost Update anomaly** deterministically.
   - Demonstrate how **Pessimistic Locking (`SELECT ... FOR UPDATE`)** serializes concurrent writes to preserve correctness.
5. **Partial Rollback Mechanics:** Demonstrate nested transaction checkpoints using `SAVEPOINT` and `ROLLBACK TO SAVEPOINT`.
6. **Isolation Level Comparison:** Contrast `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE` modes.
7. **Deadlock Detection:** Provoke a genuine circular dependency between transactions and capture PostgreSQL's engine-level cycle abort.
8. **Real Database Operations:** Connect directly to Supabase PostgreSQL via `psycopg 3` with SSL/TLS encryption.

---

## 4. Technology Stack

- **Language:** Python 3.11+
- **Database:** Supabase PostgreSQL 15+
- **Driver:** `psycopg` (psycopg 3 binary) with TLS/SSL enforcement
- **Frontend Dashboard:** Streamlit 1.35+
- **Visualizations:** Plotly (Gantt timelines, state transition graphs, value comparisons)
- **Data Manipulation:** Pandas
- **Configuration & Security:** `python-dotenv` with password masking
- **Testing:** Pytest

---

## 5. Software & Hardware Requirements

### Software:
- Operating System: Windows 10/11, macOS, or Linux
- Python 3.11, 3.12, or 3.13
- Internet connection (to connect to Supabase PostgreSQL over SSL)
- Existing Supabase project (free tier is fully supported)

### Hardware:
- Processor: Dual-core CPU or higher
- RAM: 4 GB minimum (8 GB recommended)
- Disk Space: ~200 MB for Python environment and dependencies

---

## 6. Project Architecture & Directory Structure

```
transaction-management-simulator/
│
├── app.py                      # Main Streamlit web application & routing
├── requirements.txt            # Python dependencies
├── .env.example                # Template for configuration & credentials
├── .env                        # Local database credentials (Git-ignored)
├── .gitignore                  # Git ignore rules protecting credentials
├── README.md                   # Complete academic documentation & guide
│
├── config/
│   ├── __init__.py
│   └── settings.py             # Settings loader, URL parsing & password masking
│
├── database/
│   ├── __init__.py
│   ├── connection.py           # psycopg 3 connection factory & SSL handling
│   ├── schema.sql              # Idempotent simulator schema definition
│   └── repository.py           # Safe data access layer for simulator tables
│
├── engine/
│   ├── __init__.py
│   ├── models.py               # Transaction states, isolation enums, event data
│   ├── transaction_manager.py  # Textbook state machine & transaction lifecycle
│   ├── concurrency.py          # Scenario coordinator & thread synchronization
│   ├── scenarios.py            # Implementation of Scenarios A through F
│   └── event_logger.py         # Thread-safe monotonic event tracing
│
├── ui/
│   ├── __init__.py
│   ├── styling.py              # Dark technical UI CSS & status badges
│   ├── dashboard.py            # Overview dashboard & system telemetry
│   ├── transaction_view.py     # State machine explorer & interactive workbench
│   ├── scenario_views.py       # Scenarios A-F runners with live Plotly charts
│   ├── history_view.py         # Persisted run history & event trace viewer
│   ├── architecture_view.py    # Architecture diagram & Supabase setup guide
│   └── visualizations.py       # Plotly charts (Gantt, bar comparisons, graphs)
│
├── diagrams/
│   └── architecture.md         # Mermaid sequence, state, and architecture diagrams
│
└── tests/
    ├── __init__.py
    ├── test_models_and_logger.py # Unit tests for models & event logging
    ├── test_transactions.py    # Unit tests for transaction state transitions
    └── test_scenarios.py       # Integration tests for concurrency scenarios
```

---

## 7. Database Design & Safe Isolation

The simulator strictly isolates all operations to three dedicated tables prefixed with `sim_`. It never drops, alters, or touches any other user or system tables.

### Table Definitions:

```sql
-- 1. Dedicated simulator test resource
CREATE TABLE IF NOT EXISTS sim_test_data (
    item_id VARCHAR(50) PRIMARY KEY,
    item_name VARCHAR(100) NOT NULL,
    value NUMERIC(14, 2) NOT NULL DEFAULT 100.00,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Execution run metadata and audit records
CREATE TABLE IF NOT EXISTS sim_runs (
    run_id VARCHAR(36) PRIMARY KEY,
    scenario_name VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL,
    initial_value NUMERIC(14, 2),
    final_value NUMERIC(14, 2),
    expected_value NUMERIC(14, 2),
    details JSONB DEFAULT '{}'::jsonb
);

-- 3. Fine-grained chronological event traces
CREATE TABLE IF NOT EXISTS sim_events (
    event_id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES sim_runs(run_id) ON DELETE CASCADE,
    transaction_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observed_value NUMERIC(14, 2),
    step_number INT DEFAULT 0
);
```

---

## 8. Theoretical DBMS Concepts & Principles

### A. The 5 Transaction States (Silberschatz Model)
1. **ACTIVE:** State immediately after `BEGIN`. Stays here while executing operations.
2. **PARTIALLY COMMITTED:** Reached after final statement executes; updates buffered in RAM/WAL.
3. **COMMITTED:** Reached after commit record is flushed to non-volatile WAL storage.
4. **FAILED:** Entered when an unrecoverable conflict, error, or lock timeout occurs.
5. **ABORTED:** Reached after `ROLLBACK` has undone staged changes, restoring the pre-transaction state.

### B. ACID Properties
- **Atomicity:** All operations complete, or all are rolled back. Guaranteed via PostgreSQL Write-Ahead Log (WAL).
- **Consistency:** Database transitions only between valid states satisfying all constraints.
- **Isolation:** Concurrent transactions execute without mutual interference. Achieved via MVCC and 2-Phase Locking.
- **Durability:** Committed changes persist across system restarts and crashes. Guaranteed via WAL fsync.

### C. Concurrency Anomalies
- **Lost Update:** Two transactions concurrently read item $X$, compute updates, and write back without locking. The second write completely overwrites the first.
- **Non-Repeatable Read:** A transaction reads $X$, another transaction commits an update to $X$, and the first transaction reads $X$ again, observing different values.
- **Deadlock:** Cyclic wait condition where $T_1$ holds lock on $A$ and waits for $B$, while $T_2$ holds lock on $B$ and waits for $A$.

---

## 9. Scenarios Implemented

| Scenario | Title | Description | Expected Final Value |
| :--- | :--- | :--- | :--- |
| **A** | **Lost Update Anomaly** | $T_1$ reads 100, computes +50. $T_2$ reads 100, computes -20, writes 80, commits. $T_1$ writes stale 150. | Actual: **150.0** (Loss: 20.0, Expected: 130.0) |
| **B** | **Pessimistic Locking** | $T_1$ locks row with `SELECT ... FOR UPDATE`. $T_2$ is blocked by PostgreSQL until $T_1$ commits. $T_2$ reads updated row. | Actual: **130.0** (Mathematically Correct) |
| **C** | **COMMIT & ROLLBACK** | $T_1$ writes 250 and commits (persisted). $T_2$ writes 999 and rolls back (undone). | Actual: **250.0** (Durability & Atomicity) |
| **D** | **SAVEPOINT** | $T_1$ writes 150, sets `SAVEPOINT`, writes 999, rolls back to savepoint, commits. | Actual: **150.0** (Partial Rollback) |
| **E** | **Isolation Levels** | Compares `READ COMMITTED` vs `REPEATABLE READ`. Triggers SQLSTATE `40001` serialization conflict. | Verified Engine Snapshots |
| **F** | **Deadlock Detection** | Creates circular lock wait between two items. PostgreSQL triggers SQLSTATE `40P01` deadlock abort on victim. | Victim Aborted, Survivor Committed |

---

## 10. Supabase Connection Configuration Guide

1. Log into your [Supabase Dashboard](https://supabase.com/dashboard).
2. Select your existing Supabase project.
3. Click **Project Settings** (gear icon) in the left sidebar.
4. Navigate to **Database** under Configuration.
5. Scroll down to **Connection string** and select the **URI** tab.
6. Copy the URI string. It will look like:
   ```
   postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
   ```
   *(Or direct: `postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require`)*
7. In the project directory `D:\transaction-management-simulator`, create a file named `.env`:
   ```env
   DATABASE_URL=postgresql://postgres:your_real_password@db.your_project_ref.supabase.co:5432/postgres?sslmode=require
   ```
8. The simulator automatically enforces `sslmode=require` and redacts credentials from all logs and screens.

---

## 11. Setup & Running Instructions (Windows)

Open PowerShell in `D:\transaction-management-simulator`:

```powershell
# 1. (Optional) Create virtual environment
python -m venv .venv

# 2. Activate virtual environment
.venv\Scripts\activate

# 3. Install dependencies
python -m pip install -r requirements.txt

# 4. Launch the Streamlit application
streamlit run app.py
```

The application will open in your default browser at `http://localhost:8501`.

---

## 12. Running Automated Tests

Run unit tests and scenario synchronization checks:

```powershell
# Run all unit and mock tests (runs with or without database connection)
pytest -v
```

If database credentials are configured in `.env`, the full integration suite will test live queries against Supabase.

---

## 13. Limitations & Disclaimers

- **Academic Simulator:** This project is designed for pedagogical demonstration of DBMS internal mechanics. It is not intended as a production business application.
- **PostgreSQL Read Uncommitted:** PostgreSQL treats `READ UNCOMMITTED` as `READ COMMITTED`. This behavior is explicitly noted and demonstrated in Scenario E.
- **Deadlock Timeout:** To make Scenario F interactively responsive, the transaction session sets `deadlock_timeout = '1s'`.

---

## 14. Future Enhancements

- **Optimistic Concurrency Control (OCC):** Add comparison with application-level version columns (`version` integer) and CAS (Compare-And-Swap) updates.
- **Two-Phase Commit (2PC):** Simulate distributed transactions across multiple independent PostgreSQL nodes.
- **Lock Granularity Explorer:** Visualize table-level vs page-level vs tuple-level locks in PostgreSQL system views (`pg_locks`).
