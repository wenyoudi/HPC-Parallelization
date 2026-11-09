#!/usr/bin/env python3
"""Fixed-mode, single-node benchmarks. Raw data and provenance are never overwritten."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shlex
import shutil
import subprocess
import uuid


def capture(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return {"command": cmd, "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"command": cmd, "error": str(e)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", choices=["openmp", "hybrid"], required=True)
    p.add_argument("--site", choices=["local", "vanda"], required=True)
    p.add_argument("--solver", required=True)
    p.add_argument("--serial", help="Member A's true serial executable, built with the same flags")
    p.add_argument("--output", type=Path, required=True, help="New run directory")
    p.add_argument("--allocated-cpus", type=int, required=True)
    p.add_argument("--sizes", default="128,256,512,1024")
    p.add_argument("--threads", default="1,2,4,8")
    p.add_argument("--configs", default="1x1,2x1,4x1,8x1,4x2,2x4,1x8")
    p.add_argument("--iterations", type=int, default=1000)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--warmups", type=int, default=1)
    p.add_argument("--seed", type=int, default=5208)
    p.add_argument("--launcher-json", default="[]", help="Array of launcher args; {ranks}/{threads} substituted")
    p.add_argument("--placement-label", default="OMP_PLACES=cores; OMP_PROC_BIND=close")
    p.add_argument("--build-log", type=Path, default=Path("build/build.log"))
    p.add_argument("--compiler", default=os.environ.get("CXX", "c++"), help="Compiler command whose version is recorded")
    args = p.parse_args()
    sizes = [int(x) for x in args.sizes.split(",")]
    configs = ([(1, int(x)) for x in args.threads.split(",")] if args.kind == "openmp"
               else [tuple(map(int, x.split("x"))) for x in args.configs.split(",")])
    launcher = json.loads(args.launcher_json)
    if not isinstance(launcher, list) or any(not isinstance(x, str) for x in launcher):
        p.error("launcher must be an array of strings")
    if args.kind == "hybrid" and (not launcher or not any("{ranks}" in x for x in launcher)):
        p.error("hybrid requires an explicit MPI launcher with {ranks}; verify placement on Vanda")
    if args.kind == "openmp" and launcher:
        p.error("OpenMP runs use no MPI launcher")
    if args.repeats < 3 or args.warmups < 0 or args.iterations < 1 or args.allocated_cpus < 1:
        p.error("require repeats>=3, warmups>=0, iterations>=1, allocated-cpus>=1")
    if not sizes or min(sizes) < 1:
        p.error("sizes must be positive")
    for ranks, threads in configs:
        if min(ranks, threads) < 1 or ranks*threads > args.allocated_cpus:
            p.error(f"invalid or oversubscribed configuration: {ranks}x{threads}")
        if ranks > min(sizes):
            p.error("ranks must not exceed N")
    if args.site == "vanda":
        if not os.environ.get("PBS_JOBID"):
            p.error("Vanda measurements require an active PBS allocation")
        nodefile = os.environ.get("PBS_NODEFILE")
        if not nodefile or not Path(nodefile).is_file():
            p.error("PBS_NODEFILE required to verify single-node placement")
        if len(set(Path(nodefile).read_text().split())) != 1:
            p.error("this benchmark plan requires exactly one allocated node")
        # Retain resource fields only; PBS Variable_List may contain private env values.
        status = capture(["qstat", "-f", os.environ["PBS_JOBID"]])
        if status.get("returncode") != 0:
            p.error("cannot verify active PBS resource allocation with qstat -f")
        allocation = dict(re.findall(r"(?m)^\s*(Resource_List\.(?:ncpus|nodect|select|place|mem|walltime)|exec_host|exec_vnode|queue)\s*=\s*(.*)$",
                                     status["stdout"]))
        try:
            actual_cpus = int(allocation["Resource_List.ncpus"])
        except (KeyError, ValueError):
            p.error("PBS did not report Resource_List.ncpus; verify allocation before benchmarking")
        if args.allocated_cpus > actual_cpus:
            p.error("declared CPU allocation exceeds PBS Resource_List.ncpus")
        if hasattr(os, "sched_getaffinity") and args.allocated_cpus > len(os.sched_getaffinity(0)):
            p.error("PBS cpuset exposes fewer CPUs than the requested benchmark allocation")
    else:
        allocation = None
    executable = Path(args.solver).resolve()
    if not executable.is_file():
        p.error(f"solver missing: {executable}; hybrid depends on Member B's MPI code")
    if not args.build_log.is_file():
        p.error("build log required to record actual compiler commands; use --build-log")
    if args.serial and not Path(args.serial).is_file():
        p.error("serial baseline does not exist")
    args.output.mkdir(parents=True, exist_ok=False)
    run_id = str(uuid.uuid4())
    metadata = {
        "run_id": run_id, "site": args.site, "start_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hostname": platform.node(), "platform": platform.platform(), "machine": platform.machine(),
        "allocated_cpus": args.allocated_cpus, "nodes": 1, "arguments": vars(args).copy(),
        "pbs_allocation": allocation,
        "binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "build_log": args.build_log.read_text(),
        "compiler_version": capture(shlex.split(args.compiler) + ["--version"]),
        "git_head": capture(["git", "rev-parse", "HEAD"]),
        "git_status": capture(["git", "status", "--porcelain"]),
        "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for root in ["src", "include", "scripts", "tests"]
            for path in sorted(Path(root).glob("*")) if path.is_file()},
        "environment": {k: os.environ[k] for k in ["PBS_JOBID", "PBS_QUEUE", "PBS_NCPUS",
            "LOADEDMODULES", "CXX", "CXXFLAGS", "OMPFLAGS", "LDLIBS"] if k in os.environ},
        "placement_requested": args.placement_label,
        "hardware": capture(["lscpu"]) if shutil.which("lscpu") else
            capture(["/usr/sbin/system_profiler", "SPHardwareDataType"]),
        "mpi_version": capture(["mpirun", "--version"]) if shutil.which("mpirun") else None,
    }
    metadata["source_sha256"]["Makefile"] = hashlib.sha256(Path("Makefile").read_bytes()).hexdigest()
    # Strip machine identifiers unrelated to reproducibility from macOS inventory.
    hardware = metadata["hardware"]
    if "stdout" in hardware:
        hardware["stdout"] = "\n".join(s for s in hardware["stdout"].splitlines()
            if not any(x in s for x in ["Serial Number", "UUID", "UDID"]))
    if args.serial:
        metadata["serial_binary_sha256"] = hashlib.sha256(Path(args.serial).read_bytes()).hexdigest()
    (args.output/"metadata.json").write_text(json.dumps(metadata, indent=2, default=str)+"\n")
    if os.environ.get("PBS_NODEFILE"):
        shutil.copyfile(os.environ["PBS_NODEFILE"], args.output/"allocated-nodes.txt")

    tasks = [(args.kind, r, t, n) for n in sizes for r, t in configs]
    if args.serial:
        tasks += [("serial", 1, 1, n) for n in sizes]
    rng = random.Random(args.seed)
    log_path = args.output/"stderr.log"
    counter = 0

    def measure(task, repeat, warmup):
        nonlocal counter
        kind, ranks, threads, n = task
        env = dict(os.environ, OMP_NUM_THREADS=str(threads), OMP_DYNAMIC="FALSE",
                   OMP_PLACES="cores", OMP_PROC_BIND="close", OMP_DISPLAY_AFFINITY="TRUE")
        prefix = [s.format(ranks=ranks, threads=threads) for s in launcher] if kind == "hybrid" else []
        solver = str(Path(args.serial).resolve()) if kind == "serial" else str(executable)
        cmd = prefix + [solver, "--n", str(n), "--mode", "fixed", "--iterations", str(args.iterations)]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
        counter += 1
        with log_path.open("a") as stream:
            stream.write(f"\nrun={counter} warmup={warmup} repeat={repeat} cmd={shlex.join(cmd)}\n")
            stream.write(proc.stderr)
        with (args.output/"stdout.log").open("a") as stream:
            stream.write(f"\nrun={counter} warmup={warmup} repeat={repeat} cmd={shlex.join(cmd)}\n")
            stream.write(proc.stdout)
        if proc.returncode:
            raise RuntimeError(f"benchmark failed (exit {proc.returncode}): {proc.stderr}")
        # Some OpenMP runtimes print OMP_DISPLAY_AFFINITY diagnostics to stdout.
        # Preserve them separately and still require exactly one primary JSON.
        lines = [s for s in proc.stdout.splitlines() if s.lstrip().startswith("{")]
        if len(lines) != 1:
            raise RuntimeError("solver must emit exactly one primary JSON line")
        result = json.loads(lines[0])
        for key, value in {"implementation": kind, "N": n, "mode": "fixed", "mpi_ranks": ranks,
                           "omp_threads": threads, "iterations_completed": args.iterations,
                           "converged": None, "max_update": None}.items():
            if result.get(key, "missing") != value:
                raise RuntimeError(f"result mismatch {key}: expected {value}, got {result.get(key)}")
        for key in ["solve_seconds", "residual_linf", "error_linf"]:
            if not isinstance(result.get(key), (int, float)) or not math.isfinite(result[key]) or result[key] < 0:
                raise RuntimeError(f"invalid metric: {key}")
        if result["solve_seconds"] <= 0:
            raise RuntimeError("nonpositive solve time")
        result.update(run_id=run_id, site=args.site, repeat=repeat, warmup=warmup,
                      command=cmd, allocated_cpus=args.allocated_cpus, nodes=1,
                      placement=args.placement_label, hostname=platform.node())
        with (args.output/("warmups.jsonl" if warmup else "raw.jsonl")).open("a") as stream:
            stream.write(json.dumps(result, allow_nan=False)+"\n")
        if not warmup:
            print(f"{args.site}: {kind} N={n} {ranks}x{threads} repeat={repeat}: {result['solve_seconds']:.6f}s", flush=True)

    # Warm up every configuration, then shuffle measured repetitions to reduce drift bias.
    for task in tasks:
        for k in range(args.warmups):
            measure(task, k, True)
    schedule = [(task, k+1) for task in tasks for k in range(args.repeats)]
    rng.shuffle(schedule)
    for task, repeat in schedule:
        measure(task, repeat, False)


if __name__ == "__main__":
    main()
