# Compiler/MPI versions taken from C's vanda-env.sh at commit 2ea8a5a.
# This MPI solver has not yet been compiled/tested on Vanda.
module load GCC/11.3.0 || return
module load CMake/3.24.3-GCCcore-11.3.0 || return
module load OpenMPI/4.1.4-GCC-11.3.0 || return
export CC="$(command -v gcc)"
export CXX="$(command -v g++)"
export PATH="/opt/pbs/bin:$PATH"
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
export VANDA_MPI_LAUNCHER=${VANDA_MPI_LAUNCHER:-single-node}
