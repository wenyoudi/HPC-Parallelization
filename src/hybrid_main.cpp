#include "hybrid_poisson.hpp"
#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
    int provided=MPI_THREAD_SINGLE;
    if (MPI_Init_thread(&argc,&argv,MPI_THREAD_FUNNELED,&provided)!=MPI_SUCCESS) return 2;
    int rank=0, ranks=0;
    try {
        poisson::mpi_check(MPI_Comm_set_errhandler(MPI_COMM_WORLD,MPI_ERRORS_RETURN),"Set error handler");
        poisson::mpi_check(MPI_Comm_rank(MPI_COMM_WORLD,&rank),"Comm_rank");
        poisson::mpi_check(MPI_Comm_size(MPI_COMM_WORLD,&ranks),"Comm_size");
        if (provided<MPI_THREAD_FUNNELED) throw std::runtime_error("MPI_THREAD_FUNNELED unavailable");
        if (argc==2 && std::string(argv[1])=="--help") {
            if (rank==0) {
                std::cout << "Hybrid solver: mpirun -n R hybrid; R<=N; set OMP_NUM_THREADS.\n";
                poisson::print_help();
            }
            return MPI_Finalize()==MPI_SUCCESS ? 0 : 2;
        }
        const auto options=poisson::parse_options(argc,argv);
        const auto result=poisson::solve_hybrid(options,MPI_COMM_WORLD);
        int output_error=0;
        if (rank==0) {
            try { poisson::write_csv(options,result.numerical); }
            catch (const std::exception& error) {
                std::cerr << "Error: " << error.what() << '\n'; output_error=2;
            }
        }
        poisson::mpi_check(MPI_Bcast(&output_error,1,MPI_INT,0,MPI_COMM_WORLD),"Output status");
        if (!output_error && rank==0) poisson::print_hybrid_result(options,result,ranks);
        const int status=output_error ? 2 : (options.mode=="converge" && !result.numerical.converged ? 3 : 0);
        return MPI_Finalize()==MPI_SUCCESS ? status : 2;
    } catch (const std::exception& error) {
        std::cerr << "Error: rank " << rank << ": " << error.what() << '\n';
        MPI_Abort(MPI_COMM_WORLD,2);
        return 2;
    }
}
