# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Measure-page service helpers."""

import importlib.util
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any
from typing import Callable

import polars as pl

from src.cli.launch import _resolve_entry_point_for_backend, load_backend_options
from src.core.config.benchmarks import find_benchmark_by_entry_point, load_benchmark_data, resolve_benchmark_input
from src.core.config.settings import Settings
from src.core.execution.orchestrator import ExecutionOrchestrator
from src.core.execution.orchestrator import ProgressCallbacks
from src.core.repeaters import REPEATER_REGISTRY
from src.core.runlogs import parse_markdown_runtime_options
from src.gui.services.experiments import list_backends, list_benchmarks


_PACKAGE_IMPORT_OVERRIDES = {
    "pyyaml": "yaml",
    "scikit-learn": "sklearn",
    "pillow": "PIL",
}


def _normalize_requirement_name(requirement: str) -> str:
    """Extract package name from a requirement string."""
    token = re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0]
    return token.strip()


def _missing_python_requirements(requirements: list[str]) -> list[str]:
    """Return missing Python requirements for the active interpreter."""
    missing: list[str] = []
    for requirement in requirements:
        package_name = _normalize_requirement_name(requirement)
        if not package_name:
            continue
        module_name = _PACKAGE_IMPORT_OVERRIDES.get(package_name.lower(), package_name.replace("-", "_"))
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)
    return missing


def _python_dependency_preflight_error(
    entry_point: str,
    benchmark_name: str | None,
    benchmark_data: dict[str, Any] | None,
    backend_names: list[str],
) -> str | None:
    """Build a user-facing error if local Python benchmark deps are missing."""
    if not entry_point.endswith(".py"):
        return None
    if not benchmark_data:
        return None

    local_style_backends = {"local", "perf", "strace", "bintime", "temps", "uname"}
    if backend_names and any(name not in local_style_backends for name in backend_names):
        return None

    py_requirements = benchmark_data.get("build", {}).get("requires", {}).get("python", [])
    if not isinstance(py_requirements, list) or not py_requirements:
        return None

    missing_requirements = _missing_python_requirements([str(req) for req in py_requirements])
    if not missing_requirements:
        return None

    benchmark_label = benchmark_name or Path(entry_point).stem
    missing_csv = ", ".join(sorted(set(missing_requirements)))
    return (
        f"Benchmark '{benchmark_label}' needs Python packages that are missing from the current GUI environment: "
        f"{missing_csv}. Build the benchmark AppImage and rerun, or install the missing packages in the active "
        f"environment."
    )


def _resolve_gui_entry_command(entry_point: str, args: list[str]) -> tuple[str, list[str]]:
    """Run Python script benchmarks with an interpreter that has project deps."""
    if not entry_point.endswith(".py"):
        return entry_point, args

    if importlib.util.find_spec("flask") is None:
        uv_path = shutil.which("uv")
        if uv_path:
            return uv_path, ["run", "python", entry_point, *args]

    return sys.executable, [entry_point, *args]


def _friendly_benchmark_input(benchmark_input: str) -> str:
    """Convert a benchmark path back to a friendly benchmark name when possible."""
    if not benchmark_input:
        return benchmark_input

    parts = benchmark_input.split(maxsplit=1)
    entry_point = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    try:
        benchmark_name, _, _ = find_benchmark_by_entry_point(entry_point)
        return f"{benchmark_name} {args}".strip()
    except ValueError:
        return benchmark_input


