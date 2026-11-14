# Standalone OpenMP: evidence and reproducibility

Only benchmark **1536259.stdct-mgmt-02** supplies timings. Local Mac, hybrid and
serial-comparison timings are excluded.

## Evidence records and limits

| Item | Verified record |
|---|---|
| Benchmark | Job 1536259; GN-A40-075; `batch_cpu`; start 10 Nov 2026 11:18:12 UTC |
| Source | `49892e7af795edc3c8adc14ddda21513d4d465c2`, clean submission tree; all 26 recorded source hashes match this Git object |
| Binary SHA-256 | `d089fcdc65793f7b7dfa7fbf14d864e1af249bba983b42456d1ecf149dd95c31` (recorded; executable bytes absent) |
| Submitted source archive SHA-256 | `ca953d640ad9c5ae24e1f454d9f15c27193effa354cdfbc49c2cc65de35a7cd7` (recorded; original source archive absent) |
| Hardware | Intel Xeon Platinum 8452Y; 2×36 cores, 72 logical CPUs, one thread/core reported; 2 NUMA nodes |
| Allocation | Eight cores, one node, **shared**; actual PBS memory 55 GB; OS CPUs 1/3/5/7/17/19/21/23 on NUMA node 1 |
| Software | Linux 5.14.0-427.125.1.el9_4; GCC 11.3.0; CMake 3.24.3 module; GNU OpenMP; C++17 Release `-O3 -DNDEBUG -fopenmp`, no fast-math |
| Runtime | One process; T=1/2/4/8; `OMP_DYNAMIC=FALSE`, `OMP_PLACES=cores`, `OMP_PROC_BIND=close`, `OMP_DISPLAY_AFFINITY=TRUE`; no MPI launcher |
| Sampling | Symmetric problem, N=128/256/512/1024, K=1000; exactly three measurements/configuration, one excluded warmup/configuration; 48 measurements + 16 warmups; shuffled seed 5208 |

All 64 primary JSON results match collection logs. Affinity masks match allocated
CPUs for 48 multithreaded launches (36 measured + 12 warmups); the sixteen
one-thread launches have no explicit mask. Diagnostics match the discrete
sine-mode prediction. All sixteen recomputed summaries match the archived
analysis; this does not independently verify full benchmark grids.

**Benchmark limitation:** terminal `status.json`, PBS completion/exit and benchmark
CTest logs are absent. The allocation records state R, not terminal success.
The complete measurement set is verified; PBS Exit_status 0 is not. Original
source-archive/executable bytes are absent, so their recorded hashes cannot be
recomputed. No rerun is needed to analyze the available measurements.

**Correctness job 1537318.stdct-mgmt-02:** success/exit 0/phase complete on
GN-A40-075; three passing CTest suites and sixteen passing full-grid comparison
receipts at N=10: both problems, T=1/2/4/8, K=31 and convergence tol=1e-10
(480 symmetric / 199 asymmetric iterations). Maximum recorded difference:
4.440892098500626e-16; atol=1e-10/rtol=1e-8. Grid CSVs and per-job source/binary
provenance are absent, preventing independent grid rechecking and exact linkage
to the benchmark binary. These are correctness records, not serial benchmark data.

## Summary and group integration

[`data/openmp-vanda-1536259-summary.csv`](data/openmp-vanda-1536259-summary.csv)
has sixteen rows with seconds, medians, extrema, sample counts and:

- `openmp_1thread_speedup` = median(OpenMP T=1) / median(OpenMP T).
- `openmp_1thread_efficiency_percent` = 100 × speedup / T.
- `speedup_observed_lower/upper` = one-thread minimum / candidate maximum,
  and one-thread maximum / candidate minimum. These are extrema bounds, not
  confidence intervals; the same-baseline T=1 point is anchored at 1.

All three samples are retained. There is no matched serial baseline, so no
serial-relative speedup is calculated. No counters/frequency traces explain
superlinear ratios. Reported L2 is 144 MiB/72 instances (nominal 2 MiB/core);
capacity is not cache residency or proof of bandwidth saturation.

Use [the section](openmp-individual-section.md) and its two PDF captions.
Reconcile OpenMP T=1 versus hybrid 1×1 baselines, persistent versus per-iteration
teams, precomputed versus in-update RHS scaling, and shared GN-A40-075 versus
exclusive CN-140. OpenMP's initial RHS parallel region precedes timing; affinity
printing is enabled here but suppressed in hybrid measurements. Neither measures
application startup. Different jobs/nodes do not establish controlled rankings.

## Original archives and offline reproduction

Obtain the unchanged archives directly from the contributor, outside Git.
Verified SHA-256:

```text
openmp-vanda-results.tar.gz
87252b2ae86028a94a841cdcaf6c78768d04b1ef3b1a95207da0ede27397aeee

serial-openmp-validation-1537318.tar.gz
c99a65ddef1f973b17ef0db7061049bafc39258f7ae1c940eec82980899c9832
```

The benchmark evidence corresponds to
`results/vanda/job-openmp-20261110T111715Z-3619533` in the original Vanda checkout.
With Python 3 and Matplotlib 3.10.6, from the repository root:

```bash
python3 scripts/reproduce_openmp_report.py /path/to/openmp-vanda-results.tar.gz \
  --validation /path/to/serial-openmp-validation-1537318.tar.gz \
  --output /tmp/openmp-report-reproduced
```

Use a new output directory. Only `summary.csv` and the two PDFs are generated;
`--audit-only` verifies evidence without figures. No extraction, contained-script
execution, solver runs or jobs occur. PDF metadata/rendering may vary; numbers
should match exactly.
