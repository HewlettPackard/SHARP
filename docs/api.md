# SHARP GUI HTTP API (`/api/v1`)

This document describes the HTTP JSON endpoints served by the SHARP FastAPI GUI.
These routes are intended for external programmatic consumers. The browser UI
continues to use `/ui/*` HTML-fragment routes.

## Intermediate architecture note

The profile and mitigation endpoints are active, but they are currently backed by
`src/gui/services/*` and `src/core/*` helpers. Phase 12 will migrate the HTTP
handlers behind the `src/api` service layer while preserving these request and
response shapes where possible.

## Active endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/v1/experiments` | List discovered experiments |
| GET | `/api/v1/experiments/{experiment}/tasks` | List tasks for an experiment |
| GET | `/api/v1/benchmarks` | List available benchmarks |
| GET | `/api/v1/backends` | List available backends |
| POST | `/api/v1/compare` | Compare two runlogs |
| POST | `/api/v1/distribution/summary` | Summary statistics for a metric |
| POST | `/api/v1/distribution/changepoints` | Changepoint analysis |
| POST | `/api/v1/distribution/characterize` | Narrative distribution characterization |
| POST | `/api/v1/profile/analyze` | Full profile analysis over a CSV/metric |
| POST | `/api/v1/profile/factors` | Ranked factor subset of profile analysis |
| POST | `/api/v1/profile/suggest-cutoff` | Binary or manual multi-group cutoff suggestion |
| GET | `/api/v1/mitigate/list` | List mitigations |
| GET | `/api/v1/mitigate/info/{mitigation}` | Mitigation metadata and automation status |
| POST | `/api/v1/mitigate/apply` | Queue an asynchronous mitigation run |
| GET | `/api/v1/mitigate/apply/{job_id}` | Poll mitigation run status |

## Filtering

All public HTTP endpoints that filter CSV rows use the same request shape:

```json
{
  "filters": [
    {"metric": "backend", "kind": "in", "values": ["local", "perf"]}
  ]
}
```

`FilterSpec` fields:

| Field | Meaning |
| --- | --- |
| `metric` | Column to filter |
| `kind` | `equals`, `in`, or `range` |
| `value` | Single value for `equals` |
| `values` | Value list for `in` |
| `min` / `max` | Inclusive range bounds for `range` |

Examples:

```json
{"metric": "backend", "kind": "equals", "value": "local"}
{"metric": "backend", "kind": "in", "values": ["local", "mpi"]}
{"metric": "repeat", "kind": "range", "min": "1", "max": "3"}
```

Current implementation note: the HTTP contract is list-shaped for forward compatibility,
but the existing GUI services support one active filter column today. Supplying more than
one filter returns HTTP 422. `wip/TODO-filters.md` tracks the later internal refactor to
make `FilterSpec` the canonical representation all the way through computation.

## Reserved stubs

| Method | Endpoint | Status |
| --- | --- | --- |
| POST | `/api/v1/mitigate/revert` | Returns HTTP 501 until safe revert semantics exist |

## Profile endpoints

### POST `/api/v1/profile/analyze`

Request: `ProfileAnalyzeRequest` in `src/gui/contracts/schemas.py`.

Returns `ProfileAnalyzeResponse` containing:
- `factors`: structured factor summaries (`name`, `strength`, `rank`, `method`, etc.)
- `labels`
- `quality`
- `analysis_data`
- `reduced_columns`
- `cleaned_columns`
- `correlations`
- `predictor_stats`
- `analyzer_name`
- `error` when the analysis service returns a recoverable analysis error

### POST `/api/v1/profile/factors`

Request: `ProfileFactorsRequest`.

Returns `ProfileFactorsResponse` with only the structured ranked factors and any
recoverable analysis error.

### POST `/api/v1/profile/suggest-cutoff`

Request: `SuggestCutoffRequest`.

- Default/binary mode returns one cutoff from `suggest_cutoff_from_data`.
- Manual mode or `num_groups > 2` returns `num_groups - 1` quantile cutoffs.

## Mitigation endpoints

### GET `/api/v1/mitigate/list`

Returns `MitigationListResponse` with all known mitigation names.

### GET `/api/v1/mitigate/info/{mitigation}`

Returns `MitigationInfoResponse` with description, references, automation flag,
and `backend_options` when the mitigation has an executable backend.

### POST `/api/v1/mitigate/apply`

Queues an asynchronous mitigation run and returns HTTP 202 with
`MitigationApplyResponse` (`job_id`, `status`, `message`).

### GET `/api/v1/mitigate/apply/{job_id}`

Returns `MitigationApplyStatusResponse` with current job status and, when
finished, `success`, `error`, `mitigation_csv`, and `notice` fields.

## Schema source

All request/response models are defined in `src/gui/contracts/schemas.py`.
