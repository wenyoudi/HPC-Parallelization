# Vanda MPI evidence

The directory `mpi-1539665.stdct-mgmt-02/` contains original outputs downloaded
from Vanda job 1539665, executed on GN-A40-075 on 11 November 2026.

- `pbs.log`: build, CTest, MPI validation and benchmark completion log.
- `validation/validation.json`: 162 checks, exact commands, parameters and metrics.
- `validation/grids/`: 144 paired serial/MPI CSV grids, including N=10,P=3.
- `benchmark/raw.jsonl`: 45 measured records (15 configurations, three repeats).
- `benchmark/warmups.jsonl`: warmup runs, excluded from summary statistics.
- `benchmark/metadata.json`: hardware, allocation, versions, source revision,
  binary hashes and validation hash.
- `benchmark/summary.csv`: original cluster median summary.
- `audit.json`: independent local evidence audit.
- `SHA256SUMS`: archive checksums; evidence bytes are preserved by .gitattributes.

From the repository root, with Python available:

```bash
python scripts/audit_mpi_results.py results/vanda/mpi-1539665.stdct-mgmt-02 \
  --output /tmp/mpi-audit-new.json
```

The output path must not already exist. Original absolute Vanda paths in JSON
are retained for provenance; the audit resolves grids within this archive.

The benchmark uses fixed K=1000, not converged solutions. Read
`report/mpi_sections.md` for the validation results, both scaling baselines and
limitations. Figures are under `report/figures/mpi-vanda-1539665/`.
