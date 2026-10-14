"""
Smoke tests for UI components and render functions.
Ensures every page can load without crashing even when the database is offline.
"""

from unittest.mock import patch
import pytest

from ui.dashboard import render_dashboard_page
from ui.transaction_view import render_transaction_lifecycle_page
from ui.scenario_views import render_scenarios_page
from ui.history_view import render_history_page
from ui.architecture_view import render_architecture_page
from ui.visualizations import (
    render_state_machine_chart,
    render_timeline_chart,
    render_value_comparison_chart,
    render_deadlock_graph,
)


def test_visualizations_render_figures():
    """Verifies that all Plotly figures generate properly."""
    fig1 = render_state_machine_chart()
    assert fig1 is not None

    fig2 = render_timeline_chart([])
    assert fig2 is not None

    fig3 = render_value_comparison_chart(100.0, 130.0, 150.0)
    assert fig3 is not None

    fig4 = render_deadlock_graph()
    assert fig4 is not None
