"""Independent mathematical checks; only tiny grids, no HPC benchmarks."""
import csv
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

EXE = str(Path(sys.argv.pop(1)).resolve())

class SerialTests(unittest.TestCase):
    def run_solver(self, n, k=1, problem="symmetric", extra=None, status=0):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "solution.csv"
            args = [EXE, "--n", str(n), "--problem", problem, "--output", str(target)]
            args += extra if extra is not None else ["--mode", "fixed", "--iterations", str(k)]
            p = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(p.returncode, status, p.stderr)
            self.assertEqual(len(p.stdout.splitlines()), 1)
            metrics = json.loads(p.stdout)
            with target.open() as f:
                grid = [list(map(float, row)) for row in csv.reader(f)]
            self.assertEqual(len(grid), n + 2)
            self.assertTrue(all(len(row) == n + 2 for row in grid))
            for i in range(n + 2):
                self.assertEqual(grid[i][0], 0)
                self.assertEqual(grid[i][-1], 0)
                self.assertEqual(grid[0][i], 0)
                self.assertEqual(grid[-1][i], 0)
            self.assertGreaterEqual(metrics["solve_seconds"], 0)
            return metrics, grid

    def test_fixed_against_discrete_eigenmode(self):
        # Closed form, not a second copy of the Jacobi update loops.
        for problem in ["symmetric", "asymmetric"]:
            for n in [1, 2, 10, 17]:
                for k in [1, 2, 7, 20]:
                    with self.subTest(problem=problem, n=n, k=k):
                        m, u = self.run_solver(n, k, problem)
                        h = 1 / (n + 1)
                        frequency = 2 if problem == "asymmetric" else 1
                        lam = (1 + frequency**2) * math.pi**2
                        lam_h = 4 / h**2 * (math.sin(math.pi*h/2)**2 + math.sin(frequency*math.pi*h/2)**2)
                        rho = 1 - h*h*lam_h/4
                        amplitude = lam / lam_h * (1-rho**k)
                        expected_error = 0
                        expected_residual = 0
                        for i in range(1, n+1):
                            for j in range(1, n+1):
                                exact = math.sin(math.pi*j*h)*math.sin(frequency*math.pi*i*h)
                                self.assertAlmostEqual(u[i][j], amplitude*exact, delta=2e-13)
                                expected_error = max(expected_error, abs((amplitude-1)*exact))
                                expected_residual = max(expected_residual, abs(lam*rho**k*exact))
                        self.assertAlmostEqual(m['error_linf'], expected_error, delta=3e-13)
                        self.assertAlmostEqual(m['residual_linf'], expected_residual, delta=2e-11)
                        self.assertEqual(m['iterations_completed'], k)
                        self.assertIsNone(m['converged'])
                        self.assertIsNone(m['max_update'])

    def test_convergence_and_final_iterate(self):
        m, u = self.run_solver(10, problem='asymmetric', extra=['--mode','converge','--tol','1e-10'])
        self.assertTrue(m['converged'])
        self.assertLessEqual(m['max_update'], 1e-10)
        fixed, uf = self.run_solver(10, m['iterations_completed'], 'asymmetric')
        self.assertEqual(u, uf)
        _, prev = self.run_solver(10, m['iterations_completed']-1, 'asymmetric')
        delta = max(abs(a-b) for ra,rb in zip(u,prev) for a,b in zip(ra,rb))
        self.assertAlmostEqual(delta, m['max_update'], delta=1e-15)

    def test_nonconvergence_is_explicit(self):
        m, _ = self.run_solver(10, extra=['--mode','converge','--tol','1e-15','--max-iters','1'], status=3)
        self.assertFalse(m['converged'])
        self.assertEqual(m['iterations_completed'], 1)

    def test_second_order_error_with_small_iteration_error(self):
        errors=[]
        for n in [15,31,63]:
            m, _ = self.run_solver(n, problem='asymmetric', extra=['--mode','converge','--tol','1e-13'])
            self.assertTrue(m['converged'])
            self.assertLess(m['residual_linf'], 2e-8)
            errors.append(m['error_linf'])
        for a,b in zip(errors,errors[1:]):
            self.assertGreater(a/b,3.8)
            self.assertLess(a/b,4.2)

    def test_bad_arguments(self):
        cases=[['--n','0'],['--n','-1'],['--n','1.5'],['--n','18446744073709551615'],
               ['--mode','bad'],['--problem','bad'],['--n'],['--iterations','0'],
               ['--mode','converge','--tol','nan'],['--mode','converge','--tol','inf'],
               ['--mode','converge','--tol','-1'],['--mode','fixed','--tol','1e-8'],
               ['--mode','converge','--iterations','3'],['--n','3','--n','4']]
        for args in cases:
            with self.subTest(args=args):
                p=subprocess.run([EXE]+args,capture_output=True,text=True)
                self.assertEqual(p.returncode,2)
                self.assertEqual(p.stdout,'')
                self.assertIn('Error:',p.stderr)

    def test_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'existing.csv';target.write_text('keep me')
            p=subprocess.run([EXE,'--n','2','--iterations','1','--output',str(target)],capture_output=True,text=True)
            self.assertEqual(p.returncode,2)
            self.assertEqual(target.read_text(),'keep me')

if __name__ == '__main__':
    unittest.main()
