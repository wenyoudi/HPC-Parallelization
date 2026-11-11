#!/usr/bin/env python3
"""Single-node strong scaling with a same-allocation serial baseline."""
import argparse
import csv
import datetime
import json
import platform
from pathlib import Path
import statistics
import subprocess
from mpi_workflow import invoke, launch_context, sha

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', required=True, type=Path)
    p.add_argument('--mpi', required=True, type=Path)
    p.add_argument('--validation', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--n', nargs='+', type=int, default=[256, 512, 1024])
    p.add_argument('--ranks', nargs='+', type=int, default=[1, 2, 4, 8])
    p.add_argument('--iterations', type=int, default=1000)
    p.add_argument('--repeats', type=int, default=3)
    a = p.parse_args()
    if min(a.n+a.ranks+[a.iterations])<1 or a.repeats<3: p.error('Positive sizes/iterations/ranks and at least 3 repeats required')
    if max(a.ranks)>min(a.n): p.error('ranks must not exceed N')
    serial, mpi = str(a.serial.resolve()), str(a.mpi.resolve())
    evidence = json.loads(a.validation.read_text())
    hashes = dict(serial=sha(serial), mpi=sha(mpi))
    if not evidence.get('passed') or evidence.get('binary_sha256') != hashes:
        p.error('Successful validation of these exact binaries is required')
    if not set(a.ranks).issubset(evidence.get('ranks', [])):
        p.error('Validate every requested MPI rank count before benchmarking')
    launch, allocation = launch_context(None, max(a.ranks))
    validated_host = evidence.get('context', {}).get('hostname')
    if validated_host != allocation['hostname']: p.error('Validate and benchmark on the same compute node')
    a.output_dir.mkdir(parents=True, exist_ok=False)
    def output(cmd):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout.strip()
    metadata = dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        allocation=allocation, binary_sha256=hashes, validation_sha256=sha(a.validation),
        revision=output(['git','rev-parse','HEAD']), git_status=output(['git','status','--short']),
        compiler=output(['mpicxx','--version']), mpi=output(['mpirun','--version']),
        cpu=output(['lscpu']), cmake=output(['cmake','--version']),
        platform=platform.platform(), experiment=vars(a).copy())
    (a.output_dir/'metadata.json').write_text(json.dumps(metadata, indent=2, default=str)+'\n')
    records = []
    with (a.output_dir/'raw.jsonl').open('x') as raw, (a.output_dir/'warmups.jsonl').open('x') as warmups:
        for n in a.n:
            common = ['--n',str(n),'--problem','asymmetric','--mode','fixed','--iterations',str(a.iterations)]
            configs = [('serial',1,launch(1)+[serial])] + [('mpi',r,launch(r)+[mpi]) for r in a.ranks]
            for implementation,ranks,command in configs:
                m,log = invoke(command+common)
                warmups.write(json.dumps(dict(metrics=m, execution=log))+'\n'); warmups.flush()
            # Rotate order across fresh invocations to reduce ordering bias.
            for repeat in range(a.repeats):
                order = configs[repeat%len(configs):]+configs[:repeat%len(configs)]
                for implementation,ranks,command in order:
                    m,log = invoke(command+common)
                    if m['implementation'] != implementation or m['mpi_ranks'] != ranks or m['iterations_completed'] != a.iterations:
                        raise ValueError('Unexpected solver configuration')
                    row = dict(n=n, implementation=implementation, ranks=ranks, repeat=repeat, metrics=m, execution=log)
                    raw.write(json.dumps(row)+'\n'); raw.flush(); records.append(row)
    with (a.output_dir/'summary.csv').open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['n','implementation','ranks','median_seconds','min_seconds','max_seconds','speedup_vs_serial','efficiency_vs_serial','speedup_vs_mpi1'])
        writer.writeheader()
        for n in a.n:
            def times(kind,r): return [row['metrics']['solve_seconds'] for row in records if row['n']==n and row['implementation']==kind and row['ranks']==r]
            baseline = statistics.median(times('serial',1))
            mpi1 = statistics.median(times('mpi',1)) if 1 in a.ranks else None
            for kind,r in [('serial',1)]+[('mpi',r) for r in a.ranks]:
                ts = times(kind,r); median = statistics.median(ts)
                writer.writerow(dict(n=n,implementation=kind,ranks=r,median_seconds=median,min_seconds=min(ts),max_seconds=max(ts),
                    speedup_vs_serial=baseline/median,efficiency_vs_serial=baseline/median/r,
                    speedup_vs_mpi1=mpi1/median if kind=='mpi' and mpi1 is not None else ''))
    print(f'Saved strong-scaling evidence to {a.output_dir}')

if __name__ == '__main__': main()
