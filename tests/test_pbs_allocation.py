#!/usr/bin/env python3
"""Local scheduler fixtures only: retries, cache identity and unchanged CPU guards."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from pbs_allocation import inspect_allocation,save_allocation_snapshot,snapshot_environment,SNAPSHOT_ENV,SNAPSHOT_SHA_ENV
from mpi_launcher import cpu_limit,launcher

STATUS='''Job Id: fixture.server
    job_state = R
    Resource_List.ncpus = 8
    Resource_List.nodect = 1
    Resource_List.select = 1:ncpus=8:mpiprocs=1:ompthreads=8:mem=4gb
    exec_host = compute01/0*8
    Variable_List = PRIVATE_TEST_VALUE=not-a-real-secret
'''


def response(status=STATUS,returncode=0):
    return subprocess.CompletedProcess([],returncode,status,'')


class AllocationTests(unittest.TestCase):
    @contextlib.contextmanager
    def context(self,nodes='compute01\n',cpus=8,physical=8):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            nodefile=root/'nodes'
            nodefile.write_text(nodes)
            with patch.dict(os.environ,{'PBS_JOBID':'fixture.server','PBS_NODEFILE':str(nodefile),
                            SNAPSHOT_ENV:'',SNAPSHOT_SHA_ENV:''}), \
                 patch('pbs_allocation.socket.gethostname',return_value='compute01.example'), \
                 patch('pbs_allocation.socket.getfqdn',return_value='compute01.example'), \
                 patch('pbs_allocation._live_cpu_limits',return_value=(list(range(cpus)),physical)) as live:
                yield root,nodefile,live

    def fixture(self,nodes,status=STATUS,cpus=8):
        with self.context(nodes,cpus,cpus),patch('pbs_allocation.subprocess.run',return_value=response(status)):
            return inspect_allocation(8)

    def test_verified_resources_exclude_private_environment(self):
        result=self.fixture('compute01\n')
        self.assertEqual(result['resources']['Resource_List.ncpus'],'8')
        self.assertNotIn('PRIVATE_TEST_VALUE',str(result))

    def test_login_or_multiple_nodes_rejected(self):
        for nodes in ['login01\n','compute01\ncompute02\n']:
            with self.assertRaises(RuntimeError): self.fixture(nodes)

    def test_insufficient_or_inactive_allocation_rejected(self):
        for status,cpus in [(STATUS.replace('ncpus = 8','ncpus = 4'),8),
                            (STATUS.replace('job_state = R','job_state = Q'),8),(STATUS,4)]:
            with self.assertRaises(RuntimeError): self.fixture('compute01\n',status,cpus)

    def test_transient_timeout_and_nonzero_status_retry_only_initial_query(self):
        with self.context(),patch('pbs_allocation.time.sleep') as sleep, \
             patch('pbs_allocation.subprocess.run',side_effect=[subprocess.TimeoutExpired('qstat',15),response(returncode=1),response()]) as query, \
             contextlib.redirect_stderr(io.StringIO()):
            result=inspect_allocation(8)
            self.assertEqual(query.call_count,3)
            self.assertEqual([call.args[0] for call in sleep.call_args_list],[1,2])
            self.assertEqual(result['scheduler_query_attempts'],3)

    def test_persistent_timeout_fails_after_three_attempts(self):
        with self.context(),patch('pbs_allocation.time.sleep'), \
             patch('pbs_allocation.subprocess.run',side_effect=subprocess.TimeoutExpired('qstat',15)) as query, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'after 3 attempts'):
                inspect_allocation(8)
            self.assertEqual(query.call_count,3)

    def test_inactive_response_does_not_retry_or_invent_resources(self):
        with self.context(),patch('pbs_allocation.subprocess.run',return_value=response(STATUS.replace('job_state = R','job_state = Q'))) as query:
            with self.assertRaises(RuntimeError): inspect_allocation(8)
            self.assertEqual(query.call_count,1)

    def test_cache_reused_without_scheduler_and_actual_not_requested_cpus(self):
        with self.context() as (root,_,_),patch('pbs_allocation.subprocess.run',return_value=response()) as query:
            original=inspect_allocation(1) # Observed allocation is 8, despite requesting a minimum of 1.
            path=root/'allocation.json'
            digest=save_allocation_snapshot(path,original)
            before=path.read_bytes()
            with patch.dict(os.environ,snapshot_environment(path,digest)), \
                 patch('pbs_allocation.subprocess.run',side_effect=AssertionError('cached child called qstat')):
                for required in [1,4,8]:
                    result=inspect_allocation(required)
                    self.assertEqual(cpu_limit(result),8)
                    self.assertEqual(result['resources']['Resource_List.ncpus'],'8')
            self.assertEqual(query.call_count,1)
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(FileExistsError): save_allocation_snapshot(path,original)

    def test_cache_rechecks_live_affinity_and_rank_thread_limit(self):
        with self.context() as (root,_,live),patch('pbs_allocation.subprocess.run',return_value=response()):
            original=inspect_allocation(8)
            path=root/'allocation.json';digest=save_allocation_snapshot(path,original)
            with patch.dict(os.environ,snapshot_environment(path,digest)), \
                 patch('pbs_allocation.subprocess.run',side_effect=AssertionError('unexpected qstat')):
                live.return_value=(list(range(4)),4)
                result=inspect_allocation(1)
                self.assertEqual(cpu_limit(result),4)
                with self.assertRaises(ValueError): launcher(result,3,2)
                with self.assertRaises(RuntimeError): inspect_allocation(8)
                live.return_value=(list(range(16)),8)
                with self.assertRaisesRegex(RuntimeError,'affinity'): inspect_allocation(1)
                live.return_value=(list(range(8)),None)
                with self.assertRaisesRegex(RuntimeError,'physical-core'): inspect_allocation(1)

    def test_cache_rejects_other_job_nodefile_host_and_bad_fields(self):
        with self.context() as (root,nodefile,_),patch('pbs_allocation.subprocess.run',return_value=response()):
            original=inspect_allocation(8)
            path=root/'allocation.json'
            for mutation in ['job','host','nodefile','schema','cpu','physical','state']:
                data=json.loads(json.dumps(original))
                if mutation=='job': data['job_id']='other.server'
                elif mutation=='host': data['hostname']='other-host'
                elif mutation=='nodefile': data['nodefile_sha256']='incorrect'
                elif mutation=='schema': data.pop('verified_via')
                elif mutation=='cpu': data['allowed_os_cpus']=['invalid']
                elif mutation=='physical': data['visible_physical_cores']=0
                else: data['resources']['job_state']='Q'
                path.write_text(json.dumps(data))
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                with self.subTest(mutation=mutation),patch.dict(os.environ,snapshot_environment(path,digest)), \
                     patch('pbs_allocation.subprocess.run',side_effect=AssertionError('invalid cache queried scheduler')):
                    with self.assertRaises(RuntimeError): inspect_allocation(1)
            path.write_text(json.dumps(original));digest=hashlib.sha256(path.read_bytes()).hexdigest()
            nodefile.write_text('compute01\ncompute01\n')
            with patch.dict(os.environ,snapshot_environment(path,digest)):
                with self.assertRaisesRegex(RuntimeError,'nodefile'): inspect_allocation(1)

    def test_cache_checksum_and_missing_hash_fail_without_fallback(self):
        with self.context() as (root,_,_),patch('pbs_allocation.subprocess.run',return_value=response()):
            data=inspect_allocation(8)
            path=root/'allocation.json';digest=save_allocation_snapshot(path,data)
            for value in ['', '0'*64]:
                with patch.dict(os.environ,snapshot_environment(path,value)), \
                     patch('pbs_allocation.subprocess.run',side_effect=AssertionError('unexpected qstat')):
                    with self.assertRaisesRegex(RuntimeError,'checksum'): inspect_allocation(1)
            with patch.dict(os.environ,snapshot_environment(path,digest)):
                path.write_bytes(path.read_bytes()+b' ')
                with self.assertRaisesRegex(RuntimeError,'checksum'): inspect_allocation(1)

    def test_refresh_ignores_inherited_cache_for_new_job(self):
        with self.context(),patch.dict(os.environ,{SNAPSHOT_ENV:'/missing/old-job.json',SNAPSHOT_SHA_ENV:'bad'}), \
             patch('pbs_allocation.subprocess.run',return_value=response()) as query:
            self.assertEqual(inspect_allocation(8,force_refresh=True)['resources']['Resource_List.ncpus'],'8')
            self.assertEqual(query.call_count,1)


if __name__=='__main__':
    unittest.main(verbosity=2)
