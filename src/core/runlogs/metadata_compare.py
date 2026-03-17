"""
Metadata comparison for benchmark runs.

Compares metadata from .md files (runtime options, invariants, system specs)
and generates difference summaries.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.core.config.settings import Settings


@dataclass
class MetadataDiff:
    """Difference in a single metadata field."""
    section: str  # "Runtime options", "Invariants", "System specs"
    field: str
    treatment_value: Any
    baseline_value: Any
    significant: bool  # Whether difference is performance-relevant


def load_metadata(md_path: Path) -> dict[str, dict[str, Any]]:
    """
    Load metadata from .md file.

    Parses JSON/YAML sections from markdown file and returns structured data.

    Args:
        md_path: Path to .md file

    Returns:
        Dictionary with sections like "Initial runtime options", "Initial system configuration", etc.
    """
    import json

    content = md_path.read_text()
    sections = {}

    # Extract code blocks (between ```json/```yaml and ```)
    in_block = False
    current_section = None
    block_lines: list[str] = []
    block_type = None

    for line in content.split('\n'):
        # Detect section headers
        if line.startswith('## '):
            current_section = line[3:].strip()
        # Detect code block start
        elif line.strip().startswith('```json') or line.strip().startswith('```yaml'):
            in_block = True
            block_type = 'json' if 'json' in line else 'yaml'
            block_lines = []
        elif line.strip() == '```':
            if in_block:
                # End of code block - parse it
                if current_section and block_lines:
                    try:
                        if block_type == 'json':
                            sections[current_section] = json.loads('\n'.join(block_lines))
                        else:
                            sections[current_section] = yaml.safe_load('\n'.join(block_lines))
                    except (json.JSONDecodeError, yaml.YAMLError):
                        # Skip malformed blocks
                        pass
                block_lines = []
                in_block = False
                block_type = None
            else:
                # Start of unknown code block (no language specified)
                in_block = True
                block_type = 'yaml'  # Default to YAML
                block_lines = []
        elif in_block:
            block_lines.append(line)

    return sections


def _should_ignore_field(section: str, field: str) -> bool:
    """
    Check if a field should be ignored in comparison.

    Args:
        section: Section name
        field: Field name

    Returns:
        True if field should be ignored
    """
    # Fields that are always ignored (vary between runs but don't affect performance)
    always_ignore_fields = {
        'timestamp',
        'date',
        'launch_id',
        'download_timestamp',
        'build_timestamp',
        'uptime_seconds',
        'running_processes',
    }

    # Additional fields to ignore only in runtime options (not in invariant parameters)
    # Note: task, start, concurrency, git_hash, timeout are significant and NOT ignored!
    runtime_only_ignore = {
        'experiment',
        'directory',
        'mode',
        'verbose',
        'skip_sys_specs',
        'repeats',
        'repeater_options',
    }

    field_parts = field.lower().split('.')

    # Always ignore these fields in any section
    if any(part in always_ignore_fields for part in field_parts):
        return True

    # Additionally ignore these only in runtime options
    if section in ('Initial runtime options', 'Runtime options'):
        if any(part in runtime_only_ignore for part in field_parts):
            return True

    return False


def _is_version_string_similar(treatment: str, baseline: str, field: str) -> bool:
    """
    Check if two version strings are similar enough to be considered insignificant.

    Args:
        treatment: Treatment version string
        baseline: Baseline version string
        field: Field name

    Returns:
        True if versions are similar (minor differences only)
    """
    if field.lower() not in ('os_version', 'kernel', 'python_version', 'version'):
        return False

    # Minor version differences often don't matter (e.g., 3.10.12 vs 3.10.13)
    if '.' in treatment and '.' in baseline:
        return treatment.split('.')[:2] == baseline.split('.')[:2]

    return False


def _is_numeric_difference_significant(
    treatment: float,
    baseline: float,
    field: str,
    core_count: int | None,
) -> bool:
    """
    Check if numeric difference exceeds significance thresholds.

    Args:
        treatment: Treatment numeric value
        baseline: Baseline numeric value
        field: Field name
        core_count: Number of processor cores (for load average)

    Returns:
        True if difference is significant
    """
    # Very small absolute differences (rounding/timing noise)
    if abs(treatment - baseline) < 0.001:
        return False

    # Load average - significant if difference is large relative to core count
    if 'load' in field.lower() or 'load_average' in field.lower():
        settings = Settings()
        threshold = float(settings.get('comparisons.load_avg_threshold_factor', 0.1))
        cores = core_count if core_count else 8
        return abs(treatment - baseline) > (threshold * cores)

    # CPU frequency - significant if exceeds threshold percentage
    if 'freq' in field.lower() or 'mhz' in field.lower():
        if baseline != 0:
            settings = Settings()
            threshold_pct = float(settings.get('comparisons.cpu_freq_threshold_pct', 5)) / 100.0
            pct_diff = abs((treatment - baseline) / baseline)
            return pct_diff > threshold_pct
        return treatment != baseline

    # Memory - significant if exceeds threshold percentage
    if 'memory' in field.lower() or 'ram' in field.lower():
        if baseline != 0:
            settings = Settings()
            threshold_pct = float(settings.get('comparisons.memory_threshold_pct', 1)) / 100.0
            pct_diff = abs((treatment - baseline) / baseline)
            return pct_diff > threshold_pct
        return treatment != baseline

    # Temperature, fan speed - not performance-relevant
    if 'temperature' in field.lower() or 'fan' in field.lower():
        return False

    # Generic numeric - significant if >5% difference
    if baseline != 0:
        pct_diff = abs((treatment - baseline) / baseline)
        return pct_diff > 0.05
    return treatment != baseline


def is_significant_difference(
    section: str,
    field: str,
    treatment: Any,
    baseline: Any,
    core_count: int | None = None,
) -> bool:
    """
    Determine if a metadata difference is significant.

    Args:
        section: Section name
        field: Field name
        treatment: Treatment value
        baseline: Baseline value
        core_count: Number of processor cores (for load average thresholds)

    Returns:
        True if difference is significant
    """
    # Check if field should be ignored
    if _should_ignore_field(section, field):
        return False

    # Handle numeric values (int or float, or strings convertible to numbers)
    treatment_num = None
    baseline_num = None

    # Convert to float if they're numeric types
    if isinstance(treatment, (int, float)):
        treatment_num = float(treatment)
    if isinstance(baseline, (int, float)):
        baseline_num = float(baseline)

    # Try to convert strings to numbers
    if treatment_num is None and isinstance(treatment, str):
        try:
            treatment_num = float(treatment)
        except ValueError:
            pass
    if baseline_num is None and isinstance(baseline, str):
        try:
            baseline_num = float(baseline)
        except ValueError:
            pass

    # If both are numeric, do numeric comparison
    if treatment_num is not None and baseline_num is not None:
        return _is_numeric_difference_significant(
            treatment_num, baseline_num, field, core_count
        )

    # String values - check for version similarity, otherwise significant if different
    if isinstance(treatment, str) and isinstance(baseline, str):
        if _is_version_string_similar(treatment, baseline, field):
            return False
        return treatment != baseline

    # Lists, dicts, or type mismatches - significant if different
    return bool(treatment != baseline)


def flatten_dict(data: dict[str, Any], prefix: str = '') -> dict[str, Any]:
    """
    Flatten a nested dictionary into dot-notation keys.

    Args:
        data: Dictionary to flatten
        prefix: Prefix for keys

    Returns:
        Flattened dictionary
    """
    result = {}
    for key, value in data.items():
        full_key = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            result.update(flatten_dict(value, full_key))
        else:
            result[full_key] = value
    return result


def extract_core_count(metadata: dict[str, dict[str, Any]]) -> int | None:
    """
    Extract processor/core count from metadata.

    Args:
        metadata: Full metadata dictionary

    Returns:
        Number of cores, or None if not found
    """
    # Try to get from Initial system configuration
    sys_config = metadata.get('Initial system configuration', {})
    cpu_info = sys_config.get('cpu', {})

    # Try processor_count first (total logical processors)
    if 'processor_count' in cpu_info:
        try:
            return int(cpu_info['processor_count'])
        except (ValueError, TypeError):
            pass

    # Fall back to cpu_cores (physical cores)
    if 'cpu_cores' in cpu_info:
        try:
            return int(cpu_info['cpu_cores'])
        except (ValueError, TypeError):
            pass

    return None


def compare_section(
    section: str,
    treatment_data: dict[str, Any],
    baseline_data: dict[str, Any],
    show_all: bool = False,
    core_count: int | None = None,
) -> list[MetadataDiff]:
    """
    Compare a single section between two runs.

    Args:
        section: Section name
        treatment_data: Treatment run metadata
        baseline_data: Baseline run metadata
        show_all: If True, include non-significant differences
        core_count: Number of processor cores (for load average thresholds)

    Returns:
        List of differences
    """
    diffs = []

    # Flatten nested structures for comparison
    treatment_flat = flatten_dict(treatment_data)
    baseline_flat = flatten_dict(baseline_data)

    # Get all fields from both runs
    all_fields = set(treatment_flat.keys()) | set(baseline_flat.keys())

    for field in sorted(all_fields):
        treatment_value = treatment_flat.get(field, 'N/A')
        baseline_value = baseline_flat.get(field, 'N/A')

        # Check if different
        if treatment_value != baseline_value:
            significant = is_significant_difference(
                section,
                field,
                treatment_value,
                baseline_value,
                core_count=core_count,
            )

            # Include if show_all or significant
            if show_all or significant:
                diffs.append(MetadataDiff(
                    section=section,
                    field=field,
                    treatment_value=treatment_value,
                    baseline_value=baseline_value,
                    significant=significant,
                ))

    return diffs


def _escape_markdown_table_cell(value: Any, max_length: int = 30) -> str:
    """
    Escape and truncate a value for safe display in a markdown table cell.

    Args:
        value: Value to escape
        max_length: Maximum length before truncation (default: 30)

    Returns:
        Escaped and truncated string safe for markdown tables
    """
    # Convert to string
    text = str(value)

    # Replace newlines and carriage returns with spaces first
    text = text.replace('\n', ' ')
    text = text.replace('\r', '')

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + '...'

    # Escape pipe characters that would break table formatting
    # Use HTML entity to prevent breaking table structure
    text = text.replace('|', '&#124;')

    return text


def format_metadata_diff_markdown(diffs: list[MetadataDiff]) -> str:
    """
    Format metadata differences as Markdown.

    Args:
        diffs: List of metadata differences

    Returns:
        Markdown-formatted string
    """
    if not diffs:
        return '## Metadata Comparison\n\nNo significant differences in metadata.'

    lines = [
        '## Metadata Comparison',
        '',
    ]

    # Group by section
    sections: dict[str, list[MetadataDiff]] = {}
    for diff in diffs:
        if diff.section not in sections:
            sections[diff.section] = []
        sections[diff.section].append(diff)

    for section, section_diffs in sorted(sections.items()):
        # Check if all differences in this section are significant
        all_significant = all(diff.significant for diff in section_diffs)

        # Build header based on whether we need the Significant column
        if all_significant:
            header = '| Field | Baseline | Treatment |'
            separator = '|-------|----------|-----------|'
        else:
            header = '| Field | Baseline | Treatment | Significant |'
            separator = '|-------|----------|-----------|-------------|'

        lines.extend([
            f'### {section}',
            '',
            header,
            separator,
        ])

        for diff in section_diffs:
            # Escape values to prevent breaking table formatting
            # Truncate field names at 50 chars, values at 30 chars
            field = _escape_markdown_table_cell(diff.field, max_length=50)
            baseline = _escape_markdown_table_cell(diff.baseline_value, max_length=30)
            treatment = _escape_markdown_table_cell(diff.treatment_value, max_length=30)

            if all_significant:
                lines.append(
                    f'| {field} '
                    f'| {baseline} '
                    f'| {treatment} |'
                )
            else:
                sig_marker = 'Yes' if diff.significant else 'No'
                lines.append(
                    f'| {field} '
                    f'| {baseline} '
                    f'| {treatment} '
                    f'| {sig_marker} |'
                )

        lines.append('')

    return '\n'.join(lines)


def format_metadata_diff_csv(diffs: list[MetadataDiff]) -> str:
    """
    Format metadata differences as CSV.

    Args:
        diffs: List of metadata differences

    Returns:
        CSV-formatted string
    """
    lines = ['section,field,baseline,treatment,significant']

    for diff in diffs:
        lines.append(
            f'{diff.section},'
            f'{diff.field},'
            f'{diff.baseline_value},'
            f'{diff.treatment_value},'
            f'{diff.significant}'
        )

    return '\n'.join(lines)


def format_metadata_diff_plaintext(diffs: list[MetadataDiff]) -> str:
    """
    Format metadata differences as plain text.

    Args:
        diffs: List of metadata differences

    Returns:
        Plain text formatted string
    """
    if not diffs:
        return 'METADATA COMPARISON\n' + '='*60 + '\n\nNo significant differences in metadata.'

    lines = [
        'METADATA COMPARISON',
        '=' * 60,
        '',
    ]

    # Group by section
    sections: dict[str, list[MetadataDiff]] = {}
    for diff in diffs:
        if diff.section not in sections:
            sections[diff.section] = []
        sections[diff.section].append(diff)

    for section, section_diffs in sorted(sections.items()):
        lines.extend([
            section.upper(),
            '-' * 60,
            '',
        ])

        for diff in section_diffs:
            sig_marker = '[SIGNIFICANT]' if diff.significant else ''
            lines.extend([
                f'{diff.field}:',
                f'  Baseline:  {diff.baseline_value}',
                f'  Treatment: {diff.treatment_value}',
                f'  {sig_marker}',
                '',
            ])

    return '\n'.join(lines)


def filter_metadata_by_launch_id(
    metadata: dict[str, dict[str, Any]],
    launch_id: str | None,
) -> dict[str, dict[str, Any]]:
    """
    Filter metadata to only include data for a specific launch ID.

    Args:
        metadata: Full metadata dictionary
        launch_id: Launch ID to filter by (None = auto-detect single launch ID)

    Returns:
        Filtered metadata dictionary
    """
    filtered = {}
    for section, data in metadata.items():
        if section == 'Invariant parameters':
            if launch_id is not None:
                # Specific launch ID requested - extract its data
                if launch_id in data:
                    filtered[section] = data[launch_id]
                else:
                    filtered[section] = {}
            elif isinstance(data, dict) and len(data) == 1:
                # Auto-detect: if there's exactly one launch ID, extract its data
                # This removes the launch ID nesting so parameters can be compared directly
                filtered[section] = next(iter(data.values()))
            else:
                # Multiple launch IDs without filter - keep nested structure
                filtered[section] = data
        else:
            # Other sections are not launch-specific
            filtered[section] = data

    return filtered


def compare_metadata(
    treatment_md: Path,
    baseline_md: Path,
    show_all: bool = False,
    format: str = 'md',
    treatment_launch_id: str | None = None,
    baseline_launch_id: str | None = None,
    # Legacy parameter names for backwards compatibility
    current_md: Path | None = None,
    previous_md: Path | None = None,
    current_launch_id: str | None = None,
    previous_launch_id: str | None = None,
) -> str:
    """
    Compare metadata from two .md files.

    Args:
        treatment_md: Path to treatment run .md file
        baseline_md: Path to baseline run .md file
        show_all: If True, show all differences (not just significant ones)
        format: Output format ('md', 'csv', or 'plaintext')
        treatment_launch_id: Launch ID for treatment run (None = use all)
        baseline_launch_id: Launch ID for baseline run (None = use all)
        current_md: (Legacy) Alias for treatment_md
        previous_md: (Legacy) Alias for baseline_md
        current_launch_id: (Legacy) Alias for treatment_launch_id
        previous_launch_id: (Legacy) Alias for baseline_launch_id

    Returns:
        Formatted comparison string
    """
    # Handle legacy parameter names
    if current_md is not None:
        treatment_md = current_md
    if previous_md is not None:
        baseline_md = previous_md
    if current_launch_id is not None:
        treatment_launch_id = current_launch_id
    if previous_launch_id is not None:
        baseline_launch_id = previous_launch_id
    # Load metadata
    treatment_data = load_metadata(treatment_md)
    baseline_data = load_metadata(baseline_md)

    # Filter by launch ID if specified
    treatment_data = filter_metadata_by_launch_id(treatment_data, treatment_launch_id)
    baseline_data = filter_metadata_by_launch_id(baseline_data, baseline_launch_id)

    # Extract core count from metadata (prefer treatment, fall back to baseline)
    core_count = extract_core_count(treatment_data)
    if core_count is None:
        core_count = extract_core_count(baseline_data)

    # Compare all sections
    all_diffs = []
    all_sections = set(treatment_data.keys()) | set(baseline_data.keys())

    for section in all_sections:
        section_diffs = compare_section(
            section,
            treatment_data.get(section, {}),
            baseline_data.get(section, {}),
            show_all=show_all,
            core_count=core_count,
        )
        all_diffs.extend(section_diffs)

    # Format output
    match format:
        case 'md':
            return format_metadata_diff_markdown(all_diffs)
        case 'csv':
            return format_metadata_diff_csv(all_diffs)
        case 'plaintext':
            return format_metadata_diff_plaintext(all_diffs)
        case _:
            raise ValueError(f"Invalid format: {format}")
