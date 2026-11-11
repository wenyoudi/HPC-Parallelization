"""Review Vanda hybrid grids directly from the original evidence archive."""
import collections
import csv
import io
import json
import math
import tarfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def review_hybrid(path):
    counts = collections.Counter()
    coverage = set()
    maximum = 0.0
    with tarfile.open(path) as archive:
        def read_json(name):
            return json.load(archive.extractfile(name))
        status = read_json("status.json")
        require(status["success"] and status["exit_status"] == 0, "Hybrid job failed")
        receipt = read_json("distributed-validation/validation.json")
        require(receipt["site"] == "vanda" and receipt["passed"], "Invalid hybrid receipt")
        require(len(receipt["checks"]) == 494 and all(c["passed"] for c in receipt["checks"]),
                "Incomplete hybrid validation receipt")
        members = {m.name: m for m in archive.getmembers() if m.isfile()}
        for name in sorted(members):
            if not name.startswith("distributed-validation/") or not name.endswith(".json") or name.endswith("/validation.json"):
                continue
            record = read_json(name)
            require(record["passed"], "Failed comparison: " + name)
            for case in record["cases"]:
                ref, candidate = case["reference"], case["candidate"]
                for key in ("n", "problem", "mode", "iterations_completed", "converged"):
                    require(ref[key] == candidate[key], "Parameter mismatch: " + name)
                require(candidate["n"] == case["n"] and candidate["mpi_ranks"] == case["ranks"]
                        and candidate["omp_threads"] == case["threads"], "Execution size mismatch")
                if candidate["implementation"] == "hybrid":
                    require(candidate["mpi_thread_provided"] >= candidate["mpi_thread_required"] == 1,
                            "Insufficient MPI thread support")
                    coverage.add((case["n"],case["ranks"],case["threads"],ref["problem"], "limit" if candidate["converged"] is False else case["mode"]))
                directory = "distributed-validation/grids/" + case["grid_directory"].rstrip("/").split("/")[-1]
                names = [n for n in members if n.startswith(directory + "/") and n.endswith(".csv")]
                require(len(names) == 2, "Expected two grids: " + directory)
                grids = []
                for n in sorted(names, key=lambda n: "reference" not in n):
                    grid = [list(map(float,row)) for row in csv.reader(io.StringIO(archive.extractfile(n).read().decode()))]
                    size = case["n"] + 2
                    require(len(grid) == size and all(len(row) == size for row in grid), "Invalid grid shape")
                    require(all(math.isfinite(v) for row in grid for v in row), "Nonfinite grid")
                    require(all(v == 0 for v in grid[0]+grid[-1]) and all(row[0] == row[-1] == 0 for row in grid), "Nonzero boundary")
                    grids.append(grid)
                error = max(abs(a-b) for ra,rb in zip(*grids) for a,b in zip(ra,rb))
                require(all(abs(a-b) <= record["atol"] + record["rtol"]*abs(a)
                            for ra,rb in zip(*grids) for a,b in zip(ra,rb)), "Grid mismatch")
                require(error == case["max_absolute_difference"], "Recorded difference mismatch")
                maximum = max(maximum,error)
                counts[candidate["implementation"] + "_vs_" + ref["implementation"]] += 1
        require(dict(counts) == {"hybrid_vs_serial":194,"hybrid_vs_mpi":194,"mpi_vs_serial":98}, "Missing comparison cases")
        require(any(n == 10 and r == 3 for n,r,t,p,m in coverage), "Missing nondivisible case")
        require({(1,8),(2,4),(4,2),(8,1)} <= {(r,t) for n,r,t,p,m in coverage}, "Missing hybrid layouts")
        require({"symmetric","asymmetric"} == {p for n,r,t,p,m in coverage}, "Missing problem")
        require({"fixed","converge","limit"} <= {m for n,r,t,p,m in coverage}, "Missing mode")
    return {"status":"passed", "site":"vanda", "job_id":status["job_id"],
            "recorded_checks":494, "grid_pairs_rechecked":sum(counts.values()),
            "comparisons":dict(counts), "max_grid_difference":maximum,
            "expected_error_checks_reviewed":8}
