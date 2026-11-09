#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Verified runtime on the development Mac; no packages are installed by this script.
prefix=${OPENMP_PREFIX:-/opt/anaconda3}
test -f "$prefix/include/omp.h"
test -f "$prefix/lib/libomp.dylib"
make clean
mkdir -p build
make test CXX=/usr/bin/clang++ \
  OMPFLAGS="-Xpreprocessor -fopenmp -I$prefix/include" \
  LDLIBS="-L$prefix/lib -Wl,-rpath,$prefix/lib -lomp" 2>&1 | tee build/build.log
