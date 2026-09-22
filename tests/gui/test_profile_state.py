# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Unit tests for ProfileState — no HTTP, no database, no filesystem."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from starlette.datastructures import QueryParams

from src.gui.models.profile_state import ProfileState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_request(params: dict) -> MagicMock:
    """Build a minimal mock Request with the given query params."""
    items: list[tuple[str, str]] = []
    for k, v in params.items():
        if isinstance(v, list):
            for item in v:
                items.append((k, str(item)))
        else:
            items.append((k, str(v)))
    mock = MagicMock()
    mock.query_params = QueryParams(items)
    return mock


def make_settings(**kwargs):
    """Return a minimal ProfileSettings-like object."""
    from types import SimpleNamespace
    defaults = {
        "default_filter_metric": None,
        "default_filter_value": None,
        "default_num_perf_groups": None,
        "default_influence_analyzer": None,
        "default_cutoff_values": [],
        "default_predictor_exclusions": [],
        "default_max_correlation": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# from_request — defaults
# ---------------------------------------------------------------------------


def test_empty_request_gives_defaults():
    s = ProfileState.from_request(make_request({}))
    assert s.experiment == ""
    assert s.task == ""
    assert s.csv_path == ""
    assert s.metric == ""
    assert s.lower_is_better is True
    assert s.num_groups == 2
    assert s.auto_detect is False
    assert s.cutoff_values == []
    assert s.filter_metric == ""
    assert s.analyzer == ""
    assert s.notice is None
    assert s.error is None


def test_explicit_string_fields():
    s = ProfileState.from_request(make_request({
        "experiment": "exp1",
        "task": "my_task",
        "csv_path": "/data/foo.csv",
        "metric": "latency",
        "analyzer": "tree",
        "filter_metric": "cpu",
        "filter_min": "0.5",
        "filter_max": "2.0",
    }))
    assert s.experiment == "exp1"
    assert s.task == "my_task"
    assert s.csv_path == "/data/foo.csv"
    assert s.metric == "latency"
    assert s.analyzer == "tree"
    assert s.filter_metric == "cpu"
    assert s.filter_min == "0.5"
    assert s.filter_max == "2.0"


def test_explicit_fields_are_tracked():
    s = ProfileState.from_request(make_request({
        "experiment": "e",
        "metric": "m",
        "num_groups": "3",
        "auto_detect": "1",
        "lower_is_better": "0",
    }))
    assert s.is_explicit("experiment")
    assert s.is_explicit("metric")
    assert s.is_explicit("num_groups")
    assert s.is_explicit("auto_detect")
    assert s.is_explicit("lower_is_better")
    assert not s.is_explicit("task")
    assert not s.is_explicit("csv_path")
    assert not s.is_explicit("analyzer")


def test_lower_is_better_false():
    s = ProfileState.from_request(make_request({"lower_is_better": "0"}))
    assert s.lower_is_better is False


def test_lower_is_better_default_true_when_absent():
    s = ProfileState.from_request(make_request({}))
    assert s.lower_is_better is True
    assert not s.is_explicit("lower_is_better")


def test_auto_detect_true():
    s = ProfileState.from_request(make_request({"auto_detect": "1"}))
    assert s.auto_detect is True


def test_auto_detect_false_explicit():
    s = ProfileState.from_request(make_request({"auto_detect": "0"}))
    assert s.auto_detect is False
    assert s.is_explicit("auto_detect")


def test_num_groups_clamped_low():
    s = ProfileState.from_request(make_request({"num_groups": "0"}))
    assert s.num_groups == 1


def test_num_groups_clamped_high():
    s = ProfileState.from_request(make_request({"num_groups": "99"}))
    assert s.num_groups == 10


def test_num_groups_invalid_defaults_to_2():
    s = ProfileState.from_request(make_request({"num_groups": "banana"}))
    assert s.num_groups == 2


def test_cutoff_value_singular():
    s = ProfileState.from_request(make_request({"cutoff_value": ["1.0", "2.5"]}))
    assert s.cutoff_values == [1.0, 2.5]
    assert s.is_explicit("cutoff_value")


def test_cutoff_values_plural_fallback():
    s = ProfileState.from_request(make_request({"cutoff_values": ["3.0", "6.0"]}))
    assert s.cutoff_values == [3.0, 6.0]
    assert s.is_explicit("cutoff_value")


def test_cutoff_invalid_values_skipped():
    s = ProfileState.from_request(make_request({"cutoff_value": ["1.0", "bad", "2.0"]}))
    assert s.cutoff_values == [1.0, 2.0]


def test_filter_values_list():
    s = ProfileState.from_request(make_request({"filter_values": ["a", "b", "c"]}))
    assert s.filter_values == ["a", "b", "c"]
    assert s.is_explicit("filter_values")


def test_notice_and_error():
    s = ProfileState.from_request(make_request({"notice": "Saved!", "error": "Oops"}))
    assert s.notice == "Saved!"
    assert s.error == "Oops"


def test_show_mitigation_modal():
    s = ProfileState.from_request(make_request({"show_mitigation_modal": "1"}))
    assert s.show_mitigation_modal is True


# ---------------------------------------------------------------------------
# _validate_cutoff_count
# ---------------------------------------------------------------------------


def test_mismatched_cutoff_count_cleared_when_num_groups_explicit():
    # 3 cutoffs but num_groups=2 (expects 1 cutoff) → cleared
    s = ProfileState.from_request(make_request({
        "num_groups": "2",
        "cutoff_value": ["1.0", "2.0", "3.0"],
    }))
    assert s.cutoff_values == []


def test_cutoff_count_not_cleared_when_num_groups_absent():
    # num_groups not in URL → mismatch allowed (preserve cutoffs)
    s = ProfileState.from_request(make_request({
        "cutoff_value": ["1.0", "2.0", "3.0"],
    }))
    assert s.cutoff_values == [1.0, 2.0, 3.0]


def test_matching_cutoff_count_preserved():
    # num_groups=3 → expects 2 cutoffs → OK
    s = ProfileState.from_request(make_request({
        "num_groups": "3",
        "cutoff_value": ["1.0", "2.0"],
    }))
    assert s.cutoff_values == [1.0, 2.0]


# ---------------------------------------------------------------------------
# apply_defaults
# ---------------------------------------------------------------------------


def test_apply_defaults_no_settings_no_change():
    s = ProfileState(metric="cpu")
    original_metric = s.metric
    s.apply_defaults(None)
    assert s.metric == original_metric
    assert s.filter_metric == ""


def test_apply_defaults_filter_metric_when_not_explicit():
    settings = make_settings(default_filter_metric="cpu_usage")
    s = ProfileState.from_request(make_request({"metric": "latency"}))
    s.apply_defaults(settings)
    assert s.filter_metric == "cpu_usage"


def test_apply_defaults_filter_metric_skipped_when_explicit():
    settings = make_settings(default_filter_metric="cpu_usage")
    s = ProfileState.from_request(make_request({"filter_metric": "mem"}))
    s.apply_defaults(settings)
    assert s.filter_metric == "mem"  # not overwritten


def test_apply_defaults_num_groups():
    settings = make_settings(default_num_perf_groups=4)
    s = ProfileState.from_request(make_request({}))
    s.apply_defaults(settings)
    assert s.num_groups == 4
    assert s.auto_detect is False


def test_apply_defaults_num_groups_zero_sets_auto_detect():
    settings = make_settings(default_num_perf_groups=0)
    s = ProfileState.from_request(make_request({}))
    s.apply_defaults(settings)
    assert s.auto_detect is True


def test_apply_defaults_num_groups_skipped_when_explicit():
    settings = make_settings(default_num_perf_groups=4)
    s = ProfileState.from_request(make_request({"num_groups": "3"}))
    s.apply_defaults(settings)
    assert s.num_groups == 3  # not overwritten


def test_apply_defaults_analyzer():
    settings = make_settings(default_influence_analyzer="shap")
    choices = {"shap": "SHAP", "tree": "Tree"}
    s = ProfileState.from_request(make_request({}))
    s.apply_defaults(settings, available_analyzers=choices)
    assert s.analyzer == "shap"


def test_apply_defaults_analyzer_skipped_when_not_in_choices():
    settings = make_settings(default_influence_analyzer="unknown_algo")
    choices = {"tree": "Tree"}
    s = ProfileState.from_request(make_request({}))
    s.apply_defaults(settings, available_analyzers=choices)
    assert s.analyzer == ""  # not applied


def test_apply_defaults_analyzer_skipped_when_explicit():
    settings = make_settings(default_influence_analyzer="shap")
    choices = {"shap": "SHAP", "tree": "Tree"}
    s = ProfileState.from_request(make_request({"analyzer": "tree"}))
    s.apply_defaults(settings, available_analyzers=choices)
    assert s.analyzer == "tree"  # not overwritten


def test_apply_defaults_cutoffs_restored():
    settings = make_settings(default_cutoff_values=[0.5, 1.5])
    s = ProfileState.from_request(make_request({}))
    s.apply_defaults(settings)
    assert s.cutoff_values == [0.5, 1.5]


def test_apply_defaults_cutoffs_skipped_when_explicit():
    settings = make_settings(default_cutoff_values=[0.5, 1.5])
    s = ProfileState.from_request(make_request({"cutoff_value": ["0.3"]}))
    s.apply_defaults(settings)
    assert s.cutoff_values == [0.3]  # not overwritten


def test_apply_defaults_cutoffs_skipped_when_num_groups_count_mismatch():
    # URL has num_groups=2 (expects 1 cutoff), but saved has 2 cutoffs → skip
    settings = make_settings(default_cutoff_values=[0.5, 1.5])
    s = ProfileState.from_request(make_request({"num_groups": "2"}))
    s.apply_defaults(settings)
    assert s.cutoff_values == []  # not restored — count mismatch


def test_apply_defaults_cutoffs_restored_when_count_matches():
    # URL has num_groups=3, saved has 2 cutoffs → 2 == 3-1 → OK
    settings = make_settings(default_cutoff_values=[0.5, 1.5])
    s = ProfileState.from_request(make_request({"num_groups": "3"}))
    s.apply_defaults(settings)
    assert s.cutoff_values == [0.5, 1.5]


# ---------------------------------------------------------------------------
# to_url
# ---------------------------------------------------------------------------


def test_to_url_basic():
    s = ProfileState(experiment="myexp", metric="lat")
    url = s.to_url()
    assert url.startswith("/ui/profile?")
    assert "experiment=myexp" in url
    assert "metric=lat" in url


def test_to_url_always_emits_lower_is_better():
    s = ProfileState(lower_is_better=True)
    assert "lower_is_better=1" in s.to_url()

    s2 = ProfileState(lower_is_better=False)
    assert "lower_is_better=0" in s2.to_url()


def test_to_url_always_emits_auto_detect():
    s = ProfileState(auto_detect=True)
    assert "auto_detect=1" in s.to_url()

    s2 = ProfileState(auto_detect=False)
    assert "auto_detect=0" in s2.to_url()


def test_to_url_always_emits_num_groups():
    s = ProfileState(num_groups=4)
    assert "num_groups=4" in s.to_url()


def test_to_url_multiple_cutoff_values():
    s = ProfileState(cutoff_values=[1.0, 2.5, 4.0])
    url = s.to_url()
    assert url.count("cutoff_value=") == 3
    assert "cutoff_value=1.0" in url
    assert "cutoff_value=2.5" in url
    assert "cutoff_value=4.0" in url


def test_to_url_filter_values_list():
    s = ProfileState(filter_values=["high", "low"])
    url = s.to_url()
    assert "filter_values=high" in url
    assert "filter_values=low" in url


def test_to_url_empty_strings_omitted():
    s = ProfileState(
        experiment="",
        task="",
        csv_path="",
        metric="",
        filter_metric="",
        analyzer="",
    )
    url = s.to_url()
    assert "experiment=" not in url
    assert "task=" not in url
    assert "csv_path=" not in url
    assert "metric=" not in url
    assert "filter_metric=" not in url
    assert "analyzer=" not in url


def test_to_url_excluded_state():
    s = ProfileState(excluded_state="abc-token-123")
    assert "excluded_state=abc-token-123" in s.to_url()


# ---------------------------------------------------------------------------
# from_dict round-trip
# ---------------------------------------------------------------------------


def test_from_dict_round_trip():
    original = ProfileState(
        experiment="e",
        task="t",
        csv_path="/foo/bar.csv",
        metric="cpu",
        lower_is_better=False,
        num_groups=3,
        auto_detect=True,
        cutoff_values=[0.5, 1.5],
        filter_metric="mem",
        filter_min="0.1",
        filter_max="0.9",
        filter_values=["a", "b"],
        analyzer="shap",
        excluded_state="token",
    )
    data = original.to_template_data()
    restored = ProfileState.from_dict(data)

    assert restored.experiment == original.experiment
    assert restored.task == original.task
    assert restored.csv_path == original.csv_path
    assert restored.metric == original.metric
    assert restored.lower_is_better == original.lower_is_better
    assert restored.num_groups == original.num_groups
    assert restored.auto_detect == original.auto_detect
    assert restored.cutoff_values == original.cutoff_values
    assert restored.filter_metric == original.filter_metric
    assert restored.filter_min == original.filter_min
    assert restored.filter_max == original.filter_max
    assert restored.filter_values == original.filter_values
    assert restored.analyzer == original.analyzer
    assert restored.excluded_state == original.excluded_state


def test_from_dict_to_url_is_consistent():
    data = {
        "experiment": "exp",
        "metric": "lat",
        "lower_is_better": False,
        "num_groups": 3,
        "auto_detect": False,
        "cutoff_values": [1.0, 2.0],
        "filter_values": [],
        "excluded_state": "",
    }
    url = ProfileState.from_dict(data).to_url()
    assert "lower_is_better=0" in url
    assert "num_groups=3" in url
    assert "cutoff_value=1.0" in url
    assert "cutoff_value=2.0" in url
