#!/usr/bin/env python3
"""Compare complete grids/diagnostics from serial, MPI, OpenMP or hybrid solvers."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def metrics_from_grid(grid,n,asymmetric):
    h=1/(n+1)
    frequency=2 if asymmetric else 1
    residual,error=0.0,0.0
    for i in range(1,n+1):
        for j in range(1,n+1):
            exact=math.sin(math.pi*(j*h))*math.sin(frequency*math.pi*(i*h))
            forcing=(1+frequency**2)*math.pi**2*exact
            au=(4*grid[i][j]-grid[i-1][j]-grid[i+1][j]-grid[i][j-1]-grid[i][j+1])/(h*h)
            residual=max(residual,abs(forcing-au))
            error=max(error,abs(grid[i][j]-exact))
    return dict(residual_linf=residual,error_linf=error)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True)
    p.add_argument('--candidate',required=True)
    p.add_argument('--launcher-json',default='[]')
    p.add_argument('--reference-launcher-json',default='[]')
    p.add_argument('--threads',type=int,default=2)
    p.add_argument('--ranks',type=int,default=3)
    p.add_argument('--n',type=int,default=10)
    p.add_argument('--iterations',type=int,default=31)
    p.add_argument('--mode',choices=['both','fixed','converge'],default='both')
    p.add_argument('--tol',default='1e-10')
    p.add_argument('--max-iters',type=int,default=100000)
    p.add_argument('--expect-nonconvergence',action='store_true')
    p.add_argument('--asymmetric',action='store_true')
    p.add_argument('--evidence',type=Path)
    p.add_argument('--grid-directory',type=Path,help='New directory retaining full reference/candidate CSVs')
    p.add_argument('--expected-implementation',choices=['serial','mpi','openmp','hybrid'])
    a=p.parse_args()
    if a.expect_nonconvergence and a.mode!='converge':
        p.error('expected non-convergence requires --mode converge')
    prefixes=[]
    for value,threads in [(a.reference_launcher_json,1),(a.launcher_json,a.threads)]:
        prefix=json.loads(value)
        if not isinstance(prefix,list) or any(not isinstance(x,str) for x in prefix):
            p.error('launchers must be JSON arrays of strings')
        prefixes.append([x.format(ranks=a.ranks,threads=threads) for x in prefix])
    if os.environ.get('PBS_JOBID'):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        from pbs_allocation import inspect_allocation
        from mpi_launcher import cpu_limit
        if (a.ranks if prefixes[1] else 1)*a.threads>cpu_limit(inspect_allocation(1)):
            p.error('comparison ranks × threads exceeds the actual PBS allocation')
    evidence=[]
    with tempfile.TemporaryDirectory() as temporary:
        directory=a.grid_directory or Path(temporary)
        if a.grid_directory:
            directory.mkdir(parents=True,exist_ok=False)
        for mode in (['fixed','converge'] if a.mode=='both' else [a.mode]):
            grids,metrics,commands,diagnostics=[],[],[],[]
            for name,exe,prefix in [('reference',a.reference,prefixes[0]),('candidate',a.candidate,prefixes[1])]:
                path=directory/f'{mode}-{name}.csv'
                cmd=prefix+[str(Path(exe).resolve()),'--n',str(a.n),'--mode',mode,'--output',str(path)]
                cmd += ['--iterations',str(a.iterations)] if mode=='fixed' else ['--tol',a.tol,'--max-iters',str(a.max_iters)]
                if a.asymmetric: cmd += ['--problem','asymmetric']
                threads=1 if name=='reference' and prefix else a.threads
                env=dict(os.environ,OMP_NUM_THREADS=str(threads),OMP_DYNAMIC='FALSE',OMP_DISPLAY_AFFINITY='FALSE')
                run=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=120)
                require((run.returncode!=0) if a.expect_nonconvergence else run.returncode==0,
                        f'{name} returned {run.returncode}: {run.stderr}')
                lines=run.stdout.strip().splitlines()
                require(len(lines)==1,'expected exactly one primary JSON line (rank 0)')
                result=json.loads(lines[0])
                require(result.get('N',result.get('n'))==a.n,'incorrect grid size in JSON')
                with path.open() as stream:
                    grid=[list(map(float,row)) for row in csv.reader(stream)]
                require(len(grid)==a.n+2 and all(len(row)==a.n+2 for row in grid),'incorrect gathered shape')
                require(all(math.isfinite(x) for row in grid for x in row),'non-finite grid')
                require(all(x==0 for x in grid[0]+grid[-1]) and all(row[0]==row[-1]==0 for row in grid),'nonzero boundary')
                require(result['mpi_ranks']==(a.ranks if prefix else 1),'incorrect MPI rank count')
                if name=='candidate':
                    require(result['omp_threads']==a.threads,'incorrect effective thread count')
                    if a.expected_implementation:
                        require(result['implementation']==a.expected_implementation,'incorrect candidate implementation')
                if result['implementation']=='hybrid':
                    required=result.get('mpi_thread_required',0)
                    require(required>0 and result.get('mpi_thread_provided',-1)>=required,'insufficient MPI FUNNELED support')
                    require(result.get('rhs_storage')=='unscaled','unexpected hybrid RHS contract')
                if a.expect_nonconvergence:
                    require(result['converged'] is False and result['iterations_completed']==a.max_iters,'incorrect non-convergence state')
                independent=metrics_from_grid(grid,a.n,a.asymmetric)
                for key,value in independent.items():
                    require(math.isfinite(result[key]) and math.isclose(result[key],value,abs_tol=1e-10,rel_tol=1e-8),
                            f'{name} {key} disagrees with complete-grid recomputation')
                grids.append(grid);metrics.append(result);commands.append(cmd)
                diagnostics.append(dict(stdout=run.stdout,stderr=run.stderr,returncode=run.returncode,independent_metrics=independent))
            largest=max(abs(x-y) for r,s in zip(*grids) for x,y in zip(r,s))
            require(all(math.isclose(x,y,abs_tol=1e-10,rel_tol=1e-8) for r,s in zip(*grids) for x,y in zip(r,s)),
                    f'pointwise solution mismatch, max absolute difference={largest}')
            for key in ['iterations_completed','converged','max_update','residual_linf','error_linf']:
                x,y=metrics[0][key],metrics[1][key]
                if x is None or y is None or isinstance(x,bool) or isinstance(y,bool):
                    require(x==y,f'{key} mismatch')
                else:
                    require(math.isclose(x,y,abs_tol=1e-10,rel_tol=1e-8),f'{key} mismatch: {x}, {y}')
            evidence.append(dict(mode=mode,n=a.n,ranks=a.ranks if prefixes[1] else 1,threads=a.threads,
                commands=commands,diagnostics=diagnostics,reference=metrics[0],candidate=metrics[1],max_absolute_difference=largest,
                grid_directory=str(directory) if a.grid_directory else None))
            print(f'PASS {mode}: N={a.n}, ranks={a.ranks if prefixes[1] else 1}, threads={a.threads}, max_diff={largest:.3g}')
    if a.evidence:
        with a.evidence.open('x') as stream:
            json.dump(dict(passed=True,atol=1e-10,rtol=1e-8,cases=evidence),stream,indent=2)
            stream.write('\n')


if __name__=='__main__':
    main()
