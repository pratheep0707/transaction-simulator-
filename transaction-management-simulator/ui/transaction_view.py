"""
Transaction Lifecycle & ACID Properties Educational Explorer.
Provides interactive step-by-step transaction control and deep-dive documentation
into the 5 textbook transaction states and ACID principles.
"""

import pandas as pd
import streamlit as st

from config.settings import get_settings
from database.connection import get_raw_connection, test_connection
from engine.acid_scenarios import AcidScenarioRunner
from engine.event_logger import EventLogger
from engine.models import IST, IsolationLevel, OperationType, TransactionState
from ui.visualizations import render_state_machine_chart


def format_event_timestamp(ts) -> str:
    """Safely formats an event timestamp to Indian Standard Time (IST)."""
    if ts is None:
        return "-"
    if hasattr(ts, "astimezone"):
        return ts.astimezone(IST).strftime("%H:%M:%S.%f")[:-3]
    return str(ts)[:19]


def render_transaction_lifecycle_page():
    """Renders the transaction state machine and ACID properties explorer."""
    st.markdown("## Transaction Lifecycle & ACID Internals")
    st.markdown(
        """
        In database theory, a **transaction** is a logical unit of database processing that includes
        one or more database access operations. To preserve data integrity, transactions must satisfy the
        **ACID** properties and follow a strict finite-state machine lifecycle.
        """
    )

    tab_lifecycle, tab_acid = st.tabs([
        "Lifecycle State Machine",
        "ACID Properties",
    ])

    with tab_lifecycle:
        col1, col2 = st.columns([1, 1.2])

        with col1:
            st.markdown("### The 5 Formal Transaction States")
            st.markdown(
                """
                1. <span class="state-active">ACTIVE</span>: The transaction enters this state upon `BEGIN`. It remains active while reading and writing data items.
                2. <span class="state-partially">PARTIALLY COMMITTED</span>: Entered after the final statement has been executed. Updates are staged in buffer pools/WAL, but not yet guaranteed to be durable on non-volatile storage.
                3. <span class="state-committed">COMMITTED</span>: Entered after the `COMMIT` record is written to the Write-Ahead Log (WAL) and acknowledged. The transaction's effects are permanent.
                4. <span class="state-failed">FAILED</span>: Entered when normal execution cannot proceed due to hardware/software faults, constraint violations, lock timeouts, or deadlocks.
                5. <span class="state-aborted">ABORTED</span>: Entered after the transaction has been rolled back and the database restored to its pre-transaction state via WAL undo records.
                """,
                unsafe_allow_html=True,
            )

            st.info(
                "**Operation Executed vs Transaction Committed**: An `UPDATE` statement modifies rows in the "
                "transaction's private snapshot / working buffer. Until `COMMIT` executes, other transactions cannot "
                "see these changes (under READ COMMITTED), and a system crash or `ROLLBACK` will undo them completely."
            )

        with col2:
            st.plotly_chart(render_state_machine_chart(), use_container_width=True)

    with tab_acid:
        st.markdown("### DBMS ACID Guarantees Dashboard")
        st.markdown(
            "Explore each foundational ACID property through live, verifiable PostgreSQL transaction experiments."
        )

        is_connected, _, _ = test_connection()
        if not is_connected:
            st.warning("⚠️ Database connection is offline. Interactive ACID experiments require Supabase connectivity.")
            return

        # ---------------------------------------------------------------------
        # CARD 1: ATOMICITY (Interactive Experiment)
        # ---------------------------------------------------------------------
        st.markdown(
            """
            <div class="acid-card" style="border-left-color: #3b82f6;">
                <h4>A — Atomicity (All or Nothing)</h4>
                <p>
                    A transaction is an indivisible unit of work: either <b>all</b> of its modifications are committed to the database,
                    or <b>none</b> of them persist. If any operation fails or an error is injected mid-stream, 
                    the transaction rolls back and all uncommitted working memory buffers are discarded via PostgreSQL's WAL mechanism.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("🔬 Interactive Atomicity Experiment: Multi-Record Fund Transfer", expanded=True):
            st.markdown(
                "This experiment operates on two isolated simulator-owned records (**Record A** and **Record B**). "
                "Both updates belong to the **same single transaction**."
            )

            col_input1, col_input2, col_input3 = st.columns(3)
            with col_input1:
                atom_a_val = st.number_input("Record A Initial Value:", value=100.0, step=10.0, key="atom_a_input")
            with col_input2:
                atom_b_val = st.number_input("Record B Initial Value:", value=50.0, step=10.0, key="atom_b_input")
            with col_input3:
                atom_transfer = st.number_input("Transfer Amount (A → B):", value=20.0, step=5.0, key="atom_tf_input")

            atom_mode = st.radio(
                "Select Atomicity Execution Mode:",
                [
                    "Mode 1: Successful Transaction (Both updates succeed and COMMIT)",
                    "Mode 2: Controlled Failure (Injected error before Record B triggers ROLLBACK)",
                ],
                key="atom_mode_select",
            )
            mode_code = "SUCCESS" if "Mode 1" in atom_mode else "FAILURE"

            if st.button("⚡ Run Atomicity Experiment", type="primary", key="btn_run_atomicity"):
                runner = AcidScenarioRunner()
                status_placeholder = st.empty()
                table_placeholder = st.empty()

                live_events_buffer = []

                def _on_live_event(evt):
                    live_events_buffer.append(evt)
                    df_live = pd.DataFrame([
                        {
                            "Step": e.step_number,
                            "TX": e.transaction_id,
                            "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                            "Description": e.description,
                            "Value": e.observed_value if e.observed_value is not None else "-",
                        }
                        for e in live_events_buffer
                    ])
                    table_placeholder.dataframe(df_live, use_container_width=True, hide_index=True)

                with st.spinner("Executing real PostgreSQL transaction against Supabase..."):
                    result = runner.run_atomicity_experiment(
                        initial_a=float(atom_a_val),
                        initial_b=float(atom_b_val),
                        transfer_amount=float(atom_transfer),
                        mode=mode_code,
                        on_event=_on_live_event,
                    )

                # Summary Display
                status_color = "#2ecc71" if result.status == "PASS" else "#e74c3c"
                status_placeholder.markdown(
                    f"""
                    <div class="acid-status-card" style="border: 1px solid {status_color};">
                        <span class="acid-status-badge" style="background-color: {status_color};">
                            STATUS: {result.status}
                        </span>
                        <span class="acid-status-title">{result.scenario_name}</span>
                        <p class="acid-status-desc">{result.explanation}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Metrics Comparison
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    st.metric("Initial Record A", f"{atom_a_val:.2f}")
                    st.metric("Initial Record B", f"{atom_b_val:.2f}")
                with col_m2:
                    st.metric("T1 State", result.t1_state)
                    st.metric("Mode", mode_code)
                with col_m3:
                    st.metric("Expected Record A", f"{result.expected_value:.2f}")
                    exp_b = (atom_b_val + atom_transfer) if mode_code == "SUCCESS" else atom_b_val
                    st.metric("Expected Record B", f"{exp_b:.2f}")
                with col_m4:
                    st.metric("Actual Final A", f"{result.final_value:.2f}")
                    act_b = 0.0
                    if hasattr(result, "details") and result.details:
                        act_b = result.details.get("record_b_final", 0.0)
                    st.metric("Actual Final B", f"{act_b:.2f}")

                # Detailed Event Timeline
                st.markdown("##### 📜 Chronological Transaction Event Trace")
                df_final = pd.DataFrame([
                    {
                        "Step": e.step_number,
                        "Timestamp (IST)": format_event_timestamp(e.event_timestamp),
                        "Transaction": e.transaction_id,
                        "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                        "Description": e.description,
                        "Value": e.observed_value if e.observed_value is not None else "-",
                    }
                    for e in result.events
                ])
                st.dataframe(df_final, use_container_width=True, hide_index=True)

        # ---------------------------------------------------------------------
        # CARD 2: CONSISTENCY (Interactive Experiment)
        # ---------------------------------------------------------------------
        st.write("---")
        st.markdown(
            """
            <div class="acid-card" style="border-left-color: #10b981;">
                <h4>C — Consistency (Database Constraint Enforcement)</h4>
                <p>
                    Transactions must transition the database from one valid state to another, strictly satisfying all
                    declared integrity constraints (such as <code>CHECK (value &gt;= 0)</code>) and domain invariants.
                    If any statement attempts to insert or update data violating a database constraint, PostgreSQL immediately
                    raises an error (e.g., <code>SQLSTATE 23514: check_violation</code>). The transaction must be rolled back,
                    guaranteeing that invalid intermediate state is never persisted.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("🔬 Interactive Consistency Experiment: PostgreSQL CHECK Constraint (value >= 0)", expanded=True):
            st.markdown(
                "This experiment operates on a dedicated simulator table `sim_consistency_data` with an active "
                "PostgreSQL constraint: `CHECK (value >= 0)`. You can enter a valid or invalid proposed balance to test "
                "whether the DBMS successfully prevents illegal data corruption."
            )

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                const_init_val = st.number_input(
                    "Initial Record Value:",
                    value=100.0,
                    step=10.0,
                    key="const_init_input",
                )
            with col_c2:
                const_attempt_val = st.number_input(
                    "Proposed Value to Write (Negative triggers CHECK violation):",
                    value=-50.0,
                    step=10.0,
                    key="const_attempt_input",
                )

            st.caption(
                "💡 **Try this**: Enter `-50.0` to verify that PostgreSQL rejects negative balances and rolls back, "
                "or enter `150.0` to verify that valid constraint-satisfying updates commit successfully."
            )

            if st.button("⚡ Run Consistency Experiment", type="primary", key="btn_run_consistency"):
                runner = AcidScenarioRunner()
                status_placeholder = st.empty()
                table_placeholder = st.empty()
                live_events_buffer = []

                def _on_live_event_c(evt):
                    live_events_buffer.append(evt)
                    df_live = pd.DataFrame([
                        {
                            "Step": e.step_number,
                            "TX": e.transaction_id,
                            "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                            "Description": e.description,
                            "Value": e.observed_value if e.observed_value is not None else "-",
                        }
                        for e in live_events_buffer
                    ])
                    table_placeholder.dataframe(df_live, use_container_width=True, hide_index=True)

                with st.spinner("Executing transaction against PostgreSQL table with CHECK (value >= 0)..."):
                    result = runner.run_consistency_experiment(
                        initial_value=float(const_init_val),
                        attempted_value=float(const_attempt_val),
                        on_event=_on_live_event_c,
                    )

                status_color = "#2ecc71" if result.status == "PASS" else "#e74c3c"
                status_placeholder.markdown(
                    f"""
                    <div class="acid-status-card" style="border: 1px solid {status_color};">
                        <span class="acid-status-badge" style="background-color: {status_color};">
                            STATUS: {result.status}
                        </span>
                        <span class="acid-status-title">{result.scenario_name}</span>
                        <p class="acid-status-desc">{result.explanation}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                col_cm1, col_cm2, col_cm3, col_cm4 = st.columns(4)
                with col_cm1:
                    st.metric("Initial Database Value", f"{const_init_val:.2f}")
                    st.metric("Enforced Constraint", "CHECK (value >= 0)")
                with col_cm2:
                    st.metric("Attempted Value", f"{const_attempt_val:.2f}")
                    st.metric("Transaction State", result.t1_state)
                with col_cm3:
                    st.metric("Expected Persisted Value", f"{result.expected_value:.2f}")
                    mode_label = "Constraint Violation" if const_attempt_val < 0 else "Valid Transition"
                    st.metric("Scenario Case", mode_label)
                with col_cm4:
                    st.metric("Actual Persisted Value", f"{result.final_value:.2f}")
                    match_label = "Protected" if result.status == "PASS" else "Corrupted"
                    st.metric("Integrity Guard", match_label)

                if result.error_message:
                    st.warning(f"🛡️ **PostgreSQL Error Caught & Handled**: `{result.error_message}`")

                st.markdown("##### 📜 Chronological Transaction Event Trace")
                df_final = pd.DataFrame([
                    {
                        "Step": e.step_number,
                        "Timestamp (IST)": format_event_timestamp(e.event_timestamp),
                        "Transaction": e.transaction_id,
                        "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                        "Description": e.description,
                        "Value": e.observed_value if e.observed_value is not None else "-",
                    }
                    for e in result.events
                ])
                st.dataframe(df_final, use_container_width=True, hide_index=True)

        # ---------------------------------------------------------------------
        # CARD 3: ISOLATION (Interactive Experiment)
        # ---------------------------------------------------------------------
        st.write("---")
        st.markdown(
            """
            <div class="acid-card" style="border-left-color: #f59e0b;">
                <h4>I — Isolation (Concurrent Transaction Control)</h4>
                <p>
                    Concurrent transactions must execute independently without mutual interference.
                    When two transactions concurrently perform read-modify-write operations on the same data item,
                    they risk experiencing concurrency anomalies such as the <b>Lost Update Anomaly</b>.
                    PostgreSQL prevents this anomaly through pessimistic row locking (<code>SELECT ... FOR UPDATE</code>)
                    or serializable snapshot isolation.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("🔬 Interactive Isolation Experiment: Lost Update Anomaly vs 2PL Row Locking", expanded=True):
            st.markdown(
                "This experiment executes **two concurrent transactions (T1 and T2)** on separate database sessions "
                "targeting the shared record `SIM_ISOLATION_X`. Compare uncontrolled execution against pessimistic row-level locking."
            )

            col_i1, col_i2, col_i3 = st.columns(3)
            with col_i1:
                iso_init_val = st.number_input("Initial Shared Balance:", value=100.0, step=10.0, key="iso_init_input")
            with col_i2:
                iso_t1_val = st.number_input("T1 Deposit (+):", value=50.0, step=10.0, key="iso_t1_input")
            with col_i3:
                iso_t2_val = st.number_input("T2 Withdrawal (-):", value=20.0, step=10.0, key="iso_t2_input")

            iso_mode = st.radio(
                "Select Isolation Concurrency Control Mode:",
                [
                    "Mode A: Lost Update Anomaly (Uncontrolled concurrent read-modify-write without locks)",
                    "Mode B: Concurrency Control (Pessimistic Row Locking via SELECT ... FOR UPDATE)",
                ],
                key="iso_mode_select",
            )
            iso_mode_code = "LOST_UPDATE" if "Mode A" in iso_mode else "ROW_LOCKING"

            if st.button("⚡ Run Isolation Experiment", type="primary", key="btn_run_isolation"):
                runner = AcidScenarioRunner()
                status_placeholder = st.empty()
                table_placeholder = st.empty()
                live_events_buffer = []

                def _on_live_event_i(evt):
                    live_events_buffer.append(evt)
                    df_live = pd.DataFrame([
                        {
                            "Step": e.step_number,
                            "TX": e.transaction_id,
                            "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                            "Description": e.description,
                            "Value": e.observed_value if e.observed_value is not None else "-",
                        }
                        for e in live_events_buffer
                    ])
                    table_placeholder.dataframe(df_live, use_container_width=True, hide_index=True)

                with st.spinner("Spawning concurrent transaction threads against Supabase PostgreSQL..."):
                    result = runner.run_isolation_experiment(
                        initial_value=float(iso_init_val),
                        mode=iso_mode_code,
                        t1_amount=float(iso_t1_val),
                        t2_amount=float(iso_t2_val),
                        on_event=_on_live_event_i,
                    )

                status_color = "#2ecc71" if result.status == "PASS" else "#e74c3c"
                status_placeholder.markdown(
                    f"""
                    <div class="acid-status-card" style="border: 1px solid {status_color};">
                        <span class="acid-status-badge" style="background-color: {status_color};">
                            STATUS: {result.status}
                        </span>
                        <span class="acid-status-title">{result.scenario_name}</span>
                        <p class="acid-status-desc">{result.explanation}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                col_im1, col_im2, col_im3, col_im4 = st.columns(4)
                with col_im1:
                    st.metric("Initial Shared Balance", f"{iso_init_val:.2f}")
                    st.metric("T1 Op (+Deposit)", f"+{iso_t1_val:.2f}")
                with col_im2:
                    st.metric("T2 Op (-Withdrawal)", f"-{iso_t2_val:.2f}")
                    st.metric("Concurrency Control", "None (Blind Writes)" if iso_mode_code == "LOST_UPDATE" else "SELECT ... FOR UPDATE")
                with col_im3:
                    st.metric("Expected Persisted Value", f"{result.expected_value:.2f}")
                    correct_ser = iso_init_val + iso_t1_val - iso_t2_val
                    st.metric("Theoretical Serial Sum", f"{correct_ser:.2f}")
                with col_im4:
                    st.metric("Actual Final Value", f"{result.final_value:.2f}")
                    anomaly_status = "T2 Overwritten (Lost Update!)" if iso_mode_code == "LOST_UPDATE" else "Fully Serialized"
                    st.metric("Isolation Outcome", anomaly_status)

                st.markdown("##### 📜 Chronological Concurrent Event Trace (Interleaved Timeline)")
                df_final = pd.DataFrame([
                    {
                        "Step": e.step_number,
                        "Timestamp (IST)": format_event_timestamp(e.event_timestamp),
                        "Transaction": e.transaction_id,
                        "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                        "Description": e.description,
                        "Value": e.observed_value if e.observed_value is not None else "-",
                    }
                    for e in result.events
                ])
                st.dataframe(df_final, use_container_width=True, hide_index=True)

        # ---------------------------------------------------------------------
        # CARD 4: DURABILITY (Interactive Experiment)
        # ---------------------------------------------------------------------
        st.write("---")
        st.markdown(
            """
            <div class="acid-card" style="border-left-color: #8b5cf6;">
                <h4>D — Durability (Persistence of Committed Data)</h4>
                <p>
                    Once a transaction successfully commits, its effects are permanent and will not be lost,
                    even in the event of an abrupt connection teardown, server restart, or system failure.
                    PostgreSQL achieves this via synchronous flushes to the Write-Ahead Log (WAL) before acknowledging <code>COMMIT</code>.
                    This experiment commits an update on one connection, explicitly terminates that connection,
                    and verifies the committed change using a completely fresh, independent connection.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("🔬 Interactive Durability Experiment: Cross-Connection Persistence Verification", expanded=True):
            st.markdown(
                "This experiment operates on simulator record `SIM_DURABILITY_X`. A writer session updates and commits "
                "the value, abruptly closes its database connection, and a completely fresh reader connection is opened "
                "to verify that the committed state persisted to PostgreSQL storage."
            )

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                dur_init_val = st.number_input("Initial Balance / Value:", value=100.0, step=10.0, key="dur_init_input")
            with col_d2:
                dur_commit_val = st.number_input("New Committed Value to Write:", value=250.0, step=10.0, key="dur_commit_input")

            if st.button("⚡ Run Durability Experiment", type="primary", key="btn_run_durability"):
                runner = AcidScenarioRunner()
                status_placeholder = st.empty()
                table_placeholder = st.empty()
                live_events_buffer = []

                def _on_live_event_d(evt):
                    live_events_buffer.append(evt)
                    df_live = pd.DataFrame([
                        {
                            "Step": e.step_number,
                            "TX": e.transaction_id,
                            "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                            "Description": e.description,
                            "Value": e.observed_value if e.observed_value is not None else "-",
                        }
                        for e in live_events_buffer
                     ])
                    table_placeholder.dataframe(df_live, use_container_width=True, hide_index=True)

                with st.spinner("Writing on Connection 1, terminating session, and verifying via Connection 2..."):
                    result = runner.run_durability_experiment(
                        initial_value=float(dur_init_val),
                        commit_value=float(dur_commit_val),
                        on_event=_on_live_event_d,
                    )

                status_color = "#2ecc71" if result.status == "PASS" else "#e74c3c"
                status_placeholder.markdown(
                    f"""
                    <div class="acid-status-card" style="border: 1px solid {status_color};">
                        <span class="acid-status-badge" style="background-color: {status_color};">
                            STATUS: {result.status}
                        </span>
                        <span class="acid-status-title">{result.scenario_name}</span>
                        <p class="acid-status-desc">{result.explanation}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                col_dm1, col_dm2, col_dm3, col_dm4 = st.columns(4)
                with col_dm1:
                    st.metric("Initial Record Value", f"{dur_init_val:.2f}")
                    st.metric("Writer Transaction", "COMMITTED")
                with col_dm2:
                    st.metric("Connection 1 Status", "Terminated & Destroyed")
                    st.metric("Target Committed Value", f"{dur_commit_val:.2f}")
                with col_dm3:
                    st.metric("Expected Persisted Value", f"{result.expected_value:.2f}")
                    st.metric("Verification Connection", "Fresh Independent Session")
                with col_dm4:
                    st.metric("Connection 2 Verified Read", f"{result.final_value:.2f}")
                    dur_status = "Durable in WAL / Disk" if result.status == "PASS" else "Lost"
                    st.metric("Persistence Guarantee", dur_status)

                st.markdown("##### 📜 Chronological Transaction Event Trace")
                df_final = pd.DataFrame([
                    {
                        "Step": e.step_number,
                        "Timestamp (IST)": format_event_timestamp(e.event_timestamp),
                        "Transaction": e.transaction_id,
                        "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                        "Description": e.description,
                        "Value": e.observed_value if e.observed_value is not None else "-",
                    }
                    for e in result.events
                ])
                st.dataframe(df_final, use_container_width=True, hide_index=True)
