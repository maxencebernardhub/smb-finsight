# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Entries page (WebUI).

Design goals (v0.5.0):
- Keep this module THIN: it orchestrates UI layout and delegates rendering to
  dedicated helpers/components (to minimize regression risk and keep the file
  readable).
- Use controlled navigation (segmented control / pills) instead of st.tabs()
  because Streamlit currently computes all tab contents on each rerun.

Initial scope in this file:
- Render the 4 controlled sub-views selector:
  - Entries
  - Import
  - Duplicates (N)
  - Recycle bin

Next iterations (to be added progressively):
- Entries table (read-only st.data_editor + selection)
- Add/Edit dialogs (form-based)
- Import workflow + import history
- Duplicates resolution dialogs
- Recycle bin restore workflow
"""

from typing import Any

import streamlit as st

from smb_finsight.config import AppConfig
from smb_finsight.entries_service import get_duplicate_stats, list_import_batches
from smb_finsight.webui.components.entries_filters import (
    render_entries_amount_filter,
    render_entries_batch_filter,
    render_entries_code_filter,
    render_entries_description_filter,
    render_entries_period_filter,
    render_entries_toggles_and_badge,
)
from smb_finsight.webui.layout import LayoutConfig, PageConfig
from smb_finsight.webui.utils import _get, _to_mapping

# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------


def _render_subview_selector(
    *,
    ui: dict[str, Any],
    duplicates_count: int,
) -> str:
    """
    Render the controlled "sub-view" selector for the Entries page.

    We intentionally avoid st.tabs() because Streamlit computes all tab content
    on each rerun (no conditional rendering). A segmented control (or pills)
    lets us execute ONLY the active sub-view code path.

    Returns:
        The selected sub-view key among:
        - "entries"
        - "import"
        - "duplicates"
        - "recycle_bin"
    """

    # Labels are configurable in layout_en.toml under [pages.entries.ui]
    label_entries = str(ui.get("subviews_entries", "Entries"))
    label_import = str(ui.get("subviews_import", "Import"))

    # Support a template label like "Duplicates ({count})"
    dup_tpl = str(ui.get("subviews_duplicates", "Duplicates ({count})"))
    label_duplicates = dup_tpl.format(count=duplicates_count)

    label_recycle = str(ui.get("subviews_recycle_bin", "Recycle bin"))

    options: list[tuple[str, str]] = [
        ("entries", label_entries),
        ("import", label_import),
        ("duplicates", label_duplicates),
        ("recycle_bin", label_recycle),
    ]

    # Store the selected sub-view in session_state for stability across reruns.
    state_key = "entries_active_subview"
    default_value = st.session_state.get(state_key, "entries")

    # Prefer segmented_control (best UX) then pills, then selectbox as a safe fallback.
    labels_only = [lbl for _, lbl in options]
    key_to_index = {k: i for i, (k, _) in enumerate(options)}
    default_index = key_to_index.get(default_value, 0)

    selected_label: str

    if hasattr(st, "segmented_control"):
        selected_label = st.segmented_control(
            label="Segmented control for Entries sub-views",
            options=labels_only,
            default=labels_only[default_index],
            key=f"{state_key}__seg",
            label_visibility="collapsed",
        )
    elif hasattr(st, "pills"):
        selected_label = st.pills(
            label="Pills for Entries sub-views",
            options=labels_only,
            default=labels_only[default_index],
            key=f"{state_key}__pills",
            label_visibility="collapsed",
        )
    else:
        # Last resort: selectbox (still controlled + conditional rendering).
        selected_label = st.selectbox(
            label="Selectbox for Entries sub-views",
            options=labels_only,
            index=default_index,
            key=f"{state_key}__select",
            label_visibility="collapsed",
        )

    # Map selected label back to our internal key
    label_to_key = {lbl: k for k, lbl in options}
    selected_key = label_to_key.get(selected_label, "entries")

    st.session_state[state_key] = selected_key
    return selected_key


# -----------------------------------------------------------------------------
# Page entry point
# -----------------------------------------------------------------------------


def render(app_config: AppConfig, layout: LayoutConfig, page: PageConfig) -> None:
    """
    Render the Entries page.

    Args:
        app_config: Global application configuration (DB path, fiscal year, standard).
        layout: Parsed layout configuration (not heavily used yet in v0.5.0).
        page: Entries page configuration loaded from layout_en.toml
              ([pages.entries], [pages.entries.ui], [pages.entries.periods], ...).
    """

    st.title(_get(page, "title", "Entries"))

    # UI labels are stored in page.ui
    ui = _to_mapping(_get(page, "ui", {}))

    # Count duplicates for the selector label "Duplicates (N)"
    # Note: we use pending duplicates to reflect the operational workload.
    dup_stats = get_duplicate_stats(app_config)
    duplicates_count = int(getattr(dup_stats, "pending", 0))

    subview = _render_subview_selector(ui=ui, duplicates_count=duplicates_count)

    # ---------------------------------------------------------------------
    # Sub-view placeholders (we will replace these progressively).
    # The whole point of controlled rendering is that ONLY this block runs.
    # ---------------------------------------------------------------------
    if subview == "entries":
        # Reserve future columns for additional filters (code/desc/amount/batch/toggles)
        c1, c2, c3, c4, c5, c6 = st.columns([1.0, 0.7, 0.9, 0.9, 0.8, 1.0])

        with c1:
            period_filter = render_entries_period_filter(
                page=page, app_config=app_config
            )

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
            right = (
                _fmt_cents(amount_max_cents) if amount_max_cents is not None else "∅"
            )
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

        with c6:
            # unknown_count is not computed yet in v0.5.0 header-only phase.
            # We'll plug it once the DB query/table rendering is implemented.
            show_unknown_only, include_deleted = render_entries_toggles_and_badge(
                page=page,
                unknown_count=None,
            )

        toggles_filter_result = (
            f"[Unknown only: {show_unknown_only}] [Include deleted: {include_deleted}] "
        )

        st.info(
            f"Applied filters:    {period_filter_result}{code_filter_result}"
            f"{description_filter_result}{amount_filter_result}"
            f"{batch_filter_result}{toggles_filter_result}"
        )

        return

    if subview == "import":
        st.info("Import view (WIP): CSV import + import history will be added next.")
        return

    if subview == "duplicates":
        st.info(
            "Duplicates view (WIP): list + resolve (Keep/Discard) will be added next."
        )
        return

    if subview == "recycle_bin":
        st.info(
            "Recycle bin view (WIP): deleted entries list + restore will be added next."
        )
        return

    # Safety fallback
    st.warning("Unknown sub-view selected. Falling back to Entries.")
