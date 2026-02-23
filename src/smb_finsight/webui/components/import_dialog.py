# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Import-specific dialogs for the Entries page (WebUI).

This module contains only Streamlit dialogs used by the Import sub-view.
Dialogs are thin UI layers: data is fetched through entries_service (DB-backed),
or passed in by the caller (e.g., last import rejected rows).

UI strings are provided via the layout configuration (ui dict).

Note: Dialog titles are intentionally blank (" ") to allow using a subheader
  with UI-configured text.
"""

from dataclasses import asdict
from typing import Any

import pandas as pd
import streamlit as st

from smb_finsight.config import AppConfig
from smb_finsight.db import EntriesFilter
from smb_finsight.entries_service import list_duplicate_pairs, search_entries


@st.dialog(" ", width="large")
def dialog_import_batch_entries(
    *,
    app_config: AppConfig,
    ui: dict[str, Any],
    batch_id: int,
) -> None:
    """
    Display entries belonging to the selected import batch.

    The dialog queries the database for entries with import_batch_id == batch_id,
    ordered by (date ASC). If no rows are found, an informational message is shown.

    The displayed columns follow a preferred ordering when available, falling back
    to the full dataframe otherwise.
    """

    st.subheader(str(ui["import_dialog_entries_title"]))

    df = search_entries(
        app_config,
        EntriesFilter(import_batch_id=int(batch_id)),
        limit=None,
        offset=0,
        order_by=("date", "ASC"),
    )

    if df.empty:
        st.info(str(ui["import_dialog_entries_empty"]))
        return

    # Display: prefer a stable, readable column order when these columns exist.

    preferred_cols = [
        "id",
        "date",
        "code",
        "description",
        "amount",
        "import_batch_id",
        "source_type",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
        "deleted_reason",
    ]
    cols = [c for c in preferred_cols if c in df.columns]
    df_view = df[cols] if cols else df

    st.dataframe(df_view, width="stretch", hide_index=True)


@st.dialog(" ", width="large")
def dialog_import_batch_duplicates(
    *,
    app_config: AppConfig,
    ui: dict[str, Any],
    batch_id: int,
) -> None:
    """
    Display duplicate candidates detected for the selected import batch.

    The dialog queries the database for duplicate pairs associated with the given
    import_batch_id (all statuses). If no duplicates are found, an informational
    message is shown.

    The displayed dataframe is built from the 'duplicate' payload of each pair.
    Columns follow a preferred ordering when available, falling back to the full
    dataframe otherwise.
    """

    st.subheader(str(ui["import_dialog_duplicates_title"]))

    pairs = list_duplicate_pairs(
        app_config,
        status=None,  # show all statuses for this batch
        import_batch_id=int(batch_id),
        period=None,
        limit=None,
        offset=0,
    )

    if not pairs:
        st.info(str(ui["import_dialog_duplicates_empty"]))
        return

    # Convert duplicate pair objects to a dataframe for display.
    df = pd.DataFrame([asdict(p.duplicate) for p in pairs])

    # Optional: stable ordering of columns (if present)
    preferred_cols = [
        "id",
        "date",
        "code",
        "description",
        "amount",
        "import_batch_id",
        "imported_at",
        "existing_entry_id",
        "resolution_status",
        "resolution_at",
        "resolved_by",
        "resolution_comment",
    ]
    cols = [c for c in preferred_cols if c in df.columns]
    df_view = df[cols] if cols else df

    st.dataframe(df_view, hide_index=True)


@st.dialog(" ")
def dialog_unknown_accounts_rejected(
    *, ui: dict[str, Any], rejected_df: pd.DataFrame | None = None
) -> None:
    """
    Display rows rejected due to unknown account codes and offer a CSV download.

    The rejected dataframe is provided by the caller (typically the Import sub-view),
    and usually represents the last executed import only. If no rejected rows are
    available, an informational message is shown.
    """

    if rejected_df is None or rejected_df.empty:
        st.info(str(ui["import_dialog_no_rejected_rows"]))
        return

    st.subheader(str(ui["import_dialog_unknown_title"]))
    st.dataframe(rejected_df, width="stretch", hide_index=True)

    csv_bytes = rejected_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=str(ui["import_dialog_download_button"]),
        data=csv_bytes,
        file_name="unknown_accounts_rejected.csv",
        mime="text/csv",
        width="stretch",
    )
