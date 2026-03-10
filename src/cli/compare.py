#!/usr/bin/env python3
"""
SHARP run comparison tool.

Compare two benchmark runs by analyzing their CSV data distributions
and metadata differences. Outputs statistical comparison tables and
environment difference summaries.

Usage:
  compare [OPTIONS] CURRENT PREVIOUS

Examples:
  # Compare two runs in same experiment
  compare -e myexp run1.csv run2.csv

  # Compare with full paths
  compare runlogs/exp1/matmul.csv runlogs/exp2/matmul.csv

  # Compare specific metrics
  compare -m outer_time,cycles run1.csv run2.csv

  # Output as CSV
  compare --format csv run1.csv run2.csv

  # Compare specific launch IDs within same experiment
  compare -e myexp --current-launch-id abc123 --previous-launch-id def456 sweep.csv sweep.csv

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import argparse
import sys
from pathlib import Path

import polars as pl

from src.core.config.include_resolver import get_project_root
from src.core.runlogs.metadata_compare import compare_metadata, load_metadata
from src.core.stats.comparisons import comparison_table


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog='compare',
        description='Compare two benchmark runs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare two runs in same experiment
  compare -e myexp run1.csv run2.csv

  # Compare with full paths
  compare runlogs/exp1/matmul.csv runlogs/exp2/matmul.csv

  # Compare specific metrics (comma-separated)
  compare -m outer_time,cycles run1.csv run2.csv

  # Output as CSV instead of Markdown
  compare --format csv run1.csv run2.csv

  # Show all metadata (not just differences)
  compare --show-all run1.csv run2.csv

  # Compare specific launch IDs within same experiment
  compare -e myexp --current-launch-id abc123 --previous-launch-id def456 sweep.csv sweep.csv

  # Compare different launch IDs from different files
  compare --current-launch-id abc123 --previous-launch-id def456 run1.csv run2.csv
""",
    )

    parser.add_argument(
        'current',
        help='Current run CSV file (or filename if -e specified)',
    )

    parser.add_argument(
        'previous',
        help='Previous run CSV file (or filename if -e specified)',
    )

    parser.add_argument(
        '-e',
        '--experiment',
        help='Experiment directory name (searches in runlogs/<experiment>/)',
    )

    parser.add_argument(
        '--current-launch-id',
        help='Launch ID for current run (required if CSV has multiple launch IDs)',
    )

    parser.add_argument(
        '--previous-launch-id',
        help='Launch ID for previous run (required if CSV has multiple launch IDs)',
    )

    parser.add_argument(
        '-m',
        '--metrics',
        default='inner_time',
        help='Comma-separated list of metrics to compare (default: inner_time, falls back to outer_time)',
    )

    parser.add_argument(
        '--format',
        choices=['md', 'csv', 'plaintext'],
        default='md',
        help='Output format (default: md)',
    )

    parser.add_argument(
        '--show-all',
        action='store_true',
        help='Show all metadata fields (not just differences)',
    )

    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Show detailed progress information',
    )

    return parser.parse_args(argv)


