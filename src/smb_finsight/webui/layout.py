# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Layout configuration loader for the SMB FinSight Web UI.

This module is responsible for:
- loading the Web UI layout configuration from a TOML file,
- validating the high-level structure of the layout,
- exposing typed dataclasses used by the Streamlit pages.

The layout TOML file defines:
- page metadata (titles, icons, default periods),
- dashboard tiles and charts (measures & ratios),
- ratios/KPIs metrics and charts,
- statements, entries, duplicates and import/config behaviour.

It is intentionally separate from the core engine configuration (see
:mod:`smb_finsight.config`) so that the Web UI remains a thin, user-configurable
layer on top of the existing computation engine.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older Python
    import tomli as tomllib  # type: ignore[import]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LayoutConfigError(ValueError):
    """
    Error raised when the Web UI layout configuration is invalid.

    This is a dedicated exception type to distinguish layout issues from
    generic ValueError / IO errors in higher layers.
    """


# ---------------------------------------------------------------------------
# Dataclasses describing the layout structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetaConfig:
    """
    Metadata for the Web UI layout configuration.

    Attributes:
        id: Identifier of this layout configuration (e.g. "default_en").
        schema_version: Version of the layout schema expected by the Web UI
            (e.g. "0.5.0").
        language: Main language of labels and titles in this layout
            (e.g. "en", "fr").
        default_page: Page opened by default when the Web UI starts.
            Typically one of: "dashboard", "statements", "ratios",
            "entries", "duplicates", "import_config".
    """

    id: str
    schema_version: str
    language: str
    default_page: str


