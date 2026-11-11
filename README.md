# HPC-Parallelization

DSA5208 Project 3: 2D Poisson equation, five-point finite differences and Jacobi iteration. Submission deadline: **16 November 2026**.

Branch **`codex/hybrid-mpi-integration`** is based on `feature/openmp-hybrid` at `2ea8a5a`. It preserves the standalone OpenMP implementation/results and A's serial reference, pins B's unmodified MPI source from `1756eff`, and builds a separate hybrid solver using B's public decomposition/halo exchange. Upstream MPI evidence remains on B's branch; no build files/scripts are blindly merged. Integration details and actual local evidence are in [report/hybrid-integration.md](report/hybrid-integration.md).

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

This runs the tests too. Set `OPENMP_PREFIX` if the runtime is elsewhere. It installs nothing. The local MPI wrapper needs `MPICH_CXX=/usr/bin/clang++` during CMake configuration. Actual local MPI/hybrid correctness tests have now run with MPICH; Vanda uses the separately verified Open MPI environment.

## Hybrid build and Vanda execution

On a local Linux system with working MPI/OpenMP, or an allocated compute shell:

```bash
cmake -S . -B build/hybrid -DCMAKE_BUILD_TYPE=Release -DBUILD_DISTRIBUTED_SOLVERS=ON
cmake --build build/hybrid --parallel 8
ctest --test-dir build/hybrid --output-on-failure
OMP_NUM_THREADS=2 mpirun -n 3 build/hybrid/hybrid --n 10 --mode fixed --iterations 31
```

Targets: `openmp`, B's unchanged `mpi`, independent `hybrid`, and A's `poisson_serial` (under `build/hybrid/references/serial/`). Hybrid forms h²*f inside each stencil, matching A/B's unscaled RHS representation. It requests/checks MPI_THREAD_FUNNELED, keeps MPI on the main thread, performs thread/global maxima, refreshes final halos and gathers nonuniform rows. The original OpenMP source/kernels are unchanged. Four CTest entries and **494 local MPI/hybrid checks** passed, including direct comparisons with serial and MPI-only; full grids and hashes are in [local hybrid evidence](results/local/hybrid-integration-20261111/README.md). This is not a Vanda hybrid measurement.

In your authenticated **Vanda SSH shell**, create a separate checkout:

```bash
work=$(mktemp -d "$HOME/project3-hybrid-vanda.XXXXXXXX")
git clone --single-branch --branch codex/hybrid-mpi-integration \
  https://github.com/wenyoudi/HPC-Parallelization.git "$work/repo"
cd "$work/repo"
bash -l "$PWD/scripts/setup_vanda.sh"
VANDA_MPI_LAUNCHER=single-node bash -l "$PWD/scripts/submit_vanda.sh" hybrid-validate
# Only after that job reports success:
VANDA_MPI_LAUNCHER=single-node bash -l "$PWD/scripts/submit_vanda.sh" hybrid
```

Jobs load GCC/11.3.0, CMake/3.24.3-GCCcore-11.3.0 and OpenMPI/4.1.4-GCC-11.3.0, use C++17 Release -O3 without fast-math, and build/test/benchmark only inside PBS allocations. The default verified single-node workaround derives `--host HOST:SLOTS` from actual PBS CPUs; `VANDA_MPI_LAUNCHER=pbs` preserves the original hostfile alternative. Every controlled launch enforces ranks × threads within the allocated/cpuset/physical-core limit.

