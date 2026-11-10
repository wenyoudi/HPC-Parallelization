"""Collect fixed-work serial runs; execute formal benchmarks on HPC compute nodes."""
import argparse
import csv
import json
import platform
import statistics
import subprocess
from pathlib import Path
from datetime import datetime, timezone

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--executable',required=True)
p.add_argument('--sizes',nargs='+',type=int,default=[128,256,512,1024])
p.add_argument('--iterations',type=int,default=1000)
p.add_argument('--repeats',type=int,default=3)
p.add_argument('--problem',choices=['symmetric','asymmetric'],default='symmetric')
p.add_argument('--output-dir',required=True)
a=p.parse_args()
if a.repeats<3 or a.iterations<1 or any(n<1 for n in a.sizes) or len(set(a.sizes))!=len(a.sizes):
    p.error('Use at least three repeats, positive sizes/iterations, and unique sizes')
out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=False)
raw=out/'runs.jsonl';summary=[]
with raw.open('w') as f:
    for n in a.sizes:
        times=[]
        for repeat in range(1,a.repeats+1):
            command=[str(Path(a.executable).resolve()),'--n',str(n),'--mode','fixed','--iterations',str(a.iterations),'--problem',a.problem]
            run=subprocess.run(command,capture_output=True,text=True,check=True)
            row=json.loads(run.stdout)
            if row['n']!=n or row['iterations_completed']!=a.iterations or row['mode']!='fixed':
                raise RuntimeError('Unexpected solver output')
            row.update(repeat=repeat,hostname=platform.node(),utc=datetime.now(timezone.utc).isoformat(),command=command)
            f.write(json.dumps(row)+'\n');f.flush();times.append(row['solve_seconds'])
        summary.append(dict(n=n,iterations=a.iterations,repeats=a.repeats,median_seconds=statistics.median(times),min_seconds=min(times),max_seconds=max(times)))
with (out/'summary.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
print(out)
