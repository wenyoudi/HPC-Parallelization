#!/usr/bin/env bash
# Generate and submit a PBS job only after live environment verification.
# Usage: bash scripts/submit_vanda.sh openmp [qsub queue/project options...]
set -euo pipefail
cd "$(dirname "$0")/.."
kind=${1:?Use openmp or hybrid}
shift
[[ "$kind" == openmp || "$kind" == hybrid ]]
config=scripts/vanda-env.local.sh
test -f "$config" || { echo "Create $config following report/vanda-runbook.md" >&2; exit 1; }
source "$config"
: "${HPC_CXX:?Set HPC_CXX after verifying modules}"
[[ ${VANDA_VERIFIED_SCHEDULER:-} == pbs ]] || { echo 'Live PBS verification required.' >&2; exit 1; }
[[ $(cat "${VANDA_DISCOVERY_DIR:?}/scheduler.txt") == pbs ]]
test -s "$VANDA_DISCOVERY_DIR/pbs-server.txt"
command -v qsub >/dev/null
command -v "$HPC_CXX" >/dev/null
if [[ "$kind" == hybrid ]]; then
    test -f src/hybrid.cpp || { echo 'Integrate Member B MPI + OpenMP first.' >&2; exit 1; }
    [[ ${MPI_LAUNCHER_JSON:-[]} != '[]' && -n ${MPI_PLACEMENT_LABEL:-} ]]
fi
stamp=$(date -u +%Y%m%dT%H%M%SZ)
jobdir="results/vanda/job-${kind}-${stamp}"
mkdir -p "$jobdir"
# A single node makes 8x1/4x2/2x4/1x8 directly comparable. Reserve eight slots
# for hybrid MPI launchers; the launcher must place ranks with threads per rank.
slots=1
[[ "$kind" == hybrid ]] && slots=8
job="$jobdir/job.pbs"
cat > "$job" <<EOF
#!/usr/bin/env bash
#PBS -N p3-${kind}
#PBS -l select=1:ncpus=8:mpiprocs=${slots}:mem=4gb
#PBS -l place=excl
#PBS -l walltime=00:30:00
#PBS -j oe
set -euo pipefail
cd "\$PBS_O_WORKDIR"
source scripts/vanda-env.local.sh
export BENCH_KIND=${kind}
export BENCH_OUTPUT=${jobdir}/measurements
bash scripts/run_vanda_job.sh
EOF
qsub "$@" "$job" | tee "$jobdir/job-id.txt"
echo "Job script and ID: $jobdir"
