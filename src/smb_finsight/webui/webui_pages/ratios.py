# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Ratios & KPIs page (WebUI).

This module intentionally stays *thin*: it orchestrates layout + user selections
and delegates most work to dedicated WebUI modules.

High-level flow:
1) Read Ratios sections from LayoutConfig (layout.ratios_page.sections)
and page UI labels.
2) Render the period controls (primary + optional comparison + granularity).
3) Run the ratios compute pipeline once for:
   - the selected primary/comparison periods (for tiles),
   - bucketized periods (used by charts).
4) Render sections in order:
   - measures and ratios tiles
   - charts

Where to look for implementation details:
- Period controls UI + preset logic:
  smb_finsight.webui.period_ui.render_period_controls()
- Compute pipeline (split into buckets + multi-period compute):
  smb_finsight.webui.pipeline.run_ratios_pipeline()
  Note: the ratios pipeline uses ratios_level="full" to ensure any ratio key
  referenced by the layout can be rendered (levels are CLI-only for now).
- Section-based rendering (tiles):
  smb_finsight.webui.components.ratios_sections.render_ratios_sections()
  This renderer reuses the shared dashboard tile renderer to keep formatting
  and delta semantics consistent across pages.

Configuration expectations (layout TOML):
- [pages.ratios]
  - allow_secondary_period : whether the user can enable a comparison period

- [pages.ratios.ui]
  - UI labels and flags used by the page and period controls
    (section labels, field labels, default comparison toggle, error messages, etc.)

- [pages.ratios.periods]
  - default_primary_preset
  - default_comparison_preset
  - default_granularity
  - allowed_granularities
  - preset labels (primary / comparison)
  - optional user-defined presets

- [ratios_page]
  - [[ratios_page.sections]] with nested:
      [[ratios_page.sections.measures]] (tile specs)
      [[ratios_page.sections.ratios]]   (tile specs)
      [[ratios_page.sections.charts]]   (draft specs, not rendered yet)
"""

import pandas as pd
import streamlit as st

from smb_finsight.config import AppConfig
from smb_finsight.webui.components.ratios_sections import (
    RatiosSectionsContext,
    render_ratios_sections,
)
from smb_finsight.webui.layout import LayoutConfig, PageConfig
from smb_finsight.webui.period_ui import render_period_controls
from smb_finsight.webui.pipeline import run_ratios_pipeline
from smb_finsight.webui.utils import _get

# -----------------------------------------------------------------------------
# UI render
# -----------------------------------------------------------------------------


def render(app_config: AppConfig, layout: LayoutConfig, page: PageConfig) -> None:
    """
    Render the Ratios & KPIs page.

    Args:
        app_config: Application configuration (currency, fiscal year,
            standard config, ratios level, etc.).
        layout: Parsed layout configuration (ratios_page sections).
        page: Page configuration (title, ui labels, period presets, feature flags).

    Notes:
        - Period selection is handled by `render_period_controls()`.
        - Computation is executed once via `run_ratios_pipeline()`.
        - Charts are rendered after tiles; they follow the global granularity.
    """

    st.title(_get(page, "title", "Ratios & KPIs"))

    currency_code = app_config.currency
    thousands_separator = getattr(app_config, "thousands_separator", ",")

    # Feature-flag: some pages may forbid comparisons even if presets exist.
    allow_secondary_period = bool(_get(page, "allow_secondary_period", True))

    # Period controls (same component as Dashboard)
    selection = render_period_controls(
        page=page,
        app_config=app_config,
        allow_secondary_period=allow_secondary_period,
    )
    primary_period = selection.primary_period
    comparison_period = selection.comparison_period
    granularity = selection.granularity
    primary_preset_code = selection.primary_preset
    comparison_preset_code = selection.comparison_preset
    primary_label = selection.primary_preset_label
    comparison_label = selection.comparison_preset_label

    # Compute once (includes optional bucket periods for future charts)
    try:
        pipe = run_ratios_pipeline(
            app_config=app_config,
            primary_period=primary_period,
            comparison_period=comparison_period,
            granularity=granularity,
        )
        measures_df = pipe.measures_df
        ratios_df = pipe.ratios_df
        primary_buckets = pipe.primary_buckets
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to compute ratios data: {exc}")
        measures_df = pd.DataFrame()
        ratios_df = pd.DataFrame()
        primary_buckets = []

    # ---- Sections ------------------------------------------------------------
    st.space(size="small")

    ctx = RatiosSectionsContext(
        measures_df=measures_df,
        ratios_df=ratios_df,
        comparison_enabled=(comparison_period is not None),
        currency_code=currency_code,
        thousands_separator=thousands_separator,
        granularity=granularity,
        primary_period=primary_period,
        comparison_period=comparison_period,
        primary_preset_code=primary_preset_code,
        comparison_preset_code=comparison_preset_code,
        primary_preset_label=primary_label,
        comparison_preset_label=comparison_label,
        primary_buckets=primary_buckets,
        comp_buckets=pipe.comp_buckets,
    )

    render_ratios_sections(
        sections=list(layout.ratios_page.sections or []),
        ctx=ctx,
    )
