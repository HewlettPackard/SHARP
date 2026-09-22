# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Summary-page service for the SHARP GUI."""

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.core.config.settings import Settings
from src.core.runlogs.scanner import get_experiments
from src.core.runlogs.scanner import scan_runlogs


def _safe_duration(run: dict[str, Any]) -> float | None:
    d = run.get("duration")
    return float(d) if d is not None and d > 0 else None


def _runlogs_dir() -> Path:
    settings = Settings()
    return Path(settings.get("sharp.runlogs_dir", "runlogs"))


def get_runlogs_dir() -> Path:
    """Return configured runlogs directory path."""
    return _runlogs_dir()


def normalize_experiment_name(name: str) -> str:
    """Return a sanitized experiment name or raise ValueError."""
    normalized = name.strip()
    if not normalized:
        raise ValueError("Please enter an experiment name.")
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        raise ValueError("Experiment name cannot contain path separators or '..'.")
    return normalized


def ensure_experiment_dir(name: str) -> Path:
    """Create an experiment directory if needed and return its path."""
    experiment_name = normalize_experiment_name(name)
    experiment_dir = _runlogs_dir() / experiment_name
    experiment_dir.mkdir(parents=True, exist_ok=True)
    return experiment_dir


def load_summary_data() -> dict[str, Any]:
    """
    Return all data needed to render the summary page in one scan.

    Returns a dict with:
      all_runs   – full run list (for KPIs and activity chart)
      recent     – limited to gui.overview.recent_runs_count
      total      – total run count
      avg_time   – avg duration string across runs that have a duration
      activity   – list of {date_label, count} for the last 30 days
    """
    settings = Settings()
    limit = settings.get("gui.overview.recent_runs_count", 10)

    all_runs = scan_runlogs(limit=None)
    recent = all_runs[:limit]

    # KPI: avg time
    durations = [d for r in all_runs if (d := _safe_duration(r)) is not None]
    avg_time = f"{sum(durations) / len(durations):.2f}s" if durations else "N/A"

    # Activity chart – last 30 days from the most recent run timestamp
    timestamps = [r["timestamp"] for r in all_runs if r.get("timestamp")]
    if timestamps:
        max_date = max(ts.date() for ts in timestamps)
    else:
        max_date = datetime.today().date()
    start_date = max_date - timedelta(days=29)

    daily: dict[Any, int] = defaultdict(int)
    for r in all_runs:
        if r.get("timestamp"):
            d = r["timestamp"].date()
            if start_date <= d <= max_date:
                daily[d] += 1

    activity = []
    for i in range(30):
        date = start_date + timedelta(days=i)
        activity.append({"date": date, "label": date.strftime("%-m/%-d"), "count": daily.get(date, 0)})

    return {
        "all_runs": all_runs,
        "recent": recent,
        "total": len(all_runs),
        "avg_time": avg_time,
        "activity": activity,
        "experiments": list(get_experiments().keys()),
    }
