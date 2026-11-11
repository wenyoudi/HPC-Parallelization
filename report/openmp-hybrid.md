# OpenMP and hybrid contribution — draft for group integration

**11 November update:** the separate hybrid solver is now integrated on `codex/hybrid-mpi-integration` using B's exact public decomposition/halo functions. Four CTest entries and 494 local MPI/hybrid checks passed; see [hybrid-integration.md](hybrid-integration.md). B's upstream Vanda receipt reports 162 MPI checks, while new Vanda hybrid validation/measurements remain pending. The dated OpenMP design/results below are preserved.

Status: OpenMP implemented and validated locally on 9 November 2026. Hybrid integration awaits Member B's MPI framework. Vanda measurements remain outstanding. Member A should insert group names/IDs and integrate these sections into the final PDF; no placeholder performance results should be presented as measured data.

## Shared-memory design

The five-point Jacobi update has spatial dependencies across iterations but independent output cells within an iteration. Two flat, contiguous, row-major `std::vector<double>` buffers preserve this distinction: every update reads only the old buffer and writes a different output cell. The outer interior-row loop is distributed across OpenMP threads using `schedule(static)`; each thread traverses contiguous columns within its assigned rows. A regular stencil gives nearly equal work per row, so static scheduling avoids repeated dynamic work assignment. Rows represent y and columns represent x, including in the asymmetric validation problem.

The OpenMP-only solver uses a persistent parallel region around the iteration loop to amortize team entry across many Jacobi steps. An implicit work-sharing barrier completes all cell writes before a `single` section swaps the two shared pointers. That section's implicit barrier publishes the new buffers and common stop decision to every thread. No interior value is updated in place. Both buffers start at zero, boundary entries are never written, and each output cell has one writer. These properties avoid stencil data races; there are no critical sections in the cell loop.

Convergence mode adds `reduction(max:max_update)` over row-local absolute update maxima. A synchronized single section resets this shared reduction variable before each step. All threads see the same `max_update<=tol` stopping decision after the swap. Reaching the limit emits `converged:false`, a diagnostic and exit status 2. Fixed mode instantiates a separate kernel without absolute-difference computation or convergence reductions, completes exactly K steps, and reports `converged:null,max_update:null`. A successful fixed benchmark does not claim numerical convergence.

The RHS is evaluated from global coordinates once before timing and stored as `h²*f`. All variants should agree to this representation when the serial/MPI implementations arrive so benchmark arithmetic and memory traffic are comparable. No fast-math flags are used. Allocation, initialization, final residual/error evaluation and CSV export are excluded from `solve_seconds`; team execution, stencil updates, buffer swaps and their required barriers are included. Convergence checks are included only in convergence-mode timings. Final maximum residual and analytical error use separate OpenMP reductions outside timing.

Each iteration needs at least a completion barrier and a synchronized swap. For small grids, this coordination can cost more than the useful arithmetic, even with a persistent team. Larger grids provide more work per synchronization but may eventually be limited by memory bandwidth. Static scheduling, buffer traversal and first-touch/NUMA placement should be revisited only after reliable cluster measurements; the current implementation prioritizes clarity and numerical correctness.

## Hybrid design prepared for integration

The agreed MPI decomposition assigns contiguous interior rows, with the first `N%ranks` ranks receiving one extra row. Each rank keeps two halo rows. Global-coordinate RHS evaluation, endpoint zero boundaries, halo tags/communication and nonuniform solution gathering must reuse Member B's implementation. See [the integration handoff](hybrid-integration.md) for exact interfaces and checks.

`include/openmp_rows.hpp` supplies a tested OpenMP local-row operation using the same numerical stencil as the standalone solver. The proposed hybrid loop performs old-buffer halo exchange on the main thread, calls the threaded local operation, then swaps buffers after its implicit thread join. Convergence mode performs an OpenMP maximum reduction followed by main-thread `MPI_Allreduce(MPI_MAX)`; fixed mode performs neither convergence reduction. Initialization must request and verify `MPI_THREAD_FUNNELED`, because worker threads never call MPI. Communication/computation overlap is deferred until this design passes validation.

