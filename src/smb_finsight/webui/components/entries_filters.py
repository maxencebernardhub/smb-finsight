# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Entries filters component for SMB FinSight WebUI.

This module intentionally stays small and focused:
- v0.5.0 only needs a single period control (no comparison, no granularity).
- It reuses existing, battle-tested validation logic from period_ui.py to ensure
  consistent behavior across pages.

Layout expectations (layout_en.toml):
- [pages.entries.ui]
    - filter_period: label for the period selectbox
    - filter_code: label for the code filter input
    - filter_description: label for the description filter input
    - filter_amount_min / filter_amount_max: labels for the amount min/max inputs
    - filter_import_batch: label for the import batch dropdown
    - option_import_batch_all: label for the "All batches" option in the import batch
    - label_custom_from / label_custom_to: labels for CUSTOM range date inputs
    - placeholder_filter_code: placeholder for the code filter input
    - placeholder_filter_description: placeholder for the description filter input
    - placeholder_filter_amount_min: placeholder for the amount min filter input
    - placeholder_filter_amount_max: placeholder for the amount max filter input
    - help_period: tooltip/help for the period selectbox
    - help_filter_code: tooltip/help for the code filter input
    - help_filter_description: tooltip/help for the description filter input
    - help_filter_amount: tooltip/help for the amount filter container
    - help_filter_import_batch: tooltip/help for the import batch dropdown
    - help_toggle_unknown_only: tooltip for the "Show unknown accounts only" toggle
    - help_toggle_include_deleted: tooltip for the "Include deleted" toggle
    - toggle_include_deleted: label for the "Include deleted" toggle
    - toggle_unknown_only: label for the "Show unknown accounts only" toggle
    - error_custom_end_before_start: message when end < start
    - warning_amount_min_gt_max: message when min amount > max amount
    - badge_unknown_accounts: label prefix for the "Unknown accounts detected" badge
- [pages.entries.periods]
    - default_primary_preset: e.g. "ALL"
    - primary_preset_labels: mapping of preset code -> label
    - user_presets: optional custom presets:
        MY_PRESET = { label = "...", start = "YYYY-MM-DD", end = "YYYY-MM-DD" }

Session state keys:
- entries__period_preset is used to store the selected period preset
  (e.g. "FY", "CUSTOM"...).
- entries_p_start / entries_p_end are used to persist the CUSTOM date range
  without interfering with other pages.
- entries__code_filter is used for the code filter input.
- entries__description_contains is used for the description filter input.
- entries__amount_min / entries__amount_max are used for the amount filter inputs.
- entries__import_batch_id is used for the import batch dropdown.
- entries__show_unknown_only is used for the "Show unknown accounts only" toggle.
- entries__include_deleted is used for the "Include deleted" toggle.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

import streamlit as st

from smb_finsight.period_utils import CustomRange, period_from_preset
from smb_finsight.webui.period_ui import _validate_custom_range  # reuse behavior
from smb_finsight.webui.utils import _get, _to_mapping


@dataclass(frozen=True)
class PeriodFilterResult:
    """
    Structured output for period filter control.
    """

    period: Any
    period_preset: str
    period_label: str


