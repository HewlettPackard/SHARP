"""
Markdown parsing utilities for SHARP runlogs.

Functions for extracting runtime options and metadata from experiment
markdown files. Handles both runtime options extraction and field parsing.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import json
import re
import yaml
from pathlib import Path
from datetime import datetime
from typing import Any, Dict


def extract_runtime_options_from_markdown(md_path: str | Path) -> Dict[str, Any] | None:
    """
    Extract raw runtime options from markdown file without modification.

    Supports both V4 (YAML frontmatter) and pre-V4 (JSON runtime options) formats.

    Args:
        md_path: Path to markdown file

    Returns:
        Dictionary containing runtime options, or None if not found

    Example pre-v4 format:
        ## Runtime options
        ```json
        {
          "entry_point": "/path/to/benchmark",
          "args": ["arg1", "arg2"],
          "task": "taskname",
          ...
        }
        ```

    Example V4 format (YAML frontmatter):
        ---
        benchmark_spec:
          entry_point: /path/to/benchmark
          args: ["arg1", "arg2"]
          task: taskname
        backend_options:
          local:
            run: $CMD $ARGS
        repeats: MAX
        ...
        ---
    """
    try:
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            return None

        with open(md_path_obj, 'r') as f:
            content = f.read()

        # Try V4 format first (YAML frontmatter)
        if content.startswith("---"):
            frontmatter_dict = _parse_yaml_frontmatter(content)
            if frontmatter_dict:
                # Convert V4 frontmatter to runtime options format
                runtime_opts = {}

                # Extract benchmark_spec fields
                if "benchmark_spec" in frontmatter_dict:
                    spec = frontmatter_dict["benchmark_spec"]
                    if isinstance(spec, dict):
                        runtime_opts.update(spec)  # Includes entry_point, args, task

                # Copy all top-level keys except benchmark_spec (which is already extracted)
                for key, value in frontmatter_dict.items():
                    if key != "benchmark_spec":
                        runtime_opts[key] = value

                # Extract backend_names from backend_options if not already present
                if "backend_names" not in runtime_opts and "backend_options" in runtime_opts:
                    backend_opts = runtime_opts["backend_options"]
                    if isinstance(backend_opts, dict):
                        runtime_opts["backend_names"] = list(backend_opts.keys())

                return runtime_opts

        # Try pre-v4 format (JSON runtime options)
        # Runtime options headings vary between "## Runtime options" (legacy)
        # and "## Starting runtime options" (current writer). Match any header
        # that includes the phrase to locate the correct JSON block.
        runtime_section = re.search(r'##\s+[^\n]*runtime options', content, re.IGNORECASE)
        if not runtime_section:
            return None

        json_block_start = content.find('```json', runtime_section.end())
        if json_block_start == -1:
            return None

        json_block_end = content.find('```', json_block_start + 7)
        if json_block_end == -1:
            return None

        json_str = content[json_block_start + 7:json_block_end].strip()
        data = json.loads(json_str)
        if isinstance(data, dict):
            return data
        return None

    except Exception as e:
        print(f"Error extracting runtime options from {md_path}: {e}")
        return None


def parse_markdown_runtime_options(md_file_path: Path) -> Dict[str, Any]:
    """
    Parse markdown file to extract rerun configuration.

    Supports both V4 (YAML frontmatter) and pre-V4 (JSON runtime options) formats.

    Args:
        md_file_path: Path to the markdown file

    Returns:
        Dictionary with configuration for rerunning the experiment
    """
    config: dict[str, Any] = {}

    try:
        # Extract raw runtime options using shared function
        runtime_opts = extract_runtime_options_from_markdown(md_file_path)

        if not runtime_opts:
            return config

        # Extract relevant fields for measure tab
        # Benchmark: combine entry_point + args
        if 'entry_point' in runtime_opts:
            bench_parts = [runtime_opts['entry_point']]
            if 'args' in runtime_opts and runtime_opts['args']:
                bench_parts.extend(runtime_opts['args'])
            config['bench'] = ' '.join(bench_parts)

        # Task name
        if 'task' in runtime_opts:
            config['task'] = runtime_opts['task']

        # Experiment name (extract from file path if not in runtime_opts)
        if md_file_path.parent.name:
            config['experiment'] = md_file_path.parent.name

        # Backend handling: if multiple backends or want to preserve order, use moreopts
        if 'backend_names' in runtime_opts and runtime_opts['backend_names']:
            backends = runtime_opts['backend_names']
            if len(backends) == 1:
                # Single backend - can use the dropdown
                config['backend'] = backends[0]
            else:
                # Multiple backends - need to use moreopts to preserve order
                config['backend'] = None  # Will set dropdown to "(none)"
                # Prepend -b flags to moreopts
                backend_flags = ' '.join([f'-b {b}' for b in backends])
                config['backend_flags'] = backend_flags  # Will prepend to moreopts
        else:
            # No backends specified
            config['backend'] = None

        # Repeater configuration
        if 'repeats' in runtime_opts:
            config['stopping'] = runtime_opts['repeats']

        # Extract max runs from repeater_options for GUI's "n" field
        if 'repeater_options' in runtime_opts:
            repeater_options = runtime_opts['repeater_options']
            # Handle both flat format {"max": 100} and nested format {"CR": {"max": 100}}
            if isinstance(repeater_options, dict):
                if 'max' in repeater_options:
                    # Flat format: {"max": 100}
                    config['max_runs'] = repeater_options['max']
                else:
                    # Nested format: {"CR": {"max": 100}}
                    for repeater_key, repeater_opts in repeater_options.items():
                        if isinstance(repeater_opts, dict) and 'max' in repeater_opts:
                            config['max_runs'] = repeater_opts['max']
                            break

        # Execution options
        if 'start' in runtime_opts:
            config['start'] = runtime_opts['start']

        if 'mpl' in runtime_opts:
            config['mpl'] = runtime_opts['mpl']

        if 'timeout' in runtime_opts:
            config['timeout'] = runtime_opts['timeout']

    except Exception as e:
        print(f"Error parsing rerun config from {md_file_path}: {e}")
        import traceback
        traceback.print_exc()

    return config


def parse_markdown_metadata(md_path: Path) -> dict[str, Any]:
    """
    Parse metadata from markdown file.

    Supports V4 markdown files with JSON runtime options in code blocks.

    Args:
        md_path: Path to markdown file

    Returns:
        Dict with extracted metadata (timestamp, benchmark, backends, duration, etc.).
        Returns empty dict if file cannot be parsed.
    """
    metadata: dict[str, Any] = {}

    try:
        content = md_path.read_text()

        # Try to extract from JSON runtime options block
        metadata = _extract_from_json_block(content)

        # If that fails, try YAML frontmatter
        if not metadata:
            metadata = _extract_v4_metadata(content)

        # Extract duration from summary line if not already present
        if "duration" not in metadata:
            duration = _extract_duration_from_summary(content)
            if duration is not None:
                metadata["duration"] = duration

        # Extract row count from summary line (V4 format only)
        row_count = _extract_row_count_from_summary(content)
        if row_count is not None:
            metadata["rows"] = row_count

    except Exception:
        # Silently fail - return empty metadata
        pass

    return metadata


def _extract_from_json_block(content: str) -> dict[str, Any]:
    """
    Extract metadata from JSON runtime options block in markdown.

    Args:
        content: Markdown file content

    Returns:
        Dict with metadata extracted from JSON block
    """
    metadata: dict[str, Any] = {}

    try:
        import json
        import re

        # Find JSON block between ```json and ```
        json_match = re.search(r'```json\s*\n(.*?)\n```', content, re.DOTALL)
        if not json_match:
            return {}

        json_str = json_match.group(1)
        runtime_opts = json.loads(json_str)

        # Extract backends from backend_names or backend_options
        if "backend_names" in runtime_opts:
            backends = runtime_opts["backend_names"]
            if isinstance(backends, list):
                metadata["backends"] = backends
            elif isinstance(backends, str):
                metadata["backends"] = [backends]
        elif "backend_options" in runtime_opts:
            backend_opts = runtime_opts["backend_options"]
            if isinstance(backend_opts, dict):
                metadata["backends"] = list(backend_opts.keys())

        # Extract benchmark from entry_point
        if "entry_point" in runtime_opts:
            entry_point = runtime_opts["entry_point"]
            if isinstance(entry_point, str):
                metadata["benchmark"] = Path(entry_point).stem

    except (json.JSONDecodeError, KeyError, AttributeError) as e:
        print(f"[DEBUG] Error extracting from JSON block: {e}")
        return {}

    return metadata


def _extract_v4_metadata(content: str) -> dict[str, Any]:
    """
    Extract metadata from V4 markdown with YAML frontmatter.

    Args:
        content: Markdown file content

    Returns:
        Dict with metadata (timestamp, benchmark, backends, duration, etc.)
        Returns empty dict if no frontmatter found or parsing fails
    """
    metadata: dict[str, Any] = {}

    if not content.startswith("---"):
        return metadata

    frontmatter_dict = _parse_yaml_frontmatter(content)
    if not frontmatter_dict:
        return metadata

    # Extract benchmark name
    if "benchmark_spec" in frontmatter_dict:
        benchmark_spec = frontmatter_dict["benchmark_spec"]
        if isinstance(benchmark_spec, dict):
            metadata["benchmark"] = benchmark_spec.get("task")

    # Extract backend names
    # Try backend_options first (most common), then backend_names
    if "backend_options" in frontmatter_dict:
        backend_opts = frontmatter_dict["backend_options"]
        if isinstance(backend_opts, dict):
            metadata["backends"] = list(backend_opts.keys())
    elif "backend_names" in frontmatter_dict:
        backend_names = frontmatter_dict["backend_names"]
        if isinstance(backend_names, list):
            metadata["backends"] = backend_names
        elif isinstance(backend_names, str):
            metadata["backends"] = [backend_names]

    # Extract timestamp
    timestamp = _extract_timestamp_from_dict(frontmatter_dict)
    if timestamp:
        metadata["timestamp"] = timestamp

    return metadata


def _parse_yaml_frontmatter(content: str) -> dict[str, Any] | None:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: Markdown file content (must start with ---)

    Returns:
        Parsed YAML dict, or None if parsing fails
    """
    lines = content.split("\n")
    yaml_lines = []
    in_frontmatter = False
    frontmatter_count = 0

    for line in lines:
        if line.strip() == "---":
            frontmatter_count += 1
            if frontmatter_count == 1:
                in_frontmatter = True
                continue
            elif frontmatter_count == 2:
                in_frontmatter = False
                break
        if in_frontmatter:
            yaml_lines.append(line)

    if not yaml_lines:
        return None

    try:
        frontmatter = yaml.safe_load("\n".join(yaml_lines))
        return frontmatter if isinstance(frontmatter, dict) else None
    except (yaml.YAMLError, AttributeError, TypeError):
        return None


