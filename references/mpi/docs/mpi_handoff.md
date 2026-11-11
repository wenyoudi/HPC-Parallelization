# Member B: MPI implementation and hybrid handoff

## Status (11 November 2026)

Implementation and execution scripts are supplied on `feature/mpi-poisson`, based
on A's serial commit `0e20822`. A's solver and mathematical contract are unchanged.
**MPI compilation, numerical validation and performance measurements on Vanda
remain pending.** No MPI speedup or correctness result is claimed here.

Local checks: 15 Python tooling tests passed (launch policy, allocation guards,
evidence parsing and scaling calculations), all Python sources passed compileall, and git diff --check
passed. These are tooling checks, not MPI numerical evidence. Local CMake
configuration could not complete because both discovered MinGW C++ executables
failed to start with Windows DLL relocation error 623. No usable MPI runtime was
found locally. Do not report a successful C++ build based on these checks.

C's `mpi_launcher.py` and `pbs_allocation.py` are copied verbatim from commit
`2ea8a5a`. The environment module names and single-node launcher workaround come
from that branch; this does not constitute testing the new solver.

## Build and run

On Vanda, from this repository root:

```bash
source config/vanda_mpi_env.sh
cmake -S . -B build-mpi-vanda -DCMAKE_BUILD_TYPE=Release -DBUILD_MPI=ON
cmake --build build-mpi-vanda --parallel 2
qsub jobs/mpi_vanda.pbs
```

The PBS job builds both variants and runs A's serial tests plus MPI validation on
one eight-core compute node. The job must be submitted from the repository root.
Do not run MPI benchmarks on the login node. Inspect the job output and
`results/hpc/mpi-JOBID/validation/validation.json` before enabling benchmarks:

```bash
qsub -v RUN_BENCHMARK=1 jobs/mpi_vanda.pbs
```

This second job validates again in its own allocation, then measures
N=256,512,1024, K=1000, ranks=1,2,4,8; three fresh measurements and one warmup per
configuration. `raw.jsonl`, warmups, stderr/bindings, metadata and `summary.csv`
are retained in `results/hpc/mpi-JOBID/benchmark/`. Results are ignored by Git;
explicitly select verified evidence for the eventual report commit.

For another machine with a real MPI installation:

```bash
cmake -S . -B build-mpi -DCMAKE_BUILD_TYPE=Release -DBUILD_MPI=ON
cmake --build build-mpi
python3 scripts/validate_mpi.py --serial build-mpi/poisson_serial \
  --mpi build-mpi/poisson_mpi --ranks 1 2 3 4 \
  --launcher-json '["mpiexec","-n","{ranks}"]' --output-dir results/local/mpi-check
```

The benchmark script deliberately requires a verified PBS allocation and a
successful same-node validation report matching both binary SHA-256 hashes and
all requested rank counts. It refuses existing result directories. Do not change
binary files between validation and benchmarking.

## Public interfaces for C

Files: `include/mpi_poisson.hpp`, `src/mpi_poisson.cpp`, `src/mpi_main.cpp`.

- `decompose_rows(N, comm)` returns `RowDomain` with `rank`, `ranks`, `n`,
  `stride`, `local_rows`, `global_first`, `upper`, `lower`.
- `exchange_halos(current, domain, comm)` exchanges full rows; row 0 and
  `local_rows+1` are halos, rows 1..local_rows are owned interiors. Physical
  endpoints use `MPI_PROC_NULL` and zero halos. Tags 100 and 101 are reserved.
  Two blocking `MPI_Sendrecv` calls leave no outstanding requests.
- `mpi_check` throws on MPI errors. The entry point sets `MPI_ERRORS_RETURN` and
  aborts the communicator on fatal exceptions to avoid stranded peers.
- `solve_mpi` owns the local buffers and returns global diagnostics on every
  rank, solve time on rank zero, and the global grid on root only when CSV is
  requested. Nonroot `solution` remains empty.
- `write_csv` is A's unmodified function, called on root. Root broadcasts output
  success/failure before all ranks finalize. Exit codes: 0 success, 2 error,
  3 convergence limit. Launcher exit-code mapping can vary on failures.

For hybrid integration, retain the MPI-only path as a reference and create a
separate hybrid target. The local update loop can be replaced by C's
`update_local_rows<TrackUpdate>` outside any OpenMP region, after the halo
exchange. C's kernel expects `h*h*f`, whereas B currently stores **unscaled f**
and multiplies by h² during the update, exactly as A does. Precompute a separate
scaled forcing array for C's kernel. Residual evaluation still needs unscaled f.
Do not pass unscaled f into C's kernel. Initialization, exchanges, all reductions
and gathering remain on the main thread under `MPI_THREAD_FUNNELED`.

