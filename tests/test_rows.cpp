#include "openmp_rows.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <omp.h>

int main() {
    constexpr int n = 10, rows = 3, stride = n + 2;
    std::vector<double> old((rows+2)*stride), next(old.size()), f(old.size());
    // Deliberately non-symmetric data and nonzero halos detect row/column mixups.
    for (int i=0; i<rows+2; ++i)
        for (int j=0; j<stride; ++j) {
            old[i*stride+j] = 0.37*i*i - 0.13*j + 0.02*i*j;
            f[i*stride+j] = 0.007*(i+4)*(j+1);
        }
    for (int threads : {1,2,4,8}) {
        omp_set_num_threads(threads);
        double expected_max = 0;
        const double actual = poisson::update_local_rows<true>(old.data(),next.data(),f.data(),rows,n);
        for (int i=1; i<=rows; ++i)
            for (int j=1; j<=n; ++j) {
                int p=i*stride+j;
                double expected=(old[p-stride]+old[p+stride]+old[p-1]+old[p+1]+f[p])/4;
                if (std::abs(next[p]-expected)>1e-14) throw std::runtime_error("local row mismatch");
                expected_max=std::max(expected_max,std::abs(expected-old[p]));
            }
        if (std::abs(actual-expected_max)>1e-14) throw std::runtime_error("local max mismatch");
        std::vector<double> fixed(next.size());
        poisson::update_local_rows<false>(old.data(),fixed.data(),f.data(),rows,n);
        if (fixed!=next) throw std::runtime_error("fixed/converge kernels differ");
        for (int i=0; i<rows+2; ++i)
            for (int j=0; j<stride; ++j)
                if ((i==0 || i==rows+1 || j==0 || j==stride-1) && next[i*stride+j]!=0)
                    throw std::runtime_error("kernel modified halo/boundary");
    }
    std::cout << "Local hybrid-ready row kernel passed (1,2,4,8 threads; 3 rows; nonzero halos).\n";
}
