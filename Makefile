CXX = c++
CPPFLAGS ?=
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wpedantic
OMPFLAGS ?= -fopenmp
LDLIBS ?=
PYTHON ?= python3
CMAKE ?= cmake

.PHONY: all openmp hybrid test clean
all: openmp
openmp: build/openmp

build/openmp: src/openmp.cpp include/poisson.hpp include/openmp_rows.hpp
	@mkdir -p build
	$(CXX) $(CPPFLAGS) -Iinclude $(CXXFLAGS) $(OMPFLAGS) $< $(LDLIBS) -o $@

hybrid:
	$(CMAKE) -S . -B build/distributed -DCMAKE_BUILD_TYPE=Release -DBUILD_DISTRIBUTED_SOLVERS=ON -DBUILD_SERIAL_REFERENCE=ON
	$(CMAKE) --build build/distributed --target mpi hybrid poisson_serial test_hybrid_rows

build/test_rows: tests/test_rows.cpp include/openmp_rows.hpp
	@mkdir -p build
	$(CXX) $(CPPFLAGS) -Iinclude $(CXXFLAGS) $(OMPFLAGS) $< $(LDLIBS) -o $@

test: openmp build/test_rows
	./build/test_rows
	$(PYTHON) tests/test_openmp.py --solver build/openmp

clean:
	rm -rf build
