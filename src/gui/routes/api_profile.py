# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Profile HTTP JSON endpoints (``/api/v1/profile/...``) for the SHARP GUI.

These endpoints are backed by GUI service modules. Phase 12 will migrate
implementation behind ``src/api``. See ``docs/api.md``.
"""

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
import json

from fastapi import APIRouter, HTTPException

from ..contracts.schemas import (
    ProfileAnalyzeRequest,
    ProfileAnalyzeResponse,
    ProfileFactorItem,
    ProfileFactorsRequest,
    ProfileFactorsResponse,
    SuggestCutoffRequest,
    SuggestCutoffResponse,
)
from ..services.profile import compute_profile_analysis
from ..services.shared import _load_filtered_dataframe, filter_kwargs_from_specs
from src.core.profile.cutoff import suggest_cutoff_from_data

router = APIRouter(prefix="/api/v1/profile", tags=["api"])


def _jsonify(value: Any) -> Any:
    """Convert common scientific/Pydantic values to JSON-safe Python objects."""
    if hasattr(value, "model_dump"):
        return _jsonify(value.model_dump())
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonify(asdict(value))
    if hasattr(value, "__dict__"):
        return _jsonify(vars(value))
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonify(v) for v in value]
    if hasattr(value, "to_dicts"):
        return _jsonify(value.to_dicts())
    if hasattr(value, "to_list"):
        return _jsonify(value.to_list())
    if hasattr(value, "tolist"):
        return _jsonify(value.tolist())
    if hasattr(value, "item"):
        return value.item()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _factor_item(factor: Any) -> ProfileFactorItem:
    """Convert an InfluenceFactor-like object into the stable API shape."""
    data = _jsonify(factor)
    return ProfileFactorItem(
        name=str(data.get("name", "")),
        strength=data.get("strength"),
        rank=data.get("rank"),
        method=data.get("method"),
        direction=data.get("direction"),
        p_value=data.get("p_value"),
        lag=data.get("lag"),
        lag_rows=data.get("lag_rows"),
        confidence_interval=data.get("confidence_interval"),
        falsification_plan=data.get("falsification_plan"),
        metadata=data.get("metadata"),
    )


def _run_analysis(req: ProfileAnalyzeRequest | ProfileFactorsRequest) -> dict[str, Any]:
    """Run shared profile analysis with consistent client-error mapping."""
    path = Path(req.csv_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"CSV file not found: {req.csv_path}")
    try:
        filter_kwargs = filter_kwargs_from_specs(req.filters)
        return compute_profile_analysis(
            csv_path=req.csv_path,
            metric=req.metric,
            lower_is_better=req.lower_is_better,
            num_groups=req.num_groups,
            auto_detect=req.auto_detect,
            analyzer_name=req.analyzer_name,
            filter_metric=filter_kwargs["filter_metric"],
            filter_min=filter_kwargs["filter_min"],
            filter_max=filter_kwargs["filter_max"],
            filter_values=filter_kwargs["filter_values"],
            excluded_predictors=req.excluded_predictors,
            cutoff_values=req.cutoff_values,
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/analyze", response_model=ProfileAnalyzeResponse)
def analyze(req: ProfileAnalyzeRequest) -> ProfileAnalyzeResponse:
    """Run full profile analysis pipeline and return all JSON-relevant results."""
    result = _run_analysis(req)
    factors = [_factor_item(f) for f in (result.get("factors") or [])]
    return ProfileAnalyzeResponse(
        error=result.get("error"),
        factors=factors,
        labels=_jsonify(result.get("labels")),
        quality=_jsonify(result.get("quality")),
        analysis_data=_jsonify(result.get("analysis_data")),
        reduced_columns=_jsonify(result.get("reduced_columns")),
        cleaned_columns=_jsonify(result.get("cleaned_columns")),
        correlations=_jsonify(result.get("correlations")),
        predictor_stats=_jsonify(result.get("predictor_stats")),
        analyzer_name=result.get("analyzer_name"),
    )


@router.post("/factors", response_model=ProfileFactorsResponse)
def factors(req: ProfileFactorsRequest) -> ProfileFactorsResponse:
    """Return the ranked factors subset from profile analysis."""
    result = _run_analysis(req)
    return ProfileFactorsResponse(
        error=result.get("error"),
        factors=[_factor_item(f) for f in (result.get("factors") or [])],
    )


@router.post("/suggest-cutoff", response_model=SuggestCutoffResponse)
def suggest_cutoff(req: SuggestCutoffRequest) -> SuggestCutoffResponse:
    """Suggest cutoff value(s) for binary or manual multi-group labeling."""
    path = Path(req.csv_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"CSV file not found: {req.csv_path}")
    try:
        filter_kwargs = filter_kwargs_from_specs(req.filters)
        df = _load_filtered_dataframe(req.csv_path, **filter_kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if req.metric not in df.columns:
        raise HTTPException(status_code=422, detail=f"Metric '{req.metric}' not found in CSV")

    values = [float(v) for v in df[req.metric].drop_nulls().to_list()]
    if not values:
        return SuggestCutoffResponse(error="Metric has no numeric values", cutoffs=None, strategy=None)

    num_groups = int(req.num_groups or 2)
    if req.strategy == "manual" or num_groups > 2:
        if num_groups < 2:
            raise HTTPException(status_code=422, detail="num_groups must be >= 2")
        sorted_values = sorted(values)
        cutoffs: list[float] = []
        for i in range(1, num_groups):
            pos = i * (len(sorted_values) - 1) / num_groups
            lo = int(pos)
            hi = min(lo + 1, len(sorted_values) - 1)
            frac = pos - lo
            cutoffs.append(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac)
        return SuggestCutoffResponse(error=None, cutoffs=cutoffs, strategy="manual")

    cutoff = suggest_cutoff_from_data(df, req.metric)
    if cutoff is None:
        return SuggestCutoffResponse(error="Could not suggest cutoff", cutoffs=None, strategy=None)
    return SuggestCutoffResponse(error=None, cutoffs=[cutoff], strategy="binary")
