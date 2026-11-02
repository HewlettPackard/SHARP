"""
Tests for SHARP's single-source version metadata and reporting.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest

from src import __version__
from src.cli.sharp import print_version
from src.core.runlogs import RunLogger


def test_build_uses_package_version() -> None:
    project_root = Path(__file__).resolve().parents[2]
    with (project_root / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)

    assert "version" not in config["project"]
    assert "version" in config["project"]["dynamic"]
    assert config["tool"]["hatch"]["version"]["path"] == "src/__init__.py"
    assert {"file": "src/__init__.py"} in config["tool"]["uv"]["cache-keys"]
    assert {"file": "pyproject.toml"} in config["tool"]["uv"]["cache-keys"]


def test_installed_version_matches_package() -> None:
    assert version("sharp") == __version__


def test_cli_reports_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    print_version()

    assert capsys.readouterr().out == f"SHARP version {__version__}\n"


def test_runlog_reports_package_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    logger = RunLogger(str(tmp_path), "version_test", "test_task", {})

    assert f"\nSHARP version: {__version__}\n" in logger._preamble
