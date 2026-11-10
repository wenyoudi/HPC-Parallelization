# Hybrid integration handoff — target 11 November 2026

## Dependency and status

Current update: user-confirmed MPI communication smoke job 1536986 passed on GN-A40-074 at 1/2/4 ranks with the single-node TM workaround. This is not Poisson or hybrid validation. Member A's serial source is available at commit `0e20822` and pinned verbatim under `references/serial/`; Member B's MPI source is still unavailable, confirmed by the user. Do not recreate their framework.

Prepared infrastructure now includes `scripts/mpi_launcher.py` (actual-PBS slots and rank/thread checks; `single-node` and original `pbs` modes), `scripts/validate_distributed.py`, a gated hybrid benchmark, and future PBS job kinds `mpi-validate`/`hybrid-validate`/`hybrid`. The actual CMake integration hook remains absent deliberately; see `cmake/README.md`. Actual integration and cluster numerical tests are pending. Existing OpenMP source/results and the upstream serial baseline are preserved.

On 9 November the local repository and remote `main` contained only a README. No MPI implementation or other remote branch existed. This branch therefore supplies the OpenMP solver and reusable local kernels, **not a competing MPI framework**. There is no `src/hybrid.cpp` executable yet. `make hybrid` deliberately fails with a dependency message; benchmark scripts refuse a missing binary.

Member B must provide:

- MPI solver source and headers, with build command and supported CLI/defaults.
- Row decomposition (`local_rows`, global first interior row, upper/lower neighbor), buffer ownership, stride and indexing.
- Blocking halo exchange routine and tags; error-handling conventions.
- Final global metric reductions and nonuniform gather/export routines.
- Known passing MPI tests and compiler/MPI module names on Vanda.

Agreed indexing: row is y, column is x. For rank `r`, `q=N/ranks`, `rem=N%ranks`, `local_rows=q+(r<rem)`, first global row `1+r*q+min(r,rem)`. Local row `i` maps to `first+i-1`. Require `ranks<=N`. Each flat buffer has `(local_rows+2)*(N+2)` elements; local rows 0 and `local_rows+1` are halos. This describes the agreed interface for comparison with B's implementation, not new MPI code.

## Integration sequence

1. Reuse B's decomposition, exchanges and exports. Create the hybrid entry point around that framework; avoid changing B's standalone MPI numerical path.
2. Initialize with `MPI_Init_thread(..., MPI_THREAD_FUNNELED, &provided)` on the main thread. Fail collectively if `provided<MPI_THREAD_FUNNELED`. Check MPI call statuses using B's convention and abort the communicator on fatal errors to avoid stranded ranks.
3. Initialize both solution buffers to zero. Evaluate RHS using global row coordinates and store `h²*f` for the kernel; this is a shared optimization that must be agreed for fair comparisons across variants.
4. Immediately before timing, call `MPI_Barrier`, then take `MPI_Wtime` on each rank. Allocate and initialize beforehand.
5. On each iteration, the main thread exchanges **old** top/bottom interior rows into **old** halos. At physical endpoints maintain zero global boundary rows. Reuse B's deadlock-safe communication and tags.
6. Call `poisson::update_local_rows<false>(old,new,rhs_scaled,local_rows,N)` in fixed mode. It has no max-update calculations/reductions. In convergence mode use `<true>`, followed by `MPI_Allreduce(...MPI_MAX...)` of its thread-reduced maximum on the main thread. Every rank participates and makes the same stopping decision.
7. Swap buffers only after the local kernel's parallel region has joined. Complete exactly K updates in fixed mode; in convergence mode use `max_update<=tol`, reporting exhausted limits explicitly.
8. Stop local timers **before** the global timing reduction. `MPI_Reduce(...MPI_MAX...)` supplies rank-0 `solve_seconds`. A rank synchronization immediately before the timers is mandatory; a trailing barrier is unnecessary for max elapsed time and must be consistent if B uses one.
9. Exchange final **current** halos again outside timing before residual evaluation. Otherwise halos may correspond to the penultimate buffer. Reduce residual/error maxima globally on the main thread.
10. For CSV export, gather interior rows in rank order using B's nonuniform `MPI_Gatherv` counts/displacements. Root constructs zero boundary rows and writes all N+2 rows; exclude duplicated halos. Check integer count/displacement limits or reject unsupported huge grids. Only root prints the primary JSON.

The prepared kernel creates and joins an OpenMP region for each local update, with `schedule(static)`. This is a simple FUNNELED design: all MPI is between parallel regions and always on the main thread. The OpenMP-only solver instead uses a persistent region to amortize repeated team setup. Keep this design difference explicit when interpreting small-grid hybrid overhead. Add a Makefile rule using the actual MPI compiler and OpenMP flags once integration exists; preserve `-O3`, exclude fast-math.

## Required integration validation

Run `tests/compare_solvers.py` with Member A's serial solver and independently with B's MPI-only solver as reference. Require N=10/ranks=3, first/last rank boundaries, N=ranks, one rank, odd/even K, fixed and convergence modes, and multiple rank/thread combinations. Add smaller N cases to the comparison script when integrating (its initial N=10 case covers nondivisible gather and final-halo metrics). Run the asymmetric test in all variants after agreeing its optional CLI. Verify fixed mode has no global convergence reduction, and verify rank-0-only output and MPI thread-support failures. These MPI checks have **not** run locally.

Use a single allocated eight-core node first for 8×1,4×2,2×4,1×8. Extend placement across nodes only after recording per-node ranks/threads and validating the launcher; do not pool single-node and multinode results.