def resolve_file_path(filename: str, experiment: str | None) -> Path:
    """
    Resolve a filename to a full path.

    Args:
        filename: Filename or path
        experiment: Experiment directory name (optional)

    Returns:
        Resolved Path object

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    # If filename is already a path, use it directly
    path = Path(filename)
    if path.is_absolute():
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path

    # If experiment specified, look in runlogs/<experiment>/
    if experiment:
        project_root = get_project_root()
        path = project_root / 'runlogs' / experiment / filename
        if not path.exists():
            raise FileNotFoundError(
                f"File not found: {path}\n"
                f"(looked in runlogs/{experiment}/ for '{filename}')"
            )
        return path

    # Otherwise, treat as relative to current directory
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path


def format_comparison_markdown(comparisons: list[dict]) -> str:
    """Format comparison results as Markdown table."""
    lines = ['# Statistical Comparison', '']

    for comp in comparisons:
        lines.append(f"## Metric: {comp['metric']}")
        lines.append('')
        lines.append('| Statistic | Baseline | Treatment |')
        lines.append('|-----------|----------|-----------|')

        # Summary statistics
        lines.append(f"| n | {comp['baseline_n']} | {comp['treatment_n']} |")
        lines.append(f"| median | {comp['baseline_median']} | {comp['treatment_median']} |")
        lines.append(f"| mean | {comp['baseline_mean']} | {comp['treatment_mean']} |")
        lines.append(f"| stddev | {comp['baseline_stddev']} | {comp['treatment_stddev']} |")
        lines.append('')

        # Change statistics
        lines.append('| Change | Value |')
        lines.append('|--------|-------|')
        lines.append(f"| Median diff | {comp['median_diff']} |")
        lines.append(f"| Percent change | {comp['pct_change']}% |")
        improved_str = 'Yes' if comp['improved'] else 'No'
        lines.append(f"| Improved | {improved_str} |")
        lines.append('')

        # Statistical tests
        lines.append('| Test | Statistic | p-value |')
        lines.append('|------|-----------|---------|')
        lines.append(f"| Mann-Whitney U | {comp['mann_whitney_u']} | {comp['p_value']} |")
        lines.append(f"| Effect size | {comp['effect_size']} | |")
        lines.append('')

    return '\n'.join(lines)


def format_comparison_csv(comparisons: list[dict]) -> str:
    """Format comparison results as CSV."""
    lines = ['metric,baseline_n,baseline_median,baseline_mean,baseline_stddev,'
             'treatment_n,treatment_median,treatment_mean,treatment_stddev,'
             'median_diff,pct_change,improved,mann_whitney_u,p_value,effect_size']

    for comp in comparisons:
        improved_str = 'Yes' if comp['improved'] else 'No'
        lines.append(
            f"{comp['metric']},"
            f"{comp['baseline_n']},{comp['baseline_median']},{comp['baseline_mean']},{comp['baseline_stddev']},"
            f"{comp['treatment_n']},{comp['treatment_median']},{comp['treatment_mean']},{comp['treatment_stddev']},"
            f"{comp['median_diff']},{comp['pct_change']},{improved_str},"
            f"{comp['mann_whitney_u']},{comp['p_value']},{comp['effect_size']}"
        )

    return '\n'.join(lines)


def format_comparison_plaintext(comparisons: list[dict]) -> str:
    """Format comparison results as plain text."""
    lines = ['Statistical Comparison', '=' * 60, '']

    for comp in comparisons:
        lines.append(f"Metric: {comp['metric']}")
        lines.append('-' * 60)

        # Summary statistics
        lines.append(f"  n:              Baseline: {comp['baseline_n']:>12}  Treatment: {comp['treatment_n']:>12}")
        lines.append(f"  median:         Baseline: {comp['baseline_median']:>12}  Treatment: {comp['treatment_median']:>12}")
        lines.append(f"  mean:           Baseline: {comp['baseline_mean']:>12}  Treatment: {comp['treatment_mean']:>12}")
        lines.append(f"  stddev:         Baseline: {comp['baseline_stddev']:>12}  Treatment: {comp['treatment_stddev']:>12}")
        lines.append('')

        # Change statistics
        improved_str = 'Yes' if comp['improved'] else 'No'
        lines.append(f"  Median diff:    {comp['median_diff']}")
        lines.append(f"  Percent change: {comp['pct_change']}%")
        lines.append(f"  Improved:       {improved_str}")
        lines.append('')

        # Statistical tests
        lines.append(f"  Mann-Whitney U: {comp['mann_whitney_u']}")
        lines.append(f"  p-value:        {comp['p_value']}")
        lines.append(f"  Effect size:    {comp['effect_size']}")
        lines.append('')

    return '\n'.join(lines)


def validate_and_filter_launch_ids(
    df: pl.DataFrame,
    file_path: Path,
    specified_launch_id: str | None,
    file_label: str,
) -> tuple[pl.DataFrame, int]:
    """
    Validate and filter DataFrame by launch_id if present.

    Args:
        df: DataFrame to validate and filter
        file_path: Path to the CSV file (for error messages)
        specified_launch_id: User-specified launch ID (optional)
        file_label: Label for error messages ('Current' or 'Previous')

    Returns:
        Tuple of (filtered DataFrame, exit_code)
        exit_code is 0 on success, 1 on error
    """
    if 'launch_id' not in df.columns:
        return df, 0

    launch_ids = df['launch_id'].unique().to_list()

    if len(launch_ids) > 1 and not specified_launch_id:
        print(
            f"Error: {file_label} file has multiple launch IDs: {', '.join(launch_ids)}\n"
            f"Please specify --{file_label.lower()}-launch-id to select one.",
            file=sys.stderr,
        )
        return df, 1

    if specified_launch_id:
        if specified_launch_id not in launch_ids:
            print(
                f"Error: Launch ID '{specified_launch_id}' not found in {file_label.lower()} file.\n"
                f"Available: {', '.join(launch_ids)}",
                file=sys.stderr,
            )
            return df, 1
        df = df.filter(pl.col('launch_id') == specified_launch_id)

    return df, 0


def determine_metrics_to_compare(
    args: argparse.Namespace,
    current_cols: set[str],
    previous_cols: set[str],
    current_path: Path,
    previous_path: Path,
) -> tuple[list[str], int]:
    """
    Determine which metrics to compare based on args and available columns.

    Args:
        args: Parsed command line arguments
        current_cols: Set of column names in current CSV
        previous_cols: Set of column names in previous CSV
        current_path: Path to current CSV (for error messages)
        previous_path: Path to previous CSV (for error messages)

    Returns:
        Tuple of (list of metrics, exit_code)
        exit_code is 0 on success, 1 on error
    """
    common_cols = current_cols & previous_cols

    # Handle default metric fallback
    if args.metrics == 'inner_time':
        # User didn't specify metrics, use default with fallback
        if 'inner_time' in common_cols:
            metrics = ['inner_time']
            if args.verbose:
                print("Using default metric: inner_time", file=sys.stderr)
        elif 'outer_time' in common_cols:
            metrics = ['outer_time']
            if args.verbose:
                print("Falling back to metric: outer_time (inner_time not available)", file=sys.stderr)
        else:
            print(
                "Error: Neither 'inner_time' nor 'outer_time' found in both CSV files.\n"
                f"Available in both: {', '.join(sorted(common_cols)) if common_cols else '(none)'}",
                file=sys.stderr,
            )
            return [], 1
    else:
        # User specified metrics explicitly
        metrics = [m.strip() for m in args.metrics.split(',')]

    # Validate all specified metrics are in both CSVs (intersection)
    missing_from_intersection = [m for m in metrics if m not in common_cols]

    if missing_from_intersection:
        print(
            f"Error: Metrics must exist in both CSV files: {', '.join(missing_from_intersection)}",
            file=sys.stderr,
        )
        missing_current = [m for m in missing_from_intersection if m not in current_cols]
        missing_previous = [m for m in missing_from_intersection if m not in previous_cols]
        if missing_current:
            print(f"  Not in {current_path.name}: {', '.join(missing_current)}", file=sys.stderr)
        if missing_previous:
            print(f"  Not in {previous_path.name}: {', '.join(missing_previous)}", file=sys.stderr)
        print(f"\nMetrics in both files: {', '.join(sorted(common_cols)) if common_cols else '(none)'}", file=sys.stderr)
        return [], 1

    # Check that we have at least one valid metric
    if not metrics:
        print(
            "Error: No metrics to compare.\n"
            f"Available in both: {', '.join(sorted(common_cols)) if common_cols else '(none)'}",
            file=sys.stderr,
        )
        return [], 1

    return metrics, 0


def load_metric_definitions(md_path: Path) -> dict[str, bool]:
    """
    Load metric definitions from metadata file.

    Args:
        md_path: Path to .md metadata file

    Returns:
        Dictionary mapping metric names to lower_is_better bool
    """
    metric_definitions = {}
    if md_path.exists():
        metadata = load_metadata(md_path)
        runtime_options = metadata.get('Initial runtime options', {})
        metrics_def = runtime_options.get('metrics', {})
        for metric_name, metric_info in metrics_def.items():
            metric_definitions[metric_name] = metric_info.get('lower_is_better', True)
    return metric_definitions


def compare_metrics(
    metrics: list[str],
    current_df: pl.DataFrame,
    previous_df: pl.DataFrame,
    metric_definitions: dict[str, bool],
) -> list[dict]:
    """
    Compare metrics between current and previous DataFrames.

    Args:
        metrics: List of metric names to compare
        current_df: Current run DataFrame
        previous_df: Previous run DataFrame
        metric_definitions: Dictionary of metric_name -> lower_is_better

    Returns:
        List of comparison result dictionaries
    """
    comparisons = []
    for metric in metrics:
        current_data = current_df[metric].drop_nulls().to_numpy()
        previous_data = previous_df[metric].drop_nulls().to_numpy()

        if len(current_data) == 0 or len(previous_data) == 0:
            print(f"Warning: Metric '{metric}' has no valid data", file=sys.stderr)
            continue

        # Determine if lower is better for this metric
        lower_is_better = metric_definitions.get(metric, True)
        better_direction = 'lower' if lower_is_better else 'higher'

        result = comparison_table(
            baseline=previous_data,
            treatment=current_data,
            metric=metric,
            better=better_direction,
            digits=5,
        )
        comparisons.append(result)

    return comparisons


def output_metadata_comparison(
    args: argparse.Namespace,
    treatment_md: Path,
    baseline_md: Path,
) -> None:
    """
    Compare and output metadata differences if files exist.

    Args:
        args: Parsed command line arguments
        treatment_md: Path to treatment .md file
        baseline_md: Path to baseline .md file
    """
    if treatment_md.exists() and baseline_md.exists():
        if args.verbose:
            print("\n" + "=" * 60, file=sys.stderr)
            print("Metadata Comparison", file=sys.stderr)
            print("=" * 60 + "\n", file=sys.stderr)

        # Pass launch IDs for metadata filtering
        metadata_diff = compare_metadata(
            treatment_md,
            baseline_md,
            show_all=args.show_all,
            format=args.format,
            treatment_launch_id=args.current_launch_id,
            baseline_launch_id=args.previous_launch_id,
        )

        if metadata_diff:
            print("\n" + metadata_diff)
    elif args.verbose:
        print("\nNote: Metadata files not found for comparison", file=sys.stderr)
        if not treatment_md.exists():
            print(f"  Missing: {treatment_md}", file=sys.stderr)
        if not baseline_md.exists():
            print(f"  Missing: {baseline_md}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the compare command.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args(argv)

    try:
        current_path = resolve_file_path(args.current, args.experiment)
        previous_path = resolve_file_path(args.previous, args.experiment)

        if args.verbose:
            print(f"Comparing: {current_path}", file=sys.stderr)
            print(f"     with: {previous_path}", file=sys.stderr)
            print("", file=sys.stderr)

        # Load CSV data
        current_df = pl.read_csv(current_path)
        previous_df = pl.read_csv(previous_path)

        # Validate and filter by launch_id if present
        current_df, exit_code = validate_and_filter_launch_ids(
            current_df, current_path, args.current_launch_id, 'Current'
        )
        if exit_code != 0:
            return exit_code

        previous_df, exit_code = validate_and_filter_launch_ids(
            previous_df, previous_path, args.previous_launch_id, 'Previous'
        )
        if exit_code != 0:
            return exit_code

        # Determine which metrics to compare
        current_cols = set(current_df.columns)
        previous_cols = set(previous_df.columns)
        metrics, exit_code = determine_metrics_to_compare(
            args, current_cols, previous_cols, current_path, previous_path
        )
        if exit_code != 0:
            return exit_code

        # Load metric definitions from metadata
        treatment_md = current_path.with_suffix('.md')
        metric_definitions = load_metric_definitions(treatment_md)

        # Compare metrics
        comparisons = compare_metrics(metrics, current_df, previous_df, metric_definitions)

        # Format and output results
        match args.format:
            case 'md':
                output = format_comparison_markdown(comparisons)
            case 'csv':
                output = format_comparison_csv(comparisons)
            case 'plaintext':
                output = format_comparison_plaintext(comparisons)

        print(output)

        # Compare metadata if .md files exist
        baseline_md = previous_path.with_suffix('.md')
        output_metadata_comparison(args, treatment_md, baseline_md)

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
