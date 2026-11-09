# Local evidence — not Vanda measurements

Development host: Apple M4 MacBook Air, 10 cores (4 performance + 6 efficiency), 16 GB RAM. Apple Clang 21.0.0, `-O3`, existing Anaconda LLVM OpenMP runtime. Requested affinity was unavailable (`{undefined}`), so binding was not verified. These runs were not made through an HPC scheduler.

- `openmp-m4-20261109/raw.jsonl`: 48 measurements (N=128/256/512/1024 × 1/2/4/8 threads × 3 repetitions), fixed K=1000.
- `openmp-m4-20261109/warmups.jsonl`: 16 excluded warm-ups.
- `openmp-m4-20261109/metadata.json`: original run configuration, actual build log, machine information, executable/source hashes, starting Git revision and dirty-tree status. Compiler version was queried immediately after the run and is explicitly marked as recorded afterward. Source hashes describe files at measurement time; documentation/pipeline checks were subsequently extended without changing the solver binary.
- `openmp-m4-20261109/stdout.log`, `stderr.log`: complete process diagnostics, including runtime affinity messages that this runtime emits to stdout. The collector extracts one primary JSON while preserving those diagnostics.
- `accuracy.json`: separate convergence/accuracy checks; their timing values are not part of the benchmark matrix.
- `validation.log`: optimized compilation, local-row test and 13 passing numerical test groups.
- `sanitizer-validation.log`: the 13 numerical test groups passed against an AddressSanitizer/UndefinedBehaviorSanitizer build.

Analysis and figures are in `report/figures/`; interpretation and limitations are in `report/openmp-hybrid.md`. No serial-baseline, MPI, hybrid or Vanda timing result is included. Intermediate failed collection attempts were moved to ignored `results/runs/`; they contained no accepted benchmark samples and are not part of this dataset.

Reproduce the numerical test suite with `bash scripts/build_local.sh`. Reproduce the benchmark into a **new** output directory with:

```bash
bash scripts/benchmark_openmp.sh --site local --allocated-cpus 8 \
  --output results/runs/local-reproduction
MPLCONFIGDIR=/tmp/project3-mpl /opt/anaconda3/bin/python scripts/analyze.py \
  results/local/openmp-m4-20261109/raw.jsonl --output report/figures --plots
```

Sanitizer compilation used `/usr/bin/clang++ -O1 -g -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer -Iinclude -Xpreprocessor -fopenmp -I/opt/anaconda3/include src/openmp.cpp -L/opt/anaconda3/lib -Wl,-rpath,/opt/anaconda3/lib -lomp -o /tmp/project3-openmp-sanitized`, followed by `python3 tests/test_openmp.py --solver /tmp/project3-openmp-sanitized`.
