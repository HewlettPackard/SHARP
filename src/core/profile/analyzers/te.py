"""
Transfer entropy influence analyzer.

Quantifies directed information flow from each predictor to the outcome using
Transfer Entropy (TE), which measures how much the past of a predictor reduces
uncertainty about the future of the outcome beyond what the outcome's own
history already explains.

Mathematical definition
-----------------------
TE(X → Y) = I(Y_{t+1}; X_t^{(k)} | Y_t^{(l)})

where X_t^{(k)} = (X_t, X_{t-τ}, …, X_{t-(k-1)τ}) is the delay-embedded
source vector, Y_t^{(l)} is the target history, and I(·; · | ·) is
Conditional Mutual Information (CMI).  TE is zero for causally unrelated
series and positive when the source contains information about the target's
future beyond what the target already knows about itself.

CMI is estimated via the k-nearest-neighbor (KSG) estimator
(Kraskov et al., 2004) using the chain rule
I(Y; X | Z) = I(Y; X, Z) − I(Y; Z).  This nonparametric approach avoids
histogram binning, is consistent for continuous distributions, and captures
both linear and nonlinear dependencies.

Under joint Gaussianity TE equals half the Granger causality log-ratio
(Barnett et al., 2009); for non-Gaussian or nonlinear processes TE detects
dependencies that Granger causality misses.

Significance is assessed via a permutation test: the source series is
randomly shuffled (breaking cross-dependence while preserving marginals)
and TE is recomputed on each permutation.  The resulting null distribution
yields both a p-value and a percentile confidence interval of the null.

TE is reported as a normalised strength score s = 1 − exp(−TE), which maps
[0, ∞) to [0, 1) monotonically and equals zero when TE = 0.  Direction is
determined by comparing TE(predictor → outcome) with TE(outcome → predictor),
with significance tests applied to both.

References
----------
Schreiber, T. (2000). Measuring information transfer.
    Physical Review Letters, 85(2), 461–464.
    https://doi.org/10.1103/PhysRevLett.85.461

Kraskov, A., Stögbauer, H., & Grassberger, P. (2004). Estimating mutual
    information. Physical Review E, 69(6), 066138.
    https://doi.org/10.1103/PhysRevE.69.066138

Barnett, L., Barrett, A. B., & Seth, A. K. (2009). Granger causality and
    transfer entropy are equivalent for Gaussian variables.
    Physical Review Letters, 103(23), 238701.
    https://doi.org/10.1103/PhysRevLett.103.238701

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import warnings
from typing import Any

import numpy as np
import polars as pl
from scipy.spatial import cKDTree
from scipy.special import digamma

from src.core.profile.base import (
    LABEL_OUTCOME_COL as _LABEL_OUTCOME_COL,
    CausalDirection,
    InfluenceAnalyzer,
    InfluenceFactor,
)
from src.core.config.settings import Settings
from src.core.profile import predictor_selection


# ---------------------------------------------------------------------------
# Core estimators (pure numpy/scipy)
# ---------------------------------------------------------------------------

def _as_col(arr: np.ndarray) -> np.ndarray:
    """Return *arr* as a 2-D (N, d) float64 column matrix."""
    arr = np.asarray(arr, dtype=np.float64)
    return arr.reshape(-1, 1) if arr.ndim == 1 else arr


def _ksg_mi(a: np.ndarray, b: np.ndarray, k: int) -> float:
    """Estimate I(A; B) via the KSG Algorithm 1 (Kraskov et al., 2004).

    Uses the Chebyshev (L∞) norm consistently in both joint and marginal
    spaces, as specified by Algorithm 1 of the original paper.

    I(X; Y) = ψ(k) − ⟨ψ(nₓ+1) + ψ(n_y+1)⟩ + ψ(N)

    Parameters
    ----------
    a, b : ndarray, shape (N, da) and (N, db)
        Jointly observed samples with the same number of rows N.
    k : int
        Number of nearest neighbours.

    Returns
    -------
    float
        MI estimate in nats.
    """
    N = a.shape[0]
    joint = np.hstack([a, b])

    # k-th nearest-neighbour distance in joint space (L∞ norm).
    # query(k+1) includes the query point itself at index 0 (distance 0).
    joint_tree = cKDTree(joint)
    dists, _ = joint_tree.query(joint, k=k + 1, p=np.inf)
    eps = dists[:, k]  # L∞ distance to the k-th neighbour (self excluded)

    # Count points strictly within eps in each marginal space.
    # return_length=True (scipy ≥ 1.7) avoids a Python loop over lists.
    a_tree = cKDTree(a)
    b_tree = cKDTree(b)
    na = a_tree.query_ball_point(a, eps - 1e-15, p=np.inf, return_length=True) - 1
    nb = b_tree.query_ball_point(b, eps - 1e-15, p=np.inf, return_length=True) - 1

    # Clamp to 1 to avoid ψ(0) = −∞ from finite-sample boundary effects.
    na = np.maximum(na.astype(float), 1.0)
    nb = np.maximum(nb.astype(float), 1.0)

    return float(digamma(k) - np.mean(digamma(na + 1.0) + digamma(nb + 1.0)) + digamma(N))


def _ksg_cmi(x: np.ndarray, y: np.ndarray, z: np.ndarray, k: int) -> float:
    """Estimate I(X; Y | Z) = I(X; Y, Z) − I(X; Z) via the chain rule.

    All inputs must be (N, d) float arrays with the same N.
    The result is clamped to 0 to suppress negative finite-sample artefacts.
    """
    yz = np.hstack([y, z])
    return max(0.0, _ksg_mi(x, yz, k) - _ksg_mi(x, z, k))


def _build_te_vectors(
    x: np.ndarray,
    y: np.ndarray,
    k: int,
    l: int,
    tau: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Build the three embedding matrices required to compute TE(X → Y).

    Returns
    -------
    (y_future, x_past, y_past) as (n_pts, d) float64 arrays,
    or None when the series is too short for the given parameters.

    y_future : Y_{t+1}                              shape (n_pts, 1)
    x_past   : (X_t, X_{t-τ}, …, X_{t-(k-1)τ})    shape (n_pts, k)
    y_past   : (Y_t, Y_{t-τ}, …, Y_{t-(l-1)τ})    shape (n_pts, l)
    """
    N = min(len(x), len(y))
    max_offset = max(k, l) * tau
    n_pts = N - max_offset - 1
    if n_pts < 2:
        return None

    y_future = y[max_offset + 1: max_offset + 1 + n_pts].reshape(-1, 1)
    x_past = np.column_stack([
        x[max_offset - i * tau: max_offset - i * tau + n_pts]
        for i in range(k)
    ])
    y_past = np.column_stack([
        y[max_offset - i * tau: max_offset - i * tau + n_pts]
        for i in range(l)
    ])
    return y_future, x_past, y_past


