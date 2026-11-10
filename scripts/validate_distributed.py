#!/usr/bin/env python3
"""Actual MPI/hybrid numerical checks against serial within one PBS allocation.

Requires real integrated executables. This prepares validation, not an MPI solver.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from mpi_launcher import MODES, cpu_limit, launcher
from pbs_allocation import inspect_allocation


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serial", required=True)
    p.add_argument("--mpi", required=True)
    p.add_argument("--hybrid", help="Include only the real integrated hybrid executable")
    p.add_argument("--launcher-mode", choices=MODES, default=os.environ.get("VANDA_MPI_LAUNCHER","single-node"))
    p.add_argument("--output", type=Path, required=True)
    a=p.parse_args()
    for name in ["serial","mpi","hybrid"]:
        path=getattr(a,name)
        if path and not Path(path).is_file():
            p.error(f"actual {name} executable is missing: {path}")
    allocation=inspect_allocation(1)
    budget=cpu_limit(allocation)
    a.output.mkdir(parents=True,exist_ok=False)
    report=dict(passed=False,allocation=allocation,launcher_mode=a.launcher_mode,
        binary_sha256={name:sha(getattr(a,name)) for name in ["serial","mpi","hybrid"] if getattr(a,name)},
        checks=[],not_run_due_to_allocation=[],scope="numerical validation; MPI thread-call discipline also requires source review")
    jobs=[]
    # N=10/ranks=3 tests nonuniform rows. N=ranks exercises one row/rank.
    for ranks in [1,2,3,4,8]:
        if ranks<=budget:
            for n in sorted({10,ranks}):
                jobs.append(("mpi",ranks,1,n))
        else:
            report["not_run_due_to_allocation"].append(dict(implementation="mpi",mpi_ranks=ranks,omp_threads=1))
    if a.hybrid:
        for ranks,threads in [(1,1),(2,1),(4,1),(8,1),(3,2),(2,2),(1,4),(4,2),(2,4),(1,8)]:
            if ranks*threads<=budget:
                for n in sorted({10,ranks}):
                    jobs.append(("hybrid",ranks,threads,n))
            else:
                report["not_run_due_to_allocation"].append(dict(implementation="hybrid",mpi_ranks=ranks,omp_threads=threads))
    try:
        for implementation,ranks,threads,n in jobs:
            prefix=launcher(allocation,ranks,threads,a.launcher_mode)
            for problem in ["symmetric","asymmetric"]:
                for mode,k in [("fixed",1),("fixed",2),("fixed",31),("converge",31)]:
                    case=f"{implementation}-n{n}-r{ranks}-t{threads}-{problem}-{mode}-k{k}"
                    cmd=[sys.executable,"tests/compare_solvers.py","--reference",a.serial,
                         "--candidate",getattr(a,implementation),"--launcher-json",json.dumps(prefix),
                         "--n",str(n),"--ranks",str(ranks),"--threads",str(threads),
                         "--mode",mode,"--iterations",str(k),"--evidence",str(a.output/f"{case}.json")]
                    if problem=="asymmetric": cmd.append("--asymmetric")
                    result=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
                    (a.output/f"{case}.stdout.log").write_text(result.stdout)
                    (a.output/f"{case}.stderr.log").write_text(result.stderr)
                    report["checks"].append(dict(case=case,command=cmd,passed=result.returncode==0,
                        implementation=implementation,mpi_ranks=ranks,omp_threads=threads,
                        n=n,problem=problem,mode=mode))
                    if result.returncode:
                        raise RuntimeError(f"Numerical validation failed: {case}; see saved logs")
        report["passed"]=True
    except Exception as error:
        report["error"]=str(error)
        raise
    finally:
        (a.output/"validation.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__ == "__main__":
    main()