PBS allocation is queried once at job startup (up to three bounded attempts), then recorded in a checksummed, job-specific snapshot. All validation children reuse it while rechecking job/host/nodefile identity and live CPU affinity/physical-core limits. No scheduler query is made for each grid comparison. The user reported job 1540875 passing CTest, MPI smoke and 312 comparisons before a scheduler timeout prevented the next solver launch; this is a partial Vanda validation, not a full pass. See the [rerun commands](report/vanda-runbook.md#rerun-after-the-allocation-query-fix) for the existing isolated checkout.

Validation uses eight CPUs with shared placement; benchmark requests eight CPUs exclusively by default (overridable with `VANDA_PLACEMENT=shared`). Jobs freeze submitted source and never require compute-node Git. Every job uses a new directory, preserving existing OpenMP and upstream MPI evidence. Hybrid timing reruns validation and requires successful Vanda evidence for the exact serial/hybrid binaries, launch mode and all configurations. Defaults are fixed K=1000, N=128/256/512/1024, 1x1/2x1/4x1/8x1/4x2/2x4/1x8, one warm-up and three repetitions, plus a same-node one-core serial baseline. No new Vanda hybrid runtime or speedup is claimed yet.

See [the runbook](report/vanda-runbook.md) for status checks, exact archive/download commands and plots from actual returned measurements. Keep the old OpenMP checkout and Person A's directory unchanged.

## Numerical and output contract

The table/defaults below describe the unchanged standalone `openmp` target. MPI/hybrid retain A/B's strict mode-specific CLI, defaults N=32/mode=fixed, lowercase `n` in JSON, error exit 2 and non-convergence exit 3. Pass explicit N/mode/iteration/tolerance flags when comparing implementations; tools accept both n/N. MPI/hybrid refuse existing CSV output files.

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
# Local MPI examples after the distributed CMake build; use PBS jobs on Vanda:
python3 tests/compare_solvers.py --reference build/hybrid/references/serial/poisson_serial \
  --candidate build/hybrid/openmp --threads 4
python3 tests/compare_solvers.py --reference build/hybrid/references/serial/poisson_serial \
  --candidate build/hybrid/hybrid --launcher-json '["mpirun","-n","{ranks}"]' --ranks 3 --threads 2
```

The launcher above is a functional-test example; choose binding arguments for the installed MPI before benchmarking. Add `--asymmetric` once both executables support that validation extension. Run rank/thread cases 1×1, 3×2, 2×4, 4×2, 8×1, 1×8, including N=10 with 3 ranks. The comparison uses N=10, checks full CSV shape, boundaries, solution, iteration count, residual, error and max update in both modes (absolute `1e-10`, relative `1e-8`).

Current automated tests use an independent scalar Python oracle, a closed-form discrete sine mode, manually calculated N=1 update, 1/2/4/8 threads, odd/even iteration counts, zero boundaries, asymmetric coordinates, independently recomputed metrics, convergence at N=32/64/128, non-convergence, invalid input and second-order refinement. The C++ row-kernel test uses nonzero halos and 3 local rows. These do **not** substitute for testing Member A/B executables or MPI communication.

After a logged build, `python3 tests/test_pipeline.py` additionally checks collection/analysis and resource/provenance guards. The full retained-grid MPI/hybrid matrix is in `scripts/validate_distributed.py`, with serial and MPI-only references; it supports actual PBS runs and explicitly labeled local MPI correctness runs. Sanitizer validation and accuracy evidence are recorded under `results/local/`.

`python3 tests/test_pbs_allocation.py` and `python3 tests/test_allocation_cache_workflow.py` test scheduler timeout/retry fixtures, cache integrity/identity, current CPU limits, and snapshot propagation through the complete validation-driver matrix. A real child comparison and environment inventory are also exercised with a deliberately unavailable scheduler. These infrastructure fixtures are not Vanda solver results.

## Benchmarks and plots

```bash
# Local smoke/performance data; output directory must be new.
bash scripts/benchmark_openmp.sh --site local --allocated-cpus 8 \
  --output results/runs/local-openmp-01
# Optional: --serial build/serial, built in the same compiler environment.
python3 scripts/analyze.py results/runs/local-openmp-01/raw.jsonl \
  --output report/generated/local-openmp-01 --plots
```

The runner requires a build log (default `build/build.log`; record compilation with `tee`), performs one warm-up and three repetitions, shuffles measured configurations with a fixed seed, and preserves raw JSONL, warm-ups, stdout/stderr affinity diagnostics and metadata. Default N=128,256,512,1024 and K=1000. OpenMP tests 1,2,4,8 threads; hybrid prepares 1×1,2×1,4×1,8×1,4×2,2×4,1×8 on a single node. It rejects missing solvers and oversubscribed requests. Vanda hybrid runs use `--launcher-mode single-node|pbs`, derive resources live and require matching successful Vanda validation; local hybrid runs may supply an explicit launcher JSON.

`analyze.py` produces median/min/max CSV and optional PDF/PNG plots (Matplotlib is needed only for plotting). It never pools different runs/sites/modes/allocations. Serial speedup and efficiency remain empty without a true serial baseline. OpenMP-one-thread-relative speedup/efficiency are labeled separately. Local Mac affinity requests may not be honored; consult preserved stdout/stderr logs. Use homogeneous allocated Vanda cores for formal performance conclusions.

**Formal report runtimes must come from allocated Atlas/Vanda compute nodes.** See [the Vanda runbook](report/vanda-runbook.md) for the verified module configuration, exact submission commands and result retrieval. New Vanda hybrid validation and benchmark evidence must still be returned; existing evidence is preserved. Benchmark directories under `results/vanda/` are ignored by Git; archive and share them separately before scratch cleanup.

Report contributions: [OpenMP design and evidence](report/openmp-hybrid.md), [hybrid handoff](report/hybrid-integration.md), [Vanda instructions](report/vanda-runbook.md), [AI usage](report/ai-usage.md). Actual committed local results and figures are under `results/local/` and `report/figures/`.
