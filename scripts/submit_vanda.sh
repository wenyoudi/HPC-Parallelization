#!/usr/bin/env bash
# Only generates/submits jobs here; compilation and tests run inside PBS.
set -euo pipefail
cd "$(dirname "$0")/.."
kind=${1:?Use openmp-validate, openmp, mpi-smoke or hybrid}
shift
case "$kind" in openmp-validate|openmp|mpi-smoke|hybrid) ;; *) echo 'Unknown job kind.' >&2; exit 1;; esac
[[ -f .vanda-openmp-workspace && $(cat .vanda-openmp-workspace) == "$(pwd -P)" ]] || {
    echo 'Use the separate clone and run bash scripts/setup_vanda.sh first.' >&2; exit 1;
}
[[ $(git branch --show-current) == feature/openmp-hybrid ]] || exit 1
source scripts/vanda-env.sh
if [[ "$kind" == hybrid ]]; then
    echo 'Hybrid integration still awaits Member B; run mpi-smoke first.' >&2
    exit 1
fi
stamp=$(date -u +%Y%m%dT%H%M%SZ)
jobdir="results/vanda/job-${kind}-${stamp}-$$"
mkdir -p "$jobdir"
job="$jobdir/job.pbs"
slots=1
ompthreads=8
jobname=p3-omp-bench
[[ "$kind" != openmp-validate ]] || jobname=p3-omp-check
[[ "$kind" != mpi-smoke ]] || jobname=p3-mpi-smoke
[[ "$kind" != mpi-smoke ]] || { slots=8; ompthreads=1; }
# Pin the job to this isolated checkout, regardless of qsub's working directory.
printf -v quoted_root '%q' "$(pwd -P)"
cat > "$job" <<EOF
#!/bin/bash -l
#PBS -N ${jobname}
#PBS -l select=1:ncpus=8:mpiprocs=${slots}:ompthreads=${ompthreads}:mem=4gb
#PBS -l place=excl
#PBS -l walltime=00:30:00
#PBS -j oe
set -euo pipefail
cd ${quoted_root}
export BENCH_KIND=${kind}
export VANDA_JOB_DIR=${jobdir}
source scripts/run_vanda_job.sh
EOF
# Queue/project flags can follow KIND; no account names are guessed.
/opt/pbs/bin/qsub "$@" "$job" | tee "$jobdir/job-id.txt"
printf '%s\n' "$jobdir" > "results/vanda/latest-${kind}.txt"
echo "Job script, build, status and results: $jobdir"