def compute_transfer_entropy(
    x: np.ndarray,
    y: np.ndarray,
    k: int = 1,
    l: int = 1,
    tau: int = 1,
    k_neighbors: int = 5,
) -> float:
    """Estimate TE(X → Y) = I(Y_{t+1}; X_t^{(k)} | Y_t^{(l)}).

    Parameters
    ----------
    x, y : ndarray, shape (N,)
        Source and target time series of equal length with no NaN values.
    k : int
        Source embedding dimension (how many past lags of X to use).
    l : int
        Target embedding dimension (how many past lags of Y to condition on).
    tau : int
        Embedding lag in samples.
    k_neighbors : int
        Number of nearest neighbours for the KSG estimator.

    Returns
    -------
    float
        Transfer entropy in nats (≥ 0), or 0.0 when estimation is not
        possible (series too short or numerical failure).
    """
    vecs = _build_te_vectors(x, y, k, l, tau)
    if vecs is None:
        return 0.0
    y_future, x_past, y_past = vecs
    if len(y_future) <= k_neighbors + 1:
        return 0.0
    try:
        return _ksg_cmi(y_future, x_past, y_past, k=k_neighbors)
    except Exception as exc:
        warnings.warn(f"Transfer entropy estimation failed: {exc}", UserWarning)
        return 0.0


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _normalise_te(te: float) -> float:
    """Map TE ∈ [0, ∞) to a strength score in [0, 1) via s = 1 − e^{−te}."""
    return float(1.0 - np.exp(-max(0.0, te)))


