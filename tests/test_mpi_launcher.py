#!/usr/bin/env python3
"""Local launch-policy fixtures, not Vanda/MPI execution evidence."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from mpi_launcher import cpu_limit, launcher


def allocation(cpus=8, visible=64):
    return dict(resources={"Resource_List.ncpus":str(cpus)},nodes=["GN-A40-074"],
                hostname="GN-A40-074",allowed_os_cpus=list(range(visible)))


class LauncherTests(unittest.TestCase):
    def test_workaround_slots_use_pbs_not_host_size(self):
        cmd=launcher(allocation(4,64),4,1)
        self.assertEqual(cmd[cmd.index("--host")+1],"GN-A40-074:4")
        self.assertEqual(cmd[:7],["mpirun","--mca","plm","rsh","--mca","ras","^tm"])
        self.assertIn("--nooversubscribe",cmd)

    def test_hybrid_budget_and_binding(self):
        self.assertIn("slot:PE=2",launcher(allocation(),4,2))
        self.assertIn("core",launcher(allocation(),4,2))
        for ranks,threads in [(8,2),(3,3),(0,1),(1,0)]:
            with self.assertRaises(ValueError): launcher(allocation(),ranks,threads)

    def test_original_launcher_is_selectable(self):
        cmd=launcher(allocation(),4,1,"pbs","/fixture/pbs-nodes")
        self.assertIn("/fixture/pbs-nodes",cmd)
        self.assertNotIn("^tm",cmd)
        self.assertNotIn("--host",cmd)

    def test_cpuset_physical_and_single_node_limits(self):
        a=allocation(8,4)
        self.assertEqual(cpu_limit(a),4)
        with self.assertRaises(ValueError): launcher(a,4,2)
        a=allocation()
        a["visible_physical_cores"]=4
        with self.assertRaises(ValueError): launcher(a,8)
        a["nodes"].append("other-node")
        with self.assertRaises(ValueError): launcher(a,1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
