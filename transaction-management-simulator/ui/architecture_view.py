"""
Architecture & Supabase Setup Guide page.
Explains component architecture, connection pool topology, security safeguards,
and provides setup instructions for Supabase PostgreSQL.
"""

from pathlib import Path
import streamlit as st

from config.settings import get_settings
from database.connection import test_connection
from database.repository import SimulatorRepository


def render_architecture_page():
    """Renders technical architecture, setup walkthrough, and schema viewer."""
    settings = get_settings()
    repo = SimulatorRepository()

    st.markdown("## System Architecture & Supabase Configuration")
    st.markdown(
        """
        Understand the multi-tier engineering architecture of the simulator
        and how it orchestrates real PostgreSQL transactions under the hood.
        """
    )

    tab_arch, tab_setup, tab_schema = st.tabs([
        "System Architecture",
        "Supabase Configuration Guide",
        "SQL Schema & Verification",
    ])

    with tab_arch:
        st.markdown("### Multi-Tier Engineering Architecture")
        st.markdown(
            """
            ```
            ┌─────────────────────────────────────────────────────────────┐
            │                  STREAMLIT WEB DASHBOARD                    │
            │  - Overview Dashboard   - Lifecycle & Workbench             │
            │  - Scenarios Runner     - Plotly Timelines & State Graphs   │
            └──────────────────────────────┬──────────────────────────────┘
                                           │ Controls & Parameters
                                           ▼
            ┌─────────────────────────────────────────────────────────────┐
            │                 CONCURRENCY COORDINATOR                     │
            │  - Threading.Event & Barrier Synchronization                │
            │  - Monotonic Step Sequencing & Bounded Timeouts (10s)       │
            └──────────────┬──────────────────────────────┬───────────────┘
                           │ Worker Thread 1              │ Worker Thread 2
                           ▼                              ▼
            ┌──────────────────────────────┐ ┌────────────────────────────┐
            │     TRANSACTION T1 (WORKER)  │ │   TRANSACTION T2 (WORKER)  │
            │  - ManagedTransaction State  │ │ - ManagedTransaction State │
            │  - Dedicated TCP Connection  │ │ - Dedicated TCP Connection │
            └──────────────┬───────────────┘ └────────────┬───────────────┘
                           │ psycopg 3 (SSL)              │ psycopg 3 (SSL)
                           ▼                              ▼
            ┌─────────────────────────────────────────────────────────────┐
            │                   SUPABASE POSTGRESQL                       │
            │  - Row-Level Locking (SELECT ... FOR UPDATE)                │
            │  - MVCC (Multi-Version Concurrency Control)                 │
            │  - Lock Manager & Deadlock Detector (Wait-For Graph)        │
            │  - Write-Ahead Logging (WAL) for Atomicity & Durability     │
            │  - sim_test_data | sim_runs | sim_events                    │
            └─────────────────────────────────────────────────────────────┘
            ```
            """
        )

        st.markdown("#### Architectural Highlights:")
        st.markdown(
            """
            - **True Multi-Connection Concurrency:** Concurrency is never faked. Each concurrent transaction (`T1`, `T2`) establishes an independent TCP socket connection to PostgreSQL.
            - **Deterministic Interleaving:** Instead of fragile, non-deterministic `sleep()` calls, operations are orchestrated using `threading.Event` synchronization barriers with fail-safe timeouts.
            - **Strict Isolation:** The simulator only accesses its own dedicated tables (`sim_test_data`, `sim_runs`, `sim_events`). No user tables or system schemas are ever touched or modified.
            - **Security & Privacy:** Passwords and credentials are automatically redacted from all UI renders, logs, and tracebacks.
            """
        )

    with tab_setup:
        st.markdown("### Supabase PostgreSQL Setup Instructions")
        st.markdown(
            """
            Follow these steps to connect your existing Supabase project:
            """
        )

        st.markdown(
            """
            1. **Log in to Supabase**: Navigate to [https://supabase.com/dashboard](https://supabase.com/dashboard).
            2. **Open Your Project**: Click on your existing Supabase database project.
            3. **Retrieve Connection String**:
               - Click on **Project Settings** (the gear icon on the left navigation bar).
               - Select **Database** under Configuration.
               - Scroll down to the **Connection string** section.
               - Select the **URI** tab.
               - Ensure **Mode** is set to either *Session* (Port 5432) or *Transaction Pooler* (Port 6543).
            4. **Copy the Connection URI**:
               - It will look like:
                 `postgresql://postgres.[PROJECT_REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres`
                 or direct:
                 `postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres`
            5. **Set in `.env`**:
               - In the project root folder `D:\\transaction-management-simulator`, create or edit `.env`:
               ```env
               DATABASE_URL=postgresql://postgres:your_actual_password@db.your_project_ref.supabase.co:5432/postgres?sslmode=require
               ```
               *(Replace `your_actual_password` and `your_project_ref` with your real Supabase credentials)*.
            6. **Verify Connection**:
               - Click the **Test Database Connection** button below.
            """
        )

        st.write("---")
        st.markdown(f"**Current Configured URL (Masked):** `{settings.masked_database_url}`")

        if st.button("TEST DATABASE CONNECTION NOW", type="primary"):
            is_ok, msg, meta = test_connection()
            if is_ok:
                st.success(f"**Connection Succeeded!** {msg}")
                st.json(meta)
            else:
                st.error(f"**Connection Failed:** {msg}")

    with tab_schema:
        st.markdown("### Simulator Database Schema")
        st.markdown(
            """
            The schema below defines the simulator tables. All statements use `CREATE TABLE IF NOT EXISTS`
            to ensure complete safety and idempotency.
            """
        )

        schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        if schema_path.exists():
            sql_text = schema_path.read_text(encoding="utf-8")
            st.code(sql_text, language="sql")

            is_ok, _, _ = test_connection()
            if is_ok:
                if st.button("INITIALIZE / VERIFY SCHEMA IN SUPABASE", type="secondary"):
                    try:
                        repo.initialize_schema()
                        st.success("Schema verified and initialized successfully in Supabase PostgreSQL!")
                    except Exception as e:
                        st.error(f"Schema initialization error: {e}")
            else:
                st.info("Connect database to enable one-click schema initialization.")
