# Member B MPI reference

The public header, MPI-only source/entry point and handoff are preserved verbatim from `feature/mpi-poisson` commit 1756effac3929c873e56624314fea54ca5155863. `UPSTREAM.json` records hashes and the upstream Vanda validation receipt. B’s CMake/scripts are not merged. Existing benchmarks and grid CSVs remain on B’s branch, untouched.

The upstream handoff predates the evidence commit and still says validation is pending; the separate receipt reports 162/162 passing cases. That is upstream MPI evidence, not hybrid evidence. The integration links the same decomposition/exchange functions into the independent hybrid target.
