# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Web UI page: Configuration.

This module implements the Streamlit "Configuration" page, allowing the user to:
- edit global settings stored in `smb_finsight_config.toml` (fiscal year, currency,
  separators),
- select the active accounting standard TOML from `config/standards/`,
- select the active WebUI layout TOML from `config/layout/`,
- select or create the SQLite database file under `data/db/`,
- edit optional numeric inputs (balance-sheet and HR inputs) used by ratios/KPIs.

Implementation notes:
- A mutable "draft" dict is stored in `st.session_state["config_draft"]` and is the
  single source of truth for pending edits.
- Saving patches the TOML using `tomlkit` to preserve comments and formatting.
- Paths are stored as repo-relative when possible, to match the loader behavior.
"""

from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st
import tomlkit

from smb_finsight.config import AppConfig, StandardConfig, _parse_standard_config
from smb_finsight.db import DatabaseConfig, init_database
from smb_finsight.webui.layout import LayoutConfig, PageConfig
from smb_finsight.webui.utils import _get, _to_mapping

# Repo conventions
MAIN_CONFIG_FILE = Path("smb_finsight_config.toml")
STANDARDS_DIR = Path("config/standards")
LAYOUTS_DIR = Path("config/layout")
DB_DIR = Path("data/db")


# ----------------------------
# TOML (read/patch/write)
# ----------------------------


def _read_main_toml_doc() -> tomlkit.TOMLDocument:
    """
    Load and parse the main application TOML configuration.

    Returns a TOMLDocument (tomlkit) so formatting/comments can be preserved
    when writing back.
    """
    path = MAIN_CONFIG_FILE.resolve()
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def _write_main_toml_doc(doc: tomlkit.TOMLDocument) -> None:
    """
    Write the main application TOML configuration back to disk.

    Uses tomlkit.dumps() to preserve formatting/comments from the parsed document.
    """
    path = MAIN_CONFIG_FILE.resolve()
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _ensure_table(doc: tomlkit.TOMLDocument, *path: str) -> dict[str, Any]:
    """
    Ensure that a nested TOML table path exists and return the deepest table.

    If any segment is missing (or not a mapping), a new tomlkit table is created.
    This helper is used to patch configuration while keeping existing structure.
    """
    cur: Any = doc
    for k in path:
        if k not in cur or not isinstance(cur[k], Mapping):
            cur[k] = tomlkit.table()
        cur = cur[k]
    return cur


def _get_str(doc: tomlkit.TOMLDocument, *path: str) -> str:
    """
    Safely retrieve a nested value as a trimmed string from a TOML document.

    Returns an empty string if the path does not exist.
    """
    cur: Any = doc
    for k in path:
        if not isinstance(cur, Mapping) or k not in cur:
            return ""
        cur = cur[k]
    return str(cur).strip() if cur is not None else ""


def _rel_from_repo_root(p: Path) -> str:
    """
    Store paths as relative to the main config file directory, when possible.

    This matches the config loader, which resolves relative paths from the TOML file
    folder.
    """
    base_dir = MAIN_CONFIG_FILE.resolve().parent
    try:
        return str(p.resolve().relative_to(base_dir)).replace("\\", "/")
    except Exception:  # noqa: BLE001
        return str(p)


# ----------------------------
# Scanners
# ----------------------------


def _scan_toml(folder: Path) -> list[Path]:
    """
    Return a sorted list of .toml files in the given folder (non-recursive).
    """
    if not folder.exists():
        return []
    return sorted([p for p in folder.glob("*.toml") if p.is_file()])


def _scan_sqlite(folder: Path) -> list[Path]:
    """
    Return a sorted list of .sqlite files in the given folder (non-recursive).
    """
    if not folder.exists():
        return []
    return sorted([p for p in folder.glob("*.sqlite") if p.is_file()])


# ----------------------------
# Draft init / helpers
# ----------------------------


def _humanize_key(k: str) -> str:
    """
    Convert a snake_case key into a human-readable Title Case label.
    """
    return k.replace("_", " ").strip().title()


def _selectbox_bound(
    *,
    key: str,
    label: str,
    options: list[str],
    draft: dict[str, Any],
    draft_field: str,
) -> str:
    """
    Render a Streamlit selectbox bound to a draft field via session_state.

    Pattern:
    - initialize `st.session_state[key]` once from `draft[draft_field]`,
    - render selectbox using session_state as the source of truth,
    - write the final selection back into the draft dict.

    This avoids widget resets on reruns and keeps draft coherent.
    """

    # Initialize widget state once from draft
    if key not in st.session_state:
        v = draft.get(draft_field)
        st.session_state[key] = v if v in options else options[0]

    # Render widget using widget state as source of truth
    st.selectbox(label, options=options, key=key)

    # Sync back into draft
    draft[draft_field] = st.session_state[key]
    return draft[draft_field]


def _init_draft(app_config: AppConfig) -> dict[str, Any]:
    """
    Draft is initialized from AppConfig plus raw TOML path strings.

    The draft stores resolved Path objects for file pickers (standard/db/layout),
    because Streamlit widgets manipulate filenames while the TOML stores strings.
    """
    doc = _read_main_toml_doc()

    base_dir = MAIN_CONFIG_FILE.resolve().parent

    std_raw = _get_str(doc, "accounting", "standard_config_file")
    std_path = (base_dir / std_raw).resolve() if std_raw else None

    return {
        # snapshot + editable
        "fy_start": app_config.fiscal_year.start_date,
        "fy_end": app_config.fiscal_year.end_date,
        "currency": app_config.currency,
        "thousands_separator": app_config.thousands_separator,
        # Only this one requires TOML read (for now)
        "standard_file": std_path,
        "db_file": app_config.database.path.resolve(),
        "layout_file": Path(app_config.webui_layout_config_path).resolve(),
        # inputs
        "balance_sheet_inputs": dict(app_config.balance_sheet_inputs),
        "hr_inputs": dict(app_config.hr_inputs),
        # preview standard (when user selects another standard file)
        "standard_preview": None,  # StandardConfig | None
    }


def _format_fy(d1: date, d2: date) -> str:
    """
    Format a fiscal-year date range for display in the page snapshot.
    """
    return f"{d1.isoformat()} → {d2.isoformat()}"


def _not_cfg(ui: Mapping[str, Any]) -> str:
    """
    Localized placeholder for missing/optional configuration values.
    """
    return str(_get(ui, "not_configured", "(not configured)"))


def _render_standard_details(
    ui: Mapping[str, Any],
    std: StandardConfig,
    selected_file: Path | None,
) -> None:
    """
    Read-only details panel for the selected standard.
    """
    not_cfg = _not_cfg(ui)

    st.markdown(f"**{_get(ui, 'std_name_label', 'Name')}**: {std.name}")
    st.markdown(
        f"**{_get(ui, 'std_primary_label', 'Primary label')}**: "
        f"{std.primary_statement_label or not_cfg}"
    )
    st.markdown(
        f"**{_get(ui, 'std_secondary_label', 'Secondary label')}**: "
        f"{std.secondary_statement_label or not_cfg}"
    )

    st.markdown(
        f"**{_get(ui, 'std_file_label', 'Standard file')}**: "
        f"`{selected_file.as_posix() if selected_file else not_cfg}`"
    )

    income_mapping_path = (
        std.income_statement_mapping.as_posix()
        if std.income_statement_mapping
        else not_cfg
    )
    st.markdown(
        f"**{_get(ui, 'std_income_mapping_label', 'Income statement mapping')}**: "
        f"`{income_mapping_path}`"
    )
    st.markdown(
        f"**{_get(ui, 'std_secondary_mapping_label', 'Secondary mapping')}**: "
        f"`{std.secondary_mapping.as_posix() if std.secondary_mapping else not_cfg}`"
    )
    st.markdown(
        f"**{_get(ui, 'std_coa_label', 'Chart of accounts')}**: "
        f"`{std.chart_of_accounts.as_posix() if std.chart_of_accounts else not_cfg}`"
    )
    st.markdown(
        f"**{_get(ui, 'std_ratios_rules_label', 'Ratios rules pack')}**: "
        f"`{std.ratios_rules_file.as_posix() if std.ratios_rules_file else not_cfg}`"
    )
    st.markdown(
        f"**{_get(ui, 'std_custom_rules_label', 'Custom ratios pack')}**: "
        f"`{std.ratios_custom_file.as_posix() if std.ratios_custom_file else not_cfg}`"
    )


def _save_configuration(ui: Mapping[str, Any], draft: dict[str, Any]) -> None:
    """
    Patch smb_finsight_config.toml using tomlkit (preserve comments/style).

    Notes:
    - `inputs.*` tables are edited in place to preserve comment blocks and ordering.
    - New keys are appended at the end because tomlkit does not reliably support
      inserting under specific comment headers.
    """
    fy_start: date = draft["fy_start"]
    fy_end: date = draft["fy_end"]
    if fy_start >= fy_end:
        st.error(
            _get(ui, "fy_validation_error", "Start date must be earlier than end date.")
        )
        return

    doc = _read_main_toml_doc()

    # fiscal year
    fy = _ensure_table(doc, "fiscal_year")
    fy["start_date"] = fy_start.isoformat()
    fy["end_date"] = fy_end.isoformat()

    # accounting
    acc = _ensure_table(doc, "accounting")
    acc["currency"] = str(draft["currency"]).upper().strip()
    acc["thousands_separator"] = str(draft["thousands_separator"])

    std_file: Path | None = draft.get("standard_file")
    if std_file:
        acc["standard_config_file"] = _rel_from_repo_root(std_file)

    # database
    db = _ensure_table(doc, "database")
    db["engine"] = "sqlite"
    db_file: Path | None = draft.get("db_file")
    if db_file:
        db["path"] = _rel_from_repo_root(db_file)

    # webui
    w = _ensure_table(doc, "webui")
    layout_file: Path | None = draft.get("layout_file")
    if layout_file:
        w["layout_config_path"] = _rel_from_repo_root(layout_file)

    # inputs (preserve order/comments by editing in place)
    inputs = _ensure_table(doc, "inputs")

    # Get existing tables if present, otherwise create them
    inputs_bs = inputs.get("balance_sheet")
    if inputs_bs is None:
        inputs_bs = tomlkit.table()
        inputs["balance_sheet"] = inputs_bs

    inputs_hr = inputs.get("hr")
    if inputs_hr is None:
        inputs_hr = tomlkit.table()
        inputs["hr"] = inputs_hr

    bs_draft: dict[str, Any] = draft.get("balance_sheet_inputs") or {}
    hr_draft: dict[str, Any] = draft.get("hr_inputs") or {}

    # 1) Update or delete keys that already exist in the TOML (keeps comments/placement)
    for k in list(inputs_bs.keys()):
        v = bs_draft.get(k, None)
        if v is None:
            # remove key -> comment block above remains in place
            inputs_bs.pop(k, None)
        else:
            inputs_bs[k] = float(v)

    for k in list(inputs_hr.keys()):
        v = hr_draft.get(k, None)
        if v is None:
            inputs_hr.pop(k, None)
        else:
            inputs_hr[k] = float(v)

    # 2) Add new keys (those not already in TOML) at the end
    # (tomlkit can’t reliably “insert under the right comment header” without
    # extra work)
    for k, v in bs_draft.items():
        if v is None:
            continue
        if k not in inputs_bs:
            inputs_bs[k] = float(v)

    for k, v in hr_draft.items():
        if v is None:
            continue
        if k not in inputs_hr:
            inputs_hr[k] = float(v)

    _write_main_toml_doc(doc)
    st.toast(_get(ui, "save_success", "Configuration saved."))


# ----------------------------
# DB creation dialog
# ----------------------------


def _ensure_sqlite_ext(filename: str) -> str:
    """
    Ensure the provided filename ends with a .sqlite extension.
    """
    fn = filename.strip()
    if not fn.lower().endswith(".sqlite"):
        fn = f"{fn}.sqlite"
    return fn


def _open_new_db_dialog(ui: Mapping[str, Any], draft: dict[str, Any]) -> None:
    """
    Open a Streamlit dialog allowing users to create a new SQLite database file.

    If "Switch now" is enabled, updates the draft and the selectbox state so the
    newly created DB becomes the active selection immediately.
    """

    @st.dialog(_get(ui, "db_new_button", "New"))
    def _dialog() -> None:
        filename = st.text_input(
            _get(ui, "db_new_filename_label", "Filename"),
            value="",
            key="cfg_db_new_filename",
        )
        switch_now = st.toggle(
            _get(ui, "db_new_switch_now", "Switch now"),
            value=True,
            key="cfg_db_new_switch_now",
        )

        if st.button(_get(ui, "db_new_create_button", "Create"), type="primary"):
            if not filename.strip():
                st.error(
                    _get(
                        ui,
                        "db_new_validation_error",
                        "Please provide a filename.",
                    )
                )
                st.stop()

            fn = _ensure_sqlite_ext(filename)
            new_path = (DB_DIR / fn).resolve()

            init_database(DatabaseConfig(engine="sqlite", path=new_path))

            st.success(_get(ui, "db_new_created_success", "Database created."))

            if switch_now:
                # Update draft and the DB selectbox widget state immediately
                draft["db_file"] = new_path
                st.session_state["cfg_db_file"] = new_path.name

            # Clean dialog-specific state (optional)
            st.session_state.pop("cfg_db_new_filename", None)
            st.session_state.pop("cfg_db_new_switch_now", None)

            st.rerun()

    _dialog()


# ----------------------------
# Render entry point
# ----------------------------


def render(app_config: AppConfig, layout: LayoutConfig, page: PageConfig) -> None:
    """
    Render the Configuration page.

    The page edits settings through a `draft` dict stored in Streamlit session_state.
    Saving applies the draft to `smb_finsight_config.toml` (tomlkit patch) and leaves
    the actual application reload behavior to the app-level config loader.

    Sections:
    - Fiscal year
    - Database selection / creation
    - Layout selection
    - Formatting (currency, thousands separator)
    - Accounting standard selection + details preview
    - Optional numeric inputs (balance sheet, HR)
    """
    st.title(_get(page, "title", "Configuration"))

    ui = _to_mapping(page.ui)

    if "config_draft" not in st.session_state:
        st.session_state["config_draft"] = _init_draft(app_config)

    # Draft persists across reruns; it contains the user's pending edits.
    # Widget states are initialized once from draft, then widgets drive draft updates.
    draft: dict[str, Any] = st.session_state["config_draft"]

    c1, c2 = st.columns([0.8, 0.2], gap="large")
    with c1:
        # Snapshot of current config (non-editable) at the top for context.
        st.info(
            f"{_get(ui, 'snapshot_standard', 'Standard')}: "
            f"{app_config.standard_config.name}"
            f"   •   {_get(ui, 'snapshot_fiscal_year', 'Fiscal year')}: "
            f"{_format_fy(draft['fy_start'], draft['fy_end'])}"
            f"   •   {_get(ui, 'snapshot_currency', 'Currency')}: "
            f"{draft['currency']}",
            icon="ℹ️",
        )
    with c2:
        # Save (top)
        st.button(
            _get(ui, "save_top", "Save configuration"),
            type="primary",
            on_click=_save_configuration,
            args=(ui, draft),
            width="stretch",
            key="save_top",
        )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        # 1) Fiscal Year
        with st.container(border=True, height="stretch"):
            st.subheader(_get(ui, "section_fiscal_year", "Fiscal Year"))
            # c1, c2 = st.columns(2)
            draft["fy_start"] = st.date_input(
                _get(ui, "fy_start_label", "Start date"), value=draft["fy_start"]
            )
            draft["fy_end"] = st.date_input(
                _get(ui, "fy_end_label", "End date"), value=draft["fy_end"]
            )
            if draft["fy_start"] >= draft["fy_end"]:
                st.error(
                    _get(
                        ui,
                        "fy_validation_error",
                        "Start date must be earlier than end date.",
                    )
                )

    with c2:
        # 2) Database
        with st.container(border=True, height="stretch"):
            st.subheader(_get(ui, "section_database", "Database"))

            a1, a2 = st.columns([0.3, 0.7])
            a1.text_input(
                _get(ui, "db_engine_label", "Engine"), value="sqlite", disabled=True
            )

            db_files = [p.resolve() for p in _scan_sqlite(DB_DIR)]
            if not db_files:
                a2.warning(f"No .sqlite files found in {DB_DIR.as_posix()}/")
            else:
                labels = [p.name for p in db_files]

                if "cfg_db_file" not in st.session_state:
                    # init once from draft
                    st.session_state["cfg_db_file"] = (
                        draft.get("db_file") or db_files[0]
                    ).name

                # If the currently selected value is not in the options anymore,
                # fall back to draft if possible, otherwise first option.
                if st.session_state["cfg_db_file"] not in labels:
                    fallback = (
                        draft.get("db_file").name if draft.get("db_file") else labels[0]
                    )
                    st.session_state["cfg_db_file"] = (
                        fallback if fallback in labels else labels[0]
                    )

                chosen = a2.selectbox(
                    _get(ui, "db_selector_label", "Database file"),
                    options=labels,
                    key="cfg_db_file",
                )
                draft["db_file"] = next(p for p in db_files if p.name == chosen)

            if st.button(_get(ui, "db_new_button", "New"), width="stretch"):
                _open_new_db_dialog(ui, draft)

    with c3:
        # 3) Layout
        with st.container(border=True, height="stretch"):
            st.subheader(_get(ui, "section_layout", "Layout"))

            layout_files = [p.resolve() for p in _scan_toml(LAYOUTS_DIR)]
            if not layout_files:
                st.warning(f"No layout files found in {LAYOUTS_DIR.as_posix()}/")
            else:
                layout_labels = [p.name for p in layout_files]

                # Init widget state ONCE from draft (or fallback)
                if "cfg_layout_file" not in st.session_state:
                    current = (draft.get("layout_file") or layout_files[0]).resolve()
                    st.session_state["cfg_layout_file"] = (
                        current.name
                        if current.name in layout_labels
                        else layout_labels[0]
                    )

                chosen = st.selectbox(
                    _get(ui, "layout_selector_label", "Layout configuration"),
                    options=layout_labels,
                    key="cfg_layout_file",
                )
                draft["layout_file"] = next(p for p in layout_files if p.name == chosen)

    with c4:
        # 4) Formatting
        with st.container(border=True, height="stretch"):
            st.subheader(_get(ui, "section_formatting", "Formatting"))

            draft["currency"] = _selectbox_bound(
                key="cfg_currency",
                label=_get(ui, "currency_label", "Currency"),
                options=["CAD", "USD", "EUR"],
                draft=draft,
                draft_field="currency",
            )
            draft["thousands_separator"] = _selectbox_bound(
                key="cfg_thousands_sep",
                label=_get(ui, "thousands_separator_label", "Thousands separator"),
                options=[",", " "],
                draft=draft,
                draft_field="thousands_separator",
            )

    # 5) Accounting Standard
    with st.container(border=True):
        st.subheader(_get(ui, "section_standard", "Accounting Standard"))

        standard_files = [p.resolve() for p in _scan_toml(STANDARDS_DIR)]
        if not standard_files:
            st.warning(f"No standard files found in {STANDARDS_DIR.as_posix()}/")
        else:
            # Build labels from parsed StandardConfig.name (robust)
            base_dir = MAIN_CONFIG_FILE.resolve().parent
            labels: list[str] = []

            # Parse the selected standard to show a live preview.
            # On failure, fall back to the current app standard to keep the page usable.
            for p in standard_files:
                try:
                    std_cfg = _parse_standard_config(
                        str(p.relative_to(base_dir)), base_dir=base_dir
                    )
                    labels.append(std_cfg.name)
                except Exception:  # noqa: BLE001
                    labels.append(p.name)

            # We store the selected file name in session_state to keep it stable and
            # unambiguous.
            file_names = [p.name for p in standard_files]

            if "cfg_standard_file" not in st.session_state:
                current = (draft.get("standard_file") or standard_files[0]).resolve()
                st.session_state["cfg_standard_file"] = (
                    current.name if current.name in file_names else file_names[0]
                )

            fname_to_label = {p.name: labels[i] for i, p in enumerate(standard_files)}

            d1, d2, d3, d4 = st.columns(4)
            with d1:
                chosen_fname = st.selectbox(
                    _get(ui, "std_selector_label", "Standard configuration"),
                    options=file_names,
                    key="cfg_standard_file",
                    format_func=lambda fn: fname_to_label.get(fn, fn),
                )

            with d2:
                st.space()
            with d3:
                st.space()
            with d4:
                st.space()

            chosen_file = next(p for p in standard_files if p.name == chosen_fname)
            draft["standard_file"] = chosen_file

            # Preview the selected standard (parse using existing parser)
            try:
                std_preview = _parse_standard_config(
                    standard_config_path_raw=str(chosen_file.relative_to(base_dir)),
                    base_dir=base_dir,
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to parse selected standard file: {chosen_file.name}")
                st.exception(exc)
                std_preview = app_config.standard_config

            with st.expander(
                f"**{_get(ui, 'std_details_title', 'Selected standard details')}**"
            ):
                _render_standard_details(ui, std_preview, chosen_file)

    # 6) Inputs
    with st.container(border=True):
        st.subheader(_get(ui, "section_inputs", "Inputs"))

        inputs_ui = _to_mapping(_get(ui, "inputs", {}))
        bs_labels = _to_mapping(_get(inputs_ui, "balance_sheet_labels", {}))
        hr_labels = _to_mapping(_get(inputs_ui, "hr_labels", {}))

        # Canonical list of fields to display comes from layout labels.
        bs_keys = list(bs_labels.keys())
        hr_keys = list(hr_labels.keys()) or ["average_headcount"]  # fallback

        # Ensure draft dicts exist and include all keys with Optional[float] values
        bs_inputs: dict[str, float | None] = draft.get("balance_sheet_inputs") or {}
        hr_inputs: dict[str, float | None] = draft.get("hr_inputs") or {}

        for k in bs_keys:
            bs_inputs.setdefault(k, None)
        for k in hr_keys:
            hr_inputs.setdefault(k, None)

        # Reset -> set all to None and clear widget states
        if st.button(_get(ui, "inputs_reset_button", "Reset inputs")):
            for k in bs_keys:
                bs_inputs[k] = None
                st.session_state.pop(f"cfg_bs_{k}", None)
            for k in hr_keys:
                hr_inputs[k] = None
                st.session_state.pop(f"cfg_hr_{k}", None)
            st.info(_get(ui, "inputs_reset_confirm", "Inputs cleared (not saved yet)."))
            st.rerun()

        st.markdown(f"**{_get(ui, 'bs_title', 'Balance sheet inputs')}**")

        cols = st.columns(4)
        for i, k in enumerate(bs_keys):
            label = _get(bs_labels, k, _humanize_key(k))
            widget_key = f"cfg_bs_{k}"

            # Initialize widget state once from draft
            if widget_key not in st.session_state:
                st.session_state[widget_key] = bs_inputs.get(k, None)

            val = cols[i % 4].number_input(
                label,
                min_value=0.0,
                step=100.0,
                key=widget_key,
            )
            bs_inputs[k] = val  # val may be None

        st.markdown(f"**{_get(ui, 'hr_title', 'HR inputs')}**")

        e1, e2, e3, e4 = st.columns(4)
        with e1:
            for k in hr_keys:
                label = _get(hr_labels, k, _humanize_key(k))
                widget_key = f"cfg_hr_{k}"

                if widget_key not in st.session_state:
                    st.session_state[widget_key] = hr_inputs.get(k, None)

                val = st.number_input(
                    label,
                    min_value=0.0,
                    step=0.5,
                    key=widget_key,
                )
                hr_inputs[k] = val  # val may be None

        with e2:
            st.space()
        with e3:
            st.space()
        with e4:
            st.space()

        # Persist back to draft
        draft["balance_sheet_inputs"] = bs_inputs
        draft["hr_inputs"] = hr_inputs

    f1, f2 = st.columns([0.8, 0.2], gap="large")
    with f1:
        st.space()
    with f2:
        # Save (bottom)
        st.button(
            _get(ui, "save_bottom", "Save configuration"),
            type="primary",
            on_click=_save_configuration,
            args=(ui, draft),
            width="stretch",
            key="save_bottom",
        )

    st.session_state["config_draft"] = draft
