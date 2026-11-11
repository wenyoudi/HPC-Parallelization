# Validation status

Date: 9 November 2026. Branch: serial-baseline-and-validation.

## Completed locally

- macOS ARM64, Apple Clang 21.0.0, CMake 3.21.3, Python 3.13.5 (CMake-selected interpreter).
- Release C++17 build with -O3: passed without compiler warnings.
- CTest serial_correctness: passed. This runs six Python unittest methods, including
  32 fixed-iteration/problem/grid subcases against an independent discrete-eigenmode
  formula, full-grid boundary checks, residual and analytic error checks, convergence
  consistency, iteration-limit handling, second-order refinement and invalid CLI cases.
- Debug build with AddressSanitizer and UndefinedBehaviorSanitizer: same tests passed.
- CSV comparison smoke: identical grids passed; changed value failed; NaN rejected.
- Benchmark collection smoke: N=8,10, K=5, three repeats each; six JSONL records and
  two CSV median summaries checked in a temporary directory. These are tooling checks,
  not scientific timing results.
- PBS shell syntax: bash -n passed.
- Asymmetric convergence example: N=32, tol=1e-8 converged after 1228 iterations;
  final max_update=9.9436989753343141e-9, residual_linf=4.2825309755301078e-5,
  error_linf=0.0025647886962486544. This illustrates why update tolerance, residual,
  and continuum error must not be treated as the same quantity.

The executable and temporary checks were built under /tmp, not committed. To repeat
core validation, follow the build and CTest commands in the root README.

## Vanda serial validation

Job 1535699 completed successfully on GN-A40-075; serial_correctness passed.
GCC 11.3.0, CMake 3.24.3 and Python 3.9.18 were recorded. See the
[original log](../results/validation/vanda_serial_1535699.log).

## Cross-implementation review (11 November 2026)

OpenMP: 16 recorded comparisons reviewed. MPI: 144 exported grid pairs independently
re-compared, plus 18 additional recorded checks. Hybrid job 1541184: 486 additional grid
pairs re-compared, all identical; eight expected-error outcomes reviewed. See the
[stage-two review](stage2_validation.md) for coverage, provenance and limitations.

## Pending

- Serial grid-size experiments and figures; consolidated scaling analysis and report.
- Integration of parallel implementations into the shared final checkout.

Local review of archived Vanda outputs is not a new HPC performance experiment.
