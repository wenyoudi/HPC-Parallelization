#pragma once
#include "poisson.hpp"
#include <mpi.h>

namespace poisson {
// Public handoff to the hybrid implementation. MPI calls stay on the main thread.
struct RowDomain {
    int rank, ranks, n, stride, local_rows, global_first, upper, lower;
};
void mpi_check(int status, const char* operation);
RowDomain decompose_rows(std::size_t n, MPI_Comm comm);
// Exchanges full rows of the CURRENT buffer, including zero boundary columns.
// Tags 100/101; blocking Sendrecv, no outstanding buffer ownership on return.
void exchange_halos(std::vector<double>& current, const RowDomain& d, MPI_Comm comm);
Result solve_mpi(const Options& options, MPI_Comm comm);
void print_mpi_result(const Options& options, const Result& result, int ranks);
} // namespace poisson
