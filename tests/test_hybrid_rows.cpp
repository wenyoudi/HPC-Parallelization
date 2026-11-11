#include "local_rows.hpp"
#include <iostream>
#include <stdexcept>
#include <vector>
#include <omp.h>

int main() {
    constexpr int n=10,rows=3,s=n+2;
    const double h2=1.0/121.0;
    std::vector<double> old((rows+2)*s),forcing(old.size()),scaled(old.size());
    for (int i=0;i<rows+2;++i) for(int j=0;j<s;++j) {
        old[i*s+j]=0.17*i*i-0.05*j+0.03*i*j;
        forcing[i*s+j]=0.13*(i+3)*(j+1);
        scaled[i*s+j]=h2*forcing[i*s+j];
    }
    for(int threads:{1,2,4,8}) {
        omp_set_num_threads(threads);
        std::vector<double> a(old.size()),b(old.size()),fixed(old.size());
        const auto scaled_change=poisson::update_local_rows<true>(old.data(),a.data(),scaled.data(),rows,n);
        const auto unscaled_change=poisson::update_local_rows<true>(old.data(),b.data(),forcing.data(),rows,n,h2);
        poisson::update_local_rows<false>(old.data(),fixed.data(),forcing.data(),rows,n,h2);
        // Compilers may contract the unscaled h²*f term differently from the
        // precomputed buffer. Allow last-bit rounding, well below solver tolerances.
        for(std::size_t q=0;q<a.size();++q)
            if(std::abs(a[q]-b[q])>1e-14 || std::abs(b[q]-fixed[q])>1e-14)
                throw std::runtime_error("scaled/unscaled or fixed/converge kernel mismatch");
        if(std::abs(scaled_change-unscaled_change)>1e-14)
            throw std::runtime_error("update maximum mismatch");
        for(int i=0;i<rows+2;++i) for(int j=0;j<s;++j)
            if((i==0 || i==rows+1 || j==0 || j==s-1) && b[i*s+j]!=0)
                throw std::runtime_error("hybrid kernel changed halo/boundary");
    }
    std::cout << "Hybrid unscaled-RHS kernel matches original kernels at 1/2/4/8 threads.\n";
}
