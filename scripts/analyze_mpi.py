#!/usr/bin/env python3
"""Recompute scaling from raw MPI measurements and export PNG/PDF figures.

Input is the benchmark directory, not a hand-edited summary. No measured input
ships with this script. Matplotlib is only needed on the analysis machine.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics


def summarize(records):
    groups = {}
    experiment = None
    for row in records:
        m = row['metrics']
        n, kind, ranks, repeat = row['n'], row['implementation'], row['ranks'], row['repeat']
        if kind not in ('serial','mpi') or ranks<1 or n<ranks or repeat<0:
            raise ValueError('Invalid configuration in raw records')
        if kind == 'serial' and ranks != 1: raise ValueError('Serial must use one rank')
        if m['n'] != n or m['implementation'] != kind or m['mpi_ranks'] != ranks or m['omp_threads'] != 1:
            raise ValueError('Raw identity disagrees with solver metrics')
        signature = (m['problem'], m['mode'], m['iterations_completed'])
        if signature[1] != 'fixed' or signature[2] < 1: raise ValueError('Expected fixed-work strong scaling')
        if experiment is None: experiment = signature
        if signature != experiment: raise ValueError('Cannot mix workloads')
        seconds = m['solve_seconds']
        if not math.isfinite(seconds) or seconds <= 0: raise ValueError('Solve time must be finite and positive')
        group = groups.setdefault((n,kind,ranks), {})
        if repeat in group: raise ValueError('Duplicate repeat')
        group[repeat] = seconds
    if not groups: raise ValueError('No measured records')
    for group in groups.values():
        if len(group)<3: raise ValueError('At least three repeats per configuration required')
    patterns = {tuple(sorted(r for nn,k,r in groups if nn==n and k=='mpi')) for n,_,_ in groups}
    if len(patterns) != 1 or not next(iter(patterns)): raise ValueError('Every N must have the same MPI rank sweep')
    summary = []
    for (n,kind,ranks), runs in sorted(groups.items()):
        baseline = groups.get((n,'serial',1))
        if baseline is None: raise ValueError('Same-workload serial baseline is missing')
        ts = list(runs.values()); med = statistics.median(ts)
        serial_time = statistics.median(baseline.values())
        mpi1 = groups.get((n,'mpi',1))
        summary.append(dict(n=n,implementation=kind,ranks=ranks,repeats=len(ts),median_seconds=med,
            min_seconds=min(ts),max_seconds=max(ts),serial_median_seconds=serial_time,
            mpi1_median_seconds=statistics.median(mpi1.values()) if mpi1 else None,
            speedup_vs_serial=serial_time/med, efficiency_vs_serial=serial_time/med/ranks,
            speedup_vs_mpi1=statistics.median(mpi1.values())/med if mpi1 and kind=='mpi' else None))
    return summary, experiment


def plot(summary, experiment, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False,
                         'pdf.fonttype':42, 'savefig.dpi':180})
    ns = sorted({row['n'] for row in summary})
    ranks = sorted({row['ranks'] for row in summary if row['implementation']=='mpi'})
    styles = {n:(color,marker) for n,color,marker in zip(ns,['#2463A5','#C46B20','#71833A'],['o','s','^'])}
    if len(ns)>3: raise ValueError('Plotting supports at most three grid sizes; add explicit styles for more')
    specs = [('runtime','Solve time (seconds)'), ('speedup','Speedup vs serial'),
             ('efficiency','Efficiency vs serial (%)')]
    if 1 in ranks:
        specs += [('speedup_mpi1','Speedup vs MPI 1 rank'), ('efficiency_mpi1','Efficiency vs MPI 1 rank (%)')]
    for metric, ylabel in specs:
        fig, ax = plt.subplots(figsize=(6.5,4.2), layout='constrained')
        for n in ns:
            rows = sorted((row for row in summary if row['n']==n and row['implementation']=='mpi'), key=lambda x:x['ranks'])
            x = [row['ranks'] for row in rows]
            color,marker = styles[n]
            if metric=='runtime':
                y = [row['median_seconds'] for row in rows]
                low = [row['min_seconds'] for row in rows]; high = [row['max_seconds'] for row in rows]
            else:
                baseline = 'mpi1_median_seconds' if metric.endswith('_mpi1') else 'serial_median_seconds'
                y = [row[baseline]/row['median_seconds'] for row in rows]
                low = [row[baseline]/row['max_seconds'] for row in rows]
                high = [row[baseline]/row['min_seconds'] for row in rows]
                if metric.startswith('efficiency'):
                    y,low,high = [[100*v/r for v,r in zip(values,x)] for values in [y,low,high]]
            line = ax.errorbar(x,y,yerr=[[v-l for v,l in zip(y,low)],[h-v for h,v in zip(high,y)]],
                              color=color,marker=marker,capsize=3,label=f'N={n}')
            if metric=='runtime': ax.axhline(rows[0]['serial_median_seconds'], color=line[0].get_color(),
                linestyle=':', alpha=.65, label=f'Serial N={n}')
        if metric.startswith('speedup'): ax.plot(ranks,ranks,'--',color='#777777',label='Ideal linear speedup')
        if metric.startswith('efficiency'): ax.axhline(100,linestyle='--',color='#777777',label='Ideal efficiency')
        if metric=='runtime': ax.set_yscale('log')
        else: ax.set_ylim(bottom=0)
        ax.set_xscale('log', base=2); ax.set_xticks(ranks, labels=[str(r) for r in ranks])
        ax.set_xlabel('MPI ranks (one thread per rank)'); ax.set_ylabel(ylabel)
        ax.set_title(f'MPI strong scaling — {experiment[0]}, K={experiment[2]}')
        ax.grid(axis='y',alpha=.2); ax.legend(fontsize=8)
        fig.text(.01,-.04,'Median of fresh runs; min–max bars; reference median held fixed for ratios.',fontsize=7)
        for ext in ['png','pdf']: fig.savefig(destination/f'mpi_{metric}.{ext}',bbox_inches='tight')
        plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('benchmark_dir', type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    a = p.parse_args()
    metadata = json.loads((a.benchmark_dir/'metadata.json').read_text())
    if not metadata.get('allocation',{}).get('job_id') or not metadata.get('validation_sha256'):
        p.error('Expected PBS benchmark metadata with a validation evidence hash')
    records = [json.loads(line) for line in (a.benchmark_dir/'raw.jsonl').read_text().splitlines() if line.strip()]
    summary, experiment = summarize(records)
    settings = metadata['experiment']
    if {row['n'] for row in summary} != set(settings['n']): p.error('Grid sweep is incomplete')
    if {row['ranks'] for row in summary if row['implementation']=='mpi'} != set(settings['ranks']): p.error('Rank sweep is incomplete')
    if any(row['repeats'] != settings['repeats'] for row in summary): p.error('Repeat count is incomplete')
    if experiment[2] != settings['iterations']: p.error('Iteration count disagrees with metadata')
    a.output_dir.mkdir(parents=True, exist_ok=False)
    with (a.output_dir/'summary.csv').open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0])); writer.writeheader(); writer.writerows(summary)
    plot(summary,experiment,a.output_dir)
    (a.output_dir/'provenance.json').write_text(json.dumps(dict(source=str(a.benchmark_dir.resolve()),
        metadata=metadata, raw_records=len(records)), indent=2)+'\n')
    print(f'Exported scaling plots (PNG and PDF, serial and MPI-1 baselines) to {a.output_dir}')

if __name__ == '__main__': main()
