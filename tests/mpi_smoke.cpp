// Environment test only. This is not Member B's MPI Poisson solver.
#include <mpi.h>
#include <algorithm>
#include <array>
#include <iostream>
#include <string>
#include <vector>
#ifdef __linux__
#include <sched.h>
#endif

namespace {
void check(int result, const char* call) {
    if (result != MPI_SUCCESS) {
        char error[MPI_MAX_ERROR_STRING];
        int length = 0;
        MPI_Error_string(result, error, &length);
        std::cerr << call << ": " << std::string(error, length) << '\n';
        MPI_Abort(MPI_COMM_WORLD, result);
    }
}
std::string quote(const char* input) {
    std::string out = "\"";
    for (const unsigned char c : std::string(input)) {
        if (c == '"' || c == '\\') out += '\\';
        if (c >= 32) out += static_cast<char>(c);
    }
    return out + '"';
}
}

int main(int argc, char** argv) {
    int provided = MPI_THREAD_SINGLE;
    if (MPI_Init_thread(&argc, &argv, MPI_THREAD_FUNNELED, &provided) != MPI_SUCCESS)
        return 1;
    check(MPI_Comm_set_errhandler(MPI_COMM_WORLD, MPI_ERRORS_RETURN), "set_errhandler");
    int rank = 0, size = 0;
    check(MPI_Comm_rank(MPI_COMM_WORLD, &rank), "rank");
    check(MPI_Comm_size(MPI_COMM_WORLD, &size), "size");
    int local_ok = provided >= MPI_THREAD_FUNNELED;
    int min_provided = MPI_THREAD_SINGLE;
    check(MPI_Allreduce(&provided,&min_provided,1,MPI_INT,MPI_MIN,MPI_COMM_WORLD), "thread support reduction");
    int contribution = rank+1, sum = 0;
    check(MPI_Allreduce(&contribution, &sum, 1, MPI_INT, MPI_SUM, MPI_COMM_WORLD), "allreduce");
    if (sum != size*(size+1)/2) local_ok = 0;
    int received = -1;
    check(MPI_Sendrecv(&rank, 1, MPI_INT, (rank+1)%size, 17,
                      &received, 1, MPI_INT, (rank+size-1)%size, 17,
                      MPI_COMM_WORLD, MPI_STATUS_IGNORE), "ring sendrecv");
    if (received != (rank+size-1)%size) local_ok = 0;
    std::array<char, MPI_MAX_PROCESSOR_NAME+1> host{};
    int length = 0;
    check(MPI_Get_processor_name(host.data(), &length), "processor_name");
    std::vector<char> hosts(size*host.size());
    check(MPI_Allgather(host.data(), static_cast<int>(host.size()), MPI_CHAR,
                        hosts.data(), static_cast<int>(host.size()), MPI_CHAR, MPI_COMM_WORLD), "host gather");
    constexpr int cpu_limit = 4096;
    std::array<int, cpu_limit> cpus{};
#ifdef __linux__
    cpu_set_t mask;
    CPU_ZERO(&mask);
    if (sched_getaffinity(0, sizeof(mask), &mask) != 0) local_ok = 0;
    for (int cpu=0; cpu<std::min(CPU_SETSIZE,cpu_limit); ++cpu)
        cpus[cpu] = CPU_ISSET(cpu, &mask) ? 1 : 0;
    if (std::count(cpus.begin(),cpus.end(),1) == 0) local_ok = 0;
#else
    local_ok = 0; // This test explicitly verifies Linux compute-node affinity.
#endif
    std::vector<int> all_cpus(size*cpu_limit);
    check(MPI_Allgather(cpus.data(),cpu_limit,MPI_INT,all_cpus.data(),cpu_limit,MPI_INT,MPI_COMM_WORLD), "affinity gather");
    for (int r=1; r<size; ++r)
        if (std::string(hosts.data()+r*host.size()) != std::string(hosts.data())) local_ok = 0;
    // Each rank's core binding must have a disjoint OS CPU set. SMT siblings
    // can both appear within a single rank's binding to one physical core.
    for (int cpu=0; cpu<cpu_limit; ++cpu) {
        int users = 0;
        for (int r=0; r<size; ++r) users += all_cpus[r*cpu_limit+cpu];
        if (users>1) local_ok = 0;
    }
    int success = 0;
    check(MPI_Allreduce(&local_ok,&success,1,MPI_INT,MPI_MIN,MPI_COMM_WORLD), "status reduction");
    if (rank == 0) {
        for (int r=0; r<size; ++r) {
            std::cout << "{\"test\":\"mpi_rank\",\"mpi_ranks\":" << size << ",\"rank\":" << r
                      << ",\"hostname\":" << quote(hosts.data()+r*host.size()) << ",\"os_cpus\":[";
            bool comma = false;
            for (int cpu=0; cpu<cpu_limit; ++cpu) if (all_cpus[r*cpu_limit+cpu]) {
                if (comma) std::cout << ',';
                std::cout << cpu;
                comma = true;
            }
            std::cout << "]}\n";
        }
        std::cout << "{\"test\":\"mpi_smoke\",\"mpi_ranks\":" << size
                  << ",\"thread_required\":" << MPI_THREAD_FUNNELED
                  << ",\"thread_provided_rank0\":" << provided
                  << ",\"thread_provided_min\":" << min_provided
                  << ",\"allreduce_sum\":" << sum
                  << ",\"success\":" << (success?"true":"false") << "}\n";
    }
    check(MPI_Finalize(), "finalize");
    return success ? 0 : 2;
}
