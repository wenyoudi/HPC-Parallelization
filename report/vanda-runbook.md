# Vanda hybrid integration: submission and evidence

Current branch: **`codex/hybrid-mpi-integration`**, based on
`feature/openmp-hybrid` at `2ea8a5a`. Use a fresh Vanda checkout for this branch;
keep Person A's directory and existing OpenMP/MPI result directories unchanged.

## Implementation and evidence status

B's `feature/mpi-poisson` commit `1756eff` is pinned verbatim under
`references/mpi/`. Its public decomposition and full-row blocking halo exchange
are directly reused by `src/hybrid_poisson.cpp`. A's unchanged serial source is
under `references/serial/`. B's CMake/scripts are not blindly merged.
`cmake/DistributedSolvers.cmake` builds separate serial, MPI-only and hybrid
targets with C++17 Release -O3, without fast-math. Root OpenMP code/kernels and
existing result artifacts are unchanged.

B's upstream Vanda receipt for job `1539665.stdct-mgmt-02`, GN-A40-075, reports
162/162 passing cases; it was inspected directly on B's branch. Its benchmark
results and complete grid CSVs remain there, untouched. The earlier user-verified
communication smoke job 1536986 passed 1/2/4 ranks on GN-A40-074 with the
single-node workaround. Neither record is a hybrid result.

The hybrid has passed **494 local checks** on Apple M4 using Clang 21, MPICH
4.3.2 and LLVM OpenMP: 486 full-grid comparisons plus eight expected-error checks.
Hybrid was compared with serial and MPI-only at matching ranks, for both sine
problems, uneven N=10/ranks=3, N=ranks, fixed counts, convergence and exhausted
convergence. Maximum observed grid difference was 0.0 on that local build.
Residual/error were independently recomputed from gathered grids. Runtime team
sizes and MPI FUNNELED support passed. Four CTest entries passed too. See
`results/local/hybrid-integration-20261111/` for summary/hashes and full evidence.
These are local correctness tests, **not Vanda hybrid measurements**.

The user reported hybrid job **1540875** on CN-151 passing all four CTest
suites, MPI smoke at 1/2/4/8 ranks, and the first 312 distributed numerical
comparisons. Check 313 stopped before solver execution/grid comparison because
a repeated `qstat -f` allocation query timed out. This is an infrastructure
failure and partial validation, **not a completed Vanda hybrid pass**. Preserve
that job's evidence. The allocation-query fix below requires a new full run;
it does not skip or relax any numerical checks.

## Rerun after the allocation-query fix

