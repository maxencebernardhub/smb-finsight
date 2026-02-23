# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Common dialog used for Add, Edit, Delete and Restore entry.

- When `existing` is None, the dialog creates a new entry via a mini import batch
  (source_type=manual, source_label=webui) and relies on the import pipeline
  to route duplicates to `duplicate_entries`.

- When `existing` is provided (AccountingEntry), the dialog performs an in-place
  update on the `entries` table via entries_service.edit_entry().

UI labels/messages are provided through the `ui` dict (layout_en.toml).

"""

from datetime import date
from typing import Any, Optional

import streamlit as st

from smb_finsight import entries_service
from smb_finsight.accounts import load_list_of_accounts
from smb_finsight.config import AppConfig
from smb_finsight.db import AccountingEntry, EntryUpdate
from smb_finsight.webui.layout import EntriesManualEntryConfig

FLASH_KEY = "entries__flash"


def _get_manual_entry_config(layout: Any) -> EntriesManualEntryConfig:
    """
    Return manual entry dialog defaults from layout configuration.
    Falls back to safe defaults if the configuration section is missing.
    """

    try:
        cfg = layout.entries.manual_entry
        input_mode = cfg.input_mode
        toggle_default_reject_unknown_accounts = (
            cfg.toggle_default_reject_unknown_accounts
        )
    except Exception:  # noqa: BLE001
        input_mode = "amount"
        toggle_default_reject_unknown_accounts = True
    return EntriesManualEntryConfig(
        input_mode=input_mode,
        toggle_default_reject_unknown_accounts=toggle_default_reject_unknown_accounts,
    )


def _is_known_account_prefix(code: str, app_config: AppConfig) -> bool:
    """
    Return True if `code` matches a known account by prefix.
    """
    std = app_config.standard_config
    if std.chart_of_accounts is None:
        return True

    df = load_list_of_accounts(str(std.chart_of_accounts))
    known = set(df["account_number"].astype(str).str.strip())
    code = code.strip()
    return any(code.startswith(k) for k in known)


def _compute_amount(
    ui: dict[str, Any],
    input_mode: str,
    amount: float | None,
    debit: float | None,
    credit: float | None,
) -> tuple[float, list[str]]:
    """
    Compute signed amount and return (amount, errors).
    """
    errs: list[str] = []

    if input_mode == "amount":
        if amount is None:
            error_msg = ui.get(
                "manual_entry_err_amount_required", "Amount is required."
            )
            errs.append(error_msg)
            return 0.0, errs
        return float(amount), errs

    # debit/credit mode
    d = float(debit or 0.0)
    c = float(credit or 0.0)

    if d > 0 and c > 0:
        error_msg = ui.get(
            "manual_entry_err_debit_credit_both",
            "Debit and Credit cannot be both filled.",
        )
        errs.append(error_msg)
    amt = d - c
    return amt, errs


def _validate_entry(
    ui: dict[str, Any],
    d: date | None,
    code: str,
    amount: float,
    extra_errors: list[str],
) -> list[str]:
    errs = list(extra_errors)

    if d is None:
        error_msg = ui.get(
            "manual_entry_err_date_required",
            "Date is required.",
        )
        errs.append(error_msg)
    if not code.strip():
        error_msg = ui.get(
            "manual_entry_err_account_required",
            "Account code is required.",
        )
        errs.append(error_msg)
    if abs(amount) < 1e-12:
        error_msg = ui.get(
            "manual_entry_err_amount_nonzero",
            "Amount must be non-zero.",
        )
        errs.append(error_msg)

    return errs


def _insert_manual_entry_with_batch(
    app_config: AppConfig,
    *,
    entry_date: date,
    code: str,
    description: str,
    amount: float,
) -> tuple[str, int]:
    """
    Insert a single manual entry via the service layer (mini-batch import).

    Returns:
        (status, batch_id) where status is "inserted" or "duplicate".
    """

    res = entries_service.create_manual_entry(
        app_config,
        entry_date=entry_date,
        code=code,
        description=description,
        amount=amount,
        source_label="webui",
    )

    return res.status, res.batch_id


@st.dialog(" ")
def open_entry_dialog(
    *,
    app_config: AppConfig,
    layout: Any,
    ui: dict[str, Any],
    title: str,
    existing: Optional[AccountingEntry] = None,
) -> None:
    """
    Common dialog used by both 'Add single entry' and 'Edit'.
    If `existing` is provided, it pre-fills the form (Edit mode).
    """
    cfg = _get_manual_entry_config(layout)

    st.subheader(title)

    # Defaults (Add)
    default_date = date.today()
    default_code = ""
    default_desc = ""
    default_mode = cfg.input_mode

    default_amount = 0.0
    default_debit = 0.0
    default_credit = 0.0

    is_edit = existing is not None
    # If Edit => override defaults from `existing`
    if is_edit:
        default_date = existing.date
        default_code = existing.code
        default_desc = existing.description or ""
        existing_amount = float(existing.amount)
        default_amount = existing_amount
        default_debit = existing_amount if existing_amount > 0 else 0.0
        default_credit = -existing_amount if existing_amount < 0 else 0.0

    with st.container(border=True):
        entry_date = st.date_input(
            ui.get("manual_entry_date_label", "Date"), value=default_date
        )

    with st.container(border=True):
        code = st.text_input(
            ui.get("manual_entry_account_code_label", "Account code"),
            value=default_code,
        ).strip()

    with st.container(border=True):
        description = st.text_area(
            ui.get("manual_entry_description_label", "Description"), value=default_desc
        )

    input_mode_label = ui.get("manual_entry_input_mode_label", "Input mode")
    amount_label = ui.get("manual_entry_amount_label", "Amount")
    debit_label = ui.get("manual_entry_debit_label", "Debit")
    credit_label = ui.get("manual_entry_credit_label", "Credit")

    opt_amount = ui.get("manual_entry_input_mode_amount", "Amount")
    opt_dc = ui.get("manual_entry_input_mode_debit_credit", "Debit / Credit")

    comp_amount_info = ui.get(
        "manual_entry_computed_amount_info", "Computed amount = debit - credit"
    )

    with st.container(border=True):
        input_mode = st.radio(
            input_mode_label,
            options=["amount", "debit_credit"],
            format_func=lambda v: opt_amount if v == "amount" else opt_dc,
            index=0 if default_mode == "amount" else 1,
            horizontal=True,
        )

        reject_unknown = st.toggle(
            ui.get(
                "manual_entry_reject_unknown_toggle",
                "Reject unknown accounts (prefix matching)",
            ),
            value=cfg.toggle_default_reject_unknown_accounts,
        )

        amount_val: float | None = None
        debit_val: float | None = None
        credit_val: float | None = None

        if input_mode == "amount":
            amount_val = st.number_input(amount_label, value=float(default_amount))
            st.caption(
                ui.get(
                    "manual_entry_amount_information_note",
                    "Signed amount: positive = debit, negative = credit "
                    "(convention used by SMB FinSight).",
                )
            )
        else:
            debit_val = st.number_input(
                debit_label, value=float(default_debit), min_value=0.0
            )
            credit_val = st.number_input(
                credit_label, value=float(default_credit), min_value=0.0
            )

        computed_amount, mode_errors = _compute_amount(
            ui, input_mode, amount_val, debit_val, credit_val
        )

        if input_mode != "amount":
            st.info(f"{comp_amount_info} = {computed_amount:.2f}")

        # Validation
        errors = _validate_entry(ui, entry_date, code, computed_amount, mode_errors)

        if reject_unknown and not _is_known_account_prefix(code, app_config):
            errors.append(
                ui.get(
                    "add_entry_unknown_account_code",
                    "Unknown account code (no prefix match in the chart of accounts).",
                )
            )

    submitted = st.button(
        ui.get("manual_entry_save_button", "Save"), type="primary", width="stretch"
    )

    if submitted:
        if errors:
            for e in errors:
                st.error(e)
            return

        if is_edit:
            # Normalize empty description to None (DB model accepts None)
            desc_norm = description.strip() or None

            update = EntryUpdate(
                date=entry_date,
                code=code,
                description=desc_norm,
                amount=float(computed_amount),
            )

            entries_service.edit_entry(app_config, existing.id, update)

            msg = ui.get("manual_entry_flash_updated", "Entry updated.")
            st.session_state[FLASH_KEY] = ("success", msg)

            st.rerun()
            return

        status, batch_id = _insert_manual_entry_with_batch(
            app_config,
            entry_date=entry_date,
            code=code,
            description=description,
            amount=computed_amount,
        )

        if status == "inserted":
            msg = ui.get(
                "manual_entry_flash_created",
                "Entry created.",
            )
            st.session_state[FLASH_KEY] = ("success", f"{msg} (batch #{batch_id})")
        else:
            msg = ui.get(
                "duplicate_detected_warning",
                "Duplicate detected → stored in Duplicates ",
            )
            st.session_state[FLASH_KEY] = ("warning", f"{msg} (batch #{batch_id}).")

        # Force refresh of the main page after save
        st.rerun()


def render_add_single_entry_button(
    *, app_config: AppConfig, layout: Any, ui: dict[str, Any]
) -> None:
    label = ui.get("button_add_entry", "Add entry")
    if st.button(label, type="primary", width="stretch"):
        open_entry_dialog(
            app_config=app_config,
            layout=layout,
            ui=ui,
            title=ui.get("manual_entry_dialog_title_add", "Add single entry"),
            existing=None,
        )


@st.dialog(" ")
def confirm_delete_entries_dialog(
    *,
    app_config: AppConfig,
    ui: dict[str, Any],
    entry_ids: list[int],
) -> None:
    """
    Confirm and execute a soft-delete for the selected entries.

    This dialog is intentionally side-effect free unless the user presses the
    confirm button. Closing the dialog (X / outside click) leaves the database
    unchanged.
    An optional reason can be provided and will be stored in deleted_reason.

    Deletion is performed via entries_service.delete_entry(), which soft-deletes
    rows in the `entries` table (is_deleted flag) and keeps them available for
    restoration from the Recycle bin.
    """
    # Title & message
    st.subheader(ui.get("dialog_delete_title", "Delete selected entries"))

    if len(entry_ids) == 1:
        text_tpl = ui.get(
            "delete_single_confirm_text",
            "Are you sure you want to delete this entry?",
        )
        st.write(text_tpl)
    else:
        text_tpl = ui.get(
            "delete_multiple_confirm_text",
            "Are you sure you want to delete these {count} entries?",
        )
        st.write(text_tpl.format(count=len(entry_ids)))

    reason = st.text_input(
        ui.get("delete_reason_label", "Reason for deletion (optional):"),
        placeholder=ui.get("delete_reason_placeholder", ""),
    )
    reason = reason.strip() or None

    # Confirm button
    if st.button(ui.get("button_confirm", "Confirm"), type="primary", width="stretch"):
        for eid in entry_ids:
            entries_service.delete_entry(app_config, int(eid), reason=reason)

        msg_tpl = ui.get("delete_success", "{count} entries deleted.")
        st.session_state[FLASH_KEY] = ("success", msg_tpl.format(count=len(entry_ids)))

        st.rerun()


@st.dialog(" ")
def confirm_restore_entries_dialog(
    *,
    app_config: AppConfig,
    ui: dict[str, Any],
    entry_ids: list[int],
) -> None:
    """
    Confirm and execute a restore for the selected entries.

    This dialog is intentionally side-effect free unless the user presses the
    confirm button. Closing the dialog leaves the database unchanged.

    Restoration is performed via entries_service.restore_deleted_entry(), which
    sets is_deleted=False and clears deletion metadata depending on DB behavior.
    """
    st.subheader(ui.get("dialog_restore_title", "Restore selected entries"))

    if len(entry_ids) == 1:
        text_tpl = ui.get(
            "restore_single_confirm_text",
            "Are you sure you want to restore this entry?",
        )
        st.write(text_tpl)
    else:
        text_tpl = ui.get(
            "restore_multiple_confirm_text",
            "Are you sure you want to restore these {count} entries?",
        )
        st.write(text_tpl.format(count=len(entry_ids)))

    if st.button(ui.get("button_confirm", "Confirm"), type="primary", width="stretch"):
        for eid in entry_ids:
            entries_service.restore_deleted_entry(app_config, int(eid))

        msg_tpl = ui.get("restore_success", "{count} entries restored.")
        st.session_state[FLASH_KEY] = ("success", msg_tpl.format(count=len(entry_ids)))
        st.rerun()
