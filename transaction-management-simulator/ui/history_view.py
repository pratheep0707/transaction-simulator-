"""
Simulation History and Audit Log Viewer.
Inspects persisted runs in sim_runs and fine-grained event traces from sim_events.
"""

import pandas as pd
import streamlit as st

from database.connection import test_connection
from database.repository import SimulatorRepository
from ui.visualizations import render_timeline_chart


def render_history_page():
    """Renders execution history, runs, and audit logs."""
    st.markdown("## Simulation History & Audit Trail")
    st.markdown(
        """
        All experimental runs and their granular operation events are recorded into PostgreSQL tables
        `sim_runs` and `sim_events` for verifiable analysis.
        """
    )

    is_connected, msg, _ = test_connection()
    if not is_connected:
        st.warning(f"Database connection offline: {msg}. History is retrieved from PostgreSQL `sim_runs`.")
        return

    repo = SimulatorRepository()
    runs = repo.get_recent_runs(limit=25)

    if not runs:
        st.info("No simulation runs recorded yet. Execute a scenario from the 'Concurrency Scenarios' page to see records here.")
        return

    st.markdown(f"**Found {len(runs)} recorded simulation runs:**")

    df_runs = pd.DataFrame(runs)
    if "started_at" in df_runs.columns and not df_runs.empty:
        df_runs["started_at_ist"] = (
            pd.to_datetime(df_runs["started_at"])
            .dt.tz_convert("Asia/Kolkata")
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )
    else:
        df_runs["started_at_ist"] = df_runs.get("started_at", "")

    display_df = df_runs[[
        "run_id", "scenario_name", "status", "initial_value",
        "final_value", "expected_value", "started_at_ist"
    ]].copy()

    display_df.columns = [
        "Run ID", "Scenario", "Status", "Initial",
        "Final Value", "Expected Value", "Executed At (IST)"
    ]

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Detailed Run Inspector
    st.write("---")
    st.subheader("Deep-Dive Event Inspector")

    def _fmt_run_label(r):
        st_at = r.get("started_at")
        if st_at and hasattr(st_at, "astimezone"):
            from datetime import timezone, timedelta
            IST = timezone(timedelta(hours=5, minutes=30), name="IST")
            t_str = st_at.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
        else:
            t_str = str(st_at)[:19]
        return f"{r['scenario_name']} ({t_str} IST) - {r['run_id'][:8]}"

    run_options = {_fmt_run_label(r): r['run_id'] for r in runs}
    selected_label = st.selectbox("Select a Run to Inspect:", list(run_options.keys()))
    selected_run_id = run_options[selected_label]

    events = repo.get_run_events(selected_run_id)

    if events:
        st.markdown(f"**Chronological Event Trace ({len(events)} events):**")
        df_events = pd.DataFrame(events)

        # Plotly Timeline
        from engine.models import TransactionEvent, OperationType
        event_objs = [
            TransactionEvent(
                run_id=e["run_id"],
                transaction_id=e["transaction_id"],
                event_type=OperationType(e["event_type"]) if e["event_type"] in [o.value for o in OperationType] else e["event_type"],
                description=e["description"],
                observed_value=e["observed_value"],
                step_number=e.get("step_number", 0),
            )
            for e in events
        ]
        st.plotly_chart(render_timeline_chart(event_objs), use_container_width=True)

        df_events_display = df_events[[
            "step_number", "transaction_id", "event_type",
            "description", "observed_value", "event_timestamp"
        ]].copy()
        if "event_timestamp" in df_events_display.columns and not df_events_display.empty:
            df_events_display["event_timestamp"] = (
                pd.to_datetime(df_events_display["event_timestamp"])
                .dt.tz_convert("Asia/Kolkata")
                .dt.strftime("%Y-%m-%d %H:%M:%S")
            )
        df_events_display.columns = ["Step", "TX", "Operation", "Description", "Value", "Timestamp (IST)"]
        st.dataframe(
            df_events_display,
            use_container_width=True,
            hide_index=True,
        )

        csv = df_events.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Run Events CSV",
            data=csv,
            file_name=f"sim_events_{selected_run_id[:8]}.csv",
            mime="text/csv",
        )
    else:
        st.info("No detailed event items found for this run.")
