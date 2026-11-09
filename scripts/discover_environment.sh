#!/usr/bin/env bash
# Source from a Vanda login shell to preserve its module function:
#   source scripts/discover_environment.sh results/vanda/discovery
# Runs inventory only; no computational experiments on the login node.
project3_discover() (
    set -u
    out=${1:?Supply a new output directory}
    if [[ -e "$out" ]]; then echo "Refusing to overwrite $out" >&2; exit 1; fi
    mkdir -p "$out"
    date -u '+%Y-%m-%dT%H:%M:%SZ' > "$out/time-utc.txt"
    uname -a > "$out/system.txt"
    hostname >> "$out/system.txt"
    for tool in c++ g++ clang++ mpicxx mpirun qstat qsub sbatch srun lscpu; do
        command -v "$tool" >> "$out/tools.txt" 2>&1 || true
    done
    if command -v qstat >/dev/null && command -v qsub >/dev/null; then
        qstat --version > "$out/scheduler-version.txt" 2>&1 || true
        qstat -Bf > "$out/pbs-server.txt" 2>&1
        if [[ $? -eq 0 ]]; then printf 'pbs\n' > "$out/scheduler.txt"; fi
        qstat -Q > "$out/queues.txt" 2>&1 || true
    elif command -v sbatch >/dev/null; then
        sbatch --version > "$out/scheduler-version.txt" 2>&1
        printf 'slurm\n' > "$out/scheduler.txt"
    else
        printf 'unverified\n' > "$out/scheduler.txt"
    fi
    if type module >/dev/null 2>&1; then
        module -t list > "$out/modules-loaded.txt" 2>&1 || true
        module -t avail > "$out/modules-available.txt" 2>&1 || true
    else
        printf 'No module command in this shell; inspect cluster login setup.\n' > "$out/modules-available.txt"
    fi
    c++ --version > "$out/compiler.txt" 2>&1 || true
    mpicxx -show > "$out/mpi-wrapper.txt" 2>&1 || mpicxx --showme >> "$out/mpi-wrapper.txt" 2>&1 || true
    mpirun --version > "$out/mpi-version.txt" 2>&1 || true
    if command -v lscpu >/dev/null; then lscpu > "$out/login-topology.txt"; fi
    echo "Inventory saved in $out. Login-node topology is not benchmark hardware."
)
if project3_discover "$@"; then
    unset -f project3_discover
else
    unset -f project3_discover
    return 1 2>/dev/null || exit 1
fi