# ---------------------------------------------------------------------------
# Influence analyzer
# ---------------------------------------------------------------------------

#: Minimum number of valid (non-NaN) paired samples before skipping a predictor.
_MIN_SAMPLES: int = 30

#: Multiplier for the lag-1 correlation threshold used in temporal-dependence
#: checks: threshold = multiplier / sqrt(n-1).
#:
#: Set conservatively high to avoid false positives from random cross-lag
#: correlations in independent benchmark runs (where many predictors can make
#: some |corr| values look significant by chance).
_PRESCREEN_SIGMA: float = 3.5


def _lag1_autocorr(y: np.ndarray) -> float:
    """Return lag-1 autocorrelation of *y*, or 0.0 if undefined."""
    if len(y) < 3:
        return 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = np.corrcoef(y[:-1], y[1:])[0, 1]
    return float(r) if np.isfinite(r) else 0.0


def _lag1_crosscorr(x: np.ndarray, y: np.ndarray) -> float:
    """Return corr(x[t], y[t+1]) or 0.0 if undefined."""
    if len(x) < 3 or len(y) < 3:
        return 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = np.corrcoef(x[:-1], y[1:])[0, 1]
    return float(r) if np.isfinite(r) else 0.0


def _delay_embed_1d(series: np.ndarray, dim: int, tau: int) -> np.ndarray | None:
    """Return delay-embedded matrix with columns [x_t, x_{t-τ}, ...]."""
    if dim < 1 or tau < 1:
        return None
    n = len(series) - (dim - 1) * tau
    if n < 3:
        return None
    cols = [
        series[(dim - 1 - j) * tau: (dim - 1 - j) * tau + n]
        for j in range(dim)
    ]
    return np.column_stack(cols)


