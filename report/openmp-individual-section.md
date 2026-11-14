# Standalone OpenMP implementation and performance

## Design and numerical correctness

The OpenMP solver keeps a persistent parallel region around the Jacobi iteration loop, amortizing team entry across K updates. Static scheduling assigns independent output rows to threads, each traversing contiguous columns. Double buffering ensures every update reads only the previous iterate. The implicit work-sharing barrier completes writes before a `single` region swaps pointers; its barrier publishes the new buffers and common stopping decision. Each cell has one writer, preventing stencil data races. Convergence mode resets and computes `reduction(max:max_update)` before the synchronized stop test. Fixed mode uses a separate kernel without update-difference calculations or convergence reductions. The scaled RHS h²f is initialized before timing.

Development-Mac records show 13 passing numerical test groups, a row-kernel test and an AddressSanitizer/UndefinedBehaviorSanitizer test pass; no Mac timings enter this analysis. Separately, Vanda correctness job **1537318** completed successfully on GN-A40-075: three CTest suites and **16 serial/OpenMP full-grid comparison receipts** passed, covering both manufactured problems, 1/2/4/8 threads, fixed K=31 and convergence at N=10. The largest recorded grid difference was **4.44×10⁻¹⁶**, within atol=1e-10/rtol=1e-8. Exported grids and per-job source/binary hashes are absent from that archive, preventing independent grid rechecking and definitive linkage to the benchmark binary.

## Benchmark methodology

Benchmark job **1536259** recorded N=128/256/512/1024, T=1/2/4/8 and fixed **K=1000** on GN-A40-075, using an Intel Xeon Platinum 8452Y and eight allocated cores on NUMA node 1. PBS placement was **shared**, not exclusive. GCC 11.3.0 compiled C++17 Release with `-O3 -DNDEBUG -fopenmp`, without fast-math. Runtime settings were `OMP_DYNAMIC=FALSE`, `OMP_PLACES=cores` and `OMP_PROC_BIND=close`; multithreaded affinity logs match the allocated CPUs.

Each configuration has **exactly three measured repetitions**, preceded by one excluded warmup: 48 measurements and 16 warmups. Measured order was shuffled with seed 5208; no samples were removed. The monotonic-clock interval includes the persistent region's entry/join, iteration updates, barriers and swaps. Allocation, RHS initialization, final diagnostics, CSV export and application startup are excluded. The recovered records establish the complete measurement set, but contain no terminal PBS status or benchmark CTest log; scheduler-level completion is therefore not independently verified.

## Strong-scaling results

For each N, **S_OMP(T)=median(t_OMP,1)/median(t_OMP,T)** and **E_OMP(T)=100S_OMP(T)/T percent**. These compare the same OpenMP executable, not a separate serial program. The following runtimes are medians in milliseconds; full minima/maxima and all efficiencies are in the [summary CSV](data/openmp-vanda-1536259-summary.csv).

| N | T=1 (ms) | T=2 (ms) | T=4 (ms) | T=8 (ms) | S_OMP(8) | E_OMP(8), % |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 10.726 | 6.835 | 4.977 | 4.310 | 2.489 | 31.1 |
| 256 | 43.975 | 23.281 | 14.086 | 8.942 | 4.918 | 61.5 |
| 512 | 246.368 | 119.443 | 49.709 | 29.271 | 8.417 | 105.2 |
| 1024 | 1183.302 | 509.809 | 252.295 | 129.133 | 9.163 | 114.5 |

**Eight threads have the lowest median at every measured size. Larger grids benefit more from threading**, consistent with more useful work per synchronization. At N=128, increasing from four to eight threads reduces the median only from 4.977 to 4.310 ms, whereas at N=1024 it falls from 252.295 to 129.133 ms. This supports size-dependent overhead amortization, without isolating its cost.

## Interpretation and limitations

The N=512/1024 results exhibit same-implementation superlinear ratios. At N=1024, the extrema-based eight-thread ratio spans **8.789–9.262**; these sensitivity bounds are not confidence intervals. Greater aggregate private-cache capacity is plausible: N=512's three arrays occupy about 6.05 MiB, or roughly 1.5 MiB per four-thread row partition, compared with the reported nominal 2 MiB L2/core. Capacity alone does not establish cache residency. Cache bandwidth, CPU frequency/placement and interference from other jobs also remain hypotheses; no relevant counters or frequency traces were collected. Ratios above 100% are not CPU utilization or proof of sustainable superlinear efficiency.

Only three samples and one shared allocation were measured. One-thread launches lack explicit affinity-mask lines, and affinity diagnostics were enabled during collection. Fixed K does not establish convergence: benchmark error/residual values match discrete sine-mode predictions, but analytical error remains substantial. No matched serial timings exist in the benchmark; correctness-job timings must not be repurposed as a performance baseline.

## Figures and reproducibility

1. **[Runtime](figures/vanda-openmp-1536259/openmp_runtime.pdf):** Median solve time versus T for each N on Vanda, K=1000; three measured repetitions, with observed minimum–maximum whiskers. Panel time scales differ.
2. **[Speedup](figures/vanda-openmp-1536259/openmp_speedup.pdf):** Ratios of three-repetition medians relative to OpenMP one thread at matching N/K; dashed S=T reference.

Source commit: **`49892e7af795edc3c8adc14ddda21513d4d465c2`**. The [evidence note](openmp-vanda-1536259-evidence.md) records archive checksums, verification limits and offline reproduction. For group integration, retain this baseline separately from hybrid 1×1 and serial-relative metrics. OpenMP precomputes h²f and uses a persistent team; hybrid scales f inside updates and joins workers each iteration. Different nodes, shared versus exclusive allocations and timing details prevent a controlled direct OpenMP/hybrid runtime comparison.