def _load_benchmark_context(benchmark_input: str, entry_point: str) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve benchmark metadata for YAML-backed benchmarks or known entry points."""
    benchmark_name = benchmark_input.split()[0] if benchmark_input.split() else ""

    try:
        benchmark_data, benchmark_metrics = load_benchmark_data(benchmark_name)
        return benchmark_name, benchmark_data, benchmark_metrics
    except Exception:
        pass

    try:
        benchmark_name, benchmark_data, benchmark_metrics = find_benchmark_by_entry_point(entry_point)
        return benchmark_name, benchmark_data, benchmark_metrics
    except ValueError:
        return None, None, None


def _repeater_label(key: str, metadata: dict[str, Any]) -> str:
    """Build a human-friendly repeater label from registry metadata."""
    repeater_class = metadata.get("class")
    class_name = getattr(repeater_class, "__name__", "")
    if class_name.endswith("Repeater"):
        base = class_name.removesuffix("Repeater")
        if base.isupper():
            return base
        parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", base)
        return parts.strip()
    return key


def load_measure_form_data() -> dict[str, Any]:
    """Load selectable options and defaults for the Measure page."""
    settings = Settings()

    benchmark_items = list_benchmarks().benchmarks
    backend_items = list_backends().backends

    repeaters: list[dict[str, str]] = []
    for key, metadata in REPEATER_REGISTRY.items():
        repeaters.append(
            {
                "key": key,
                "label": _repeater_label(key, metadata),
                "description": str(metadata.get("description") or ""),
            }
        )

    return {
        "default_experiment": settings.get("gui.default_experiment", "misc"),
        "benchmarks": [item.name for item in benchmark_items],
        "backends": [item.name for item in backend_items],
        "repeaters": repeaters,
    }


def load_rerun_prefill(rerun_csv_path: str | None, fallback_experiment: str | None, fallback_task: str | None) -> dict[str, Any]:
    """Load rerun form defaults from markdown runtime options when available."""
    data: dict[str, Any] = {}
    if fallback_experiment:
        data["experiment"] = fallback_experiment
    if fallback_task:
        data["task"] = fallback_task

    if not rerun_csv_path:
        return data

    csv_path = Path(rerun_csv_path)
    md_path = csv_path.with_suffix(".md")
    if not md_path.exists():
        return data

    try:
        cfg = parse_markdown_runtime_options(md_path)
        if cfg.get("bench"):
            data["bench"] = _friendly_benchmark_input(str(cfg["bench"]))
        if cfg.get("task"):
            data["task"] = cfg["task"]
        if cfg.get("experiment"):
            data["experiment"] = cfg["experiment"]
        if cfg.get("stopping"):
            data["stopping"] = cfg["stopping"]
        if cfg.get("max_runs"):
            data["n"] = cfg["max_runs"]
        if cfg.get("start"):
            data["start"] = cfg["start"]
        if cfg.get("mpl"):
            data["mpl"] = cfg["mpl"]
        if cfg.get("timeout"):
            data["timeout"] = cfg["timeout"]
        if cfg.get("backend"):
            data["backend_selected"] = [cfg["backend"]]
        data["rerun_csv_path"] = str(csv_path)
    except Exception:
        # Non-fatal for rerun: fallback query params are still applied.
        pass

    return data


def run_measure_workflow(
    form: dict[str, Any],
    progress_callback: Callable[[int, int | None], None] | None = None,
) -> dict[str, Any]:
    """Run a benchmark experiment and return status/details for UI rendering."""
    experiment = str(form.get("experiment") or "").strip()
    bench = str(form.get("bench") or "").strip()

    if not experiment:
        return {"success": False, "error": "Experiment name is required."}
    if not bench:
        return {
            "success": False,
            "error": "Benchmark field is required. Please enter a benchmark name or path.",
        }

    task_input = str(form.get("task") or "").strip()
    stopping_rule = str(form.get("stopping") or "COUNT")
    max_runs = max(1, int(form.get("n") or 1))
    timeout = max(1, int(form.get("timeout") or 60))
    mpl = max(1, int(form.get("mpl") or 1))
    start_mode = str(form.get("start") or "as-is")

    # Preserve order, remove empty values.
    backend_names = [b for b in list(form.get("backend") or []) if str(b).strip()]

    start_time = time.time()

    try:
        benchmark_info = resolve_benchmark_input(
            benchmark_input=bench,
            override_task=task_input if task_input else None,
        )

        entry_point = benchmark_info["entry_point"]
        args = list(benchmark_info["args"])
        task_name = benchmark_info["task"]
        benchmark_name, benchmark_data, benchmark_metrics = _load_benchmark_context(bench, entry_point)

        config: dict[str, Any] = {}
        backend_options = load_backend_options(backend_names, config) if backend_names else {}

        if benchmark_name and benchmark_data:
            entry_point = _resolve_entry_point_for_backend(
                benchmark_name,
                benchmark_data,
                backend_names or ["local"],
            )

        dependency_error = _python_dependency_preflight_error(
            entry_point,
            benchmark_name,
            benchmark_data,
            backend_names,
        )
        if dependency_error:
            return {
                "success": False,
                "error": dependency_error,
            }

        entry_point, args = _resolve_gui_entry_command(entry_point, args)

        repeater_key = "CR" if stopping_rule == "COUNT" else stopping_rule
        options: dict[str, Any] = {
            "entry_point": entry_point,
            "args": args,
            "task": task_name,
            "backend_names": backend_names,
            "backend_options": backend_options,
            "fail_on_nonzero": True,
            "repeats": stopping_rule,
            "repeater_options": {
                repeater_key: {
                    "max": max_runs,
                }
            },
            "timeout": timeout,
            "verbose": True,
            "start": start_mode,
            "mpl": mpl,
            "directory": "runlogs",
            "skip_sys_specs": False,
            "mode": "w",
        }

        if "metrics" in config:
            options["metrics"] = config["metrics"]

        # Merge benchmark-specific metrics when benchmark name is known.
        if benchmark_metrics:
            options.setdefault("metrics", {})
            options["metrics"].update(benchmark_metrics)

        orchestrator = ExecutionOrchestrator(options=options, experiment_name=experiment)

        # Count iterations via callback closure.
        counter: list[int] = [0]
        total_iterations = max_runs if stopping_rule == "COUNT" else None

        if progress_callback is not None:
            progress_callback(0, total_iterations)

        def on_iteration_complete(iteration: int, metrics: dict[str, Any]) -> None:
            counter[0] = iteration
            if progress_callback is not None:
                progress_callback(iteration, total_iterations)

        callbacks = ProgressCallbacks(
            on_iteration_complete=on_iteration_complete,
        )

        result = orchestrator.run(callbacks)

        if not result.success:
            return {
                "success": False,
                "error": f"Experiment failed: {result.error_message or 'unknown error'}",
            }

        duration_seconds = max(0.0, time.time() - start_time)
        iterations_done = counter[0]
        if stopping_rule == "COUNT":
            iter_note = f"{iterations_done}/{max_runs} iterations"
        else:
            iter_note = f"{iterations_done} iteration{'s' if iterations_done != 1 else ''}"
        return {
            "success": True,
            "experiment": experiment,
            "task": task_name,
            "csv_path": result.output_paths.get("csv"),
            "md_path": result.output_paths.get("markdown"),
            "duration_seconds": duration_seconds,
            "notice": f"Run completed ({iter_note}) in {format_duration(duration_seconds)}.",
        }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


def load_measure_outputs(csv_path: str | None, md_path: str | None) -> dict[str, Any]:
    """Load run outputs for rendering in the Measure tab."""
    payload: dict[str, Any] = {
        "results_columns": [],
        "results_rows": [],
        "metadata_text": "No results yet. Click Run to start an experiment.",
    }

    if csv_path:
        try:
            df = pl.read_csv(Path(csv_path))
            payload["results_columns"] = list(df.columns)
            payload["results_rows"] = [list(row.values()) for row in df.to_dicts()]
        except Exception as exc:  # noqa: BLE001
            payload["metadata_text"] = f"Error loading CSV results: {exc}"

    if md_path:
        try:
            payload["metadata_text"] = Path(md_path).read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            payload["metadata_text"] = f"Error loading metadata: {exc}"

    return payload


def format_duration(seconds: float) -> str:
    """Format duration like old Measure completion status."""
    total = int(max(0, seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"