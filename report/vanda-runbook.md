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

This job requests **one exclusive node, 8 CPUs, 1 MPI slot, ompthreads=8, 4 GB memory, 30 minutes**. It builds in a fresh `results/vanda/job-openmp-validate-*/build/` using CMake 3.24.3 Release, then runs the existing local-row and 13 numerical test groups, including 1/2/4/8 threads, convergence/fixed modes, boundaries, asymmetric coordinates, residual/error checks and non-convergence. No other build directory is cleaned. Machine-readable CTest JUnit is saved as `validation.xml`; detailed output is in `validation-detail.log`.

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

The benchmark uses N=128/256/512/1024, fixed K=1000 and 1/2/4/8 threads, one warm-up and exactly three recorded runs for every configuration. Measurements are shuffled with seed 5208; medians/minima/maxima are computed afterward. The one-node eight-CPU allocation is identical to validation. Every process sets `OMP_DYNAMIC=FALSE`, `OMP_PLACES=cores`, `OMP_PROC_BIND=close` and `OMP_DISPLAY_AFFINITY=TRUE`. Check actual CPU-binding reports in `measurements/stdout.log` and `stderr.log`; do not claim verified binding merely because variables were set. The PBS allocation, compute-node hostname/CPU topology, module list, compiler/MPI versions, command lines, executable/source hashes and Git state are saved. There is no solution CSV during benchmarking.

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

The job requests **one exclusive node, 8 CPUs, 8 MPI slots, ompthreads=1, 4 GB, 30 minutes**. CMake finds MPI through the verified Open MPI module and builds `tests/mpi_smoke.cpp`. The launcher runs 1/2/4/8 ranks using the PBS node file with explicit `--map-by slot:PE=1 --bind-to core --nooversubscribe --report-bindings`, following the [Open MPI 4.1 launcher documentation](https://www.open-mpi.org/doc/v4.1/man1/mpirun.1.php). It checks MPI_THREAD_FUNNELED support on every rank, collective sum, a neighbor ring, expected rank count, execution on the allocated single node and non-overlapping Linux affinity masks. A rank bound to a physical core may include both SMT siblings in its CPU mask.

Require four `success:true` records in `mpi-smoke/results.jsonl`, plus the overall successful job status. Per-rank host/CPU records and launcher stderr are retained for every rank count. This proves only single-node process launch/basic communication/thread support/binding; it does not validate Poisson decomposition, inter-node communication, halo exchange or hybrid numerical correctness. `submit_vanda.sh hybrid` remains blocked until Member B's code arrives.

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
tar --exclude='*/build' -czf "$archive" results/vanda
printf 'Download this exact file: %s\n' "$archive"
```

The archive includes each generated PBS script, job ID, `status.json`, allocation/compute inventory, configure/build logs, copied CMake cache/compile commands, validation XML/details, raw JSONL, affinity diagnostics, MPI smoke evidence and median CSV. Build subdirectories/binaries are omitted; no credentials or full PBS `Variable_List` are collected. If one job fails, archive its directory too and return the error; do not edit its status/results.

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
