#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" scripts/benchmark.py --kind hybrid --solver "${HYBRID_SOLVER:-build/distributed/hybrid}" "$@"
