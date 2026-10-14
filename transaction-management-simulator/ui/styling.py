"""
Styling and modern dark technical theme for the Streamlit dashboard.
Provides clean typography, compact metrics, glowing status badges,
responsive tables, and restrained alerts.
"""

import streamlit as st


def apply_custom_css():
    """Injects high-contrast, modern engineering dark-mode CSS with balanced typography."""
    st.markdown(
        """
        <style>
        /* Base typography and background */
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 14px;
        }

        code, pre, .mono-text, .stCodeBlock {
            font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
        }

        /* =========================================================================
           1. TYPOGRAPHY HIERARCHY
           ========================================================================= */

        /* Main page title: 28–32px */
        h1, 
        [data-testid="stMarkdownContainer"] h1,
        .tech-header h1 {
            font-size: 28px !important;
            font-weight: 700 !important;
            line-height: 1.25 !important;
            letter-spacing: -0.02em !important;
            color: #f8fafc !important;
            margin-top: 0.2rem !important;
            margin-bottom: 0.6rem !important;
        }

        /* Section headings: 20–24px */
        h2, 
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stHeader"] {
            font-size: 22px !important;
            font-weight: 700 !important;
            line-height: 1.3 !important;
            letter-spacing: -0.01em !important;
            color: #e2e8f0 !important;
            margin-top: 1rem !important;
            margin-bottom: 0.5rem !important;
        }

        /* Experiment headings: 17–19px */
        h3, 
        [data-testid="stMarkdownContainer"] h3,
        [data-testid="stSubheader"] {
            font-size: 18px !important;
            font-weight: 600 !important;
            line-height: 1.35 !important;
            color: #cbd5e1 !important;
            margin-top: 0.8rem !important;
            margin-bottom: 0.4rem !important;
        }

        /* Subheadings: 15–16px */
        h4, 
        [data-testid="stMarkdownContainer"] h4,
        .acid-card h4 {
            font-size: 15px !important;
            font-weight: 600 !important;
            line-height: 1.4 !important;
            color: #94a3b8 !important;
            margin-top: 0.6rem !important;
            margin-bottom: 0.3rem !important;
        }

        /* Minor subheadings / labels: 14px */
        h5, 
        [data-testid="stMarkdownContainer"] h5 {
            font-size: 14px !important;
            font-weight: 600 !important;
            line-height: 1.4 !important;
            color: #94a3b8 !important;
            margin-top: 0.5rem !important;
            margin-bottom: 0.25rem !important;
        }

        /* Body text: 13–15px */
        p, 
        li, 
        [data-testid="stMarkdownContainer"] p, 
        [data-testid="stMarkdownContainer"] li,
        .stMarkdown {
            font-size: 14px !important;
            line-height: 1.55 !important;
            color: #cbd5e1 !important;
        }

        /* Captions and secondary information: 11–12px */
        small, 
        .stCaption, 
        [data-testid="stCaptionContainer"],
        .subtext {
            font-size: 12px !important;
            color: #64748b !important;
            line-height: 1.4 !important;
        }

        /* =========================================================================
           2. STREAMLIT METRICS: COMPACT VALUES (24-28px) & LABELS (12-14px)
           ========================================================================= */

        [data-testid="stMetric"] {
            background-color: #111927 !important;
            border: 1px solid #1f2e46 !important;
            border-radius: 8px !important;
            padding: 10px 14px !important;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2) !important;
            min-height: 74px !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
        }

        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] p,
        [data-testid="stMetricLabel"] label,
        [data-testid="stMetricLabel"] span {
            font-size: 13px !important;
            font-weight: 600 !important;
            color: #8da4c4 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.4px !important;
            line-height: 1.25 !important;
            margin: 0 0 3px 0 !important;
            white-space: normal !important;
            word-break: break-word !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }

        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] > div {
            font-size: 24px !important;
            font-weight: 700 !important;
            color: #ffffff !important;
            font-family: 'JetBrains Mono', monospace !important;
            line-height: 1.2 !important;
            white-space: normal !important;
            word-break: break-word !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }

        [data-testid="stMetricDelta"] {
            font-size: 12px !important;
            font-weight: 600 !important;
            line-height: 1.2 !important;
        }

        /* =========================================================================
           3. DATABASE EVENT TABLES & DATAFRAMES
           ========================================================================= */

        [data-testid="stDataFrame"] {
            font-size: 12px !important;
            font-family: 'JetBrains Mono', monospace !important;
            border: 1px solid #1f2e46 !important;
            border-radius: 8px !important;
            overflow: hidden !important;
        }

        table, .stTable {
            font-size: 12px !important;
            width: 100% !important;
            border-collapse: collapse !important;
            border: 1px solid #1f2e46 !important;
            border-radius: 8px !important;
        }

        table th, .stTable th {
            font-size: 11px !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.6px !important;
            color: #94a3b8 !important;
            background-color: #0d1520 !important;
            border-bottom: 1px solid #1f2e46 !important;
            padding: 8px 12px !important;
            white-space: nowrap !important;
        }

        table td, .stTable td {
            font-size: 12px !important;
            color: #e2e8f0 !important;
            padding: 6px 12px !important;
            border-bottom: 1px solid #141e2e !important;
            line-height: 1.4 !important;
            word-break: break-word !important;
        }

        table tr:hover td {
            background-color: rgba(30, 41, 59, 0.4) !important;
        }

        /* =========================================================================
           4. ALERTS, ERROR MESSAGES, AND PASS/FAIL BANNERS
           ========================================================================= */

        [data-testid="stAlert"] {
            font-size: 13px !important;
            padding: 10px 14px !important;
            border-radius: 8px !important;
            line-height: 1.45 !important;
            word-break: break-word !important;
            overflow-wrap: anywhere !important;
            margin-top: 8px !important;
            margin-bottom: 10px !important;
        }

        [data-testid="stAlert"] p {
            font-size: 13px !important;
            line-height: 1.45 !important;
            margin: 0 !important;
            color: inherit !important;
        }

        [data-testid="stAlert"] code {
            font-size: 12px !important;
            font-family: 'JetBrains Mono', monospace !important;
            background: rgba(0, 0, 0, 0.35) !important;
            padding: 2px 6px !important;
            border-radius: 4px !important;
            word-break: break-all !important;
            white-space: pre-wrap !important;
        }

        /* PASS / FAIL Experiment Status Banner */
        .acid-status-card {
            background: rgba(15, 23, 42, 0.65);
            border-radius: 8px;
            padding: 10px 14px;
            margin-bottom: 14px;
            line-height: 1.4;
        }

        .acid-status-badge {
            color: #000;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            letter-spacing: 0.5px;
            display: inline-block;
            text-transform: uppercase;
        }

        .acid-status-title {
            color: #f8fafc;
            margin-left: 10px;
            font-weight: 600;
            font-size: 14px;
        }

        .acid-status-desc {
            color: #cbd5e1;
            margin: 6px 0 0 0;
            font-size: 13px !important;
            line-height: 1.45;
            word-break: break-word;
            overflow-wrap: anywhere;
        }

        /* =========================================================================
           5. EXPANDERS, TABS, INPUTS & BUTTONS
           ========================================================================= */

        [data-testid="stExpander"] {
            border: 1px solid #1f2e46 !important;
            border-radius: 8px !important;
            background-color: #0b111a !important;
            margin-bottom: 14px !important;
        }

        [data-testid="stExpander"] details summary {
            padding: 10px 14px !important;
        }

        [data-testid="stExpander"] details summary p,
        [data-testid="stExpander"] details summary span {
            font-size: 15px !important;
            font-weight: 600 !important;
            color: #e2e8f0 !important;
        }

        [data-testid="stExpander"] details summary:hover p {
            color: #38bdf8 !important;
        }

        [data-testid="stExpanderDetails"] {
            padding: 12px 14px !important;
        }

        /* Tabs */
        button[data-baseweb="tab"] {
            font-size: 14px !important;
            font-weight: 600 !important;
            padding: 8px 16px !important;
        }

        /* Form Controls */
        [data-testid="stNumberInput"] label,
        [data-testid="stTextInput"] label,
        [data-testid="stSelectbox"] label,
        [data-testid="stRadio"] label {
            font-size: 13px !important;
            font-weight: 500 !important;
            color: #cbd5e1 !important;
        }

        [data-testid="stNumberInput"] input,
        [data-testid="stTextInput"] input {
            font-size: 14px !important;
            font-family: 'JetBrains Mono', monospace !important;
            padding: 6px 10px !important;
        }

        [data-testid="stButton"] button {
            font-size: 13px !important;
            font-weight: 600 !important;
            padding: 6px 14px !important;
            border-radius: 6px !important;
        }

        /* Status Widget (Spinner / Progress Box) */
        [data-testid="stStatusWidget"] {
            font-size: 13px !important;
            border-radius: 8px !important;
            padding: 8px 12px !important;
        }

        [data-testid="stStatusWidget"] p {
            font-size: 13px !important;
            margin: 0 !important;
        }

        /* Top banner card */
        .tech-header {
            background: linear-gradient(135deg, #0d1b2a 0%, #1b263b 50%, #0d1b2a 100%);
            border: 1px solid #415a77;
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 20px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
        }

        .tech-header h1 {
            color: #e0e1dd;
            font-size: 26px !important;
            font-weight: 700;
            margin: 0 0 6px 0 !important;
            letter-spacing: -0.5px;
        }

        .tech-header p {
            color: #778da9;
            font-size: 13px !important;
            margin: 0 !important;
        }

        /* Status Badges */
        .badge-connected {
            background-color: rgba(46, 204, 113, 0.15);
            color: #2ecc71;
            border: 1px solid #2ecc71;
            padding: 3px 10px;
            border-radius: 14px;
            font-size: 11px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }

        .badge-disconnected {
            background-color: rgba(231, 76, 60, 0.15);
            color: #e74c3c;
            border: 1px solid #e74c3c;
            padding: 3px 10px;
            border-radius: 14px;
            font-size: 11px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }

        .badge-warning {
            background-color: rgba(243, 156, 18, 0.15);
            color: #f39c12;
            border: 1px solid #f39c12;
            padding: 3px 10px;
            border-radius: 14px;
            font-size: 11px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }

        /* Academic Callout Boxes */
        .acid-card {
            background: #0d1520;
            border-left: 4px solid #3b82f6;
            border-radius: 0 8px 8px 0;
            padding: 14px 18px;
            margin-bottom: 14px;
        }

        .acid-card h4 {
            color: #60a5fa;
            margin: 0 0 4px 0 !important;
            font-size: 15px !important;
            font-weight: 600 !important;
        }

        .acid-card p {
            color: #94a3b8;
            font-size: 13px !important;
            margin: 0 !important;
            line-height: 1.5;
        }

        /* State Indicator Pills */
        .state-active { color: #38bdf8; font-weight: bold; }
        .state-committed { color: #4ade80; font-weight: bold; }
        .state-aborted { color: #f87171; font-weight: bold; }
        .state-failed { color: #fb923c; font-weight: bold; }
        .state-partially { color: #facc15; font-weight: bold; }

        </style>
        """,
        unsafe_allow_html=True,
    )
