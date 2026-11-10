#!/usr/bin/env bash
# Run only in the fresh feature-branch checkout created by the runbook.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $(git branch --show-current) == feature/openmp-hybrid ]] || {
    echo 'Expected a dedicated feature/openmp-hybrid checkout.' >&2; exit 1;
}
source scripts/vanda-env.sh
root=$(pwd -P)
if [[ -f .vanda-openmp-workspace ]]; then
    [[ $(cat .vanda-openmp-workspace) == "$root" ]] || exit 1
fi
out="results/vanda/setup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
source scripts/discover_environment.sh "$out"
[[ $(cat "$out/scheduler.txt") == pbs ]] || {
    echo "PBS verification failed; inspect $out" >&2; exit 1;
}
cmake --version > "$out/cmake.txt"
python3 --version > "$out/python.txt"
mpicxx --showme > "$out/mpi-wrapper.txt"
printf '%s\n' "$root" > .vanda-openmp-workspace
echo "Prepared separate workspace: $root"
echo 'Next: bash scripts/submit_vanda.sh openmp-validate'
