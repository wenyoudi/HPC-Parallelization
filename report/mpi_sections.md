# MPI-only parallelization of the Jacobi solver

**Draft status:** the design and correctness argument below describe the supplied
source. Cluster compilation, numerical validation, runtime measurements and
scaling conclusions are pending. This draft must not be presented as a completed
experimental evaluation. It supplements A's algorithm introduction and C's
OpenMP/hybrid sections.

## Domain decomposition and storage

We parallelize the agreed five-point Jacobi discretization of the two-dimensional
Poisson equation using a one-dimensional decomposition of its N interior rows.
For P MPI ranks, let q=floor(N/P), r=N mod P. Rank p owns

\[
n_p=q+\mathbf{1}_{p<r},\qquad s_p=1+pq+\min(p,r).
\]

Here s_p is the first owned global row. Local row i maps to global row s_p+i-1;
the global y coordinate is therefore (s_p+i-1)h, where h=1/(N+1). Each rank owns
complete rows, so columns require no inter-rank communication. Ranks>N are
rejected because the design assumes at least one owned row per rank.

The owned row counts differ by at most one. For example, N=10 and P=3 gives
4,3,3 rows with first global rows 1,5,8. Unlike a simple N/P truncation, this
rule covers the entire interior without overlapping ownership. Each rank stores
two solution arrays and the unscaled forcing array, each of size
(n_p+2)(N+2). Local rows 0 and n_p+1 are halo rows, while columns 0 and N+1 are
physical zero boundary columns. The first and last global halo rows are also zero.
Approximate local array storage is 3(n_p+2)(N+2) times sizeof(double), excluding
MPI overhead. Optional CSV export additionally allocates a complete grid on root.

A row decomposition provides contiguous communication buffers and a small,
reusable interface for the hybrid version. Compared with a two-dimensional
decomposition, it avoids column datatypes and additional neighbor bookkeeping.
Its limitation is that a halo row remains length N+2 as P grows, while owned
computation shrinks; the implementation also cannot use more than N ranks.

## Halo exchange and iteration ordering

Every iteration exchanges the boundary rows of the old solution before updating
any interior point. With rank p-1 as the upper neighbor and p+1 as the lower
neighbor, the first MPI_Sendrecv sends the first owned row upward (tag 100) and
receives the lower neighbor's first owned row into the lower halo. The second
sends the last owned row downward (tag 101) and receives the upper neighbor's
last owned row into the upper halo. Endpoints use MPI_PROC_NULL and explicit
zero boundary halos. Separate tags distinguish the two directions. The send and
receive buffers do not overlap, including when each rank owns only one row.

MPI_Sendrecv avoids the cyclic dependency that can occur when all ranks perform
a blocking send before posting any receive. Both exchanges complete before the
stencil reads the halos. The local stencil then reads exclusively from the old
array and writes exclusively to the next array. After the local update, the
buffers are swapped. The code does not introduce a global barrier every iteration.

Fixed mode performs exactly K iterations without an update-norm reduction. In
convergence mode, each rank computes its maximum local update and MPI_Allreduce
with MPI_MAX obtains the global infinity norm. The implementation swaps first,
then reduces and tests that norm; consequently the retained solution is the new
iterate, including on the stopping iteration. Every rank receives the same norm
and makes the same stopping decision. Reaching the maximum iteration count
without convergence is reported explicitly with exit code 3.

All MPI calls execute on the main thread. Initialization requests and checks
MPI_THREAD_FUNNELED, so C can reuse the decomposition and exchange code around
OpenMP local loops. C's kernel expects pre-scaled h²f; the MPI baseline stores
unscaled f to match A. Integration must account for that interface difference.

## Correctness argument

Initially, every owned interior and physical boundary value is zero, matching the
serial initial grid. Assume that before iteration k each owned interior value
equals its serial counterpart. Halo exchange copies the adjacent owned rows of
that same iterate into the receiver's halos. Physical endpoints remain zero.
Thus every local update reads the same four neighbor values and forcing value as
the serial update at the corresponding global coordinate. It applies the same
arithmetic expression and writes a distinct next-buffer location. Swapping the
buffers therefore preserves the correspondence for iteration k+1. By induction,
the assembled fixed-iteration MPI grid represents the same Jacobi sequence.

In convergence mode, the global maximum of local maxima equals the maximum over
the entire interior. Consequently the serial and distributed stopping tests
apply to the same iterate and mathematical norm. Numerical comparison is still
required because compilation and floating-point details can affect actual output.

The final swap leaves halos that may belong to an earlier iterate, so the solver
refreshes the current halos again before evaluating the residual. It computes

\[
R_\infty=\max_{i,j}|f_{i,j}-(4u_{i,j}-u_{i-1,j}-u_{i+1,j}
 -u_{i,j-1}-u_{i,j+1})/h^2|,
\]

and the maximum error against the manufactured continuum solution over owned
interiors, followed by global maximum reductions. The update norm, discrete
residual and continuum error measure different quantities and are reported
separately. A small update norm alone is not evidence that all three are small.

CSV export uses MPI_Gatherv because row counts can differ. Each rank sends only
owned rows, including physical boundary columns but excluding halo rows. Root
places them at their global row displacements in a zero-initialized complete
grid. This includes every interior exactly once and inserts each physical
boundary row once. The implementation bounds counts and displacements to the
supported MPI integer range. Only root prints the primary JSON result.