In your authenticated Vanda shell, `cd` to the **existing isolated hybrid
clone** used for job 1540875 (leave Person A's and OpenMP directories untouched).
Confirm the branch is `codex/hybrid-mpi-integration` and the working tree is
clean, then run:

```bash
git branch --show-current
git status --short
git pull --ff-only origin codex/hybrid-mpi-integration
bash -l "$PWD/scripts/setup_vanda.sh"
VANDA_MPI_LAUNCHER=single-node \
  bash -l "$PWD/scripts/submit_vanda.sh" hybrid-validate
validation_dir=$(cat results/vanda/latest-hybrid-validate.txt)
validation_id=$(cat "$validation_dir/job-id.txt")
qstat "$validation_id"
```

If the branch/working tree check differs, preserve those changes before updating;
do not reset or remove old results. Submission creates a new source archive and
job directory. It does not reuse or overwrite job 1540875. After completion,
inspect `status.json` and `distributed-validation/validation.json` using section 2
below; require the complete 494-check pass before submitting benchmarks.
Archive/download the new evidence using section 5.

## 1. Create a new isolated checkout on Vanda

In your already authenticated Vanda SSH shell:

```bash
work=$(mktemp -d "$HOME/project3-hybrid-vanda.XXXXXXXX")
git clone --single-branch --branch codex/hybrid-mpi-integration \
  https://github.com/wenyoudi/HPC-Parallelization.git "$work/repo"
cd "$work/repo"
printf 'New hybrid checkout: %s\n' "$PWD"
bash -l "$PWD/scripts/setup_vanda.sh"
```

Setup loads/rechecks the exact user-verified modules:

```bash
module load GCC/11.3.0
module load CMake/3.24.3-GCCcore-11.3.0
module load OpenMPI/4.1.4-GCC-11.3.0
```

It also checks Python >=3.8 for the existing test/data scripts and the PBS paths
`/opt/pbs/bin/qsub`/`qstat`. It only inventories/checks the login environment;
compilation, numerical tests and benchmarking all run inside PBS allocations.
No password, MFA code or private key belongs in scripts, Git or returned logs.
The agent's session cannot reuse your authenticated terminal; run these commands
manually and return the resulting evidence archive.

## 2. Submit hybrid correctness validation

```bash
VANDA_MPI_LAUNCHER=single-node \
  bash -l "$PWD/scripts/submit_vanda.sh" hybrid-validate
validation_dir=$(cat results/vanda/latest-hybrid-validate.txt)
validation_id=$(cat "$validation_dir/job-id.txt")
qstat "$validation_id"
```

After it finishes:

```bash
cat "$validation_dir/status.json"
python3 - "$validation_dir/distributed-validation/validation.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
print('site:', r['site'], 'passed:', r['passed'],
      'checks:', len(r['checks']), 'passing:', sum(c['passed'] for c in r['checks']))
PY
qstat -xf "$validation_id" | sed -n '/job_state =/p; /Exit_status =/p'
```

Require `success:true`, `exit_status:0`, `phase:complete`, a Vanda validation
receipt with `passed:true`, and all 494 checks passing on the default eight-core
allocation. Missing status while queued/running is not a pass. The job requests
one node, eight CPUs/eight MPI slots, 4 GB memory, one hour and shared placement.
The longer hybrid walltime accommodates direct comparisons with both serial and
MPI-only; B's successful upstream queue allocation also allowed one hour.
Site-normalized resources (including any memory change to 55 GB) are captured
from actual PBS records; they are not assumed to match the request text.

At job startup, `pbs_allocation.py --refresh` queries `qstat -f "$PBS_JOBID"`
and verifies running state, single-node identity, actual `Resource_List.ncpus`,
OS affinity and visible physical-core capacity. Scheduler timeouts/nonzero
responses get at most three attempts, each with a 15-second timeout and 1/2-second
delays (48-second total timeout budget). Exhaustion, a missing scheduler, or an
invalid successful response fails the job; requested CPUs are never substituted.

The verified, filtered record is saved once as `allocation.json`, including its
verification time, nodefile SHA-256 and query-attempt count. The job exports
`VANDA_ALLOCATION_SNAPSHOT` and `VANDA_ALLOCATION_SHA256` to discovery, smoke,
validation, every child comparison and benchmarking. Each consumer verifies the
checksum, job ID, host and nodefile against the current job and rechecks live
affinity/physical-core limits. A narrower current cpuset lowers the available
budget; a widened/unverifiable mask or changed/corrupt cache fails. Rank × thread
limits and all smoke binding checks remain active. Consumers never re-query PBS
or fall back to requested resources if the supplied snapshot is invalid.

Compute-node inventory also uses this record instead of extra scheduler RPCs;
the login-node setup inventory remains separate. Standalone Vanda validation
without a pre-exported snapshot performs its initial verification once and saves
`distributed-validation/allocation-snapshot.json` (inside its chosen output
directory) for all its children. The validation report records the snapshot path
and checksum. Do not manually point a new job at an old job's snapshot.

The job builds separate real serial/MPI/hybrid executables in its own `build/`,
runs CTest and communication/binding smoke, then runs the complete matrix.
The hybrid uses B's unscaled f and forms h²*f inside each stencil, matching both
baselines. It checks FUNNELED/main-thread entry, keeps every MPI call outside
worker regions, verifies equal effective teams across ranks, and joins workers
before communication/swaps. Final halos are refreshed before global diagnostics;
nonuniform Gatherv excludes halos and inserts physical boundaries once.

Evidence includes full reference/candidate CSV grids, both problem types,
pointwise atol=1e-10/rtol=1e-8 checks, independently recomputed residual/error,
iteration counts, convergence/max-update values, non-convergence and no-hang
failure cases. Candidate and MPI-reference launcher counts are both checked.
The original OpenMP tests and A's serial tests also run without source changes.

## 3. Single-node launcher and resource controls

Default `single-node` mode implements the user-verified pattern:

```bash
mpirun --mca plm rsh --mca ras ^tm --host COMPUTE_HOST:ACTUAL_PBS_CPUS \
  --np R --map-by slot:PE=T --bind-to core --nooversubscribe --report-bindings PROGRAM
```

Host/slots are derived on the compute node from the verified allocation and
`qstat -f`, not hard-coded to four/eight or inferred from total machine cores.
Every launch requires R*T <= actual PBS CPUs, process cpuset size and visible
physical-core capacity. Smoke checks disjoint rank masks, allocation containment
and same-node execution. Thread placement uses OMP_PLACES=cores,
OMP_PROC_BIND=close and OMP_DYNAMIC=FALSE. Inspect actual binding diagnostics;
setting variables alone is not evidence that placement was honored.

The original PBS/hostfile alternative remains selectable:

```bash
# Optional separate experiment; no silent launcher fallback:
VANDA_MPI_LAUNCHER=pbs bash -l "$PWD/scripts/submit_vanda.sh" hybrid-validate
```

For just the environment smoke with four requested CPUs:

```bash
VANDA_CPUS=4 VANDA_MPI_LAUNCHER=single-node \
  bash -l "$PWD/scripts/submit_vanda.sh" mpi-smoke
```

Smoke records fitting and allocation-excluded ranks in `plan.json`; exclusions
are not passes. Full validation/benchmark jobs require at least eight CPUs for
existing 1/2/4/8-thread tests. `mpi-validate` is also available for B's MPI-only
solver versus serial; `serial-compare` checks serial versus unchanged OpenMP.

## 4. Submit hybrid benchmarking only after validation succeeds

```bash
VANDA_MPI_LAUNCHER=single-node \
  bash -l "$PWD/scripts/submit_vanda.sh" hybrid
benchmark_dir=$(cat results/vanda/latest-hybrid.txt)
benchmark_id=$(cat "$benchmark_dir/job-id.txt")
qstat "$benchmark_id"
```

This job validates again in its own allocation, so it cannot time unvalidated
binaries or reuse a local receipt. Timing is gated on site=Vanda, successful
checks, exact serial/hybrid hashes, selected launcher and coverage of every
rank/thread configuration. Any failed correctness check stops the job.

Default workload: N=128/256/512/1024, fixed K=1000. Configurations:
1x1,2x1,4x1,8x1,4x2,2x4,1x8. The equal-eight-worker comparison is
8x1/4x2/2x4/1x8. Each has one excluded warm-up and three measured repetitions.
A's true serial baseline is rebuilt with the same compiler/flags and measured
on that same node/allocation through a one-rank/one-core-bound launch.
There are **96 measured rows** and **32 warm-ups** including serial.
MPI startup is outside each program's internal solve timer. Iteration exchanges,
local updates/joins/swaps and necessary convergence reductions are inside;
initialization, team probing, final diagnostics, gathering/export are outside.
No solution CSV is exported during timing. Hybrid thread-affinity printing runs
in excluded warm-ups only; MPI binding reports are retained for every launch.

The benchmark default is exclusive placement to reduce contention. If the site
requires sharing, explicitly use `VANDA_PLACEMENT=shared` and keep those results
separate. Never pool local data, earlier B benchmark runs, different placements,
node allocations, modes or iteration counts. New hybrid benchmark evidence is
not claimed until this job actually succeeds and its raw data are inspected.

After completion:

```bash
cat "$benchmark_dir/status.json"
cat "$benchmark_dir/analysis/summary.csv"
wc -l "$benchmark_dir/measurements/raw.jsonl"
qstat -xf "$benchmark_id" | sed -n '/job_state =/p; /Exit_status =/p'
```

## 5. Source provenance and result retrieval

Submission requires a clean feature checkout and records Git commit/status on
the login node. It freezes a checksummed `source.tar.gz`; the compute job verifies
and builds that snapshot without invoking Git. A later checkout update cannot
change a queued job's source. Job directories and output files are never reused.

After the validation/benchmark jobs finish, from this new checkout:

```bash
archive="$HOME/project3-hybrid-vanda-results-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar --exclude='*/build' --exclude='*/source' -czf "$archive" results/vanda
printf 'Download this exact file: %s\n' "$archive"
```

The archive retains job scripts/IDs/status, source snapshot/provenance, build
commands/cache, hardware/modules/PBS allocation, CTest details, all comparison
CSVs/metrics/stdout/stderr, raw benchmark/warm-up JSONL and median CSV.
Binaries/unpacked source are excluded. No full PBS Variable_List is collected.

Download from your Mac (replace account and filename with your session values):

```bash
scp YOUR_NUSNETID@vanda.nus.edu.sg:~/project3-hybrid-vanda-results-TIMESTAMP.tar.gz /tmp/
```

Return that archive here. Extract into this integration checkout, preserving
existing results, and generate figures from the actual new benchmark directory:

```bash
tar -xzf /tmp/project3-hybrid-vanda-results-TIMESTAMP.tar.gz
MPLCONFIGDIR=/tmp/project3-mpl /opt/anaconda3/bin/python scripts/analyze.py \
  results/vanda/job-hybrid-TIMESTAMP-PID/measurements/raw.jsonl \
  --output report/generated/vanda-hybrid-TIMESTAMP --plots
```

## Scheduler failures versus application failures

The prior MPI-smoke job 1535955 reached a compute node but failed on a missing
Git command; provenance was moved to submission and compute jobs no longer need
Git. Earlier OpenMP job 1535954 was held after 21 launch attempts with exit -3
and no job log. Its cause was not established; changing shared/exclusive placement
was a controlled retry, not a diagnosis. Do not relabel either as a solver pass.

If a new job is held before producing `job.log`, retain its generated job/provenance
and inspect normalized scheduler fields:

```bash
qstat -fx NEW_JOB_ID | sed -n '/job_state =/p; /Hold_Types =/p; /comment =/p; /run_count =/p; /Exit_status =/p; /Resource_List/p; /exec_host =/p; /exec_vnode =/p'
# If accessible:
tracejob NEW_JOB_ID
```

Ask NUS HPC support to inspect launch/server/MOM records for that ID/time if it
recurs. Do not repeatedly release system holds or guess larger allocations.
Queue/project flags can be appended to submission commands if your account
requires them; no queue/account name is invented by these scripts.
