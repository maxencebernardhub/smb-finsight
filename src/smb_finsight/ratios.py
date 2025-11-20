# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Ratios and KPI computation engine for SMB FinSight.

This module is responsible for:
- loading ratio and measure definitions from standard-specific TOML files,
- evaluating derived measures based on canonical measures,
- computing ratios per level (basic, advanced, full) for display.

It is intentionally independent from I/O and CLI concerns: it only works
with in-memory dictionaries and paths to TOML rule files.
"""

import ast
import operator
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import tomllib  # Python 3.11+

# Logical ordering of ratio levels. This is used so that requesting an
# "advanced" level includes both "basic" and "advanced" ratios, and
# requesting "full" includes all levels.
LEVEL_ORDER: tuple[str, ...] = ("basic", "advanced", "full")


@dataclass(frozen=True)
class RatioResult:
    """
    Computed ratio or KPI as returned by this module.

    Attributes:
        key: Internal identifier (e.g. 'gross_margin_pct').
        label: Human-readable label for display (e.g. 'Marge brute (%)').
        value: Numeric value (float) or None if not computable.
        unit: Unit hint ('percent', 'amount', 'ratio', 'days', etc.).
        notes: Optional human-readable notes or description.
        level: Logical level ('basic', 'advanced', 'full', etc.).
    """

    key: str
    label: str
    value: Optional[float]
    unit: str
    notes: str
    level: str


def _load_toml(path: Path) -> dict[str, Any]:
    """
    Load a TOML file and return its content as a dictionary.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the TOML content cannot be parsed or is not a table.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Ratio rules file not found: {path}")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Failed to parse TOML ratio rules file: {path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Invalid TOML root type in {path}, expected a table.")

    return data


_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}


def _safe_eval_expr(expr: str, variables: Mapping[str, float]) -> float:
    """
    Safely evaluate a simple arithmetic expression using the given variables.

    Supported:
        - numeric literals
        - variable names (keys from `variables`)
        - binary operations: +, -, *, /, %, **
        - unary minus
        - parentheses

    Args:
        expr: Expression string (e.g. "net_income + depreciation_amortization").
        variables: Mapping of variable names to float values.

    Returns:
        The evaluated float value.

    Raises:
        ValueError: if the expression contains unsupported constructs.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression syntax: {expr!r}") from exc

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)

        if isinstance(node, ast.Constant):  # Python 3.8+
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Unsupported constant in expression: {node.value!r}")

        if isinstance(node, ast.Name):
            name = node.id
            if name not in variables:
                raise ValueError(f"Unknown variable in expression: {name!r}")
            return float(variables[name])

        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            op_type = type(node.op)
            if op_type not in _ALLOWED_OPERATORS:
                raise ValueError(f"Unsupported operator in expression: {op_type}")
            op_func = _ALLOWED_OPERATORS[op_type]
            return float(op_func(left, right))

        if isinstance(node, ast.UnaryOp):
            if type(node.op) not in _ALLOWED_OPERATORS:
                raise ValueError(f"Unsupported unary operator: {node.op!r}")
            operand = _eval(node.operand)
            op_func = _ALLOWED_OPERATORS[type(node.op)]
            return float(op_func(operand))

        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    return _eval(tree)


def compute_derived_measures(
    base_measures: Mapping[str, float],
    rules_file: Path,
) -> dict[str, float]:
    """
    Compute derived measures from canonical measures and a TOML rules file.

    This function:
    - loads the [measures.*] definitions from the TOML file,
    - evaluates each 'formula' using the base measures and already computed
      derived measures,
    - returns a dictionary with both base and derived measures.

    Args:
        base_measures: Mapping of canonical measure names to float values.
        rules_file: Path to a TOML file defining [measures.*] sections.

    Returns:
        A dictionary containing all base measures plus the derived measures.
        If a formula cannot be evaluated (missing variable, division by zero),
        the corresponding measure is skipped.
    """
    data = _load_toml(rules_file)

    measures_section = data.get("measures") or {}
    if not isinstance(measures_section, Mapping):
        measures_section = {}

    # Start with a mutable copy of base measures
    all_measures: dict[str, float] = {
        str(k): float(v) for k, v in base_measures.items()
    }

    # We evaluate measures in the order they appear in the TOML.
    # This allows measures to depend on previously defined derived measures.
    for key, cfg in measures_section.items():
        if not isinstance(cfg, Mapping):
            continue

        formula = cfg.get("formula")
        if not formula:
            continue

        formula_str = str(formula)
        try:
            value = _safe_eval_expr(formula_str, all_measures)
        except Exception:
            # Ignore measures that cannot be evaluated; they will not be
            # available for subsequent ratios.
            continue

        all_measures[str(key)] = float(value)

    return all_measures


def compute_ratios(
    measures: Mapping[str, float],
    rules_file: Path,
    level: str,
) -> list[RatioResult]:
    """
    Compute ratios for a given level using measure values and a TOML rules file.

    Args:
        measures:
            Mapping of measure names to float values. This should include both
            canonical measures and derived measures (see compute_derived_measures()).
        rules_file:
            Path to a TOML file defining [ratios.<level>.*] sections.
        level:
            Ratios level to compute ('basic', 'advanced', 'full', etc.).
            The level is interpreted cumulatively: for example, 'advanced'
            includes both 'basic' and 'advanced' ratios, and 'full' includes
            all levels ('basic', 'advanced' and 'full').

    Returns:
        A list of RatioResult instances for all included levels. The ``level``
        attribute of each result reflects the logical level it belongs to
        ('basic', 'advanced', 'full', etc.). Ratios whose formula cannot be
        evaluated (missing measures, division by zero, etc.) will have
        value=None.
    """
    data = _load_toml(rules_file)

    ratios_section = data.get("ratios") or {}
    if not isinstance(ratios_section, Mapping):
        return []

    # Determine which levels to include. For known levels in LEVEL_ORDER we
    # include all levels up to the requested one (basic -> [basic],
    # advanced -> [basic, advanced], full -> [basic, advanced, full]).
    # For unknown levels, we only include the matching section if present.
    if level in LEVEL_ORDER:
        max_index = LEVEL_ORDER.index(level)
        levels_to_include = [
            lvl for lvl in LEVEL_ORDER[: max_index + 1] if lvl in ratios_section
        ]
    else:
        levels_to_include = [level] if level in ratios_section else []

    if not levels_to_include:
        return []

    results: list[RatioResult] = []

    for current_level in levels_to_include:
        level_section = ratios_section.get(current_level) or {}
        if not isinstance(level_section, Mapping):
            continue

        for key, cfg in level_section.items():
            if not isinstance(cfg, Mapping):
                continue

            label = str(cfg.get("label", key))
            formula = cfg.get("formula")
            unit = str(cfg.get("unit", "amount"))
            notes = str(cfg.get("notes", ""))

            value: Optional[float]

            if not formula:
                value = None
            else:
                formula_str = str(formula)
                try:
                    # A ratio formula may either reference a single measure
                    # (e.g. "gross_margin_pct") or be a full expression
                    # (e.g. "(net_income / revenue) * 100").
                    if formula_str in measures:
                        value = float(measures[formula_str])
                    else:
                        value = float(_safe_eval_expr(formula_str, measures))
                except Exception:
                    value = None

            results.append(
                RatioResult(
                    key=str(key),
                    label=label,
                    value=value,
                    unit=unit,
                    notes=notes,
                    level=current_level,
                )
            )

    return results
