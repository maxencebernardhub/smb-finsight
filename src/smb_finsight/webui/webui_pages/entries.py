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

Current scope in this file:
- Render the 4 controlled sub-views selector:
  - Entries
  - Import
  - Duplicates (N)
  - Recycle bin

"""

import streamlit as st

from smb_finsight.config import AppConfig
from smb_finsight.entries_service import (
    get_duplicate_stats,
)
from smb_finsight.webui.components.duplicates_subview import (
    render_duplicates_subview,
)
from smb_finsight.webui.components.entries_subview import render_entries_subview
from smb_finsight.webui.components.import_subview import render_import_subview
from smb_finsight.webui.components.recycle_bin_subview import render_recycle_bin_subview
from smb_finsight.webui.components.subview_selector import (
    render_entries_subview_selector,
)
from smb_finsight.webui.layout import LayoutConfig, PageConfig
from smb_finsight.webui.utils import _get, _to_mapping

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
    Notes:
        This function orchestrates navigation and delegates UI rendering to sub-view
        components. Database operations (e.g., CSV import) are executed inside the
        corresponding sub-view modules.

    """

    st.title(_get(page, "title", "Entries"))

    # UI labels are stored in page.ui
    ui = _to_mapping(_get(page, "ui", {}))

    # Count duplicates for the selector label "Duplicates (N)"
    # Note: we use pending duplicates to reflect the operational workload.
    dup_stats = get_duplicate_stats(app_config)
    duplicates_count = int(getattr(dup_stats, "pending", 0))

    subview = render_entries_subview_selector(ui=ui, duplicates_count=duplicates_count)

    # ---------------------------------------------------------------------
    # Controlled sub-view rendering:
    # Only the selected sub-view is rendered to avoid computing all views on each rerun.
    # ---------------------------------------------------------------------
    if subview == "entries":
        render_entries_subview(
            app_config=app_config,
            layout=layout,
            page=page,
            ui=ui,
        )
        return

    if subview == "import":
        render_import_subview(
            app_config=app_config,
            layout=layout,
            page=page,
            ui=ui,
        )
        return

    if subview == "duplicates":
        render_duplicates_subview(
            app_config=app_config,
            layout=layout,
            page=page,
            ui=ui,
        )
        return

    if subview == "recycle_bin":
        render_recycle_bin_subview(
            app_config=app_config,
            layout=layout,
            page=page,
            ui=ui,
        )
        return

    # Safety fallback
    st.warning("Unknown sub-view selected. Falling back to Entries.")
