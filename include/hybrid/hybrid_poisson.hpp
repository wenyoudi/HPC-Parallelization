#pragma once
#include "mpi_poisson.hpp"

namespace poisson {
struct HybridResult {
    Result numerical;
    int omp_threads=0;
    int mpi_thread_provided=0; // Minimum support level over all ranks.
};
HybridResult solve_hybrid(const Options& options, MPI_Comm comm);
void print_hybrid_result(const Options& options, const HybridResult& result, int ranks);
} // namespace poisson
