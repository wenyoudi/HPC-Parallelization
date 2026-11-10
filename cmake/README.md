# Pending Member B integration hook

No MPI Poisson or hybrid implementation is supplied by this infrastructure.

When Member B's source is available, inspect and reuse its decomposition, halos,
global metrics, gather and error handling. Add a real `DistributedSolvers.cmake`
in this directory, defining executable target `mpi` and (after integration)
`hybrid`, with output paths `${CMAKE_BINARY_DIR}/mpi` and `/hybrid`.
Link the verified `MPI::MPI_CXX`; link hybrid to `OpenMP::OpenMP_CXX` too.
Use the common C++17 Release -O3 configuration, without fast-math.
Do not create a stub executable or a competing MPI framework to satisfy this hook.

PBS job kinds `mpi-validate`, `hybrid-validate`, and `hybrid` are deliberately
blocked until that tracked integration file exists. Configuration then requires
real targets; validation requires actual serial/MPI/hybrid executable files.
The hybrid benchmark reruns numerical validation in the same job and requires a
successful evidence report matching exact serial/hybrid binary hashes, launch
mode and each rank/thread configuration before it starts timing.

Use `references/serial/poisson_serial` under the build directory as Member A's
pinned, unmodified reference. It forms h²*f inside each update; agree that work
with Member B and use the same arithmetic/timing scope for hybrid comparisons.
Preserve existing OpenMP code/results, whose RHS was pre-scaled outside timing.
