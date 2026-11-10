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

## Pending

- Group review of the version-1 interface contract, especially row=y/column=x and
  optional asymmetric problem selection.
- MPI, OpenMP and hybrid integration; full-grid cross-implementation checks including
  N=10 with three ranks.
- Agreed HPC compiler/modules, scheduler allocation, core binding and compute-node trial.
- Actual Vanda/Atlas timing runs, scaling and grid-size figures, final report.

No Vanda job has been submitted by this work. No local timing is used as a substitute
for required HPC performance results. No commits, pushes or pull requests were made.
