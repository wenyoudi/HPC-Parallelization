#!/usr/bin/env python3
"""Prepared integration matrix. Requires a real hybrid executable; never skips failures."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from mpi_launcher import MODES, cpu_limit, launcher
from pbs_allocation import inspect_allocation

p=argparse.ArgumentParser()
p.add_argument("--reference", required=True)
p.add_argument("--candidate", default="build/distributed/hybrid")
p.add_argument("--launcher-json", help="Local custom launcher only; PBS uses --launcher-mode")
p.add_argument("--launcher-mode", choices=MODES, default=os.environ.get("VANDA_MPI_LAUNCHER","single-node"))
p.add_argument("--allocated-cpus", type=int, default=os.cpu_count() or 1, help="Local test CPU budget")
p.add_argument("--asymmetric", action="store_true", help="Both solvers must support --problem")
a=p.parse_args()
if not Path(a.reference).is_file() or not Path(a.candidate).is_file():
    p.error("reference and real integrated hybrid executables must exist")
allocation=inspect_allocation(1) if os.environ.get("PBS_JOBID") else None
if allocation and a.launcher_json:
    p.error("PBS tests use --launcher-mode to derive host slots from the verified allocation")
if not allocation and not a.launcher_json:
    p.error("local tests require --launcher-json")
budget=cpu_limit(allocation) if allocation else a.allocated_cpus
for n, ranks, threads in [(10,3,2),(8,8,1),(10,1,8),(10,4,2),(10,2,4),(1,1,1),(3,3,2)]:
    if ranks*threads>budget:
        print(json.dumps(dict(not_run="exceeds CPU allocation",n=n,mpi_ranks=ranks,omp_threads=threads)))
        continue
    prefix=json.dumps(launcher(allocation,ranks,threads,a.launcher_mode)) if allocation else a.launcher_json
    for asymmetric in ([False,True] if a.asymmetric else [False]):
        base=[sys.executable,"tests/compare_solvers.py","--reference",a.reference,
              "--candidate",a.candidate,"--launcher-json",prefix,
              "--ranks",str(ranks),"--threads",str(threads),"--n",str(n)]
        if asymmetric:
            base.append("--asymmetric")
        for k in [1,2,31]:
            subprocess.run(base+["--mode","fixed","--iterations",str(k)], check=True)
        subprocess.run(base+["--mode","converge"], check=True)
