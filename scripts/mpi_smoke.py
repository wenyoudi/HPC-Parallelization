#!/usr/bin/env python3
"""Launch the Linux MPI environment test only after verifying PBS allocation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from pbs_allocation import inspect_allocation
from mpi_launcher import MODES, cpu_limit, launcher

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--solver", required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--launcher-mode", choices=MODES, default=os.environ.get("VANDA_MPI_LAUNCHER", "single-node"))
p.add_argument("--ranks", default="1,2,4,8", help="Counts exceeding the actual allocation are excluded and recorded")
a = p.parse_args()
allocation = inspect_allocation(1)
requested = [int(s) for s in a.ranks.split(",")]
if not requested or min(requested) < 1 or len(requested) != len(set(requested)):
    p.error("rank counts must be positive and distinct")
counts = [n for n in requested if n <= cpu_limit(allocation)]
if not counts:
    p.error("no smoke-test configuration fits the PBS allocation")
a.output.mkdir(parents=True, exist_ok=False)
(a.output/"allocation.json").write_text(json.dumps(allocation, indent=2)+"\n")
(a.output/"plan.json").write_text(json.dumps(dict(launcher_mode=a.launcher_mode,
    requested_ranks=requested, executed_ranks=counts, excluded_ranks=[n for n in requested if n not in counts]),indent=2)+"\n")
for ranks in counts:
    cmd = launcher(allocation,ranks,1,a.launcher_mode) + [str(Path(a.solver).resolve())]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                          env=dict(os.environ, OMP_NUM_THREADS="1", OMP_DISPLAY_AFFINITY="FALSE"))
    (a.output/f"ranks-{ranks}.stdout.jsonl").write_text(proc.stdout)
    (a.output/f"ranks-{ranks}.stderr.log").write_text(proc.stderr)
    result = dict(command=cmd, mpi_ranks=ranks, returncode=proc.returncode)
    try:
        records = [json.loads(s) for s in proc.stdout.splitlines() if s.startswith("{")]
        summaries = [r for r in records if r.get("test")=="mpi_smoke"]
        rank_records = [r for r in records if r.get("test")=="mpi_rank"]
        result["success"] = (proc.returncode==0 and len(summaries)==1 and summaries[0]["success"] is True
                             and summaries[0]["mpi_ranks"]==ranks
                             and sorted(r["rank"] for r in rank_records)==list(range(ranks))
                             and all(r["hostname"].split(".")[0].lower() == allocation["hostname"].split(".")[0].lower()
                                     for r in rank_records))
        allowed=allocation.get("allowed_os_cpus")
        if allowed is not None:
            result["success"] = result["success"] and all(
                set(r["os_cpus"]).issubset(set(allowed)) for r in rank_records)
    except (ValueError, KeyError, TypeError):
        result["success"] = False
    with (a.output/"results.jsonl").open("a") as stream:
        stream.write(json.dumps(result)+"\n")
    if not result["success"]:
        raise RuntimeError(f"MPI smoke failed at {ranks} ranks; inspect {a.output}")
    print(f"PASS: MPI launch/collectives/ring/FUNNELED/disjoint binding, ranks={ranks}", flush=True)
