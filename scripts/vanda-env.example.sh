# Copy to scripts/vanda-env.local.sh (ignored by Git).
# After discovery, load the EXACT available compiler/MPI modules here.
# Do not add credentials, tokens, private keys, or passwords.
# module load <compiler-module-from-modules-available.txt>
# module load <compatible-mpi-module-from-modules-available.txt>

VANDA_DISCOVERY_DIR="results/vanda/discovery"
# Set only after reviewing successful qstat -Bf and scheduler.txt:
VANDA_VERIFIED_SCHEDULER=""
# Absolute compiler path or command from the verified module environment:
HPC_CXX=""
HPC_CXXFLAGS="-O3 -std=c++17 -Wall -Wextra -Wpedantic"
HPC_OMPFLAGS="-fopenmp"
HPC_LDLIBS=""
# Optional queue/project flags supplied explicitly to submit_vanda.sh after --.
# No queue or project name is assumed.

# Hybrid only: exact launcher for the selected MPI, with process/thread binding.
# JSON array, containing {ranks} and {threads} placeholders; no shell expansion.
MPI_LAUNCHER_JSON='[]'
MPI_PLACEMENT_LABEL=""
# Member A's executable, only after building in the SAME compiler environment:
SERIAL_EXE=""
