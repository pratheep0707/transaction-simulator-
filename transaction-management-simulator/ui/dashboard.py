"""
Overview Dashboard page.
Displays database connection telemetry, system metrics, scenario index, and recent runs.
"""

from datetime import datetime
import streamlit as st

from config.settings import get_settings
from database.connection import test_connection
from database.repository import SimulatorRepository
from engine.models import IST
from ui.visualizations import render_state_machine_chart


def render_dashboard_page():
    """Renders the central system status and scenario overview."""
    settings = get_settings()
    repo = SimulatorRepository()

    # Connection Diagnostic Check
    is_connected, conn_msg, server_info = test_connection()

    # Header Card
    st.markdown(
        """
        <div class="tech-header">
            <h1>Transaction Management & Concurrency Control Simulator</h1>
            <p>DBMS Engineering Project • Interactive Internal Transaction Engine • PostgreSQL ACID Verifier</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Top Status & Metadata Bar
    col1, col2, col3 = st.columns([1.5, 1, 1])

    with col1:
        if is_connected:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="label">Database Connection</div>
                    <div style="margin: 8px 0;">
                        <span class="badge-connected">● ONLINE (SUPABASE POSTGRESQL)</span>
                    </div>
                    <div class="subtext">Endpoint: {server_info.get('server_address', 'Cloud')} | Port: {server_info.get('port', '5432')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="metric-card">
                    <div class="label">Database Connection</div>
                    <div style="margin: 8px 0;">
                        <span class="badge-disconnected">● DISCONNECTED / NOT CONFIGURED</span>
                    </div>
                    <div class="subtext">Configure DATABASE_URL in .env to enable live operations</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="label">Active Schema</div>
                <div class="value">{settings.schema_name}</div>
                <div class="subtext">Prefix: sim_test_data, sim_runs</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        runs = repo.get_recent_runs(limit=10) if is_connected else []
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="label">Recorded Experiments</div>
                <div class="value">{len(runs)}</div>
                <div class="subtext">Persisted in sim_runs table</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not is_connected:
        st.warning(
            f"**Database Setup Required**: {conn_msg}\n\n"
            "To execute transactions against your real Supabase PostgreSQL instance, "
            "obtain your connection string from the **Supabase Dashboard → Project Settings → Database → Connection string (URI)**, "
            "and set `DATABASE_URL` in your `.env` file. See the **Architecture & Setup** tab for step-by-step instructions."
        )

    st.write("")

    # Two column layout for Scenarios and Lifecycle Diagram
    left_col, right_col = st.columns([1.2, 1])

    with left_col:
        st.subheader("Available DBMS Scenarios")
        st.markdown(
            """
            This engineering simulator models exact database internal operations.
            Each scenario uses **independent PostgreSQL worker connections** and explicit thread synchronization.
            """
        )

        scenarios = [
            {
                "title": "Scenario A: Lost Update Anomaly",
                "tag": "Concurrency Anomaly",
                "desc": "Interleaved T1 and T2 operations overwrite uncommitted changes without locking. Result deviates from serial execution.",
            },
            {
                "title": "Scenario B: Pessimistic Row Locking",
                "tag": "Lock-Based Control",
                "desc": "T1 uses SELECT ... FOR UPDATE. PostgreSQL suspends T2 until T1 commits. Guarantees mathematical correctness (130.0).",
            },
            {
                "title": "Scenario C: COMMIT vs ROLLBACK",
                "tag": "ACID Durability & Atomicity",
                "desc": "Proves durability of committed writes in WAL versus atomicity rollback of uncommitted changes.",
            },
            {
                "title": "Scenario D: SAVEPOINT Partial Rollback",
                "tag": "Nested Checkpoint",
                "desc": "Creates intermediate savepoints within an active transaction and performs partial rollback without aborting.",
            },
            {
                "title": "Scenario E: Isolation Levels Comparison",
                "tag": "ANSI / SQL-92 Invariants",
                "desc": "Compares READ COMMITTED vs REPEATABLE READ snapshot isolation and observes PostgreSQL serialization conflict 40001.",
            },
            {
                "title": "Scenario F: Deadlock Detection & Victim Abort",
                "tag": "Wait-For Graph Cycle",
                "desc": "Causes circular dependency on two rows. PostgreSQL's lock manager detects cycle (40P01) and aborts victim transaction.",
            },
        ]

        for s in scenarios:
            with st.container():
                st.markdown(
                    f"""
                    <div style="background:#111927; border:1px solid #1f2e46; border-radius:8px; padding:12px; margin-bottom:10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong style="color:#e2e8f0; font-size:14px;">{s['title']}</strong>
                            <span style="background:#1e293b; color:#38bdf8; padding:2px 8px; border-radius:4px; font-size:11px;">{s['tag']}</span>
                        </div>
                        <p style="color:#94a3b8; font-size:12px; margin:6px 0 0 0;">{s['desc']}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with right_col:
        st.subheader("Transaction State Machine")
        fig = render_state_machine_chart()
        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            """
            <div class="acid-card">
                <h4>Engine Operational Guarantee</h4>
                <p>
                    The simulator drives PostgreSQL connections directly.
                    When a scenario runs, operations are issued in real time to Supabase.
                    No synthetic timelines or mocked database responses are used.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Recent runs table if connected
    if is_connected and runs:
        st.write("---")
        st.subheader("Latest Recorded Simulation Runs")
        formatted = []
        for r in runs[:5]:
            st_at = r.get("started_at_ist") or r.get("started_at")
            if st_at:
                if hasattr(st_at, "astimezone"):
                    t_str = st_at.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    t_str = str(st_at)[:19]
            else:
                t_str = "-"
            formatted.append(
                {
                    "Run ID": r["run_id"][:8] + "...",
                    "Scenario": r["scenario_name"],
                    "Status": r["status"],
                    "Initial": r["initial_value"],
                    "Final Value": r["final_value"],
                    "Expected": r["expected_value"],
                    "Timestamp (IST)": t_str,
                }
            )
        st.dataframe(formatted, use_container_width=True, hide_index=True)
