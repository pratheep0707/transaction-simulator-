"""
Transaction Management and Concurrency Control Simulator.
Main Streamlit Application Entrypoint.
"""

import importlib
import sys
import streamlit as st

for _mod in [
    "database.repository",
    "engine.models",
    "engine.acid_scenarios",
    "ui.styling",
    "ui.dashboard",
    "ui.transaction_view",
    "ui.scenario_views",
    "ui.history_view",
    "ui.live_monitor_view",
    "ui.architecture_view",
]:
    if _mod in sys.modules:
        try:
            importlib.reload(sys.modules[_mod])
        except Exception:
            pass

from config.settings import get_settings
from database.connection import test_connection
from ui.styling import apply_custom_css
from ui.dashboard import render_dashboard_page
from ui.transaction_view import render_transaction_lifecycle_page
from ui.scenario_views import render_scenarios_page
from ui.history_view import render_history_page
from ui.live_monitor_view import render_live_monitor_page
from ui.architecture_view import render_architecture_page

# Configure Streamlit page
st.set_page_config(
    page_title="DBMS Transaction & Concurrency Simulator",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply high-contrast engineering dark styling
apply_custom_css()

# Sidebar Navigation and Diagnostics
settings = get_settings()
is_connected, status_msg, _ = test_connection()

with st.sidebar:
    st.markdown("### ⚡ DBMS Simulator")
    st.markdown("*Transaction & Concurrency Engine*")
    st.write("---")

    # Connection Status Chip
    if is_connected:
        st.markdown('<span class="badge-connected">● DATABASE ONLINE</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-disconnected">● DATABASE OFFLINE</span>', unsafe_allow_html=True)

    st.write("")
    nav_choice = st.radio(
        "Navigation Menu:",
        [
            "Overview Dashboard",
            "Transaction Lifecycle & ACID",
            "Concurrency Scenarios (A - F)",
            "Simulation History & Logs",
            "🔴 Live Backend Monitor",
            "Architecture & Setup Guide",
        ],
        index=0,
    )

    st.write("---")
    st.markdown("#### Engine Specifications")
    st.markdown(
        """
        - **Target DB:** Supabase PostgreSQL
        - **Driver:** psycopg 3 (Binary)
        - **Protocol:** TLS / SSL Required
        - **Isolation:** MVCC + 2PL Locks
        - **Realtime:** CDC WebSocket Enabled
        - **Tables:** `sim_test_data`, `sim_runs`, `sim_events`
        """
    )

    st.write("---")
    st.caption("College DBMS Engineering Project")

# Page Routing
if nav_choice == "Overview Dashboard":
    render_dashboard_page()
elif nav_choice == "Transaction Lifecycle & ACID":
    render_transaction_lifecycle_page()
elif nav_choice == "Concurrency Scenarios (A - F)":
    render_scenarios_page()
elif nav_choice == "Simulation History & Logs":
    render_history_page()
elif nav_choice == "🔴 Live Backend Monitor":
    render_live_monitor_page()
elif nav_choice == "Architecture & Setup Guide":
    render_architecture_page()
