# Vanda validation and benchmarking — verified environment, 10 November 2026

## Verified facts and access

The user successfully loaded and checked these exact modules on Vanda:

```bash
module load GCC/11.3.0
module load CMake/3.24.3-GCCcore-11.3.0
module load OpenMPI/4.1.4-GCC-11.3.0
```

GCC and the MPI wrapper use GCC 11.3.0; `mpirun` is Open MPI 4.1.4. PBS commands are `/opt/pbs/bin/qsub` and `/opt/pbs/bin/qstat`. Person A's serial compilation/correctness job `1535699.stdct-mgmt-02` completed with Exit_status 0, **as reported by the user**; this is not an OpenMP result and its logs have not been inspected in this chat.

On 10 November the agent's network-enabled SSH probe reached Vanda but could not authenticate using its available session. The desktop tool cannot access Terminal. The user's authenticated terminal remains usable by the user; no password, MFA code or private key needs to be shared. The commands below run from that existing SSH session. No Vanda OpenMP/MPI-smoke job has yet been submitted by the agent, and no new runtime is claimed.

`scripts/vanda-env.sh` loads these exact modules and checks tool versions both before submission and inside each job. It also checks Python >=3.8, required by the existing test/data scripts. If that preflight fails, inspect `module avail Python` on Vanda and return the output; no unverified Python module name is assumed. CMake Release uses C++17 and `-O3 -DNDEBUG`, without fast-math. Existing OpenMP solver/kernel/test logic is unchanged.

Preparation checks performed locally: CMake 3.24.3 configured and built Release targets; both CTest entries passed (the local-row check and 13 numerical groups). The MPI smoke source compiled against the local MPI installation without being launched. Three allocation-fixture tests and two data-pipeline groups passed; shell/Python syntax checks passed. These results do not claim GCC 11.3/Open MPI 4.1.4 execution on Vanda.

## Verified single-node launch workaround and pending solver integration

The user reports that **PBS job 1536986 completed on GN-A40-074 with Exit_status 0** using 1, 2 and 4 ranks. `MPI_Init_thread`, `MPI_Allreduce` and `MPI_Sendrecv` passed with this single-node command pattern:

```bash
mpirun --mca plm rsh --mca ras ^tm --host "$(hostname):4" -np 4 PROGRAM
```

This is communication/environment evidence, **not MPI Poisson or hybrid numerical validation**, and does not establish an 8-rank or bound-thread result. The returned smoke logs have not been inspected here. Person B's MPI source is not yet available, as confirmed by the user. Do not recreate it: actual halo exchange, distributed residual/gather, FUNNELED call discipline and hybrid integration remain pending that source.

`scripts/mpi_launcher.py` makes the workaround the default `single-node` mode. It uses the current verified compute hostname and **`Resource_List.ncpus` from `qstat -f`** as `--host HOST:SLOTS`, rather than hard-coding 4 or using the host's total CPU count. It checks `ranks*threads` against that allocation, the process cpuset, and visible physical cores when Linux topology is available. It adds explicit `--map-by slot:PE=THREADS --bind-to core --nooversubscribe --report-bindings`. These binding settings need their own successful Vanda evidence. Only one allocated compute node is supported; this is not a multinode workaround.

The previous scheduler/hostfile launch remains available as `VANDA_MPI_LAUNCHER=pbs`. Launcher selection is saved in the PBS script and propagated to each smoke, validation and benchmark process; failed launches are not silently retried with a different mode. Smoke `plan.json` records executed and allocation-excluded rank counts.

In your existing isolated Vanda feature checkout:

```bash
git status --short
git pull --ff-only origin feature/openmp-hybrid
bash -l "$PWD/scripts/setup_vanda.sh"
# Reproduce the four-CPU single-node setting, with additional binding checks:
VANDA_CPUS=4 VANDA_MPI_LAUNCHER=single-node \
  bash -l "$PWD/scripts/submit_vanda.sh" mpi-smoke
# Alternative: original PBS/hostfile launcher, only if you want to test it:
# VANDA_CPUS=4 VANDA_MPI_LAUNCHER=pbs bash -l "$PWD/scripts/submit_vanda.sh" mpi-smoke
# Independent serial/OpenMP comparisons; writes a new job directory:
bash -l "$PWD/scripts/submit_vanda.sh" serial-compare
```

