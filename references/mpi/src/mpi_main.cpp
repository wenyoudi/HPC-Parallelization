#include "mpi_poisson.hpp"
#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
    int provided = 0;
    if (MPI_Init_thread(&argc, &argv, MPI_THREAD_FUNNELED, &provided) != MPI_SUCCESS) return 2;
    int rank = 0, ranks = 0;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &ranks);
    try {
        poisson::mpi_check(MPI_Comm_set_errhandler(MPI_COMM_WORLD, MPI_ERRORS_RETURN), "Set error handler");
        if (provided < MPI_THREAD_FUNNELED) throw std::runtime_error("MPI_THREAD_FUNNELED unavailable");
        if (argc == 2 && std::string(argv[1]) == "--help") {
            if (rank == 0) std::cout << "MPI solver: launch with mpiexec -n R poisson_mpi; R <= N.\n";
            if (rank == 0) poisson::print_help();
            MPI_Finalize(); return 0;
        }
        const auto options = poisson::parse_options(argc, argv);
        const auto result = poisson::solve_mpi(options, MPI_COMM_WORLD);
        int output_error = 0;
        if (rank == 0) {
            try { poisson::write_csv(options, result); }
            catch (const std::exception& e) {
                std::cerr << "Error: " << e.what() << '\n'; output_error = 2;
            }
        }
        poisson::mpi_check(MPI_Bcast(&output_error, 1, MPI_INT, 0, MPI_COMM_WORLD), "Output status");
        if (!output_error && rank == 0) poisson::print_mpi_result(options, result, ranks);
        const int status = output_error ? 2 : (options.mode == "converge" && !result.converged ? 3 : 0);
        MPI_Finalize(); return status;
    } catch (const std::exception& e) {
        std::cerr << "Error: rank " << rank << ": " << e.what() << '\n';
        // Also handles a single-rank allocation/diagnostic failure: peers cannot
        // be left blocked in a collective or Sendrecv.
        MPI_Abort(MPI_COMM_WORLD, 2); return 2;
    }
}
