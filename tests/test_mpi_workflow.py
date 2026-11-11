"""Test evidence parsing and rank substitution without simulating an MPI solver."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from mpi_workflow import invoke, launch_context

class WorkflowTests(unittest.TestCase):
    def command(self, values, suffix=''):
        return [sys.executable, '-c', 'print('+repr(json.dumps(values))+')'+suffix]

    def test_launcher_preserves_argument_boundaries(self):
        launch, _ = launch_context('["C:/Program Files/MPI/mpiexec", "-n", "{ranks}"]', 4)
        self.assertEqual(launch(3), ['C:/Program Files/MPI/mpiexec', '-n', '3'])
        for template in ['"mpiexec"', '[]', '["mpiexec"]', '[1,"{ranks}"]']:
            with self.assertRaises(ValueError): launch_context(template, 1)

    def test_rejects_multiple_stdout_records(self):
        with self.assertRaises(ValueError):
            invoke(self.command(dict(solve_seconds=1,residual_linf=0,error_linf=0), '; print("extra")'))

    def test_rejects_nonfinite_and_negative_metrics(self):
        for value in [float('nan'), float('inf'), -1]:
            with self.assertRaises(ValueError):
                invoke(self.command(dict(solve_seconds=value,residual_linf=0,error_linf=0)))

    def test_expected_nonconvergence_exit(self):
        cmd = self.command(dict(solve_seconds=1,residual_linf=0,error_linf=0), '; raise SystemExit(3)')
        metrics, log = invoke(cmd, expected=3)
        self.assertEqual(metrics['solve_seconds'], 1)
        self.assertEqual(log['returncode'], 3)
        with self.assertRaises(RuntimeError): invoke(cmd)

if __name__ == '__main__': unittest.main()
