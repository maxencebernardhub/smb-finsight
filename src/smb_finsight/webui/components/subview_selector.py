# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Entries page sub-view selector component.

This module provides a small, reusable UI component used by the Entries page
to select the active sub-view ("entries", "import", "duplicates", "recycle_bin")
while keeping Streamlit's rendering controlled (conditional rendering).

We intentionally avoid st.tabs() because Streamlit computes all tab contents on
each rerun. Using a segmented control (or pills/selectbox fallback) ensures that
only the active sub-view code path runs, reducing unnecessary work and limiting
regression risk when sub-views grow.
"""

from typing import Any

import streamlit as st


def render_entries_subview_selector(
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
