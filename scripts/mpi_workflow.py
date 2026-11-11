"""Shared invocation helpers. Default launcher uses C's verified PBS policy."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def launch_context(launcher_json, required_cpus):
    if launcher_json:
        template = json.loads(launcher_json)
        if not isinstance(template, list) or not template or not all(isinstance(x, str) for x in template):
            raise ValueError('Launcher must be a JSON list of strings with {ranks}')
        if not any('{ranks}' in x for x in template):
            raise ValueError('Launcher must contain {ranks}')
        return lambda ranks: [x.replace('{ranks}', str(ranks)) for x in template], dict(custom_launcher=template)
    from mpi_launcher import launcher
    from pbs_allocation import inspect_allocation
    allocation = inspect_allocation(required_cpus)
    return lambda ranks: launcher(allocation, ranks, 1, os.environ.get('VANDA_MPI_LAUNCHER', 'single-node')), allocation

def invoke(command, expected=0):
    env = dict(os.environ, OMP_NUM_THREADS='1', OMP_DYNAMIC='FALSE')
    p = subprocess.run(command, capture_output=True, text=True, timeout=300, env=env)
    if p.returncode != expected:
        raise RuntimeError(f'{command}: expected exit {expected}, got {p.returncode}\n{p.stdout}\n{p.stderr}')
    lines = p.stdout.strip().splitlines()
    if len(lines) != 1:
        raise ValueError(f'Expected exactly one JSON line: {p.stdout!r}')
    record = json.loads(lines[0])
    for key in ['solve_seconds', 'residual_linf', 'error_linf']:
        if not math.isfinite(record[key]) or record[key] < 0:
            raise ValueError(f'Invalid metric {key}')
    return record, dict(command=command, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
