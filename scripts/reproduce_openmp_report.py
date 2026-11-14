#!/usr/bin/env python3
"""Verify recovered Vanda OpenMP evidence and reproduce one CSV and two PDFs.

Offline only: no extraction, solver execution, scheduling, or Git mutations.
Requires Python 3; figures use Matplotlib (prepared with version 3.10.6).
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import random
import re
import shlex
import statistics
import tarfile

BENCH_SHA='87252b2ae86028a94a841cdcaf6c78768d04b1ef3b1a95207da0ede27397aeee'
VALIDATION_SHA='c99a65ddef1f973b17ef0db7061049bafc39258f7ae1c940eec82980899c9832'
COMMIT='49892e7af795edc3c8adc14ddda21513d4d465c2'
SIZES=(128,256,512,1024)
THREADS=(1,2,4,8)


def require(condition,message):
    if not condition:
        raise ValueError(message)


def read_archive(path,expected):
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==expected,'Evidence archive checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        members=archive.getmembers()
        require(len({m.name for m in members})==len(members),'Duplicate archive members')
        require(all(not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts
                    and (m.isdir() or m.isfile()) for m in members),'Unsafe archive member')
        return {m.name:archive.extractfile(m).read() for m in members if m.isfile()}


def close(x,y):
    return math.isfinite(x) and math.isfinite(y) and math.isclose(x,y,abs_tol=1e-10,rel_tol=1e-8)


def verify(benchmark,comparison):
    files=read_archive(benchmark,BENCH_SHA)
    metadata=json.loads(files['measurements/metadata.json'])
    allocation=json.loads(files['allocation.json'])
    require(metadata['pbs_allocation']==allocation and metadata['site']=='vanda'
            and metadata['hostname']=='GN-A40-075' and metadata['nodes']==1,'Benchmark identity mismatch')
    require(allocation['job_id']=='1536259.stdct-mgmt-02' and allocation['resources']['job_state']=='R'
            and allocation['resources']['Resource_List.ncpus']=='8'
            and allocation['resources']['Resource_List.place']=='shared'
            and allocation['allowed_os_cpus']==[1,3,5,7,17,19,21,23],'Allocation mismatch')
    provenance=metadata['source_provenance']
    require(metadata['git_head']==provenance['git_head'] and metadata['git_status']==provenance['git_status']
            and provenance['git_head']['stdout'].strip()==COMMIT and provenance['git_status']['stdout']==''
            and provenance['git_head']['returncode']==provenance['git_status']['returncode']==0,'Source provenance mismatch')
    args=metadata['arguments']
    require(args['serial'] is None and args['kind']=='openmp' and args['repeats']==3
            and args['warmups']==1 and args['iterations']==1000 and args['seed']==5208,'Protocol mismatch')
    build=metadata['build_log']
    require(all(s in build for s in ['-O3','-DNDEBUG','-std=c++17','-fopenmp'])
            and '-ffast-math' not in build and '-Ofast' not in build,'Build flags mismatch')
    raw=[json.loads(s) for s in files['measurements/raw.jsonl'].splitlines() if s.strip()]
    warm=[json.loads(s) for s in files['measurements/warmups.jsonl'].splitlines() if s.strip()]
    require(len(raw)==48 and len(warm)==16,'Expected 48 measurements and 16 excluded warmups')
    groups=collections.defaultdict(list); warm_groups=collections.Counter()
    expected={(n,t) for n in SIZES for t in THREADS}
    for row in raw+warm:
        key=(row['N'],row['omp_threads'])
        require(key in expected and row['implementation']=='openmp' and row['site']=='vanda'
                and row['run_id']==metadata['run_id'] and row['hostname']=='GN-A40-075'
                and row['mpi_ranks']==1 and row['allocated_cpus']==8 and row['nodes']==1
                and row['problem']=='symmetric' and row['mode']=='fixed' and row['iterations_completed']==1000
                and row['converged'] is None and row['max_update'] is None
                and row['placement']=='OMP_PLACES=cores; OMP_PROC_BIND=close'
                and math.isfinite(row['solve_seconds']) and row['solve_seconds']>0,'Unexpected benchmark record')
        require(row['command']==[args['solver'],'--n',str(row['N']),'--mode','fixed','--iterations','1000'],
                'Unexpected benchmark command')
        if row['warmup'] is True:
            require(row['repeat']==0,'Warmup repeat mismatch')
            warm_groups[key]+=1
        else:
            require(row['warmup'] is False,'Invalid warmup flag')
            groups[key].append(row)
        h=1/(row['N']+1); rho=math.cos(math.pi*h)
        amplitude=math.pi**2*h*h/2*(1-rho**1000)/(1-rho)
        peak=math.sin(math.pi*(row['N']//2)*h)**2
        require(close(row['error_linf'],abs(1-amplitude)*peak)
                and close(row['residual_linf'],2*math.pi**2*rho**1000*peak),
                'Benchmark diagnostics disagree with discrete sine-mode prediction')
    require(set(groups)==expected and set(warm_groups)==expected and all(v==1 for v in warm_groups.values())
            and all(len(g)==3 and {r['repeat'] for r in g}=={1,2,3} for g in groups.values()),
            'Missing/duplicate repetitions or configurations')
    schedule=[(n,t,k) for n in SIZES for t in THREADS for k in [1,2,3]]
    random.Random(5208).shuffle(schedule)
    require([(r['N'],r['omp_threads'],r['repeat']) for r in raw]==schedule,'Shuffled measurement order mismatch')
    stdout=re.split(r'\nrun=\d+ ',files['measurements/stdout.log'].decode())[1:]
    stderr=re.split(r'\nrun=\d+ ',files['measurements/stderr.log'].decode())[1:]
    require(len(stdout)==len(stderr)==64,'Incomplete launch logs')
    for row,out,err in zip(warm+raw,stdout,stderr):
        require(shlex.join(row['command']) in out and shlex.join(row['command']) in err,'Launch log order mismatch')
        result=json.loads(next(s for s in out.splitlines() if s.startswith('{')))
        require(all(row[k]==v for k,v in result.items()),'Raw record differs from primary solver JSON')
        masks=[int(x) for x in re.findall(r'level 1 thread \S+ affinity (\d+)\s*$',err,re.M)]
        expected_masks=allocation['allowed_os_cpus'][:row['omp_threads']] if row['omp_threads']>1 else []
        require(sorted(masks)==expected_masks,'Unexpected affinity diagnostics')

    validation=read_archive(comparison,VALIDATION_SHA)
    status=json.loads(validation['status.json'])
    require(status['job_id']=='1537318.stdct-mgmt-02' and status['kind']=='serial-compare'
            and status['success'] is True and status['exit_status']==0 and status['phase']=='complete'
            and status['hostname']=='GN-A40-075','Comparison job did not complete successfully')
    require(b'100% tests passed, 0 tests failed out of 3' in validation['validation.log'],'CTest failure')
    max_difference=0.; count=0
    for problem in ['symmetric','asymmetric']:
        for threads in THREADS:
            receipt=json.loads(validation[f'serial-comparison/{problem}-{threads}.json'])
            require(receipt['passed'] is True and receipt['atol']==1e-10 and receipt['rtol']==1e-8
                    and len(receipt['cases'])==2,'Invalid comparison receipt')
            require({c['mode'] for c in receipt['cases']}=={'fixed','converge'},'Missing stop mode')
            for case in receipt['cases']:
                require(case['n']==10 and case['threads']==threads and case['max_absolute_difference']<=1e-10,
                        'Invalid grid-comparison result')
                ref,candidate=case['reference'],case['candidate']
                require(ref['implementation']=='serial' and candidate['implementation']=='openmp'
                        and ref['problem']==candidate['problem']==problem and candidate['omp_threads']==threads,
                        'Wrong reference/candidate')
                for key in ['iterations_completed','converged','max_update','residual_linf','error_linf']:
                    x,y=ref[key],candidate[key]
                    require(x==y if x is None or y is None or isinstance(x,bool) else close(x,y),'Numerical mismatch')
                require(ref['iterations_completed']==(31 if case['mode']=='fixed' else (480 if problem=='symmetric' else 199)),
                        'Iteration count mismatch')
                count+=1; max_difference=max(max_difference,case['max_absolute_difference'])
    require(count==16,'Incomplete comparison matrix')
    return groups,dict(benchmark_job='1536259.stdct-mgmt-02',source_commit=COMMIT,
        measurements=48,excluded_warmups=16,groups=16,repetitions_per_group=3,
        explicit_multithread_affinity_launches=48,one_thread_launches_without_explicit_mask=16,
        benchmark_terminal_pbs_status_available=False,comparison_job='1537318.stdct-mgmt-02',
        comparison_terminal_success=True,comparison_ctest_suites=3,comparison_receipts=16,
        comparison_recorded_max_grid_difference=max_difference,comparison_grid_csvs_available=False,
        comparison_source_or_binary_hash_linkage_available=False)


def summarize(groups):
    baselines={n:statistics.median(r['solve_seconds'] for r in groups[(n,1)]) for n in SIZES}
    rows=[]
    for (n,threads),group in sorted(groups.items()):
        times=[r['solve_seconds'] for r in group]; median=statistics.median(times)
        base_times=[r['solve_seconds'] for r in groups[(n,1)]]
        speedup=baselines[n]/median
        rows.append(dict(N=n,K=1000,omp_threads=threads,samples=3,median_seconds=median,
            min_seconds=min(times),max_seconds=max(times),openmp_1thread_speedup=speedup,
            openmp_1thread_efficiency_percent=100*speedup/threads,
            speedup_observed_lower=min(base_times)/max(times) if threads!=1 else 1.,
            speedup_observed_upper=max(base_times)/min(times) if threads!=1 else 1.))
    return rows


def figures(rows,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import ScalarFormatter
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,
        'axes.labelsize':10,'legend.fontsize':8,'pdf.fonttype':42,'ps.fonttype':42,
        'axes.spines.top':False,'axes.spines.right':False})
    colors=['#0072B2','#D55E00','#009E73','#CC79A7']
    for metric,name,ylabel in [('median_seconds','openmp_runtime','Median solve time (ms)'),
                              ('openmp_1thread_speedup','openmp_speedup','Speedup vs OpenMP one thread')]:
        fig,axs=plt.subplots(2,2,figsize=(8.2,6.1),layout='constrained')
        for n,color,ax in zip(SIZES,colors,axs.flat):
            group=[r for r in rows if r['N']==n]
            x=[r['omp_threads'] for r in group]
            if metric=='median_seconds':
                ax.errorbar(x,[r[metric]*1000 for r in group],
                    yerr=[[1000*(r[metric]-r['min_seconds']) for r in group],
                          [1000*(r['max_seconds']-r[metric]) for r in group]],
                    fmt='-o',color=color,capsize=3,label='Median; observed min–max')
                ax.set_ylim(bottom=0)
            else:
                ax.plot(x,[r[metric] for r in group],'-o',color=color,label='OpenMP, same executable')
                ax.plot(THREADS,THREADS,'--',color='#777777',lw=1,label='Linear reference S = T')
                ax.set_ylim(bottom=0)
            ax.set_xscale('log',base=2);ax.set_xticks(THREADS);ax.xaxis.set_major_formatter(ScalarFormatter())
            ax.set_title(f'N = {n}');ax.set_ylabel(ylabel);ax.grid(alpha=.2);ax.legend(loc='best')
        fig.supxlabel('OpenMP threads T (one process)')
        title='Median and observed min–max' if metric=='median_seconds' else 'Same-implementation baseline: OpenMP one thread'
        fig.suptitle(f'Vanda GN-A40-075 • K = 1000 • 3 measured repetitions\n{title}',fontsize=10)
        fig.savefig(out/f'{name}.pdf',bbox_inches='tight',metadata={'Creator':'OpenMP Vanda evidence analysis'})
        plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('benchmark',type=Path)
    p.add_argument('--validation',type=Path,required=True)
    p.add_argument('--output',type=Path,help='New directory for summary.csv and two PDFs')
    p.add_argument('--audit-only',action='store_true')
    a=p.parse_args()
    require(a.audit_only or a.output is not None,'Supply --output or --audit-only')
    require(a.output is None or not a.output.exists(),'Output directory must be new')
    groups,audit=verify(a.benchmark,a.validation)
    print(json.dumps(audit,indent=2))
    if a.audit_only:
        return
    rows=summarize(groups)
    a.output.mkdir(parents=True)
    with (a.output/'summary.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    figures(rows,a.output)
    print(f'{a.output}: 16 summary rows and two PDFs; no experiments run.')


if __name__=='__main__':
    main()
