"""
Array conversion utilities shared across core modules.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

import numpy as np
import polars as pl


NUMERIC_POLARS_DTYPES = {
    pl.Float64,
    pl.Float32,
    pl.Int64,
    pl.Int32,
    pl.Int16,
    pl.Int8,
    pl.UInt64,
    pl.UInt32,
    pl.UInt16,
    pl.UInt8,
    pl.Boolean,
}


def to_numpy(values: np.ndarray | pl.Series | pl.DataFrame | None) -> np.ndarray:
    """Convert supported inputs to a NumPy array."""
    if values is None:
        return np.array([], dtype=float)
    if isinstance(values, pl.Series):
        return values.to_numpy()
    if isinstance(values, pl.DataFrame):
        return values.to_numpy()
    return np.asarray(values)


def is_numeric_polars_dtype(dtype: pl.DataType) -> bool:
    """Return True when dtype is numeric or boolean in Polars."""
    return dtype in NUMERIC_POLARS_DTYPES


__all__ = ["to_numpy", "is_numeric_polars_dtype", "NUMERIC_POLARS_DTYPES"]