def _one_step_regression_design(
    series: np.ndarray,
    dim: int,
    tau: int,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Build (X, y_next) for one-step prediction from delay vectors."""
    if dim < 1 or tau < 1:
        return None
    n = len(series) - (dim - 1) * tau - 1
    if n < max(20, dim + 2):
        return None
    cols = [
        series[(dim - 1 - j) * tau: (dim - 1 - j) * tau + n]
        for j in range(dim)
    ]
    X = np.column_stack(cols)
    y_next = series[(dim - 1) * tau + 1: (dim - 1) * tau + 1 + n]
    return X, y_next


def _bic_for_tau(series: np.ndarray, tau: int, dim_for_bic: int) -> float:
    """Compute linear one-step predictive BIC for a candidate tau."""
    design = _one_step_regression_design(series, dim=dim_for_bic, tau=tau)
    if design is None:
        return float("inf")
    X, y_next = design
    n = len(y_next)

    X_aug = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(X_aug, y_next, rcond=None)
    resid = y_next - X_aug @ beta
    rss = float(np.sum(resid * resid))
    rss = max(rss, 1e-12)

    # BIC for Gaussian residual model up to additive constants.
    k_params = X_aug.shape[1]
    return float(n * np.log(rss / n) + k_params * np.log(n))


def _fnn_rate(series: np.ndarray, dim: int, tau: int, rtol: float, atol: float) -> float:
    """Estimate false-nearest-neighbour rate for embedding dimension *dim*."""
    emb_ep1 = _delay_embed_1d(series, dim=dim + 1, tau=tau)
    if emb_ep1 is None:
        return 1.0

    emb_e = emb_ep1[:, :dim]
    extra = emb_ep1[:, dim]
    n = emb_e.shape[0]
    if n < 5:
        return 1.0

    tree = cKDTree(emb_e)
    dists, inds = tree.query(emb_e, k=2, p=2)
    nn_d = dists[:, 1]
    nn_i = inds[:, 1]

    eps = 1e-12
    delta_extra = np.abs(extra - extra[nn_i])
    cond1 = (delta_extra / (nn_d + eps)) > rtol

    # Kennel's second criterion: growth relative to signal scale.
    signal_scale = float(np.std(series))
    if signal_scale <= 0:
        signal_scale = 1e-12
    dist_ep1 = np.linalg.norm(emb_ep1 - emb_ep1[nn_i], axis=1)
    cond2 = (dist_ep1 / signal_scale) > atol

    return float(np.mean(cond1 | cond2))


class TransferEntropyInfluenceAnalyzer(InfluenceAnalyzer):
    """Directional information-flow analyzer based on Transfer Entropy.

    Evaluates TE(predictor → outcome) for each predictor and classifies
    causal direction by comparing forward and reverse TE estimates with
    permutation-test significance levels (Schreiber, 2000).

    Parameters
    ----------
    seed : int or None
        Seed for the permutation-test RNG.  Set for reproducible p-values.
    k_neighbors : int
        KSG estimator neighbourhood size.  The standard recommendation is 5
        (Kraskov et al., 2004); smaller values increase variance.
    """

    def __init__(self, seed: int | None = None, k_neighbors: int = 5) -> None:
        self._rng = np.random.default_rng(seed)
        self._k_neighbors = k_neighbors

    @property
    def name(self) -> str:
        return "te"

    @property
    def label(self) -> str:
        return "Transfer Entropy"

    @property
    def description(self) -> str:
        return (
            "Measures directed information flow via Transfer Entropy (Schreiber, 2000), "
            "using a nonparametric KSG estimator. Detects both linear and nonlinear "
            "causal dependencies. Requires time-ordered data; ≥100 samples recommended."
        )

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "lag_detection": False,
            "direction": True,
            "uncertainty": True,
            "falsification": False,
        }

    def _auto_select_embedding(
        self,
        outcome: np.ndarray,
        settings_obj: Any,
    ) -> tuple[int, int, dict[str, float | int]]:
        """Select embedding parameters (dimension, tau) via BIC + FNN.

        BIC chooses tau by one-step predictive fit; FNN chooses minimum
        dimension where false-neighbour rate falls below threshold.
        """
        y = outcome[np.isfinite(outcome)]
        if len(y) < _MIN_SAMPLES:
            return 1, 1, {"auto_tau": 1, "auto_dim": 1}

        max_tau = int(self._get_setting(settings_obj, "profiling.te.auto_embed_max_tau", 5))
        max_dim = int(self._get_setting(settings_obj, "profiling.te.auto_embed_max_dim", 3))
        dim_for_bic = int(self._get_setting(settings_obj, "profiling.te.auto_embed_bic_dim", 3))
        fnn_threshold = float(self._get_setting(settings_obj, "profiling.te.auto_embed_fnn_threshold", 0.20))
        fnn_rtol = float(self._get_setting(settings_obj, "profiling.te.auto_embed_fnn_rtol", 10.0))
        fnn_atol = float(self._get_setting(settings_obj, "profiling.te.auto_embed_fnn_atol", 2.0))

        max_tau = max(1, min(max_tau, max(1, len(y) // 5)))
        max_dim = max(1, min(max_dim, 8))
        dim_for_bic = max(1, min(dim_for_bic, max_dim))

        bic_scores: list[tuple[int, float]] = []
        for tau_candidate in range(1, max_tau + 1):
            bic = _bic_for_tau(y, tau=tau_candidate, dim_for_bic=dim_for_bic)
            if np.isfinite(bic):
                bic_scores.append((tau_candidate, bic))

        if bic_scores:
            tau = min(bic_scores, key=lambda t: t[1])[0]
        else:
            tau = 1

        fnn_rates: list[tuple[int, float]] = []
        for dim_candidate in range(1, max_dim + 1):
            rate = _fnn_rate(y, dim=dim_candidate, tau=tau, rtol=fnn_rtol, atol=fnn_atol)
            fnn_rates.append((dim_candidate, rate))

        dim = 1
        for dim_candidate, rate in fnn_rates:
            if rate <= fnn_threshold:
                dim = dim_candidate
                break
        else:
            dim = min(fnn_rates, key=lambda t: t[1])[0] if fnn_rates else 1

        diagnostics: dict[str, float | int] = {
            "auto_tau": int(tau),
            "auto_dim": int(dim),
            "auto_fnn_rate": float(dict(fnn_rates).get(dim, 1.0)),
        }
        return dim, tau, diagnostics

    def _resolve_te_outcome(
        self,
        data: pl.DataFrame,
        original_outcome_col: str | None,
        outcome_mode: str,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Validate TE eligibility and return (outcome, finite_outcome)."""
        if outcome_mode != "regression":
            warnings.warn(
                "Transfer Entropy skipped: TE is enabled only for regression "
                "with a continuous outcome. Classification mode is unsupported.",
                UserWarning,
            )
            return None

        if (
            not original_outcome_col
            or original_outcome_col == _LABEL_OUTCOME_COL
            or original_outcome_col not in data.columns
        ):
            warnings.warn(
                "Transfer Entropy skipped: no continuous outcome column was provided.",
                UserWarning,
            )
            return None

        outcome_dtype = data[original_outcome_col].dtype
        if outcome_dtype in (pl.Utf8, pl.Categorical, pl.Boolean):
            warnings.warn(
                "Transfer Entropy skipped: outcome must be continuous numeric "
                f"(got {outcome_dtype}).",
                UserWarning,
            )
            return None

        te_outcome = data[original_outcome_col].to_numpy().astype(float)
        te_outcome_valid = te_outcome[np.isfinite(te_outcome)]
        if len(np.unique(te_outcome_valid)) < 10:
            warnings.warn(
                "Transfer Entropy skipped: outcome appears discrete/low-cardinality; "
                "a continuous outcome is required.",
                UserWarning,
            )
            return None
        return te_outcome, te_outcome_valid

    def _resolve_analysis_params(
        self,
        settings_obj: Any,
        te_outcome_valid: np.ndarray,
        max_predictors: int | None,
        max_correlation: float | None,
    ) -> tuple[int, float, int, int, int, float, int, dict[str, float | int]]:
        """Resolve predictor limits and TE hyperparameters."""
        if max_predictors is None:
            max_predictors = int(self._get_setting(settings_obj, "profiling.max_predictors", 100))
        if max_correlation is None:
            max_correlation = float(self._get_setting(settings_obj, "profiling.max_correlation", 0.99))

        auto_meta: dict[str, float | int] = {}
        auto_embed = bool(self._get_setting(settings_obj, "profiling.te.auto_embed", True))
        if auto_embed:
            try:
                auto_dim, auto_tau, auto_meta = self._auto_select_embedding(te_outcome_valid, settings_obj)
                embed_k = auto_dim
                embed_l = auto_dim
                tau = auto_tau
            except Exception as exc:
                warnings.warn(
                    f"Transfer Entropy auto-embedding failed, using defaults: {exc}",
                    UserWarning,
                )
                embed_k = int(self._get_setting(settings_obj, "profiling.te.embed_k", 1))
                embed_l = int(self._get_setting(settings_obj, "profiling.te.embed_l", 1))
                tau = int(self._get_setting(settings_obj, "profiling.te.tau", 1))
        else:
            embed_k = int(self._get_setting(settings_obj, "profiling.te.embed_k", 1))
            embed_l = int(self._get_setting(settings_obj, "profiling.te.embed_l", 1))
            tau = int(self._get_setting(settings_obj, "profiling.te.tau", 1))

        significance_level = float(
            self._get_setting(settings_obj, "profiling.te.significance_level", 0.05)
        )
        permutations = int(self._get_setting(settings_obj, "profiling.te.permutations", 50))

        return (
            max_predictors,
            max_correlation,
            embed_k,
            embed_l,
            tau,
            significance_level,
            permutations,
            auto_meta,
        )

    def _passes_temporal_dependence_gate(
        self,
        data: pl.DataFrame,
        predictors: list[str],
        te_outcome: np.ndarray,
        te_outcome_valid: np.ndarray,
    ) -> bool:
        """Return True when lag structure is strong enough for TE."""
        n_valid = len(te_outcome_valid)
        if n_valid <= 2:
            return True

        threshold = _PRESCREEN_SIGMA / np.sqrt(n_valid - 1)
        y_auto = abs(_lag1_autocorr(te_outcome_valid))
        max_cross = 0.0
        for predictor in predictors:
            predictor_vals = data[predictor].to_numpy().astype(float)
            valid = ~(np.isnan(predictor_vals) | np.isnan(te_outcome))
            if int(np.sum(valid)) < 3:
                continue
            x = predictor_vals[valid]
            y = te_outcome[valid]
            max_cross = max(max_cross, abs(_lag1_crosscorr(x, y)))

        if y_auto < threshold and max_cross < threshold:
            warnings.warn(
                "Transfer Entropy skipped: data appears temporally independent "
                "(i.i.d.-like), so directional TE is not reliable.",
                UserWarning,
            )
            return False
        return True

    def _analyze_predictors(
        self,
        data: pl.DataFrame,
        predictors: list[str],
        te_outcome: np.ndarray,
        progress_callback: Any | None,
        embed_k: int,
        embed_l: int,
        tau: int,
        significance_level: float,
        permutations: int,
        median_dt: float | None,
        auto_meta: dict[str, float | int],
    ) -> list[InfluenceFactor]:
        """Run TE analysis for each predictor and return ranked factors."""
        factors: list[InfluenceFactor] = []
        total = len(predictors)

        for idx, predictor in enumerate(predictors, start=1):
            if progress_callback:
                progress_callback(idx, total, predictor)

            predictor_vals = data[predictor].to_numpy().astype(float)
            valid = ~(np.isnan(predictor_vals) | np.isnan(te_outcome))
            x = predictor_vals[valid]
            y = te_outcome[valid]
            if len(x) < _MIN_SAMPLES:
                continue

            factor = self._analyze_pair(
                predictor,
                x,
                y,
                embed_k=embed_k,
                embed_l=embed_l,
                tau=tau,
                significance_level=significance_level,
                permutations=permutations,
                median_dt=median_dt,
                auto_meta=auto_meta,
            )
            if factor is not None:
                factors.append(factor)

        factors.sort(key=lambda f: f.strength, reverse=True)
        return [
            InfluenceFactor(
                name=f.name,
                strength=f.strength,
                rank=i + 1,
                method=f.method,
                direction=f.direction,
                p_value=f.p_value,
                lag=f.lag,
                lag_rows=f.lag_rows,
                confidence_interval=f.confidence_interval,
                falsification_plan=f.falsification_plan,
                metadata=f.metadata,
            )
            for i, f in enumerate(factors)
        ]

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        data: pl.DataFrame,
        labels: np.ndarray,
        outcome_col: str | None = None,
        settings: Any | None = None,
        exclude_cols: list[str] | None = None,
        max_predictors: int | None = None,
        max_correlation: float | None = None,
        timestamp_col: str | None = None,
        timestamps: np.ndarray | None = None,
        progress_callback: Any | None = None,
        outcome_mode: str = "classification",
        **kwargs: Any,
    ) -> list[InfluenceFactor]:
        if data is None or data.is_empty():
            return []

        exclude_cols = exclude_cols or []
        settings_obj = settings if settings is not None else Settings()

        # Save the caller-supplied outcome column before _resolve_outcome
        # potentially replaces it with synthetic labels.
        original_outcome_col = outcome_col

        outcome, data, outcome_col = self._resolve_outcome(
            data, labels, outcome_col, outcome_mode
        )
        if len(outcome) == 0:
            return []

        resolved = self._resolve_te_outcome(data, original_outcome_col, outcome_mode)
        if resolved is None:
            return []
        te_outcome, te_outcome_valid = resolved

        (
            max_predictors,
            max_correlation,
            embed_k,
            embed_l,
            tau,
            significance_level,
            permutations,
            auto_meta,
        ) = self._resolve_analysis_params(
            settings_obj,
            te_outcome_valid,
            max_predictors,
            max_correlation,
        )

        predictors = predictor_selection.select_predictors(
            data,
            outcome_col,
            exclude_cols,
            max_predictors=max_predictors,
            max_correlation=max_correlation,
        )
        if not predictors:
            return []

        if not self._passes_temporal_dependence_gate(
            data, predictors, te_outcome, te_outcome_valid
        ):
            return []

        timestamps_arr = self._resolve_timestamps(data, timestamp_col, timestamps, settings_obj)
        median_dt = _median_dt(timestamps_arr)

        return self._analyze_predictors(
            data=data,
            predictors=predictors,
            te_outcome=te_outcome,
            progress_callback=progress_callback,
            embed_k=embed_k,
            embed_l=embed_l,
            tau=tau,
            significance_level=significance_level,
            permutations=permutations,
            median_dt=median_dt,
            auto_meta=auto_meta,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _analyze_pair(
        self,
        name: str,
        x: np.ndarray,
        y: np.ndarray,
        *,
        embed_k: int,
        embed_l: int,
        tau: int,
        significance_level: float,
        permutations: int,
        median_dt: float | None,
        auto_meta: dict[str, float | int] | None = None,
    ) -> InfluenceFactor | None:
        """Compute TE in both directions, run permutation tests, classify direction."""
        # The KSG estimator assumes a continuous joint distribution and fails when
        # variables take only a few discrete values (e.g., classification labels
        # 0/1/2). With discrete y_future and y_past, all k nearest-neighbour
        # distances collapse to 0, causing MI(y_future; y_past) to explode and the
        # CMI to become a large negative number that clamps to 0.
        #
        # Fix: add Gaussian jitter with scale << signal stddev to the outcome series
        # before computing TE. The jitter is negligibly small (1e-5 × std) so it does
        # not affect the entropy for well-separated distributions, but it breaks the
        # exact ties that make the KSG estimator degenerate.
        y_te = _jitter_discrete(y, self._rng)

        te_fwd = compute_transfer_entropy(
            x, y_te, k=embed_k, l=embed_l, tau=tau, k_neighbors=self._k_neighbors
        )
        te_rev = compute_transfer_entropy(
            y_te, x, k=embed_k, l=embed_l, tau=tau, k_neighbors=self._k_neighbors
        )

        # Skip pairs where both TE directions are zero after clamping.  This
        # happens when KSG CMI estimates are negative (finite-sample bias) and
        # the true signal is absent.  Including these factors would pollute the
        # consensus with rank noise.
        if te_fwd == 0.0 and te_rev == 0.0:
            return None

        p_fwd, ci_fwd = self._permutation_test(x, y_te, te_fwd, embed_k, embed_l, tau, permutations)
        p_rev, _ = self._permutation_test(y_te, x, te_rev, embed_k, embed_l, tau, permutations)

        fwd_sig = p_fwd is not None and p_fwd < significance_level
        rev_sig = p_rev is not None and p_rev < significance_level

        if fwd_sig and not rev_sig:
            direction = CausalDirection.FORWARD
        elif rev_sig and not fwd_sig:
            direction = CausalDirection.REVERSE
        elif fwd_sig and rev_sig:
            direction = CausalDirection.BIDIRECTIONAL
        else:
            direction = CausalDirection.INDETERMINATE

        lag_seconds = float(tau * median_dt) if median_dt is not None else None

        return InfluenceFactor(
            name=name,
            strength=_normalise_te(te_fwd),
            method=self.name,
            direction=direction,
            p_value=p_fwd,
            lag=lag_seconds,
            lag_rows=tau,
            confidence_interval=ci_fwd,
            metadata={
                "te_forward_nats": te_fwd,
                "te_reverse_nats": te_rev,
                "delta_te": te_fwd - te_rev,
                "p_value_reverse": p_rev,
                "embed_k": embed_k,
                "embed_l": embed_l,
                "tau": tau,
                "k_neighbors": self._k_neighbors,
                "n_samples": len(x),
                "permutations": permutations,
                "auto_embedding": bool(auto_meta),
                "auto_tau": int(auto_meta.get("auto_tau", tau)) if auto_meta else tau,
                "auto_dim": int(auto_meta.get("auto_dim", embed_k)) if auto_meta else embed_k,
                "auto_fnn_rate": float(auto_meta.get("auto_fnn_rate", np.nan)) if auto_meta else np.nan,
                "model_assumptions": [
                    "Requires time-ordered observations",
                    "KSG estimator assumes continuous distributions",
                    "Does not control for observed confounders",
                    "Stationarity improves reliability but is not required",
                ],
            },
        )

    def _permutation_test(
        self,
        x: np.ndarray,
        y: np.ndarray,
        observed_te: float,
        k: int,
        l: int,
        tau: int,
        permutations: int,
    ) -> tuple[float | None, tuple[float, float] | None]:
        """Permutation test for TE(X → Y).

        Shuffles *x* to break the temporal coupling while preserving its
        marginal distribution, then recomputes TE for each permuted series.
        Returns the one-sided p-value and the 95th-percentile interval of
        the null distribution.
        """
        if permutations <= 0:
            return None, None

        null_te = np.empty(permutations, dtype=float)
        for i in range(permutations):
            x_perm = self._rng.permutation(x)
            null_te[i] = compute_transfer_entropy(
                x_perm, y, k=k, l=l, tau=tau, k_neighbors=self._k_neighbors
            )

        count = int(np.sum(null_te >= observed_te))
        p_value = float((count + 1) / (permutations + 1))
        ci = (float(np.percentile(null_te, 2.5)), float(np.percentile(null_te, 97.5)))
        return p_value, ci

    def _resolve_timestamps(
        self,
        data: pl.DataFrame,
        timestamp_col: str | None,
        timestamps: np.ndarray | None,
        settings: Any,
    ) -> np.ndarray | None:
        if timestamps is not None:
            return self._coerce_timestamps(timestamps)
        if timestamp_col and timestamp_col in data.columns:
            return self._coerce_timestamps(data[timestamp_col].to_numpy())
        settings_col = self._get_setting(
            settings, "profiling.lag_detection.timestamp_column", None
        )
        if settings_col and settings_col in data.columns:
            return self._coerce_timestamps(data[settings_col].to_numpy())
        return None


def _median_dt(timestamps: np.ndarray | None) -> float | None:
    """Return the median time step from a timestamps array, or None."""
    if timestamps is None or len(timestamps) < 2:
        return None
    diffs = np.diff(timestamps.astype(float))
    dt = float(np.nanmedian(diffs))
    return dt if dt > 0 else None


def _jitter_discrete(arr: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Return *arr* unchanged if it looks continuous, or with tiny Gaussian jitter
    if it looks discrete (fewer than 10 unique values).

    The KSG nearest-neighbour MI estimator requires a continuous joint
    distribution.  When the outcome series is discrete (e.g., performance class
    labels 0/1/2), all nearest-neighbour distances collapse to zero, making
    the estimator degenerate.  Adding jitter with scale 1e-5 × std breaks the
    exact ties without meaningfully perturbing the entropy of well-separated
    distributions.
    """
    n_unique = len(np.unique(arr))
    if n_unique >= 10:
        return arr
    scale = float(np.std(arr)) * 1e-5
    if scale == 0.0:
        scale = 1e-8
    return arr + rng.normal(0.0, scale, size=len(arr))
