# HPC Parallelization of a Two-Dimensional Poisson Solver

## MPI work (Member B)

MPI source, validation, Vanda PBS job and strong-scaling collection are available
on `feature/mpi-poisson`. See [MPI build instructions and hybrid
handoff](docs/mpi_handoff.md). Cluster numerical validation and benchmarks remain
pending; no MPI performance results are claimed yet.

The MPI report draft is in [report/mpi_sections.md](report/mpi_sections.md).
After real benchmarks, `scripts/analyze_mpi.py` exports runtime, speedup and
efficiency figures directly from raw measurement records.

This project investigates the correctness, runtime, and parallel efficiency of
Jacobi iteration for a two-dimensional Poisson problem. The implementation uses
C++17, with MPI for distributed-memory parallelism and OpenMP for shared-memory
parallelism. A serial reference provides the basis for validating parallel results
and calculating speedup.

The comparison covers serial, MPI-only, OpenMP-only, and hybrid MPI + OpenMP
execution. Neighbour dependencies between grid points require communication across
subdomain boundaries, making communication and synchronization important parts of
the parallel design.

## Implementation status

| Component | Status in this checkout |
| --- | --- |
| Serial Jacobi solver | Implemented; correctness tests passed locally and on Vanda |
| Numerical tests and full-grid comparison tool | Available |
| Serial benchmark collection and PBS workflow | Available; formal benchmark results pending |
| MPI-only implementation | Source and scripts available; cluster compilation/validation pending |
| OpenMP-only and hybrid implementations | Maintained on C's feature/openmp-hybrid branch; hybrid integration pending |
| Parallel validation, scaling results, and final report | Pending completion |

Commands below apply to the files currently included in this checkout. Parallel
build targets and launch commands will be documented when those implementations
are integrated. Detailed verification records are maintained in
[docs/validation_status.md](docs/validation_status.md).

## Mathematical problem

Solve the Poisson equation

```text
-Laplacian(u) = f,    (x, y) in (0, 1) x (0, 1),
u = 0 on the boundary.
```

`N` denotes the number of interior grid points along each axis. The full grid has
`(N+2) x (N+2)` points, including boundaries, and spacing `h = 1/(N+1)`.
Interior values are initially zero. All calculations use double precision.

The five-point finite-difference Jacobi update is

```text
u_new(i,j) = [u_old(i-1,j) + u_old(i+1,j)
            + u_old(i,j-1) + u_old(i,j+1) + h^2*f(i,j)] / 4.
```

Separate old and new arrays are exchanged after each iteration. Storage is
row-major: row `i` corresponds to `y=i*h`, and column `j` to `x=j*h`.

Two manufactured solutions support independent correctness checks:

| Problem | Exact solution | Right-hand side |
| --- | --- | --- |
| `symmetric` | `sin(pi*x) sin(pi*y)` | `2*pi^2 sin(pi*x) sin(pi*y)` |
| `asymmetric` | `sin(pi*x) sin(2*pi*y)` | `5*pi^2 sin(pi*x) sin(2*pi*y)` |

The asymmetric problem helps expose axis-ordering and subdomain-indexing errors.
The experiment uses manufactured problems and does not require an external dataset.

## Requirements

- C++17-compatible compiler.
- CMake 3.16 or later.
- Python 3.9 or later for the included tests and result-processing scripts; no
  third-party Python packages are required by these scripts.
- MPI and OpenMP support for the parallel implementations when integrated.
- PBS access on Vanda for the supplied batch workflow.

MPI and OpenMP are not required to build the current serial target. Use consistent
compiler versions and optimization settings when comparing implementations.

## Build

From the repository root:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 2
```

The serial executable is `build/poisson_serial`. Release builds use `-O3`; do not
add fast-math options to the comparison builds.

Run the correctness suite when validating a new build or a relevant code change:

```bash
ctest --test-dir build --output-on-failure
```

## Running the serial solver

### Convergence mode

```bash
./build/poisson_serial --n 32 --mode converge --tol 1e-8 --max-iters 100000
```

Iteration stops when `max|u_new-u_old| <= tol`, or when the iteration limit is
reached. The result explicitly indicates whether convergence was achieved. An
update tolerance is not a residual tolerance or a bound on continuum solution
error. Larger grids may require more iterations or tighter stopping criteria.

### Fixed-work mode

```bash
./build/poisson_serial --n 128 --mode fixed --iterations 1000
```

This mode performs exactly the requested number of iterations without convergence
checks. It is used to compare runtimes for equal amounts of work; completion does
not imply convergence.

### Export a reference solution

```bash
mkdir -p results/local
./build/poisson_serial --n 10 --mode fixed --iterations 20 \
  --problem asymmetric --output results/local/serial_n10_k20.csv \
  > results/local/serial_n10_k20.json
