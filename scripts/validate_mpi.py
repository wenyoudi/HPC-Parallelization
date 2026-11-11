#!/usr/bin/env python3
"""Full-grid and metric validation; no third-party Python packages required."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import tempfile
from compare_solutions import read_grid
from mpi_workflow import invoke, launch_context, sha

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', required=True, type=Path)
    p.add_argument('--mpi', required=True, type=Path)
    p.add_argument('--ranks', nargs='+', type=int, default=[1, 2, 3, 4])
    p.add_argument('--launcher-json', help='Explicit local launcher, e.g. ["mpiexec","-n","{ranks}"]')
    p.add_argument('--output-dir', required=True, type=Path)
    a = p.parse_args()
    if not __debug__: p.error('Validation requires assertions enabled; unset PYTHONOPTIMIZE and omit -O')
    if not a.ranks or min(a.ranks) < 1: p.error('Positive ranks required')
    if len(set(a.ranks)) != len(a.ranks): p.error('Rank counts must be unique')
    if max(a.ranks) > 15: p.error('This correctness suite supports ranks up to 15; use larger grids for scaling separately')
    serial, mpi = str(a.serial.resolve()), str(a.mpi.resolve())
    launch, context = launch_context(a.launcher_json, max(a.ranks))
    a.output_dir.mkdir(parents=True, exist_ok=False)
    grid_dir = a.output_dir/'grids'
    grid_dir.mkdir()
    report = dict(passed=False, context=context, binary_sha256=dict(serial=sha(serial), mpi=sha(mpi)),
                  ranks=a.ranks, checks=[], atol=1e-10, rtol=1e-8)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for ranks in a.ranks:
                for n in sorted({10, ranks} | ({2, 32} if ranks == 1 else {32} if ranks == 4 else set())):
                    for problem in ['symmetric', 'asymmetric']:
                        modes = [('fixed', 1), ('fixed', 2), ('fixed', 31), ('converge', 0), ('limit', 0)]
                        if n == 10: modes.append(('fixed', 100))
                        if n == 32: modes.append(('fixed', 500))
                        for mode, amount in modes:
                            common = ['--n', str(n), '--problem', problem]
                            expected = 3 if mode == 'limit' else 0
                            if mode == 'fixed': common += ['--mode', 'fixed', '--iterations', str(amount)]
                            else:
                                common += ['--mode', 'converge', '--tol', '1e-30' if mode == 'limit' else '1e-11']
                                if mode == 'limit': common += ['--max-iters', '1']
                            case = f'n{n}-r{ranks}-{problem}-{mode}-{amount}'
                            paths = [grid_dir/f'{case}-serial.csv', grid_dir/f'{case}-mpi.csv']
                            ref, ref_log = invoke([serial]+common+['--output', str(paths[0])], expected)
                            got, mpi_log = invoke(launch(ranks)+[mpi]+common+['--output', str(paths[1])], expected)
                            entry = dict(case=case, passed=False, n=n, ranks=ranks, problem=problem,
                                mode=mode, serial_metrics=ref, mpi_metrics=got,
                                serial=ref_log, mpi=mpi_log, grids=[str(path) for path in paths])
                            report['checks'].append(entry)
                            grids = [read_grid(path) for path in paths]
                            for grid in grids:
                                assert len(grid) == n+2 and all(len(row) == n+2 for row in grid), case
                                assert all(grid[0][j] == grid[-1][j] == grid[j][0] == grid[j][-1] == 0 for j in range(n+2)), case
                            errors = [abs(x-y) for row1,row2 in zip(*grids) for x,y in zip(row1,row2)]
                            assert all(abs(x-y) <= 1e-10+1e-8*abs(x) for row1,row2 in zip(*grids) for x,y in zip(row1,row2)), case
                            for key in ['schema_version', 'n', 'problem', 'mode', 'iterations_completed', 'converged', 'tol']:
                                assert ref[key] == got[key], (case, key)
                            for key in ['max_update', 'residual_linf', 'error_linf']:
                                assert (ref[key] is None and got[key] is None) or math.isclose(ref[key], got[key], rel_tol=1e-8, abs_tol=1e-10), (case,key)
                            assert got['mpi_ranks'] == ranks and got['omp_threads'] == 1 and got['implementation'] == 'mpi', case
                            entry.update(passed=True, max_absolute_error=max(errors))
                # Errors must terminate collectively rather than hang; output failures
                # use a root-to-all status broadcast. Launchers may remap nonzero codes.
                existing = tmp/f'existing-{ranks}.csv'
                existing.write_text('keep me')
                for args in [['--n', str(max(1,ranks-1))] if ranks>1 else ['--n','0'],
                             ['--mode','fixed','--tol','1e-8'],
                             ['--n',str(max(2,ranks)),'--iterations','1','--output',str(existing)]]:
                    cmd = launch(ranks)+[mpi]+args
                    run = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    assert run.returncode != 0 and not run.stdout.strip(), (cmd, run.stdout, run.stderr)
                    report['checks'].append(dict(case='invalid-input', passed=True, command=cmd, returncode=run.returncode, stderr=run.stderr))
                assert existing.read_text() == 'keep me'
            # Independent continuum refinement check on an actual distributed
            # solve. Tight convergence makes iteration error negligible.
            refinement_ranks = max(a.ranks)
            if refinement_ranks <= 15:
                errors = []
                for n in [15, 31, 63]:
                    cmd = launch(refinement_ranks)+[mpi, '--n', str(n), '--problem', 'asymmetric',
                        '--mode', 'converge', '--tol', '1e-13', '--max-iters', '100000']
                    metrics, log = invoke(cmd)
                    assert metrics['converged'] and metrics['residual_linf'] < 2e-8, metrics
                    errors.append(metrics['error_linf'])
                    report['checks'].append(dict(case='mpi-refinement', passed=True, n=n,
                        ranks=refinement_ranks, mpi_metrics=metrics, mpi=log))
                ratios = [a/b for a,b in zip(errors, errors[1:])]
                assert all(3.8 < ratio < 4.2 for ratio in ratios), ratios
                report['refinement'] = dict(ranks=refinement_ranks, n=[15,31,63], errors=errors, ratios=ratios)
            else:
                raise ValueError('Refinement grids require a validation rank list with maximum <=15')
        report['passed'] = True
    except Exception as e:
        report['error'] = str(e)
        raise
    finally:
        (a.output_dir/'validation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f"Passed {len(report['checks'])} MPI checks; evidence: {a.output_dir/'validation.json'}")

if __name__ == '__main__': main()
