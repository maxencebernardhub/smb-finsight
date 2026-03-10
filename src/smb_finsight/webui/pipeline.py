# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
WebUI compute pipelines.

This module defines high-level computation pipelines used by the Web UI
(Streamlit application).

A "pipeline" is responsible for:
- preparing the list of periods to compute (primary, optional comparison,
  and optional bucketized sub-periods for charts),
- calling the core computation engine once (`compute_all_multi_period`),
- returning pre-structured pandas DataFrames ready for UI rendering.

Design principles
-----------------
1) Separation of concerns:
   - Core computation logic lives in the engine layer
     (e.g. compute_all_multi_period, ratios engine).
   - This module orchestrates computations for UI needs only.
   - UI pages (dashboard, ratios, statements) should not perform computations
     directly, but rely on these pipelines.

2) Single computation pass:
   - Each pipeline computes all required periods in one call to
     `compute_all_multi_period`.
   - The resulting multi-period DataFrames are then reused for tiles and charts.

3) Page-specific pipelines:
   - Each analytical page has its own pipeline function with a clear contract:
       * Dashboard        -> run_dashboard_pipeline
       * Ratios & KPIs    -> run_ratios_pipeline
       * Statements       -> run_statements_pipeline
       * Future: Cashflow, etc.
   - This keeps page logic simple and avoids duplication in Streamlit code.

4) Periods and granularity:
   - Pipelines receive already-resolved Period objects from the UI layer
     (period_ui).
   - Granularity is used to generate bucketized sub-periods for charts.
     The selected granularity drives period bucketing for both tiles and charts
     (global per page).
   - Metric tiles always reflect full primary/comparison periods;
     bucketized periods are intended for charts only.

5) Ratios levels:
   - The Web UI and CLI can compute ratios at level "basic", "standard" and "full".
   - The UI layout decides which measures/ratios are displayed.

Outputs
-------
Each pipeline returns a typed result object (dataclass) containing:
- computed measures DataFrame,
- computed ratios DataFrame,
- the list of periods used for computation,
- optional bucketized periods for chart rendering.

This approach allows:
- lightweight page implementations,
- consistent behavior across pages,
- easy future extension (new pages, new chart types).
"""

from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class RatiosPipelineResult:
    """
    Output of the Ratios & KPIs compute pipeline.

    Attributes:
        measures_df:
            Multi-period measures DataFrame, including PRIMARY/COMPARISON and
            bucket periods (for future charts).
        ratios_df:
            Multi-period ratios DataFrame, including PRIMARY/COMPARISON and
            bucket periods (for future charts).
        primary_buckets:
            Bucket periods for the primary selection (labels prefixed with "P_").
        comp_buckets:
            Bucket periods for the comparison selection (labels prefixed with "C_"),
            or [] when comparison is disabled.
        all_periods:
            Period list passed to `compute_all_multi_period()`
            (primary/comparison + buckets).
    """

    measures_df: pd.DataFrame
    ratios_df: pd.DataFrame
    primary_buckets: list[Any]
    comp_buckets: list[Any]
    all_periods: list[Any]


@dataclass(frozen=True)
class StatementsPipelineResult:
    """
    Output of the Statements compute pipeline.

    Attributes:
        primary_df: Multi-period income statement DataFrame for the selected periods.
        secondary_df: Optional multi-period income statement DataFrame
        all_periods: Period list passed to `compute_all_multi_period()`.
    """

    primary_df: pd.DataFrame
    secondary_df: pd.DataFrame | None
    all_periods: list[Any]


def run_dashboard_pipeline(
    *,
    app_config: AppConfig,
    primary_period: Any,
    comparison_period: Any | None,
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
        (DAY/WEEK/MONTH/QUARTER/CY/FY).

    Returns:
        DashboardPipelineResult containing computed dataframes and bucket periods.

    Notes:
        - The dashboard forces `ratios_level="full"` to ensure all tiles/charts can
        render consistently regardless of `app_config.default_ratios_level`.
        - On the dashboard, `comp_buckets` is an empty list when comparison is disabled.
    """

    # Tiles use PRIMARY/COMPARISON periods directly (not bucketized).
    periods_for_compute = [primary_period]
    if comparison_period is not None:
        periods_for_compute.append(comparison_period)

    # Prefix buckets to keep them distinct from PRIMARY/COMPARISON
    # in multi-period outputs.
    primary_buckets = split_period(
        primary_period,
        granularity,
        label_prefix="P_",
        fiscal_year=app_config.fiscal_year,
    )
    comp_buckets: list[Any] = []
    if comparison_period is not None:
        comp_buckets = split_period(
            comparison_period,
            granularity,
            label_prefix="C_",
            fiscal_year=app_config.fiscal_year,
        )

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


