# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Generic WebUI helpers.

This module provides small, defensive utilities used across WebUI pages and components.
They primarily deal with config objects originating from TOML (layout_en.toml),
which may be parsed into nested dictionaries, dataclasses,
or other mapping-like objects.

Goals:
- Normalize unknown TOML-derived objects into plain Python mappings/lists.
- Provide safe accessors with predictable defaults to reduce boilerplate in UI code.
- Keep WebUI modules thin and resilient to partial/missing config.
"""

from dataclasses import asdict, is_dataclass
from typing import Any


def _to_mapping(obj: Any) -> dict[str, Any]:
    """
    Convert an arbitrary object into a plain dict-like mapping.

    Supported inputs:
    - dict: returned as-is
    - dataclass instances: converted via `dataclasses.asdict`
    - objects exposing `__dict__`: converted from their attribute dict

    Returns:
        A dict (possibly empty). Never raises for unknown inputs; instead returns {}.

    Notes:
        This helper is used to normalize layout TOML objects
        (page configs, tiles, charts)
        into plain mappings so downstream code can rely on `.get(...)`.
    """

    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_")}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """
    Safe `.get()` accessor for mapping-like objects.

    Args:
        mapping: Usually a dict (or dict-like) returned by `_to_mapping`.
        key: Key to fetch.
        default: Returned when mapping is None, not a mapping, or key is missing.

    Returns:
        Value for `key` or `default`.
    """
    # Avoid repetitive `if mapping and ...` checks in Streamlit pages/components.
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_list(value: Any) -> list[Any]:
    """
    Normalize a possibly-missing TOML value into a list.

    - None -> []
    - list/tuple -> list(value)
    - single item -> [value]

    This is useful for TOML fields that may accept either a single mapping or a list.
    """

    if value is None:
        return []
    if isinstance(value, list):
        return value
    return list(value)
