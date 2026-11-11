#pragma once
#include "../openmp_rows.hpp"

namespace poisson {
// Compatible overload for A/B's UNSCALED forcing. The original scaled-RHS
// functions remain untouched. Form h²*f in the stencil, matching both baselines.
template <bool TrackUpdate>
inline double update_unscaled_row(const double* old_u, double* new_u, const double* forcing,
                                  int row, int n, double h2) {
    const std::size_t stride = static_cast<std::size_t>(n)+2;
    const std::size_t start = static_cast<std::size_t>(row)*stride;
    double change = 0.0;
    for (int j=1; j<=n; ++j) {
        const std::size_t p=start+j;
        new_u[p]=0.25*(old_u[p-stride]+old_u[p+stride]+old_u[p-1]+old_u[p+1]+h2*forcing[p]);
        if constexpr (TrackUpdate)
            change=std::max(change,std::abs(new_u[p]-old_u[p]));
    }
    return change;
}

template <bool TrackUpdate>
inline double update_local_rows(const double* old_u, double* new_u, const double* forcing,
                                int rows, int n, double h2) {
    double change=0.0;
    if constexpr (TrackUpdate) {
        #pragma omp parallel for schedule(static) reduction(max:change)
        for (int i=1; i<=rows; ++i)
            change=std::max(change,update_unscaled_row<true>(old_u,new_u,forcing,i,n,h2));
    } else {
        #pragma omp parallel for schedule(static)
        for (int i=1; i<=rows; ++i)
            update_unscaled_row<false>(old_u,new_u,forcing,i,n,h2);
    }
    // Implicit join completes all writes before the main thread swaps or calls MPI.
    return change;
}
} // namespace poisson
