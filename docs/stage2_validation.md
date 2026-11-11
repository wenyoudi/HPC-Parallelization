# Serial and parallel validation review

Review date: 11 November 2026. Scope: the available OpenMP, MPI and Vanda hybrid evidence.

## Results

| Implementation | Vanda job | Evidence reviewed | Outcome |
| --- | --- | --- | --- |
| Serial | 1535699 | Existing compilation and CTest log | Passed |
| OpenMP vs serial | 1537318 | 16 recorded comparisons | All reported passing; largest recorded grid difference 4.440892098500626e-16 |
| MPI vs serial | 1539665 | 144 full-grid pairs independently re-compared locally | All passed; maximum absolute difference 0 |
| MPI additional checks | 1539665 | 15 invalid-input and 3 refinement records | All reported passing |
| Hybrid/MPI/serial cross-checks | 1541184 | 486 complete-grid pairs independently re-compared | All passed; maximum absolute difference 0 |

The earlier OpenMP and MPI validation jobs identify Vanda node GN-A40-075.
The hybrid validation job ran on CN-140. The comparison rule
is abs(candidate-reference) <= 1e-10 + 1e-8*abs(reference).
These differences measure agreement between implementations, not error against
the continuous manufactured solution. Small-grid validation timings are not scaling
benchmarks and are not used to infer speedup.

## OpenMP evidence

The supplied archive contains eight comparison JSON files, each with fixed and
convergence cases: N=10, symmetric/asymmetric problems, and 1/2/4/8 threads.
Fixed mode uses 31 iterations. Convergence mode uses tol=1e-10; both implementations
finish after 480 iterations for the symmetric problem and 199 for the asymmetric
problem. Parameters, iteration counts and reported convergence statuses match.
The accompanying CTest log reports local_rows, openmp_numerical and
serial_correctness passing.

Raw grids were written to temporary paths and are not included in the supplied
archive. This review verifies the recorded comparison evidence, not a new
point-by-point OpenMP calculation. The archive also omits source-provenance.json
referenced by job.pbs; the archive checksum identifies the received evidence but
does not independently establish the exact submitted source revision.

The PBS template requests 4 GB and 30 minutes, whereas allocation.json records
8 CPUs, 55 GB and 10 minutes. Use the recorded allocation when describing this job;
the template is not proof of the actual allocation. Its job_state=R is an in-run
snapshot; status.json records successful completion.

## MPI evidence

The archived JSON includes commands, parameters, stdout/stderr, binary hashes and
allocation context. All 144 exported serial/MPI grid pairs were read independently:
shape (N+2 by N+2), finite entries, zero physical boundaries and every numerical
value were checked. The grids agree exactly at the stored precision.
Coverage includes ranks 1/2/3/4/8, N=10 with three ranks, N equal to rank count,
both manufactured problems, odd/even fixed iteration counts, convergence, and
iteration-limit cases. Additional input checks are reviewed from the recorded
exit statuses rather than rerun. The refinement records at N=15/31/63 give error
ratios 4.0181 and 4.0045, consistent with second-order spatial accuracy in those runs.

## Reproduce the evidence review

From the repository root, with Python 3.9 or later:

```bash
python3 scripts/review_stage2.py
```

This command verifies archived file checksums, checks OpenMP record consistency,
and re-compares the MPI and hybrid archive CSV pairs. It requires neither MPI nor a solver build and
does not rerun HPC jobs. The recorded review output is stored alongside the evidence.
Original MPI command paths refer to the submitting contributor's environment;
they are provenance, not portable run instructions.

## Handoff and remaining work

The second-stage review of the supplied OpenMP, MPI and hybrid evidence is complete.
Retain these records for the correctness section of the report. This establishes
agreement for the tested cases, not a proof for all possible inputs. Grid-size
experiments and performance figures remain separate third-stage work.

Evidence was collected by the contributing implementation owners. This review used
AI assistance to inspect and organise records and implement a reproducible checker;
no additional solver or performance runs were performed during the review.

## Vanda hybrid evidence added

The original `hybrid-vanda-results-1541184.tar.gz` is preserved without modification
under `results/validation/stage2/`, with its SHA-256 in provenance.json. The checker
reads it in memory without extracting or executing its contents.

Job 1541184 completed with exit status 0 on CN-140, with 8 allocated CPUs and
55 GB memory. Four CTest entries passed. The distributed receipt records 494
successful checks: 486 numerical comparisons and eight expected-error checks.
The independent review re-compared all 486 grid pairs: hybrid versus serial (194),
hybrid versus MPI (194), and MPI versus serial (98). Shapes, finite values, zero
boundaries, matching parameters and iteration counts were checked; the maximum
stored-grid difference is zero. Runtime records indicate sufficient FUNNELED
thread support and matching rank/thread counts.

Coverage includes symmetric/asymmetric forcing, N=10 with three ranks, N=ranks,
fixed K=1/2/31, convergence and iteration-limit cases, and layouts 1x8/2x4/4x2/8x1.
The eight expected-error outcomes are reviewed from the receipt, not rerun.
The source receipt records clean commit 7a6b6e7b04fc6b7a1a9f172503dcf7b6b03e9fd8.
The submitted source archive is not included; source provenance is recorded rather
than independently reconstructed from these result files.

The original package also contains 96 performance measurements and analysis output.
They are retained to preserve the supplied archive, but this review does not audit
speedup/efficiency calculations. CN-140 differs from the earlier GN-A40-075 node;
measurements across those jobs must not be combined as a controlled scaling series.
