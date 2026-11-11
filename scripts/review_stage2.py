"""Audit archived stage-two evidence without running solvers or benchmarks."""
import hashlib
import json
from pathlib import Path
from compare_solutions import read_grid


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    base = Path(__file__).resolve().parents[1] / "results/validation/stage2"
    provenance = json.loads((base / "provenance.json").read_text())
    for name, expected in provenance["sha256"].items():
        require(hashlib.sha256((base / name).read_bytes()).hexdigest() == expected,
                "Evidence checksum mismatch: " + name)
    omp_cases = []
    for path in sorted((base / "openmp/serial-comparison").glob("*.json")):
        record = json.loads(path.read_text())
        require(record["passed"] is True, "OpenMP reported failure")
        for case in record["cases"]:
            ref, candidate = case["reference"], case["candidate"]
            require(ref["n"] == candidate["N"] == case["n"], "OpenMP size mismatch")
            for key in ("problem", "mode", "iterations_completed", "converged"):
                require(ref[key] == candidate[key], "OpenMP mismatch: " + key)
            require(candidate["omp_threads"] == case["threads"], "Thread mismatch")
            require(0 <= case["max_absolute_difference"] <= record["atol"],
                    "OpenMP recorded difference exceeds absolute tolerance")
            omp_cases.append(case)
    require(len(omp_cases) == 16, "Expected 16 OpenMP cases")
    coverage = {(c["reference"]["problem"], c["mode"], c["threads"]) for c in omp_cases}
    require(coverage == {(p, m, t) for p in ("symmetric", "asymmetric")
                         for m in ("fixed", "converge") for t in (1, 2, 4, 8)},
            "Incomplete OpenMP coverage")
    data = json.loads((base / "mpi/validation.json").read_text())
    require(data["passed"] and all(c["passed"] for c in data["checks"]),
            "MPI record reports failure")
    pairs, maximum = 0, 0.0
    for case in data["checks"]:
        if "grids" not in case:
            continue
        ref, candidate = case["serial_metrics"], case["mpi_metrics"]
        for key in ("n", "problem", "mode", "iterations_completed", "converged"):
            require(ref[key] == candidate[key], "MPI mismatch: " + key)
        require(candidate["mpi_ranks"] == case["ranks"], "Rank mismatch")
        grids = [read_grid(base / "mpi/grids" / Path(p).name) for p in case["grids"]]
        for grid in grids:
            size = case["n"] + 2
            require(len(grid) == size and all(len(row) == size for row in grid),
                    "Incorrect full-grid shape")
            require(all(v == 0 for v in grid[0] + grid[-1]) and
                    all(row[0] == row[-1] == 0 for row in grid), "Nonzero boundary")
        errors = [abs(x-y) for ra, rb in zip(*grids) for x, y in zip(ra, rb)]
        require(all(abs(x-y) <= data["atol"] + data["rtol"]*abs(x)
                    for ra, rb in zip(*grids) for x, y in zip(ra, rb)),
                "Grid comparison failed: " + case["case"])
        require(max(errors) == case["max_absolute_error"], "Recorded difference mismatch")
        maximum = max(maximum, max(errors))
        pairs += 1
    require(pairs == 144 and len(data["checks"]) == 162, "Unexpected MPI coverage")
    require(any(c.get("n") == 10 and c.get("ranks") == 3 and "grids" in c
                for c in data["checks"]), "Missing nondivisible decomposition")
    print(json.dumps({"passed": True, "openmp_recorded_cases_reviewed": len(omp_cases),
        "openmp_max_recorded_grid_difference": max(c["max_absolute_difference"] for c in omp_cases),
        "openmp_raw_grids_rechecked": False, "mpi_recorded_checks": len(data["checks"]),
        "mpi_grid_pairs_rechecked": pairs, "mpi_max_grid_difference": maximum,
        "hybrid": "pending", "solver_runs_performed": 0}, indent=2))


if __name__ == "__main__":
    main()
