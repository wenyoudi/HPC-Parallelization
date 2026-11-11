#!/usr/bin/env python3
"""Retain serial/MPI/hybrid grid comparisons, including uneven rows and stop modes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from mpi_launcher import MODES,cpu_limit,launcher
from pbs_allocation import inspect_allocation


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial',required=True)
    p.add_argument('--mpi',required=True)
    p.add_argument('--hybrid')
    p.add_argument('--site',choices=['vanda','local'],default='vanda')
    p.add_argument('--allocated-cpus',type=int,default=8,help='Local correctness budget only; Vanda uses live PBS allocation')
    p.add_argument('--launcher-json',help='Local MPI launcher, e.g. ["mpirun","-n","{ranks}"]')
    p.add_argument('--launcher-mode',choices=MODES,default=os.environ.get('VANDA_MPI_LAUNCHER','single-node'))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    for name in ['serial','mpi','hybrid']:
        path=getattr(a,name)
        if path and not Path(path).is_file(): p.error(f'actual {name} executable missing: {path}')
    if a.site=='vanda':
        if a.launcher_json: p.error('Vanda uses the verified --launcher-mode and live PBS resources')
        allocation=inspect_allocation(1)
        prefix_template=None
    else:
        if not a.launcher_json: p.error('Local validation requires --launcher-json')
        prefix_template=json.loads(a.launcher_json)
        if not isinstance(prefix_template,list) or any(not isinstance(s,str) for s in prefix_template):
            p.error('launcher must be a JSON array of strings')
        if a.allocated_cpus<1 or a.allocated_cpus>(os.cpu_count() or 1):
            p.error('invalid local CPU budget')
        allocation=dict(hostname=platform.node(),nodes=[platform.node()],
            resources={'Resource_List.ncpus':str(a.allocated_cpus)},
            allowed_os_cpus=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None)
    budget=cpu_limit(allocation)
    a.output.mkdir(parents=True,exist_ok=False)
    report=dict(passed=False,site=a.site,allocation=allocation,
        launcher_mode=a.launcher_mode if a.site=='vanda' else 'custom-local',
        binary_sha256={name:sha(getattr(a,name)) for name in ['serial','mpi','hybrid'] if getattr(a,name)},
        checks=[],not_run_due_to_allocation=[],
        scope='Full-grid comparisons and independently recomputed diagnostics; hybrid runtime FUNNELED checks; not performance measurements')

    def launch(ranks,threads):
        if ranks*threads>budget: raise ValueError('ranks × threads exceeds CPU allocation')
        if a.site=='vanda': return launcher(allocation,ranks,threads,a.launcher_mode)
        return [s.format(ranks=ranks,threads=threads) for s in prefix_template]

    jobs=[]
    for ranks in [1,2,3,4,8]:
        if ranks<=budget:
            for n in sorted({10,ranks}): jobs.append(('mpi',ranks,1,n))
        else: report['not_run_due_to_allocation'].append(dict(implementation='mpi',mpi_ranks=ranks,omp_threads=1))
    if a.hybrid:
        for ranks,threads in [(1,1),(2,1),(4,1),(8,1),(3,2),(2,2),(1,4),(4,2),(2,4),(1,8)]:
            if ranks*threads<=budget:
                for n in sorted({10,ranks}): jobs.append(('hybrid',ranks,threads,n))
            else: report['not_run_due_to_allocation'].append(dict(implementation='hybrid',mpi_ranks=ranks,omp_threads=threads))
    try:
        for implementation,ranks,threads,n in jobs:
            for reference in (['serial','mpi'] if implementation=='hybrid' else ['serial']):
                for problem in ['symmetric','asymmetric']:
                    modes=[('fixed',1),('fixed',2),('fixed',31),('converge',0)]
                    if n>=2: modes.append(('limit',0))
                    for mode,k in modes:
                        case=f'{implementation}-vs-{reference}-n{n}-r{ranks}-t{threads}-{problem}-{mode}-k{k}'
                        cmd=[sys.executable,'tests/compare_solvers.py','--reference',getattr(a,reference),
                            '--candidate',getattr(a,implementation),'--launcher-json',json.dumps(launch(ranks,threads)),
                            '--expected-implementation',implementation,'--n',str(n),'--ranks',str(ranks),'--threads',str(threads),
                            '--mode','fixed' if mode=='fixed' else 'converge','--iterations',str(k),
                            '--evidence',str(a.output/f'{case}.json'),'--grid-directory',str(a.output/'grids'/case)]
                        if reference=='mpi': cmd += ['--reference-launcher-json',json.dumps(launch(ranks,1))]
                        if mode=='limit': cmd += ['--expect-nonconvergence','--max-iters','1','--tol','1e-15']
                        if problem=='asymmetric': cmd.append('--asymmetric')
                        run=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
                        (a.output/f'{case}.stdout.log').write_text(run.stdout)
                        (a.output/f'{case}.stderr.log').write_text(run.stderr)
                        report['checks'].append(dict(case=case,command=cmd,passed=run.returncode==0,
                            implementation=implementation,reference=reference,mpi_ranks=ranks,omp_threads=threads,
                            n=n,problem=problem,mode=mode))
                        if run.returncode: raise RuntimeError(f'Validation failed: {case}; see saved logs')
                        if len(report['checks'])%20==0: print(f"{a.site}: {len(report['checks'])} numerical comparisons passed",flush=True)
        # Fatal input/output errors must terminate all ranks without hanging.
        for implementation in ['mpi']+(['hybrid'] if a.hybrid else []):
            ranks=min(2,budget)
            executable=str(Path(getattr(a,implementation)).resolve())
            failures=[('bad-mode',['--n','10','--mode','bad']),
                      ('incompatible-options',['--n','10','--mode','converge','--iterations','3'])]
            if ranks>1: failures.append(('ranks-exceed-n',['--n','1','--mode','fixed','--iterations','1']))
            existing=a.output/f'{implementation}-preserve-existing.csv'
            existing.write_text('preserve existing file\n')
            failures.append(('output-overwrite',['--n','10','--mode','fixed','--iterations','1','--output',str(existing)]))
            for name,options in failures:
                cmd=launch(ranks,1)+[executable]+options
                run=subprocess.run(cmd,env=dict(os.environ,OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE'),
                                   capture_output=True,text=True,timeout=60)
                case=f'{implementation}-{name}'
                (a.output/f'{case}.stdout.log').write_text(run.stdout)
                (a.output/f'{case}.stderr.log').write_text(run.stderr)
                passed=run.returncode!=0 and existing.read_text()=='preserve existing file\n'
                report['checks'].append(dict(case=case,command=cmd,passed=passed,implementation=implementation,kind='expected-error'))
                if not passed: raise RuntimeError(f'Failure handling check did not pass: {case}')
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        (a.output/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"{a.site}: all {len(report['checks'])} validation checks passed",flush=True)


if __name__=='__main__':
    main()
