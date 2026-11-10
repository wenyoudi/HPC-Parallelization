#!/usr/bin/env python3
"""Check the active single-node PBS allocation without storing Variable_List."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess


def inspect_allocation(required_cpus):
    job_id = os.environ.get("PBS_JOBID")
    nodefile = os.environ.get("PBS_NODEFILE")
    if not job_id or not nodefile or not Path(nodefile).is_file():
        raise RuntimeError("Run inside an allocated PBS compute job (PBS_JOBID/PBS_NODEFILE required)")
    nodes = set(Path(nodefile).read_text().split())
    if len(nodes) != 1:
        raise RuntimeError("This experiment requires exactly one allocated node")
    host = socket.gethostname()
    aliases = {host.split(".")[0].lower(), socket.getfqdn().split(".")[0].lower()}
    if next(iter(nodes)).split(".")[0].lower() not in aliases:
        raise RuntimeError("Current host is not the allocated compute node; refusing login-node execution")
    status = subprocess.run(["qstat", "-f", job_id], capture_output=True, text=True, timeout=15)
    if status.returncode:
        raise RuntimeError("Cannot verify active allocation using qstat -f")
    resources = dict(re.findall(
        r"(?m)^[ \t]*(Resource_List\.(?:ncpus|nodect|select|place|mem|walltime)|exec_host|exec_vnode|queue|job_state)[ \t]*=[ \t]*(.*)$",
        status.stdout))
    if resources.get("job_state") != "R":
        raise RuntimeError("PBS job is not running")
    try:
        ncpus = int(resources["Resource_List.ncpus"])
    except (KeyError, ValueError):
        raise RuntimeError("PBS did not report Resource_List.ncpus")
    if required_cpus > ncpus:
        raise RuntimeError("Requested benchmark CPUs exceed the PBS allocation")
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    if affinity is not None and len(affinity) < required_cpus:
        raise RuntimeError("The job cpuset exposes fewer CPUs than this experiment requires")
    return dict(job_id=job_id, hostname=host, nodes=sorted(nodes), resources=resources,
                allowed_os_cpus=affinity, requested_cpus=required_cpus)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cpus", type=int, default=8)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    allocation = inspect_allocation(a.cpus)
    a.output.write_text(json.dumps(allocation, indent=2)+"\n")
    print(json.dumps(allocation))