def render_entries_period_filter(*, page: Any, app_config: Any) -> PeriodFilterResult:
    """
    Render the period selector for the Entries sub-view.

    Notes:
    - Uses controlled rendering (only this component is executed when the
      Entries sub-view is active).
    - Aligns CUSTOM range validation with other pages via _validate_custom_range().
    - Supports preset "ALL" (no time filtering) assuming period_from_preset()
      supports it. "ALL" is implemented as a very wide date range, so downstream
      code can keep using Period(start, end) without special-casing.
    """
    ui = _to_mapping(_get(page, "ui", {}))

    key = "entries__period_preset"
    periods_cfg = _to_mapping(_get(page, "periods", {}))

    preset_labels = _to_mapping(periods_cfg.get("primary_preset_labels", {}))

    # User presets from layout TOML (normalize keys to uppercase for compatibility).
    user_presets_raw = _to_mapping(periods_cfg.get("user_presets", {}))
    user_presets = {str(k).upper(): v for k, v in user_presets_raw.items()}

    # Precompute user preset display labels (prefer their explicit label if provided).
    user_preset_labels: dict[str, str] = {}
    for k, v in user_presets.items():
        tbl = v if isinstance(v, dict) else {}
        user_preset_labels[str(k).upper()] = str(tbl.get("label", k))

    def fmt(code: str) -> str:
        """Format preset codes to human-friendly labels."""
        c = str(code).upper()
        if c in user_preset_labels:
            return user_preset_labels[c]
        return str(preset_labels.get(c, c))

    default_period_preset = (periods_cfg.get("default_primary_preset") or "ALL").upper()

    # Built-in presets for Entries (includes ALL).
    builtin_period = ["ALL", "FY", "YTD", "MTD", "LAST_MONTH", "CUSTOM"]
    user_keys = [str(k).upper() for k in user_presets.keys()]
    period_options = builtin_period + user_keys

    today = date.today()
    fy = app_config.fiscal_year

    with st.container(border=True, height="stretch"):
        period_idx = (
            period_options.index(default_period_preset)
            if default_period_preset in period_options
            else 0
        )

        period_preset = st.selectbox(
            ui.get("filter_period", "Period"),
            options=period_options,
            index=period_idx,
            format_func=fmt,
            key=key,
            help=ui.get("help_period", "Select the period."),
        )

        period_custom_start: Optional[date] = None
        period_custom_end: Optional[date] = None

        if period_preset == "CUSTOM":
            # Dedicated keys for Entries to avoid interfering with other pages.
            if "entries_p_start" not in st.session_state:
                st.session_state["entries_p_start"] = fy.start_date
            if "entries_p_end" not in st.session_state:
                st.session_state["entries_p_end"] = min(fy.end_date, today)

            d1, d2 = st.columns(2)
            with d1:
                period_custom_start = st.date_input(
                    ui.get("label_custom_from", "From"),
                    key="entries_p_start",
                )
            with d2:
                period_custom_end = st.date_input(
                    ui.get("label_custom_to", "To"),
                    key="entries_p_end",
                )

    # Build the Period exactly like period_ui.py does
    # (CUSTOM uses _validate_custom_range)
    custom_range_error_msg = ui.get(
        "error_custom_end_before_start", "End date cannot be earlier than start date."
    )

    custom_period: Optional[CustomRange] = None
    if period_preset == "CUSTOM":
        if _validate_custom_range(
            period_custom_start,
            period_custom_end,
            toast=True,
            error_message=custom_range_error_msg,
        ):
            custom_period = CustomRange(period_custom_start, period_custom_end)

    # Centralized period computation (includes user presets).
    period = period_from_preset(
        period_preset,
        fy,
        custom=custom_period,
        label="PERIOD",
        user_presets=user_presets,
    )

    return PeriodFilterResult(
        period=period,
        period_preset=period_preset,
        period_label=fmt(period_preset),
    )


