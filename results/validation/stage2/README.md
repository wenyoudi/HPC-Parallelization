# Stage-two validation evidence

See [review and limitations](../../../docs/stage2_validation.md).

- `openmp/`: unchanged files from the supplied serial-openmp-validation-1537318 archive.
- `mpi/`: validation JSON, 288 grid CSV files and job log from the pinned MPI commit.
- `provenance.json`: source identifiers and SHA-256 hashes for imported evidence.
- `hybrid-vanda-results-1541184.tar.gz`: unchanged Vanda hybrid results, including all grids.
- `review.json`: output of `python3 scripts/review_stage2.py`.

The original hybrid archive also contains performance data; this correctness review
does not audit its performance analysis.