def _extract_timestamp_from_dict(data: dict[str, Any]) -> datetime | None:
    """
    Extract timestamp from a dictionary using multiple possible field names.

    Args:
        data: Dictionary that may contain timestamp fields

    Returns:
        datetime object or None if not found
    """
    for key in ["timestamp", "start_time", "created_at"]:
        if key in data:
            ts = _parse_timestamp(data[key])
            if ts:
                return ts
    return None


def _extract_pre_v4_metadata(content: str) -> dict[str, Any]:
    """
    Extract metadata from pre-v4 format markdown (JSON runtime options).

    Args:
        content: Markdown file content

    Returns:
        Dict with extracted metadata, empty dict if not pre-v4 format
    """
    metadata: dict[str, Any] = {}

    # Find JSON block (usually after "## Runtime options")
    json_match = re.search(r'##\s+Runtime\s+options\s*\n\s*(\{.*?\n\})', content, re.DOTALL)
    if not json_match:
        return metadata

    try:
        runtime_opts = json.loads(json_match.group(1))
        if not isinstance(runtime_opts, dict):
            return metadata

        # Extract benchmark name
        metadata["benchmark"] = runtime_opts.get("task")

        # Extract backend names
        backends = runtime_opts.get("backends")
        if isinstance(backends, list):
            metadata["backends"] = backends

        # Extract timestamp
        if "start" in runtime_opts:
            ts = _parse_timestamp(runtime_opts["start"])
            if ts:
                metadata["timestamp"] = ts

    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    return metadata


