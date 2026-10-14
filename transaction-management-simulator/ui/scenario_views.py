"""
Interactive Scenarios Execution Dashboard.
Hosts runners for Scenarios A through F with real-time Plotly charts,
live event streaming, custom user operation inputs, transaction state badges,
and value comparison diagnostics.
"""

from typing import Any
import streamlit as st

from database.connection import test_connection
from engine.models import IsolationLevel, TransactionEvent
from engine.scenarios import ScenarioRunner, apply_operation
from ui.visualizations import (
    render_deadlock_graph,
    render_timeline_chart,
    render_value_comparison_chart,
)


def render_scenarios_page():
    """Renders the scenario execution workbench."""
    st.markdown("## Interactive DBMS Concurrency Scenarios")
    st.markdown(
        """
        Execute real-time concurrency scenarios directly against **Supabase PostgreSQL**.
        Each test executes concurrently using independent database connections and synchronized threads.
        """
    )

    is_connected, msg, _ = test_connection()
    if not is_connected:
        st.warning(
            f"**Database Disconnected / Not Configured**: {msg}\n\n"
            "Live scenario runs require a working PostgreSQL connection string. "
            "Configure `DATABASE_URL` in `.env` to execute live database transactions."
        )

    tab_ab, tab_cd, tab_e, tab_f = st.tabs([
        "Scenarios A & B: Lost Update vs Locking",
        "Scenarios C & D: Commit, Rollback & Savepoint",
        "Scenario E: Isolation Levels",
        "Scenario F: Deadlock Detection",
    ])

    runner = ScenarioRunner()

    # -------------------------------------------------------------------------
    # TAB 1: SCENARIOS A & B
    # -------------------------------------------------------------------------
    with tab_ab:
        st.subheader("Concurrency Anomaly: Lost Update vs Pessimistic Row Locking")
        st.markdown(
            """
            Configure your custom initial value, transaction operations, and execution mode.
            The simulator uses **independent PostgreSQL connections** and controlled thread barriers
            to demonstrate whether updates are preserved or overwritten.
            """
        )

        # 1. User Input Controls
        st.markdown("#### 1. Simulation Parameters & Transaction Operations")
        cfg_col0, cfg_col1, cfg_col2 = st.columns([1, 1.2, 1.2])

        with cfg_col0:
            init_val = st.number_input(
                "Initial Value (X)",
                value=100.0,
                step=10.0,
                key="ab_init_val",
                help="Initial value seeded into the dedicated sim_test_data test row.",
            )

        with cfg_col1:
            st.markdown("**Transaction T1 Operation:**")
            t1_op_raw = st.selectbox(
                "T1 Op Type",
                ["ADD (+)", "SUBTRACT (-)", "SET (=)"],
                index=0,
                key="ab_t1_op",
            )
            t1_amount = st.number_input("T1 Amount", value=50.0, step=5.0, key="ab_t1_amt")
            t1_op = "ADD" if "+" in t1_op_raw else ("SUBTRACT" if "-" in t1_op_raw else "SET")

        with cfg_col2:
            st.markdown("**Transaction T2 Operation:**")
            t2_op_raw = st.selectbox(
                "T2 Op Type",
                ["SUBTRACT (-)", "ADD (+)", "SET (=)"],
                index=0,
                key="ab_t2_op",
            )
            t2_amount = st.number_input("T2 Amount", value=20.0, step=5.0, key="ab_t2_amt")
            t2_op = "SUBTRACT" if "-" in t2_op_raw else ("ADD" if "+" in t2_op_raw else "SET")

        # Expected formula calculation
        t1_preview = apply_operation(init_val, t1_op, t1_amount)
        expected_preview = apply_operation(t1_preview, t2_op, t2_amount)

        st.markdown(
            f"""
            <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:12px; margin:12px 0;">
                <span style="color:#94a3b8; font-size:12px;">MATHEMATICAL FORMULA (SERIALIZED EXPECTATION):</span><br/>
                <code style="color:#38bdf8; font-size:14px;">
                    Initial ({init_val:.1f}) → T1 [{t1_op} {t1_amount:.1f}] → ({t1_preview:.1f}) → T2 [{t2_op} {t2_amount:.1f}] → Expected Result = {expected_preview:.1f}
                </code>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### 2. Select Concurrency Mode & Execute")
        col_btn_a, col_btn_b = st.columns(2)

        # Helper callback for live streaming events into an st.status container
        def create_live_stream_handler(status_container):
            def handler(event: TransactionEvent):
                op_name = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
                status_container.write(
                    f"**Step {event.step_number}** `[{event.transaction_id}]` **{op_name}**: {event.description}"
                )
            return handler

        with col_btn_a:
            if st.button("RUN SCENARIO A: UNCONTROLLED LOST UPDATE", type="primary", use_container_width=True):
                if not is_connected:
                    st.error("Cannot run live scenario: Database connection not configured.")
                else:
                    status_box = st.status("Executing interleaved concurrent transactions in PostgreSQL...", expanded=True)
                    try:
                        result = runner.run_lost_update_scenario(
                            initial_value=init_val,
                            t1_op=t1_op,
                            t1_amount=t1_amount,
                            t2_op=t2_op,
                            t2_amount=t2_amount,
                            on_event=create_live_stream_handler(status_box),
                        )
                        status_box.update(label="Scenario A Finished: Lost update anomaly demonstrated!", state="complete", expanded=False)
                        st.session_state.result_a = result
                    except Exception as e:
                        status_box.update(label=f"Execution error: {e}", state="error")
                        st.error(f"Scenario failed: {e}")

        with col_btn_b:
            if st.button("RUN SCENARIO B: PESSIMISTIC LOCKING (FOR UPDATE)", type="secondary", use_container_width=True):
                if not is_connected:
                    st.error("Cannot run live scenario: Database connection not configured.")
                else:
                    status_box = st.status("Executing locking transactions with row-level locks...", expanded=True)
                    try:
                        result = runner.run_pessimistic_locking_scenario(
                            initial_value=init_val,
                            t1_op=t1_op,
                            t1_amount=t1_amount,
                            t2_op=t2_op,
                            t2_amount=t2_amount,
                            on_event=create_live_stream_handler(status_box),
                        )
                        status_box.update(label="Scenario B Finished: Correctness preserved via row locking!", state="complete", expanded=False)
                        st.session_state.result_b = result
                    except Exception as e:
                        status_box.update(label=f"Execution error: {e}", state="error")
                        st.error(f"Scenario failed: {e}")

        # ---------------------------------------------------------------------
        # Render Scenario A Results
        # ---------------------------------------------------------------------
        if "result_a" in st.session_state:
            res_a = st.session_state.result_a
            st.markdown("---")
            st.markdown("### Scenario A: Execution Results & Anomaly Breakdown")
            st.error(f"**Anomaly Outcome:** {res_a.explanation}")

            # 3 KPI Cards
            kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
            with kpi1:
                st.metric("Initial Value", f"{res_a.initial_value:.1f}")
            with kpi2:
                st.metric("Expected Value", f"{res_a.expected_value:.1f}")
            with kpi3:
                st.metric("Final DB Value", f"{res_a.final_value:.1f}", delta=f"{res_a.final_value - res_a.expected_value:+.1f}", delta_color="inverse")
            with kpi4:
                st.markdown(
                    f"""
                    <div style="background:#111927; border:1px solid #1f2e46; border-radius:6px; padding:10px; text-align:center;">
                        <span style="color:#8da4c4; font-size:11px;">T1 STATE</span><br/>
                        <span class="badge-connected">● {res_a.t1_state or 'COMMITTED'}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with kpi5:
                st.markdown(
                    f"""
                    <div style="background:#111927; border:1px solid #1f2e46; border-radius:6px; padding:10px; text-align:center;">
                        <span style="color:#8da4c4; font-size:11px;">T2 STATE</span><br/>
                        <span class="badge-connected">● {res_a.t2_state or 'COMMITTED'}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            chart_col1, chart_col2 = st.columns([1, 1.2])
            with chart_col1:
                st.plotly_chart(
                    render_value_comparison_chart(
                        res_a.initial_value,
                        res_a.expected_value,
                        res_a.final_value,
                        title="Scenario A: Value Comparison",
                    ),
                    use_container_width=True,
                )
            with chart_col2:
                st.plotly_chart(render_timeline_chart(res_a.events), use_container_width=True)

            with st.expander("View Full Interleaved Event Log (Scenario A)"):
                st.dataframe(
                    [
                        {
                            "Step": e.step_number,
                            "Transaction": e.transaction_id,
                            "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                            "Description": e.description,
                            "Observed Value": e.observed_value,
                        }
                        for e in res_a.events
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

        # ---------------------------------------------------------------------
        # Render Scenario B Results
        # ---------------------------------------------------------------------
        if "result_b" in st.session_state:
            res_b = st.session_state.result_b
            st.markdown("---")
            st.markdown("### Scenario B: Execution Results & Locking Verification")
            st.success(f"**Correctness Outcome:** {res_b.explanation}")

            kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
            with kpi1:
                st.metric("Initial Value", f"{res_b.initial_value:.1f}")
            with kpi2:
                st.metric("Expected Value", f"{res_b.expected_value:.1f}")
            with kpi3:
                st.metric("Final DB Value", f"{res_b.final_value:.1f}", delta="Correct", delta_color="normal")
            with kpi4:
                st.markdown(
                    f"""
                    <div style="background:#111927; border:1px solid #1f2e46; border-radius:6px; padding:10px; text-align:center;">
                        <span style="color:#8da4c4; font-size:11px;">T1 STATE</span><br/>
                        <span class="badge-connected">● {res_b.t1_state or 'COMMITTED'}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with kpi5:
                st.markdown(
                    f"""
                    <div style="background:#111927; border:1px solid #1f2e46; border-radius:6px; padding:10px; text-align:center;">
                        <span style="color:#8da4c4; font-size:11px;">T2 STATE</span><br/>
                        <span class="badge-connected">● {res_b.t2_state or 'COMMITTED'}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            chart_col1, chart_col2 = st.columns([1, 1.2])
            with chart_col1:
                st.plotly_chart(
                    render_value_comparison_chart(
                        res_b.initial_value,
                        res_b.expected_value,
                        res_b.final_value,
                        title="Scenario B: Value Comparison",
                    ),
                    use_container_width=True,
                )
            with chart_col2:
                st.plotly_chart(render_timeline_chart(res_b.events), use_container_width=True)

            with st.expander("View Full Interleaved Event Log (Scenario B)"):
                st.dataframe(
                    [
                        {
                            "Step": e.step_number,
                            "Transaction": e.transaction_id,
                            "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                            "Description": e.description,
                            "Observed Value": e.observed_value,
                        }
                        for e in res_b.events
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

    # -------------------------------------------------------------------------
    # TAB 2: SCENARIOS C & D
    # -------------------------------------------------------------------------
    with tab_cd:
        st.subheader("Scenarios C & D: COMMIT, ROLLBACK and SAVEPOINT")
        col_c_box, col_d_box = st.columns(2)

        with col_c_box:
            st.markdown("#### Scenario C: COMMIT & ROLLBACK")
            c_init = st.number_input("Initial Value (C)", value=100.0, step=10.0, key="c_init")
            c_t1_val = st.number_input("T1 Committed Write", value=250.0, step=10.0, key="c_t1_val")
            c_t2_val = st.number_input("T2 Rolled-back Write", value=999.0, step=10.0, key="c_t2_val")

            if st.button("RUN SCENARIO C (COMMIT / ROLLBACK)", use_container_width=True):
                if not is_connected:
                    st.error("Database connection not configured.")
                else:
                    status_c = st.status("Executing COMMIT and ROLLBACK in PostgreSQL...", expanded=True)
                    try:
                        res_c = runner.run_commit_rollback_scenario(
                            initial_value=c_init,
                            t1_write_val=c_t1_val,
                            t2_write_val=c_t2_val,
                            on_event=create_live_stream_handler(status_c),
                        )
                        status_c.update(label="Scenario C Complete!", state="complete", expanded=False)
                        st.session_state.result_c = res_c
                    except Exception as e:
                        status_c.update(label=f"Error: {e}", state="error")
                        st.error(f"Error: {e}")

        with col_d_box:
            st.markdown("#### Scenario D: SAVEPOINT Partial Rollback")
            d_init = st.number_input("Initial Value (D)", value=100.0, step=10.0, key="d_init")
            d_step1 = st.number_input("Step 1 (Retained) Write", value=150.0, step=10.0, key="d_step1")
            d_step2 = st.number_input("Step 2 (Discarded via Savepoint) Write", value=999.0, step=10.0, key="d_step2")

            if st.button("RUN SCENARIO D (SAVEPOINT)", use_container_width=True):
                if not is_connected:
                    st.error("Database connection not configured.")
                else:
                    status_d = st.status("Executing SAVEPOINT operations in PostgreSQL...", expanded=True)
                    try:
                        res_d = runner.run_savepoint_scenario(
                            initial_value=d_init,
                            step1_val=d_step1,
                            step2_val=d_step2,
                            on_event=create_live_stream_handler(status_d),
                        )
                        status_d.update(label="Scenario D Complete!", state="complete", expanded=False)
                        st.session_state.result_d = res_d
                    except Exception as e:
                        status_d.update(label=f"Error: {e}", state="error")
                        st.error(f"Error: {e}")

        if "result_c" in st.session_state:
            rc = st.session_state.result_c
            st.markdown("---")
            st.markdown("### Scenario C Output & State Verification")
            st.info(rc.explanation)
            st.markdown(
                f"""
                **T1 State:** <span class="badge-connected">● {rc.t1_state}</span> &nbsp;&nbsp;|&nbsp;&nbsp;
                **T2 State:** <span class="badge-disconnected">● {rc.t2_state}</span>
                """,
                unsafe_allow_html=True,
            )
            st.plotly_chart(render_timeline_chart(rc.events), use_container_width=True)

        if "result_d" in st.session_state:
            rd = st.session_state.result_d
            st.markdown("---")
            st.markdown("### Scenario D Output & Savepoint Verification")
            st.info(rd.explanation)
            st.markdown(
                f"""
                **Transaction State:** <span class="badge-connected">● {rd.t1_state}</span> (Surviving modifications committed)
                """,
                unsafe_allow_html=True,
            )
            st.plotly_chart(render_timeline_chart(rd.events), use_container_width=True)

    # -------------------------------------------------------------------------
    # TAB 3: SCENARIO E
    # -------------------------------------------------------------------------
    with tab_e:
        st.subheader("Scenario E: PostgreSQL Isolation Levels")
        st.markdown(
            """
            PostgreSQL supports three distinct transaction isolation levels:
            - **READ COMMITTED** (Default): A statement sees only rows committed before it began. Repeated reads within the same transaction can observe concurrent commits (**Non-repeatable reads**).
            - **REPEATABLE READ**: A transaction sees a snapshot as of the transaction's start. Concurrent updates to the same row cause PostgreSQL to abort the second committer with **SQLSTATE 40001 (Serialization Failure)**!
            - **SERIALIZABLE**: Uses Serializable Snapshot Isolation (SSI). Tracks dependency graphs and aborts any transaction creating non-serializable interleavings.
            """
        )

        st.caption(
            "Note: PostgreSQL does not support distinct READ UNCOMMITTED behavior; "
            "it treats READ UNCOMMITTED as READ COMMITTED."
        )

        iso_choice = st.selectbox(
            "Select Isolation Level to Test:",
            [
                IsolationLevel.READ_COMMITTED.value,
                IsolationLevel.REPEATABLE_READ.value,
                IsolationLevel.SERIALIZABLE.value,
            ],
        )

        if st.button(f"RUN ISOLATION LEVEL EXPERIMENT ({iso_choice})", type="primary"):
            if not is_connected:
                st.error("Database connection not configured.")
            else:
                status_e = st.status(f"Testing concurrency under {iso_choice} in PostgreSQL...", expanded=True)
                try:
                    iso_enum = IsolationLevel(iso_choice)
                    res_e = runner.run_isolation_level_scenario(iso_enum)
                    status_e.update(label=f"Isolation experiment for {iso_choice} complete!", state="complete", expanded=False)
                    st.session_state.result_e = res_e
                except Exception as e:
                    status_e.update(label=f"Error: {e}", state="error")
                    st.error(f"Error executing isolation scenario: {e}")

        if "result_e" in st.session_state:
            re = st.session_state.result_e
            st.markdown("---")
            st.markdown("### Isolation Level Experiment Outcome")
            if "CONFLICT" in re.status:
                st.warning(f"**Outcome:** {re.explanation}")
            else:
                st.info(f"**Outcome:** {re.explanation}")
            st.plotly_chart(render_timeline_chart(re.events), use_container_width=True)

    # -------------------------------------------------------------------------
    # TAB 4: SCENARIO F
    # -------------------------------------------------------------------------
    with tab_f:
        st.subheader("Scenario F: Deadlock Detection & Cycle Resolution")
        st.markdown(
            """
            A **deadlock** occurs when two or more transactions have a mutual cyclic dependency on locks held by each other.
            Neither can proceed without the other releasing its lock.
            """
        )

        col_dead_info, col_dead_graph = st.columns([1, 1])

        with col_dead_info:
            st.markdown(
                """
                #### Execution Steps:
                1. **T1** acquires exclusive row lock on `Resource A`.
                2. **T2** acquires exclusive row lock on `Resource B`.
                3. **T1** attempts to acquire lock on `Resource B` (blocks waiting for T2).
                4. **T2** attempts to acquire lock on `Resource A` (blocks waiting for T1).
                5. **Wait-For Graph Cycle:** `T1 -> T2 -> T1`.
                6. **DBMS Engine Action:** PostgreSQL's deadlock detector identifies the cycle, selects a victim transaction, and aborts it with **SQLSTATE 40P01**.
                7. **Survivor:** The remaining transaction unblocks and completes its commit.
                """
            )

            if st.button("TRIGGER POSTGRESQL DEADLOCK", type="primary", use_container_width=True):
                if not is_connected:
                    st.error("Database connection not configured.")
                else:
                    status_f = st.status("Inducing deadlock cycle and awaiting PostgreSQL detector...", expanded=True)
                    try:
                        res_f = runner.run_deadlock_scenario()
                        status_f.update(label="Deadlock cycle detected and aborted by PostgreSQL!", state="complete", expanded=False)
                        st.session_state.result_f = res_f
                    except Exception as e:
                        status_f.update(label=f"Deadlock error: {e}", state="error")
                        st.error(f"Deadlock test error: {e}")

        with col_dead_graph:
            st.plotly_chart(render_deadlock_graph(), use_container_width=True)

        if "result_f" in st.session_state:
            rf = st.session_state.result_f
            st.markdown("---")
            st.markdown("### Deadlock Resolution Outcome")
            st.error(rf.explanation)
            st.plotly_chart(render_timeline_chart(rf.events), use_container_width=True)
