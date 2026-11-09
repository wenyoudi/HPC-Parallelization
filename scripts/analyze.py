#!/usr/bin/env python3
"""Summarize one run; never pool sites, modes, allocations or compiler environments."""
import argparse
import collections
import csv
import json
from pathlib import Path
import statistics


def main():
    p = argparse.ArgumentParser()
    p.add_argument("raw", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--plots", action="store_true", help="Requires matplotlib; solver has no Python dependencies")
    args = p.parse_args()
    with args.raw.open() as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    if not records:
        p.error("no measurements")
    provenance = {(r["run_id"], r["site"], r["mode"], r["allocated_cpus"], r["nodes"], r["placement"], r["hostname"])
                  for r in records}
    if len(provenance) != 1 or any(r["mode"] != "fixed" or r["warmup"] for r in records):
        p.error("analyze one fixed-mode run with identical provenance, excluding warmups")
    groups = collections.defaultdict(list)
    for r in records:
        groups[(r["implementation"], r["N"], r["iterations_completed"], r["mpi_ranks"], r["omp_threads"])].append(r)
    rows = []
    for (impl, n, k, ranks, threads), group in sorted(groups.items()):
        if len(group) < 3 or len({r["repeat"] for r in group}) != len(group):
            p.error(f"insufficient or duplicate repetitions: {impl}, {n}, {ranks}x{threads}")
        times = [r["solve_seconds"] for r in group]
        rows.append(dict(site=group[0]["site"], implementation=impl, N=n, iterations=k,
                         mpi_ranks=ranks, omp_threads=threads, workers=ranks*threads,
                         samples=len(times), median_seconds=statistics.median(times),
                         min_seconds=min(times), max_seconds=max(times)))
    serial = {(r["N"],r["iterations"]): r["median_seconds"] for r in rows if r["implementation"] == "serial"}
    omp1 = {(r["N"],r["iterations"]): r["median_seconds"] for r in rows
            if r["implementation"] == "openmp" and r["workers"] == 1}
    for r in rows:
        key = (r["N"],r["iterations"])
        r["serial_speedup"] = serial[key]/r["median_seconds"] if key in serial else ""
        r["serial_efficiency"] = r["serial_speedup"]/r["workers"] if key in serial else ""
        r["relative_to_openmp_1thread"] = omp1[key]/r["median_seconds"] if key in omp1 and r["implementation"] == "openmp" else ""
        r["relative_omp_efficiency"] = r["relative_to_openmp_1thread"]/r["workers"] if r["relative_to_openmp_1thread"] != "" else ""
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output/"summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if args.plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.size": 10, "figure.dpi": 150, "savefig.dpi": 300})
        site = records[0]["site"].upper()
        for impl in sorted({r["implementation"] for r in rows} - {"serial"}):
            selected = [r for r in rows if r["implementation"] == impl]
            for metric, ylabel, suffix in [("median_seconds", "Median solve time (s)", "runtime"),
                ("serial_speedup", "Speedup vs serial", "speedup_serial"),
                ("serial_efficiency", "Efficiency vs serial baseline", "efficiency_serial"),
                ("relative_to_openmp_1thread", "Speedup vs OpenMP 1 thread", "speedup_omp1"),
                ("relative_omp_efficiency", "Relative efficiency vs OpenMP 1 thread", "efficiency_omp1")]:
                valid = [r for r in selected if r[metric] != ""]
                if not valid:
                    continue
                fig, ax = plt.subplots(figsize=(6.8,4.3))
                # Hybrid x labels distinguish decompositions having the same P.
                configs = sorted({(r["mpi_ranks"],r["omp_threads"]) for r in valid}, key=lambda x:(x[0]*x[1],-x[0]))
                for n, k in sorted({(r["N"],r["iterations"]) for r in valid}):
                    group = sorted([r for r in valid if (r["N"],r["iterations"]) == (n,k)],
                                   key=lambda r:configs.index((r["mpi_ranks"],r["omp_threads"])))
                    xs = [r["omp_threads"] if impl == "openmp" else configs.index((r["mpi_ranks"],r["omp_threads"])) for r in group]
                    if metric == "median_seconds":
                        ax.errorbar(xs, [r[metric] for r in group],
                            yerr=[[r[metric]-r["min_seconds"] for r in group],
                                  [r["max_seconds"]-r[metric] for r in group]],
                            marker="o", capsize=3, label=f"N={n}, K={k}")
                    else:
                        ax.plot(xs, [r[metric] for r in group], marker="o", label=f"N={n}, K={k}")
                if impl == "hybrid":
                    ax.set_xticks(range(len(configs)), [f"{r}×{t}" for r,t in configs])
                    ax.set_xlabel("MPI ranks × threads/rank (one node)")
                    if "speedup" in suffix:
                        ax.plot(range(len(configs)),[r*t for r,t in configs],"k--",linewidth=1,label="Ideal")
                else:
                    ts=sorted({r["omp_threads"] for r in valid})
                    ax.set_xticks(ts)
                    ax.set_xlabel("OpenMP threads (one process)")
                    if "speedup" in suffix:
                        ax.plot(ts,ts,"k--",linewidth=1,label="Ideal")
                ax.set_ylabel(ylabel)
                if "efficiency" in suffix:
                    ax.axhline(1, color="black", linestyle="--", linewidth=1, label="Ideal")
                ax.set_title(f"{site} — {impl}, fixed mode, median of ≥3 runs")
                ax.grid(alpha=.25)
                ax.legend(fontsize=8)
                fig.tight_layout()
                for ext in ["png", "pdf"]:
                    fig.savefig(args.output/f"{site.lower()}_{impl}_{suffix}.{ext}")
                plt.close(fig)
    print(args.output/"summary.csv")


if __name__ == "__main__":
    main()
