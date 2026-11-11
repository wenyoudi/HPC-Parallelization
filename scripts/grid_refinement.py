"""Measure serial spatial error; formal results must run on an HPC compute node."""
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from compare_solutions import read_grid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--sizes', nargs='+', type=int, default=[15,31,63,127])
    parser.add_argument('--tol', type=float, default=1e-13)
    parser.add_argument('--max-iters', type=int, default=500000)
    parser.add_argument('--local-smoke', action='store_true')
    args = parser.parse_args()
    if args.sizes != sorted(set(args.sizes)) or any(n < 1 for n in args.sizes):
        parser.error('Sizes must be positive, unique and increasing')
    if not math.isfinite(args.tol) or args.tol <= 0 or args.max_iters < 1:
        parser.error('Use a finite positive tolerance and positive iteration limit')
    if not args.local_smoke and not os.environ.get('PBS_JOBID'):
        parser.error('Submit formal experiments through PBS; local checks require --local-smoke')
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    executable = Path(args.executable).resolve()
    metadata = dict(site='local-smoke' if args.local_smoke else 'vanda',
                    hostname=platform.node(), job_id=os.environ.get('PBS_JOBID'),
                    utc=datetime.now(timezone.utc).isoformat(), arguments=vars(args),
                    binary_sha256=hashlib.sha256(executable.read_bytes()).hexdigest())
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    rows=[]
    with (out/'runs.jsonl').open('w') as raw:
        for problem,m in [('symmetric',1),('asymmetric',2)]:
            previous=None
            for n in args.sizes:
                grid_path=out/f'{problem}-n{n}.csv'
                command=[str(executable),'--n',str(n),'--problem',problem,'--mode','converge',
                         '--tol',str(args.tol),'--max-iters',str(args.max_iters),'--output',str(grid_path.resolve())]
                run=subprocess.run(command,capture_output=True,text=True)
                (out/f'{problem}-n{n}.stdout.txt').write_text(run.stdout)
                (out/f'{problem}-n{n}.stderr.txt').write_text(run.stderr)
                if run.returncode != 0:
                    raise RuntimeError(f'{problem} N={n} failed or did not converge; inspect saved output')
                metrics=json.loads(run.stdout)
                if not (metrics['converged'] and metrics['n']==n and metrics['problem']==problem):
                    raise RuntimeError('Unexpected solver output')
                grid=read_grid(grid_path)
                if len(grid)!=n+2 or any(len(row)!=n+2 for row in grid):
                    raise RuntimeError('Wrong grid shape')
                h=1/(n+1)
                # This sine forcing is an eigenvector of the discrete stencil.
                # Its exact discrete solution separates iteration error from spatial error.
                eigenvalue=4/h**2*(math.sin(math.pi*h/2)**2+math.sin(m*math.pi*h/2)**2)
                amplitude=(1+m*m)*math.pi**2/eigenvalue
                continuum_error=iteration_error=discretization_error=0.0
                for i,row in enumerate(grid):
                    for j,value in enumerate(row):
                        exact=0.0 if i in (0,n+1) or j in (0,n+1) else math.sin(math.pi*j*h)*math.sin(m*math.pi*i*h)
                        discrete=amplitude*exact
                        continuum_error=max(continuum_error,abs(value-exact))
                        iteration_error=max(iteration_error,abs(value-discrete))
                        discretization_error=max(discretization_error,abs(discrete-exact))
                fraction=iteration_error/discretization_error
                if fraction>0.01 or not math.isclose(continuum_error,metrics['error_linf'],rel_tol=1e-8,abs_tol=1e-12):
                    raise RuntimeError('Iteration error too large or reported error inconsistent')
                record=dict(problem=problem,n=n,h=h,iterations=metrics['iterations_completed'],
                            error_linf=continuum_error,discretization_error_linf=discretization_error,
                            iteration_error_linf=iteration_error,iteration_error_fraction=fraction,
                            residual_linf=metrics['residual_linf'],solve_seconds=metrics['solve_seconds'],
                            observed_order=None if previous is None else math.log(previous['error_linf']/continuum_error)/math.log(previous['h']/h))
                raw.write(json.dumps(dict(metrics=metrics,command=command,analysis=record))+'\n');raw.flush()
                rows.append(record);previous=record
    with (out/'summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (out/'status.json').write_text(json.dumps(dict(passed=True,cases=len(rows),site=metadata['site']),indent=2)+'\n')
    print(out)


if __name__=='__main__':
    main()
