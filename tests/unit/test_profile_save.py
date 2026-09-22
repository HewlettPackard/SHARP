# © Copyright 2025--2025 Hewlett Packard Enterprise Development LP
#!/usr/bin/env python3
"""Unit tests for profile settings save functionality."""

from src.core.runlogs.profile_settings import (
    build_profile_settings_payload,
    extract_profile_settings_from_md,
    update_markdown_profile_settings,
)


def test_build_profile_settings_payload_empty():
    """Empty settings return empty dict."""
    result = build_profile_settings_payload(
        filter_metric=None,
        filter_value=None,
        num_perf_groups=None,
        cutoff_values=None,
        influence_analyzer=None,
    )

    assert result == {}


def test_build_profile_settings_payload_all_fields():
    """All fields serialize correctly."""
    result = build_profile_settings_payload(
        filter_metric="timestamp",
        filter_value=[0, 600],
        num_perf_groups=3,
        cutoff_values=[0.12, 0.45],
        influence_analyzer="granger",
    )

    assert result["profiling.default_filter_metric"] == "timestamp"
    assert result["profiling.default_filter_value"] == [0, 600]
    assert result["profiling.default_num_perf_groups"] == 3
    assert result["profiling.default_cutoff_values"] == [0.12, 0.45]
    assert result["profiling.default_influence_analyzer"] == "granger"


def test_build_profile_settings_payload_partial():
    """Only non-None/non-empty fields are included."""
    result = build_profile_settings_payload(
        filter_metric="backend",
        filter_value=["local", "mpi"],
        num_perf_groups=None,
        cutoff_values=None,
        influence_analyzer="pcmci",
    )

    assert "profiling.default_filter_metric" in result
    assert "profiling.default_filter_value" in result
    assert "profiling.default_influence_analyzer" in result
    assert "profiling.default_num_perf_groups" not in result
    assert "profiling.default_cutoff_values" not in result


def test_build_profile_settings_payload_dedupes_cutoffs():
    """Duplicate cutoff values are sorted and deduplicated."""
    result = build_profile_settings_payload(
        filter_metric=None,
        filter_value=None,
        num_perf_groups=None,
        cutoff_values=[2.5, 1.2, 2.5, 0.8, 1.2],
        influence_analyzer=None,
    )

    assert result["profiling.default_cutoff_values"] == [0.8, 1.2, 2.5]


def test_update_markdown_creates_new_section(tmp_path):
    """Profile settings section is created if missing."""
    md_path = tmp_path / "test.md"
    md_path.write_text(
        """# Benchmark Results

Some content here.

## Analysis
Results of analysis.
"""
    )

    settings = {
        "profiling.default_filter_metric": "time",
        "profiling.default_num_perf_groups": 2,
    }
    success, _ = update_markdown_profile_settings(str(md_path), settings)

    assert success
    content = md_path.read_text()
    assert "## Profile settings" in content
    assert "profiling.default_filter_metric" in content
    assert "profiling.default_num_perf_groups" in content


def test_update_markdown_replaces_existing_section(tmp_path):
    """Existing profile settings section is replaced."""
    md_path = tmp_path / "test.md"
    md_path.write_text(
        """# Benchmark

## Profile settings

```json
{
    "profiling.default_filter_metric": "old_metric",
    "profiling.default_num_perf_groups": 1
}
```

## Analysis
More content
"""
    )

    new_settings = {
        "profiling.default_filter_metric": "new_metric",
        "profiling.default_num_perf_groups": 3,
    }
    success, _ = update_markdown_profile_settings(str(md_path), new_settings)

    assert success
    content = md_path.read_text()
    assert "new_metric" in content
    assert '"profiling.default_num_perf_groups": 3' in content
    assert "old_metric" not in content
    assert content.count("profiling.default_num_perf_groups") == 1
    assert "## Analysis" in content
    assert "More content" in content


def test_update_markdown_missing_file(tmp_path):
    """Missing file returns error."""
    md_path = tmp_path / "nonexistent.md"

    success, msg = update_markdown_profile_settings(str(md_path), {})

    assert not success
    assert "not found" in msg.lower()


def test_update_markdown_preserves_other_sections(tmp_path):
    """Existing sections outside profile settings are preserved."""
    md_path = tmp_path / "test.md"
    original_content = """# Benchmark Results

Here is the introduction.

## Performance Summary

Average: 100ms
Median: 95ms

## Analysis Details

Complex analysis goes here with special chars: !@#$%^&*()

## Alternatives Considered

Option A: very good
Option B: better still
"""
    md_path.write_text(original_content)

    settings = {"profiling.default_filter_metric": "time"}
    success, _ = update_markdown_profile_settings(str(md_path), settings)

    assert success
    content = md_path.read_text()
    assert "## Performance Summary" in content
    assert "Average: 100ms" in content
    assert "## Analysis Details" in content
    assert "Complex analysis" in content
    assert "## Alternatives Considered" in content
    assert "Option A: very good" in content


def test_save_roundtrip_preserves_cutoff_values(tmp_path):
    """Saved cutoff values survive markdown write/read round-trip."""
    md_path = tmp_path / "test.md"
    md_path.write_text(
        """# Benchmark Results

## Analysis
Results of analysis.
"""
    )

    settings = build_profile_settings_payload(
        filter_metric="latency",
        filter_value=[1.0, 9.0],
        num_perf_groups=4,
        cutoff_values=[1.5, 3.25, 7.75],
        influence_analyzer="granger",
    )

    success, _ = update_markdown_profile_settings(str(md_path), settings)

    assert success
    parsed = extract_profile_settings_from_md(md_path)
    assert parsed["profiling.default_num_perf_groups"] == 4
    assert parsed["profiling.default_cutoff_values"] == [1.5, 3.25, 7.75]