## Numerical validation protocol

The automated validator compares both symmetric and asymmetric manufactured
solutions against A's serial executable. The asymmetric mode is particularly
useful for detecting wrong y-coordinate offsets or reversed row ordering.
Cases include P=1; N=10,P=3; N=P; odd and even iteration counts; converged solves;
and intentionally exhausted solves. Additional serial/MPI comparisons include
N=2,K=1, N=10,K=100 and N=32,K=500. Full-grid values use the agreed tolerance
|u_MPI-u_serial| <= 1e-10 + 1e-8|u_serial|, with no automatic relaxation.
The validator checks boundaries, JSON fields, actual ranks, iteration counts,
final update norms, residuals and errors. Invalid inputs and attempts to overwrite
an existing CSV must fail without leaving peers blocked.

An independent MPI continuum-refinement test uses N=15,31,63 with the asymmetric
solution and update tolerance 1e-13. It requires a final residual below 2e-8 and
error ratios between 3.8 and 4.2 under halving of h, consistent with a
second-order discretization. These are prescribed checks, not results obtained
in this session. A also supplies independent discrete eigenmode tests for the
serial reference.

Actual validation evidence will be stored in validation.json, including binary
hashes, commands, raw stdout/stderr, maximum grid differences and diagnostics.
No numerical pass rate or measured error is stated until that file is produced
by an actual MPI run and reviewed.

## Timing and strong-scaling protocol

Initialization, allocation and construction of the forcing array occur before
timing. MPI_Barrier synchronizes the timing start; MPI_Wtime measures the complete
iteration loop independently on each rank. The first and subsequent halo
exchanges, local updates, swaps and convergence reductions are included. The
reported solve time is the maximum elapsed time across ranks. The timing
reduction itself, final halo refresh, diagnostics, gathering and file output
are excluded. The serial reference times the corresponding iteration loop.

The planned single-node sweep uses N=256,512,1024, fixed K=1000, the asymmetric
problem and P=1,2,4,8. The active PBS allocation and physical-core availability
are checked, each MPI rank uses one thread, and Open MPI binds ranks to cores
without oversubscription. The serial baseline runs on the same compute node
with a one-process binding policy. One warmup and at least three fresh runs are
performed per configuration; measurement order rotates across repetitions.

Define T_s as the median serial solve time and T_P as the median P-rank MPI time:

\[
S(P)=T_s/T_P,\qquad E(P)=S(P)/P.
\]

T_MPI(1)/T_MPI(P) is retained as a separate measure of MPI scaling; it is not
substituted for serial-relative speedup. Runtime figures show median times and
min–max ranges. Speedup and efficiency ranges hold the serial median fixed and
transform MPI extrema; they are descriptive ranges, not confidence intervals.
P counts actively used compute cores. The eight-core reservation made for the
entire sweep is separately recorded and should not be confused with active-core
efficiency.

The raw records preserve every measured solver JSON and launcher stderr.
Metadata records node/allocation, CPU details, compiler and MPI versions, source
revision and working-tree status, binary hashes and the validation evidence hash.
Only same-node validated binaries can enter the benchmark script. Analysis
regenerates summaries and figures from raw measurements and rejects incomplete
or inconsistent sweeps.

## Performance model and pending interpretation

Ignoring row remainders, each rank performs O(KN²/P) stencil work. A middle rank
sends two N+2-element rows per iteration and receives two; a boundary rank has
one neighbor. A simple qualitative fixed-mode model is

\[
T_P \approx K\left(cN^2/P+2\alpha+2\beta(N+2)\right),
\]

where c denotes effective local stencil cost, alpha message latency and beta
effective cost per transmitted double. This model treats each Sendrecv as one
effective neighbor-exchange phase and omits topology, bandwidth contention,
protocol effects and overlap. It is not a fitted prediction. Convergence mode
adds a global-reduction cost each iteration and is not mixed into the fixed-work
strong-scaling sweep.

Increasing P reduces local compute work while the row-message length remains
constant. Communication, synchronization and memory-bandwidth limits can thus
restrict scaling, especially for smaller N. Larger N can improve the
compute-to-communication ratio, but may change cache and memory behavior. Row
remainder imbalance is at most one row. Its significance depends on N/P.
The blocking baseline does not overlap halo transfers with interior updates.

The runtime, speedup and efficiency figures will be generated from actual Vanda
data by scripts/analyze_mpi.py. The final interpretation must identify measured
speedups and variability before discussing candidate bottlenecks. The current
instrumentation does not isolate communication time or memory bandwidth, so it
cannot by itself establish either as the dominant cause of a plateau. No scaling
outcome is claimed until those measurements are available.

## AI assistance

ChatGPT assisted with source inspection, MPI implementation, validation and
benchmark tooling, analysis code and this technical draft. A's mathematical
contract and serial source were retained; C's existing launch/allocation
utilities were reused with commit attribution in the handoff. Local Python
tooling checks are separate from cluster solver validation. Students must review
the source, execute and inspect Vanda/Atlas validation and experiments, and
replace pending experimental statements with verified results before submission.
