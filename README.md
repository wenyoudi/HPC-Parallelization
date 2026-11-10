# HPC-Parallelization

DSA5208 Project 3: 2D Poisson equation, five-point finite differences and Jacobi iteration. Submission deadline: **16 November 2026**.

Member A owns the production serial solver, common validation and final PDF; Member B owns MPI decomposition/communication. This branch adds the OpenMP contribution. Neither teammate's implementation was present in the repository or remote branches inspected on 9 November. Hybrid **integration is pending**, with the reusable local computation prepared in `include/openmp_rows.hpp` and the exact handoff in [report/hybrid-integration.md](report/hybrid-integration.md).

Update: Member A's serial baseline is now pinned verbatim under `references/serial/` from commit `0e20822`, in an isolated build/include directory. Member B's source remains unavailable, confirmed by the user. No MPI Poisson solver or hybrid replacement is created here. Existing OpenMP source and benchmark artifacts remain unchanged.

## Build and run

Requires C++17 and an OpenMP compiler/runtime. On a verified GNU/Linux compiler:

```bash
make CXX=g++
OMP_NUM_THREADS=4 OMP_DYNAMIC=FALSE OMP_PLACES=cores OMP_PROC_BIND=close \
  ./build/openmp --n 128 --mode fixed --iterations 1000
OMP_NUM_THREADS=4 ./build/openmp --n 32 --mode converge --tol 1e-8 \
  --max-iters 100000 --output /tmp/solution.csv
make test CXX=g++
```

The development Mac has Apple Clang and an existing Anaconda OpenMP runtime. Use:

```bash
bash scripts/build_local.sh
```

This runs the tests too. Set `OPENMP_PREFIX` if the runtime is elsewhere. It installs nothing. The local MPI wrapper's default compiler is absent; the new smoke source was compile-checked by overriding it to Apple Clang, without running MPI locally. This does not validate the Vanda Open MPI environment.

## Vanda: verified modules and separate PBS jobs

On 10 November the user verified GCC/11.3.0, CMake/3.24.3-GCCcore-11.3.0, OpenMPI/4.1.4-GCC-11.3.0 and PBS (`/opt/pbs/bin/qsub`, `/opt/pbs/bin/qstat`). Person A's successful serial test job is separate evidence; no OpenMP Vanda measurements have been returned yet. `scripts/vanda-env.sh` now loads and rechecks exactly those modules. CMake Release uses C++17, `-O3 -DNDEBUG`, and no fast-math. Python >=3.8 is checked for the existing validation/data scripts.

Run these commands in your authenticated **Vanda SSH shell**, creating a fresh checkout that does not touch Person A's directory:

```bash
work=$(mktemp -d "$HOME/project3-openmp-vanda.XXXXXXXX")
git clone --single-branch --branch feature/openmp-hybrid \
  https://github.com/wenyoudi/HPC-Parallelization.git "$work/repo"
cd "$work/repo"
bash -l "$PWD/scripts/setup_vanda.sh"
bash -l "$PWD/scripts/submit_vanda.sh" openmp-validate
bash -l "$PWD/scripts/submit_vanda.sh" mpi-smoke
# Once the validation status.json reports success:true:
bash -l "$PWD/scripts/submit_vanda.sh" openmp
```

Submission records Git commit/status on the login node and archives the clean committed source. Compute jobs verify/unpack that snapshot and need no Git; later checkout updates cannot change a queued job's source. Commit or preserve local edits before submitting; the scripts never reset or stash them.

Each PBS job requests eight CPUs on one node and builds under its own `results/vanda/job-*/build/`; no other checkout/build directory is cleaned. Validation and MPI smoke default to `place=shared`; performance benchmarks retain `place=excl` by default. `VANDA_PLACEMENT=shared` or `excl` explicitly overrides placement at submission. The validation hold reported for job 1535954 has no confirmed cause; shared placement is a smaller request, not a diagnosed fix. OpenMP jobs use one MPI slot and eight OpenMP threads; MPI smoke uses eight slots and one thread. Benchmark configurations are 1/2/4/8 threads, N=128/256/512/1024, fixed K=1000, one warm-up and three recorded repetitions (48 measured rows). Actual normalized allocation, binding reports, compiler/hardware metadata and login-node provenance are retained. The smoke test checks 1/2/4/8-rank launch, FUNNELED support, collective/ring communication and disjoint bindings; it does not implement MPI Poisson.

