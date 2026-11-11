# Actual local hybrid validation (not Vanda measurements)

494 checks passed on 11 November 2026: 486 complete-grid numerical comparisons
and eight expected-error cases, using serial, B's unmodified MPI-only solver and
the separate hybrid solver. Largest grid difference: 0.0 on this build.

`validation-summary.json` records counts by reference/mode, source/binary hashes,
compiler/MPI versions and scope. `full-validation.tar.gz` retains all full-grid
CSVs, per-case metrics/commands and stdout/stderr, plus the full receipt.
The uncompressed working copy is in ignored
`results/runs/hybrid-integration-20261111-local/`.

Local build: CMake 3.24.3, Apple Clang 21.0.0 Release -O3, MPICH 4.3.2 and the
existing Anaconda OpenMP runtime. No fast-math or explicit local core binding.
The Mac has mixed performance/efficiency cores; no scaling conclusion is drawn.
Validation solve-time fields are diagnostics, not benchmark samples.

Reproduce after building the `mpi`, `hybrid`, and `poisson_serial` CMake targets
with a working local MPI/OpenMP compiler (replace BUILD_DIR and MPI path):

```bash
python3 scripts/validate_distributed.py --site local --allocated-cpus 8 \
  --serial BUILD_DIR/references/serial/poisson_serial \
  --mpi BUILD_DIR/mpi --hybrid BUILD_DIR/hybrid \
  --launcher-json '["mpirun","-n","{ranks}"]' \
  --output results/runs/NEW-local-hybrid-check
```

Output must be new. On the development Mac the Anaconda MPI wrapper needs
`MPICH_CXX=/usr/bin/clang++` during CMake configuration, and Apple Clang needs
its existing libomp include/link settings. Local MPI launches require permission
for the process manager's localhost sockets. See the runbook for Vanda commands,
which use Open MPI 4.1.4 and the actual PBS allocation instead of this local mode.
