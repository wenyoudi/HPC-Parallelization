#include "hybrid_poisson.hpp"
#include "local_rows.hpp"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <omp.h>
#include <stdexcept>

namespace poisson {
HybridResult solve_hybrid(const Options& o, MPI_Comm comm) {
    if (omp_in_parallel()) throw std::runtime_error("Hybrid solve must be called outside an OpenMP region");
    int is_main=0, provided=MPI_THREAD_SINGLE;
    mpi_check(MPI_Is_thread_main(&is_main),"Is_thread_main");
    mpi_check(MPI_Query_thread(&provided),"Query_thread");
    if (!is_main || provided<MPI_THREAD_FUNNELED)
        throw std::runtime_error("Hybrid requires the MPI main thread and MPI_THREAD_FUNNELED");
    // B's exact public decomposition and halo exchange are linked unchanged.
    const auto d=decompose_rows(o.n,comm);
    const auto s=static_cast<std::size_t>(d.stride);
    const double h=1.0/(o.n+1), h2=h*h;
    std::vector<double> old((d.local_rows+2)*s,0.0), next(old), forcing(old);
    for (int i=1; i<=d.local_rows; ++i)
        for (int j=1; j<=d.n; ++j)
            forcing[i*s+j]=rhs(j*h,(d.global_first+i-1)*h,o.problem);
    HybridResult result;
    auto& r=result.numerical;
    // Keep the team size stable and verify the actual size on every rank, before timing.
    omp_set_dynamic(0);
    int threads=0, minimum=0, maximum=0;
    #pragma omp parallel
    {
        #pragma omp single
        threads=omp_get_num_threads();
    }
    mpi_check(MPI_Allreduce(&threads,&minimum,1,MPI_INT,MPI_MIN,comm),"Minimum team size");
    mpi_check(MPI_Allreduce(&threads,&maximum,1,MPI_INT,MPI_MAX,comm),"Maximum team size");
    if (minimum!=maximum) throw std::runtime_error("OpenMP team sizes differ between MPI ranks");
    result.omp_threads=minimum;
    mpi_check(MPI_Allreduce(&provided,&result.mpi_thread_provided,1,MPI_INT,MPI_MIN,comm),"Thread support minimum");
    const bool check=o.mode=="converge";
    const auto count=check ? o.max_iters : o.iterations;
    mpi_check(MPI_Barrier(comm),"Timing barrier");
    const double start=MPI_Wtime();
    for (std::size_t k=0; k<count; ++k) {
        exchange_halos(old,d,comm);
        const double change=check
            ? update_local_rows<true>(old.data(),next.data(),forcing.data(),d.local_rows,d.n,h2)
            : update_local_rows<false>(old.data(),next.data(),forcing.data(),d.local_rows,d.n,h2);
        old.swap(next);
        ++r.iterations_completed;
        if (check) {
            mpi_check(MPI_Allreduce(&change,&r.max_update,1,MPI_DOUBLE,MPI_MAX,comm),"Update maximum");
            if (r.max_update<=o.tol) { r.converged=true; break; }
        }
    }
    const double elapsed=MPI_Wtime()-start;
    mpi_check(MPI_Reduce(&elapsed,&r.solve_seconds,1,MPI_DOUBLE,MPI_MAX,0,comm),"Timing maximum");
    // Diagnostics/gather follow B's proven indexing and are outside solve timing.
    exchange_halos(old,d,comm);
    double local[2]={0.0,0.0}, global[2]={0.0,0.0};
    for (int i=1; i<=d.local_rows; ++i)
        for (int j=1; j<=d.n; ++j) {
            const auto q=i*s+j;
            const double au=(4*old[q]-old[q-s]-old[q+s]-old[q-1]-old[q+1])/h2;
            const double residual=std::abs(forcing[q]-au);
            const double error=std::abs(old[q]-exact(j*h,(d.global_first+i-1)*h,o.problem));
            if (!std::isfinite(old[q]) || !std::isfinite(residual) || !std::isfinite(error))
                throw std::runtime_error("Non-finite hybrid solver result");
            local[0]=std::max(local[0],residual);
            local[1]=std::max(local[1],error);
        }
    mpi_check(MPI_Allreduce(local,global,2,MPI_DOUBLE,MPI_MAX,comm),"Diagnostic maxima");
    r.residual_linf=global[0]; r.error_linf=global[1];
    if (!o.output.empty()) {
        std::vector<int> counts(d.ranks), offsets(d.ranks);
        for (int rank=0; rank<d.ranks; ++rank) {
            const int base=d.n/d.ranks, extra=d.n%d.ranks;
            counts[rank]=(base+(rank<extra))*d.stride;
            offsets[rank]=(1+rank*base+std::min(rank,extra))*d.stride;
        }
        if (d.rank==0) r.solution.assign(s*s,0.0);
        mpi_check(MPI_Gatherv(old.data()+s,d.local_rows*d.stride,MPI_DOUBLE,
            d.rank==0 ? r.solution.data() : nullptr,counts.data(),offsets.data(),
            MPI_DOUBLE,0,comm),"Gather interior rows");
    }
    return result;
}

void print_hybrid_result(const Options& o, const HybridResult& h, int ranks) {
    const auto& r=h.numerical;
    std::cout << std::setprecision(17)
        << "{\"schema_version\":1,\"implementation\":\"hybrid\",\"n\":" << o.n
        << ",\"mode\":\"" << o.mode << "\",\"problem\":\"" << o.problem
        << "\",\"mpi_ranks\":" << ranks << ",\"omp_threads\":" << h.omp_threads
        << ",\"mpi_thread_required\":" << MPI_THREAD_FUNNELED
        << ",\"mpi_thread_provided\":" << h.mpi_thread_provided
        << ",\"rhs_storage\":\"unscaled\",\"iterations_completed\":" << r.iterations_completed
        << ",\"converged\":";
    if (o.mode=="fixed") std::cout << "null,\"max_update\":null,\"tol\":null";
    else std::cout << (r.converged?"true":"false") << ",\"max_update\":" << r.max_update << ",\"tol\":" << o.tol;
    std::cout << ",\"solve_seconds\":" << r.solve_seconds << ",\"residual_linf\":" << r.residual_linf
              << ",\"error_linf\":" << r.error_linf << "}\n";
}
} // namespace poisson
