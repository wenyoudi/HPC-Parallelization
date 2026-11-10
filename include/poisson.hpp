#pragma once
#include <cstddef>
#include <string>
#include <vector>

namespace poisson {
// Row i is y; column j is x. Boundaries are included in the serial storage.
struct Options {
    std::size_t n = 32;
    std::string mode = "fixed";
    std::string problem = "symmetric";
    std::size_t iterations = 1000;
    std::size_t max_iters = 100000;
    double tol = 1e-8;
    std::string output;
};
struct Result {
    std::vector<double> solution;
    std::size_t iterations_completed = 0;
    bool converged = false;
    double solve_seconds = 0;
    double max_update = 0;
    double residual_linf = 0;
    double error_linf = 0;
};
Options parse_options(int argc, char** argv);
void print_help();
double exact(double x, double y, const std::string& problem);
double rhs(double x, double y, const std::string& problem);
Result solve_serial(const Options& options);
void write_csv(const Options& options, const Result& result);
void print_result(const Options& options, const Result& result);
} // namespace poisson
