#!/usr/bin/env python3
"""Prepared integration matrix. Requires a real hybrid executable; never skips failures."""
import argparse
from pathlib import Path
import subprocess
import sys

p=argparse.ArgumentParser()
p.add_argument("--reference", required=True)
p.add_argument("--candidate", default="build/hybrid")
p.add_argument("--launcher-json", required=True)
p.add_argument("--asymmetric", action="store_true", help="Both solvers must support --problem")
a=p.parse_args()
if not Path(a.reference).is_file() or not Path(a.candidate).is_file():
    p.error("reference and real integrated hybrid executables must exist")
for n, ranks, threads in [(10,3,2),(8,8,1),(10,1,8),(10,4,2),(10,2,4),(1,1,1),(3,3,2)]:
    for asymmetric in ([False,True] if a.asymmetric else [False]):
        base=[sys.executable,"tests/compare_solvers.py","--reference",a.reference,
              "--candidate",a.candidate,"--launcher-json",a.launcher_json,
              "--ranks",str(ranks),"--threads",str(threads),"--n",str(n)]
        if asymmetric:
            base.append("--asymmetric")
        for k in [0,1,2,31]:
            subprocess.run(base+["--mode","fixed","--iterations",str(k)], check=True)
        subprocess.run(base+["--mode","converge"], check=True)
