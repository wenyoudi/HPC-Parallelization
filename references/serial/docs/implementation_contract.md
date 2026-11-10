# Shared solver contract (version 1)

## Mathematical problem and storage

Use C++17 and double precision. Solve `-Laplacian(u)=f` on `[0,1]^2`, with zero
Dirichlet boundaries and zero interior initial values. N counts interior points.
`h=1/(N+1)`; complete grid `(N+2)*(N+2)`. A row-major vector entry `i*(N+2)+j`
represents `y=i*h, x=j*h`. This axis convention also applies to CSV output.

Problems selected by `--problem`:
- `symmetric` (default): exact `sin(pi*x)*sin(pi*y)`, RHS `2*pi^2*exact`.
- `asymmetric`: exact `sin(pi*x)*sin(2*pi*y)`, RHS `5*pi^2*exact`.

Update interior points by `(north+south+west+east+h*h*f)/4`. Read old values only,
write a second array, then swap. Never update boundaries. An initial halo exchange
must make neighbour values available before the first update.

## MPI and OpenMP agreement

Use one-dimensional row decomposition with `1 <= ranks <= N`.
For rank r: `base=N/ranks`, `extra=N%ranks`,
`local_rows=base+(r<extra)`, `global_first=1+r*base+min(r,extra)`.
Local row l in `1..local_rows` maps to global row `global_first+l-1`.
Each rank stores `(local_rows+2)*(N+2)`, including two halo rows. Columns remain
complete including physical boundary columns. Use global y when computing RHS.
Example N=10, ranks=3: row counts 4,3,3; global first rows 1,5,8.

The hybrid version should reuse decomposition and halo code, parallelizing local
loops with OpenMP `schedule(static)`. Request/check MPI_THREAD_FUNNELED; only the
main thread calls MPI. Nonblocking requests must complete before send buffers are
modified or received halos are used. Gathering CSV requires nonuniform counts and
displacements and excludes halo rows; global physical boundaries appear once.
Refresh final solution halos before residual evaluation after the last swap.

## CLI and stopping

All versions accept `--n`, `--problem`, `--mode`, `--iterations`, `--tol`,
`--max-iters`, `--output`, and `--help`. MPI ranks are configured by the launcher;
threads by OMP_NUM_THREADS. Serial reports one rank and one thread regardless of
that environment variable. Parallel versions report actual effective resources.

Defaults: N=32, mode=fixed, problem=symmetric, K=1000, tol=1e-8, max_iters=100000.
Reject incompatible options: fixed with tol/max-iters, converge with iterations.
In converge mode compute the global infinity norm of the update every iteration,
including MPI_MAX reduction. Swap to the new solution before stopping. A small
update is not itself a small residual or a sufficiently accurate continuum solution.
Use N=32,64,128 for initial convergence trials, not automatic large-grid runs.
Fixed mode does exactly K iterations and omits convergence checks/reductions.

## Output schema

One JSON line on stdout (rank zero only), with keys:
`schema_version=1`, `implementation` (serial/mpi/openmp/hybrid), `n`, `problem`,
`mode`, `mpi_ranks`, `omp_threads`, `iterations_completed`, `converged`,
`max_update`, `tol`, `solve_seconds`, `residual_linf`, `error_linf`.
Fixed mode: converged/max_update/tol are null. No NaN or Infinity in JSON.
Converge mode: converged is boolean and max_update is the final global update norm.
`residual_linf=max|f-A_h*u|`; `A_h*u=(4*u-north-south-west-east)/h^2`.
`error_linf=max|u-u_exact|`. Both use final interior solution values.
Exit codes: 0 success; 2 error; 3 convergence limit reached. MPI should coordinate
failures so one rank does not exit while others wait in communication.

CSV is a numeric matrix with no header, global y rows and x columns increasing
from zero, all physical boundaries included, 17 significant digits. Do not overwrite
existing solution files. File output is optional and excluded from timing.

## Timing and experiments

Allocate arrays and construct RHS before timing. Time the complete iteration loop,
including required communication, synchronization and reductions. Start MPI timing
after a barrier and report maximum elapsed time over ranks. The initial halo exchange,
if performed for the solve, belongs inside the timing region. Final diagnostics,
final halo refresh for diagnostics, gathering, CSV and JSON serialization are excluded.
Avoid a barrier per iteration unless required by the implementation.

Use Release -O3 and no fast-math, matching compiler/hardware. At least three fresh
runs per configuration, report median and retain all raw results. First test small
configurations on a compute node. Strong scaling fixes N, K and problem. Use the
same-machine serial baseline for speedup; efficiency denominator is total allocated
compute cores used (`ranks*threads` for hybrid). Do not oversubscribe cores.
At total eight cores compare 8x1,4x2,2x4,1x8 after correctness checks.
Weak scaling, if added, needs a separate explicit workload/efficiency definition.

## Validation and integration

A supplies serial reference and independent closed-form discrete-mode checks.
B supplies MPI-only and halo exchange; C supplies OpenMP, hybrid, environment setup.
B targets an initial MPI version on 10 November; B/C target hybrid correctness by
11 November. These are integration targets, not completed results.

Check full grids for fixed K, both problems, multiple rank/thread counts, and
N=10/ranks=3. Default comparison atol=1e-10, rtol=1e-8. Do not silently loosen
thresholds. Check convergence flags, boundary values and final residuals as well.
Analytic refinement tests must make iteration error much smaller than discretization
error; the local test uses tightened tolerance and checks residuals and second-order
error reduction. MPI/OpenMP/hybrid correctness remains pending their implementations.
