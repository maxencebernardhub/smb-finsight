# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Duplicates-specific dialogs for the Entries page (WebUI).

This module centralizes Streamlit dialogs used by the Duplicates sub-view:
- confirm_resolve_duplicates_dialog(): confirm and resolve one or many duplicates
  (keep/discard) with an optional resolution comment.
- view_duplicate_details_dialog(): show a side-by-side comparison between a
  DuplicateEntry and its linked existing AccountingEntry (if available).

Design notes
------------
- Dialogs receive `ui` (layout config dict) to remain fully config-driven and
  avoid hardcoded labels.
- Field/Value tables are rendered with a small DataFrame normalized to strings
  to avoid Arrow serialization warnings in Streamlit.

"""

from typing import Any, Optional

import pandas as pd
import streamlit as st

from smb_finsight.config import AppConfig
from smb_finsight.db import AccountingEntry, DuplicateEntry
from smb_finsight.entries_service import (
    list_import_batches,
    load_duplicate_entry,
    load_entry,
    resolve_duplicate_entry,
)

FLASH_KEY = "entries__flash"


def _build_batch_label_map(app_config: AppConfig) -> dict[int, str]:
    """
    Build a mapping import_batch_id -> human-readable label.

    The label uses batch notes when available, otherwise falls back to the
    created_at timestamp.
    """
    batches_df = list_import_batches(app_config, limit=200)
    out: dict[int, str] = {}
    if batches_df.empty:
        return out

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
        out[batch_id] = notes if notes else created_label
    return out


def _kv_df(
    rows: list[tuple[str, Any]],
    *,
    ui: dict[str, Any],
) -> pd.DataFrame:
    """
    Return a small 'Field / Value' DataFrame for display.

    Column labels are read from layout configuration (layout_en.toml).

    Notes
    -----
    Streamlit serializes DataFrames through Arrow (pyarrow). A mixed-typed
    "Value" column can trigger Arrow conversion warnings. We normalize
    everything to strings for stability.
    """

    col_field = ui.get("duplicate_details_column_field", "Field")
    col_value = ui.get("duplicate_details_column_value", "Value")

    def _fmt(v: Any) -> str:
        if v is None:
            return ""
        # date / datetime / pandas Timestamp, etc.
        if hasattr(v, "isoformat"):
            try:
                return v.isoformat()
            except Exception:  # noqa: BLE001
                return str(v)
        # floats (amounts)
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    df = pd.DataFrame(rows, columns=[col_field, col_value])
    df[col_field] = df[col_field].map(lambda x: "" if x is None else str(x))
    df[col_value] = df[col_value].map(_fmt)

    return df


def _resolution_status_label(ui: dict[str, Any], status: str | None) -> str:
    """Return a human-readable resolution status label from the UI config."""
    s = (status or "").strip().lower()
    if s == "pending":
        return ui.get("resolution_status_pending", "Pending")
    if s == "kept":
        return ui.get("resolution_status_kept", "Kept")
    if s == "discarded":
        return ui.get("resolution_status_discarded", "Discarded")
    return status or ""


@st.dialog(" ")
def confirm_resolve_duplicates_dialog(
    *,
    app_config: AppConfig,
    ui: dict[str, Any],
    duplicate_ids: list[int],
    decision: str,
) -> None:
    """Confirm and resolve selected duplicates.

    This dialog is opened from the Duplicates sub-view action panel.
    When confirmed, it calls entries_service.resolve_duplicate_entry() for each
    selected duplicate id and stores a flash message in st.session_state to
    refresh the parent view.
    """
    decision = (decision or "").strip().lower()
    if decision not in {"keep", "discard"}:
        st.error(f"Unsupported decision: {decision!r}")
        return

    st.subheader(
        ui.get("duplicate_resolution_dialog_title", "Resolve duplicate entries")
    )

    if decision == "keep":
        msg_one = ui.get(
            "duplicate_keep_single_confirm_text",
            "Are you sure you want to keep this duplicate entry?",
        )
        msg_many = ui.get(
            "duplicate_keep_multiple_confirm_text",
            "Are you sure you want to keep these {count} duplicate entries?",
        )
    else:
        msg_one = ui.get(
            "duplicate_discard_single_confirm_text",
            "Are you sure you want to discard this duplicate entry?",
        )
        msg_many = ui.get(
            "duplicate_discard_multiple_confirm_text",
            "Are you sure you want to discard these {count} duplicate entries?",
        )

    st.write(
        msg_one
        if len(duplicate_ids) == 1
        else msg_many.format(count=len(duplicate_ids))
    )

    comment = st.text_input(
        ui.get("duplicate_resolution_comment", "Resolution comment"),
        placeholder=ui.get("duplicate_resolution_comment_placeholder", ""),
    )
    comment = comment.strip() or None

    if st.button(ui.get("button_confirm", "Confirm"), type="primary", width="stretch"):
        for did in duplicate_ids:
            resolve_duplicate_entry(
                app_config,
                int(did),
                decision,  # "keep" | "discard"
                comment=comment,
                resolved_by="webui",
            )

        msg_tpl = ui.get(
            "duplicate_resolution_success",
            "{count} duplicate entries resolved.",
        )
        st.session_state[FLASH_KEY] = (
            "success",
            msg_tpl.format(count=len(duplicate_ids)),
        )
        st.rerun()


@st.dialog(" ", width="medium")
def view_duplicate_details_dialog(
    *,
    app_config: AppConfig,
    ui: dict[str, Any],
    duplicate_id: int,
) -> None:
    """Show a side-by-side comparison for a duplicate and its existing entry.

    Left side: DuplicateEntry fields (including resolution metadata).
    Right side: linked AccountingEntry fields (including deletion metadata).
    Field labels are read from layout configuration (ui dict).
    """
    st.subheader(ui.get("duplicate_view_details_title", "Duplicate details"))

    dup: Optional[DuplicateEntry] = load_duplicate_entry(app_config, int(duplicate_id))
    if dup is None:
        st.warning(
            ui.get("duplicate_view_details_not_found", "Duplicate entry not found.")
        )
        return

    existing: Optional[AccountingEntry] = None
    if dup.existing_entry_id is not None:
        existing = load_entry(app_config, int(dup.existing_entry_id))

    batch_labels = _build_batch_label_map(app_config)
    dup_batch_label = batch_labels.get(
        int(dup.import_batch_id), str(dup.import_batch_id)
    )

    left_rows: list[tuple[str, Any]] = [
        (ui.get("field_date", ui.get("column_date", "Date")), dup.date),
        (ui.get("field_code", ui.get("column_code", "Account code")), dup.code),
        (
            ui.get("field_description", ui.get("column_description", "Description")),
            dup.description or "",
        ),
        (ui.get("field_amount", ui.get("column_amount", "Amount")), float(dup.amount)),
        (
            ui.get("field_imported_at", ui.get("column_imported_at", "Imported at")),
            dup.imported_at,
        ),
        (
            ui.get("field_import_batch", ui.get("column_import_batch", "Import batch")),
            dup_batch_label,
        ),
        (
            ui.get(
                "field_resolution_status",
                ui.get("resolution_status", "Resolution status"),
            ),
            _resolution_status_label(ui, dup.resolution_status),
        ),
        (
            ui.get("field_resolution_at", ui.get("resolution_at", "Resolved at")),
            dup.resolution_at,
        ),
        (
            ui.get("field_resolved_by", ui.get("resolved_by", "Resolved by")),
            dup.resolved_by or "",
        ),
        (
            ui.get(
                "field_resolution_comment",
                ui.get("resolution_comment", "Resolution notes"),
            ),
            dup.resolution_comment or "",
        ),
    ]

    if existing is None:
        right_rows = [
            (
                ui.get("duplicate_existing_entry_missing", "Existing entry"),
                ui.get(
                    "duplicate_existing_entry_missing_value", "No linked entry found."
                ),
            )
        ]
    else:
        existing_batch_label = batch_labels.get(
            int(existing.import_batch_id), str(existing.import_batch_id)
        )
        right_rows = [
            (ui.get("field_date", ui.get("column_date", "Date")), existing.date),
            (
                ui.get("field_code", ui.get("column_code", "Account code")),
                existing.code,
            ),
            (
                ui.get(
                    "field_description", ui.get("column_description", "Description")
                ),
                existing.description or "",
            ),
            (
                ui.get("field_amount", ui.get("column_amount", "Amount")),
                float(existing.amount),
            ),
            (
                ui.get(
                    "field_imported_at", ui.get("column_imported_at", "Imported at")
                ),
                existing.created_at,
            ),
            (
                ui.get(
                    "field_import_batch", ui.get("column_import_batch", "Import batch")
                ),
                existing_batch_label,
            ),
            (
                ui.get("field_updated_at", ui.get("column_updated_at", "Last updated")),
                existing.updated_at,
            ),
            (ui.get("field_is_deleted", "Deleted?"), bool(existing.is_deleted)),
            (
                ui.get("field_deleted_at", ui.get("column_deleted_at", "Deleted at")),
                existing.deleted_at,
            ),
            (
                ui.get(
                    "field_deleted_reason",
                    ui.get("column_deleted_reason", "Deletion reason"),
                ),
                existing.deleted_reason or "",
            ),
        ]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"**{ui.get('duplicate_view_details_left', 'Duplicate candidate')}**"
        )
        st.dataframe(_kv_df(left_rows, ui=ui), hide_index=True, width="stretch")

    with c2:
        st.markdown(f"**{ui.get('duplicate_view_details_right', 'Existing entry')}**")
        st.dataframe(_kv_df(right_rows, ui=ui), hide_index=True, width="stretch")
