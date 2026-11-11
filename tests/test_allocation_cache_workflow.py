#!/usr/bin/env python3
"""Local infrastructure fixtures, not Vanda numerical or performance evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import validate_distributed
from pbs_allocation import inspect_allocation,save_allocation_snapshot,snapshot_environment,SNAPSHOT_ENV,SNAPSHOT_SHA_ENV


class CacheWorkflowTests(unittest.TestCase):
    @contextlib.contextmanager
    def context(self,root):
        host=socket.gethostname()
        nodefile=root/'nodes'
        nodefile.write_text(host+'\n')
        status=f'Job Id: fixture.server\n    job_state = R\n    Resource_List.ncpus = 8\n    exec_host = {host}/0*8\n'
        with patch.dict(os.environ,{'PBS_JOBID':'fixture.server','PBS_NODEFILE':str(nodefile),
                                   SNAPSHOT_ENV:'',SNAPSHOT_SHA_ENV:''}):
            yield status

    def test_standalone_driver_queries_once_and_passes_cache_to_every_case(self):
        self.check_driver_cache(inherited=False)

    def test_job_driver_reuses_startup_cache_without_scheduler_queries(self):
        self.check_driver_cache(inherited=True)

    def check_driver_cache(self,inherited):
        # Simulate the entire driver matrix, then verify each child's allocation
        # check would use the cache. No solver results or measurements are made.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            solver=root/'not-an-executable'
            solver.write_text('Infrastructure fixture only\n')
            out=root/'validation'
            argv=['validate_distributed.py','--serial',str(solver),'--mpi',str(solver),
                  '--hybrid',str(solver),'--output',str(out)]
            calls=[]
            with self.context(root) as status:
                def run(cmd,**kwargs):
                    calls.append(cmd)
                    if cmd[0]=='qstat':
                        return subprocess.CompletedProcess(cmd,0,status,'')
                    env=kwargs['env']
                    self.assertTrue(Path(env[SNAPSHOT_ENV]).is_file())
                    self.assertEqual(len(env[SNAPSHOT_SHA_ENV]),64)
                    with patch.dict(os.environ,env):
                        self.assertEqual(inspect_allocation(1)['resources']['Resource_List.ncpus'],'8')
                    # The driver expects comparisons to succeed and invalid CLI
                    # launches to fail. Actual comparisons are tested separately.
                    return subprocess.CompletedProcess(cmd,0 if cmd[0]==sys.executable else 2,'','')
                with patch.object(sys,'argv',argv), \
                     patch('pbs_allocation._live_cpu_limits',return_value=(list(range(8)),8)), \
                     patch('pbs_allocation.subprocess.run',side_effect=run), \
                     contextlib.redirect_stdout(io.StringIO()):
                    if inherited:
                        allocation=inspect_allocation(8)
                        cache=root/'job-allocation.json'
                        digest=save_allocation_snapshot(cache,allocation)
                        with patch.dict(os.environ,snapshot_environment(cache,digest)):
                            validate_distributed.main()
                    else:
                        cache=out/'allocation-snapshot.json'
                        validate_distributed.main()
            self.assertEqual(sum(cmd[0]=='qstat' for cmd in calls),1)
            report=json.loads((out/'validation.json').read_text())
            self.assertTrue(report['passed'])
            self.assertEqual(len(report['checks']),494)
            self.assertEqual(len(calls),495)
            self.assertEqual(report['allocation_snapshot']['path'],str(cache.resolve()))
            self.assertEqual((out/'allocation-snapshot.json').exists(),not inherited)

    def test_real_children_and_discovery_use_cache_with_scheduler_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.context(root) as status, \
                 patch('pbs_allocation.subprocess.run',return_value=subprocess.CompletedProcess([],0,status,'')):
                allocation=inspect_allocation(1)
                cache=root/'allocation.json'
                digest=save_allocation_snapshot(cache,allocation)
                original=cache.read_bytes()
                env=snapshot_environment(cache,digest)
            # Only the scheduler response is simulated. Children recheck their
            # real hostname, nodefile and OS affinity in fresh Python processes.
            marker=root/'qstat-called'
            bindir=root/'bin';bindir.mkdir()
            qstat=bindir/'qstat'
            qstat.write_text(f'#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\nraise SystemExit(99)\n')
            qstat.chmod(0o755)
            env['PATH']=str(bindir)+os.pathsep+env['PATH']
            # A one-cell fixture exercises the real grid-comparison code without
            # requiring a compiler/MPI installation or creating benchmark data.
            solver=root/'one-cell-fixture'
            solver.write_text(f'''#!{sys.executable}
import csv,json,math,sys
from pathlib import Path
center=math.pi**2/8
path=Path(sys.argv[sys.argv.index('--output')+1])
with path.open('x') as stream:
    csv.writer(stream).writerows([[0,0,0],[0,center,0],[0,0,0]])
print(json.dumps(dict(N=1,mpi_ranks=1,omp_threads=1,implementation='openmp',
    iterations_completed=1,converged=None,max_update=None,
    residual_linf=abs(2*math.pi**2-16*center),error_linf=abs(center-1))))
''')
            solver.chmod(0o755)
            cmd=[sys.executable,str(ROOT/'tests/compare_solvers.py'),'--reference',str(solver),
                 '--candidate',str(solver),'--n','1','--threads','1','--mode','fixed','--iterations','1']
            compared=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(compared.returncode,0,compared.stderr)
            self.assertIn('PASS fixed',compared.stdout)
            rejected=subprocess.run(cmd+['--launcher-json','["must-not-launch"]','--ranks','3','--threads','4'],
                                    env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(rejected.returncode,2,rejected.stderr)
            self.assertIn('exceeds the actual PBS allocation',rejected.stderr)
            discovered=subprocess.run(['bash','-c','source "$1" "$2"','discovery-fixture',
                str(ROOT/'scripts/discover_environment.sh'),str(root/'inventory')],
                env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(discovered.returncode,0,discovered.stderr)
            self.assertEqual((root/'inventory/scheduler.txt').read_text().strip(),'pbs')
            self.assertFalse(marker.exists(),'cached workflow invoked qstat')
            self.assertEqual(cache.read_bytes(),original)


if __name__=='__main__':
    unittest.main(verbosity=2)