MPI-only executable name is `poisson_mpi`, target `poisson_mpi`. C's existing
scripts accept explicit binary paths, so pass this path to `--mpi`. C's optional
distributed CMake hook expects a target named `mpi`; add that executable target
when integrating the branches rather than renaming A's targets or editing C's
unrelated working tree. The public core links to `poisson_core` and MPI CXX.

## Design and timing

The decomposition follows the contract exactly: distribute N interior rows with
q=N/P and remainder N%P; the first remainder ranks own q+1 rows. This balances
work to within one row and permits contiguous MPI messages. Ranks>N are rejected.
N+2 columns, including physical zero boundary columns, stay local. RHS uses
global y coordinates, which is essential for the asymmetric sine mode.

Each iteration exchanges old boundary rows, computes all owned interiors into a
second buffer, then swaps. Sendrecv avoids cyclic blocking-send deadlocks,
including the one-row-per-rank case. It is a simple communication baseline and
does not overlap communication with computation. A possible later comparison is
nonblocking receives/sends plus interior work before waiting; it has not been
implemented or measured in this branch.

Fixed mode performs exactly K updates with no per-iteration global reduction.
Converge mode uses the global max update each iteration, swaps before testing,
and makes the same stopping decision on all ranks. Small updates are not a
guarantee of small residual or continuum error; both are separately reported.

Allocation and forcing initialization are excluded from timing. A barrier
precedes MPI_Wtime. Timed work includes all iteration exchanges (including the
first), local updates, swaps and required convergence reductions. A maximum
elapsed-time reduction follows the loop outside timing. Final halos are refreshed
after the last swap, outside timing, before residuals. Final metric reductions,
Gatherv, root CSV writing and JSON are also excluded. Gatherv counts/displacements
include all interior rows and no halos; root inserts the two zero boundary rows.
The implementation rejects grids whose complete size exceeds INT_MAX elements.

## Evidence and interpretation plan

Validation runs both sine problems, ranks 1/2/3/4/8 (PBS job), N=10 and N=P,
K=1/2/31, converged solves and explicitly exhausted solves. Complete grids,
boundaries, convergence iteration counts and final diagnostics are compared to
A without loosening the contract tolerances. Invalid inputs and output-overwrite
failures must terminate without a hang. A's independent discrete eigenmode and
refinement tests remain available through CTest.

Strong scaling fixes N, K and problem. Use median solve time over at least three
fresh runs: S(P)=T_serial/T_MPI(P), E(P)=S(P)/P. Also retain T_MPI(1)/T_MPI(P) as a
separate scaling metric. The script runs serial through a one-process launcher
to apply the same core-binding policy, with launch overhead outside solver time.
Record same-node hardware, compiler, MPI, placement and variability. The full
eight-core allocation is reserved for every run, but P cores actively execute
the P-rank MPI-only configurations; the reported efficiency denominator is P.
Queue resource utilization of the whole reservation is a separate concept.

Per rank, compute is O(K*N²/P), while halo traffic is O(K*N) doubles to at most
two neighbors. Expected scaling limits include shrinking work per rank, message
latency, memory bandwidth and (in convergence mode) global reduction latency.
These are hypotheses to evaluate against measurements, not observed conclusions.
This uses manufactured solutions rather than real-world data, so continuum
accuracy and numerical performance replace data-domain conclusions.

## Analysis and report handoff

Copy the benchmark directory back to a machine with Python and Matplotlib. From
the repository root, generate figures from the raw measured JSONL:

```bash
python scripts/analyze_mpi.py results/hpc/mpi-JOBID/benchmark \
  --output-dir results/hpc/mpi-JOBID/figures
```

This exports runtime, speedup and efficiency as PNG/PDF, plus a recomputed summary
and provenance receipt. It rejects incomplete sweeps, mixed workloads, duplicate
repetitions and missing serial baselines. Min–max error bars are descriptive,
with the serial median held fixed for speedup/efficiency; they are not confidence
intervals. Matplotlib is only needed for plotting, not on the compute node.

The extended validator retains the full serial/MPI CSVs in its `grids/` directory,
adds N=10,K=100 and N=32,K=500 comparisons, and performs independent MPI continuum
refinement on N=15,31,63. `report/mpi_sections.md` contains the design, an induction
argument for correctness, the measurement protocol and the performance model.
Its experimental section is explicitly pending actual cluster evidence.

## AI usage draft

ChatGPT assisted with inspecting the team interfaces, drafting MPI decomposition,
halo exchange, diagnostics/gather logic, validation and benchmark tooling, and
this handoff documentation. The implementation follows A's existing mathematical
contract and reuses C's launch/allocation utilities with attribution. Students
must review the generated code, run actual cluster validation and benchmarks,
and report actual outcomes and limitations. No cluster results were generated
or fabricated by AI during this implementation session.
