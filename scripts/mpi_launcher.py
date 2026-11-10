#!/usr/bin/env python3
"""Single-node Open MPI launch policies constrained by a verified PBS allocation."""
import argparse
import json
import os
from pbs_allocation import inspect_allocation

MODES = ("single-node", "pbs")


def cpu_limit(allocation):
    allocated = int(allocation["resources"]["Resource_List.ncpus"])
    if allocated < 1 or len(allocation["nodes"]) != 1:
        raise ValueError("A positive, single-node PBS CPU allocation is required")
    available = allocation.get("allowed_os_cpus")
    physical = allocation.get("visible_physical_cores")
    return min([allocated] + ([len(available)] if available is not None else [])
               + ([physical] if physical is not None else []))


def launcher(allocation, ranks, threads=1, mode="single-node", nodefile=None):
    if mode not in MODES:
        raise ValueError("Unknown MPI launcher mode")
    if ranks < 1 or threads < 1 or ranks*threads > cpu_limit(allocation):
        raise ValueError("MPI ranks × OpenMP threads exceeds allocated/available cores")
    allocated = int(allocation["resources"]["Resource_List.ncpus"])
    host = allocation["hostname"]
    if not host or any(c.isspace() or c in ":/" for c in host):
        raise ValueError("Invalid compute-node hostname")
    cmd = ["mpirun"]
    if mode == "single-node":
        # User-verified workaround: avoid the Open MPI TM launch path while
        # staying on the already verified PBS compute node. Never use host CPU count.
        cmd += ["--mca", "plm", "rsh", "--mca", "ras", "^tm", "--host", f"{host}:{allocated}"]
    else:
        nodefile = nodefile or os.environ.get("PBS_NODEFILE")
        if not nodefile:
            raise ValueError("The original PBS launcher requires PBS_NODEFILE")
        cmd += ["--hostfile", nodefile]
    return cmd + ["--np", str(ranks), "--map-by", f"slot:PE={threads}", "--bind-to", "core",
                  "--nooversubscribe", "--report-bindings"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=MODES, default=os.environ.get("VANDA_MPI_LAUNCHER", "single-node"))
    p.add_argument("--ranks", type=int, required=True)
    p.add_argument("--threads", type=int, default=1)
    a = p.parse_args()
    print(json.dumps(launcher(inspect_allocation(1), a.ranks, a.threads, a.mode)))
