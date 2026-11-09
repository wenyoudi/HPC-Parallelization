CXX = c++
CPPFLAGS ?=
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wpedantic
OMPFLAGS ?= -fopenmp
LDLIBS ?=
PYTHON ?= python3

.PHONY: all openmp hybrid test clean
all: openmp
openmp: build/openmp

build/openmp: src/openmp.cpp include/poisson.hpp include/openmp_rows.hpp
	@mkdir -p build
	$(CXX) $(CPPFLAGS) -Iinclude $(CXXFLAGS) $(OMPFLAGS) $< $(LDLIBS) -o $@

# Member B's MPI framework is not present. Never build a misleading stub.
hybrid:
	@echo 'Hybrid integration pending Member B: see report/hybrid-integration.md' >&2
	@exit 1

build/test_rows: tests/test_rows.cpp include/openmp_rows.hpp
	@mkdir -p build
	$(CXX) $(CPPFLAGS) -Iinclude $(CXXFLAGS) $(OMPFLAGS) $< $(LDLIBS) -o $@

test: openmp build/test_rows
	./build/test_rows
	$(PYTHON) tests/test_openmp.py --solver build/openmp

clean:
	rm -rf build