`VANDA_CPUS` sets the requested PBS allocation, while actual runtime slots always come from PBS. OpenMP/serial comparison jobs still require at least eight CPUs for the existing 1/2/4/8-thread tests. MPI smoke supports smaller allocations and records exclusions (for example rank 8 on a four-CPU job). Check each new `status.json`, `mpi-smoke/plan.json`, `results.jsonl` and binding logs. Previous OpenMP result directories and numerical solver code are untouched.

### Serial reference and prepared hybrid workflow

Person A's unmodified serial implementation is pinned from `serial-baseline-and-validation` commit `0e20822ffda1d0493a1f1564438fbe8f58d0b1a2` under `references/serial/`, with file hashes in `UPSTREAM.json`. It is compiled separately with the same C++17 Release compiler/flags; its branch/source are not edited. `serial-compare` runs its existing tests and compares its full numerical grid with the existing OpenMP solver for both problems, fixed/convergence modes and 1/2/4/8 threads. The tool handles `n` versus `N` and passes only options appropriate to each mode. Local CMake/CTest checks and all 16 serial/OpenMP comparison cases passed; this does not replace the new Vanda comparison job.

**Before Member B's source arrives:** `mpi-validate`, `hybrid-validate` and `hybrid` reject submission with a dependency message. The required build adapter is documented in `cmake/README.md`; there is deliberately no stub `DistributedSolvers.cmake` or replacement MPI solver. Once actual integration defines real `mpi` and `hybrid` targets, these prepared commands apply:

```bash
# Pending actual source integration; not runnable yet:
bash -l "$PWD/scripts/submit_vanda.sh" mpi-validate
bash -l "$PWD/scripts/submit_vanda.sh" hybrid-validate
# Only after correctness succeeds:
bash -l "$PWD/scripts/submit_vanda.sh" hybrid
```

The prepared jobs build serial/MPI/hybrid in the same fresh job directory, run CTest and binding/communication smoke, then use `scripts/validate_distributed.py`. It compares pointwise solutions, iteration counts, convergence/update values, boundaries, final residual and analytical error against serial with atol=1e-10/rtol=1e-8. Cases include N=10/ranks=3, N=ranks, first/last ranks, positive odd/even fixed counts 1/2/31, convergence and the asymmetric problem. Rank/thread cases exceeding the actual allocation are explicitly recorded as not run. Member B's source must also be inspected for final-halo refresh, global reductions, safe nonuniform gather and proper main-thread-only FUNNELED MPI calls; the numerical evidence alone does not prove call discipline.

The hybrid benchmark is gated on successful numerical evidence for **the exact serial/hybrid binary hashes, selected launch mode and every benchmark rank/thread configuration**. It reruns validation in the benchmark allocation before any timing. Its fixed-K matrix includes strong-scaling configurations and 8x1/4x2/2x4/1x8, with one warm-up and three recorded repetitions per grid/configuration. Every launch checks the actual PBS core budget. The true serial baseline is rerun on that same node/allocation with the same N/K/problem/build flags and bound through a one-rank/one-core launch; MPI startup stays outside the solver's internal `solve_seconds`. Raw serial samples are retained with the hybrid samples for median serial-baseline speedup/efficiency. Hybrid OpenMP affinity diagnostics are enabled in excluded warm-ups and disabled in measured solves, so first-team diagnostic printing cannot contaminate the iteration timer; MPI binding reports remain saved for every launch.

Person A's serial code forms h²*f inside each update; the existing OpenMP code pre-scales RHS before timing. Preserve both existing implementations/results, and align/document MPI/hybrid arithmetic with the serial baseline during actual integration before publishing speedups. No hybrid runtime, numerical pass or efficiency result is currently claimed.

## First submission failures and fixes

The user reported two distinct outcomes; neither is a passing Vanda numerical/MPI test:

