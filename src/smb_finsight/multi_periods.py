# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Multi-period orchestration for statements, measures and ratios.

This module provides the high-level entry point used to compute all
financial outputs for multiple reporting periods in a *single pass*.
It replaces the former split design (separate functions for statements,
measures and ratios) with a unified orchestration layer that significantly
reduces code duplication and improves performance.

Overview
--------
The core function, ``compute_all_multi_period()``, performs all required
steps to build:

1. Statements (primary + optional secondary)
2. Measures (canonical + extra + derived)
3. Ratios (basic / advanced / full)

It executes the entire compute pipeline once per period, and once for
the global set of accounting entries. The Web UI or any higher-level
component only needs to call this function to obtain all the data needed
to power dashboards, charts and analytics.

Responsibilities and workflow
-----------------------------
For a list of Period objects, the function:

1. Computes the overall [min(start), max(end)] date range covering all
   requested periods.

2. Loads accounting entries from the database *once* for that global
   range, avoiding repeated I/O.

3. Loads the primary and (optionally) secondary mapping templates and
   extracts canonical-measure metadata.

4. Loads metadata for derived measures defined in the ratios TOML files.

5. For each Period:
   - filters the globally loaded accounting entries to the period
     boundaries,
   - aggregates the primary (and optional secondary) financial statement,
   - computes canonical measures and extra measures (balance-sheet
     inputs, HR inputs, period_days),
   - computes derived measures using ratios rules (standard + custom),
   - computes ratios at the configured logical level,
   - records all statement rows, measures, and ratios with a
     ``period_label`` column.

6. Concatenates all per-period results into three long-format DataFrames:
   - ``StatementsMultiPeriod``   : primary + optional secondary statements
   - ``MeasuresMultiPeriod``     : canonical + derived measures with metadata
   - ``RatiosMultiPeriod``       : ratios with metadata and levels

Data model
----------
The three returned dataclasses contain:

- Long-format DataFrames, where each row corresponds to one item
  (statement line, measure, ratio) for one period.
- A ``period_label`` column enabling easy filtering, sorting and
  visualisation in time-series contexts (Web UI, BI tools, CLI exports).
- Rich metadata (label, unit, notes, kind) coming from mapping templates
  or ratios TOML files.

Separation of concerns
----------------------
- ``engine.py`` remains the single source of truth for how statements and
  canonical measures are computed for one period.
- ``ratios.py`` handles derived measures and ratios for one period.
- ``multi_periods.py`` assembles everything across multiple periods and
  returns consolidated results suitable for dashboards and advanced
  analytics.
- Configuration of which metrics appear in which dashboard sections will
  be handled by separate dashboard configuration files (planned for the
  Web UI, v0.5.x).

