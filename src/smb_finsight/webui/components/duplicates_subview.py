# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Duplicates sub-view renderer (WebUI).

This module renders the "Duplicates" sub-view on the Entries page.

Main responsibilities
---------------------
- Render the shared Entries filters (period, code, description, amount, import batch).
- Add Duplicates-specific controls:
  - resolution status pills (Pending / Kept / Discarded, deselect => All),
  - "Unknown accounts only" toggle with a badge showing the number of unknown
    accounts among currently displayed duplicates.
- Query duplicates from the database (filters applied at SQL level via
  entries_service.list_duplicate_pairs()).
- Provide an action panel:
  - View details (enabled only when exactly one row is selected),
  - Keep / Discard (enabled when at least one row is selected),
    with a pre-check to prevent resolving already-resolved duplicates.

Notes
-----
- The resolution status pills are implemented with a single source of truth in
  st.session_state to avoid one-rerun lag issues
  (see _render_duplicates_toggles_and_pills()).
- Unknown accounts badge requires the query result set to compute unknown_count,
  therefore the badge is rendered after the query.

"""

from dataclasses import asdict
from typing import Any, Optional

import pandas as pd
import streamlit as st

from smb_finsight.accounts import (
    load_list_of_accounts,
    split_known_and_unknown_accounts,
)
from smb_finsight.config import AppConfig
from smb_finsight.entries_service import list_duplicate_pairs, list_import_batches
from smb_finsight.webui.components.duplicates_dialog import (
    confirm_resolve_duplicates_dialog,
    view_duplicate_details_dialog,
)
from smb_finsight.webui.components.entries_filters import (
    render_entries_amount_filter,
    render_entries_batch_filter,
    render_entries_code_filter,
    render_entries_description_filter,
    render_entries_period_filter,
)
from smb_finsight.webui.layout import LayoutConfig, PageConfig
from smb_finsight.webui.utils import _get, _to_mapping

FLASH_KEY = "entries__flash"


def _status_labels(ui: dict[str, Any]) -> dict[str, str]:
    """Return display labels for resolution statuses from UI layout config."""
    return {
        "pending": str(ui.get("resolution_status_pending", "Pending")),
        "kept": str(ui.get("resolution_status_kept", "Kept")),
        "discarded": str(ui.get("resolution_status_discarded", "Discarded")),
    }


def _render_duplicates_toggles_and_pills(
    *,
    page: Any,
    unknown_count: Optional[int] = None,
) -> tuple[bool, Optional[str]]:
    """
    Render the "Unknown only" toggle + resolution status pills.

    IMPORTANT:
    - The pills widget stores its selected value directly in session_state,
      so we must use a single, stable key shared by both:
        (a) the widget and (b) the query logic.
    - Pills can be deselected => selected value can be None.
      In that case, we return status=None meaning "no status filter".
    """

    ui = _to_mapping(_get(page, "ui", {}))

    key_unknown_only = "duplicates__show_unknown_only"
    key_status_label = "duplicates__resolution_status_label"  # single source of truth

    label_unknown_only = ui.get("toggle_unknown_only", "Show unknown accounts only")
    help_unknown_only = ui.get("help_toggle_unknown_only", None)
    badge_prefix = ui.get("badge_unknown_accounts", "Unknown accounts detected")

    filter_status_label = ui.get("filter_resolution_status", "Resolution status")
    labels = _status_labels(ui)  # {"pending": "...", "kept": "...", "discarded": "..."}

    options = [labels["pending"], labels["kept"], labels["discarded"]]
    label_to_status = {
        labels["pending"]: "pending",
        labels["kept"]: "kept",
        labels["discarded"]: "discarded",
    }

    # We set the initial value in session_state (instead of using pills "default=")
    # because session_state is the single source of truth for both the widget and
    # the DB query logic, preventing one-rerun lag.

    # Default selected pill on first load: Pending
    if key_status_label not in st.session_state:
        st.session_state[key_status_label] = labels["pending"]

    with st.container(border=True, height="stretch"):
        if unknown_count is not None:
            badge_text = f"{badge_prefix}: {int(unknown_count)}"
            if hasattr(st, "badge"):
                st.badge(badge_text)
            else:
                st.caption(badge_text)

        show_unknown_only = st.toggle(
            label_unknown_only,
            key=key_unknown_only,
            help=help_unknown_only,
        )

        if hasattr(st, "pills"):
            selected_label = st.pills(
                filter_status_label,
                options=options,
                key=key_status_label,
            )
        else:
            # selectbox fallback can't be empty; keep one selected
            idx = options.index(st.session_state[key_status_label])
            selected_label = st.selectbox(
                filter_status_label,
                options=options,
                index=idx,
                key=key_status_label,
            )

    # Pills can be deselected -> None => no filter
    if selected_label is None:
        return bool(show_unknown_only), None

    return bool(show_unknown_only), label_to_status.get(str(selected_label), "pending")


def render_duplicates_subview(
    *,
    app_config: AppConfig,
    layout: LayoutConfig,
    page: PageConfig,
    ui: dict[str, Any],
) -> None:
    """Render the Duplicates sub-view.

    This view is similar to Recycle Bin but operates on the duplicate_entries
    table and adds resolution workflow (keep/discard) and a details dialog.

    The main data query is executed via entries_service.list_duplicate_pairs()
    with filters applied at SQL level.
    """
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        level, msg = flash
        if level == "success":
            st.success(msg)
            st.toast(msg, icon="✅")
            st.balloons()
        elif level == "warning":
            st.warning(msg)
            st.toast(msg, icon="⚠️")
        else:
            st.info(msg)
            st.toast(msg, icon="ℹ️")

    c1, c2, c3, c4, c5, c6 = st.columns([1.0, 0.7, 0.9, 0.9, 0.8, 1.0])

    show_unknown_only_state = bool(
        st.session_state.get("duplicates__show_unknown_only", False)
    )

    with c1:
        period_filter = render_entries_period_filter(page=page, app_config=app_config)

    selected_period_label = ui.get("filter_period", "Selected period")
    period_filter_result = str(
        f"[{selected_period_label}: {period_filter.period.start} "
        f"– {period_filter.period.end}] "
    )

    with c2:
        code_exact, code_prefix = render_entries_code_filter(page=page)

    filter_code_label = ui.get("filter_code", "Code filter")
    code_filter_result = (
        f"[{filter_code_label}: {code_exact}] "
        if code_exact
        else f"[{filter_code_label}: {code_prefix}*] "
        if code_prefix
        else ""
    )

    with c3:
        description_contains = render_entries_description_filter(page=page)

    filter_description_label = ui.get("filter_description", "Description contains")
    description_filter_result = (
        f"[{filter_description_label}: {description_contains}] "
        if description_contains
        else ""
    )

    with c4:
        amount_min_cents, amount_max_cents = render_entries_amount_filter(page=page)

    filter_amount_label = ui.get("filter_amount", "Amount")
    if amount_min_cents is None and amount_max_cents is None:
        min_amount = None
        max_amount = None
        amount_filter_result = ""
    else:
        min_amount = (
            (amount_min_cents / 100.0) if amount_min_cents is not None else None
        )
        max_amount = (
            (amount_max_cents / 100.0) if amount_max_cents is not None else None
        )

        def _fmt_cents(x: int) -> str:
            return f"{x / 100:.2f}"

        left = _fmt_cents(amount_min_cents) if amount_min_cents is not None else "∅"
        right = _fmt_cents(amount_max_cents) if amount_max_cents is not None else "∅"
        amount_filter_result = f"[{filter_amount_label}: {left} .. {right}] "

    batches_df = list_import_batches(app_config, limit=200)
    batch_options: list[tuple[int, str]] = []
    if not batches_df.empty:
        for row in batches_df.itertuples(index=False):
            batch_id = int(row.id)
            notes = (getattr(row, "notes", "") or "").strip()
            created_at = getattr(row, "created_at", None)
            created_label = (
                created_at.strftime("%Y-%m-%d %H:%M")
                if hasattr(created_at, "strftime") and created_at is not None
                else str(created_at)
                if created_at is not None
                else ""
            )
            label = notes if notes else created_label
            batch_options.append((batch_id, label))

    with c5:
        import_batch_id = render_entries_batch_filter(
            page=page, batch_options=batch_options
        )

    filter_batch_label = ui.get("filter_import_batch", "Import batch")
    if import_batch_id is None:
        batch_filter_result = ""
    else:
        batch_label_map = {bid: blabel for bid, blabel in batch_options}
        batch_display = batch_label_map.get(import_batch_id, str(import_batch_id))
        batch_filter_result = f"[{filter_batch_label}: {batch_display}] "

    max_limit = int(getattr(layout.entries.pagination, "max_limit", 2000)) or 2000

    # Resolution status is read from session_state BEFORE the DB query.
    # This avoids the classic Streamlit "one-rerun delay" when a widget writes to a
    # different key than the one used by the query logic.

    labels = _status_labels(ui)
    label_to_status = {
        labels["pending"]: "pending",
        labels["kept"]: "kept",
        labels["discarded"]: "discarded",
    }
    selected_label = st.session_state.get(
        "duplicates__resolution_status_label", labels["pending"]
    )
    status_for_query = (
        None
        if selected_label is None
        else label_to_status.get(selected_label, "pending")
    )

    pairs = list_duplicate_pairs(
        app_config,
        status=status_for_query,  # <-- uses None when pills are deselected
        import_batch_id=import_batch_id,
        code_exact=code_exact or None,
        code_prefix=code_prefix or None,
        description_contains=description_contains or None,
        min_amount=min_amount,
        max_amount=max_amount,
        period=period_filter.period,
        limit=max_limit + 1,
        offset=0,
    )

    rows: list[dict[str, Any]] = [asdict(p.duplicate) for p in pairs]
    df = pd.DataFrame(rows)

    if len(df) > max_limit:
        df = df.iloc[:max_limit].copy()
        st.warning(
            ui.get(
                "warning_max_limit", "Results exceed the display limit. Narrow filters."
            )
        )

    unknown_count: Optional[int] = None
    df_unknown: Optional[pd.DataFrame] = None
    coa_path = getattr(
        getattr(app_config, "standard_config", None), "chart_of_accounts", None
    )

    # If chart of accounts is configured, show the badge even when there are 0 rows.
    if coa_path:
        unknown_count = 0

    if coa_path and not df.empty:
        coa_df = load_list_of_accounts(str(coa_path))
        known_codes = set(coa_df["account_number"].astype(str).str.strip())
        _, unknown_df = split_known_and_unknown_accounts(df, known_codes)
        unknown_count = int(len(unknown_df))
        df_unknown = unknown_df

    if show_unknown_only_state and df_unknown is not None:
        df = df_unknown

    # We render the badge in c6 AFTER the query because unknown_count is computed
    # from the current result set (unknown accounts among displayed duplicates).

    with c6:
        show_unknown_only, resolution_status = _render_duplicates_toggles_and_pills(
            page=page,
            unknown_count=unknown_count,
        )

    toggle_filter_unknown_result = f"[Unknown only: {show_unknown_only}] "

    status_label = (
        ui.get("resolution_status_all", "All")
        if status_for_query is None
        else status_for_query
    )
    resolution_status_result = f"[Resolution status: {status_label}] "
    result_info = f"==> Rows: {len(df)} "

    st.info(
        f"Applied filters:    {period_filter_result}{code_filter_result}"
        f"{description_filter_result}{amount_filter_result}"
        f"{batch_filter_result}{toggle_filter_unknown_result}{resolution_status_result}{result_info}"
    )

    # if df.empty:
    #    st.caption(ui.get("duplicates_empty", "No duplicates match these filters."))
    #    return

    df_view = df.copy()
    batch_label_map = {bid: blabel for bid, blabel in batch_options}
    if "import_batch_id" in df_view.columns:
        df_view["batch"] = df_view["import_batch_id"].map(batch_label_map)
        df_view["batch"] = df_view["batch"].fillna(
            df_view["import_batch_id"].astype(str)
        )

    display_cols = [
        "id",
        "date",
        "code",
        "description",
        "amount",
        "batch",
        "imported_at",
        "resolution_at",
        "resolved_by",
        "resolution_comment",
    ]
    display_cols = [c for c in display_cols if c in df_view.columns]
    df_view = df_view[display_cols]

    df_view.insert(0, "_selected", False)
    if "id" in df_view.columns:
        df_view = df_view.set_index("id")

    colcfg: dict[str, Any] = {
        "_selected": st.column_config.CheckboxColumn(
            label="",
            help=ui.get("help_selected_column", "Select one or more rows for actions."),
        )
    }

    if "date" in df_view.columns:
        colcfg["date"] = st.column_config.DateColumn(
            label=ui.get("column_date", "Date"), format="YYYY-MM-DD"
        )
    if "code" in df_view.columns:
        colcfg["code"] = st.column_config.TextColumn(
            label=ui.get("column_code", "Account code")
        )
    if "description" in df_view.columns:
        colcfg["description"] = st.column_config.TextColumn(
            label=ui.get("column_description", "Description")
        )
    if "amount" in df_view.columns:
        colcfg["amount"] = st.column_config.NumberColumn(
            label=ui.get("column_amount", "Amount"), format="%.2f"
        )
    if "batch" in df_view.columns:
        colcfg["batch"] = st.column_config.TextColumn(
            label=ui.get("column_import_batch", "Import batch")
        )
    if "imported_at" in df_view.columns:
        colcfg["imported_at"] = st.column_config.DatetimeColumn(
            label=ui.get("column_imported_at", "Imported at"), format="YYYY-MM-DD HH:mm"
        )
    if "resolution_at" in df_view.columns:
        colcfg["resolution_at"] = st.column_config.DatetimeColumn(
            label=ui.get("resolution_at", "Resolved at"), format="YYYY-MM-DD HH:mm"
        )
    if "resolved_by" in df_view.columns:
        colcfg["resolved_by"] = st.column_config.TextColumn(
            label=ui.get("resolved_by", "Resolved by")
        )
    if "resolution_comment" in df_view.columns:
        colcfg["resolution_comment"] = st.column_config.TextColumn(
            label=ui.get("resolution_comment", "Resolution notes")
        )

    table_col, actions_col = st.columns([5.5, 0.5], vertical_alignment="top")

    with table_col:
        edited_df_view = st.data_editor(
            df_view,
            hide_index=True,
            width="stretch",
            height=700,
            disabled=[c for c in df_view.columns if c != "_selected"],
            column_config=colcfg,
            key="entries__duplicates_table_editor",
        )

    with actions_col:
        selected_ids: list[int] = []
        if edited_df_view is not None and "_selected" in edited_df_view.columns:
            selected_ids = edited_df_view.index[edited_df_view["_selected"]].tolist()

        status_by_id: dict[int, str] = {}
        if not df.empty and "id" in df.columns and "resolution_status" in df.columns:
            status_by_id = {
                int(row["id"]): str(row["resolution_status"] or "").strip().lower()
                for _, row in df[["id", "resolution_status"]].iterrows()
            }

        disabled_any = len(selected_ids) == 0
        disabled_details = len(selected_ids) != 1

        if st.button(
            ui.get("duplicate_button_view_details", "View details"),
            disabled=disabled_details,
            type="primary",
            width="stretch",
        ):
            view_duplicate_details_dialog(
                app_config=app_config, ui=ui, duplicate_id=int(selected_ids[0])
            )

        if st.button(
            ui.get("duplicate_button_keep", "Keep"),
            disabled=disabled_any,
            type="primary",
            width="stretch",
        ):
            # UX guard: prevent resolving duplicates twice (DB layer raises ValueError).
            # If any selected row is already resolved, we warn and do not open
            # the dialog.

            already_resolved = [
                i
                for i in selected_ids
                if status_by_id.get(int(i)) in {"kept", "discarded"}
            ]
            if already_resolved:
                msg = ui.get(
                    "duplicates_already_resolved_warning",
                    "At least one selected duplicate is already resolved "
                    "(kept/discarded). You cannot resolve duplicates twice.",
                )
                st.toast(msg, icon="⚠️")
            else:
                confirm_resolve_duplicates_dialog(
                    app_config=app_config,
                    ui=ui,
                    duplicate_ids=[int(x) for x in selected_ids],
                    decision="keep",
                )

        if st.button(
            ui.get("duplicate_button_discard", "Discard"),
            disabled=disabled_any,
            type="primary",
            width="stretch",
        ):
            already_resolved = [
                i
                for i in selected_ids
                if status_by_id.get(int(i)) in {"kept", "discarded"}
            ]
            if already_resolved:
                msg = ui.get(
                    "duplicates_already_resolved_warning",
                    "At least one selected duplicate is already resolved "
                    "(kept/discarded). You cannot resolve duplicates twice.",
                )
                st.toast(msg, icon="⚠️")
            else:
                confirm_resolve_duplicates_dialog(
                    app_config=app_config,
                    ui=ui,
                    duplicate_ids=[int(x) for x in selected_ids],
                    decision="discard",
                )
