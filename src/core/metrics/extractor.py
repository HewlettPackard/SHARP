"""
Metrics extraction from benchmark outputs.

Extracts numerical metrics from command outputs using regex patterns
or shell commands defined in benchmark/backend configurations.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import re
import subprocess
import warnings
from typing import Any, Dict, List, Optional

from src.core.rundata import RunData


class MetricExtractor:
    """
    Extracts metrics from benchmark output files.

    Supports:
    - Shell command-based extraction (e.g., grep | awk)
    - Regex-based extraction
    - Auto-metrics (format: "name value" per line)
    """

    def __init__(self, metric_specs: Dict[str, Dict[str, Any]]) -> None:
        """
        Initialize extractor with metric specifications.

        Args:
            metric_specs: Dict mapping metric name to extraction spec:
                {
                    "inner_time": {
                        "extract": "grep 'Time:' output.txt | awk '{print $NF}'",
                        "type": "float",
                        "units": "seconds"
                    },
                    "auto": {
                        "extract": "cat results.txt | grep '^[a-z]'",
                        "type": "auto"
                    }
                }
        """
        self.metric_specs = metric_specs

    def extract(self, output_file: str, outer_metrics: Dict[str, List[str]] = {}) -> RunData:
        """
        Extract all metrics from an output file.

        Args:
            output_file: Path to file with command output
            outer_metrics: Additional metrics to merge (e.g., outer_time from orchestrator)

        Returns:
            RunData object containing extracted metrics

        Raises:
            RuntimeError if extraction fails for required metrics
            ValueError if outer_time not present in extracted metrics
        """
        metrics: Dict[str, List[str]] = {}

        for name, spec in self.metric_specs.items():
            if not spec:
                continue

            cmd = spec.get("extract", "")
            if not cmd:
                continue

            # Run extraction command
            try:
                full_cmd = f"cat {output_file} | {cmd}"
                result = subprocess.run(
                    full_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode != 0 or not result.stdout:
                    warnings.warn(
                        f"Failed to extract metric {name}: {result.stderr or 'No output'}"
                    )
                    metrics[name] = ["NA"]
                    continue

                # Parse output
                if name == "auto":
                    # Auto-metrics: each line is "name value"
                    auto_metrics = self._parse_auto_metrics(result.stdout)
                    metrics.update(auto_metrics)
                else:
                    # Regular metric: values separated by whitespace/newlines
                    metrics[name] = result.stdout.split()

            except subprocess.TimeoutExpired:
                warnings.warn(f"Extraction timeout for metric {name}")
                metrics[name] = ["NA"]
            except Exception as e:
                warnings.warn(f"Extraction error for metric {name}: {e}")
                metrics[name] = ["NA"]

        # Validate all metrics have same number of values
        if metrics:
            value_counts = [len(vals) for vals in metrics.values()]
            if len(set(value_counts)) > 1:
                raise RuntimeError(
                    f"Metrics have inconsistent value counts: {metrics}"
                )

        # Return RunData (validates outer_time is present)
        return RunData(metrics | outer_metrics)

    def _parse_auto_metrics(self, output: str) -> Dict[str, List[str]]:
        """
        Parse auto-metrics from output (format: "name value" per line).

        Args:
            output: Multi-line output with "name value" per line

        Returns:
            Dict mapping metric name to list of values
        """
        metrics: dict[str, list[str]] = {}
        for line in output.splitlines():
            cols = line.split()
            if len(cols) < 2:
                continue
            name, value = cols[0], cols[1]
            if name not in metrics:
                metrics[name] = []
            metrics[name].append(value)
        return metrics

    def validate_metrics(self, metrics: Dict[str, List[str]],
                        required: Optional[List[str]] = None) -> bool:
        """
        Validate extracted metrics.

        Args:
            metrics: Extracted metrics dict
            required: List of required metric names

        Returns:
            True if all required metrics are present and non-NA

        Raises:
            ValueError if validation fails
        """
        if not required:
            return True

        for name in required:
            if name not in metrics:
                raise ValueError(f"Required metric '{name}' not found")
            if all(v == "NA" for v in metrics[name]):
                raise ValueError(f"Required metric '{name}' has only NA values")

        return True
