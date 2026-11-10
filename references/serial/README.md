# Pinned Member A serial reference

Verbatim source/test/build snapshot from commit 0e20822ffda1d0493a1f1564438fbe8f58d0b1a2 on `serial-baseline-and-validation`. `UPSTREAM.json` records hashes. This is Member A’s implementation, preserved in an isolated include/build directory; changes belong on their branch. No upstream file has been edited.

Enable with `-DBUILD_SERIAL_REFERENCE=ON`. Executable: `references/serial/poisson_serial` under the selected CMake build directory. Comparison tooling accepts its `n` output key and mode-specific CLI without changing the OpenMP solver. The serial RHS is unscaled and multiplied by h² in each update; the existing OpenMP RHS is pre-scaled. Future hybrid timing comparisons must record/align this arithmetic choice while preserving these upstream sources and existing OpenMP results.
