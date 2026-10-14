"""
Plotly visualization components for transaction states, concurrency timelines,
value comparison charts, and deadlock graphs.
"""

from typing import List, Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from engine.models import TransactionEvent


def render_state_machine_chart() -> go.Figure:
    """
    Renders the classic DBMS 5-state transaction lifecycle diagram.
    States: ACTIVE, PARTIALLY_COMMITTED, COMMITTED, FAILED, ABORTED.
    """
    nodes = {
        "ACTIVE": {"x": 2, "y": 3, "color": "#38bdf8", "desc": "Initial state: executing reads/writes"},
        "PARTIALLY_COMMITTED": {"x": 5, "y": 4, "color": "#facc15", "desc": "Final statement executed; awaiting WAL flush"},
        "COMMITTED": {"x": 8, "y": 4, "color": "#4ade80", "desc": "Transaction succeeded; updates durable"},
        "FAILED": {"x": 5, "y": 2, "color": "#fb923c", "desc": "Failure detected (deadlock, error, conflict)"},
        "ABORTED": {"x": 8, "y": 2, "color": "#f87171", "desc": "Transaction rolled back; changes undone"},
    }

    fig = go.Figure()

    # Draw state transition edges
    edges = [
        ("ACTIVE", "PARTIALLY_COMMITTED", "End of Operations"),
        ("PARTIALLY_COMMITTED", "COMMITTED", "Commit Logged"),
        ("PARTIALLY_COMMITTED", "FAILED", "WAL Flush Error"),
        ("ACTIVE", "FAILED", "Execution Error / Conflict"),
        ("FAILED", "ABORTED", "Rollback / Cleanup"),
        ("ACTIVE", "ABORTED", "Explicit ROLLBACK"),
    ]

    for src, dst, label in edges:
        x0, y0 = nodes[src]["x"], nodes[src]["y"]
        x1, y1 = nodes[dst]["x"], nodes[dst]["y"]
        fig.add_annotation(
            x=x1,
            y=y1,
            ax=x0,
            ay=y0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            text=label,
            showarrow=True,
            arrowhead=3,
            arrowsize=1.5,
            arrowwidth=2,
            arrowcolor="#64748b",
            font=dict(color="#94a3b8", size=10, family="JetBrains Mono"),
        )

    # Add State Nodes
    for state_name, props in nodes.items():
        fig.add_trace(
            go.Scatter(
                x=[props["x"]],
                y=[props["y"]],
                mode="markers+text",
                name=state_name,
                marker=dict(size=45, color=props["color"], line=dict(color="#0f172a", width=3)),
                text=[state_name.replace("_", "<br>")],
                textposition="middle center",
                textfont=dict(color="#0f172a", size=10, family="JetBrains Mono", weight="bold"),
                hovertext=f"<b>{state_name}</b><br>{props['desc']}",
                hoverinfo="text",
                showlegend=False,
            )
        )

    fig.update_layout(
        title=dict(
            text="DBMS Transaction State Transition Diagram (Silberschatz / Garcia-Molina Model)",
            font=dict(color="#e2e8f0", size=14, family="Inter"),
        ),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.5, 9.5]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[1, 5]),
        paper_bgcolor="rgba(15, 23, 42, 0.4)",
        plot_bgcolor="rgba(15, 23, 42, 0.4)",
        height=380,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def render_timeline_chart(events: List[TransactionEvent]) -> go.Figure:
    """
    Renders an interactive event timeline chart comparing transaction step ordering.
    """
    if not events:
        fig = go.Figure()
        fig.update_layout(
            title="No event records available for this run",
            paper_bgcolor="rgba(15, 23, 42, 0.4)",
            plot_bgcolor="rgba(15, 23, 42, 0.4)",
            height=200,
        )
        return fig

    records = []
    for e in events:
        records.append(
            {
                "Step": e.step_number,
                "Transaction": e.transaction_id,
                "Operation": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                "Description": e.description,
                "ObservedValue": str(e.observed_value) if e.observed_value is not None else "N/A",
            }
        )

    df = pd.DataFrame(records)

    color_map = {
        "BEGIN": "#38bdf8",
        "READ": "#60a5fa",
        "WRITE": "#a855f7",
        "LOCK_ACQUIRE": "#f59e0b",
        "LOCK_WAIT": "#ef4444",
        "LOCK_RELEASED": "#10b981",
        "SAVEPOINT": "#06b6d4",
        "ROLLBACK_TO_SAVEPOINT": "#ec4899",
        "COMMIT": "#22c55e",
        "ROLLBACK": "#f43f5e",
        "STATE_CHANGE": "#64748b",
        "DEADLOCK_DETECTED": "#dc2626",
        "ERROR": "#b91c1c",
    }

    fig = px.scatter(
        df,
        x="Step",
        y="Transaction",
        color="Operation",
        color_discrete_map=color_map,
        hover_data=["Description", "ObservedValue"],
        size_max=18,
    )

    fig.update_traces(marker=dict(size=14, line=dict(width=1, color="#ffffff")))

    # Connect transactions with a line for continuity
    fig.update_layout(
        title=dict(text="Interleaved Transaction Execution Timeline (Monotonic Steps)", font=dict(color="#e2e8f0", size=14)),
        xaxis=dict(
            title="Monotonic Execution Step",
            gridcolor="#1e293b",
            color="#94a3b8",
            dtick=1,
        ),
        yaxis=dict(
            title="Transaction Context",
            gridcolor="#1e293b",
            color="#94a3b8",
            categoryorder="array",
            categoryarray=["SYSTEM", "T2", "T1"],
        ),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0b1120",
        height=320,
        legend=dict(
            font=dict(color="#cbd5e1", size=10),
            orientation="h",
            yanchor="bottom",
            y=-0.4,
            xanchor="center",
            x=0.5,
        ),
        margin=dict(l=30, r=30, t=50, b=60),
    )
    return fig