See [the updated runbook](report/vanda-runbook.md) for exact status, result retrieval and plotting commands. The agent can reach Vanda but cannot use the authenticated SSH session, so these jobs must currently be submitted manually. Live CPU hardware and measurements will come from returned compute-node evidence.

The user has now verified single-node MPI communication at 1/2/4 ranks in Vanda job **1536986**, on GN-A40-074, exit 0. The default launcher supports that `--mca plm rsh --mca ras ^tm --host HOST:SLOTS` workaround, deriving slots from actual PBS `ncpus`. Set `VANDA_MPI_LAUNCHER=pbs` to retain the original scheduler/hostfile alternative. `VANDA_CPUS=4` requests a four-CPU smoke allocation; fitting rank counts and exclusions are recorded. Explicit PE/core binding is included and needs its own Vanda evidence. Every controlled MPI/hybrid launch rejects `ranks × threads` above the PBS/cpuset/physical-core limit.

```bash
# In the existing isolated Vanda checkout after pulling this branch:
VANDA_CPUS=4 VANDA_MPI_LAUNCHER=single-node bash -l "$PWD/scripts/submit_vanda.sh" mpi-smoke
bash -l "$PWD/scripts/submit_vanda.sh" serial-compare
```

`serial-compare` builds/tests the pinned serial reference and compares full grids with OpenMP without altering old results. `mpi-validate`, `hybrid-validate`, and `hybrid` jobs are prepared but refuse submission until real targets are integrated through [cmake/README.md](cmake/README.md). Distributed validation covers halo-sensitive final metrics, nonuniform N=10/ranks=3, N=ranks, both problems and fixed/convergence modes against serial. Hybrid benchmarking requires successful evidence matching the exact binaries, launch mode and all configurations; serial baselines are measured in the same allocation with explicit one-core binding. No MPI Poisson/hybrid numerical validation or hybrid timing is claimed yet.

## Numerical and output contract

`N` counts interior points; full storage is `(N+2)²`, flat row-major double arrays, zero boundaries, zero initial interior, `h=1/(N+1)`. **Rows are y and columns are x.** The default manufactured solution is `sin(pi*x)sin(pi*y)` and RHS `2*pi²*u_exact`. Each step reads the old buffer, writes the new buffer, and swaps.

| Argument | Default | Meaning |
|---|---|---|
| `--n N` | 128 | Positive interior dimension |
| `--mode fixed\|converge` | converge | Common numerical execution mode |
| `--iterations K` | 1000 | Exact fixed iteration count; zero is allowed for initialization checks |
| `--tol T` | 1e-8 | Positive finite max-update tolerance |
| `--max-iters M` | 100000 | Positive convergence iteration limit |
| `--output PATH` | none | Headerless full-grid CSV, 17 significant digits, boundaries included |
| `--problem symmetric\|asymmetric` | symmetric | Optional validation extension; asymmetric is `sin(pi*x)sin(2*pi*y)`, RHS `5*pi²*u_exact` |

Defaults and the optional validation flag need agreement with A/B when their interfaces arrive. All supplied arguments are validated, including those unused by a mode. Duplicates and unknown options are rejected. `OMP_NUM_THREADS` controls the team; the result records the actual team size. Tests and benchmarks set `OMP_DYNAMIC=FALSE`.

The solver prints exactly one JSON result line on success or non-convergence. Fixed mode reports `converged:null` and `max_update:null`; it performs no convergence check/reduction in the loop. Convergence mode reports the maximum absolute update and stops at `<=tol`. Exit status: **0** success, **1** input/allocation/output error, **2** convergence iteration limit reached (JSON still emitted; diagnostic on stderr). CSV paths need an existing parent directory.