def run_ratios_pipeline(
    *,
    app_config: AppConfig,
    primary_period: Any,
    comparison_period: Any | None,
    granularity: str,
) -> RatiosPipelineResult:
    """
    Run the Ratios & KPIs compute pipeline.

    This pipeline mirrors `run_dashboard_pipeline()`:
    - include the selected primary and optional comparison periods (for tiles),
    - generate bucketized periods for future charts via `split_period(...)`,
      using fixed label prefixes:
        primary buckets -> "P_<...>"
        comparison buckets -> "C_<...>"
    - compute all periods once using `compute_all_multi_period()`,
      then expose measures_df and ratios_df for the UI.

    Args:
        app_config:
            Application config. Provides `standard_config` and global settings.
        primary_period:
            Period object labeled "PRIMARY" (from period_ui).
        comparison_period:
            Optional Period object labeled "COMPARISON" (from period_ui).
        granularity:
            Bucket granularity for future charts (DAY/WEEK/MONTH/QUARTER/FY).
            Note: v1 of the Ratios page uses granularity only for future charts.
            Tiles always reflect the full selected PRIMARY/COMPARISON periods.

    Returns:
        RatiosPipelineResult containing computed dataframes and bucket periods.

    Notes:
        - The ratio pipeline forces `ratios_level="full"` to ensure all tiles/charts can
        render consistently regardless of `app_config.default_ratios_level`.

    """

    # Tiles use PRIMARY/COMPARISON periods directly (not bucketized).
    periods_for_compute = [primary_period]
    if comparison_period is not None:
        periods_for_compute.append(comparison_period)

    primary_buckets = split_period(
        primary_period,
        granularity,
        label_prefix="P_",
        fiscal_year=app_config.fiscal_year,
    )
    comp_buckets = (
        split_period(
            comparison_period,
            granularity,
            label_prefix="C_",
            fiscal_year=app_config.fiscal_year,
        )
        if comparison_period
        else []
    )

    all_periods = periods_for_compute + primary_buckets + comp_buckets

    # Compute once. Ratios page policy: always compute full ratios.
    _, measures_mp, ratios_mp = compute_all_multi_period(
        app_config=app_config,
        standard_config=app_config.standard_config,
        periods=all_periods,
        ratios_level="full",
    )

    return RatiosPipelineResult(
        measures_df=measures_mp.data,
        ratios_df=ratios_mp.data,
        primary_buckets=primary_buckets,
        comp_buckets=comp_buckets,
        all_periods=all_periods,
    )


def run_statements_pipeline(
    *,
    app_config: AppConfig,
    primary_period: Any,
    comparison_period: Any | None,
) -> StatementsPipelineResult:
    """
    Run the Statements compute pipeline.

    v0.5.x policy: compute the income statement(s) for PRIMARY and optional COMPARISON.
    (Comparison rendering is handled at the page/build layer.)

    Args:
        app_config: Application config.
        primary_period: Period labeled "PRIMARY" (from period_ui).
        comparison_period: Optional Period labeled "COMPARISON" (from period_ui).

    Returns:
        StatementsPipelineResult.
    """
    periods_for_compute = [primary_period]
    if comparison_period is not None:
        periods_for_compute.append(comparison_period)

    statements_mp, _, _ = compute_all_multi_period(
        app_config=app_config,
        standard_config=app_config.standard_config,
        periods=periods_for_compute,
        ratios_level="full",
    )

    return StatementsPipelineResult(
        primary_df=statements_mp.primary,
        secondary_df=statements_mp.secondary,
        all_periods=periods_for_compute,
    )
