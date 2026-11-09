#!/usr/bin/env python3
"""Run when Member A/B executables exist; failure is never silently skipped."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument("--reference", required=True)
p.add_argument("--candidate", required=True)
p.add_argument("--launcher-json", default="[]", help='e.g. ["mpirun","-n","3"]')
p.add_argument("--threads", type=int, default=2)
p.add_argument("--ranks", type=int, default=3)
p.add_argument("--n", type=int, default=10)
p.add_argument("--iterations", type=int, default=31)
p.add_argument("--mode", choices=["both", "fixed", "converge"], default="both")
p.add_argument("--asymmetric", action="store_true", help="Both programs must support --problem")
args = p.parse_args()
launcher = json.loads(args.launcher_json)
if not isinstance(launcher, list) or any(not isinstance(x, str) for x in launcher):
    p.error("launcher must be a JSON array of strings")
launcher = [s.format(ranks=args.ranks, threads=args.threads) for s in launcher]
env = dict(os.environ, OMP_NUM_THREADS=str(args.threads), OMP_DYNAMIC="FALSE")
with tempfile.TemporaryDirectory() as tmp:
    for mode in (["fixed", "converge"] if args.mode == "both" else [args.mode]):
        grids, metrics = [], []
        for name, prefix in [("ref", [str(Path(args.reference).resolve())]),
                             ("candidate", launcher+[str(Path(args.candidate).resolve())])]:
            path = Path(tmp)/f"{name}.csv"
            cmd = prefix + ["--n", str(args.n), "--mode", mode, "--iterations", str(args.iterations),
                            "--tol", "1e-10", "--output", str(path)]
            if args.asymmetric:
                cmd += ["--problem", "asymmetric"]
            run = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True, timeout=120)
            lines = run.stdout.strip().splitlines()
            if len(lines) != 1:
                raise AssertionError("expected exactly one primary result (rank 0)")
            metrics.append(json.loads(lines[0]))
            with path.open() as stream:
                grids.append([list(map(float, row)) for row in csv.reader(stream)])
        for grid in grids:
            assert len(grid) == args.n+2 and all(len(r)==args.n+2 for r in grid), "incorrect gathered shape"
            assert all(x == 0 for x in grid[0]+grid[-1]), "row boundary"
            assert all(r[0] == r[-1] == 0 for r in grid), "column boundary"
        for row_a, row_b in zip(*grids):
            assert all(math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-10) for a,b in zip(row_a,row_b))
        assert metrics[1]["mpi_ranks"] == (args.ranks if launcher else 1), "incorrect rank count"
        assert metrics[1]["omp_threads"] == args.threads, "incorrect thread count"
        for key in ["iterations_completed", "converged", "max_update", "residual_linf", "error_linf"]:
            a, b = metrics[0][key], metrics[1][key]
            if a is None or b is None or isinstance(a, bool) or isinstance(b, bool):
                assert a == b, key
            else:
                assert math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-10), (key,a,b)
        print(f"PASS {mode}: N={args.n}, reference vs candidate, threads={args.threads}")
