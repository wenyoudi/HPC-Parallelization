# Source from a login shell on Vanda. Module versions verified by the user on
# 10 November 2026; rechecked both at submission and on each compute node.
type module >/dev/null 2>&1 || {
    echo 'The module command is unavailable. Use a Vanda login shell (bash -l).' >&2
    return 1
}
module load GCC/11.3.0 || return
module load CMake/3.24.3-GCCcore-11.3.0 || return
module load OpenMPI/4.1.4-GCC-11.3.0 || return

[[ $(g++ -dumpfullversion -dumpversion) == 11.3.0 ]] || {
    echo 'Expected GCC 11.3.0.' >&2; return 1;
}
[[ $(cmake --version | head -n 1) == 'cmake version 3.24.3' ]] || {
    echo 'Expected CMake 3.24.3.' >&2; return 1;
}
[[ $(mpirun --version) == *'Open MPI) 4.1.4'* ]] || {
    echo 'Expected Open MPI 4.1.4.' >&2; return 1;
}
[[ $(mpicxx -dumpfullversion -dumpversion) == 11.3.0 ]] || {
    echo 'Expected the MPI wrapper to use GCC 11.3.0.' >&2; return 1;
}
test -x /opt/pbs/bin/qsub && test -x /opt/pbs/bin/qstat || return 1
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' || {
    echo 'The existing Python test/benchmark pipeline requires Python >=3.8; inspect module avail Python if needed.' >&2
    return 1
}
export PATH="/opt/pbs/bin:$PATH"
export CXX=g++
export CXXFLAGS='-O3 -std=c++17 -Wall -Wextra -Wpedantic'
export OMPFLAGS=-fopenmp
export LDLIBS=''
export OMP_DYNAMIC=FALSE OMP_PLACES=cores OMP_PROC_BIND=close
# Validation parses JSON directly. Benchmark subprocesses enable affinity reports.
export OMP_DISPLAY_AFFINITY=FALSE OMP_NUM_THREADS=8
# The single-node TM workaround was verified by the user in job 1536986.
# The original scheduler/hostfile launch remains selectable with "pbs".
export VANDA_MPI_LAUNCHER=${VANDA_MPI_LAUNCHER:-single-node}
MPI_LAUNCHER_JSON='["mpirun","--np","{ranks}","--map-by","slot:PE={threads}","--bind-to","core","--nooversubscribe","--report-bindings"]'
MPI_PLACEMENT_LABEL='OpenMPI 4.1.4: slot:PE=threads, bind-to core, nooversubscribe; OMP_PLACES=cores, OMP_PROC_BIND=close'
