"""
Unit tests for TransferEntropyInfluenceAnalyzer.

Tests cover:
  - Core TE estimation (continuous data)
  - Regression: discrete (classification-label) outcome returns nonzero strength
  - Direction detection (FORWARD vs REVERSE)
  - Permutation test p-values are valid probabilities
  - Full analyzer pipeline on synthetic classification and regression data
  - Edge cases: too-short series, constant predictor, independent series

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
import pytest

from src.core.profile.analyzers.te import (
    TransferEntropyInfluenceAnalyzer,
    _jitter_discrete,
    _ksg_mi,
    _normalise_te,
    compute_transfer_entropy,
)
from src.core.profile.base import CausalDirection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_causal_pair(n: int, coupling: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (x, y) where x[t-1] drives y[t] with given coupling strength."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    y = np.empty(n)
    y[0] = rng.standard_normal()
    for t in range(1, n):
        y[t] = coupling * x[t - 1] + np.sqrt(1 - coupling ** 2) * rng.standard_normal()
    return x, y


def _make_independent_pair(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n), rng.standard_normal(n)


# ---------------------------------------------------------------------------
# Unit tests: _jitter_discrete
# ---------------------------------------------------------------------------

class TestJitterDiscrete:
    def test_continuous_unchanged(self):
        rng = np.random.default_rng(0)
        arr = rng.standard_normal(100)
        out = _jitter_discrete(arr, rng)
        # Many unique values → no jitter applied; array should be identical
        np.testing.assert_array_equal(out, arr)

    def test_binary_is_jittered(self):
        rng = np.random.default_rng(0)
        arr = np.array([0.0, 1.0, 0.0, 1.0, 0.0] * 20)
        out = _jitter_discrete(arr, rng)
        assert not np.array_equal(out, arr), "binary array should be jittered"
        assert np.allclose(out, arr, atol=1e-3), "jitter should be tiny"

    def test_constant_does_not_crash(self):
        rng = np.random.default_rng(0)
        arr = np.zeros(50)
        out = _jitter_discrete(arr, rng)
        assert out.shape == arr.shape
        assert not np.all(out == 0.0), "constant array should receive nonzero jitter"


# ---------------------------------------------------------------------------
# Unit tests: KSG sanity
# ---------------------------------------------------------------------------

class TestKSGMI:
    def test_independent_variables_near_zero(self):
        rng = np.random.default_rng(1)
        n = 500
        a = rng.standard_normal((n, 1))
        b = rng.standard_normal((n, 1))
        mi = _ksg_mi(a, b, k=5)
        assert mi < 0.15, f"MI of independent vars should be near 0, got {mi}"

    def test_identical_variables_positive(self):
        rng = np.random.default_rng(2)
        n = 300
        a = rng.standard_normal((n, 1))
        mi = _ksg_mi(a, a, k=5)
        assert mi > 0.5, f"MI(X; X) should be large, got {mi}"

    def test_independent_yz_mi_not_exploding(self):
        """KSG MI for two independent continuous variables should be near zero,
        not explode to implausible values (guards against the epsilon=0 bug)."""
        rng = np.random.default_rng(3)
        n = 300
        a = rng.standard_normal((n, 1))
        b = rng.standard_normal((n, 1))
        mi = _ksg_mi(a, b, k=5)
        # For independent variables MI should be near 0; allow generous slack
        # for finite-sample variance but reject the pre-fix explosion (~5.9 nats).
        assert mi < 1.0, (
            f"MI of independent vars should be near 0, got {mi:.3f}. "
            "Large values suggest the epsilon=0 degenerate-distance bug."
        )


# ---------------------------------------------------------------------------
# Unit tests: compute_transfer_entropy
# ---------------------------------------------------------------------------

class TestComputeTransferEntropy:
    def test_causal_direction_continuous(self):
        """TE(x→y) >> TE(y→x) for truly causal x→y."""
        x, y = _make_causal_pair(n=400, coupling=0.8, seed=10)
        te_fwd = compute_transfer_entropy(x, y)
        te_rev = compute_transfer_entropy(y, x)
        assert te_fwd > te_rev, (
            f"Forward TE ({te_fwd:.4f}) should exceed reverse ({te_rev:.4f})"
        )
        assert te_fwd > 0.05, f"Forward TE should be detectably positive, got {te_fwd:.4f}"

    def test_independent_near_zero(self):
        x, y = _make_independent_pair(n=500, seed=20)
        te = compute_transfer_entropy(x, y)
        assert te < 0.15, f"TE for independent series should be near 0, got {te:.4f}"

    def test_too_short_returns_zero(self):
        x = np.arange(5, dtype=float)
        y = np.arange(5, dtype=float)
        assert compute_transfer_entropy(x, y) == 0.0

    def test_output_nonnegative(self):
        rng = np.random.default_rng(30)
        x = rng.standard_normal(200)
        y = rng.standard_normal(200)
        assert compute_transfer_entropy(x, y) >= 0.0


# ---------------------------------------------------------------------------
# Regression test: discrete outcome (the s=0.000 bug)
# ---------------------------------------------------------------------------

class TestDiscreteOutcomeBug:
    """Regression tests for strict TE eligibility policy.

    TE is intentionally disabled in classification mode. These tests ensure we
    return no factors instead of attempting KSG on discrete labels.
    """

    def test_continuous_metric_classification_mode_skipped(self):
        """Classification mode should skip TE entirely under strict policy."""
        rng = np.random.default_rng(42)
        n = 300
        x = rng.standard_normal(n)
        y_cont = np.concatenate([[0.0], 0.8 * x[:-1]]) + 0.2 * rng.standard_normal(n)
        labels = (y_cont > np.median(y_cont)).astype(int)

        # Use "metric" (not "__perf_label__") so the continuous column is
        # preserved after _resolve_outcome adds the synthetic labels column.
        data = pl.DataFrame({"metric": y_cont, "predictor": x})

        analyzer = TransferEntropyInfluenceAnalyzer(seed=42)
        factors = analyzer.analyze(
            data, labels,
            outcome_col="metric",
            outcome_mode="classification",
            permutations=0,
        )

        assert factors == []

    def test_analyzer_binary_labels_nonzero(self):
        """Binary-label classification mode should skip TE entirely."""
        rng = np.random.default_rng(99)
        n = 300
        x = rng.standard_normal(n)
        y_cont = np.concatenate([[0.0], 0.8 * x[:-1]]) + 0.2 * rng.standard_normal(n)
        labels = (y_cont > np.median(y_cont)).astype(int)  # binary: 0 or 1

        data = pl.DataFrame({
            "metric": y_cont,       # continuous metric column
            "predictor": x,
            "noise": rng.standard_normal(n),
        })

        analyzer = TransferEntropyInfluenceAnalyzer(seed=42)
        factors = analyzer.analyze(
            data,
            labels,
            outcome_col="metric",
            outcome_mode="classification",
            permutations=0,
        )

        assert factors == []

    def test_tertile_labels_nonzero(self):
        """Tertile-label classification mode should skip TE entirely."""
        rng = np.random.default_rng(77)
        n = 300
        x = rng.standard_normal(n)
        y_cont = np.concatenate([[0.0], 0.7 * x[:-1]]) + 0.3 * rng.standard_normal(n)
        thirds = np.percentile(y_cont, [33, 67])
        labels = np.digitize(y_cont, thirds).astype(int)  # 0, 1, or 2

        data = pl.DataFrame({"metric": y_cont, "predictor": x})

        analyzer = TransferEntropyInfluenceAnalyzer(seed=0)
        factors = analyzer.analyze(
            data,
            labels,
            outcome_col="metric",
            outcome_mode="classification",
            permutations=0,
        )

        assert factors == []


# ---------------------------------------------------------------------------
# Analyzer integration tests
# ---------------------------------------------------------------------------

class TestTransferEntropyAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return TransferEntropyInfluenceAnalyzer(seed=42)

    def test_empty_data_returns_empty(self, analyzer):
        empty = pl.DataFrame({"a": [], "b": []})
        result = analyzer.analyze(empty, np.array([]))
        assert result == []

    def test_regression_mode_ranks_causal_first(self, analyzer):
        """In regression mode the causal predictor should rank above independent noise."""
        rng = np.random.default_rng(5)
        n = 300
        x_cause = rng.standard_normal(n)
        x_noise = rng.standard_normal(n)
        y = np.concatenate([[0.0], 0.8 * x_cause[:-1]]) + 0.2 * rng.standard_normal(n)

        data = pl.DataFrame({"metric": y, "cause": x_cause, "noise": x_noise})
        labels = np.zeros(n, dtype=int)  # dummy labels for regression mode

        factors = analyzer.analyze(
            data,
            labels,
            outcome_col="metric",
            outcome_mode="regression",
            permutations=0,
        )

        names = [f.name for f in factors]
        assert "cause" in names
        cause_idx = names.index("cause")
        if "noise" in names:
            noise_idx = names.index("noise")
            assert cause_idx < noise_idx, (
                f"Causal predictor (rank {cause_idx+1}) should rank above noise (rank {noise_idx+1})"
            )

    def test_factors_have_required_fields(self, analyzer):
        rng = np.random.default_rng(6)
        n = 200
        x = rng.standard_normal(n)
        y = np.concatenate([[0.0], 0.6 * x[:-1]]) + 0.4 * rng.standard_normal(n)
        data = pl.DataFrame({"metric": y, "predictor": x})
        labels = np.zeros(n, dtype=int)

        factors = analyzer.analyze(
            data, labels, outcome_col="metric",
            outcome_mode="regression", permutations=0,
        )
        assert len(factors) > 0
        f = factors[0]
        assert f.rank == 1
        assert f.method == "te"
        assert 0.0 <= f.strength <= 1.0
        assert f.direction is not None
        assert f.metadata is not None
        assert "te_forward_nats" in f.metadata

    def test_direction_forward_detected(self):
        """FORWARD causality should be detected for a clearly causal predictor."""
        rng = np.random.default_rng(7)
        n = 500
        x, y = _make_causal_pair(n=n, coupling=0.9, seed=7)
        y_cont = y
        data = pl.DataFrame({"metric": y_cont, "predictor": x})
        labels = np.zeros(n, dtype=int)

        analyzer = TransferEntropyInfluenceAnalyzer(seed=7)
        factors = analyzer.analyze(
            data, labels, outcome_col="metric",
            outcome_mode="regression", permutations=50,
        )
        assert len(factors) > 0
        f = next(f for f in factors if f.name == "predictor")
        assert f.direction in (CausalDirection.FORWARD, CausalDirection.BIDIRECTIONAL), (
            f"Expected FORWARD direction, got {f.direction}"
        )

    def test_p_value_in_range(self, analyzer):
        rng = np.random.default_rng(8)
        n = 200
        x, y = _make_causal_pair(n, coupling=0.7, seed=8)
        data = pl.DataFrame({"metric": y, "predictor": x})
        labels = np.zeros(n, dtype=int)

        factors = analyzer.analyze(
            data, labels, outcome_col="metric",
            outcome_mode="regression", permutations=20,
        )
        assert len(factors) > 0
        f = factors[0]
        assert f.p_value is not None
        assert 0.0 <= f.p_value <= 1.0

    def test_ranks_are_contiguous(self, analyzer):
        rng = np.random.default_rng(9)
        n = 200
        data = pl.DataFrame({
            "metric": rng.standard_normal(n),
            "a": rng.standard_normal(n),
            "b": rng.standard_normal(n),
            "c": rng.standard_normal(n),
        })
        labels = np.zeros(n, dtype=int)
        factors = analyzer.analyze(
            data, labels, outcome_col="metric",
            outcome_mode="regression", permutations=0,
        )
        ranks = [f.rank for f in factors]
        assert ranks == list(range(1, len(factors) + 1))

    def test_normalise_te_bounds(self):
        assert _normalise_te(0.0) == 0.0
        assert 0.0 < _normalise_te(1.0) < 1.0
        assert 0.0 < _normalise_te(10.0) < 1.0
        assert _normalise_te(0.0) < _normalise_te(1.0) < _normalise_te(10.0)
