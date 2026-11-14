#!/usr/bin/env python3
"""Reproduce the compact table and two report PDFs from Vanda evidence, offline.

Requires Python 3 and Matplotlib (original exports: 3.10.6). Reads the separately
shared archive; never extracts evidence, executes solvers or submits jobs.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import tarfile

SHA256='5ed7283d928154ef58581a959a1e5d107c8b31737dc570927bc2505555e3911b'
COMMIT='7a6b6e7b04fc6b7a1a9f172503dcf7b6b03e9fd8'
JOB='1541184.stdct-mgmt-02'
SIZES=(128,256,512,1024)
CONFIGS=((1,1),(2,1),(4,1),(8,1),(4,2),(2,4),(1,8))


def require(condition,message):
    if not condition:
        raise ValueError(message)


def summarize(path):
    require(hashlib.sha256(path.read_bytes()).hexdigest()==SHA256,'Archive checksum mismatch')
    with tarfile.open(path,'r:gz') as archive:
        def obj(name):
            return json.load(archive.extractfile(name))
        status=obj('status.json'); validation=obj('distributed-validation/validation.json')
        metadata=obj('measurements/metadata.json'); provenance=obj('source-provenance.json')
        allocation=obj('allocation.json')
        raw=[json.loads(line) for line in archive.extractfile('measurements/raw.jsonl') if line.strip()]
        warm=[json.loads(line) for line in archive.extractfile('measurements/warmups.jsonl') if line.strip()]
    require(status['job_id']==JOB and status['hostname']=='CN-140' and status['success'] is True
            and status['exit_status']==0 and status['phase']=='complete','Job status mismatch')
    require(provenance['git_head']['stdout'].strip()==COMMIT and provenance['git_status']['stdout']==''
            and provenance==metadata['source_provenance'],'Source provenance mismatch')
    checks=validation['checks']
    require(validation['passed'] is True and validation['site']=='vanda' and len(checks)==494
            and all(c['passed'] is True for c in checks)
            and sum(c.get('kind')=='expected-error' for c in checks)==8,'Validation receipt mismatch')
    require(metadata['binary_sha256']==validation['binary_sha256']['hybrid']
            and metadata['serial_binary_sha256']==validation['binary_sha256']['serial'],'Binary linkage mismatch')
    require(allocation['job_id']==JOB and allocation['resources']['Resource_List.ncpus']=='8'
            and allocation['resources']['Resource_List.place']=='excl','Allocation mismatch')
    require(len(raw)==96 and len(warm)==32,'Incomplete measurement/warmup evidence')
    expected={(impl,n,r,t) for n in SIZES for impl,r,t in
              [('serial',1,1)]+[('hybrid',r,t) for r,t in CONFIGS]}
    groups=collections.defaultdict(list)
    warm_groups=collections.Counter()
    for record in raw+warm:
        key=(record['implementation'],record['N'],record['mpi_ranks'],record['omp_threads'])
        require(key in expected and record['site']=='vanda' and record['hostname']=='CN-140'
                and record['run_id']==metadata['run_id'] and record['allocated_cpus']==8 and record['nodes']==1
                and record['problem']=='symmetric' and record['mode']=='fixed' and record['iterations_completed']==1000
                and math.isfinite(record['solve_seconds']) and record['solve_seconds']>0,'Unexpected measurement')
        if record['warmup'] is True:
            warm_groups[key]+=1
        else:
            require(record['warmup'] is False,'Invalid warmup flag')
            groups[key].append(record)
    require(set(groups)==expected and set(warm_groups)==expected
            and all(len(g)==3 and {r['repeat'] for r in g}=={1,2,3} for g in groups.values())
            and all(v==1 for v in warm_groups.values()),'Missing/duplicate configurations or repetitions')
    rows=[]
    for (impl,n,r,t),group in sorted(groups.items()):
        times=[record['solve_seconds'] for record in group]
        rows.append(dict(implementation=impl,N=n,K=1000,mpi_ranks=r,omp_threads=t,workers=r*t,samples=3,
                         median_seconds=statistics.median(times),min_seconds=min(times),max_seconds=max(times)))
    serial={r['N']:r['median_seconds'] for r in rows if r['implementation']=='serial'}
    hybrid1={r['N']:r['median_seconds'] for r in rows if r['implementation']=='hybrid' and r['workers']==1}
    for row in rows:
        speedup=hybrid1[row['N']]/row['median_seconds'] if row['implementation']=='hybrid' else ''
        row.update(hybrid_1x1_speedup=speedup,
                   hybrid_1x1_efficiency_percent=100*speedup/row['workers'] if speedup!='' else '',
                   serial_relative_speedup=serial[row['N']]/row['median_seconds'])
    return rows


def figures(rows,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import ScalarFormatter
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,
        'axes.labelsize':10,'legend.fontsize':8,'pdf.fonttype':42,'ps.fonttype':42,
        'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':300})
    colors=['#0072B2','#D55E00','#009E73','#CC79A7']
    selected=[r for r in rows if r['implementation']=='hybrid']
    fig,axs=plt.subplots(2,2,figsize=(8.2,6.1),layout='constrained')
    for n,ax in zip(SIZES,axs.flat):
        group=sorted([r for r in selected if r['N']==n and r['omp_threads']==1],key=lambda r:r['workers'])
        ax.plot([r['workers'] for r in group],[r['hybrid_1x1_speedup'] for r in group],
                '-o',color=colors[0],label='Hybrid, T = 1')
        for color,(r,t),marker in zip(colors[1:],[(4,2),(2,4),(1,8)],['s','^','D']):
            row=next(x for x in selected if x['N']==n and x['mpi_ranks']==r and x['omp_threads']==t)
            ax.plot(8,row['hybrid_1x1_speedup'],marker=marker,color=color,ls='',label=f'{r}×{t}')
        ax.plot([1,8],[1,8],'--',color='#777777',lw=1,label='Linear reference S = P')
        ax.set_xscale('log',base=2);ax.set_xticks([1,2,4,8]);ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.set_title(f'N = {n}');ax.set_ylabel('Speedup vs hybrid 1×1');ax.grid(alpha=.2);ax.legend(loc='best',fontsize=7)
    fig.supxlabel('Workers P = MPI ranks × threads per rank',fontsize=10)
    fig.suptitle('Vanda CN-140 • hybrid 1×1 baseline • K = 1000\n'
                 'Ratios of medians; 3 measured repetitions per configuration',fontsize=10)
    fig.savefig(out/'speedup.pdf',bbox_inches='tight',metadata={'Creator':'Vanda evidence analysis'})
    plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(8.2,6.1),layout='constrained')
    for n,ax in zip(SIZES,axs.flat):
        group=[next(x for x in selected if x['N']==n and (x['mpi_ranks'],x['omp_threads'])==c)
               for c in [(8,1),(4,2),(2,4),(1,8)]]
        for i,(row,color) in enumerate(zip(group,colors)):
            med=row['median_seconds']*1000
            ax.bar(i,med,color=color,width=.65)
            ax.errorbar(i,med,yerr=[[1000*(row['median_seconds']-row['min_seconds'])],
                        [1000*(row['max_seconds']-row['median_seconds'])]],fmt='none',color='#222222',capsize=3)
            ax.annotate(f'{med:.2f}',(i,row['max_seconds']*1000),xytext=(0,6),
                        textcoords='offset points',ha='center',fontsize=9)
        ax.set_xticks(range(4),['8×1','4×2','2×4','1×8']);ax.set_ylabel('Solve time (ms)')
        ax.set_ylim(0,max(r['max_seconds']*1000 for r in group)*1.22)
        ax.set_title(f'N = {n}');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.supxlabel('Eight workers: MPI ranks × OpenMP threads per rank')
    fig.suptitle('Vanda CN-140 • K = 1000 • medians and min–max of 3 measurements',fontsize=11)
    fig.savefig(out/'eight_workers.pdf',bbox_inches='tight',metadata={'Creator':'Vanda evidence analysis'})
    plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path,help='Separately shared hybrid-vanda-results-1541184.tar.gz')
    p.add_argument('--output',type=Path,required=True,help='New directory for summary.csv and two PDFs')
    args=p.parse_args()
    require(not args.output.exists(),'Output directory must be new; existing evidence is never overwritten')
    rows=summarize(args.archive)
    args.output.mkdir(parents=True)
    with (args.output/'summary.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    figures(rows,args.output)
    print(f'{args.output}: 32 summary rows and two PDFs reproduced from 96 measurements; no experiments run.')


if __name__=='__main__':
    main()