def _parse_code_pattern(raw: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse a code filter expression.

    Rules:
    - "606"  -> exact match (code_exact="606")
    - "606*" -> prefix match (code_prefix="606")
    - ""     -> no filter

    Notes:
    - Whitespace is trimmed.
    - Multiple trailing '*' are collapsed to a single '*'.
    - '*' alone is treated as empty (no filter).
    """
    s = (raw or "").strip()
    if not s:
        return None, None

    # Collapse multiple trailing stars: "606**" -> "606*"
    while s.endswith("**"):
        s = s[:-1]

    if s == "*":
        return None, None

    if s.endswith("*"):
        prefix = s[:-1].strip()
        return (None, prefix or None)

    return (s, None)


def render_entries_code_filter(*, page: Any) -> tuple[Optional[str], Optional[str]]:
    """
    Render the Account code filter (single input with '*' wildcard suffix).

    Layout expectations (layout_en.toml) under [pages.entries.ui]:
    - filter_code: main label
    - help_filter_code: help tooltip explaining "606" vs "606*"
    - placeholder_filter_code: placeholder text

    Returns:
        (code_exact, code_prefix)
        Exactly one of them is set (other is None), or both are None if filter is empty.

    Notes:
    1) SQL service layer will apply filtering logic (exact vs LIKE).
    2) We allow a single trailing '*' as a wildcard for prefix matching.
       Multiple trailing '*' are collapsed to one, and a single '*' is treated as empty.
    3) We trim whitespace, but we don't enforce strict patterns (e.g. "60 6*" is
       accepted but may yield no results). We just warn about unusual characters.
    4) The code filter is stored in session state under "entries__code_filter" for
       potential future use (e.g. pre-filling the input, or passing to other
       components).
    """
    ui = _to_mapping(_get(page, "ui", {}))

    key = "entries__code_filter"

    label = ui.get("filter_code", "Account code")
    help_text = ui.get(
        "help_filter_code",
        'Type an account code (e.g. "606") or use "*" for prefix (e.g. "606*").',
    )
    placeholder = ui.get("placeholder_filter_code", "e.g. 606 or 606*")

    with st.container(border=True, height="stretch"):
        code_raw = st.text_input(
            label,
            key=key,
            placeholder=placeholder,
            help=help_text,
        )

    if code_raw and not re.fullmatch(r"[A-Za-z0-9_.-]+\*?", code_raw.strip()):
        st.warning(
            "Code filter contains unusual characters; results may be unexpected."
        )

    return _parse_code_pattern(code_raw)


def render_entries_description_filter(*, page: Any) -> str:
    """
    Render the "Description contains" filter for the Entries view.

    Layout expectations (layout_en.toml) under [pages.entries.ui]:
    - filter_description: label for the text input
    - help_filter_description: optional tooltip
    - placeholder_filter_description: optional placeholder text

    Returns:
        A trimmed string. Empty string means "no filter".

    Notes:
        The DB/service layer should apply this as a "contains" filter
        (e.g. LIKE '%...%'), ideally case-insensitive depending on
        the chosen SQL collation strategy.
    """
    ui = _to_mapping(_get(page, "ui", {}))

    key = "entries__description_contains"

    label = ui.get("filter_description", "Description contains")
    help_text = ui.get("help_filter_description", None)
    placeholder = ui.get("placeholder_filter_description", "e.g. rent, invoice, amazon")

    with st.container(border=True, height="stretch"):
        value = st.text_input(
            label,
            key=key,
            help=help_text,
            placeholder=placeholder,
        )

    return (value or "").strip()


def render_entries_amount_filter(*, page: Any) -> tuple[Optional[int], Optional[int]]:
    """
    Render the Amount min/max filter for the Entries view.

    Layout expectations (layout_en.toml) under [pages.entries.ui]:
    - filter_amount_min: label for the minimum amount input
    - filter_amount_max: label for the maximum amount input
    - help_filter_amount: optional tooltip for the container
    - placeholder_filter_amount_min / placeholder_filter_amount_max: optional
      placeholders
    - warning_amount_min_gt_max: warning message shown when minimum value is
      greater than maximum value

    Returns:
        (amount_min_cents, amount_max_cents)
        - Values are returned as integer cents.
        - None means no bound.
    """
    ui = _to_mapping(_get(page, "ui", {}))

    with st.container(border=True, height="stretch"):
        # c1, c2 = st.columns(2)

        # with c1:
        amount_min = st.number_input(
            ui.get("filter_amount_min", "Min"),
            value=None,
            step=0.01,
            format="%.2f",
            placeholder=ui.get("placeholder_filter_amount_min", None),
            help=ui.get("help_filter_amount", None),
            key="entries__amount_min",
        )

        # with c2:
        amount_max = st.number_input(
            ui.get("filter_amount_max", "Max"),
            value=None,
            step=0.01,
            format="%.2f",
            placeholder=ui.get("placeholder_filter_amount_max", None),
            help=ui.get("help_filter_amount", None),
            key="entries__amount_max",
        )

    # Convert to cents
    min_cents = int(round(amount_min * 100)) if amount_min is not None else None
    max_cents = int(round(amount_max * 100)) if amount_max is not None else None

    # Optional logical validation
    if min_cents is not None and max_cents is not None and min_cents > max_cents:
        st.warning(
            ui.get(
                "warning_amount_min_gt_max",
                "Min amount cannot be greater than max amount.",
            )
        )
        max_cents = None

    return min_cents, max_cents


def render_entries_batch_filter(
    *, page: Any, batch_options: list[tuple[int, str]]
) -> Optional[int]:
    """
    Render the Import Batch filter (dropdown) for the Entries view.

    Layout expectations (layout_en.toml) under [pages.entries.ui]:
    - filter_import_batch: label for the dropdown
    - help_filter_import_batch: optional tooltip
    - option_import_batch_all: label for the "All batches" option

    Args:
        batch_options:
            List of (batch_id, display_label). The caller decides how to build
            display_label (e.g., notes if present, else created_at).

    Returns:
        Selected import_batch_id (int) or None if "All batches" is selected.
    """
    ui = _to_mapping(_get(page, "ui", {}))

    key = "entries__import_batch_id"

    label = ui.get("filter_import_batch", "Import batch")
    help_text = ui.get("help_filter_import_batch", None)
    opt_all = ui.get("option_import_batch_all", "All batches")

    # Streamlit selectbox options: first entry is None meaning "All".
    ids: list[Optional[int]] = [None] + [bid for (bid, _) in batch_options]

    # Map id -> label for formatting
    label_map: dict[Optional[int], str] = {None: opt_all}
    for bid, blabel in batch_options:
        label_map[bid] = blabel

    def fmt(value: Optional[int]) -> str:
        return label_map.get(value, str(value))

    with st.container(border=True, height="stretch"):
        selected = st.selectbox(
            label,
            options=ids,
            key=key,
            format_func=fmt,
            help=help_text,
        )

    return selected


def render_entries_toggles_and_badge(
    *,
    page: Any,
    unknown_count: Optional[int] = None,
) -> tuple[bool, bool]:
    """
    Render the right-side controls for the Entries header:
    - an "Unknown accounts detected" badge (optional)
    - two toggles (v0.5.0):
        1) Show unknown accounts only
        2) Include deleted entries

    Layout expectations (layout_en.toml) under [pages.entries.ui]:
    - badge_unknown_accounts: badge text prefix (e.g. "Unknown accounts detected")
    - toggle_unknown_only: label for toggle #1
    - help_toggle_unknown_only: optional tooltip for toggle #1
    - toggle_include_deleted: label for toggle #2
    - help_toggle_include_deleted: optional tooltip for toggle #2

    Args:
        unknown_count:
            If provided, the badge is displayed with this count.
            If None, the badge is not displayed (caller may not have computed it yet).

    Returns:
        (show_unknown_only, include_deleted)

    Notes:
        - Both toggles persist via widget keys.
        - This renderer does NOT compute unknown_count: it only displays it.
    """
    ui = _to_mapping(_get(page, "ui", {}))

    key_unknown_only = "entries__show_unknown_only"
    key_include_deleted = "entries__include_deleted"

    label_unknown_only = ui.get("toggle_unknown_only", "Show unknown accounts only")
    help_unknown_only = ui.get("help_toggle_unknown_only", None)

    label_include_deleted = ui.get("toggle_include_deleted", "Include deleted")
    help_include_deleted = ui.get("help_toggle_include_deleted", None)

    badge_prefix = ui.get("badge_unknown_accounts", "Unknown accounts detected")

    with st.container(border=True, height="stretch"):
        # Badge (optional): show only when the caller has a meaningful count.
        if unknown_count is not None:
            badge_text = f"{badge_prefix}: {int(unknown_count)}"
            if hasattr(st, "badge"):
                st.badge(badge_text)
            else:
                # Fallback for older Streamlit versions
                st.caption(badge_text)

        # Two compact toggles stacked vertically.
        show_unknown_only = st.toggle(
            label_unknown_only,
            key=key_unknown_only,
            help=help_unknown_only,
        )
        include_deleted = st.toggle(
            label_include_deleted,
            key=key_include_deleted,
            help=help_include_deleted,
        )

    return show_unknown_only, include_deleted
