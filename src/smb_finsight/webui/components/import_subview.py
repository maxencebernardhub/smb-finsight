# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Import sub-view renderer (WebUI).

This sub-view provides a DB-backed CSV import workflow:
- Left column: CSV uploader, optional import label (stored as import_batches.notes),
  and a toggle to reject unknown account codes (based on the chart of accounts).
- Import execution writes to the database using db.import_entries, which inserts
  entries and records duplicates for later review.
- An import summary is displayed (inserted / duplicates / unknown rejected).
  The success banner + balloons are shown as a one-shot UI event.
- Unknown rejected rows (if any) are kept in session memory for the last import
  and can be reviewed/downloaded via a dialog.
- Right column: import history (DB: import_batches) with actions to display batch
  entries and duplicates in dedicated dialogs.

Dialogs are implemented in smb_finsight.webui.components.import_dialog.

"""

from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pandas as pd
import streamlit as st

from smb_finsight.accounts import (
    load_list_of_accounts,
    split_known_and_unknown_accounts,
)
from smb_finsight.config import AppConfig
from smb_finsight.db import import_entries as db_import_entries
from smb_finsight.entries_service import list_import_batches, set_import_batch_notes
from smb_finsight.io import read_accounting_entries
from smb_finsight.webui.components.import_dialog import (
    dialog_import_batch_duplicates,
    dialog_import_batch_entries,
    dialog_unknown_accounts_rejected,
)
from smb_finsight.webui.layout import LayoutConfig, PageConfig

# -----------------------------------------------------------------------------
# UI state
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportResultsState:
    """Durable UI state: summary metrics for the last executed import."""

    rows_inserted: int = 0
    duplicates_detected: int = 0
    unknown_rejected: int = 0


# Session state keys:
# - _RESULTS_STATE_KEY: durable UI state (last import summary metrics)
# - _UNKNOWN_REJECTED_DF_KEY: durable UI state (unknown rejected rows for last import)
# - _LAST_IMPORTED_BATCH_ID_KEY: durable UI state (last imported batch id)
# - "import__just_succeeded": one-shot UI event consumed on next render
#   (success + balloons)

_RESULTS_STATE_KEY = "import__results_state"
_UNKNOWN_REJECTED_DF_KEY = "import__unknown_rejected_df"
_LAST_IMPORTED_BATCH_ID_KEY = "import__last_batch_id"


# -----------------------------------------------------------------------------
# Handlers
# -----------------------------------------------------------------------------
def _handle_import_click(
    *,
    app_config: AppConfig,
    ui: dict[str, Any],
    uploaded,
    import_label: str,
    reject_unknown: bool,
) -> None:
    """
    Handle the Import button click.

    Steps:
        1) Persist the uploaded CSV to a temporary file and parse it using
           read_accounting_entries() (same parsing rules as the CLI).
        2) If reject_unknown is enabled, split rows into known vs unknown account
           codes using the current standard's chart of accounts. The chart of
           accounts file is expected to include an 'account_number' column.
        3) Import known rows into the database via db.import_entries(), which
           creates an import batch, inserts entries, and records duplicates.
        4) Store the optional import label into import_batches.notes.
        5) Update Streamlit session state for the last import summary and trigger
           a rerun to refresh the import history.

    Side effects:
        - Writes to DB: import_batches, entries, duplicate_entries (via import_entries).
        - Updates session state:
            * _RESULTS_STATE_KEY: ImportResultsState (durable last import summary)
            * _UNKNOWN_REJECTED_DF_KEY: rejected rows for last import (durable)
            * _LAST_IMPORTED_BATCH_ID_KEY: last imported batch id (durable)
            * "import__just_succeeded": one-shot success event for next render

    Error handling:
        - Displays a user-friendly error message through Streamlit.
        - Technical error details are intentionally not exposed here.
    """
    try:
        if uploaded is None:
            st.error(str(ui["import_error_no_file"]))
            return

        # 1) Read CSV using the same parsing rules as the CLI.
        #    Note: the uploaded file is written to a temporary CSV file for parsing.

        with NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded.getbuffer())
            tmp_path = Path(tmp.name)

        df = read_accounting_entries(tmp_path)

        if df.empty:
            st.error(str(ui["import_error_empty_file"]))
            return

        # 2) Optionally reject unknown accounts (prefix-matching on chart of accounts)
        unknown_df = pd.DataFrame()
        df_to_import = df

        if reject_unknown:
            std_cfg = app_config.standard_config
            if std_cfg.chart_of_accounts is None:
                st.error(str(ui["import_error_missing_chart_of_accounts"]))
                return

            accounts_df = load_list_of_accounts(str(std_cfg.chart_of_accounts))

            # Contract: chart of accounts must provide an 'account_number' column.
            known_codes = set(accounts_df["account_number"].astype(str).str.strip())

            known_df, unknown_df = split_known_and_unknown_accounts(df, known_codes)
            df_to_import = known_df

        # 3) Import known entries
        if df_to_import.empty:
            st.error(str(ui["import_error_no_known_entries"]))
            st.session_state[_UNKNOWN_REJECTED_DF_KEY] = unknown_df
            st.session_state[_RESULTS_STATE_KEY] = ImportResultsState(
                rows_inserted=0,
                duplicates_detected=0,
                unknown_rejected=int(len(unknown_df)),
            )
            return

        source_label = uploaded.name  # visible in history
        stats = db_import_entries(
            df_to_import,
            app_config.database,
            source_type="csv",
            source_label=str(source_label),
        )

        # 4) Save notes in import_batches.notes
        set_import_batch_notes(
            app_config, batch_id=int(stats.batch_id), notes=import_label
        )

        # 5) Update UI state
        st.session_state[_UNKNOWN_REJECTED_DF_KEY] = unknown_df
        st.session_state[_LAST_IMPORTED_BATCH_ID_KEY] = int(stats.batch_id)

        st.session_state[_RESULTS_STATE_KEY] = ImportResultsState(
            rows_inserted=int(stats.rows_inserted),
            duplicates_detected=int(stats.duplicates_detected),
            unknown_rejected=int(len(unknown_df)),
        )

        # Refresh history + metrics immediately
        st.session_state["import__just_succeeded"] = True
        st.rerun()

    except Exception:
        # Intentionally keep user-facing errors generic here (no technical details).
        st.error(str(ui["import_error_generic"]))


# -----------------------------------------------------------------------------
# Public renderer
# -----------------------------------------------------------------------------


def render_import_subview(
    *,
    app_config: AppConfig,
    layout: LayoutConfig,
    page: PageConfig,
    ui: dict[str, Any],
) -> None:
    """
    Render the Import sub-view (Entries page).

    Args:
        app_config: Global application config (DB path, standard, etc.).
        layout: Layout configuration (unused for now, but kept for consistency).
        page: Entries page config (contains UI strings).
        ui: Flattened UI strings from layout.toml.

    Notes:
        Import execution happens on button click (left panel) and triggers a rerun
        to refresh the import history (right panel).

    """

    # Init durable UI state (last import summary / last unknown rejected rows).

    if _RESULTS_STATE_KEY not in st.session_state:
        st.session_state[_RESULTS_STATE_KEY] = ImportResultsState()

    if _UNKNOWN_REJECTED_DF_KEY not in st.session_state:
        st.session_state[_UNKNOWN_REJECTED_DF_KEY] = pd.DataFrame()

    if _LAST_IMPORTED_BATCH_ID_KEY not in st.session_state:
        st.session_state[_LAST_IMPORTED_BATCH_ID_KEY] = None

    left, right = st.columns([0.5, 1.0], gap="medium")

    with left:
        _render_import_panel(app_config=app_config, ui=ui)

    with right:
        _render_import_history_panel(app_config=app_config, ui=ui)


# -----------------------------------------------------------------------------
# Left panel: Import controls + results
# -----------------------------------------------------------------------------


def _render_import_panel(*, app_config: AppConfig, ui: dict[str, Any]) -> None:
    with st.container(border=True):
        st.subheader(str(ui["import_section_title"]))

        uploaded = st.file_uploader(
            label=str(ui["import_uploader_label"]),
            type=["csv"],
            accept_multiple_files=False,
            key="import__file_uploader",
        )

        import_label = st.text_input(
            label=str(ui["import_label_input_label"]),
            placeholder=str(ui["import_label_input_placeholder"]),
            key="import__label_input",
        )

        reject_unknown = st.toggle(
            label=str(ui["import_reject_unknown_toggle_label"]),
            value=True,
            key="import__reject_unknown_toggle",
            help=str(ui["import_reject_unknown_toggle_help"]),
        )

        # Runs the import workflow and triggers a rerun on success.

        clicked = st.button(
            label=str(ui["import_button_import"]),
            type="primary",
            width="stretch",
            key="import__run_button",
            disabled=(uploaded is None),
            help=str(ui["import_button_import_help"]),
        )
        if clicked:
            _handle_import_click(
                app_config=app_config,
                ui=ui,
                uploaded=uploaded,
                import_label=import_label,
                reject_unknown=bool(reject_unknown),
            )

    # Results

    with st.container(border=True):
        st.subheader(str(ui["import_results_section_title"]))

        rs: ImportResultsState = st.session_state[_RESULTS_STATE_KEY]

        if st.session_state.pop("import__just_succeeded", False):
            st.success(str(ui["import_results_success_message"]))
            st.balloons()

        with st.container(border=True):
            c1, c2, c3 = st.columns(3, gap="small")
            c1.metric(str(ui["import_results_metric_inserted"]), f"{rs.rows_inserted}")
            c2.metric(
                str(ui["import_results_metric_duplicates"]), f"{rs.duplicates_detected}"
            )
            c3.metric(
                str(ui["import_results_metric_unknown_rejected"]),
                f"{rs.unknown_rejected}",
            )

        # Unknown rejected action (enabled only if applicable)
        st.button(
            label=str(ui["import_results_button_view_unknown"]),
            disabled=(rs.unknown_rejected <= 0),
            width="stretch",
            key="import__btn_unknown_rejected",
            on_click=lambda: dialog_unknown_accounts_rejected(
                ui=ui, rejected_df=st.session_state[_UNKNOWN_REJECTED_DF_KEY]
            ),
            help=str(ui["import_results_button_view_unknown_help"]),
        )


# -----------------------------------------------------------------------------
# Right panel: Import history (DB) + actions
# -----------------------------------------------------------------------------


def _render_import_history_panel(*, app_config: AppConfig, ui: dict[str, Any]) -> None:
    with st.container(border=True):
        st.subheader(str(ui["import_history_section_title"]))

        history_df = list_import_batches(app_config, limit=200)

        df_view = history_df.copy()

        # Add selection column (first column)
        if "_selected" not in df_view.columns:
            df_view.insert(0, "_selected", False)

        # Hide id by using it as index (same pattern as duplicates_subview.py)
        if "id" in df_view.columns:
            df_view = df_view.set_index("id")

        # Keep only visible columns in the order you want
        desired_cols = [
            "_selected",
            "created_at",
            "source_type",
            "source_label",
            "rows_inserted",
            "notes",
        ]
        keep_cols = [c for c in desired_cols if c in df_view.columns]
        df_view = df_view[keep_cols]

        edited = st.data_editor(
            df_view,
            key="import__history_editor",
            hide_index=True,
            width="stretch",
            column_config={
                "_selected": st.column_config.CheckboxColumn(
                    label=str(ui["import_history_col_selected_label"]),
                    help=str(ui["import_history_col_selected_help"]),
                ),
                "created_at": st.column_config.DatetimeColumn(
                    label=str(ui["import_history_col_created_at"]),
                    format=str(ui["import_history_col_created_at_format"]),
                    disabled=True,
                ),
                "source_type": st.column_config.TextColumn(
                    label=str(ui["import_history_col_source_type"]),
                    disabled=True,
                ),
                "source_label": st.column_config.TextColumn(
                    label=str(ui["import_history_col_source_label"]),
                    disabled=True,
                ),
                "rows_inserted": st.column_config.NumberColumn(
                    label=str(ui["import_history_col_rows_inserted"]),
                    disabled=True,
                ),
                "notes": st.column_config.TextColumn(
                    label=str(ui["import_history_col_notes"]),
                    disabled=True,
                ),
            },
            disabled=[
                "created_at",
                "source_type",
                "source_label",
                "rows_inserted",
                "notes",
            ],
        )

        # Single-row selection logic.
        selected_ids = edited.index[edited["_selected"] == True].tolist()  # noqa: E712
        single_selected = len(selected_ids) == 1

        batch_id = int(selected_ids[0]) if single_selected else None

        st.caption(str(ui["import_history_caption_select_one"]))

        b1, b2 = st.columns(2, gap="small")

        with b1:
            st.button(
                label=str(ui["import_history_button_display_entries"]),
                disabled=not single_selected,
                width="stretch",
                key="import__btn_display_entries",
                type="primary",
                on_click=lambda bid=batch_id: dialog_import_batch_entries(
                    app_config=app_config,
                    ui=ui,
                    batch_id=int(bid),
                ),
                help=str(ui["import_history_button_display_entries_help"]),
            )

        with b2:
            st.button(
                label=str(ui["import_history_button_display_duplicates"]),
                disabled=not single_selected,
                width="stretch",
                key="import__btn_display_duplicates",
                type="primary",
                on_click=lambda bid=batch_id: dialog_import_batch_duplicates(
                    app_config=app_config,
                    ui=ui,
                    batch_id=int(bid),
                ),
                help=str(ui["import_history_button_display_duplicates_help"]),
            )
