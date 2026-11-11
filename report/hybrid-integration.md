# Hybrid integration — 11 November 2026

Implementation branch: `codex/hybrid-mpi-integration`, based on
`feature/openmp-hybrid` commit `2ea8a5a`. Existing OpenMP source/kernels/results
and Person A's serial baseline are unchanged.

## Reused MPI implementation

B's `feature/mpi-poisson` commit `1756eff` supplies the four reviewed files:
`docs/mpi_handoff.md`, `include/mpi_poisson.hpp`, `src/mpi_poisson.cpp`, and
`src/mpi_main.cpp`. They are preserved verbatim in `references/mpi/`, with exact
hashes in `UPSTREAM.json`. A's serial core matches the version B used.
The MPI-only target compiles these same sources. B's build files/scripts and
existing validation/benchmark/grid CSV evidence are not merged or overwritten.

The upstream receipt at
`results/hpc/mpi-1539665.stdct-mgmt-02/validation/validation.json` reports 162/162
passing cases on GN-A40-075. It was inspected directly on B's branch. This is
upstream MPI evidence, not new hybrid evidence. The old handoff's pending-status
paragraph predates that evidence commit.

`solve_hybrid` calls B's `decompose_rows` and `exchange_halos` directly. Row counts
are N/P plus one for the first N%P ranks, with local-to-global y mapping supplied
by B's domain object. The same full-row blocking Sendrecv calls/tags 100/101,
physical zero halos, int-count bounds and rank<=N restriction apply. Only the
local update is replaced by the OpenMP operation.

## RHS, threads and timing

A/B store unscaled f. The existing standalone OpenMP kernel expects h²*f. A new
overload in `include/hybrid/local_rows.hpp` uses unscaled f and forms h²*f in the
stencil, matching serial/MPI arithmetic and avoiding a second scale factor.
The original OpenMP implementation/header is untouched. The overload retains
static row scheduling, two buffers and a thread-local maximum reduction.

`hybrid_main` requests/checks MPI_THREAD_FUNNELED. The solve additionally checks
MPI_Is_thread_main, MPI_Query_thread and that it is outside an OpenMP region.
Dynamic teams are disabled; the actual team size is probed and its minimum and
maximum compared across ranks before timing. A mismatch aborts the communicator.
The JSON reports actual threads and the minimum provided MPI support level.

Every MPI call is on the initializing/main thread outside worker regions. Each
local kernel returns only after all threads join. The main thread swaps buffers,
then in convergence mode performs MPI_Allreduce(MPI_MAX) and tests <=tol. Fixed
mode does exactly K updates with no convergence work/reductions in the loop.

Allocation, unscaled forcing construction and team probing precede the timing
barrier. MPI_Wtime covers each halo exchange, local update/join, swap and required
convergence reduction. The maximum-rank elapsed time reduction follows the timer.
Final-current halos are refreshed before diagnostics; residual/error maxima are
reduced globally. Nonuniform Gatherv uses B's row counts/offsets and root inserts
zero boundary rows. Only root writes the full CSV and primary JSON; an output
failure is broadcast before all ranks finalize. Fatal exceptions abort peers.

MPI/hybrid use A/B's strict mode-specific CLI, `n` JSON key, exit 2 for errors and
3 for non-convergence. The standalone OpenMP interface remains unchanged; tools
accept either n/N and pass explicit problem/mode/iteration settings.

## Actual local validation

Apple M4 MacBook Air; Apple Clang 21.0.0, CMake 3.24.3 Release -O3,
Anaconda MPICH 4.3.2 and LLVM OpenMP. These are local functional tests, not Vanda
Open MPI measurements or performance results.

- Four CTest entries passed: original local rows, original OpenMP numerical suite,
  new unscaled hybrid kernel test, and A's original serial tests.
- 494 distributed checks passed: 486 complete-grid numerical comparisons and
  eight expected-error/no-hang checks.
- MPI-only versus serial: 98 numerical cases. Hybrid versus serial: 194;
  hybrid versus MPI-only at matching ranks: 194.
- Both sine problems, N=10/ranks=3, N=ranks, rank/thread combinations through
  8x1/4x2/2x4/1x8, fixed K=1/2/31, convergence tol=1e-10 and explicit exhausted
  convergence were checked. The latter uses tol=1e-15/max-iters=1 for N>=2.
- Every full CSV shape, finite value, zero boundary and pointwise solution was
  checked with atol=1e-10/rtol=1e-8. The largest observed grid difference was
  **0.0** on this local build. Residual/error were independently recomputed from
  gathered grids, also detecting stale final halos or wrong global metrics.
- Runtime hybrid thread support/effective team sizes were checked in every
  hybrid numerical case. Bad CLI, ranks>N and output-overwrite failures exited
  without hanging. Existing output contents were preserved.

Compact evidence and exact source/binary hashes:
`results/local/hybrid-integration-20261111/validation-summary.json`.
Full grids, per-case metrics, commands and stdout/stderr are retained in
`full-validation.tar.gz` beside it. No local timing is used for a scaling figure.

## Vanda validation and benchmarks pending execution

Follow `report/vanda-runbook.md` using a fresh clone of this new branch.
`hybrid-validate` reruns the environment smoke, CTest and full serial/MPI/hybrid
matrix on allocated compute nodes with the verified single-node workaround.
The `hybrid` benchmark job validates again in its own allocation, then gates
all timing on the exact binaries, launch mode and covered rank/thread cases.
Local evidence cannot satisfy that gate.

The prepared eight-worker comparison is 1x8/2x4/4x2/8x1, plus 1x1/2x1/4x1 for
strong scaling, N=128/256/512/1024 and fixed K=1000. Each has one excluded warm-up
and three measurements; serial is rebuilt and measured on the same node through
a one-core-bound launcher. OpenMP affinity diagnostics run only in excluded
warm-ups for hybrid, while process bindings are logged on every launch. Raw data,
medians, hardware, PBS allocation and source/compiler/MPI provenance are retained.
Do not mix these future jobs with B's earlier benchmark hardware/placement.

No Vanda hybrid numerical pass, runtime, speedup or efficiency is claimed yet.
The per-iteration team entry/join is deliberately simple; its overhead and the
tradeoff between ranks/threads must be assessed from actual cluster measurements.
