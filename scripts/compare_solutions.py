"""Compare full CSV grids from serial and parallel runs with matching inputs."""
import argparse
import csv
import json
import math
from pathlib import Path


def read_grid(path):
    with Path(path).open() as f:
        grid = [list(map(float, row)) for row in csv.reader(f)]
    if not grid or not grid[0] or any(len(row) != len(grid[0]) for row in grid):
        raise ValueError('Empty or non-rectangular grid')
    if any(not math.isfinite(v) for row in grid for v in row):
        raise ValueError('Non-finite grid entry')
    return grid


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference');p.add_argument('candidate')
    p.add_argument('--atol',type=float,default=1e-10)
    p.add_argument('--rtol',type=float,default=1e-8)
    args=p.parse_args()
    if any(not math.isfinite(v) or v<0 for v in [args.atol,args.rtol]):
        p.error('Tolerances must be finite and nonnegative')
    try:
        a,b=read_grid(args.reference),read_grid(args.candidate)
        if len(a)!=len(b) or len(a[0])!=len(b[0]):
            raise ValueError('Grid shapes differ')
        errors=[abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb)]
        bad=sum(abs(x-y)>args.atol+args.rtol*abs(x) for ra,rb in zip(a,b) for x,y in zip(ra,rb))
        print(json.dumps(dict(passed=bad==0,mismatched_values=bad,max_absolute_error=max(errors),atol=args.atol,rtol=args.rtol)))
        return 1 if bad else 0
    except (OSError,ValueError) as e:
        p.exit(2,str(e)+'\n')

if __name__=='__main__':
    raise SystemExit(main())
