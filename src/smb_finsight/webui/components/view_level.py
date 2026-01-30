# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
View-level selector component for Web UI pages.

This component renders a selectbox allowing the user to choose
the level of detail for a page (e.g. simplified, regular, detailed, complete).

The control is driven by page.ui configuration and page.default_view.
"""

from collections.abc import Mapping

import streamlit as st

from smb_finsight.webui.layout import PageConfig
from smb_finsight.webui.utils import _to_mapping

_ALLOWED_VIEWS = ("simplified", "regular", "detailed", "complete")


def render_view_level_control(*, page: PageConfig) -> str:
    """
    Render a view-level selector and return the selected view.

    Args:
        page: Parsed PageConfig for the current page.

    Returns:
        The selected view level (lowercase string).
    """
    ui: Mapping[str, str] = _to_mapping(page.ui)

    label = ui.get("label_view", "View level")
    help_text = ui.get("help_view", "")
    view_labels = _to_mapping(ui.get("view_labels", {}))

    default_view = (page.default_view or "regular").strip().lower()
    if default_view not in _ALLOWED_VIEWS:
        default_view = "regular"

    index = _ALLOWED_VIEWS.index(default_view)

    def _fmt(value: str) -> str:
        return str(view_labels.get(value, value.capitalize()))

    selected = st.selectbox(
        label,
        options=_ALLOWED_VIEWS,
        index=index,
        format_func=_fmt,
        help=help_text,
    )

    return str(selected).lower()
