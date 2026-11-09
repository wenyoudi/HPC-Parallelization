# NUS Vanda execution runbook

## Access findings (9 November 2026)

Both a bounded HTTPS request and noninteractive SSH probe failed at DNS resolution of `vanda.nus.edu.sg` from the development Mac, including the network-enabled retry. The in-app browser independently returned `net::ERR_NAME_NOT_RESOLVED`; the public web reader also could not open the portal. No Vanda-specific SSH alias/account was configured. No password, MFA code or private key was read or requested. This establishes that this session cannot currently reach Vanda; it does not establish that the user's HPC account is invalid.

[NUS IT's batch job documentation](https://nusit.nus.edu.sg/services/getting-started/how-to-run-batch-job/) identifies PBS Pro. The [NUS course teaching team's Vanda guide](https://mle4217-5219.matsci.dev/orientation/vanda/) specifically identifies Vanda's PBS scheduler, SSH and OnDemand access. These are documentation evidence; **live scheduler version, module names, queues, project/account flags, compiler and MPI remain unverified**. No final submitted job or cluster performance result is claimed. The PBS generator is conditional on successful live discovery; it does not assume Slurm.

## User authentication steps

1. Register/activate your NUS HPC account if needed using the links in the course guide. Connect to NUS VPN when off campus; the guide specifies NUS/NUS-STU Wi-Fi on campus and warns that eduroam alone does not provide HPC access.
2. Open <https://vanda.nus.edu.sg> yourself and finish NUS authentication/MFA in the portal. Never paste credentials into this chat, scripts or repository. If first-time activation is needed, run `ssh YOUR_NUSNETID@vanda.nus.edu.sg` in your own terminal and authenticate there; verify any new host-key fingerprint through NUS documentation/support.
3. Open **Vanda Shell Access** in OnDemand for light inventory/submission only. Do not benchmark on login nodes. Alternatively use your authenticated SSH session. If Codex cannot use your authenticated session, execute the commands below yourself and return the resulting inventory/data files (no credentials).

## Transfer code and discover the actual environment

From Vanda's shell, clone the feature branch once pushed:

```bash
git clone --branch feature/openmp-hybrid https://github.com/wenyoudi/HPC-Parallelization.git
cd HPC-Parallelization
source scripts/discover_environment.sh results/vanda/discovery
cat results/vanda/discovery/scheduler.txt
cat results/vanda/discovery/pbs-server.txt
cat results/vanda/discovery/queues.txt
cat results/vanda/discovery/modules-available.txt
```

If Git access is unavailable, upload a source archive via OnDemand Files instead (locally, after committing: `git archive --format=tar.gz -o /tmp/project3-source.tar.gz feature/openmp-hybrid`; upload and extract into a new directory). Do not transfer the Mac binaries.

Review discovery output; it must identify a responding PBS server before using the supplied generator. If the live scheduler differs, stop submission and adapt the generator to the verified scheduler. Inventory records login-node topology separately; actual benchmark hardware is collected inside the allocation. Use `hpc pbs help` for current NUS queue/resource guidance.

```bash
cp scripts/vanda-env.example.sh scripts/vanda-env.local.sh
# Edit scripts/vanda-env.local.sh using module names found above.
# Set VANDA_VERIFIED_SCHEDULER="pbs" only after verifying qstat -Bf.
# Set HPC_CXX to the compiler available after loading those modules.
# Set supported HPC_OMPFLAGS (e.g. -fopenmp for a verified GNU compiler).
# Load the matching MPI module only after the MPI/hybrid code arrives.
```

Do not invent a module name. Capture `module list`, compiler version and `mpicxx -show`/`--showme` after loading. For hybrid, set `MPI_LAUNCHER_JSON` and `MPI_PLACEMENT_LABEL` for **that exact MPI**. Its arguments must bind each rank to a disjoint group of `{threads}` cores, with `{ranks}` processes on the one allocated node. Verify using launcher binding reports plus `OMP_DISPLAY_AFFINITY=TRUE` (preserved in stdout/stderr logs). No universal MPI placement syntax is assumed. Hybrid scripts intentionally remain gated until B's code and a verified launcher are available.

## Submit OpenMP correctness and benchmark job

From the project directory on Vanda after completing the config:

```bash
bash scripts/submit_vanda.sh openmp
# If your account requires queue/project flags, supply the VERIFIED values:
# bash scripts/submit_vanda.sh openmp -q QUEUE -P PROJECT
qstat -u "$USER"
```

The generated job requests one exclusive node allocation with 8 CPU cores, 4 GB memory and 30 minutes. The generator passes optional queue/project flags directly to `qsub` without guessing names. Verify these resource settings against your current queue policy before submission. The job reloads your module config, inventories the compute node, builds with logged commands, runs numerical tests and only then benchmarks. Defaults: N=128/256/512/1024, K=1000, threads=1/2/4/8, one warm-up and three measured runs per configuration. No solution CSV is written in benchmarks. Settings are validated and all measurements are fixed mode.

`OMP_NUM_THREADS`, `OMP_DYNAMIC=FALSE`, `OMP_PLACES=cores` and `OMP_PROC_BIND=close` are set for each run. Compare requested affinity with actual binding diagnostics; ensure the PBS cpuset grants physical cores and no concurrent workload shares them. Metadata saves actual allocation, host CPU topology, loaded module names, compiler commands, MPI version, executable hash, Git revision and working-tree status. Results are written under `results/vanda/job-openmp-TIMESTAMP/measurements/`. A failure prevents subsequent benchmarks and must be investigated, not skipped.

Once serial is available, add Member A's `make serial` rule using the same compiler/optimization variables and set `SERIAL_EXE` in your config. The job rebuilds serial after cleaning, then the benchmark runner includes a serial baseline within the same run. The plotter leaves serial speedup/efficiency blank if it is absent.

## Hybrid job after integration

Complete [hybrid-integration.md](hybrid-integration.md) first, replace the intentional `make hybrid` guard with the actual build rule, and configure your verified MPI launcher. Then:

```bash
bash scripts/submit_vanda.sh hybrid
```

The initial prepared matrix includes 1×1/2×1/4×1/8×1 for strong scaling and 8×1/4×2/2×4/1×8 for equal eight-worker comparisons. The prepared `tests/validate_hybrid.py` first checks nondivisible rows, N=ranks, one rank, first/last boundaries, K=0/1/2/31, final-halo metrics and convergence against OpenMP, including asymmetric coordinates. It also compares against serial if configured; repeat with Member B's MPI executable as reference before claiming all-variant validation. None of these MPI tests have run yet. Keep the same N/K and timing scope as OpenMP and serial. One node only; multinode experiments require a separately verified allocation/launcher plan.

## Retrieve and analyze measured data

The run directory contains `metadata.json`, `raw.jsonl`, `warmups.jsonl`, `stdout.log`, `stderr.log`, allocated node list and `analysis/summary.csv`. Keep the generated job, scheduler output and compute inventory alongside it.

On Vanda, replace the timestamp below with the actual directory:

```bash
tar -czf /tmp/project3-vanda-results.tar.gz results/vanda/job-openmp-TIMESTAMP
```

Download using OnDemand Files, or run locally with your own account:

```bash
scp YOUR_NUSNETID@vanda.nus.edu.sg:/tmp/project3-vanda-results.tar.gz /tmp/
tar -xzf /tmp/project3-vanda-results.tar.gz
MPLCONFIGDIR=/tmp/project3-mpl python3 scripts/analyze.py \
  results/vanda/job-openmp-TIMESTAMP/measurements/raw.jsonl \
  --output report/generated/vanda-openmp-TIMESTAMP --plots
```

Use a local Python with Matplotlib (on the development Mac `/opt/anaconda3/bin/python` has it). The analysis accepts one consistent run at a time, computes medians from raw samples, preserves min/max, and labels all plots VANDA. Never change a local row's `site` label to manufacture cluster evidence. Return the whole run archive for analysis and report integration, avoiding credentials and account configuration. Download promptly; `/tmp` is temporary.

Until Vanda is reachable and these compute jobs pass, the instructor's cluster-runtime requirement remains outstanding. This blocks actual cluster measurements only, not local implementation/testing.
