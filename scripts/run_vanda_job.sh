#!/usr/bin/env bash
set -euo pipefail
: "${PBS_JOBID:?Run only inside an allocated PBS job}"
: "${BENCH_KIND:?}"
: "${VANDA_JOB_DIR:?}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ "$VANDA_JOB_DIR" == /*/results/vanda/job-* && -d "$VANDA_JOB_DIR" ]] || exit 1
jobdir=$(cd "$VANDA_JOB_DIR" && pwd -P)
[[ $(pwd -P) == "$jobdir/source" ]] || exit 1
test -s "$jobdir/source-provenance.json" && test -s "$jobdir/source-commit.txt"
test ! -e "$jobdir/status.json" || { echo 'Refusing to overwrite a completed attempt.' >&2; exit 1; }
exec > >(tee "$jobdir/job.log") 2>&1
phase=environment
finish() {
    rc=$?
    trap - EXIT
    python3 - "$jobdir/status.json" "$rc" "$phase" "$BENCH_KIND" "$PBS_JOBID" <<'STATUS_PY'
import datetime, json, socket, sys
from pathlib import Path
path, rc, phase, kind, job_id = sys.argv[1:]
Path(path).write_text(json.dumps(dict(job_id=job_id, kind=kind, exit_status=int(rc),
    success=int(rc)==0, phase=phase, hostname=socket.gethostname(),
    finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()), indent=2)+'\n')
STATUS_PY
    exit "$rc"
}
trap finish EXIT
source scripts/vanda-env.sh
phase=allocation
python3 scripts/pbs_allocation.py --cpus "${VANDA_CPUS:-8}" --output "$jobdir/allocation.json"
source scripts/discover_environment.sh "$jobdir/compute-environment"
cmake --version > "$jobdir/compute-environment/cmake.txt"
mpicxx --showme > "$jobdir/compute-environment/mpi-wrapper.txt"
builddir="$jobdir/build"
phase=configure
mpi=OFF
[[ "$BENCH_KIND" != mpi-smoke ]] || mpi=ON
serial=OFF
[[ "$BENCH_KIND" != serial-compare ]] || serial=ON
distributed=OFF
case "$BENCH_KIND" in mpi-validate|hybrid-validate|hybrid) distributed=ON; serial=ON; mpi=ON;; esac
cmake -S . -B "$builddir" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_COMPILER="$(command -v g++)" \
    -DPython3_EXECUTABLE="$(command -v python3)" \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DBUILD_MPI_SMOKE="$mpi" -DBUILD_SERIAL_REFERENCE="$serial" \
    -DBUILD_DISTRIBUTED_SOLVERS="$distributed" \
    2>&1 | tee "$jobdir/configure.log"
phase=build
targets=(openmp test_rows)
[[ "$BENCH_KIND" != mpi-smoke ]] || targets=(mpi_smoke)
[[ "$BENCH_KIND" != serial-compare ]] || targets+=(poisson_serial)
case "$BENCH_KIND" in mpi-validate|hybrid-validate|hybrid) targets+=(mpi mpi_smoke poisson_serial);; esac
case "$BENCH_KIND" in hybrid-validate|hybrid) targets+=(hybrid);; esac
cmake --build "$builddir" --parallel "${VANDA_CPUS:-8}" --verbose --target "${targets[@]}" \
    2>&1 | tee "$jobdir/build.log"
cp "$builddir/compile_commands.json" "$jobdir/compile_commands.json"
cp "$builddir/CMakeCache.txt" "$jobdir/CMakeCache.txt"
if [[ "$BENCH_KIND" == mpi-smoke ]]; then
    phase=mpi-smoke
    python3 scripts/mpi_smoke.py --solver "$builddir/mpi_smoke" --output "$jobdir/mpi-smoke" \
        --launcher-mode "$VANDA_MPI_LAUNCHER"
else
    phase=validation
    ctest --test-dir "$builddir" --output-on-failure --output-junit "$jobdir/validation.xml" \
        2>&1 | tee "$jobdir/validation.log"
    cp "$builddir/Testing/Temporary/LastTest.log" "$jobdir/validation-detail.log"
    if [[ "$BENCH_KIND" == openmp ]]; then
        phase=benchmark
        python3 scripts/benchmark.py --kind openmp --solver "$builddir/openmp" \
            --site vanda --allocated-cpus 8 --threads 1,2,4,8 \
            --sizes 128,256,512,1024 --iterations 1000 --warmups 1 --repeats 3 \
            --compiler g++ --build-log "$jobdir/build.log" \
            --source-provenance "$jobdir/source-provenance.json" --output "$jobdir/measurements"
        phase=analysis
        python3 scripts/analyze.py "$jobdir/measurements/raw.jsonl" --output "$jobdir/analysis"
    elif [[ "$distributed" == ON ]]; then
        phase=mpi-smoke
        python3 scripts/mpi_smoke.py --solver "$builddir/mpi_smoke" --output "$jobdir/mpi-smoke" \
            --launcher-mode "$VANDA_MPI_LAUNCHER"
        phase=distributed-validation
        extra=()
        [[ "$BENCH_KIND" == mpi-validate ]] || extra+=(--hybrid "$builddir/hybrid")
        python3 scripts/validate_distributed.py --serial "$builddir/references/serial/poisson_serial" \
            --mpi "$builddir/mpi" --output "$jobdir/distributed-validation" \
            --launcher-mode "$VANDA_MPI_LAUNCHER" "${extra[@]}"
        if [[ "$BENCH_KIND" == hybrid ]]; then
            phase=hybrid-benchmark
            python3 scripts/benchmark.py --kind hybrid --site vanda --solver "$builddir/hybrid" \
                --serial "$builddir/references/serial/poisson_serial" --allocated-cpus "${VANDA_CPUS:-8}" \
                --launcher-mode "$VANDA_MPI_LAUNCHER" --sizes 128,256,512,1024 --iterations 1000 \
                --warmups 1 --repeats 3 --compiler g++ --build-log "$jobdir/build.log" \
                --source-provenance "$jobdir/source-provenance.json" \
                --validation-evidence "$jobdir/distributed-validation/validation.json" --output "$jobdir/measurements"
            phase=analysis
            python3 scripts/analyze.py "$jobdir/measurements/raw.jsonl" --output "$jobdir/analysis"
        fi
    elif [[ "$BENCH_KIND" == serial-compare ]]; then
        phase=serial-comparison
        mkdir "$jobdir/serial-comparison"
        for threads in 1 2 4 8; do
            for problem in symmetric asymmetric; do
                extra=()
                [[ "$problem" != asymmetric ]] || extra+=(--asymmetric)
                python3 tests/compare_solvers.py --reference "$builddir/references/serial/poisson_serial" \
                    --candidate "$builddir/openmp" --n 10 --iterations 31 --threads "$threads" \
                    --evidence "$jobdir/serial-comparison/${problem}-${threads}.json" "${extra[@]}"
            done
        done
    elif [[ "$BENCH_KIND" != openmp-validate ]]; then
        echo 'Unsupported workload.' >&2; exit 1
    fi
fi
phase=complete
