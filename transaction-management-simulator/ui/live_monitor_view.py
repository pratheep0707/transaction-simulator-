"""
Live Supabase Backend Monitor & Realtime Feed.
Continuously polls pg_stat_activity, pg_locks, and sim_events in PostgreSQL,
providing an auto-refreshing real-time telemetry stream without manual browser refreshes.
"""

import time
import pandas as pd
import streamlit as st

from database.connection import test_connection
from database.repository import SimulatorRepository


def render_live_monitor_page():
    """Renders real-time backend telemetry and live events feed."""
    st.markdown("## 🔴 Live Supabase Backend & Realtime Telemetry")
    st.markdown(
        """
        Monitor what PostgreSQL is doing in real time inside Supabase.
        Watch active client connections, row-level locks, and live table mutations
        **without manual browser refreshing**.
        """
    )

    is_connected, msg, server_info = test_connection()
    if not is_connected:
        st.error(f"Cannot connect to Supabase: {msg}")
        return

    repo = SimulatorRepository()

    # Top Control Bar: Auto-refresh switch & interval
    top_col1, top_col2, top_col3 = st.columns([1.5, 1, 1])

    with top_col1:
        auto_refresh = st.toggle("🟢 Auto-Refresh Feed (Live Watch Mode)", value=False, help="Automatically refreshes live telemetry every few seconds without clicking reload.")

    with top_col2:
        interval_sec = st.slider("Poll Interval (seconds)", min_value=1, max_value=5, value=2, disabled=not auto_refresh)

    with top_col3:
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.rerun()

    st.write("---")

    # 1. Live Test Data Item State
    st.subheader("1. Live Test Data Row (`sim_test_data`)")
    items = repo.get_live_test_items()
    if items:
        cols = st.columns(len(items))
        for idx, itm in enumerate(items):
            with cols[idx]:
                st.metric(
                    label=f"Resource {itm['item_id']}",
                    value=f"{itm['value']:.2f}",
                    help=f"Last updated: {itm['updated_at']}",
                )
                last_upd = itm.get("updated_at")
                if last_upd and hasattr(last_upd, "astimezone"):
                    from datetime import timezone, timedelta
                    IST = timezone(timedelta(hours=5, minutes=30), name="IST")
                    upd_str = last_upd.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")
                else:
                    upd_str = str(last_upd)[:19]
                st.caption(f"Last DB Update: `{upd_str}`")
    else:
        st.info("No test items found in `sim_test_data`.")

    # 2. Live Events Feed
    st.write("---")
    st.subheader("2. Streaming Events Feed (`sim_events`)")
    latest_events = repo.get_latest_live_events(limit=15)
    if latest_events:
        df_events = pd.DataFrame(latest_events)
        if "event_timestamp" in df_events.columns and not df_events.empty:
            df_events["event_timestamp"] = (
                pd.to_datetime(df_events["event_timestamp"])
                .dt.tz_convert("Asia/Kolkata")
                .dt.strftime("%Y-%m-%d %H:%M:%S")
            )
        df_display = df_events[[
            "step_number", "transaction_id", "event_type",
            "description", "observed_value", "event_timestamp"
        ]].copy()
        df_display.columns = ["Step", "TX", "Operation", "Description", "Value", "Timestamp (IST)"]
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("No events recorded yet. Run a scenario to see the event stream populate.")

    # 3. PostgreSQL Lock Manager (pg_locks) & Client Activity (pg_stat_activity)
    st.write("---")
    col_locks, col_sessions = st.columns(2)

    with col_locks:
        st.subheader("3. Live PostgreSQL Lock Manager (`pg_locks`)")
        locks = repo.get_active_locks()
        if locks:
            st.dataframe(pd.DataFrame(locks), use_container_width=True, hide_index=True)
        else:
            st.markdown(
                """
                <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:16px; text-align:center;">
                    <span style="color:#22c55e; font-weight:600;">● No Active Lock Contention</span><br/>
                    <span style="color:#94a3b8; font-size:12px;">Locks appear here during execution of Scenario B (SELECT ... FOR UPDATE) and Scenario F (Deadlock).</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_sessions:
        st.subheader("4. Client Backends (`pg_stat_activity`)")
        sessions = repo.get_active_sessions()
        if sessions:
            df_sess = pd.DataFrame(sessions)[["pid", "usename", "state", "query"]].copy()
            st.dataframe(df_sess, use_container_width=True, hide_index=True)
        else:
            st.info("No other concurrent client queries running.")

    # 5. Instructions for Supabase Realtime Inspector
    st.write("---")
    st.markdown(
        """
        <div style="background:#111927; border:1px solid #3b82f6; border-radius:8px; padding:16px;">
            <h4 style="color:#60a5fa; margin:0 0 8px 0;">📡 Supabase Realtime WebSocket Broadcast is ACTIVE</h4>
            <p style="color:#cbd5e1; font-size:13px; margin:0;">
                The tables <code>sim_test_data</code>, <code>sim_runs</code>, and <code>sim_events</code> are published to
                <code>supabase_realtime</code>. You can open your <b>Supabase Dashboard → Realtime → Inspector</b>,
                subscribe to <code>public:*</code>, and watch PostgreSQL CDC change events stream live over WebSockets without any page reload!
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Auto-refresh loop
    if auto_refresh:
        time.sleep(interval_sec)
        st.rerun()