- **1535955, MPI smoke:** started on CN-077 with 8 CPUs and the confirmed modules, then failed before compilation at `git: command not found`, exit 127, phase `allocation`. This is a confirmed compute-node Git dependency bug.
- **1535954, OpenMP validation:** held with `run_count=21`, `Exit_status=-3` and `job held, too many failed attempts to run`, with no job log. PBS normalized the request to `1:ncpus=8:mpiprocs=1:ompthreads=8:mem=55GB`, `place=excl`. This is a scheduler launch/hold outcome, not a solver test failure; the reported fields do not establish its root cause.

Git commit and working-tree status are now saved by `submit_vanda.sh` on the **login node**, alongside `source-provenance.json` and a SHA-256-identified `source.tar.gz`. Submission requires a clean checkout. Each compute job verifies the archive and builds from its frozen source snapshot, with no Git invocation. Benchmarks read the saved provenance instead of querying Git. Updating the checkout after submission does not alter the source of queued jobs. Preserve these files with the results.

Validation and smoke now request **shared** placement: eight CPU workers do not require node exclusivity for correctness/launch checks. `place=shared` is standard PBS syntax; site vnode policy can still override sharing. See the [PBS reference guide](https://2021.help.altair.com/2021.1/PBSProfessional/PBSReferenceGuide2021.1.pdf). Benchmarks retain exclusive placement by default to reduce contention; `VANDA_PLACEMENT=shared` or `excl` can override it explicitly. Do not pool performance data from different placements.

This change is a controlled smaller request, **not confirmation that exclusivity caused the hold**. The requested memory remains 4 GB; the observed 55 GB normalization is recorded as a site-applied value, not silently treated as our request or diagnosed as the cause. New successful job/allocation evidence is required.

### Update the existing isolated checkout and retry

In the existing Vanda clone created for this contribution, leaving Person A's directory alone:

```bash
git status --short
git branch --show-current
git pull --ff-only origin feature/openmp-hybrid
bash -l "$PWD/scripts/setup_vanda.sh"
bash -l "$PWD/scripts/submit_vanda.sh" openmp-validate
bash -l "$PWD/scripts/submit_vanda.sh" mpi-smoke
```

Expect branch `feature/openmp-hybrid`. If there are local edits, preserve/commit them before submission; do not reset them. These commands create fresh job directories and IDs; they do not release, modify, cancel or overwrite jobs 1535954/1535955. Follow the status checks below using the new IDs. No benchmark should be launched until correctness succeeds.

If the new validation is held before a job log appears, preserve the normalized scheduler fields from the new ID (substitute its actual value):

```bash
qstat -fx NEW_JOB_ID | sed -n '/job_state =/p; /Hold_Types =/p; /comment =/p; /run_count =/p; /Exit_status =/p; /Resource_List/p; /exec_host =/p; /exec_vnode =/p'
# If available to your account:
tracejob NEW_JOB_ID
```

Keep the generated `job.pbs`, submission provenance and scheduler diagnostics; ask NUS HPC support to inspect server/MOM and launch-hook/prologue records for that ID/time. Do not repeatedly release a system hold or guess a different memory/node request without evidence. The agent has not inspected those cluster logs or established the hold's cause.

## 1. Create a completely separate checkout

Run in your authenticated **Vanda SSH shell**, not inside Person A's directory:

```bash
work=$(mktemp -d "$HOME/project3-openmp-vanda.XXXXXXXX")
git clone --single-branch --branch feature/openmp-hybrid \
  https://github.com/wenyoudi/HPC-Parallelization.git "$work/repo"
cd "$work/repo"
printf 'Your separate checkout: %s\n' "$PWD"
bash -l "$PWD/scripts/setup_vanda.sh"
```

Keep this shell open in the new checkout. `mktemp` creates a fresh directory every time. No `git pull`, checkout, clean, rebuild or write is performed in Person A's directory. Setup only loads/verifies modules, inventories the login environment and records a checkout marker; it does **not** compile, test or benchmark on the login node. The submission script requires this marker and the feature branch. Setup evidence is under `results/vanda/setup-*`.

If the repository cannot be cloned on Vanda, create a source archive locally (`git archive --format=tar.gz -o /tmp/project3-source.tar.gz feature/openmp-hybrid`) and transfer it, but the normal scripts require a Git checkout/branch marker. Prefer cloning; report a Git/network failure before attempting a source-only adaptation.

## 2. Submit OpenMP validation first

```bash
bash -l "$PWD/scripts/submit_vanda.sh" openmp-validate
validation_dir=$(cat results/vanda/latest-openmp-validate.txt)
validation_id=$(cat "$validation_dir/job-id.txt")
qstat "$validation_id"
```

After PBS finishes (repeat `qstat` as needed):

```bash
cat "$validation_dir/status.json"
cat "$validation_dir/validation.log"
qstat -xf "$validation_id" | sed -n '/job_state =/p; /Exit_status =/p'
```

Require `success: true`, `exit_status: 0`, `phase: complete` and all CTest tests passed. Some PBS installations remove completed-job history; the per-job JSON and saved logs remain available. A missing status file while queued/running means the job has not finished, not success. If validation fails, return the job directory before running the benchmark.

This job requests **one shared node allocation, 8 CPUs, 1 MPI slot, ompthreads=8, 4 GB memory, 30 minutes**. It verifies/unpacks the submitted snapshot to `results/vanda/job-openmp-validate-*/source/` and builds in that job's `build/` directory using CMake 3.24.3 Release, then runs the existing local-row and 13 numerical test groups, including 1/2/4/8 threads, convergence/fixed modes, boundaries, asymmetric coordinates, residual/error checks and non-convergence. No other build directory is cleaned. Machine-readable CTest JUnit is saved as `validation.xml`; detailed output is in `validation-detail.log`.

## 3. Submit the OpenMP benchmark

Once validation passes:

```bash
bash -l "$PWD/scripts/submit_vanda.sh" openmp
benchmark_dir=$(cat results/vanda/latest-openmp.txt)
benchmark_id=$(cat "$benchmark_dir/job-id.txt")
qstat "$benchmark_id"
```

After completion:

```bash
cat "$benchmark_dir/status.json"
qstat -xf "$benchmark_id" | sed -n '/job_state =/p; /Exit_status =/p'
cat "$benchmark_dir/analysis/summary.csv"
wc -l "$benchmark_dir/measurements/raw.jsonl"
```

Require the same successful status, **48 measured JSONL rows** (4 grid sizes × 4 thread counts × 3 repeats), plus 16 separately stored warm-ups. The job rebuilds/tests in its own directory and stops before measurements if correctness fails.

The benchmark uses N=128/256/512/1024, fixed K=1000 and 1/2/4/8 threads, one warm-up and exactly three recorded runs for every configuration. Measurements are shuffled with seed 5208; medians/minima/maxima are computed afterward. It uses the same eight-CPU resource count as validation but **exclusive placement by default** for performance isolation. If site policy requires shared placement, submit with `VANDA_PLACEMENT=shared bash -l "$PWD/scripts/submit_vanda.sh" openmp`, retain that distinction in analysis, and inspect actual normalized placement. Every process sets `OMP_DYNAMIC=FALSE`, `OMP_PLACES=cores`, `OMP_PROC_BIND=close` and `OMP_DISPLAY_AFFINITY=TRUE`. Check actual CPU-binding reports in `measurements/stdout.log` and `stderr.log`; do not claim verified binding merely because variables were set. The PBS allocation, compute-node hostname/CPU topology, module list, compiler/MPI versions, command lines, executable/source hashes and submission-time Git state are saved. There is no solution CSV during benchmarking.

Serial-baseline speedup/efficiency remain absent until Person A's source/executable interface is integrated into **this checkout** and measured with identical settings. Person A's successful correctness job alone does not provide a timing baseline. The current plots can show explicitly labeled OpenMP-one-thread-relative speedup.

## 4. Submit the MPI launch smoke test

This is independent of the absent MPI Poisson solver and may be submitted alongside OpenMP validation:

```bash
bash -l "$PWD/scripts/submit_vanda.sh" mpi-smoke
mpi_dir=$(cat results/vanda/latest-mpi-smoke.txt)
mpi_id=$(cat "$mpi_dir/job-id.txt")
qstat "$mpi_id"
```

After completion:

```bash
cat "$mpi_dir/status.json"
cat "$mpi_dir/mpi-smoke/results.jsonl"
qstat -xf "$mpi_id" | sed -n '/job_state =/p; /Exit_status =/p'
```

The job requests **one shared node allocation, 8 CPUs, 8 MPI slots, ompthreads=1, 4 GB, 30 minutes**. CMake finds MPI through the verified Open MPI module and builds `tests/mpi_smoke.cpp` from the submitted snapshot. The original `pbs` mode runs the fitting 1/2/4/8-rank cases using the PBS node file with explicit `--map-by slot:PE=1 --bind-to core --nooversubscribe --report-bindings`, following the [Open MPI 4.1 launcher documentation](https://www.open-mpi.org/doc/v4.1/man1/mpirun.1.php). It checks MPI_THREAD_FUNNELED support on every rank, collective sum, a neighbor ring, expected rank count, execution on the allocated single node and non-overlapping Linux affinity masks. A rank bound to a physical core may include both SMT siblings in its CPU mask.

Require one `success:true` record for each executed rank count listed in `mpi-smoke/plan.json`, plus the overall successful job status. Excluded rank counts are not passes. Per-rank host/CPU records and launcher stderr are retained for every rank count. This proves only single-node process launch/basic communication/thread support/binding; it does not validate Poisson decomposition, inter-node communication, halo exchange or hybrid numerical correctness. `submit_vanda.sh hybrid` remains blocked until Member B's code and the actual build adapter arrive.

If the queue requires a project or queue selection, append the **actual values** to any submission command, for example `... openmp -q QUEUE -P PROJECT`. No queue/account name is invented. Requested defaults are in each generated `job.pbs`; if PBS rejects the memory/exclusive-node policy, return its exact error for adjustment. Never execute `run_vanda_job.sh`, `mpirun` or the benchmark directly on a login node.

## 5. Archive and retrieve results

After all relevant jobs finish, from the dedicated Vanda checkout:

```bash
for kind in openmp-validate openmp mpi-smoke; do
  dir=$(cat "results/vanda/latest-$kind.txt")
  id=$(cat "$dir/job-id.txt")
  qstat -xf "$id" | sed -n '/job_state =/p; /Exit_status =/p' \
    > "$dir/pbs-final-status.txt"
done
archive="$HOME/project3-openmp-vanda-results-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar --exclude='*/build' --exclude='*/source' -czf "$archive" results/vanda
printf 'Download this exact file: %s\n' "$archive"
```

The archive includes each generated PBS script, job ID, login-node commit/status/provenance, frozen `source.tar.gz`, `status.json`, allocation/compute inventory, configure/build logs, copied CMake cache/compile commands, validation XML/details, raw JSONL, affinity diagnostics, MPI smoke evidence and median CSV. Build binaries and unpacked source directories are omitted; the small source archive preserves the exact revision without duplicate unpacked files. No credentials or full PBS `Variable_List` are collected. If one job fails, archive its directory too and return the error; do not edit its status/results.

Run **locally** (replace account and archive filename with the values from your session):

```bash
scp YOUR_NUSNETID@vanda.nus.edu.sg:~/project3-openmp-vanda-results-TIMESTAMP.tar.gz /tmp/
cd '/Users/wenyoudi/Desktop/DSA5208 Scalable Distributed Computing/HPC-Parallelization'
tar -xzf /tmp/project3-openmp-vanda-results-TIMESTAMP.tar.gz
```

Alternatively download the same archive through OnDemand Files. Return the archive here. To generate figures locally after extraction, use the actual `job-openmp-*` directory name:

```bash
MPLCONFIGDIR=/tmp/project3-mpl /opt/anaconda3/bin/python scripts/analyze.py \
  results/vanda/job-openmp-TIMESTAMP-PID/measurements/raw.jsonl \
  --output report/generated/vanda-openmp-TIMESTAMP --plots
```

Actual Vanda data remain separate from `results/local/`. Do not relabel local rows, pool different jobs/allocations, or infer numerical convergence from fixed K. The instructor's compute-node runtime requirement is met only when these actual benchmark results are returned and checked. Hybrid integration/benchmarking and comparisons with Person A's serial reference remain subsequent work.