def _extract_duration_from_summary(content: str) -> float | None:
    """
    Extract duration from experiment summary line.

    Format: "Experiment completed at <timestamp> (total experiment time: <duration>)."

    Args:
        content: Markdown file content

    Returns:
        Duration in seconds, or None if not found
    """
    duration_match = re.search(r'total experiment time:\s*(\d+(?:\.\d+)?)\s*([smh])', content)
    if not duration_match:
        return None

    try:
        value = float(duration_match.group(1))
        unit = duration_match.group(2)

        # Convert to seconds
        if unit == 'm':
            return value * 60
        elif unit == 'h':
            return value * 3600
        else:
            return value

    except (ValueError, AttributeError, TypeError):
        return None


def _extract_row_count_from_summary(content: str) -> int | None:
    """
    Extract row count from experiment summary line.

    Format: "Experiment completed at <timestamp> (total experiment time: <duration>, total rows: <count>)."

    Args:
        content: Markdown file content

    Returns:
        Row count as integer, or None if not found
    """
    row_match = re.search(r'total rows:\s*(\d+)', content)
    if not row_match:
        return None

    try:
        return int(row_match.group(1))
    except (ValueError, AttributeError, TypeError):
        return None



def _parse_timestamp(ts_value: Any) -> datetime | None:
    """
    Parse timestamp from various formats.

    Args:
        ts_value: Timestamp value (string, datetime, or numeric)

    Returns:
        datetime object or None if parsing fails
    """
    if isinstance(ts_value, datetime):
        return ts_value

    if isinstance(ts_value, str):
        # Try common datetime formats
        for fmt in [
            "%Y-%m-%d %H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
        ]:
            try:
                return datetime.strptime(ts_value, fmt)
            except ValueError:
                continue

    if isinstance(ts_value, (int, float)):
        try:
            return datetime.fromtimestamp(ts_value)
        except (ValueError, OSError):
            pass

    return None
