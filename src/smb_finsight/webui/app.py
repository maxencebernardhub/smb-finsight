# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

# src/smb_finsight/webui/app.py
# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (...)
# Licensed under the MIT License.

"""
Streamlit application entry point for SMB FinSight Web UI.

This module:
- loads the global application configuration (AppConfig),
- loads the layout configuration (LayoutConfig),
- constructs a dynamic sidebar navigation based on the layout pages,
- dispatches page rendering to the corresponding page modules.

The actual page implementations live in `smb_finsight/webui/pages/*`
and expose a single public function:

    def render(app_config: AppConfig, layout: LayoutConfig, page: PageConfig) -> None

The Web UI remains a thin layer that reuses the core computation engine
and configuration logic from the `smb_finsight` package.
"""

from pathlib import Path

import streamlit as st

from smb_finsight import __version__ as package_version
from smb_finsight.config import load_app_config
from smb_finsight.entries_service import get_duplicate_stats, get_entries_count
from smb_finsight.webui.layout import (
    LayoutConfig,
    PageConfig,
    load_layout_config,
)

# ---------------------------------------------------------------------------
# Local CSS file loader
# ---------------------------------------------------------------------------


def load_local_css() -> None:
    """
    Load local CSS file (style.css) to customize the Web UI look and feel.

    This function is intentionally simple: if the CSS file is present
    next to this module, it will be injected into the Streamlit app
    using a <style> tag.
    """
    css_path = Path(__file__).with_name("style.css")
    if css_path.is_file():
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Internal helper to load a page module dynamically
# ---------------------------------------------------------------------------


def _load_page_module(page_id: str):
    """
    Attempt to import the module for a given page.

    Expected module path:
        smb_finsight.webui.pages.<page_id>

    The module must define:
        def render(app_config, layout, page_config) -> None

    Args:
        page_id: The identifier of the page (e.g., "dashboard", "entries").

    Returns:
        The imported module object.

    Raises:
        ImportError: If the module does not exist or cannot be imported.
    """
    module_path = f"smb_finsight.webui.webui_pages.{page_id}"
    try:
        module = __import__(module_path, fromlist=["render"])
    except Exception as exc:  # noqa: BLE001
        msg = f"Page module '{module_path}' could not be imported."
        raise ImportError(msg) from exc

    if not hasattr(module, "render"):
        msg = f"Page module '{module_path}' does not define a 'render()' function."
        raise ImportError(msg)

    return module


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Main entry point for the SMB FinSight Web UI.

    Steps:
    1. Load global AppConfig (engine configuration, standard config,
    fiscal year, paths...)
    2. Resolve layout config path from AppConfig and load LayoutConfig.
    3. Build Streamlit sidebar navigation from LayoutConfig.pages.
    4. Dispatch rendering to the selected page module.
    """
    st.set_page_config(page_title="SMB FinSight", layout="wide")

    # -----------------------------
    # Step 1: Load custom CSS for sidebar and other visual tweaks.
    # -----------------------------
    load_local_css()

    # -----------------------------
    # Step 2: Load application config
    # -----------------------------
    app_config = load_app_config()

    # -----------------------------
    # Step 3: Load layout config
    # -----------------------------
    layout_path = Path(app_config.webui_layout_config_path)
    layout: LayoutConfig = load_layout_config(layout_path)

    # -----------------------------
    # Sidebar: header + navigation
    # -----------------------------
    st.sidebar.title("SMB FinSight")

    pages = layout.pages  # mapping {page_id: PageConfig}
    page_ids = list(pages.keys())

    # Determine default page:
    default_page_id = layout.meta.default_page
    if default_page_id not in pages:
        default_page_id = page_ids[0]  # fallback to first page

    # Sidebar navigation
    selected_page_id = st.sidebar.radio(
        label="Navigation",
        options=page_ids,
        format_func=lambda pid: f"{pages[pid].icon}  {pages[pid].title}"
        if pages[pid].icon
        else pages[pid].title,
        index=page_ids.index(default_page_id),
        label_visibility="collapsed",  # hide the label from the UI
        width="stretch",  # <-- NEW: make the widget use full sidebar width
    )

    st.sidebar.space(size="medium")

    # Sidebar footer: version, standard, database status, docs, copyright ---

    entries_count = 0  # TODO: wire this to a real DB helper for the Web UI

    with st.sidebar.container(key="sidebar_footer"):
        # Version (from package metadata)
        st.caption(f"Version {package_version}", text_alignment="center")

        # Active accounting standard (raw value from AppConfig.standard)
        st.caption(
            f"Standard: {app_config.standard_config.name}", text_alignment="center"
        )

        # Database status: get entries count and duplicate entries
        entries_count = get_entries_count(app_config)
        dup_stats = get_duplicate_stats(app_config)

        st.caption(f"Database entries: {entries_count:,}", text_alignment="center")
        st.caption(f"Duplicate entries: {dup_stats.pending:,}", text_alignment="center")

        # Documentation reference (can be plain text for now)
        st.markdown(
            "[Docs: README](https://github.com/maxencebernardhub/smb-finsight#readme)",
            unsafe_allow_html=False,
            text_alignment="center",
        )
        # st.caption("Docs: README · Release notes", text_alignment="center")

        # Copyright
        st.caption("© 2026 SMB FinSight", text_alignment="center")

    # -----------------------------
    # Step 4: Load and render the selected page
    # -----------------------------
    page_cfg: PageConfig = pages[selected_page_id]

    try:
        module = _load_page_module(page_cfg.id)
        module.render(app_config=app_config, layout=layout, page=page_cfg)
    except ImportError as exc:
        st.error(f"Failed to load page '{page_cfg.id}': {exc}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
