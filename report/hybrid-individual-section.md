# Hybrid MPI+OpenMP implementation and performance

## Design and correctness

The hybrid solver reuses the MPI implementation's contiguous row decomposition and blocking halo exchange, distributing local stencil rows with OpenMP `schedule(static)`. Two solution buffers separate reads from writes. The RHS remains unscaled f, with h²f formed inside the stencil. `MPI_THREAD_FUNNELED` support is checked; workers join before buffer swaps and MPI calls on the main thread. Convergence mode combines a local OpenMP maximum with `MPI_Allreduce`; fixed mode omits convergence reductions. Final halos are refreshed before diagnostics, and nonuniform gathering reconstructs the global grid. The local OpenMP region is entered/joined each iteration; communication/computation overlap is not implemented.

Vanda job **1541184.stdct-mgmt-02** passed four CTest suites, MPI smoke at 1/2/4/8 ranks, and **494/494 distributed checks**: 486 numerical comparisons plus eight expected-error cases. Tests covered both manufactured problems, uneven N=10 with three ranks, fixed iterations, convergence and iteration-limit exhaustion. All 972 saved grids were independently rechecked at absolute tolerance 1e-10 and relative tolerance 1e-8; the largest reference/candidate grid difference was zero.

## Methodology and scaling definitions

Measurements used one exclusive eight-core allocation on Vanda CN-140, with N=128/256/512/1024 and fixed K=1000. Each of seven hybrid layouts and a matched serial baseline had one excluded warmup and **exactly three measured repetitions per N**, giving 96 measurements and 32 warmups. Configurations were shuffled with seed 5208. Reported times are medians; whiskers show sample minimum–maximum, not confidence intervals. Fixed K controls work and does not imply convergence.

For P=R×T workers, the primary same-implementation metrics are **S_h = median(t_hybrid,1×1) / median(t_hybrid,R×T)** and **E_h = 100S_h/P percent**, at matching N and K. Thus hybrid 1×1 starts at S_h=1 and E_h=100%. The connected scaling curve varies ranks with T=1; other eight-worker layouts are separate points. All layouts, including 8×1 and 1×8, use the **hybrid executable**. They are not controlled comparisons with the standalone MPI-only or OpenMP-only solvers, whose performance superiority is not established here.

The measured hybrid interval is the maximum rank-local solve-loop time, including halo exchange, threaded updates, joins and swaps. Process launch, initialization, team probing, final diagnostics, gathering and export are excluded. The final timing reduction is outside the interval. No local-machine or separate-node timings are pooled.

## Results and interpretation

**The best eight-worker layout depends on grid size. Mixed MPI+OpenMP layouts are competitive at larger grids but do not have the lowest median at any of the four measured sizes.**

| N | Lowest-median eight-worker layout | Median time (ms) | S_h | E_h (%) |
|---:|:---:|---:|---:|---:|
| 128 | 8×1 | 7.108 | 1.957 | 24.5 |
| 256 | 8×1 | 13.747 | 4.256 | 53.2 |
| 512 | 1×8 | 48.846 | 6.766 | 84.6 |
| 1024 | 1×8 | 172.688 | 7.325 | 91.6 |

With T=1, runtime decreases monotonically from one to eight ranks at every N. Small-grid scaling is limited: N=128 reaches only 1.957× at eight workers. More useful work per synchronization is consistent with the improved scaling at larger N, although overhead components were not timed separately.

At N=512, all four eight-worker medians span less than 2.5%; 2×4 takes 49.168 ms versus 48.846 ms for 1×8. At N=1024, 2×4 takes 177.759 ms, about 2.94% longer than 1×8. These results support competitiveness of mixed layouts, not a universal hybrid advantage. Several larger-grid sample ranges overlap, and three repetitions on one allocation do not establish a general ranking. Per-iteration thread synchronization and additional MPI halo interfaces offer plausible tradeoffs; their individual costs were not measured.

For assignment-style comparison, the matched same-job serial ratio **S_s = median(t_serial) / median(t_hybrid,R×T)** remains available separately. At N=1024, 1×8 gives S_s=8.781 but S_h=7.325: hybrid 1×1 is already 1.199× faster than serial. Serial-relative ratios therefore combine scaling with implementation differences. A smaller same-code superlinear result remains at N=512, where 4×1 gives S_h=4.187 (E_h=104.7%). Cache locality or compiler effects are hypotheses; no cache, bandwidth, instruction or frequency counters were collected. Neither baseline-relative result proves sustainable greater-than-100% computational efficiency, and efficiency is not CPU utilization. These are single-node, fixed-iteration solve timings, not end-to-end or multi-node scaling results.

## Recommended main-report figures

1. **[Eight-worker runtime comparison](figures/vanda-hybrid-1541184-revised/eight_workers.pdf).** Median solve-loop times for 8×1, 4×2, 2×4 and 1×8 at each N, K=1000; three measured repetitions per bar, with minimum–maximum whiskers. Per-panel linear axes start at zero and have different scales. This directly supports the grid-dependent layout finding.
2. **[Same-implementation strong scaling](figures/vanda-hybrid-1541184-revised/speedup.pdf).** S_h relative to hybrid 1×1 at matching N and K; ratios of three-repetition medians. The T=1 curve varies R=1/2/4/8, while separate symbols show mixed and 1×8 layouts at P=8. S=P is a linear reference. This separates scaling from the serial/hybrid kernel difference.

These two figures are sufficient for the main report: one establishes the layout comparison, and the other separates scaling from implementation differences. The [compact benchmark summary](data/hybrid-vanda-1541184-summary.csv) retains full-precision medians, observed ranges and both scaling definitions. Additional charts are omitted from this handoff to avoid redundant report material.

## Reproducibility note

CN-140 has Intel Xeon Platinum 8452Y processors; the allocation provided eight physical cores (OS CPUs 0/2/4/6/8/10/12/14), on NUMA node 0, with exclusive placement and actual PBS memory 55 GB. Builds used GCC 11.3.0, CMake 3.24.3 and Open MPI 4.1.4, C++17 Release `-O3 -DNDEBUG`, without fast-math. Placement used `slot:PE=T`, core binding, no oversubscription, `OMP_PLACES=cores`, `OMP_PROC_BIND=close` and dynamic teams disabled. The 1×8 MPI diagnostic says unbound or all available CPUs; warmup thread masks cover the eight allowed CPUs, while measured iterations have no per-thread affinity trace.

Source commit: **`7a6b6e7b04fc6b7a1a9f172503dcf7b6b03e9fd8`**, branch `codex/hybrid-mpi-integration`. The [evidence and reproducibility note](hybrid-vanda-1541184-evidence.md) records the full launcher, source/binary hashes, original archive checksum, direct-sharing instructions and offline reproduction command. Original source-archive/executable bytes are absent, so recorded binary hashes cannot be recomputed from the returned archive. The detailed analysis and original evidence remain preserved separately. This section is prepared for later group integration; Members A/B's sections have not been merged or rewritten.