`solve_seconds` covers the complete iteration team and its synchronization. Allocation, RHS initialization, final metrics and export are excluded. Final metrics are `max |f-A_h u|` and `max |u-u_exact|`, distinct from max update. For large N the default limit may not converge; fixed-mode completion never implies convergence.

## Validation

```bash
make test CXX=g++
# After teammate executables are available, run the actual cross-implementation checks:
python3 tests/compare_solvers.py --reference build/serial --candidate build/openmp --threads 4
python3 tests/compare_solvers.py --reference build/serial --candidate build/hybrid \
  --launcher-json '["mpirun","-n","{ranks}"]' --ranks 3 --threads 2
```

The launcher above is a functional-test example; choose binding arguments for the installed MPI before benchmarking. Add `--asymmetric` once both executables support that validation extension. Run rank/thread cases 1×1, 3×2, 2×4, 4×2, 8×1, 1×8, including N=10 with 3 ranks. The comparison uses N=10, checks full CSV shape, boundaries, solution, iteration count, residual, error and max update in both modes (absolute `1e-10`, relative `1e-8`).

Current automated tests use an independent scalar Python oracle, a closed-form discrete sine mode, manually calculated N=1 update, 1/2/4/8 threads, odd/even iteration counts, zero boundaries, asymmetric coordinates, independently recomputed metrics, convergence at N=32/64/128, non-convergence, invalid input and second-order refinement. The C++ row-kernel test uses nonzero halos and 3 local rows. These do **not** substitute for testing Member A/B executables or MPI communication.

After a logged build, `python3 tests/test_pipeline.py` additionally checks collection/analysis and resource/provenance guards. The complete future MPI integration matrix is prepared in `tests/validate_hybrid.py`; it fails if the real hybrid executable is absent. Sanitizer validation and accuracy evidence are recorded under `results/local/`.

## Benchmarks and plots

```bash
# Local smoke/performance data; output directory must be new.
bash scripts/benchmark_openmp.sh --site local --allocated-cpus 8 \
  --output results/runs/local-openmp-01
# Optional: --serial build/serial, built in the same compiler environment.
python3 scripts/analyze.py results/runs/local-openmp-01/raw.jsonl \
  --output report/generated/local-openmp-01 --plots
```

The runner requires a build log (default `build/build.log`; record compilation with `tee`), performs one warm-up and three repetitions, shuffles measured configurations with a fixed seed, and preserves raw JSONL, warm-ups, stdout/stderr affinity diagnostics and metadata. Default N=128,256,512,1024 and K=1000. OpenMP tests 1,2,4,8 threads; hybrid prepares 1×1,2×1,4×1,8×1,4×2,2×4,1×8 on a single node. It rejects missing solvers and oversubscribed requests. Hybrid requires an explicit MPI launcher JSON with `{ranks}` and `{threads}` placeholders and verified process binding.

`analyze.py` produces median/min/max CSV and optional PDF/PNG plots (Matplotlib is needed only for plotting). It never pools different runs/sites/modes/allocations. Serial speedup and efficiency remain empty without a true serial baseline. OpenMP-one-thread-relative speedup/efficiency are labeled separately. Local Mac affinity requests may not be honored; consult preserved stdout/stderr logs. Use homogeneous allocated Vanda cores for formal performance conclusions.

**Formal report runtimes must come from allocated Atlas/Vanda compute nodes.** See [the Vanda runbook](report/vanda-runbook.md) for the verified module configuration, exact submission commands and result retrieval. No Vanda OpenMP runtime data have been returned to this chat. Benchmark directories under `results/vanda/` are ignored by Git; archive and share them separately before scratch cleanup.

Report contributions: [OpenMP design and evidence](report/openmp-hybrid.md), [hybrid handoff](report/hybrid-integration.md), [Vanda instructions](report/vanda-runbook.md), [AI usage](report/ai-usage.md). Actual committed local results and figures are under `results/local/` and `report/figures/`.
