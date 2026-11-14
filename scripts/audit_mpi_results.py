#!/usr/bin/env python3
"""Audit transferred cluster evidence, independently of a working MPI runtime."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from analyze_mpi import summarize
from compare_solutions import read_grid

def require(condition, message):
    if not condition: raise ValueError(message)

def audit(root):
    validation_path=root/'validation/validation.json'
    validation=json.loads(validation_path.read_text())
    metadata=json.loads((root/'benchmark/metadata.json').read_text())
    require(validation.get('passed') and all(c['passed'] for c in validation['checks']), 'Validation failed')
    require(hashlib.sha256(validation_path.read_bytes()).hexdigest()==metadata['validation_sha256'], 'Validation hash mismatch')
    require(validation['binary_sha256']==metadata['binary_sha256'], 'Binary evidence mismatch')
    require(validation['context']['hostname']==metadata['allocation']['hostname'], 'Different validation/benchmark nodes')
    records=[json.loads(line) for line in (root/'benchmark/raw.jsonl').read_text().splitlines() if line.strip()]
    summary,experiment=summarize(records)
    settings=metadata['experiment']
    require({r['n'] for r in summary}==set(settings['n']), 'Incomplete N sweep')
    require({r['ranks'] for r in summary if r['implementation']=='mpi'}==set(settings['ranks']), 'Incomplete rank sweep')
    require(all(r['repeats']==settings['repeats'] for r in summary), 'Wrong repeats')
    require(experiment[2]==settings['iterations'], 'Wrong iteration count')
    reference=list(csv.DictReader((root/'benchmark/summary.csv').open()))
    require(len(reference)==len(summary), 'Summary row count differs')
    for saved in reference:
        row=next(r for r in summary if (r['n'],r['implementation'],r['ranks'])==(int(saved['n']),saved['implementation'],int(saved['ranks'])))
        for key in ['median_seconds','min_seconds','max_seconds','speedup_vs_serial','efficiency_vs_serial']:
            require(math.isclose(float(saved[key]),row[key],rel_tol=1e-12,abs_tol=1e-15), f'Summary mismatch: {key}')
    max_error=0.0; grid_pairs=0
    for check in validation['checks']:
        if 'grids' not in check: continue
        paths=[root/'validation/grids'/Path(path).name for path in check['grids']]
        grids=[read_grid(path) for path in paths]
        n=check['n']
        for grid in grids:
            require(len(grid)==n+2 and all(len(row)==n+2 for row in grid), 'Wrong grid shape')
            require(all(grid[0][j]==grid[-1][j]==grid[j][0]==grid[j][-1]==0 for j in range(n+2)), 'Nonzero physical boundary')
        differences=[abs(x-y) for row1,row2 in zip(*grids) for x,y in zip(row1,row2)]
        require(all(abs(x-y)<=validation['atol']+validation['rtol']*abs(x) for row1,row2 in zip(*grids) for x,y in zip(row1,row2)), 'Transferred grids disagree')
        require(max(differences)==check['max_absolute_error'], 'Recorded grid difference is incorrect')
        max_error=max(max_error,max(differences)); grid_pairs+=1
    for row in records:
        execution=row['execution']
        require(execution['returncode']==0, 'Benchmark command failed')
        require(len(execution['stdout'].strip().splitlines())==1, 'Non-root/extra stdout')
        require(json.loads(execution['stdout'])==row['metrics'], 'Metric disagrees with raw stdout')
        bindings=re.findall(r'MCW rank (\d+) bound to socket (\d+)\[core (\d+)\[hwt (\d+)\]\]',execution['stderr'])
        require(len(bindings)==row['ranks'], 'Missing binding evidence')
        require({int(b[0]) for b in bindings}==set(range(row['ranks'])), 'Wrong rank bindings')
        require(len({b[1:] for b in bindings})==row['ranks'], 'Overlapping bindings')
        require('warning' not in execution['stderr'].lower() and 'error' not in execution['stderr'].lower(), 'Launcher warning/error')
    diagnostics={}
    for n in settings['n']:
        rows=[r['metrics'] for r in records if r['n']==n]
        diagnostics[str(n)]={key:dict(min=min(r[key] for r in rows),max=max(r[key] for r in rows))
                             for key in ['residual_linf','error_linf']}
        require(all(d['min']==d['max'] for d in diagnostics[str(n)].values()), 'Benchmark implementations differ in diagnostics')
    return dict(passed=True,job_id=metadata['allocation']['job_id'],node=metadata['allocation']['hostname'],
        validation_checks=len(validation['checks']),grid_pairs=grid_pairs,max_absolute_grid_error=max_error,
        refinement=validation['refinement'],measurement_records=len(records),configurations=len(summary),
        hashes_match=True,raw_summaries_match=True,distinct_core_bindings_verified=True,
        benchmark_diagnostics=diagnostics,
        source_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [root/'benchmark/raw.jsonl',root/'benchmark/metadata.json',root/'benchmark/summary.csv',validation_path]})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('result_dir',type=Path); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=audit(a.result_dir)
    with a.output.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
