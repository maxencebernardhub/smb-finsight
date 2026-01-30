# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Period selection UI (WebUI).

This module renders the period controls used by WebUI pages
(Dashboard and Ratios & KPIs & Statements pages):
- primary period preset (FY/YTD/MTD/LAST_MONTH/CUSTOM + optional user-defined presets),
- optional comparison period preset (FY_PREV/YTD_PREV_FY/... + CUSTOM + user presets),
- Optional chart granularity selector (DAY/WEEK/MONTH/QUARTER/CY/FY). Granularity is
global to the page (no per-chart override).

NB: Some pages may hide granularity and use the third slot for a custom control via
third_slot_renderer (e.g., the Statements page view level selector); ; its return value
is surfaced in PeriodControlsResult.third_slot_value.

Configuration source:
- In layout_en.toml, presets and labels are typically configured under:
  [pages.<page_id>.periods] and [pages.<page_id>.ui]
- At runtime, `page` is a parsed PageConfig object (not raw TOML); this module reads
  `page.periods` and `page.ui` via safe mapping helpers.

Design notes:
- Built-in presets are defined in code to keep the UI predictable.
- User presets can be added in TOML and are appended to built-in options.
- CUSTOM uses Streamlit session_state keys:
  - primary:  p_start / p_end
  - comparison: c_start / c_end
- The returned Period objects are labeled "PRIMARY" / "COMPARISON"
and can be bucketized later.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

import streamlit as st

from smb_finsight.period_utils import (
    CustomRange,
    period_from_preset,
    period_from_relative_preset,
)
from smb_finsight.webui.utils import _as_list, _get, _to_mapping


def _validate_custom_range(
    start: Optional[date],
    end: Optional[date],
    *,
    toast: bool,
    error_message: str,
) -> bool:
    """
    Validate a custom date range from Streamlit inputs.

    This helper is intentionally Streamlit-aware:
    - it displays a warning,
    - optionally toasts,
    - and calls `st.stop()` to prevent rendering with an invalid range.
    """

    if start is None or end is None:
        return False
    if end < start:
        st.warning(error_message)
        if toast:
            st.toast(error_message, icon="⚠️")
        # Stop rendering to avoid cascading errors with invalid dates.
        st.stop()
        return False
    return True


@dataclass(frozen=True)
class PeriodControlsResult:
    """
    Structured output of the period controls.

    This object is used by pages to:
    - run compute pipelines (primary/comparison Period objects),
    - label charts (human-friendly preset labels),
    - keep preset codes for downstream decisions (render mode, etc.).
    """

    primary_period: Any
    comparison_period: Optional[Any]
    granularity: str
    primary_preset: str
    comparison_preset: Optional[str]
    comparison_enabled: bool
    primary_preset_label: str
    comparison_preset_label: Optional[str]
    # Optional value returned by a custom renderer injected in the 3rd column.
    third_slot_value: Any = None