Timing will start after a rank barrier, use local `MPI_Wtime` measurements and report their global maximum, with the final timing reduction outside the measured section. Final-current halos must be exchanged again before residual evaluation; otherwise a correct solution may have an incorrect reported residual. Residual/error maxima are global reductions. Root gathers nonuniform interior rows, inserts global boundary rows and writes one complete CSV without duplicate halos. Only rank 0 prints the primary JSON.

Fewer ranks reduce halo interfaces and global-collective participants, while more threads add local barriers and may contend for memory bandwidth. More ranks can improve locality or avoid threaded overhead but increase communication and reduce rows per rank. These are hypotheses to test with 8×1,4×2,2×4,1×8 on the same allocated node and binding policy. No hybrid runtime or MPI correctness result is claimed yet.

## Local validation evidence

`results/local/validation.log` records the optimized build and 13 passing Python test groups, plus a passing C++ local-row test across 1/2/4/8 threads. The tests compare with an independently written scalar Python oracle at absolute tolerance `1e-10` and relative tolerance `1e-8`; this is not yet a comparison with Member A's production serial executable. A separate closed-form discrete sine mode checks multiple iterations, and the one-interior-point first update is checked against `pi²/8`.

Other checks cover initialization with K=0, exact iteration counts, odd/even swaps, zero boundaries, independently recomputed residual and analytical error, maximum-update convergence iteration counts, explicit non-convergence and malformed CLI/output paths. The asymmetric exact solution `sin(pi*x)sin(2*pi*y)` and RHS `5*pi²*u_exact` detect transposed x/y indexing. The local-row C++ test uses three interior rows, deliberately non-symmetric values and nonzero upper/lower halos; it validates the prepared local kernel, not MPI halo exchange or gather operations.

The same 13 numerical test groups also passed an `-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer` build, recorded in `results/local/sanitizer-validation.log`, with no sanitizer report. Two additional pipeline test groups check tiny real solves, median calculation, absent serial baselines, oversubscription rejection, required cluster allocation, insufficient/duplicate samples, warm-up exclusion and prevention of mixed-site analysis. The comparison harness was smoke-tested with OpenMP as both inputs in asymmetric fixed/convergence modes; this validates the harness, not equivalence of distinct implementations.

The additional convergence evidence in `results/local/accuracy.json` was obtained separately from fixed-mode benchmarks, with one OpenMP thread:

| N | Mode | Tolerance | Iterations | Final max update | Residual infinity norm | Analytical error infinity norm |
|---:|---|---:|---:|---:|---:|---:|
| 32 | converge | 1e-8 | 2871 | 9.9662e-9 | 4.3216e-5 | 7.5169e-4 |
| 64 | converge | 1e-8 | 9987 | 9.9944e-9 | 1.6871e-4 | 1.8603e-4 |
| 128 | converge | 1e-8 | 34722 | 9.9987e-9 | 6.6536e-4 | 1.5709e-5 |

Max update, residual and analytical error measure different quantities. In particular, the residual associated with an update is scaled by `4/h²`, so a fixed update tolerance does not imply a fixed residual tolerance as N grows. A converged discrete solution retains truncation error relative to the continuous exact solution. Iteration and discretization errors can also partially cancel, making the default-tolerance error table unsuitable for a refinement-rate claim.

For refinement, tighter `tol=1e-13` was used with grids that halve h exactly:

| N | h | Iterations | Analytical error infinity norm |
|---:|---:|---:|---:|
| 15 | 1/16 | 1341 | 0.0032189644350 |
| 31 | 1/32 | 5098 | 0.0008035776588 |
| 63 | 1/64 | 19260 | 0.0002008217268 |

Successive error ratios are approximately 4, consistent with second-order spatial accuracy after reducing iteration error. These accuracy runs are not mixed into scaling comparisons.

Pending validation: comparisons against the real serial/MPI implementations, MPI_THREAD_FUNNELED checks, nondivisible N=10/ranks=3 communication and gathering, final-halo residuals, other rank/thread combinations and all tests on allocated Vanda compute nodes.

