#include "poisson.hpp"
#include <exception>
#include <iostream>
#include <string>
int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--help") {
        poisson::print_help(); return 0;
    }
    try {
        const auto options = poisson::parse_options(argc, argv);
        const auto result = poisson::solve_serial(options);
        poisson::write_csv(options, result);
        poisson::print_result(options, result);
        return options.mode == "converge" && !result.converged ? 3 : 0;
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n'; return 2;
    }
}
