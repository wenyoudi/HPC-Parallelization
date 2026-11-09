#pragma once

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstddef>
#include <fstream>
#include <iomanip>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace poisson {
constexpr double pi = 3.141592653589793238462643383279502884;

struct Options {
    int n = 128;
    std::string mode = "converge";
    int iterations = 1000;
    double tol = 1e-8;
    int max_iters = 100000;
    std::string output;
    bool asymmetric = false; // Explicit validation extension; default problem unchanged.
};

inline int integer(const std::string& s, int minimum, const std::string& flag) {
    int v = 0;
    const auto parsed = std::from_chars(s.data(), s.data() + s.size(), v);
    if (parsed.ec != std::errc{} || parsed.ptr != s.data() + s.size() || v < minimum)
        throw std::invalid_argument(flag + " requires an integer >= " + std::to_string(minimum));
    return v;
}

inline Options parse(int argc, char** argv) {
    Options o;
    std::vector<std::string> seen;
    for (int k = 1; k < argc; ++k) {
        const std::string flag = argv[k];
        if (std::find(seen.begin(), seen.end(), flag) != seen.end())
            throw std::invalid_argument("duplicate argument: " + flag);
        seen.push_back(flag);
        if (k + 1 == argc) throw std::invalid_argument("missing value for " + flag);
        const std::string value = argv[++k];
        if (flag == "--n") o.n = integer(value, 1, flag);
        else if (flag == "--iterations") o.iterations = integer(value, 0, flag);
        else if (flag == "--max-iters") o.max_iters = integer(value, 1, flag);
        else if (flag == "--mode") {
            if (value != "fixed" && value != "converge")
                throw std::invalid_argument("--mode must be fixed or converge");
            o.mode = value;
        } else if (flag == "--tol") {
            std::size_t used = 0;
            try { o.tol = std::stod(value, &used); }
            catch (const std::exception&) { throw std::invalid_argument("invalid --tol"); }
            if (used != value.size() || !std::isfinite(o.tol) || o.tol <= 0)
                throw std::invalid_argument("--tol must be finite and positive");
        } else if (flag == "--output") {
            if (value.empty()) throw std::invalid_argument("empty output path");
            o.output = value;
        } else if (flag == "--problem") {
            if (value != "symmetric" && value != "asymmetric")
                throw std::invalid_argument("--problem must be symmetric or asymmetric");
            o.asymmetric = value == "asymmetric";
        } else throw std::invalid_argument("unknown argument: " + flag);
    }
    if (o.n > std::numeric_limits<int>::max() - 2)
        throw std::invalid_argument("--n is too large");
    const std::size_t width = static_cast<std::size_t>(o.n) + 2;
    if (width > std::vector<double>().max_size() / width)
        throw std::invalid_argument("grid size exceeds addressable storage");
    return o;
}

// Row i is y_i; column j is x_j. This convention matters in the asymmetric test.
inline double exact(int global_row, int col, const Options& o) {
    if (global_row == 0 || col == 0 || global_row == o.n + 1 || col == o.n + 1)
        return 0.0;
    const double h = 1.0 / (o.n + 1.0);
    return std::sin(pi * col * h) * std::sin((o.asymmetric ? 2.0 : 1.0) * pi * global_row * h);
}

inline double rhs(int global_row, int col, const Options& o) {
    return (o.asymmetric ? 5.0 : 2.0) * pi * pi * exact(global_row, col, o);
}

inline void write_csv(const std::string& path, const double* u, int n) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open output: " + path);
    out << std::setprecision(17);
    const std::size_t width = static_cast<std::size_t>(n) + 2;
    for (std::size_t i = 0; i < width; ++i) {
        for (std::size_t j = 0; j < width; ++j) {
            if (j) out << ',';
            out << u[i * width + j];
        }
        out << '\n';
    }
    out.close();
    if (!out) throw std::runtime_error("failed writing output: " + path);
}
} // namespace poisson
