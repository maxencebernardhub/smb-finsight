# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Recycle bin sub-view renderer (WebUI).

This module contains the rendering logic for the "Recycle bin" sub-view of the
Entries page. It is intentionally similar to entries_subview.py to minimize
regression risk and keep behavior consistent across sub-views.

Differences vs. Entries sub-view:
- The "Include deleted entries" toggle is not displayed (Recycle bin only).
- The DB query returns only deleted entries (EntriesFilter.deleted_only=True).
- The table shows extra columns: deleted_at, deleted_reason.
- The Actions panel exposes a single button: "Restore", which opens a dialog
  to confirm restoration of the selected entries.

Notes:
- We reuse the same filters (period/code/description/amount/import batch).
- Unknown accounts detection remains available (optional) if a chart of accounts
  is configured for the current standard.

"""

# SMB FinSight - Recycle bin subview renderer (WebUI)

from typing import Any, Optional

import streamlit as st

from smb_finsight.accounts import (
    load_list_of_accounts,
    split_known_and_unknown_accounts,
)
from smb_finsight.config import AppConfig
from smb_finsight.db import EntriesFilter
from smb_finsight.entries_service import list_import_batches, search_entries
from smb_finsight.webui.components.entries_entry_dialog import (
    confirm_restore_entries_dialog,
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


def __render_unknown_toggle_and_badge(
    *,
    page: Any,
    unknown_count: Optional[int] = None,
) -> bool:
    """
    Render the right-side controls for the Recycle Bin header:
    - an "Unknown accounts detected" badge (optional)
    - one toggle (Recycle Bin):
        1) Show unknown accounts only

    This function intentionally mirrors
    entries_filters.render_entries_toggles_and_badge() as closely as possible,
    except it does NOT render the "Include deleted entries" toggle
    (Recycle Bin is deleted-only by design).

    Layout expectations (layout_en.toml) under [pages.entries.ui]:
    - badge_unknown_accounts: badge text prefix (e.g. "Unknown accounts detected")
    - toggle_unknown_only: label for toggle
    - help_toggle_unknown_only: optional tooltip for toggle

    Args:
        unknown_count:
            If provided, the badge is displayed with this count.
            If None, the badge is not displayed (caller may not have computed it yet).

    Returns:
        show_unknown_only (bool)

    Notes:
        - The toggle persists via widget key "entries__show_unknown_only".
        - This renderer does NOT compute unknown_count: it only displays it.
    """
    ui = _to_mapping(_get(page, "ui", {}))

    key_unknown_only = "entries__show_unknown_only"

    label_unknown_only = ui.get("toggle_unknown_only", "Show unknown accounts only")
    help_unknown_only = ui.get("help_toggle_unknown_only", None)

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

        # One compact toggle stacked vertically (same style as Entries).
        show_unknown_only = st.toggle(
            label_unknown_only,
            key=key_unknown_only,
            help=help_unknown_only,
        )

    return bool(show_unknown_only)


def render_recycle_bin_subview(
    *,
    app_config: AppConfig,
    layout: LayoutConfig,
    page: PageConfig,
    ui: dict[str, Any],
) -> None:
    """
    Render the "Recycle bin" sub-view.

    Behavior:
        - Renders filters in a 6-column header layout (same as Entries),
          but only renders the "unknown only" toggle in column 6.
        - Queries entries with deleted_only=True and a soft max display limit.
        - Computes unknown accounts when chart_of_accounts is configured.
        - Renders a read-only table with a selectable checkbox column.
        - Provides a single action: Restore (disabled if no rows selected).
    """
    flash = st.session_state.pop("entries__flash", None)
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

    # Read current toggle state BEFORE rendering widgets
    show_unknown_only_state = bool(
        st.session_state.get("entries__show_unknown_only", False)
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
        amount_filter_result = ""
    else:

        def _fmt_cents(x: int) -> str:
            return f"{x / 100:.2f}"

        left = _fmt_cents(amount_min_cents) if amount_min_cents is not None else "∅"
        right = _fmt_cents(amount_max_cents) if amount_max_cents is not None else "∅"
        amount_filter_result = f"[{filter_amount_label}: {left} .. {right}] "

    # Import batches dropdown options (same UX rule as Entries)
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

    # Build DB filter: deleted-only
    filters = EntriesFilter(
        start=period_filter.period.start,
        end=period_filter.period.end,
        code_exact=code_exact,
        code_prefix=code_prefix,
        description_contains=description_contains or None,
        min_amount=(amount_min_cents / 100.0) if amount_min_cents is not None else None,
        max_amount=(amount_max_cents / 100.0) if amount_max_cents is not None else None,
        import_batch_id=import_batch_id,
        include_deleted=True,  # harmless, deleted_only takes precedence
        deleted_only=True,  # recycle bin = only deleted entries
    )

    max_limit = int(getattr(layout.entries.pagination, "max_limit", 2000))
    if max_limit <= 0:
        max_limit = 2000

    df = search_entries(
        app_config,
        filters,
        limit=max_limit + 1,
        offset=0,
        order_by=("deleted_at", "DESC"),
    )

    too_many_rows = len(df) > max_limit
    if too_many_rows:
        df = df.iloc[:max_limit].copy()
        st.warning(
            ui.get(
                "warning_max_limit",
                "Results exceed the display limit. Please narrow your filters.",
            )
        )

    # Unknown accounts detection (optional)
    unknown_count: int | None = None
    df_unknown = None

    coa_path = getattr(
        getattr(app_config, "standard_config", None), "chart_of_accounts", None
    )
    if coa_path and not df.empty:
        try:
            coa_df = load_list_of_accounts(str(coa_path))
            known_codes = set(coa_df["account_number"].astype(str).str.strip())
            _, unknown_df = split_known_and_unknown_accounts(df, known_codes)

            unknown_count = int(len(unknown_df))
            df_unknown = unknown_df
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Could not compute unknown accounts: {exc}")

    if show_unknown_only_state and df_unknown is not None:
        df = df_unknown

    with c6:
        show_unknown_only = __render_unknown_toggle_and_badge(
            page=page, unknown_count=unknown_count
        )

    toggles_filter_result = f"[Unknown only: {show_unknown_only}] "
    result_info = f"==> Rows: {len(df)} "

    st.info(
        f"Applied filters:    {period_filter_result}{code_filter_result}"
        f"{description_filter_result}{amount_filter_result}"
        f"{batch_filter_result}{toggles_filter_result}{result_info}"
    )

    # Display dataframe
    df_view = df.copy()

    batch_label_map: dict[int, str] = (
        {bid: blabel for bid, blabel in batch_options} if batch_options else {}
    )
    if "import_batch_id" in df_view.columns:
        df_view["batch"] = df_view["import_batch_id"].map(batch_label_map)
        df_view["batch"] = df_view["batch"].fillna(
            df_view["import_batch_id"].astype(str)
        )

    # Columns to display (Recycle bin adds deleted_at + deleted_reason)
    display_cols = [
        "id",
        "date",
        "code",
        "description",
        "amount",
        "batch",
        "updated_at",
        "deleted_at",
        "deleted_reason",
    ]
    display_cols = [c for c in display_cols if c in df_view.columns]
    df_view = df_view[display_cols]

    df_view.insert(0, "_selected", False)

    # Use DB id as index (hidden)
    if "id" in df_view.columns:
        df_view = df_view.set_index("id")

    colcfg: dict[str, Any] = {}

    colcfg["_selected"] = st.column_config.CheckboxColumn(
        label="",
        help=ui.get("help_selected_column", "Select one or more rows for actions."),
    )

    if "date" in df_view.columns:
        colcfg["date"] = st.column_config.DateColumn(
            label=ui.get("column_date", "Date"),
            format="YYYY-MM-DD",
        )
    if "code" in df_view.columns:
        colcfg["code"] = st.column_config.TextColumn(
            label=ui.get("column_code", "Account code"),
        )
    if "description" in df_view.columns:
        colcfg["description"] = st.column_config.TextColumn(
            label=ui.get("column_description", "Description"),
        )
    if "amount" in df_view.columns:
        colcfg["amount"] = st.column_config.NumberColumn(
            label=ui.get("column_amount", "Amount"),
            format="%.2f",
        )
    if "batch" in df_view.columns:
        colcfg["batch"] = st.column_config.TextColumn(
            label=ui.get("column_import_batch", "Import batch"),
        )
    if "updated_at" in df_view.columns:
        colcfg["updated_at"] = st.column_config.DatetimeColumn(
            label=ui.get("column_updated_at", "Last updated"),
            format="YYYY-MM-DD HH:mm",
        )
    if "deleted_at" in df_view.columns:
        colcfg["deleted_at"] = st.column_config.DatetimeColumn(
            label=ui.get("column_deleted_at", "Deleted at"),
            format="YYYY-MM-DD HH:mm",
        )
    if "deleted_reason" in df_view.columns:
        colcfg["deleted_reason"] = st.column_config.TextColumn(
            label=ui.get("column_deleted_reason", "Deletion reason"),
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
            key="entries__recycle_bin_table_editor",
        )

    with actions_col:
        selected_ids: list[int] = []
        if edited_df_view is not None and "_selected" in edited_df_view.columns:
            selected_ids = edited_df_view.index[edited_df_view["_selected"]].tolist()

        restore_disabled = len(selected_ids) == 0

        if st.button(
            ui.get("button_restore", "Restore"),
            disabled=restore_disabled,
            type="primary",
            width="stretch",
        ):
            confirm_restore_entries_dialog(
                app_config=app_config,
                ui=ui,
                entry_ids=[int(x) for x in selected_ids],
            )

    return
