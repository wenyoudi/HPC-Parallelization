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
# Git is available on the login node, not necessarily on compute nodes.
git rev-parse HEAD > "$jobdir/source-commit.txt"
git status --porcelain > "$jobdir/source-status.txt"
if [[ -s "$jobdir/source-status.txt" ]]; then
    echo 'Commit or preserve local changes before submitting; no files were changed.' >&2
    echo "Working-tree status saved in $jobdir/source-status.txt" >&2
    exit 1
fi
git archive --format=tar.gz "$(cat "$jobdir/source-commit.txt")" > "$jobdir/source.tar.gz"
python3 - "$jobdir" <<'PROVENANCE_PY'
import datetime, hashlib, json, socket, sys
from pathlib import Path
out=Path(sys.argv[1])
data=dict(recorded_on="login_node", hostname=socket.gethostname(),
    recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    git_head=dict(command=["git","rev-parse","HEAD"],returncode=0,stdout=(out/"source-commit.txt").read_text(),stderr=""),
    git_status=dict(command=["git","status","--porcelain"],returncode=0,stdout=(out/"source-status.txt").read_text(),stderr=""),
    archive_sha256=hashlib.sha256((out/"source.tar.gz").read_bytes()).hexdigest())
(out/"source-provenance.json").write_text(json.dumps(data,indent=2)+"\n")
PROVENANCE_PY
job="$jobdir/job.pbs"
slots=1
ompthreads=8
jobname=p3-omp-bench
[[ "$kind" != openmp-validate ]] || jobname=p3-omp-check
[[ "$kind" != mpi-smoke ]] || jobname=p3-mpi-smoke
[[ "$kind" != mpi-smoke ]] || { slots=8; ompthreads=1; }
placement=${VANDA_PLACEMENT:-shared}
[[ "$kind" != openmp || -n ${VANDA_PLACEMENT:-} ]] || placement=excl
case "$placement" in shared|excl) ;; *) echo 'VANDA_PLACEMENT must be shared or excl.' >&2; exit 1;; esac
# Pin the job to this isolated checkout, regardless of qsub's working directory.
printf -v quoted_jobdir '%q' "$(pwd -P)/$jobdir"
cat > "$job" <<EOF
#!/bin/bash -l
#PBS -N ${jobname}
#PBS -l select=1:ncpus=8:mpiprocs=${slots}:ompthreads=${ompthreads}:mem=4gb
#PBS -l place=${placement}
#PBS -l walltime=00:30:00
#PBS -j oe
set -euo pipefail
cd ${quoted_jobdir}
python3 - <<'VERIFY_PY'
import hashlib, json
from pathlib import Path
expected=json.loads(Path("source-provenance.json").read_text())["archive_sha256"]
if hashlib.sha256(Path("source.tar.gz").read_bytes()).hexdigest()!=expected:
    raise SystemExit("Submitted source archive checksum mismatch")
VERIFY_PY
mkdir source
tar -xzf source.tar.gz -C source
export BENCH_KIND=${kind}
export VANDA_JOB_DIR=${quoted_jobdir}
source source/scripts/run_vanda_job.sh
EOF
# Queue/project flags can follow KIND; no account names are guessed.
/opt/pbs/bin/qsub "$@" "$job" | tee "$jobdir/job-id.txt"
printf '%s\n' "$jobdir" > "results/vanda/latest-${kind}.txt"
echo "Job script, build, status and results: $jobdir"