@dataclass(frozen=True)
class PagePeriodsConfig:
    """
    Default period presets configuration for a given page.

    These presets are used as defaults when the user first opens the page.
    Individual tiles/charts may override these defaults.

    Attributes:
        default_primary_preset:
            Identifier of the default primary period preset
            (e.g. "FY", "YTD", "MTD", "LAST_MONTH").
        default_comparison_preset:
            Identifier of the default secondary period preset used for
            comparison (e.g. "FY_PREV", "YTD_PREV_FY"). May be an empty
            string if the page does not use a default comparison.
        default_granularity:
            Default sub-period granularity for charts (e.g. "DAY", "WEEK",
            "MONTH", "QUARTER", "FY"). Not all pages need to use this.
        allowed_granularities:
            Sequence of granularities allowed on this page. An empty
            sequence means "no explicit restriction" and the Web UI may
            choose sensible defaults.
        primary_preset_labels:
            Optional mapping from primary period preset codes (e.g. "FY") to
            user-facing labels (e.g. "Current fiscal year").
            Used to display friendly labels in dropdowns.
        comparison_preset_labels:
            Optional mapping from comparison period preset codes (e.g. "PREV_FY") to
            user-facing labels (e.g. "Previous fiscal year").
            Used to display friendly labels in dropdowns.
        granularity_labels:
            Optional mapping from granularity codes (e.g. "MONTH") to
            user-facing labels (e.g. "Month").
            Used to display friendly labels in dropdowns.
        user_presets:
            Optional mapping of user-defined presets.
            Format:
                {
                    "Q4_2025": {"label": "Q4 2025", "start": "2025-10-01",
                    "end": "2025-12-31"},
                    ...
                }
            Keys are preset identifiers used in dropdowns.
            Values are ISO date strings and a UI label.


    """

    default_primary_preset: str
    default_comparison_preset: str
    default_granularity: Optional[str]
    allowed_granularities: Sequence[str]
    primary_preset_labels: Mapping[str, str] = field(default_factory=dict)
    comparison_preset_labels: Mapping[str, str] = field(default_factory=dict)
    granularity_labels: Mapping[str, str] = field(default_factory=dict)
    user_presets: Mapping[str, Mapping[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class PageConfig:
    """
    Top-level configuration of a single Web UI page.

    Attributes:
        id: Internal identifier of the page (e.g. "dashboard").
        title: Human-readable title displayed in navigation and headers.
        icon: Optional emoji/icon used in navigation (may be an empty string).
        allow_secondary_period:
            Whether the UI should show controls for selecting a secondary
            comparison period on this page.
        periods: Default period presets for this page, or None if the page
            does not use periods directly.
        ui:
            Optional mapping of user-facing strings for that page
            (section headers, control labels, messages). This enables
            localization via the layout TOML file.

    """

    id: str
    title: str
    icon: str
    allow_secondary_period: bool
    periods: Optional[PagePeriodsConfig]
    ui: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DashboardTileConfig:
    """
    Configuration for a single Dashboard tile (metric card).

    Attributes:
        id: Unique identifier of the tile within the dashboard.
        source:
            Data source type: "measure", "ratio" or "system".
            - "measure": canonical or derived measures (revenue, gross_margin).
            - "ratio": ratios defined in ratios_*.toml.
            - "system": internal values (e.g. duplicates counters).
        key:
            Identifier of the measure/ratio/system value to display.
        label:
            Human-readable label shown on the tile.
        format:
            UI formatting hint: "amount", "percent", "number", or an empty
            string to indicate that the Web UI should infer the format from
            the underlying unit.
        period_preset:
            Optional override of the page's default primary period preset
            (empty string means "use page default").
        comparison_preset:
            Optional override of the page's default secondary period preset
            (empty string means "use page default").
        show_delta_abs:
            Whether to display the absolute difference vs the comparison
            period (in amount/points).
        show_delta_pct:
            Whether to display the relative difference vs the comparison
            period (percentage change).
        delta_good_direction:
            "up" (default) or "down". Controls st.metric delta_color
            ("normal" vs "inverse").
        tooltip_from:
            Source for tooltip text: "measure_notes", "ratio_notes" or
            "none". The Web UI uses this to decide whether and where to
            fetch explanatory notes for the tile.
    """

    id: str
    source: str
    key: str
    label: str
    format: str
    period_preset: str
    comparison_preset: str
    show_delta_abs: bool
    show_delta_pct: bool
    delta_good_direction: str = "up"
    tooltip_from: str = "none"


@dataclass(frozen=True)
class ChartSeriesConfig:
    """
    Configuration for a single data series within a chart.

    Attributes:
        source: "measure" or "ratio".
        key: Identifier of the measure/ratio to plot.
        label: Label used in the chart legend.
    """

    source: str
    key: str
    label: str


@dataclass(frozen=True)
class DashboardChartConfig:
    """
    Configuration for a single Dashboard chart.

    Attributes:
        id: Unique identifier of the chart.
        type: Chart type, typically "line" or "bar".
        title: Human-readable title displayed above the chart.
        period_preset:
            Primary period preset used for this chart. If empty, falls back
            to the page-level default.
        comparison_preset:
            Optional secondary period preset used for comparison. If empty,
            falls back to the page-level default.
        default_granularity:
            Default sub-period granularity for this chart
            (e.g. "DAY", "WEEK", "MONTH", "QUARTER", "FY").
        allowed_granularities:
            Sequence of granularities allowed for this chart. An empty
            sequence means "no explicit restriction".
        series:
            Sequence of :class:`ChartSeriesConfig` describing each plotted
            measure/ratio.
    """

    id: str
    type: str
    title: str
    period_preset: str
    comparison_preset: str
    default_granularity: Optional[str]
    allowed_granularities: Sequence[str]
    series: Sequence[ChartSeriesConfig]


@dataclass(frozen=True)
class DashboardConfig:
    """
    Dashboard configuration loaded from the [dashboard] section.

    Attributes:
        allow_secondary_period:
            Whether the Dashboard page allows a comparison period.
            This is a dashboard-level capability flag.
        tiles:
            Sequence of dashboard tile configurations.
        charts:
            Sequence of dashboard chart configurations.
    """

    allow_secondary_period: bool
    tiles: Sequence[DashboardTileConfig]
    charts: Sequence[DashboardChartConfig]


@dataclass(frozen=True)
class RatiosMetricConfig:
    """
    Configuration for a single metric tile on the Ratios & KPIs page.

    Attributes:
        id: Unique identifier of the metric tile.
        source:
            Data source type: typically "ratio", but may also be "measure"
            if some measures are displayed on the ratios page.
        key:
            Identifier of the ratio/measure.
        label:
            Human-readable label shown on the tile.
        format:
            UI formatting hint: "percent", "amount", "number", or empty for
            auto-detection based on unit.
        comparison:
            Whether this metric should use the secondary period when it is
            enabled on the page.
        show_delta_abs:
            Whether to show the absolute delta vs the secondary period
            (for percentages this is typically "points").
        show_delta_pct:
            Whether to show the relative change (%) vs the secondary period.
        tooltip_from:
            Source for tooltip text: "ratio_notes", "measure_notes" or
            "none".
        period_preset:
            Optional override of the page default primary period preset
            (empty string -> use page default).
        comparison_preset:
            Optional override of the page default secondary period preset
            (empty string -> use page default).
    """

    id: str
    source: str
    key: str
    label: str
    format: str
    comparison: bool
    show_delta_abs: bool
    show_delta_pct: bool
    tooltip_from: str
    period_preset: str
    comparison_preset: str


@dataclass(frozen=True)
class RatiosChartConfig:
    """
    Configuration for a single chart on the Ratios & KPIs page.

    Attributes:
        id: Unique identifier of the chart.
        type: Chart type ("bar", "line", etc.).
        title: Title displayed above the chart.
        period_preset:
            Primary period preset used for this chart (empty -> page default).
        comparison_preset:
            Secondary period preset used for this chart (empty -> page default).
        series:
            Sequence of :class:`ChartSeriesConfig` describing the plotted
            ratios/measures.
    """

    id: str
    type: str
    title: str
    period_preset: str
    comparison_preset: str
    series: Sequence[ChartSeriesConfig]


@dataclass(frozen=True)
class StatementsPageConfig:
    """
    Configuration options for the Statements page.

    Attributes:
        show_delta_columns:
            In comparison mode, whether to show delta (absolute/percent)
            columns in addition to the two period amounts.
        hide_zero_lines_in_comparison:
            If True, hide lines where both periods are zero (and therefore
            the delta is also zero).
        hide_zero_lines_single_period:
            If True, hide zero lines even in single-period mode; if False,
            always show the full statement structure.
    """

    show_delta_columns: bool
    hide_zero_lines_in_comparison: bool
    hide_zero_lines_single_period: bool


@dataclass(frozen=True)
class EntriesFiltersConfig:
    """
    Default filter behaviour for the Entries page.

    Attributes:
        default_period_preset:
            Default period preset used when opening the Entries page.
        show_deleted_by_default:
            Whether deleted entries should be included in the initial view.
    """

    default_period_preset: str
    show_deleted_by_default: bool


@dataclass(frozen=True)
class EntriesManualEntryConfig:
    """
    Behaviour of manual entry creation/editing on the Entries page.

    Attributes:
        input_mode:
            How amounts are entered:
            - "amount": single signed amount field (positive/negative).
            - "debit_credit": two fields for debit and credit.
        require_known_account:
            If True, the Web UI should block save when the account code
            does not exist in the current chart of accounts. If False, the
            UI may allow the entry and rely on other mechanisms to flag
            unknown accounts.
    """

    input_mode: str
    require_known_account: bool


@dataclass(frozen=True)
class EntriesPageConfig:
    """
    Configuration for the Entries page.

    Attributes:
        columns:
            Sequence of column identifiers to display in the main entries
            table (e.g. "date", "account_code", "description", "amount").
        filters:
            Default filter behaviour.
        manual_entry:
            Behaviour for manual creation/editing of entries.
    """

    columns: Sequence[str]
    filters: EntriesFiltersConfig
    manual_entry: EntriesManualEntryConfig


@dataclass(frozen=True)
class DuplicatesPageConfig:
    """
    Configuration for the Duplicates page.

    Attributes:
        default_status_filter:
            Default status filter when opening the page
            ("pending", "kept", "discarded").
        show_stats_tiles:
            Whether to display tiles summarising duplicates counts.
        show_nav_badge_when_pending:
            Whether to show a visual indicator in the navigation when
            there are pending duplicates.
        nav_badge_label:
            Optional text used inside the navigation badge (e.g. "•" or "!").
    """

    default_status_filter: str
    show_stats_tiles: bool
    show_nav_badge_when_pending: bool
    nav_badge_label: str


@dataclass(frozen=True)
class ImportConfigPageConfig:
    """
    Configuration for the Import & Configuration page.

    Attributes:
        input_dir:
            Directory (relative to the project root) where CSV files are
            stored/read from.
        on_existing_filename:
            Behaviour when uploading a file whose name already exists in
            the input directory: "ask", "overwrite", "keep_both" or "skip".
        show_existing_files_selector:
            Whether to show a drop-down list of existing CSV files so the
            user can re-import them directly from the Web UI.
    """

    input_dir: str
    on_existing_filename: str
    show_existing_files_selector: bool


@dataclass(frozen=True)
class LayoutConfig:
    """
    Aggregated Web UI layout configuration.

    This is the main object returned by :func:`load_layout_config` and
    consumed by the Web UI (Streamlit app).

    Attributes:
        meta:
            High-level metadata about the layout (id, schema_version,
            language, default_page).
        pages:
            Mapping from page id to :class:`PageConfig`.
        dashboard:
            Dashboard page configuration (allow_secondary_period, tiles, charts)
            loaded from the [dashboard] section.
        dashboard_tiles:
            (Legacy) Same as `dashboard.tiles`. Kept for backward compatibility.
        dashboard_charts:
            (Legacy) Same as `dashboard.charts`. Kept for backward compatibility.
        ratios_metrics:
            Sequence of metric tiles for the Ratios & KPIs page.
        ratios_charts:
            Sequence of charts for the Ratios & KPIs page.
        statements:
            Statements page specific options.
        entries:
            Entries page specific options.
        duplicates:
            Duplicates page specific options.
        import_config:
            Import & Configuration page specific options.
    """

    meta: MetaConfig
    pages: Mapping[str, PageConfig]
    dashboard: DashboardConfig
    dashboard_tiles: Sequence[DashboardTileConfig]  # legacy
    dashboard_charts: Sequence[DashboardChartConfig]  # legacy
    ratios_metrics: Sequence[RatiosMetricConfig]
    ratios_charts: Sequence[RatiosChartConfig]
    statements: StatementsPageConfig
    entries: EntriesPageConfig
    duplicates: DuplicatesPageConfig
    import_config: ImportConfigPageConfig


# ---------------------------------------------------------------------------
# Internal helpers for parsing sections
# ---------------------------------------------------------------------------


def _expect_table(data: Any, section: str) -> Mapping[str, Any]:
    """
    Ensure that a given section is a TOML table (mapping).

    Args:
        data: Parsed TOML subsection.
        section: Name of the section for error reporting.

    Returns:
        The data cast as a mapping.

    Raises:
        LayoutConfigError: if the section is not a mapping.
    """
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise LayoutConfigError(f"Section [{section}] must be a table.")
    return data


def _get_str(table: Mapping[str, Any], key: str, default: str = "") -> str:
    """Return a string value from a mapping, with a default fallback."""
    value = table.get(key, default)
    return str(value) if value is not None else default


def _get_bool(table: Mapping[str, Any], key: str, default: bool = False) -> bool:
    """Return a boolean value from a mapping, with a default fallback."""
    value = table.get(key, default)
    return bool(value)


def _get_str_list(table: Mapping[str, Any], key: str) -> list[str]:
    """
    Return a list of strings from a mapping.

    If the key is missing or the value is not a list, an empty list is
    returned to keep the loader tolerant.
    """
    value = table.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(v) for v in value]


def _parse_meta(root: Mapping[str, Any]) -> MetaConfig:
    meta_tbl = _expect_table(root.get("meta"), "meta")
    return MetaConfig(
        id=_get_str(meta_tbl, "id", "default"),
        schema_version=_get_str(meta_tbl, "schema_version", ""),
        language=_get_str(meta_tbl, "language", "en"),
        default_page=_get_str(meta_tbl, "default_page", "dashboard"),
    )


def _parse_page_periods(tbl: Mapping[str, Any]) -> PagePeriodsConfig:
    """Parse the [pages.<id>.periods] table.

    In addition to defaults (primary/comparison presets, granularity),
    this parser also supports optional label mappings:

    - [pages.<id>.periods.preset_labels]
    - [pages.<id>.periods.granularity_labels]

    These mappings allow the Web UI to display friendly, localized labels
    instead of raw codes (e.g. "FY", "YTD_PREV_FY", "MONTH").
    """
    primary_labels_tbl = _expect_table(
        tbl.get("primary_preset_labels"),
        "pages.*.periods.primary_preset_labels",
    )
    comparison_labels_tbl = _expect_table(
        tbl.get("comparison_preset_labels"),
        "pages.*.periods.comparison_preset_labels",
    )
    gran_labels_tbl = _expect_table(
        tbl.get("granularity_labels"),
        "pages.*.periods.granularity_labels",
    )
    user_presets_tbl = _expect_table(
        tbl.get("user_presets"),
        "pages.*.periods.user_presets",
    )

    primary_preset_labels = {
        str(k).upper(): str(v) for k, v in primary_labels_tbl.items()
    }
    comparison_preset_labels = {
        str(k).upper(): str(v) for k, v in comparison_labels_tbl.items()
    }
    granularity_labels = {str(k).upper(): str(v) for k, v in gran_labels_tbl.items()}

    user_presets: dict[str, dict[str, str]] = {}
    for key, val in user_presets_tbl.items():
        if isinstance(val, Mapping):
            user_presets[str(key).upper()] = {str(k): str(v) for k, v in val.items()}

    return PagePeriodsConfig(
        default_primary_preset=_get_str(tbl, "default_primary_preset", ""),
        default_comparison_preset=_get_str(tbl, "default_comparison_preset", ""),
        default_granularity=_get_str(tbl, "default_granularity", "") or None,
        allowed_granularities=_get_str_list(tbl, "allowed_granularities"),
        primary_preset_labels=primary_preset_labels,
        comparison_preset_labels=comparison_preset_labels,
        granularity_labels=granularity_labels,
        user_presets=user_presets,
    )


def _parse_pages(root: Mapping[str, Any]) -> dict[str, PageConfig]:
    """Parse the [pages] section.

    Supports per-page UI strings under [pages.<id>.ui] for localization.
    """
    pages_section = _expect_table(root.get("pages"), "pages")
    pages: dict[str, PageConfig] = {}

    for page_name, page_data in pages_section.items():
        page_tbl = _expect_table(page_data, f"pages.{page_name}")
        periods_tbl = page_tbl.get("periods")
        periods_cfg = (
            _parse_page_periods(
                _expect_table(periods_tbl, f"pages.{page_name}.periods")
            )
            if periods_tbl is not None
            else None
        )
        ui_tbl_raw = page_tbl.get("ui") or {}
        ui_tbl = (
            {
                str(k): str(v)
                for k, v in _expect_table(ui_tbl_raw, f"pages.{page_name}.ui").items()
            }
            if ui_tbl_raw
            else {}
        )

        page_cfg = PageConfig(
            id=_get_str(page_tbl, "id", page_name),
            title=_get_str(page_tbl, "title", page_name.capitalize()),
            icon=_get_str(page_tbl, "icon", ""),
            allow_secondary_period=_get_bool(page_tbl, "allow_secondary_period", False),
            periods=periods_cfg,
            ui=ui_tbl,
        )
        pages[page_cfg.id] = page_cfg

    return pages


def _parse_dashboard(root: Mapping[str, Any]) -> DashboardConfig:
    """Parse the [dashboard] section.

    Returns a DashboardConfig that groups:
    - allow_secondary_period (dashboard-level capability flag)
    - tiles (DashboardTileConfig list)
    - charts (DashboardChartConfig list)
    """
    dashboard_tbl = _expect_table(root.get("dashboard"), "dashboard")

    allow_secondary_period = _get_bool(dashboard_tbl, "allow_secondary_period", True)

    tiles_raw = dashboard_tbl.get("tiles", [])
    charts_raw = dashboard_tbl.get("charts", [])

    tiles: list[DashboardTileConfig] = []
    if isinstance(tiles_raw, Sequence):
        for idx, tile in enumerate(tiles_raw):
            tile_tbl = _expect_table(tile, f"dashboard.tiles[{idx}]")
            tiles.append(
                DashboardTileConfig(
                    id=_get_str(tile_tbl, "id", f"tile_{idx}"),
                    source=_get_str(tile_tbl, "source", "measure"),
                    key=_get_str(tile_tbl, "key", ""),
                    label=_get_str(tile_tbl, "label", ""),
                    format=_get_str(tile_tbl, "format", "currency"),
                    period_preset=_get_str(tile_tbl, "period_preset", ""),
                    comparison_preset=_get_str(tile_tbl, "comparison_preset", ""),
                    show_delta_abs=_get_bool(tile_tbl, "show_delta_abs", True),
                    show_delta_pct=_get_bool(tile_tbl, "show_delta_pct", False),
                    delta_good_direction=_get_str(
                        tile_tbl, "delta_good_direction", "up"
                    ),
                    tooltip_from=_get_str(tile_tbl, "tooltip_from", "none"),
                )
            )

    charts: list[DashboardChartConfig] = []
    if isinstance(charts_raw, Sequence):
        for idx, chart in enumerate(charts_raw):
            chart_tbl = _expect_table(chart, f"dashboard.charts[{idx}]")
            series_raw = chart_tbl.get("series", [])
            series: list[ChartSeriesConfig] = []
            if isinstance(series_raw, Sequence):
                for j, s in enumerate(series_raw):
                    s_tbl = _expect_table(s, f"dashboard.charts[{idx}].series[{j}]")
                    series.append(
                        ChartSeriesConfig(
                            source=_get_str(s_tbl, "source", "measure"),
                            key=_get_str(s_tbl, "key", ""),
                            label=_get_str(s_tbl, "label", ""),
                        )
                    )

            charts.append(
                DashboardChartConfig(
                    id=_get_str(chart_tbl, "id", f"chart_{idx}"),
                    type=_get_str(chart_tbl, "type", "line"),
                    title=_get_str(chart_tbl, "title", ""),
                    period_preset=_get_str(chart_tbl, "period_preset", ""),
                    comparison_preset=_get_str(chart_tbl, "comparison_preset", ""),
                    default_granularity=(
                        _get_str(chart_tbl, "default_granularity", "") or None
                    ),
                    allowed_granularities=_get_str_list(
                        chart_tbl, "allowed_granularities"
                    ),
                    series=series,
                )
            )

    return DashboardConfig(
        allow_secondary_period=allow_secondary_period,
        tiles=tiles,
        charts=charts,
    )


def _parse_ratios_page(
    root: Mapping[str, Any],
) -> tuple[list[RatiosMetricConfig], list[RatiosChartConfig]]:
    ratios_tbl = _expect_table(root.get("ratios_page"), "ratios_page")
    metrics_raw = ratios_tbl.get("metrics", [])
    charts_raw = ratios_tbl.get("charts", [])

    metrics: list[RatiosMetricConfig] = []
    if isinstance(metrics_raw, Sequence):
        for idx, metric in enumerate(metrics_raw):
            metric_tbl = _expect_table(metric, f"ratios_page.metrics[{idx}]")
            metrics.append(
                RatiosMetricConfig(
                    id=_get_str(metric_tbl, "id", f"metric_{idx}"),
                    source=_get_str(metric_tbl, "source", "ratio"),
                    key=_get_str(metric_tbl, "key", ""),
                    label=_get_str(metric_tbl, "label", ""),
                    format=_get_str(metric_tbl, "format", ""),
                    comparison=_get_bool(metric_tbl, "comparison", False),
                    show_delta_abs=_get_bool(metric_tbl, "show_delta_abs", False),
                    show_delta_pct=_get_bool(metric_tbl, "show_delta_pct", False),
                    tooltip_from=_get_str(metric_tbl, "tooltip_from", "none"),
                    period_preset=_get_str(metric_tbl, "period_preset", ""),
                    comparison_preset=_get_str(metric_tbl, "comparison_preset", ""),
                )
            )

    charts: list[RatiosChartConfig] = []
    if isinstance(charts_raw, Sequence):
        for idx, chart in enumerate(charts_raw):
            chart_tbl = _expect_table(chart, f"ratios_page.charts[{idx}]")
            series_raw = chart_tbl.get("series", [])
            series: list[ChartSeriesConfig] = []
            if isinstance(series_raw, Sequence):
                for s_idx, s in enumerate(series_raw):
                    s_tbl = _expect_table(
                        s, f"ratios_page.charts[{idx}].series[{s_idx}]"
                    )
                    series.append(
                        ChartSeriesConfig(
                            source=_get_str(s_tbl, "source", "ratio"),
                            key=_get_str(s_tbl, "key", ""),
                            label=_get_str(s_tbl, "label", ""),
                        )
                    )

            charts.append(
                RatiosChartConfig(
                    id=_get_str(chart_tbl, "id", f"ratio_chart_{idx}"),
                    type=_get_str(chart_tbl, "type", "bar"),
                    title=_get_str(chart_tbl, "title", ""),
                    period_preset=_get_str(chart_tbl, "period_preset", ""),
                    comparison_preset=_get_str(chart_tbl, "comparison_preset", ""),
                    series=series,
                )
            )

    return metrics, charts


def _parse_statements_page(root: Mapping[str, Any]) -> StatementsPageConfig:
    tbl = _expect_table(root.get("statements_page"), "statements_page")
    return StatementsPageConfig(
        show_delta_columns=_get_bool(tbl, "show_delta_columns", True),
        hide_zero_lines_in_comparison=_get_bool(
            tbl, "hide_zero_lines_in_comparison", True
        ),
        hide_zero_lines_single_period=_get_bool(
            tbl, "hide_zero_lines_single_period", False
        ),
    )


def _parse_entries_page(root: Mapping[str, Any]) -> EntriesPageConfig:
    tbl = _expect_table(root.get("entries_page"), "entries_page")
    columns = tbl.get("columns")
    if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes)):
        columns_list: list[str] = []
    else:
        columns_list = [str(c) for c in columns]

    filters_tbl = _expect_table(
        root.get("entries_page", {}).get("filters"), "entries_page.filters"
    )
    filters_cfg = EntriesFiltersConfig(
        default_period_preset=_get_str(filters_tbl, "default_period_preset", ""),
        show_deleted_by_default=_get_bool(
            filters_tbl, "show_deleted_by_default", False
        ),
    )

    manual_tbl = _expect_table(
        root.get("entries_page", {}).get("manual_entry"), "entries_page.manual_entry"
    )
    manual_cfg = EntriesManualEntryConfig(
        input_mode=_get_str(manual_tbl, "input_mode", "amount"),
        require_known_account=_get_bool(manual_tbl, "require_known_account", True),
    )

    return EntriesPageConfig(
        columns=columns_list, filters=filters_cfg, manual_entry=manual_cfg
    )


