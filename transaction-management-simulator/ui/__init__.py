"""UI package for Transaction Management Simulator."""
from .styling import apply_custom_css
from .dashboard import render_dashboard_page
from .transaction_view import render_transaction_lifecycle_page
from .scenario_views import render_scenarios_page
from .history_view import render_history_page
from .architecture_view import render_architecture_page
from .live_monitor_view import render_live_monitor_page

__all__ = [
    "apply_custom_css",
    "render_dashboard_page",
    "render_transaction_lifecycle_page",
    "render_scenarios_page",
    "render_history_page",
    "render_architecture_page",
    "render_live_monitor_page",
]
