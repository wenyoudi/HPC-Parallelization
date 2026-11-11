# MPI and hybrid build integration

`DistributedSolvers.cmake` builds B's MPI-only target `mpi` from the verbatim
source snapshot under `references/mpi/`, linked to A's unchanged `poisson_core`.
It separately builds `hybrid` from `src/hybrid_main.cpp` and
`src/hybrid_poisson.cpp`, linking B's exact decomposition/halo functions and
OpenMP. No upstream CMake file or script is merged.

Enable with `-DBUILD_DISTRIBUTED_SOLVERS=ON -DCMAKE_BUILD_TYPE=Release`.
This also enables A's serial reference. Outputs are `${CMAKE_BINARY_DIR}/mpi`,
`/hybrid` and `/references/serial/poisson_serial`.

The hybrid include path is `include/hybrid/`, not root `include/`: A/B and the
standalone OpenMP solver have different `poisson.hpp` interfaces. The original
OpenMP target and kernels are unchanged. The new unscaled-forcing overload in
`include/hybrid/local_rows.hpp` forms h²*f inside each stencil, matching A/B.

PBS jobs `mpi-validate`, `hybrid-validate` and `hybrid` build real targets and run
correctness checks. Hybrid timing requires a successful Vanda receipt matching
serial/hybrid binary hashes, launcher mode and every benchmark configuration.
Local validation receipts cannot authorize Vanda timing. Only the main thread
calls MPI; each local OpenMP update joins before swaps/communication.