def _parse_duplicates_page(root: Mapping[str, Any]) -> DuplicatesPageConfig:
    tbl = _expect_table(root.get("duplicates_page"), "duplicates_page")
    return DuplicatesPageConfig(
        default_status_filter=_get_str(tbl, "default_status_filter", "pending"),
        show_stats_tiles=_get_bool(tbl, "show_stats_tiles", True),
        show_nav_badge_when_pending=_get_bool(tbl, "show_nav_badge_when_pending", True),
        nav_badge_label=_get_str(tbl, "nav_badge_label", "•"),
    )


def _parse_import_config_page(root: Mapping[str, Any]) -> ImportConfigPageConfig:
    tbl = _expect_table(root.get("import_config_page"), "import_config_page")
    return ImportConfigPageConfig(
        input_dir=_get_str(tbl, "input_dir", "data/input"),
        on_existing_filename=_get_str(tbl, "on_existing_filename", "ask"),
        show_existing_files_selector=_get_bool(
            tbl, "show_existing_files_selector", True
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_layout_config(path: str | Path) -> LayoutConfig:
    """
    Load the Web UI layout configuration from a TOML file.

    This function is the main entry point for the Web UI. It reads the
    given TOML file, validates its high-level structure and returns a
    fully-typed :class:`LayoutConfig` instance that can be consumed by
    Streamlit pages.

    The loader is intentionally tolerant:
    - unknown fields are ignored,
    - missing optional sections/fields fall back to sensible defaults,
    - structural errors (e.g. a section that should be a table but is not)
      raise :class:`LayoutConfigError`.

    Args:
        path:
            Path to the layout TOML file. Can be a string or a Path object.

    Returns:
        A :class:`LayoutConfig` instance representing the loaded layout.

    Raises:
        FileNotFoundError:
            If the file does not exist.
        LayoutConfigError:
            If the TOML content is structurally invalid for a layout
            configuration.
    """
    layout_path = Path(path)

    if not layout_path.is_file():
        raise FileNotFoundError(f"Layout config file not found: {layout_path}")

    try:
        raw_text = layout_path.read_text(encoding="utf-8")
        data = tomllib.loads(raw_text)
    except Exception as exc:  # noqa: BLE001
        raise LayoutConfigError(
            f"Failed to parse layout TOML file: {layout_path}"
        ) from exc

    if not isinstance(data, Mapping):
        raise LayoutConfigError("Layout configuration root must be a TOML table.")

    meta = _parse_meta(data)
    pages = _parse_pages(data)
    dashboard_cfg = _parse_dashboard(data)
    dashboard_tiles = dashboard_cfg.tiles
    dashboard_charts = dashboard_cfg.charts
    ratios_metrics, ratios_charts = _parse_ratios_page(data)
    statements_cfg = _parse_statements_page(data)
    entries_cfg = _parse_entries_page(data)
    duplicates_cfg = _parse_duplicates_page(data)
    import_cfg = _parse_import_config_page(data)

    return LayoutConfig(
        meta=meta,
        pages=pages,
        dashboard=dashboard_cfg,
        dashboard_tiles=dashboard_tiles,  # legacy
        dashboard_charts=dashboard_charts,  # legacy
        ratios_metrics=ratios_metrics,
        ratios_charts=ratios_charts,
        statements=statements_cfg,
        entries=entries_cfg,
        duplicates=duplicates_cfg,
        import_config=import_cfg,
    )
