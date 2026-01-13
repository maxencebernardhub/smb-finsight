# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
WebUI compute pipelines.

This module centralizes compute steps shared by Streamlit pages. It exists to:
- keep page files (dashboard.py, future ratios.py) thin and focused on UI,
- compute multi-period outputs once and reuse them across tiles and charts,
- standardize period labeling conventions used throughout the WebUI.

Key conventions:
- The selected primary/comparison periods are included as-is and are expected to have
  `period_label` values "PRIMARY" and "COMPARISON" (set upstream by period_ui).
- Chart buckets are derived from those periods using `split_period(...)`
and are labeled:
  - primary buckets:  "P_<...>" (label_prefix="P_")
  - comparison buckets: "C_<...>" (label_prefix="C_")

Why ratios_level="full" on the Dashboard:
- The dashboard mixes measures and ratios in tiles and charts.
- For deterministic rendering, we compute all ratios regardless of
app_config.ratios_level.
  (Other pages may choose a different policy.)
"""

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from smb_finsight.config import AppConfig
from smb_finsight.multi_periods import compute_all_multi_period
from smb_finsight.period_utils import split_period


@dataclass(frozen=True)
class DashboardPipelineResult:
    """
    Output of the Dashboard compute pipeline.

    Attributes:
        measures_df: Multi-period measures DataFrame
        (includes PRIMARY/COMPARISON and bucket periods).
        ratios_df: Multi-period ratios DataFrame
        (includes PRIMARY/COMPARISON and bucket periods).
        primary_buckets: Bucket periods for the primary selection
        (labels prefixed with "P_").
        comp_buckets: Bucket periods for the comparison selection
        (labels prefixed with "C_"), or [].
        all_periods: Period list passed to `compute_all_multi_period()`
        (primary/comparison + buckets).
    """

    measures_df: pd.DataFrame
    ratios_df: pd.DataFrame
    primary_buckets: list[Any]
    comp_buckets: list[Any]
    all_periods: list[Any]


def run_dashboard_pipeline(
    *,
    app_config: AppConfig,
    primary_period: Any,
    comparison_period: Optional[Any],
    granularity: str,
) -> DashboardPipelineResult:
    """
    Run the Dashboard compute pipeline.

    This function is a strict extraction of the dashboard.py compute logic:
    - include the selected primary and optional comparison periods (for KPI tiles),
    - generate bucketized periods for charts via `split_period`
    using a fixed label_prefix:
        primary buckets -> "P_<...>"
        comparison buckets -> "C_<...>"
    - compute all periods once using `compute_all_multi_period`,
      then expose measures_df and ratios_df for the UI.

    Args:
        app_config: Application config. Provides `standard_config`
        and other global settings.
        primary_period: Period object labeled "PRIMARY" (from period_ui).
        comparison_period: Optional Period object labeled "COMPARISON" (from period_ui).
        granularity: Bucket granularity used for chart x-axes
        (DAY/WEEK/MONTH/QUARTER/FY).

    Returns:
        DashboardPipelineResult containing computed dataframes and bucket periods.

    Notes:
        - The dashboard forces `ratios_level="full"` to ensure all tiles/charts can
        render consistently regardless of `app_config.ratios_level`.
        - On the dashboard, `comp_buckets` is an empty list when comparison is disabled.
    """

    # Tiles use PRIMARY/COMPARISON periods directly (not bucketized).
    periods_for_compute = [primary_period]
    if comparison_period is not None:
        periods_for_compute.append(comparison_period)

    # Prefix buckets to keep them distinct from PRIMARY/COMPARISON
    # in multi-period outputs.
    primary_buckets = split_period(primary_period, granularity, label_prefix="P_")
    comp_buckets: list[Any] = []
    if comparison_period is not None:
        comp_buckets = split_period(comparison_period, granularity, label_prefix="C_")

    all_periods = periods_for_compute + primary_buckets + comp_buckets

    # Compute once for tiles + charts. Dashboard policy: always compute full ratios.
    _, measures_mp, ratios_mp = compute_all_multi_period(
        app_config=app_config,
        standard_config=app_config.standard_config,
        periods=all_periods,
        ratios_level="full",
    )
    measures_df = measures_mp.data
    ratios_df = ratios_mp.data

    return DashboardPipelineResult(
        measures_df=measures_df,
        ratios_df=ratios_df,
        primary_buckets=primary_buckets,
        comp_buckets=comp_buckets,
        all_periods=all_periods,
    )