def render_value_comparison_chart(
    initial_value: Optional[float],
    expected_value: Optional[float],
    actual_value: Optional[float],
    title: str = "Database Value Comparison",
) -> go.Figure:
    """
    Renders bar chart comparing Initial, Expected, and Actual values,
    highlighting concurrency anomalies or locked correctness.
    """
    categories = ["Initial Value", "Expected Value", "Final Database Value"]
    values = [initial_value or 0.0, expected_value or 0.0, actual_value or 0.0]

    # Decide color for final value: Green if matches expected, Red if lost update anomaly
    is_anomaly = (
        actual_value is not None
        and expected_value is not None
        and abs(actual_value - expected_value) > 0.001
    )
    final_color = "#ef4444" if is_anomaly else "#22c55e"

    colors = ["#64748b", "#3b82f6", final_color]

    fig = go.Figure(
        data=[
            go.Bar(
                x=categories,
                y=values,
                text=[f"{v:.1f}" for v in values],
                textposition="auto",
                textfont=dict(family="JetBrains Mono", size=14, color="#ffffff", weight="bold"),
                marker=dict(color=colors, line=dict(color="#0f172a", width=2)),
            )
        ]
    )

    status_subtitle = (
        "ANOMALY DETECTED (Data Loss)"
        if is_anomaly
        else "CORRECT SERIALIZABLE OUTCOME"
    )

    fig.update_layout(
        title=dict(
            text=f"{title} — <span style='color:{final_color};'>{status_subtitle}</span>",
            font=dict(color="#e2e8f0", size=14),
        ),
        xaxis=dict(color="#94a3b8", gridcolor="#1e293b"),
        yaxis=dict(title="Resource Value", color="#94a3b8", gridcolor="#1e293b"),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0b1120",
        height=320,
        margin=dict(l=30, r=30, t=50, b=30),
    )
    return fig


def render_deadlock_graph() -> go.Figure:
    """
    Renders a Wait-For Graph (WFG) illustrating circular dependency between T1 and T2.
    """
    fig = go.Figure()

    nodes = {
        "T1": {"x": 2, "y": 3, "label": "Transaction T1<br>(Holds A, Waits B)"},
        "Resource A": {"x": 4, "y": 4.5, "label": "Resource A<br>(Locked by T1)"},
        "T2": {"x": 6, "y": 3, "label": "Transaction T2<br>(Holds B, Waits A)"},
        "Resource B": {"x": 4, "y": 1.5, "label": "Resource B<br>(Locked by T2)"},
    }

    # Arrows showing resource allocation and lock requests
    edges = [
        ("T1", "Resource A", "Holds Lock", "#22c55e"),
        ("T2", "Resource B", "Holds Lock", "#22c55e"),
        ("T1", "Resource B", "Requests Lock (Blocked)", "#ef4444"),
        ("T2", "Resource A", "Requests Lock (Deadlock Cycle!)", "#ef4444"),
    ]

    for src, dst, label, color in edges:
        x0, y0 = nodes[src]["x"], nodes[src]["y"]
        x1, y1 = nodes[dst]["x"], nodes[dst]["y"]
        fig.add_annotation(
            x=x1,
            y=y1,
            ax=x0,
            ay=y0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            text=label,
            showarrow=True,
            arrowhead=3,
            arrowsize=1.5,
            arrowwidth=2.5,
            arrowcolor=color,
            font=dict(color=color, size=10, family="JetBrains Mono"),
        )

    # Plot Nodes
    for name, props in nodes.items():
        is_tx = name.startswith("T")
        fig.add_trace(
            go.Scatter(
                x=[props["x"]],
                y=[props["y"]],
                mode="markers+text",
                marker=dict(
                    size=50 if is_tx else 40,
                    color="#1e293b" if is_tx else "#334155",
                    line=dict(color="#38bdf8" if is_tx else "#f59e0b", width=3),
                ),
                text=[props["label"]],
                textposition="middle center",
                textfont=dict(color="#f8fafc", size=9, family="JetBrains Mono"),
                hoverinfo="none",
                showlegend=False,
            )
        )

    fig.update_layout(
        title=dict(
            text="Lock Manager Wait-For Graph (Circular Wait Cycle Detected: T1 ⇄ T2)",
            font=dict(color="#e2e8f0", size=14),
        ),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[1, 7]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.5, 5.5]),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0b1120",
        height=360,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig
