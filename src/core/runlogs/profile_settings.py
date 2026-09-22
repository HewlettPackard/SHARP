# © Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""Read and write Profile settings sections in runlog markdown files.

This module handles the raw markdown document I/O for the optional
`## Profile settings` JSON section. Higher-level GUI modules are responsible
for interpreting or serializing UI state into these raw dictionaries.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def build_profile_settings_payload(
    filter_metric: str | None,
    filter_value: Any,
    num_perf_groups: int | None,
    cutoff_values: list[float] | None,
    influence_analyzer: str | None,
    outcome_metric: str | None = None,
    excluded_predictors: list[str] | None = None,
    max_correlation: float | None = None,
) -> dict[str, Any]:
    """Build a raw profile-settings payload suitable for markdown persistence.

    ``num_perf_groups=0`` is treated as the auto-detect sentinel and is
    preserved as-is so the restore path can re-enable ``perf_auto_detect``.
    ``filter_value`` is only persisted when ``filter_metric`` is also set.
    """
    settings: dict[str, Any] = {}

    if outcome_metric:
        settings["profiling.default_outcome_metric"] = outcome_metric

    if excluded_predictors:
        settings["profiling.default_predictor_exclusions"] = list(excluded_predictors)

    # Only persist filter_value when the column to filter on is also known;
    # a stray filter_value without a metric cannot be meaningfully restored.
    if filter_metric:
        settings["profiling.default_filter_metric"] = filter_metric
        if filter_value is not None:
            settings["profiling.default_filter_value"] = filter_value

    if num_perf_groups is not None:
        settings["profiling.default_num_perf_groups"] = num_perf_groups

    if cutoff_values:
        settings["profiling.default_cutoff_values"] = sorted(set(cutoff_values))

    if influence_analyzer:
        settings["profiling.default_influence_analyzer"] = influence_analyzer

    if max_correlation is not None:
        settings["profiling.default_max_correlation"] = round(float(max_correlation), 4)

    return settings


def extract_profile_settings_from_md(md_path: str | Path) -> dict[str, Any]:
    """Extract the optional `## Profile settings` JSON section from markdown."""
    try:
        content = Path(md_path).read_text()
    except (OSError, IOError):
        return {}

    section_match = re.search(
        r'^##\s+Profile\s+settings\s*$',
        content,
        re.IGNORECASE | re.MULTILINE,
    )
    if not section_match:
        return {}

    after_header = content[section_match.end():]
    json_block_match = re.search(r'\s*```json\s*\n(.*?)(?:\n```|$)', after_header, re.DOTALL)
    if not json_block_match:
        return {}

    try:
        json_str = json_block_match.group(1)
        json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
        data = json.loads(json_str)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def update_markdown_profile_settings(
    md_path: str | Path,
    new_settings: dict[str, Any],
) -> tuple[bool, str]:
    """Update or create the `## Profile settings` JSON section in markdown."""
    path = Path(md_path)

    if not path.exists():
        return False, f"Markdown file not found: {md_path}"

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Error reading markdown: {str(e)}"

    json_lines = ["{"]
    for index, (key, value) in enumerate(new_settings.items()):
        json_str = json.dumps({key: value})
        match = re.match(r'{\s*"([^"]+)":\s*(.+)\s*}', json_str)
        if match:
            json_key, json_value = match.groups()
            comma = "," if index < len(new_settings) - 1 else ""
            json_lines.append(f'    "{json_key}": {json_value}{comma}')
    json_lines.append("}")
    json_content = "\n".join(json_lines)

    profile_section_pattern = r'^## Profile settings\s*\n+```json\n.*?\n```\s*$'
    match = re.search(profile_section_pattern, content, re.MULTILINE | re.DOTALL)

    if match:
        new_section = f"## Profile settings\n\n```json\n{json_content}\n```"
        new_content = content[:match.start()] + new_section + content[match.end():]
    else:
        first_section_match = re.search(r'^##\s+', content, re.MULTILINE)
        if first_section_match:
            insert_pos = first_section_match.start()
            new_section = f"## Profile settings\n\n```json\n{json_content}\n```\n\n"
            new_content = content[:insert_pos] + new_section + content[insert_pos:]
        else:
            new_section = f"\n## Profile settings\n\n```json\n{json_content}\n```\n"
            new_content = content.rstrip() + new_section

    try:
        path.write_text(new_content, encoding="utf-8")
        return True, "Settings saved to markdown"
    except Exception as e:
        return False, f"Error writing markdown: {str(e)}"


__all__ = [
    "build_profile_settings_payload",
    "extract_profile_settings_from_md",
    "update_markdown_profile_settings",
]