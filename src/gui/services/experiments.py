# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Discovery services for the SHARP GUI API."""

from collections import defaultdict

from src.cli.discovery import get_backend_names, get_benchmark_names
from src.core.config.loader import discover_backends
from src.core.runlogs.scanner import scan_runlogs

from ..contracts.schemas import (
    BackendItem,
    BackendListResponse,
    BenchmarkItem,
    BenchmarkListResponse,
    ExperimentItem,
    ExperimentListResponse,
    TaskItem,
    TaskListResponse,
)


def list_experiments() -> ExperimentListResponse:
    """Return discovered experiments with basic run counts and timestamps."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for run in scan_runlogs(limit=None):
        grouped[str(run["experiment"])].append(run)

    items: list[ExperimentItem] = []
    for name, runs in sorted(grouped.items()):
        latest = max((run.get("timestamp") for run in runs), default=None)
        items.append(
            ExperimentItem(
                name=name,
                run_count=len(runs),
                latest_timestamp=latest,
            )
        )

    return ExperimentListResponse(experiments=items)


def list_tasks(experiment: str) -> TaskListResponse:
    """Return tasks for a selected experiment."""
    tasks: list[TaskItem] = []
    for run in scan_runlogs(limit=None):
        if run["experiment"] != experiment or run["csv_path"] is None:
            continue
        tasks.append(
            TaskItem(
                experiment=experiment,
                task=str(run["task"]),
                csv_path=str(run["csv_path"]),
                md_path=str(run["md_path"]),
                timestamp=run.get("timestamp"),
                benchmark=run.get("benchmark"),
                backends=list(run.get("backends") or []),
                duration=run.get("duration"),
                rows=run.get("rows"),
                description=run.get("description"),
            )
        )

    tasks.sort(key=lambda item: item.timestamp or 0, reverse=True)
    return TaskListResponse(experiment=experiment, tasks=tasks)


def list_benchmarks() -> BenchmarkListResponse:
    """Return discovered benchmark definitions."""
    benchmarks = [
        BenchmarkItem(name=name, path=str(path))
        for name, path in sorted(get_benchmark_names().items())
    ]
    return BenchmarkListResponse(benchmarks=benchmarks)


def list_backends() -> BackendListResponse:
    """Return discovered backend definitions with lightweight metadata."""
    backend_paths = get_backend_names()
    backend_configs = discover_backends()

    items: list[BackendItem] = []
    for name in sorted(backend_paths.keys()):
        config = backend_configs.get(name)
        option = config.backend_options[name] if config is not None else None
        items.append(
            BackendItem(
                name=name,
                path=str(backend_paths[name]),
                profiling=bool(option.profiling) if option is not None else False,
                composable=bool(option.composable) if option is not None else True,
                description=option.description if option is not None else None,
            )
        )

    return BackendListResponse(backends=items)
