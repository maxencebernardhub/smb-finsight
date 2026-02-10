# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Entries sub-view renderer (WebUI).

This module contains the rendering logic for the "Entries" sub-view of the
Entries page. It is intentionally separated from the page orchestrator to keep
the main entries page file thin and reduce regression risk.

Responsibilities:
- Render filter controls (period/code/description/amount/import batch/toggles).
- Build an EntriesFilter and query the DB via the service layer.
- Optionally compute "unknown accounts" (based on the chart of accounts).
- Render the entries table (data_editor) and an actions placeholder.

Notes:
- The page uses controlled navigation (segmented control / pills), so this
  renderer only runs when the active sub-view is "entries".
- Widget session_state may be cleared when the sub-view is not rendered
  (Streamlit "stale widget" cleanup). This is expected with controlled rendering.


"""

# SMB FinSight - Entries subview renderer (WebUI)

from typing import Any

import streamlit as st

from smb_finsight.accounts import (
    load_list_of_accounts,
    split_known_and_unknown_accounts,
)
from smb_finsight.config import AppConfig
from smb_finsight.db import EntriesFilter
from smb_finsight.entries_service import list_import_batches, search_entries
from smb_finsight.webui.components.entries_filters import (
    render_entries_amount_filter,
    render_entries_batch_filter,
    render_entries_code_filter,
    render_entries_description_filter,
    render_entries_period_filter,
    render_entries_toggles_and_badge,
)
from smb_finsight.webui.layout import LayoutConfig, PageConfig


def render_entries_subview(
    *,
    app_config: AppConfig,
    layout: LayoutConfig,
    page: PageConfig,
    ui: dict[str, Any],
) -> None:
    """
    Render the "Entries" sub-view.

    Args:
        app_config: Global application configuration (DB path, standard config, etc.).
        layout: Layout configuration (used for pagination caps and future UI rules).
        page: Entries page configuration node (labels, period presets, defaults).
        ui: UI labels dictionary (typically derived from page.ui).

    Behavior:
        - Renders filters and toggles in a 6-column header layout.
        - Queries entries with a soft max display limit
          (layout.entries.pagination.max_limit).
        - Computes unknown accounts when a chart of accounts is configured.
        - Renders a read-only table with a selectable checkbox column to prepare
          upcoming row-level actions (Edit/Delete/Restore via dialogs).
    """

    # Reserve future columns for additional filters (code/desc/amount/batch/toggles)
    c1, c2, c3, c4, c5, c6 = st.columns([1.0, 0.7, 0.9, 0.9, 0.8, 1.0])

    # Read current toggle values from session_state BEFORE rendering widgets.
    # This allows us to:
    # - use include_deleted in the DB query,
    # - compute unknown_count and show the badge in the same rerun.
    show_unknown_only_state = bool(
        st.session_state.get("entries__show_unknown_only", False)
    )
    include_deleted_state = bool(
        st.session_state.get("entries__include_deleted", False)
    )

    with c1:
        period_filter = render_entries_period_filter(page=page, app_config=app_config)

    selected_period_label = ui.get("filter_period", "Selected period")
    period_filter_result = str(
        f"[{selected_period_label}: "
        f"{period_filter.period.start} – {period_filter.period.end}] "
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
        # display in dollars for readability
        def _fmt_cents(x: int) -> str:
            return f"{x / 100:.2f}"

        left = _fmt_cents(amount_min_cents) if amount_min_cents is not None else "∅"
        right = _fmt_cents(amount_max_cents) if amount_max_cents is not None else "∅"
        amount_filter_result = f"[{filter_amount_label}: {left} .. {right}] "

    # -----------------------------------------------------------------
    # Import batch dropdown options.
    # UX rule (agreed spec):
    # - Show import_batches.notes when present (human-friendly label),
    # - else fall back to created_at (timestamp).
    # -----------------------------------------------------------------
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
            page=page,
            batch_options=batch_options,
        )

    filter_batch_label = ui.get("filter_import_batch", "Import batch")

    if import_batch_id is None:
        batch_filter_result = ""
    else:
        # Display the selected batch label (notes or created_at fallback).
        batch_label_map = {bid: blabel for bid, blabel in batch_options}
        batch_display = batch_label_map.get(import_batch_id, str(import_batch_id))
        batch_filter_result = f"[{filter_batch_label}: {batch_display}] "

    # -----------------------------------------------------------------
    # Build DB filter (EntriesFilter) from UI controls.
    # Note: EntriesFilter.min_amount/max_amount are in monetary units (float),
    # while our UI amount filter returns cents (int).
    # -----------------------------------------------------------------
    filters = EntriesFilter(
        start=period_filter.period.start,
        end=period_filter.period.end,
        code_exact=code_exact,
        code_prefix=code_prefix,
        description_contains=description_contains or None,
        min_amount=(amount_min_cents / 100.0) if amount_min_cents is not None else None,
        max_amount=(amount_max_cents / 100.0) if amount_max_cents is not None else None,
        import_batch_id=import_batch_id,
        include_deleted=include_deleted_state,
        deleted_only=False,  # Recycle bin sub-view will use
        # deleted_only=True later.
    )

    # Soft display cap (Option B): we fetch up to max_limit rows.
    # If the result count reaches the cap, we warn the user to narrow filters.
    max_limit = int(getattr(layout.entries.pagination, "max_limit", 2000))
    if max_limit <= 0:
        max_limit = 2000

    # -----------------------------------------------------------------
    # Query the DB via service layer.
    # For now, keep a conservative limit; pagination will come later.
    # -----------------------------------------------------------------
    df = search_entries(
        app_config,
        filters,
        limit=max_limit + 1,
        offset=0,
        order_by=("date", "ASC"),
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

    # -----------------------------------------------------------------
    # Unknown accounts detection (prefix matching) using the chart of accounts.
    # If no chart_of_accounts is configured, unknown_count stays None and the
    # "unknown only" toggle has no effect.
    # -----------------------------------------------------------------
    unknown_count: int | None = None
    df_unknown = None  # lazy: only set if COA is available

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
        except Exception as exc:
            # UI should not crash if the COA file is missing/malformed.
            st.warning(f"Could not compute unknown accounts: {exc}")

    # Apply "unknown only" post-filtering (when available)
    if show_unknown_only_state and df_unknown is not None:
        df = df_unknown

    with c6:
        # Now that we have queried the DB, we can display the badge count.
        show_unknown_only, include_deleted = render_entries_toggles_and_badge(
            page=page,
            unknown_count=unknown_count,
        )

    toggles_filter_result = (
        f"[Unknown only: {show_unknown_only}] [Include deleted: {include_deleted}] "
    )

    result_info = f"==> Rows: {len(df)} "

    st.info(
        f"Applied filters:    {period_filter_result}{code_filter_result}"
        f"{description_filter_result}{amount_filter_result}"
        f"{batch_filter_result}{toggles_filter_result}{result_info}"
    )

    # ------------------------------------------------------------
    # Build a display dataframe (subset + derived columns + labels)
    # ------------------------------------------------------------
    df_view = df.copy()

    # Build a batch label column from import_batches:
    # - use notes when present,
    # - else fallback to created_at
    batch_label_map: dict[int, str] = {}
    if batch_options:
        # batch_options already follow the rule notes else created_at
        # (built earlier)
        batch_label_map = {bid: blabel for bid, blabel in batch_options}

    if "import_batch_id" in df_view.columns:
        df_view["batch"] = df_view["import_batch_id"].map(batch_label_map)

        # If mapping missing (rare), fallback to id as string
        df_view["batch"] = df_view["batch"].fillna(
            df_view["import_batch_id"].astype(str)
        )

    # Columns to display (in order)
    display_cols = [
        "id",
        "date",
        "code",
        "description",
        "amount",
        "batch",
        "updated_at",
    ]
    display_cols = [c for c in display_cols if c in df_view.columns]
    df_view = df_view[display_cols]

    # Insert a selection checkbox column (read/write).
    # This prepares row-level actions (Edit/Delete/Restore) for the next steps.
    df_view.insert(0, "_selected", False)

    colcfg = {}

    # Use DB id as index (hidden) so we can map selected rows back to entries later.
    if "id" in df_view.columns:
        df_view = df_view.set_index("id")

    if "_selected" in df_view.columns:
        colcfg["_selected"] = st.column_config.CheckboxColumn(
            label="",
            help=ui.get("help_select_column", "Select one or more rows for actions."),
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

    # -----------------------------------------------------------------
    # Table area (left) + actions placeholder (right)
    # -----------------------------------------------------------------
    table_col, actions_col = st.columns([5.5, 0.5], vertical_alignment="top")

    with table_col:
        st.data_editor(
            df_view,
            hide_index=True,
            width="stretch",
            disabled=[c for c in df_view.columns if c != "_selected"],
            column_config=colcfg,
            key="entries__table_editor",
        )

    with actions_col:
        # Placeholder for future action buttons (Edit/Delete/Restore, etc.)
        st.subheader("Actions")
        st.caption("Actions will be added in the next steps.")

    return
