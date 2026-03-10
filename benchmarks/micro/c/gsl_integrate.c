/*
 * Numerical integration benchmark using GNU Scientific Library (GSL).
 *
 * This benchmark computes the integral of sin(x)/x from 0 to N*pi
 * using GSL's adaptive quadrature routines. GSL is typically NOT
 * installed on systems by default, demonstrating how SHARP can
 * package C programs with external library dependencies into AppImages.
 *
 * Usage: gsl_integrate <upper_bound_multiplier>
 *   upper_bound_multiplier: Integrate sin(x)/x from 0 to N*pi
 *
 * Returns the computation time in SHARP's @@@ Time format.
 *
 * © Copyright 2022--2025 Hewlett Packard Enterprise Development LP
 */

#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>

/* GSL headers - requires libgsl-dev */
#include <gsl/gsl_integration.h>
#include <gsl/gsl_errno.h>

/* Number of subintervals for adaptive integration */
#define WORKSPACE_SIZE 10000

/* Relative and absolute error tolerances */
#define EPSABS 1e-10
#define EPSREL 1e-10

/*
 * The integrand: sin(x)/x (sinc function, unnormalized)
 * This has a removable singularity at x=0 where the limit is 1.
 */
double sinc(double x, void *params) {
    (void)params;  /* unused */
    if (fabs(x) < 1e-10) {
        return 1.0;  /* limit as x->0 */
    }
    return sin(x) / x;
}

/*
 * Get current time in seconds with high precision.
 */
double get_time(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <upper_bound_multiplier>\n", argv[0]);
        fprintf(stderr, "  Integrates sin(x)/x from 0 to N*pi\n");
        return 1;
    }

    int n = atoi(argv[1]);
    if (n <= 0) {
        fprintf(stderr, "Error: multiplier must be positive\n");
        return 1;
    }

    double upper_bound = n * M_PI;

    printf("Computing integral of sin(x)/x from 0 to %d*pi (%.6f)\n", n, upper_bound);

    /* Set up GSL integration */
    gsl_integration_workspace *workspace = gsl_integration_workspace_alloc(WORKSPACE_SIZE);
    if (!workspace) {
        fprintf(stderr, "Error: failed to allocate GSL workspace\n");
        return 1;
    }

    gsl_function F;
    F.function = &sinc;
    F.params = NULL;

    double result, error;
    double start_time = get_time();

    /* Use QAGS (adaptive integration with singularities) */
    int status = gsl_integration_qags(&F, 0.0, upper_bound, EPSABS, EPSREL,
                                       WORKSPACE_SIZE, workspace, &result, &error);

    double elapsed = get_time() - start_time;

    gsl_integration_workspace_free(workspace);

    if (status != GSL_SUCCESS) {
        fprintf(stderr, "GSL integration error: %s\n", gsl_strerror(status));
        return 1;
    }

    /*
     * The integral of sin(x)/x from 0 to infinity is pi/2.
     * For finite bounds, it oscillates around pi/2.
     */
    printf("Result: %.15f\n", result);
    printf("Estimated error: %.2e\n", error);
    printf("Reference (pi/2): %.15f\n", M_PI / 2.0);
    printf("Computation time: %.6f seconds\n", elapsed);
    printf("@@@ Time %.6f\n", elapsed);

    return 0;
}