This design keeps the engine minimal, predictable and reusable, while
providing a clean and efficient multi-period interface for higher-level
layers.
"""

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from .config import AppConfig, StandardConfig
from .db import load_entries
from .engine import (
    MeasureMeta,
    aggregate,
    build_canonical_measures,
    build_canonical_measures_metadata,
)
from .mapping import Template
from .periods import Period
from .ratios import (
    compute_derived_measures,
    compute_ratios,
    load_derived_measures_metadata,
)


@dataclass(frozen=True)
class StatementsMultiPeriod:
    """
    Multi-period result for financial statements.

    Attributes
    ----------
    primary :
        Long-format DataFrame for the primary statement (e.g. income
        statement). Each row represents one statement line for one
        period.

        Expected columns (minimum):
            - period_label : str
                Identifier of the period (e.g. 'FY-2024', '2024-01').
            - level        : int or str
                Hierarchical level used to drive indentation in the UI.
            - display_order: int
                Ordering hint used when rendering the statement.
            - id           : int
                Row identifier as defined in the mapping template.
            - name         : str
                Human-readable label for the row.
            - type         : str
                Row type, typically 'acc' (accounts aggregation) or
                'calc' (formula).
            - amount       : float
                Numerical value of the row for the given period.
            - notes        : str
                Optional notes coming from the mapping, useful for tooltips
                or contextual help in the Web UI.

    secondary :
        Optional long-format DataFrame for the secondary statement
        (e.g. French "SIG" for FR_PCG). When present, it follows the
        same column conventions as `primary`.
    """

    primary: pd.DataFrame
    secondary: Optional[pd.DataFrame] = None


@dataclass(frozen=True)
class MeasuresMultiPeriod:
    """
    Multi-period result for canonical and derived measures.

    Each row represents the value of a measure for a given period.

    Expected columns (minimum):
        - period_label : str
            Identifier of the period (e.g. 'FY-2024', '2024-01').
        - measure_key  : str
            Internal measure identifier (e.g. 'revenue',
            'external_charges', 'gross_margin').
        - label        : str
            Human-readable label for display.
        - value        : float
            Numerical value of the measure.
        - unit         : str
            Unit hint (e.g. 'amount', 'percent', 'days').
        - notes        : str
            Optional human-readable notes or description.
        - kind         : str
            Either 'canonical' (from the statement mapping) or 'extra'
            (derived measures defined in ratios TOML files).

    Notes
    -----
    - Canonical measures computed by the engine do not carry labels or
      units in the low-level computation. Metadata is reconstructed
      from the mapping template via MeasureMeta.
    - Derived measures defined in ratios TOML files provide explicit
      label/unit/notes metadata which is propagated here, with
      kind='extra'.
    """

    data: pd.DataFrame


@dataclass(frozen=True)
class RatiosMultiPeriod:
    """
    Multi-period result for ratios.

    Each row represents the value of a ratio for a given period and
    logical level.

    Expected columns (minimum):
        - period_label : str
            Identifier of the period (e.g. 'FY-2024', '2024-01').
        - key          : str
            Internal ratio identifier as defined in the ratios TOML
            file.
        - label        : str
            Human-readable label for display.
        - value        : float or None
            Numerical value of the ratio. May be None if the ratio
            cannot be computed (e.g. division by zero).
        - unit         : str
            Unit hint (e.g. 'percent', 'ratio', 'days', 'amount').
        - notes        : str
            Optional human-readable notes or description.
        - level        : str
            Logical level of the ratio (e.g. 'basic', 'advanced',
            'full'), as defined in the TOML file.
    """

    data: pd.DataFrame


def compute_all_multi_period(
    app_config: AppConfig,
    standard_config: StandardConfig,
    periods: list[Period],
) -> tuple[StatementsMultiPeriod, MeasuresMultiPeriod, RatiosMultiPeriod]:
    """
    Compute statements, measures and ratios over multiple periods in a
    single pass.

    This function is the high-level entry point for multi-period
    analysis. It:

    - computes the global [min(start), max(end)] interval covered by
      all requested periods;
    - loads accounting entries once from the database for this global
      interval;
    - builds templates and metadata for the primary and optional
      secondary statements;
    - for each Period:
        * filters entries to the period boundaries,
        * aggregates the primary statement,
        * aggregates the secondary statement if configured,
        * builds canonical measures (primary + secondary) using
          ``build_canonical_measures()``, including extra measures
          (balance sheet inputs, HR inputs, period_days),
        * optionally applies derived measure rules from the ratios TOML
          files (standard rules + optional custom rules),
        * computes ratios using the configured ratio level
          (basic / advanced / full),
        * records all statement lines, measures and ratios with a
          `period_label` column;
    - concatenates all per-period results into three long-format
      DataFrames:
        * statements (primary + optional secondary),
        * measures (canonical + derived),
        * ratios.

    Parameters
    ----------
    app_config :
        Global application configuration. Uses:
        - database
        - balance_sheet_inputs
        - hr_inputs
        - period_days
        - ratios_enabled
        - ratios_level
    standard_config :
        Standard-specific configuration. Uses:
        - income_statement_mapping
        - secondary_mapping
        - ratios_rules_file
        - ratios_custom_file
    periods :
        List of Period objects defining the time windows to compute.

    Returns
    -------
    (StatementsMultiPeriod, MeasuresMultiPeriod, RatiosMultiPeriod)
        A tuple containing:
        - statements : primary and optional secondary statements,
        - measures   : canonical + derived measures with metadata,
        - ratios     : ratios for the requested level.

    Raises
    ------
    ValueError
        If no periods are provided or if no primary mapping is configured.
    """
    if not periods:
        raise ValueError("compute_all_multi_period requires at least one Period.")

    primary_mapping_path = standard_config.income_statement_mapping
    if primary_mapping_path is None:
        raise ValueError(
            "No primary income statement mapping configured in StandardConfig."
        )

    secondary_mapping_path = standard_config.secondary_mapping
    ratios_rules_file = standard_config.ratios_rules_file
    ratios_custom_file = standard_config.ratios_custom_file

    # 1) Global date range across all requested periods.
    global_start = min(p.start for p in periods)
    global_end = max(p.end for p in periods)

    # 2) Load accounting entries once for the global range.
    tx_all = load_entries(
        cfg=app_config.database,
        start=global_start,
        end=global_end,
    )

    # 3) Build templates for primary and optional secondary statements.
    primary_template = Template.from_csv(str(primary_mapping_path))
    secondary_template = (
        Template.from_csv(str(secondary_mapping_path))
        if secondary_mapping_path is not None
        else None
    )

    # 4) Canonical measure metadata from templates.
    canonical_meta: dict[str, MeasureMeta] = build_canonical_measures_metadata(
        primary_template
    )
    if secondary_template is not None:
        secondary_meta = build_canonical_measures_metadata(secondary_template)
        # Secondary metadata overrides primary if keys overlap, which is
        # consistent with how canonical values are merged.
        canonical_meta.update(secondary_meta)

    # 5) Derived measure metadata from ratios TOML files (standard + custom).
    derived_meta: dict[str, MeasureMeta] = {}
    if ratios_rules_file is not None:
        derived_meta.update(load_derived_measures_metadata(ratios_rules_file))
    if ratios_custom_file is not None:
        derived_meta.update(load_derived_measures_metadata(ratios_custom_file))

    # 6) Prepare containers for statements, measures and ratios.
    primary_frames: list[pd.DataFrame] = []
    secondary_frames: list[pd.DataFrame] = []

    measure_rows: list[dict[str, Any]] = []
    ratio_rows: list[dict[str, Any]] = []

    ratios_enabled: bool = bool(getattr(app_config, "ratios_enabled", False))
    ratio_level: str = getattr(app_config, "ratios_level", "basic") or "basic"

    for period in periods:
        # Filter entries to the current period boundaries.
        if tx_all.empty:
            tx_period = tx_all
        else:
            mask = (tx_all["date"] >= period.start) & (tx_all["date"] <= period.end)
            tx_period = tx_all.loc[mask]

        # ------------------------------------------------------------------
        # Statements (primary + optional secondary)
        # ------------------------------------------------------------------
        primary_base = aggregate(
            accounting_entries=tx_period,
            template=primary_template,
        )
        primary_base = primary_base.copy()
        primary_base["period_label"] = period.label
        primary_frames.append(primary_base)

        secondary_base: Optional[pd.DataFrame] = None
        if secondary_template is not None:
            secondary_base = aggregate(
                accounting_entries=tx_period,
                template=secondary_template,
            )
            secondary_base = secondary_base.copy()
            secondary_base["period_label"] = period.label
            secondary_frames.append(secondary_base)

        # ------------------------------------------------------------------
        # Measures (canonical + extra + derived)
        # ------------------------------------------------------------------
        extra_measures: dict[str, float] = {}
        extra_measures.update(app_config.balance_sheet_inputs)
        extra_measures.update(app_config.hr_inputs)
        try:
            extra_measures["period_days"] = float(app_config.period_days)
        except (TypeError, ValueError):
            # Ignore if period_days is not a number.
            pass

        canonical_values = build_canonical_measures(
            statement=primary_base,
            template=primary_template,
            extra_measures=extra_measures,
        )

        if secondary_template is not None and secondary_base is not None:
            secondary_values = build_canonical_measures(
                statement=secondary_base,
                template=secondary_template,
            )
            canonical_values.update(secondary_values)

        all_measures: dict[str, float] = dict(canonical_values)

        if ratios_enabled:
            # Apply derived measure rules (standard + optional custom).
            if ratios_rules_file is not None:
                all_measures = compute_derived_measures(
                    base_measures=all_measures,
                    rules_file=ratios_rules_file,
                )
            if ratios_custom_file is not None:
                all_measures = compute_derived_measures(
                    base_measures=all_measures,
                    rules_file=ratios_custom_file,
                )

        # Build measure rows for this period using metadata.
        for key, value in all_measures.items():
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                # Skip non-numeric values.
                continue

            meta = canonical_meta.get(key) or derived_meta.get(key)
            if meta is None:
                unit = "days" if key == "period_days" else "amount"
                meta = MeasureMeta(
                    key=key,
                    label=key,
                    unit=unit,
                    notes="",
                    kind="extra",
                )

            measure_rows.append(
                {
                    "period_label": period.label,
                    "measure_key": key,
                    "label": meta.label,
                    "value": numeric_value,
                    "unit": meta.unit,
                    "notes": meta.notes,
                    "kind": meta.kind,
                }
            )

        # ------------------------------------------------------------------
        # Ratios
        # ------------------------------------------------------------------
        if ratios_enabled and (
            ratios_rules_file is not None or ratios_custom_file is not None
        ):
            ratio_results = []

            if ratios_rules_file is not None:
                ratio_results.extend(
                    compute_ratios(
                        all_measures=all_measures,
                        rules_file=ratios_rules_file,
                        level=ratio_level,
                    )
                )
            if ratios_custom_file is not None:
                ratio_results.extend(
                    compute_ratios(
                        all_measures=all_measures,
                        rules_file=ratios_custom_file,
                        level=ratio_level,
                    )
                )

            for r in ratio_results:
                ratio_rows.append(
                    {
                        "period_label": period.label,
                        "key": r.key,
                        "label": r.label,
                        "value": r.value,
                        "unit": r.unit,
                        "notes": r.notes,
                        "level": r.level,
                    }
                )

    # ----------------------------------------------------------------------
    # Build statements DataFrames and enrich with notes from templates
    # ----------------------------------------------------------------------
    if primary_frames:
        primary_df = pd.concat(primary_frames, ignore_index=True)
    else:
        primary_df = pd.DataFrame(
            columns=[
                "period_label",
                "level",
                "display_order",
                "id",
                "name",
                "type",
                "amount",
                "notes",
            ]
        )

    notes_by_id_primary = {
        row.id: getattr(row, "notes", "") for row in primary_template.rows
    }
    primary_df["notes"] = primary_df["id"].map(notes_by_id_primary).fillna("")

    secondary_df: Optional[pd.DataFrame]
    if secondary_frames and secondary_template is not None:
        secondary_df = pd.concat(secondary_frames, ignore_index=True)
        notes_by_id_secondary = {
            row.id: getattr(row, "notes", "") for row in secondary_template.rows
        }
        secondary_df["notes"] = secondary_df["id"].map(notes_by_id_secondary).fillna("")
    else:
        secondary_df = None

    statements = StatementsMultiPeriod(primary=primary_df, secondary=secondary_df)

    # ----------------------------------------------------------------------
    # Build measures DataFrame
    # ----------------------------------------------------------------------
    if measure_rows:
        measures_df = pd.DataFrame(measure_rows)
    else:
        measures_df = pd.DataFrame(
            columns=[
                "period_label",
                "measure_key",
                "label",
                "value",
                "unit",
                "notes",
                "kind",
            ]
        )

    measures = MeasuresMultiPeriod(data=measures_df)

    # ----------------------------------------------------------------------
    # Build ratios DataFrame
    # ----------------------------------------------------------------------
    if ratio_rows:
        ratios_df = pd.DataFrame(ratio_rows)
    else:
        ratios_df = pd.DataFrame(
            columns=[
                "period_label",
                "key",
                "label",
                "value",
                "unit",
                "notes",
                "level",
            ]
        )

    ratios = RatiosMultiPeriod(data=ratios_df)

    return statements, measures, ratios