```

Use a new CSV destination for each export; existing solution files are not
overwritten. Output parent directories must already exist.

### Command-line options

| Option | Meaning | Default |
| --- | --- | --- |
| `--n` | Interior grid points per axis | `32` |
| `--problem` | `symmetric` or `asymmetric` | `symmetric` |
| `--mode` | `fixed` or `converge` | `fixed` |
| `--iterations` | Number of fixed-mode iterations | `1000` |
| `--tol` | Maximum update tolerance in convergence mode | `1e-8` |
| `--max-iters` | Convergence-mode iteration limit | `100000` |
| `--output` | Optional full-grid CSV destination | No file |
| `--help` | Display usage information | — |

`--iterations` applies only to fixed mode. `--tol` and `--max-iters` apply only to
convergence mode; incompatible combinations are rejected.

## Output and correctness validation

A successful solver invocation prints one JSON record to standard output. It
contains the problem, grid size, execution mode, rank/thread counts, completed
iterations, solver time, final residual, and error against the exact solution.
Errors are reported on standard error.

- `residual_linf`: maximum absolute discrete residual, `|f - A_h*u|`.
- `error_linf`: maximum absolute difference from the manufactured exact solution.
- `max_update`: final maximum update in convergence mode.
- `converged`, `max_update`, and `tol`: `null` in fixed mode.
- Exit codes: `0` for success, `2` for an input/runtime/output error, and `3` when
  the convergence-mode iteration limit is reached. Exit code `3` still produces
  the numerical result and any requested CSV.

CSV output is a numeric matrix without a header, including all physical boundaries,
in global row order with 17 significant digits. It does not include MPI halo rows.

The serial tests check the fixed-iteration solution against an independent discrete
sine-mode formula, boundary preservation, residuals, convergence handling, and
second-order grid refinement with sufficiently small iteration error. Parallel
implementations must additionally be compared with the serial reference, including
non-divisible decompositions such as `N=10` with three MPI ranks.

After producing serial and parallel CSV files using the same problem, N, and K:

```bash
python3 scripts/compare_solutions.py serial_solution.csv parallel_solution.csv
```

The comparator checks every value using
`abs(candidate-reference) <= atol + rtol*abs(reference)`, with defaults
`atol=1e-10` and `rtol=1e-8`. It rejects non-finite entries and mismatched shapes.
It exits with `0` for a match, `1` for numerical differences, and `2` for invalid
inputs. The two paths above refer to files generated by the respective solvers.

## Running on Vanda

Submit compilation, tests, and performance experiments through PBS from the
repository root. Do not run performance experiments on the login node.

The validated serial environment is specified by
[config/vanda_serial_env.sh](config/vanda_serial_env.sh): GCC 11.3.0 and CMake
3.24.3. Python 3.9.18 was used for the recorded Vanda test. Parallel environment
configuration must use a compatible MPI installation.

Submit compilation and correctness tests:

```bash
qsub -v HPC_SETUP="$PWD/config/vanda_serial_env.sh" jobs/serial_vanda.pbs
```

Submit the same workflow followed by serial benchmark collection:

```bash
qsub -v RUN_BENCHMARK=1,HPC_SETUP="$PWD/config/vanda_serial_env.sh" \
  jobs/serial_vanda.pbs
```

The PBS template requests one CPU, 4 GB memory, and one hour. Actual scheduler
allocations can differ; preserve the scheduler record alongside the job log.
The completed serial validation job received one CPU and 6 GB memory. Its log is
available in [results/validation/vanda_serial_1535699.log](results/validation/vanda_serial_1535699.log).
Test-suite duration is not a solver benchmark.

## Benchmark methodology and results

The collection script can also run directly inside an allocated compute-node job
using an existing compiled executable, without rebuilding or rerunning the tests:

```bash
python3 scripts/benchmark_serial.py \
  --executable build-vanda/poisson_serial \
  --sizes 128 256 512 1024 \
  --iterations 1000 --repeats 3 \
  --output-dir results/hpc/serial-run-001
```

Each invocation requires a new output directory and produces:

- `runs.jsonl`: every run's metrics, command, hostname, and timestamp.
- `summary.csv`: median, minimum, and maximum solver times for each grid size.

Solver timing excludes allocation, initialization, final error evaluation, and file
output. Parallel timing must include communication and synchronization needed by
the iterative solve; MPI timing is reported as the maximum elapsed time over ranks.

Strong-scaling experiments hold N, iteration count, and problem fixed. Compute
speedup as `T_serial/T_parallel` and efficiency as `speedup/P`, where P is the
number of compute cores used. For hybrid runs, `P = MPI ranks * threads per rank`.
Use comparable hardware, compiler settings, and timing boundaries for both times.
Record process/thread binding and avoid oversubscription. All configurations require
at least three repeats, with the median used for comparisons.

Formal performance figures must use Atlas or Vanda measurements. Local development
results are for correctness checks only. Large generated run directories are ignored
by Git; curated experimental records and figures should be added deliberately when
available. No completed parallel scaling results are reported in this checkout.

## Repository structure

```text
CMakeLists.txt                 Build configuration
include/poisson.hpp            Solver types and function declarations
src/poisson.cpp                Serial solver, problem definitions, and CLI handling
src/serial_main.cpp           Serial executable entry point
tests/test_serial.py          Independent numerical and input-validation tests
scripts/compare_solutions.py Full-grid numerical comparison
scripts/benchmark_serial.py  Repeated-run collection and timing summaries
jobs/serial_vanda.pbs         Vanda batch workflow
config/vanda_serial_env.sh   Validated serial compiler environment
docs/implementation_contract.md  Common interface and parallelization conventions
docs/validation_status.md        Verification record and outstanding checks
results/validation/              Archived validation evidence
```

The [implementation contract](docs/implementation_contract.md) specifies the
row decomposition, halo handling, shared CLI/JSON schema, and timing conventions
for integrating the parallel implementations.

## AI usage

AI assistance was used in drafting the serial implementation, tests, documentation,
and execution scripts. Numerical correctness was checked using independent
mathematical references and automated tests, with additional checks recorded in the
validation document. The final report will consolidate the contributors' actual AI
usage and review procedures across the complete project.
