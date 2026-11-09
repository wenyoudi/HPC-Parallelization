#!/usr/bin/env bash
set -euo pipefail
: "${PBS_JOBID:?Run only inside an allocated PBS job}"
: "${BENCH_KIND:?}"
: "${BENCH_OUTPUT:?}"
source scripts/vanda-env.local.sh
mkdir -p build
export CXX="$HPC_CXX" CXXFLAGS="$HPC_CXXFLAGS" OMPFLAGS="$HPC_OMPFLAGS" LDLIBS="$HPC_LDLIBS"
export OMP_NUM_THREADS=8 OMP_DYNAMIC=FALSE OMP_PLACES=cores OMP_PROC_BIND=close
# Capture actual compute-node allocation and modules; no full environment dump.
mkdir -p "$(dirname "$BENCH_OUTPUT")/compute-environment"
source scripts/discover_environment.sh "$(dirname "$BENCH_OUTPUT")/compute-environment/inventory"
make clean
mkdir -p build
make test CXX="$CXX" CXXFLAGS="$CXXFLAGS" OMPFLAGS="$OMPFLAGS" LDLIBS="$LDLIBS" \
  2>&1 | tee build/build.log
extra=()
if [[ -n ${SERIAL_EXE:-} ]]; then
    # Member A must supply the serial target. Rebuild it after clean, with the
    # same exported compiler/flags, so the baseline cannot be a stale binary.
    make serial 2>&1 | tee -a build/build.log
    test -x "$SERIAL_EXE"
    extra+=(--serial "$SERIAL_EXE")
fi
if [[ "$BENCH_KIND" == hybrid ]]; then
    # Replace the Makefile dependency guard after integrating Member B's code.
    make hybrid 2>&1 | tee -a build/build.log
    python3 tests/validate_hybrid.py --reference build/openmp --candidate build/hybrid \
      --launcher-json "$MPI_LAUNCHER_JSON" --asymmetric
    if [[ -n ${SERIAL_EXE:-} ]]; then
        python3 tests/validate_hybrid.py --reference "$SERIAL_EXE" --candidate build/hybrid \
          --launcher-json "$MPI_LAUNCHER_JSON"
    fi
    extra+=(--launcher-json "$MPI_LAUNCHER_JSON" --placement-label "$MPI_PLACEMENT_LABEL")
fi
bash "scripts/benchmark_${BENCH_KIND}.sh" --site vanda --allocated-cpus 8 \
  --output "$BENCH_OUTPUT" "${extra[@]}"
python3 scripts/analyze.py "$BENCH_OUTPUT/raw.jsonl" --output "$BENCH_OUTPUT/analysis"
