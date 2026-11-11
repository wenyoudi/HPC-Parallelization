#!/usr/bin/env python3
"""Fixture-based allocation guard checks, not evidence of real Vanda jobs."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from pbs_allocation import inspect_allocation

STATUS = """Job Id: fixture.server
    job_state = R
    Resource_List.ncpus = 8
    Resource_List.nodect = 1
    Resource_List.select = 1:ncpus=8:mpiprocs=1:ompthreads=8:mem=4gb
    exec_host = compute01/0*8
    Variable_List = PRIVATE_TEST_VALUE=not-a-real-secret
"""


class AllocationTests(unittest.TestCase):
    def fixture(self, nodes, status=STATUS, cpus=8):
        with tempfile.TemporaryDirectory() as tmp:
            nodefile=Path(tmp)/"nodes"
            nodefile.write_text(nodes)
            with patch.dict(os.environ, PBS_JOBID="fixture.server", PBS_NODEFILE=str(nodefile)), \
                 patch("pbs_allocation.socket.gethostname", return_value="compute01.example"), \
                 patch("pbs_allocation.socket.getfqdn", return_value="compute01.example"), \
                 patch("pbs_allocation.os.sched_getaffinity", return_value=set(range(cpus)), create=True), \
                 patch("pbs_allocation.subprocess.run", return_value=subprocess.CompletedProcess([],0,status,"")):
                return inspect_allocation(8)

    def test_verified_resources_exclude_private_environment(self):
        result=self.fixture("compute01\n")
        self.assertEqual(result["resources"]["Resource_List.ncpus"],"8")
        self.assertNotIn("PRIVATE_TEST_VALUE",str(result))

    def test_login_or_multiple_nodes_rejected(self):
        for nodes in ["login01\n","compute01\ncompute02\n"]:
            with self.assertRaises(RuntimeError): self.fixture(nodes)

    def test_insufficient_or_inactive_allocation_rejected(self):
        for status,cpus in [(STATUS.replace("ncpus = 8","ncpus = 4"),8),
                            (STATUS.replace("job_state = R","job_state = Q"),8),(STATUS,4)]:
            with self.assertRaises(RuntimeError): self.fixture("compute01\n",status,cpus)


if __name__ == "__main__":
    unittest.main(verbosity=2)
