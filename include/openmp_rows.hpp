#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>

namespace poisson {
// Local row index; rhs_scaled contains h^2 f. Both arrays include halo rows.
// This kernel can be reused inside Member B's decomposition without any MPI calls.
template <bool TrackUpdate>
inline double update_row(const double* old_u, double* new_u, const double* rhs_scaled,
                         int row, int n) {
    const std::size_t stride = static_cast<std::size_t>(n) + 2;
    const std::size_t start = static_cast<std::size_t>(row) * stride;
    double max_update = 0.0;
    for (int j = 1; j <= n; ++j) {
        const std::size_t p = start + j;
        new_u[p] = (old_u[p - stride] + old_u[p + stride] +
                    old_u[p - 1] + old_u[p + 1] + rhs_scaled[p]) * 0.25;
        if constexpr (TrackUpdate)
            max_update = std::max(max_update, std::abs(new_u[p] - old_u[p]));
    }
    return max_update;
}

// Hybrid-ready local operation. Caller is the MPI main thread, outside any
// parallel region. Implicit join completes all writes before return/MPI/swap.
template <bool TrackUpdate>
inline double update_local_rows(const double* old_u, double* new_u,
                                const double* rhs_scaled, int local_rows, int n) {
    double max_update = 0.0;
    if constexpr (TrackUpdate) {
        #pragma omp parallel for schedule(static) reduction(max:max_update)
        for (int i = 1; i <= local_rows; ++i)
            max_update = std::max(max_update, update_row<true>(old_u, new_u, rhs_scaled, i, n));
    } else {
        #pragma omp parallel for schedule(static)
        for (int i = 1; i <= local_rows; ++i)
            update_row<false>(old_u, new_u, rhs_scaled, i, n);
    }
    return max_update;
}
} // namespace poisson
