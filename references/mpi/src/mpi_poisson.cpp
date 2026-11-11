#include "mpi_poisson.hpp"
#include <algorithm>
#include <cmath>
#include <climits>
#include <iomanip>
#include <iostream>
#include <stdexcept>

namespace poisson {
void mpi_check(int status, const char* operation) {
    if (status == MPI_SUCCESS) return;
    char message[MPI_MAX_ERROR_STRING];
    int length = 0;
    MPI_Error_string(status, message, &length);
    throw std::runtime_error(std::string(operation) + ": " + std::string(message, length));
}

RowDomain decompose_rows(std::size_t n, MPI_Comm comm) {
    RowDomain d{};
    mpi_check(MPI_Comm_rank(comm, &d.rank), "Comm_rank");
    mpi_check(MPI_Comm_size(comm, &d.ranks), "Comm_size");
    // Gatherv uses int counts/displacements. Bound the complete grid, even
    // without CSV, so the supported domain does not depend on output choices.
    if (n > static_cast<std::size_t>(INT_MAX - 2) ||
        (n + 2) > static_cast<std::size_t>(INT_MAX) / (n + 2))
        throw std::invalid_argument("Grid exceeds supported MPI int counts/displacements");
    if (n < static_cast<std::size_t>(d.ranks))
        throw std::invalid_argument("MPI ranks must not exceed N");
    d.n = static_cast<int>(n);
    d.stride = d.n + 2;
    const int base = d.n / d.ranks, extra = d.n % d.ranks;
    d.local_rows = base + (d.rank < extra);
    d.global_first = 1 + d.rank * base + std::min(d.rank, extra);
    d.upper = d.rank == 0 ? MPI_PROC_NULL : d.rank - 1;
    d.lower = d.rank + 1 == d.ranks ? MPI_PROC_NULL : d.rank + 1;
    return d;
}

void exchange_halos(std::vector<double>& u, const RowDomain& d, MPI_Comm comm) {
    const auto s = static_cast<std::size_t>(d.stride);
    // PROC_NULL receives leave buffers unchanged; explicitly preserve physical
    // boundaries so the function remains safe for reuse in hybrid code.
    if (d.upper == MPI_PROC_NULL) std::fill_n(u.data(), s, 0.0);
    if (d.lower == MPI_PROC_NULL)
        std::fill_n(u.data() + (d.local_rows + 1) * s, s, 0.0);
    mpi_check(MPI_Sendrecv(u.data() + s, d.stride, MPI_DOUBLE, d.upper, 100,
        u.data() + (d.local_rows + 1) * s, d.stride, MPI_DOUBLE, d.lower, 100,
        comm, MPI_STATUS_IGNORE), "Sendrecv upper interior/lower halo");
    mpi_check(MPI_Sendrecv(u.data() + d.local_rows * s, d.stride, MPI_DOUBLE, d.lower, 101,
        u.data(), d.stride, MPI_DOUBLE, d.upper, 101,
        comm, MPI_STATUS_IGNORE), "Sendrecv lower interior/upper halo");
}

Result solve_mpi(const Options& o, MPI_Comm comm) {
    const auto d = decompose_rows(o.n, comm);
    const auto s = static_cast<std::size_t>(d.stride);
    const double h = 1.0 / (o.n + 1), h2 = h * h;
    std::vector<double> old((d.local_rows + 2) * s, 0.0), next(old), forcing(old);
    for (int i = 1; i <= d.local_rows; ++i)
        for (int j = 1; j <= d.n; ++j)
            forcing[i*s+j] = rhs(j*h, (d.global_first+i-1)*h, o.problem);
    Result r;
    const bool check = o.mode == "converge";
    const auto count = check ? o.max_iters : o.iterations;
    mpi_check(MPI_Barrier(comm), "Timing barrier");
    const double start = MPI_Wtime();
    for (std::size_t k = 0; k < count; ++k) {
        exchange_halos(old, d, comm);
        double change = 0.0;
        for (int i = 1; i <= d.local_rows; ++i)
            for (int j = 1; j <= d.n; ++j) {
                const auto q = i*s+j;
                next[q] = 0.25 * (old[q-s] + old[q+s] + old[q-1] + old[q+1] + h2*forcing[q]);
                if (check) change = std::max(change, std::abs(next[q]-old[q]));
            }
        old.swap(next);
        ++r.iterations_completed;
        if (check) {
            mpi_check(MPI_Allreduce(&change, &r.max_update, 1, MPI_DOUBLE, MPI_MAX, comm), "Update maximum");
            if (r.max_update <= o.tol) { r.converged = true; break; }
        }
    }
    const double elapsed = MPI_Wtime() - start;
    mpi_check(MPI_Reduce(&elapsed, &r.solve_seconds, 1, MPI_DOUBLE, MPI_MAX, 0, comm), "Timing maximum");
    // The final swap invalidates neighbor halos: refresh before diagnostics.
    exchange_halos(old, d, comm);
    double local[2] = {0.0, 0.0}, global[2] = {0.0, 0.0};
    for (int i = 1; i <= d.local_rows; ++i)
        for (int j = 1; j <= d.n; ++j) {
            const auto q = i*s+j;
            const double au = (4*old[q]-old[q-s]-old[q+s]-old[q-1]-old[q+1])/h2;
            const double residual = std::abs(forcing[q]-au);
            const double error = std::abs(old[q]-exact(j*h, (d.global_first+i-1)*h, o.problem));
            if (!std::isfinite(old[q]) || !std::isfinite(residual) || !std::isfinite(error))
                throw std::runtime_error("Non-finite MPI solver result");
            local[0] = std::max(local[0], residual);
            local[1] = std::max(local[1], error);
        }
    mpi_check(MPI_Allreduce(local, global, 2, MPI_DOUBLE, MPI_MAX, comm), "Diagnostic maxima");
    r.residual_linf = global[0]; r.error_linf = global[1];
    if (!o.output.empty()) {
        std::vector<int> counts(d.ranks), offsets(d.ranks);
        for (int rank = 0; rank < d.ranks; ++rank) {
            const int base = d.n/d.ranks, extra = d.n%d.ranks;
            counts[rank] = (base+(rank<extra))*d.stride;
            offsets[rank] = (1+rank*base+std::min(rank,extra))*d.stride;
        }
        if (d.rank == 0) r.solution.assign(s*s, 0.0);
        mpi_check(MPI_Gatherv(old.data()+s, d.local_rows*d.stride, MPI_DOUBLE,
            d.rank == 0 ? r.solution.data() : nullptr, counts.data(), offsets.data(),
            MPI_DOUBLE, 0, comm), "Gather interior rows");
    }
    return r;
}

void print_mpi_result(const Options& o, const Result& r, int ranks) {
    std::cout << std::setprecision(17)
      << "{\"schema_version\":1,\"implementation\":\"mpi\",\"n\":" << o.n
      << ",\"mode\":\"" << o.mode << "\",\"problem\":\"" << o.problem
      << "\",\"mpi_ranks\":" << ranks << ",\"omp_threads\":1,\"iterations_completed\":" << r.iterations_completed
      << ",\"converged\":";
    if (o.mode == "fixed") std::cout << "null,\"max_update\":null,\"tol\":null";
    else std::cout << (r.converged ? "true" : "false") << ",\"max_update\":" << r.max_update << ",\"tol\":" << o.tol;
    std::cout << ",\"solve_seconds\":" << r.solve_seconds << ",\"residual_linf\":" << r.residual_linf
              << ",\"error_linf\":" << r.error_linf << "}\n";
}
} // namespace poisson
