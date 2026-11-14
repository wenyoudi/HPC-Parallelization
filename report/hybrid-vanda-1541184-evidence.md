# Hybrid contribution: evidence and reproduction

This handoff contains one report section, two main-report PDFs, one compact
summary CSV and one offline reproduction script. Insert the section after the
group's serial/MPI material; use the two PDFs with their supplied captions.
No merge with Members A/B's work has been performed.

## Verified experiment

| Item | Record |
|---|---|
| Vanda job / node / queue | `1541184.stdct-mgmt-02` / CN-140 / `batch_cpu`; completed successfully |
| Benchmark date | 11 November 2026, starting 08:36:29 UTC |
| Source | `codex/hybrid-mpi-integration`, commit `7a6b6e7b04fc6b7a1a9f172503dcf7b6b03e9fd8`; clean submission tree |
| Hardware | Intel Xeon Platinum 8452Y; 2 sockets × 36 cores, 72 logical CPUs with one thread/core as reported; 2 NUMA nodes |
| Allocation | One node, eight physical cores; OS CPUs 0/2/4/6/8/10/12/14 on NUMA node 0; exclusive placement; actual PBS memory 55 GB |
| Software | Linux 5.14.0-427.134.1.el9_4; GCC 11.3.0; CMake 3.24.3; Open MPI 4.1.4; GNU OpenMP |
| Build | C++17 Release `-O3 -DNDEBUG`, `-fopenmp` for hybrid; no fast-math; matched serial rebuilt in the same job |
| Correctness | Four CTest suites; MPI smoke at 1/2/4/8 ranks; **494/494 distributed checks** (486 numerical comparisons + eight expected-error cases); 972 saved grids rechecked, maximum reference/candidate difference 0.0 at atol=1e-10/rtol=1e-8 |
| Timing protocol | Symmetric problem, N=128/256/512/1024, fixed K=1000; seven hybrid layouts plus serial; one excluded warmup and **three measured repetitions per configuration**; 96 timings and 32 warmups; measured order shuffled with seed 5208 |

Hybrid timing is the maximum rank-local solve-loop interval, including halo
exchange, local updates, joins and swaps. Process launch, initialization, team
probing, final timing reduction, diagnostics, gathering and output are excluded.
Serial uses a monotonic clock around its solve loop. Fixed K does not imply
convergence. Reported values are medians; ranges are extrema, not confidence
intervals. These are one-node results with no controlled performance comparison
against standalone MPI-only/OpenMP-only executables.

Launch pattern (R ranks, T threads/rank):

```bash
mpirun --mca plm rsh --mca ras ^tm --host CN-140:8 --np R \
  --map-by slot:PE=T --bind-to core --nooversubscribe --report-bindings PROGRAM
```

`OMP_PLACES=cores`, `OMP_PROC_BIND=close`, `OMP_DYNAMIC=FALSE`; R×T≤8.
Startup verifies actual PBS resources; subsequent checks use a job-bound
checksummed snapshot. Rank binding reports are explicit for 112 launches;
the sixteen 1×8 launches say unbound or all available processors. Threaded
warmups cover the eight allowed CPUs; measured iterations have no per-thread
affinity trace. No cache/bandwidth/instruction/frequency counters were collected.

## Summary definitions

[`data/hybrid-vanda-1541184-summary.csv`](data/hybrid-vanda-1541184-summary.csv)
has 32 rows (four N × eight configurations), with times in seconds, sample count,
median/minimum/maximum, and clearly separate metrics:

- `hybrid_1x1_speedup` = median(hybrid 1×1) / median(hybrid R×T).
- `hybrid_1x1_efficiency_percent` = 100 × that speedup / (R×T).
- `serial_relative_speedup` = median(same-job serial) / median(configuration).

Same-implementation columns are blank for the separate serial executable.
Efficiency is a timing ratio, not utilization; superlinear ratios do not prove
sustainable greater-than-100% computational efficiency. 8×1 has the lowest
eight-worker median at N=128/256; 1×8 at N=512/1024. Mixed layouts are competitive
at larger N but have no lowest median in this measured set. All layouts are the
hybrid executable. Larger-grid ranges overlap and only three samples are available.

## Original evidence and offline reproduction

Obtain **`hybrid-vanda-results-1541184.tar.gz` directly from the hybrid contributor**
through the group's agreed file-sharing method. The original archive is preserved
separately and is deliberately not uploaded to GitHub. Verify its SHA-256:

```text
5ed7283d928154ef58581a959a1e5d107c8b31737dc570927bc2505555e3911b
```

It contains status, allocation, source provenance, build/validation logs,
complete validation grids, raw/warmup JSONL and binding logs. Recorded binary
hashes agree between validation and timing metadata:

- Hybrid: `3328716756d275662bc134800ac6bd69a125e2aef20c21ccd1245cd7bd9bb646`
- Serial: `660531c78de21f66fb0f64e857780ed40bb0ebccfca75909c006f54416d53c96`

The recorded submitted source-archive hash is
`9eed22186e2e851d665ed88670d8cccba0bc4f686fb52060c26f6a35dc038804`.
Original source-archive/executable bytes are absent from the result archive,
so those hashes cannot be independently recomputed from it. The prior audit
checked 34 recorded source hashes against the pinned Git object. No new cluster
job is needed to integrate or reproduce this handoff.

Using Python 3 with Matplotlib 3.10.6 (the original plotting version), from the
repository root:

```bash
python3 scripts/reproduce_hybrid_report.py /path/to/hybrid-vanda-results-1541184.tar.gz \
  --output /tmp/hybrid-report-reproduced
```

The output directory must be new. The script verifies the archive checksum and
record linkage, then writes only `summary.csv`, `eight_workers.pdf` and
`speedup.pdf`. It reads evidence without extracting it, running solvers or
submitting jobs. Numeric values should match the committed CSV exactly;
PDF timestamps/rendering can vary with plotting dependencies. The full detailed
analysis and other figure formats remain available separately from the contributor.
