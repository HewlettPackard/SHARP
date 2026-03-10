#!/usr/bin/env python3
"""
Symbolic polynomial expansion benchmark using SymPy.

This benchmark expands a polynomial (x + y + z)^N symbolically,
demonstrating symbolic computation performance. It uses the SymPy
library which is NOT in SHARP's standard venv, showing how SHARP
can package Python programs with external dependencies into AppImages.

Usage: sympy_expand.py <degree>
  degree: Polynomial degree N for (x + y + z)^N expansion

Returns the computation time in SHARP's @@@ Time format.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import sys
import time

# This import requires 'sympy' package (NOT in SHARP's venv)
from sympy import symbols, expand


def expand_polynomial(degree: int) -> tuple[int, int]:
    """
    Expand (x + y + z)^degree symbolically.

    Returns:
        Tuple of (number_of_terms, total_coefficient_sum)
    """
    x, y, z = symbols('x y z')
    expr = (x + y + z) ** degree
    expanded = expand(expr)

    # Count terms and sum coefficients
    terms = expanded.as_ordered_terms()
    num_terms = len(terms)

    # Sum all coefficients (for verification)
    # When x=y=z=1, result should be 3^degree
    coeff_sum = int(expanded.subs([(x, 1), (y, 1), (z, 1)]))

    return num_terms, coeff_sum


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: sympy_expand.py <degree>", file=sys.stderr)
        sys.exit(1)

    degree = int(sys.argv[1])

    print(f"Expanding (x + y + z)^{degree} symbolically...")

    start_time = time.perf_counter()

    num_terms, coeff_sum = expand_polynomial(degree)

    elapsed = time.perf_counter() - start_time

    # Verify: sum of coefficients should be 3^degree
    expected = 3 ** degree
    status = "OK" if coeff_sum == expected else "MISMATCH"

    print(f"Terms: {num_terms}, Coefficient sum: {coeff_sum} ({status})")
    print(f"Computation time: {elapsed:.4f}s")
    print(f"@@@ Time {elapsed:.6f}")


if __name__ == "__main__":
    main()
