#!/usr/bin/env python3
"""Launch the Linux MPI environment test only after verifying PBS allocation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from pbs_allocation import inspect_allocation

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--solver", required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
allocation = inspect_allocation(8)
a.output.mkdir(parents=True, exist_ok=False)
(a.output/"allocation.json").write_text(json.dumps(allocation, indent=2)+"\n")
for ranks in [1,2,4,8]:
    cmd = ["mpirun", "--np", str(ranks), "--hostfile", os.environ["PBS_NODEFILE"],
           "--map-by", "slot:PE=1", "--bind-to", "core", "--nooversubscribe", "--report-bindings",
           str(Path(a.solver).resolve())]
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
    except (ValueError, KeyError, TypeError):
        result["success"] = False
    with (a.output/"results.jsonl").open("a") as stream:
        stream.write(json.dumps(result)+"\n")
    if not result["success"]:
        raise RuntimeError(f"MPI smoke failed at {ranks} ranks; inspect {a.output}")
    print(f"PASS: MPI launch/collectives/ring/FUNNELED/disjoint binding, ranks={ranks}", flush=True)
