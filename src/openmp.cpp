#include "poisson.hpp"
#include "openmp_rows.hpp"

#include <chrono>
#include <iostream>
#include <omp.h>
#include <utility>

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--help") {
            std::cout << "Usage: openmp [--n N] [--mode fixed|converge] [--iterations K]\n"
                         "              [--tol T] [--max-iters M] [--output PATH]\n"
                         "              [--problem symmetric|asymmetric]\n"
                         "Defaults: N=128, converge, K=1000, tol=1e-8, max-iters=100000\n"
                         "Exit: 0 success, 1 invalid input/I/O, 2 non-convergence\n";
            return 0;
        }
        const auto o = poisson::parse(argc, argv);
        const int n = o.n;
        const std::size_t stride = static_cast<std::size_t>(n) + 2;
        const std::size_t cells = stride * stride;
        std::vector<double> a(cells, 0.0), b(cells, 0.0), scaled_rhs(cells, 0.0);
        const double h = 1.0 / (n + 1.0), h2 = h * h;
        #pragma omp parallel for schedule(static)
        for (int i = 1; i <= n; ++i)
            for (int j = 1; j <= n; ++j)
                scaled_rhs[static_cast<std::size_t>(i) * stride + j] = h2 * poisson::rhs(i, j, o);

        double* old_u = a.data();
        double* new_u = b.data();
        double max_update = 0.0;
        int completed = 0, threads = 0;
        bool converged = false;
        const bool check = o.mode == "converge";
        const int limit = check ? o.max_iters : o.iterations;
        const auto begin = std::chrono::steady_clock::now();
        // Persistent team: each omp-for completes before the single buffer swap;
        // the single barrier publishes both pointers and the shared stop decision.
        #pragma omp parallel shared(old_u,new_u,max_update,completed,threads,converged)
        {
            #pragma omp single
            threads = omp_get_num_threads();
            for (int k = 0; k < limit; ++k) {
                if (check) {
                    #pragma omp single
                    max_update = 0.0;
                    #pragma omp for schedule(static) reduction(max:max_update)
                    for (int i = 1; i <= n; ++i)
                        max_update = std::max(max_update,
                            poisson::update_row<true>(old_u, new_u, scaled_rhs.data(), i, n));
                } else {
                    #pragma omp for schedule(static)
                    for (int i = 1; i <= n; ++i)
                        poisson::update_row<false>(old_u, new_u, scaled_rhs.data(), i, n);
                }
                #pragma omp single
                {
                    std::swap(old_u, new_u);
                    ++completed;
                    if (check) converged = max_update <= o.tol;
                }
                if (converged) break;
            }
        }
        const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();

        double residual = 0.0, error = 0.0;
        #pragma omp parallel for schedule(static) reduction(max:residual,error)
        for (int i = 1; i <= n; ++i) {
            for (int j = 1; j <= n; ++j) {
                const std::size_t p = static_cast<std::size_t>(i) * stride + j;
                const double ahu = (4 * old_u[p] - old_u[p - stride] - old_u[p + stride] -
                                    old_u[p - 1] - old_u[p + 1]) / h2;
                residual = std::max(residual, std::abs(poisson::rhs(i, j, o) - ahu));
                error = std::max(error, std::abs(old_u[p] - poisson::exact(i, j, o)));
            }
        }
        if (!o.output.empty()) poisson::write_csv(o.output, old_u, n);
        std::cout << std::setprecision(17)
                  << "{\"implementation\":\"openmp\",\"N\":" << n
                  << ",\"mode\":\"" << o.mode << "\",\"mpi_ranks\":1,\"omp_threads\":" << threads
                  << ",\"iterations_completed\":" << completed << ",\"converged\":";
        if (check) std::cout << (converged ? "true" : "false");
        else std::cout << "null";
        std::cout << ",\"solve_seconds\":" << seconds << ",\"max_update\":";
        if (check) std::cout << max_update;
        else std::cout << "null";
        std::cout << ",\"residual_linf\":" << residual << ",\"error_linf\":" << error
                  << ",\"problem\":\"" << (o.asymmetric ? "asymmetric" : "symmetric") << "\"}\n";
        if (check && !converged) {
            std::cerr << "Non-convergence: reached max-iters=" << o.max_iters << '\n';
            return 2;
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << '\n';
        return 1;
    }
}