def render_period_controls(
    *,
    page: Any,
    app_config: Any,
    allow_secondary_period: bool,
    show_granularity: bool = True,
    third_slot_renderer: Optional[Callable[[], Any]] = None,
) -> PeriodControlsResult:
    """
    Render period controls (primary, optional comparison, and optional granularity).

    Args:
        page: Parsed PageConfig for the current page (e.g., layout.pages["dashboard"]).
        app_config: AppConfig (used for fiscal year boundaries).
        allow_secondary_period: Whether comparison selection is enabled for this page.
        show_granularity: Whether to display the granularity selector (used by
            chart-heavy pages).
        third_slot_renderer:
            Optional callback used to render custom UI in the 3rd column (c3) when
            ``show_granularity`` is False. This is typically used by pages that need
            a third control (e.g., "View level" on the Statements page). The callback
            may return a value (e.g., selected view level), which will be exposed as
            ``PeriodControlsResult.third_slot_value``.

    Layout keys used (from page.periods and page.ui):
        page.periods:
            - default_primary_preset, default_comparison_preset
            - primary_preset_labels, comparison_preset_labels
            - user_presets (optional):
                Mapping of preset_code ->
                {start="YYYY-MM-DD", end="YYYY-MM-DD", label="..."}.
            - (optional, used only when show_granularity=True):
                default_granularity, allowed_granularities, granularity_labels
        page.ui:
            - label_primary_period
            - label_comparison_toggle
            - label_comparison_period
            - label_custom_from, label_custom_to
            - label_granularity (only when show_granularity=True)
            - help_primary_period
            - help_comparison_period
            - help_granularity (only when show_granularity=True)
            - error_custom_end_before_start
            - default_enable_comparison (optional)

    Notes:
        - The controls are laid out in three columns (primary, comparison, and
          a third slot).
        - When ``show_granularity`` is True, the third slot shows the granularity
          selector.
        - When ``show_granularity`` is False, the third slot can be populated by
          ``third_slot_renderer`` (if provided). If provided, the return value is
          propagated via third_slot_value.
    """

    page_periods = _get(page, "periods", None)
    periods_cfg = _to_mapping(page_periods)

    # UI labels are stored in page.ui
    ui = _to_mapping(_get(page, "ui", {}))

    primary_labels = _to_mapping(periods_cfg.get("primary_preset_labels", {}))
    comparison_labels = _to_mapping(periods_cfg.get("comparison_preset_labels", {}))
    granularity_labels = (
        _to_mapping(periods_cfg.get("granularity_labels", {}))
        if show_granularity
        else {}
    )

    # NEW: user-defined presets from layout_en.toml
    user_presets = _to_mapping(periods_cfg.get("user_presets", {}))
    user_preset_labels: dict[str, str] = {}
    for k, v in user_presets.items():
        if isinstance(v, dict):
            user_preset_labels[str(k).upper()] = str(v.get("label", k))
        else:
            user_preset_labels[str(k).upper()] = str(k)

    def fmt_primary(code: str) -> str:
        c = str(code).upper()
        if c in user_preset_labels:
            return user_preset_labels[c]
        return str(primary_labels.get(c, c))

    def fmt_comparison(code: str) -> str:
        c = str(code).upper()
        if c in user_preset_labels:
            return user_preset_labels[c]
        return str(comparison_labels.get(c, c))

    def fmt_granularity(code: str) -> str:
        code_u = str(code).upper()
        return str(granularity_labels.get(code_u, code_u.lower()))

    # Defaults
    default_primary_preset = (
        periods_cfg.get("default_primary_preset") or "YTD"
    ).upper()
    default_comparison_preset = (
        periods_cfg.get("default_comparison_preset") or "YTD_PREV_FY"
    ).upper()
    default_granularity = (periods_cfg.get("default_granularity") or "MONTH").upper()

    allowed_granularities = [
        str(g).upper() for g in _as_list(periods_cfg.get("allowed_granularities", []))
    ]

    # Built-in presets are hardcoded to keep the UI stable across layouts.

    builtin_primary = ["FY", "YTD", "MTD", "LAST_MONTH", "CUSTOM"]
    builtin_comparison = [
        "FY_PREV",
        "YTD_PREV_FY",
        "LAST_MONTH",
        "PREV_PERIOD",
        "SAME_PERIOD_PREV_FY",
        "CUSTOM",
    ]

    # Append user presets (keys from TOML)
    # User presets extend built-ins (configured in TOML)
    # and are appended to option lists.
    user_preset_keys = [str(k).upper() for k in user_presets.keys()]

    primary_options = builtin_primary + user_preset_keys
    comparison_options = builtin_comparison + user_preset_keys

    # ---- Controls row -------------------------------------------------------
    today = date.today()
    fy = app_config.fiscal_year

    # Always reserve 3 columns so pages can reuse the 3rd slot
    # (e.g., Statements uses it for "View level" instead of granularity).
    c1, c2, c3 = st.columns([1.2, 1.2, 1.0])

    primary_preset: str
    comparison_preset: Optional[str] = None
    comparison_enabled: bool

    primary_custom_start: Optional[date] = None
    primary_custom_end: Optional[date] = None
    comparison_custom_start: Optional[date] = None
    comparison_custom_end: Optional[date] = None

    third_slot_value: Any = None

    # Primary
    with c1:
        with st.container(border=True, height="stretch"):
            primary_idx = (
                primary_options.index(default_primary_preset)
                if default_primary_preset in primary_options
                else 0
            )
            primary_preset = st.selectbox(
                ui.get("label_primary_period", "Primary period"),
                options=primary_options,
                index=primary_idx,
                format_func=fmt_primary,
                help=ui.get("help_primary_period", "Select the primary period"),
            )

            if primary_preset == "CUSTOM":
                if "p_start" not in st.session_state:
                    st.session_state["p_start"] = fy.start_date
                if "p_end" not in st.session_state:
                    st.session_state["p_end"] = min(fy.end_date, today)

                d1, d2 = st.columns(2)
                with d1:
                    primary_custom_start = st.date_input(
                        ui.get("label_custom_from", "Start date"),
                        key="p_start",
                    )
                with d2:
                    primary_custom_end = st.date_input(
                        ui.get("label_custom_to", "End date"),
                        key="p_end",
                    )

    # Comparison
    with c2:
        with st.container(border=True, height="stretch"):
            if allow_secondary_period:
                raw = ui.get("default_enable_comparison", False)
                default_enable = (
                    raw if isinstance(raw, bool) else str(raw).strip().lower() == "true"
                )
                comparison_enabled = st.toggle(
                    ui.get("label_comparison_toggle", "Enable comparison"),
                    value=default_enable,
                    help=ui.get(
                        "help_comparison_toggle", "Enable or disable comparison period."
                    ),
                )
            else:
                comparison_enabled = False
                st.toggle(
                    ui.get("label_comparison_toggle", "Enable comparison"),
                    value=False,
                    disabled=True,
                )

            if comparison_enabled:
                comp_idx = (
                    comparison_options.index(default_comparison_preset)
                    if default_comparison_preset in comparison_options
                    else 0
                )
                comparison_preset = st.selectbox(
                    ui.get("label_comparison_period", "Comparison period"),
                    options=comparison_options,
                    index=comp_idx,
                    format_func=fmt_comparison,
                    help=ui.get(
                        "help_comparison_period", "Select the comparison period"
                    ),
                )

                if comparison_preset == "CUSTOM":
                    if "c_start" not in st.session_state:
                        st.session_state["c_start"] = fy.start_date
                    if "c_end" not in st.session_state:
                        st.session_state["c_end"] = min(fy.end_date, today)

                    d1, d2 = st.columns(2)
                    with d1:
                        comparison_custom_start = st.date_input(
                            ui.get("label_custom_from", "Start date"),
                            key="c_start",
                        )
                    with d2:
                        comparison_custom_end = st.date_input(
                            ui.get("label_custom_to", "End date"),
                            key="c_end",
                        )

    # Granularity (optional)
    if show_granularity:
        with c3:
            with st.container(border=True, height="stretch"):
                if not allowed_granularities:
                    allowed_granularities = [
                        "DAY",
                        "WEEK",
                        "MONTH",
                        "QUARTER",
                        "CY",
                        "FY",
                    ]

                granularity = st.selectbox(
                    ui.get("label_granularity", "Granularity"),
                    options=allowed_granularities,
                    index=allowed_granularities.index(default_granularity)
                    if default_granularity in allowed_granularities
                    else 0,
                    format_func=fmt_granularity,
                    help=ui.get("help_granularity", "Granularity affects charts."),
                )
    else:
        # Selector hidden: keep a stable value for downstream code.
        if not allowed_granularities:
            allowed_granularities = ["DAY", "WEEK", "MONTH", "QUARTER", "CY", "FY"]
        if default_granularity not in allowed_granularities:
            default_granularity = allowed_granularities[0]
        granularity = default_granularity

        # Allow the calling page to render its own control in the third column.
        if third_slot_renderer is not None:
            with c3:
                with st.container(border=True, height="stretch"):
                    third_slot_value = third_slot_renderer()

    # ---- Build Period objects ------------------------------------------------
    custom_range_error_msg = ui.get(
        "error_custom_end_before_start", "End date cannot be earlier than start date."
    )

    custom_primary: Optional[CustomRange] = None
    if primary_preset == "CUSTOM":
        if _validate_custom_range(
            primary_custom_start,
            primary_custom_end,
            toast=True,
            error_message=custom_range_error_msg,
        ):
            custom_primary = CustomRange(primary_custom_start, primary_custom_end)

    custom_comp: Optional[CustomRange] = None
    if comparison_enabled and comparison_preset == "CUSTOM":
        if _validate_custom_range(
            comparison_custom_start,
            comparison_custom_end,
            toast=True,
            error_message=custom_range_error_msg,
        ):
            custom_comp = CustomRange(comparison_custom_start, comparison_custom_end)

    # Compute periods (user_presets passed through)
    primary_period = period_from_preset(
        primary_preset,
        fy,
        custom=custom_primary,
        label="PRIMARY",
        user_presets=user_presets,
    )

    comparison_period = None
    if comparison_enabled and comparison_preset:
        rel = comparison_preset.strip().upper()
        # Relative presets depend on the chosen primary period (not the fiscal year).
        if rel in {"PREV_PERIOD", "SAME_PERIOD_PREV_FY"}:
            comparison_period = period_from_relative_preset(
                rel,
                reference=primary_period,
                label="COMPARISON",
            )
        else:
            comparison_period = period_from_preset(
                comparison_preset,
                fy,
                custom=custom_comp,
                label="COMPARISON",
                user_presets=user_presets,
            )

    if comparison_enabled and comparison_period is None:
        comparison_enabled = False
        comparison_preset = None
        st.warning(
            "Comparison period could not be computed; comparison has been disabled."
        )

    # Display a compact summary to make selections explicit to the user.
    prim_label = ui.get("label_primary_period", "Primary period")
    comp_label = ui.get("label_comparison_period", "Comparison period")
    st.markdown(
        f"###### {prim_label}: {primary_period.start} – {primary_period.end}"
        + (
            f" | {comp_label}: {comparison_period.start} – {comparison_period.end}"
            if comparison_period is not None
            else ""
        )
    )

    return PeriodControlsResult(
        primary_period=primary_period,
        comparison_period=comparison_period,
        granularity=granularity,
        primary_preset=primary_preset,
        comparison_preset=comparison_preset,
        comparison_enabled=comparison_enabled,
        primary_preset_label=fmt_primary(primary_preset),
        comparison_preset_label=fmt_comparison(comparison_preset)
        if comparison_preset is not None
        else None,
        third_slot_value=third_slot_value,
    )
