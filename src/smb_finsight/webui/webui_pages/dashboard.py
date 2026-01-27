# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Dashboard page (WebUI).

This module intentionally stays *thin*: it orchestrates layout + user selections
and delegates most work to dedicated WebUI modules.

High-level flow:
1) Read Dashboard sections from LayoutConfig (tiles + charts) and page UI labels.
2) Render the period controls (primary + optional comparison + granularity).
3) Run the dashboard compute pipeline once for:
   - the selected primary/comparison periods (for tiles),
   - bucketized periods (for charts).
4) Render tiles and the Trends section.

Where to look for implementation details:
- Period controls UI + preset logic:
  smb_finsight.webui.period_ui.render_period_controls()
- Compute pipeline (split into buckets + multi-period compute):
  smb_finsight.webui.pipeline.run_dashboard_pipeline()
  Note: the dashboard uses ratios_level="full" to ensure tiles/charts can
  display any ratio.
- Tiles rendering + delta formatting rules (incl. pp for percent abs-deltas):
  smb_finsight.webui.components.metric_tiles.render_metric_tiles()
  smb_finsight.webui.formatting
- Trends charts layout and rendering:
  smb_finsight.webui.components.dashboard_charts.render_dashboard_trends_charts()
  smb_finsight.webui.components.charts

Configuration expectations (layout TOML):
Dashboard page configuration is sourced from the following sections:

- [dashboard]
  - [[dashboard.tiles]]   : list of KPI tiles displayed at the top of the page
  - [[dashboard.charts]]  : list of charts displayed in the Trends section

- [pages.dashboard]
  - allow_secondary_period : whether the user can enable a comparison period

- [pages.dashboard.ui]
  - UI labels and flags used by the dashboard page and period controls
    (section titles, field labels, default comparison toggle, error messages, etc.)

- [pages.dashboard.periods]
  - default_primary_preset
  - default_comparison_preset
  - default_granularity
  - allowed_granularities
  - preset labels (primary / comparison)
  - optional user-defined presets

Design notes (v0.5.0):
- Page-level period settings drive ALL tiles and charts.
- No per-tile / per-chart overrides (by design for simplicity).
- Tiles may show tooltips sourced from measure/ratio notes (when available).
- Delta display supports abs/pct; delta_good_direction maps to Streamlit delta_color.
"""

import pandas as pd
import streamlit as st

from smb_finsight.config import AppConfig
from smb_finsight.webui.components.dashboard_charts import (
    DashboardChartsContext,
    render_dashboard_trends_charts,
)
from smb_finsight.webui.components.metric_tiles import render_metric_tiles
from smb_finsight.webui.layout import LayoutConfig, PageConfig
from smb_finsight.webui.period_ui import render_period_controls
from smb_finsight.webui.pipeline import run_dashboard_pipeline
from smb_finsight.webui.utils import _get, _to_mapping

# -----------------------------------------------------------------------------
# UI render
# -----------------------------------------------------------------------------


def render(app_config: AppConfig, layout: LayoutConfig, page: PageConfig) -> None:
    """
    Render the Dashboard page.

    Args:
        app_config: Application configuration (currency, fiscal year,
        standard config, ratios level, etc.).
        layout: Parsed layout configuration (dashboard tiles/charts).
        page: Page configuration (title, ui labels, period presets, feature flags).

    Notes:
        - Period selection is handled by `render_period_controls()`.
        - Computation is executed once via `run_dashboard_pipeline()` and
        reused for both tiles and charts.
        - Errors in computation are surfaced via Streamlit and the page
        renders empty tables/sections.
    """

    st.title(_get(page, "title", "Dashboard"))

    # ---- Pull dashboard sections from global layout -------------------------
    currency_code = app_config.currency
    thousands_separator = getattr(app_config, "thousands_separator", ",")

    # Feature-flag: some pages may forbid comparisons even if presets exist.
    allow_secondary_period = bool(_get(page, "allow_secondary_period", True))

    tiles = list(layout.dashboard.tiles or [])
    charts = list(layout.dashboard.charts or [])

    # UI labels are stored in page.ui
    ui = _to_mapping(_get(page, "ui", {}))

    selection = render_period_controls(
        page=page,
        app_config=app_config,
        allow_secondary_period=allow_secondary_period,
    )
    primary_period = selection.primary_period
    comparison_period = selection.comparison_period
    granularity = selection.granularity
    primary_preset = selection.primary_preset
    comparison_preset = selection.comparison_preset
    # comparison_enabled = selection.comparison_enabled

    # Compute once for both tiles and charts (includes bucketized periods).
    # The pipeline forces ratios_level="full" to keep dashboard rendering deterministic.
    try:
        pipe = run_dashboard_pipeline(
            app_config=app_config,
            primary_period=primary_period,
            comparison_period=comparison_period,
            granularity=granularity,
        )
        measures_df = pipe.measures_df
        ratios_df = pipe.ratios_df
        primary_buckets = pipe.primary_buckets
        comp_buckets = pipe.comp_buckets
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to compute dashboard data: {exc}")
        measures_df = pd.DataFrame()
        ratios_df = pd.DataFrame()
        primary_buckets = []
        comp_buckets = []

    # ---- Tiles ---------------------------------------------------------------
    st.space(size="small")
    st.subheader(ui.get("section_key_metrics", "Key metrics"))

    render_metric_tiles(
        tiles=tiles,
        measures_df=measures_df,
        ratios_df=ratios_df,
        comparison_enabled=(comparison_period is not None),
        currency_code=currency_code,
        thousands_separator=thousands_separator,
    )

    # ---- Charts --------------------------------------------------------------
    st.space(size="small")
    st.subheader(ui.get("section_trends", "Trends"))

    ctx = DashboardChartsContext(
        measures_df=measures_df,
        ratios_df=ratios_df,
        granularity=granularity,
        primary_preset_code=primary_preset,
        comparison_preset_code=comparison_preset,
        primary_period=primary_period,
        comparison_period=comparison_period,
        primary_buckets=primary_buckets,
        comp_buckets=comp_buckets,
        comparison_enabled=(comparison_period is not None),
        primary_preset_label=selection.primary_preset_label,
        comparison_preset_label=selection.comparison_preset_label,
        currency_code=currency_code,
        thousands_separator=thousands_separator,
    )

    render_dashboard_trends_charts(charts=charts, ctx=ctx)
