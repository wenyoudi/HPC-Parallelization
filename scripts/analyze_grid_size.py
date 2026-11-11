"""Plot existing Vanda serial timings or completed grid-refinement results."""
import argparse
import csv
import hashlib
import json
import statistics
import tarfile
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--runtime-archive')
    group.add_argument('--refinement-dir')
    p.add_argument('--output-dir',required=True)
    a=p.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=False)
    if a.runtime_archive:
        path=Path(a.runtime_archive)
        with tarfile.open(path) as archive:
            status=json.load(archive.extractfile('status.json'))
            if not status['success']: raise ValueError('Source job failed')
            rows=[json.loads(line) for line in archive.extractfile('measurements/raw.jsonl') if line.strip()]
            rows=[r for r in rows if r['implementation']=='serial' and not r['warmup']]
            if len(rows)!=12: raise ValueError('Expected 12 serial measurements')
            summary=[]
            for n in [128,256,512,1024]:
                samples=[r for r in rows if r['n']==n]
                if len(samples)!=3 or {r['repeat'] for r in samples}!={1,2,3}: raise ValueError('Invalid repeat coverage')
                if any(r['mode']!='fixed' or r['iterations_completed']!=1000 or r['problem']!='symmetric' or r['hostname']!='CN-140' or r['site']!='vanda' for r in samples): raise ValueError('Mixed experimental settings')
                values=[r['solve_seconds'] for r in samples]
                summary.append(dict(n=n,iterations=1000,repeats=3,median_seconds=statistics.median(values),min_seconds=min(values),max_seconds=max(values)))
            (out/'serial_runs.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            provenance=dict(archive=path.name,archive_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),job=status['job_id'],hostname='CN-140',note='Reused contributor-provided Vanda serial measurements; no new solver execution')
            (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
            fig,ax=plt.subplots(figsize=(7,4.5),layout='constrained')
            x=[r['n'] for r in summary];y=[r['median_seconds'] for r in summary]
            ax.errorbar(x,y,yerr=[[r['median_seconds']-r['min_seconds'] for r in summary],[r['max_seconds']-r['median_seconds'] for r in summary]],marker='o',capsize=4,label='Median; range of 3 runs')
            ax.plot(x,[y[0]*(n/x[0])**2 for n in x],'--',color='gray',label='N² reference (anchored at N=128)')
            ax.set(xscale='log',yscale='log',xlabel='Interior grid size N (N × N points)',ylabel='Solver time (s)',title='Serial fixed-work runtime on Vanda CN-140')
            ax.set_xticks(x,labels=[str(n) for n in x])
            ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
            ax.legend();ax.grid(alpha=.2)
            fig.text(.5,-.03,'1000 Jacobi iterations; symmetric forcing; one bound CPU core.',ha='center',fontsize=9)
            stem='serial_grid_runtime'
        with (out/'summary.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    else:
        source=Path(a.refinement_dir)
        if not json.loads((source/'status.json').read_text())['passed']:raise ValueError('Refinement incomplete')
        meta=json.loads((source/'metadata.json').read_text())
        if meta['site']!='vanda':raise ValueError('Formal figures require Vanda results')
        with (source/'summary.csv').open() as f: rows=list(csv.DictReader(f))
        fig,ax=plt.subplots(figsize=(7,4.5),layout='constrained')
        for problem in ['symmetric','asymmetric']:
            selected=sorted([r for r in rows if r['problem']==problem],key=lambda r:float(r['h']))
            if not selected:raise ValueError('Missing problem')
            x=[float(r['h']) for r in selected];y=[float(r['error_linf']) for r in selected]
            ax.loglog(x,y,'o-',label=problem.capitalize())
        ax.loglog(x,[y[0]*(h/x[0])**2 for h in x],'--',color='gray',label='h² reference')
        ax.set(xlabel='Grid spacing h = 1/(N+1)',ylabel='Maximum error against analytic solution',title='Serial spatial convergence on Vanda')
        ax.legend();ax.grid(alpha=.2);stem='serial_grid_accuracy'
        (out/'source_metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
        (out/'summary.csv').write_bytes((source/'summary.csv').read_bytes())
    fig.savefig(out/(stem+'.png'),dpi=220,bbox_inches='tight')
    fig.savefig(out/(stem+'.pdf'),bbox_inches='tight')
    plt.close(fig)
    print(out)


if __name__=='__main__':
    main()
