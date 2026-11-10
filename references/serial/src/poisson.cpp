#include "poisson.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <set>
#include <stdexcept>

namespace poisson {
namespace {
constexpr double pi = 3.141592653589793238462643383279502884;
std::size_t positive_integer(const std::string& s) {
    if (s.empty() || s.find_first_not_of("0123456789") != std::string::npos)
        throw std::invalid_argument("Expected a positive integer: " + s);
    const auto v = std::stoull(s);
    if (v == 0 || v > std::numeric_limits<std::size_t>::max())
        throw std::invalid_argument("Integer out of range: " + s);
    return static_cast<std::size_t>(v);
}
void validate_size(std::size_t n) {
    const auto limit = std::numeric_limits<std::size_t>::max();
    if (n > limit - 2) throw std::invalid_argument("Grid size overflow");
    const auto stride = n + 2;
    if (stride > limit / stride || stride * stride > std::vector<double>().max_size() / 3)
        throw std::invalid_argument("Grid allocation size overflow");
}
}
Options parse_options(int argc, char** argv) {
    Options o;
    std::set<std::string> seen;
    for (int i = 1; i < argc; ++i) {
        const std::string key = argv[i];
        if (!seen.insert(key).second) throw std::invalid_argument("Repeated option: " + key);
        if (i + 1 >= argc) throw std::invalid_argument("Missing value for " + key);
        const std::string value = argv[++i];
        if (key == "--n") o.n = positive_integer(value);
        else if (key == "--iterations") o.iterations = positive_integer(value);
        else if (key == "--max-iters") o.max_iters = positive_integer(value);
        else if (key == "--mode") o.mode = value;
        else if (key == "--problem") o.problem = value;
        else if (key == "--output") {
            if (value.empty() || value.rfind("--", 0) == 0)
                throw std::invalid_argument("Invalid output path");
            o.output = value;
        } else if (key == "--tol") {
            std::size_t end = 0;
            o.tol = std::stod(value, &end);
            if (end != value.size() || !std::isfinite(o.tol) || o.tol <= 0)
                throw std::invalid_argument("Tolerance must be finite and positive");
        } else throw std::invalid_argument("Unknown option: " + key);
    }
    if (o.mode != "fixed" && o.mode != "converge")
        throw std::invalid_argument("Mode must be fixed or converge");
    if (o.problem != "symmetric" && o.problem != "asymmetric")
        throw std::invalid_argument("Problem must be symmetric or asymmetric");
    if (o.mode == "converge" && seen.count("--iterations"))
        throw std::invalid_argument("Use --max-iters with converge mode");
    if (o.mode == "fixed" && (seen.count("--tol") || seen.count("--max-iters")))
        throw std::invalid_argument("--tol and --max-iters require converge mode");
    validate_size(o.n);
    return o;
}
void print_help() {
    std::cout << "Usage: poisson_serial [--n N] [--problem symmetric|asymmetric]\n"
              << "  --mode fixed [--iterations K]\n"
              << "  --mode converge [--tol T] [--max-iters M]\n"
              << "  [--output solution.csv]\n"
              << "Defaults: N=32, problem=symmetric, mode=fixed, K=1000, tol=1e-8, M=100000.\n";
}
double exact(double x, double y, const std::string& problem) {
    return std::sin(pi * x) * std::sin((problem == "asymmetric" ? 2.0 : 1.0) * pi * y);
}
double rhs(double x, double y, const std::string& problem) {
    return (problem == "asymmetric" ? 5.0 : 2.0) * pi * pi * exact(x, y, problem);
}
Result solve_serial(const Options& o) {
    validate_size(o.n);
    const auto n = o.n, stride = n + 2;
    const double h = 1.0 / static_cast<double>(n + 1), h2 = h * h;
    std::vector<double> old(stride * stride, 0.0), next(old), forcing(old);
    for (std::size_t i = 1; i <= n; ++i)
        for (std::size_t j = 1; j <= n; ++j)
            forcing[i * stride + j] = rhs(j * h, i * h, o.problem);
    Result r;
    const bool check = o.mode == "converge";
    const auto count = check ? o.max_iters : o.iterations;
    const auto start = std::chrono::steady_clock::now();
    for (std::size_t k = 0; k < count; ++k) {
        double change = 0;
        for (std::size_t i = 1; i <= n; ++i) {
            for (std::size_t j = 1; j <= n; ++j) {
                const auto q = i * stride + j;
                next[q] = 0.25 * (old[q-stride] + old[q+stride] + old[q-1] + old[q+1] + h2 * forcing[q]);
                if (check) change = std::max(change, std::abs(next[q] - old[q]));
            }
        }
        old.swap(next);
        ++r.iterations_completed;
        if (check) {
            r.max_update = change;
            if (change <= o.tol) { r.converged = true; break; }
        }
    }
    r.solve_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    // Diagnostics are deliberately outside the solver timing region.
    for (std::size_t i = 1; i <= n; ++i) {
        for (std::size_t j = 1; j <= n; ++j) {
            const auto q = i * stride + j;
            const double au = (4 * old[q] - old[q-stride] - old[q+stride] - old[q-1] - old[q+1]) / h2;
            r.residual_linf = std::max(r.residual_linf, std::abs(forcing[q] - au));
            r.error_linf = std::max(r.error_linf, std::abs(old[q] - exact(j*h, i*h, o.problem)));
            if (!std::isfinite(old[q]) || !std::isfinite(au))
                throw std::runtime_error("Non-finite solver result");
        }
    }
    r.solution = std::move(old);
    return r;
}
void write_csv(const Options& o, const Result& r) {
    if (o.output.empty()) return;
    // Refuse existing files to avoid accidentally destroying reference solutions.
    std::ifstream existing(o.output);
    if (existing.good()) throw std::runtime_error("Output already exists: " + o.output);
    std::ofstream file(o.output);
    if (!file) throw std::runtime_error("Cannot open output: " + o.output);
    file << std::setprecision(17);
    const auto stride = o.n + 2;
    for (std::size_t i = 0; i < stride; ++i) {
        for (std::size_t j = 0; j < stride; ++j) {
            if (j) file << ',';
            file << r.solution[i * stride + j];
        }
        file << '\n';
    }
    file.flush();
    if (!file) throw std::runtime_error("Failed writing output: " + o.output);
}
void print_result(const Options& o, const Result& r) {
    std::cout << std::setprecision(17)
      << "{\"schema_version\":1,\"implementation\":\"serial\",\"n\":" << o.n
      << ",\"mode\":\"" << o.mode << "\",\"problem\":\"" << o.problem
      << "\",\"mpi_ranks\":1,\"omp_threads\":1,\"iterations_completed\":" << r.iterations_completed
      << ",\"converged\":";
    if (o.mode == "fixed") std::cout << "null,\"max_update\":null,\"tol\":null";
    else std::cout << (r.converged ? "true" : "false") << ",\"max_update\":" << r.max_update << ",\"tol\":" << o.tol;
    std::cout << ",\"solve_seconds\":" << r.solve_seconds
      << ",\"residual_linf\":" << r.residual_linf << ",\"error_linf\":" << r.error_linf << "}\n";
}
} // namespace poisson