## Local benchmark methodology and observations

Hardware: MacBook Air Mac16,12, Apple M4, 10 CPU cores (4 performance, 6 efficiency), 16 GB memory; Darwin 25.6.0, arm64. Compiler: Apple Clang 21.0.0 (`clang-2100.1.1.101`), `-O3 -std=c++17`, linked to the existing Anaconda LLVM OpenMP runtime. Exact build commands, platform inventory and executable/source hashes are in `results/local/openmp-m4-20261109/metadata.json`. The MPI launcher identifies MPICH 4.3.2 but its configured C++ compiler is absent; it was not used for these OpenMP runs.

The matrix used one process, N=128/256/512/1024, fixed K=1000 and 1/2/4/8 threads, never exceeding eight workers on the ten-core host. Each configuration had one recorded warm-up and three recorded measurements. Measured repetitions were shuffled with seed 5208; the table reports their medians. No solution export was requested. Each process set `OMP_DYNAMIC=FALSE`, `OMP_PLACES=cores`, `OMP_PROC_BIND=close`; the runtime's affinity diagnostic nevertheless reported `{undefined}` on macOS. Placement is therefore **requested, not verified**. The Mac was not an exclusive scheduler allocation, so these are local exploratory results, not instructor-required cluster evidence.

| N | 1 thread (s) | 2 threads (s) | 4 threads (s) | 8 threads (s) |
|---:|---:|---:|---:|---:|
| 128 | 0.004312 | 0.010176 | 0.014233 | 0.036831 |
| 256 | 0.018026 | 0.016775 | 0.018270 | 0.041856 |
| 512 | 0.071316 | 0.042624 | 0.037304 | 0.055018 |
| 1024 | 0.276842 | 0.187498 | 0.152261 | 0.175992 |

At N=128 all multithreaded configurations were slower than one thread; eight threads took about 8.54 times as long. At N=512, four threads gave approximately 1.91× relative speedup and 47.8% relative efficiency. At N=1024, four threads gave approximately 1.82× relative speedup and 45.5% relative efficiency; eight threads were slower than four, and their samples ranged from 0.1669 to 0.2304 s. These ratios use **the OpenMP solver with one thread**, because no production serial baseline was available. They are not the assignment's serial-baseline speedup or efficiency.

The growth in useful work with grid size is consistent with better amortization of thread synchronization, but the measurements do not isolate the causes of the eight-thread decline. Mixed core capabilities, unavailable affinity, bandwidth, operating-system scheduling and thermal behavior are possible contributors. No hardware counters or controlled cluster experiment were collected, so attributing a measured fraction to any one cause would be unsupported.

The analysis pipeline preserves every raw measurement and computes medians/minima/maxima in `report/figures/summary.csv`. Actual local figures are available as PDF and 300-dpi PNG:

- `local_openmp_runtime`: runtime versus threads for each grid; error bars span sample minimum/maximum.
- `local_openmp_speedup_omp1`: relative speedup, with ideal scaling.
- `local_openmp_efficiency_omp1`: relative efficiency versus threads.

These plots are labeled LOCAL. No serial-baseline or hybrid figure is generated without appropriate measurements.

## Vanda experiments required before submission

Reach Vanda through the user's authorized network/authentication; discover its live PBS/module environment, then run the supplied conditional job workflow in [vanda-runbook.md](vanda-runbook.md). Keep all actual cluster results under a separate Vanda run directory. Collect compiler/MPI versions, scheduler allocation, actual compute-node CPU topology and binding evidence. Run correctness before performance, include Member A's same-build serial baseline, and repeat each configuration at least three times.

After MPI integration, compare equal eight-worker hybrid configurations and strong scaling at fixed N/K. Use `S(P)=T_serial/T_parallel` and `E(P)=S(P)/P`, with `P=ranks*threads`; do not substitute local one-thread-relative results for this definition. Keep node count/placement and mode explicit. Replace or supplement this local exploratory section with actual Vanda figures and conclusions; the required cluster results and final PDF remain group deliverables due 16 November.