def test_build_profile_settings_payload_outcome_metric():
    """Outcome metric is serialized under the correct key."""
    result = build_profile_settings_payload(
        filter_metric=None,
        filter_value=None,
        num_perf_groups=None,
        cutoff_values=None,
        influence_analyzer=None,
        outcome_metric="allreduce_latency_us",
    )

    assert result == {"profiling.default_outcome_metric": "allreduce_latency_us"}


def test_build_profile_settings_payload_empty_outcome_metric_omitted():
    """Empty/None outcome metric is not included in the payload."""
    result = build_profile_settings_payload(
        filter_metric=None,
        filter_value=None,
        num_perf_groups=None,
        cutoff_values=None,
        influence_analyzer=None,
        outcome_metric=None,
    )

    assert "profiling.default_outcome_metric" not in result


def test_save_roundtrip_includes_outcome_metric(tmp_path):
    """Saved outcome metric survives markdown write/read round-trip."""
    md_path = tmp_path / "test.md"
    md_path.write_text("# Benchmark Results\n\n## Analysis\nResults.\n")

    settings = build_profile_settings_payload(
        filter_metric="timestamp",
        filter_value=[0, 100],
        num_perf_groups=3,
        cutoff_values=[1.0, 2.0],
        influence_analyzer=None,
        outcome_metric="max_allreduce_latency_us",
    )

    success, _ = update_markdown_profile_settings(str(md_path), settings)

    assert success
    parsed = extract_profile_settings_from_md(md_path)
    assert parsed["profiling.default_outcome_metric"] == "max_allreduce_latency_us"
    assert parsed["profiling.default_filter_metric"] == "timestamp"
    assert parsed["profiling.default_num_perf_groups"] == 3


# ─── Bug regression: excluded predictors ────────────────────────────────────


def test_build_profile_settings_payload_excluded_predictors():
    """Extra excluded predictors are serialized under the correct key."""
    result = build_profile_settings_payload(
        filter_metric=None,
        filter_value=None,
        num_perf_groups=None,
        cutoff_values=None,
        influence_analyzer=None,
        excluded_predictors=["cpu_clock", "cache_misses"],
    )

    assert result == {
        "profiling.default_predictor_exclusions": ["cpu_clock", "cache_misses"]
    }


def test_build_profile_settings_payload_empty_excluded_predictors_omitted():
    """Empty excluded_predictors list is not written to the payload."""
    result = build_profile_settings_payload(
        filter_metric=None,
        filter_value=None,
        num_perf_groups=None,
        cutoff_values=None,
        influence_analyzer=None,
        excluded_predictors=[],
    )

    assert "profiling.default_predictor_exclusions" not in result


def test_save_roundtrip_includes_excluded_predictors(tmp_path):
    """Saved excluded predictors survive markdown write/read round-trip."""
    md_path = tmp_path / "task.md"
    md_path.write_text("# Benchmark\n\n## Analysis\nResults.\n")

    settings = build_profile_settings_payload(
        filter_metric="task",
        filter_value=["A", "B"],
        num_perf_groups=3,
        cutoff_values=[1.0, 2.0],
        influence_analyzer="tree",
        excluded_predictors=["cpu_clock", "L1_dcache_load_misses"],
    )

    success, _ = update_markdown_profile_settings(str(md_path), settings)

    assert success
    parsed = extract_profile_settings_from_md(md_path)
    assert parsed["profiling.default_predictor_exclusions"] == [
        "cpu_clock",
        "L1_dcache_load_misses",
    ]


# ─── Bug regression: auto-detect sentinel ───────────────────────────────────


def test_build_profile_settings_payload_auto_detect_sentinel():
    """num_perf_groups=0 sentinel is written when auto-detect is active."""
    result = build_profile_settings_payload(
        filter_metric=None,
        filter_value=None,
        num_perf_groups=0,
        cutoff_values=None,
        influence_analyzer=None,
    )

    assert result == {"profiling.default_num_perf_groups": 0}


def test_save_roundtrip_auto_detect_sentinel(tmp_path):
    """The auto-detect sentinel (0) survives markdown write/read round-trip."""
    md_path = tmp_path / "task.md"
    md_path.write_text("# Benchmark\n\n## Analysis\nResults.\n")

    settings = build_profile_settings_payload(
        filter_metric=None,
        filter_value=None,
        num_perf_groups=0,
        cutoff_values=None,
        influence_analyzer=None,
    )

    success, _ = update_markdown_profile_settings(str(md_path), settings)

    assert success
    parsed = extract_profile_settings_from_md(md_path)
    assert parsed["profiling.default_num_perf_groups"] == 0


# ─── Bug regression: filter_value without filter_metric not saved ────────────


def test_build_profile_settings_payload_filter_value_without_metric_omitted():
    """filter_value must not be saved unless filter_metric is also present."""
    result = build_profile_settings_payload(
        filter_metric=None,
        filter_value=[100, 200],
        num_perf_groups=None,
        cutoff_values=None,
        influence_analyzer=None,
    )

    assert "profiling.default_filter_value" not in result
    assert "profiling.default_filter_metric" not in result