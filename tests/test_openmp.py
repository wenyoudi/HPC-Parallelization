#!/usr/bin/env python3
"""Independent scalar oracle and sine-eigenmode checks; no production serial solver."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOLVER = None


def scalar(n, k, asymmetric=False):
    w = n + 2
    h = 1 / (n + 1)
    old = [[0.0] * w for _ in range(w)]
    coefficient = (5 if asymmetric else 2) * math.pi**2
    f = [[coefficient * math.sin(math.pi * j * h) *
          math.sin((2 if asymmetric else 1) * math.pi * i * h)
          for j in range(w)] for i in range(w)]
    for _ in range(k):
        new = [[0.0] * w for _ in range(w)]
        for i in range(1, n + 1):
            for j in range(1, n + 1):
                new[i][j] = (old[i-1][j] + old[i+1][j] + old[i][j-1] +
                             old[i][j+1] + h*h*f[i][j]) / 4
        old = new
    return old


def run(args, threads=1, expected=0):
    env = dict(os.environ, OMP_NUM_THREADS=str(threads), OMP_DYNAMIC="FALSE")
    p = subprocess.run([str(SOLVER), *map(str, args)], env=env, capture_output=True,
                       text=True, timeout=90)
    if p.returncode != expected:
        raise AssertionError(f"exit {p.returncode}, expected {expected}: {p.stderr}")
    return p


class SolverTests(unittest.TestCase):
    def grid_run(self, n, k, t=1, problem="symmetric"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "u.csv"
            p = run(["--n", n, "--mode", "fixed", "--iterations", k,
                     "--output", path, "--problem", problem], t)
            data = json.loads(p.stdout)
            with path.open() as stream:
                grid = [list(map(float, r)) for r in csv.reader(stream)]
        self.assertEqual(data["iterations_completed"], k)
        self.assertEqual(data["omp_threads"], t)
        self.assertIsNone(data["converged"])
        self.assertIsNone(data["max_update"])
        self.assertEqual(len(grid), n + 2)
        self.assertTrue(all(len(r) == n + 2 for r in grid))
        self.assertTrue(all(x == 0.0 for x in grid[0] + grid[-1]))
        self.assertTrue(all(r[0] == r[-1] == 0.0 for r in grid))
        return data, grid

    def assert_grid(self, got, expected):
        for a, b in zip(got, expected):
            for x, y in zip(a, b):
                self.assertTrue(math.isclose(x, y, abs_tol=1e-10, rel_tol=1e-8), (x, y))

    def test_initialization(self):
        _, grid = self.grid_run(7, 0, 2)
        self.assertTrue(all(x == 0 for row in grid for x in row))

    def test_manual_one_point(self):
        data, grid = self.grid_run(1, 1, 4)
        self.assertAlmostEqual(grid[1][1], math.pi**2 / 8, places=14)
        self.assertAlmostEqual(data["residual_linf"], 0.0, places=12)

    def test_scalar_equivalence(self):
        for n, k in [(2, 1), (7, 2), (10, 17), (11, 18)]:
            ref = scalar(n, k)
            for t in [1, 2, 4, 8]:
                with self.subTest(n=n, k=k, threads=t):
                    _, grid = self.grid_run(n, k, t)
                    self.assert_grid(grid, ref)

    def test_asymmetric_coordinates(self):
        ref = scalar(10, 19, asymmetric=True)
        self.assertGreater(ref[2][3], 0)
        self.assertLess(ref[9][3], 0)
        self.assertNotAlmostEqual(ref[2][3], ref[3][2])
        for t in [1, 2, 4, 8]:
            _, grid = self.grid_run(10, 19, t, "asymmetric")
            self.assert_grid(grid, ref)

    def test_fixed_eigenmode(self):
        for problem in ["symmetric", "asymmetric"]:
            n, k = 13, 53
            _, grid = self.grid_run(n, k, 4, problem)
            h = 1/(n+1)
            ky = 2 if problem == "asymmetric" else 1
            rho = (math.cos(math.pi*h) + math.cos(ky*math.pi*h))/2
            amp = (1+ky*ky)*math.pi**2*h*h/4 * (1-rho**k)/(1-rho)
            for i in range(1, n+1):
                for j in range(1, n+1):
                    expected = amp * math.sin(math.pi*j*h) * math.sin(ky*math.pi*i*h)
                    self.assertAlmostEqual(grid[i][j], expected, places=13)

    def test_metrics_independently(self):
        for problem in ["symmetric", "asymmetric"]:
            n = 10
            d, u = self.grid_run(n, 31, 2, problem)
            h = 1/(n+1)
            ky = 2 if problem == "asymmetric" else 1
            residual, error = 0, 0
            for i in range(1, n+1):
                for j in range(1, n+1):
                    exact = math.sin(math.pi*j*h)*math.sin(ky*math.pi*i*h)
                    f = (1+ky*ky)*math.pi**2*exact
                    ahu = (4*u[i][j]-u[i-1][j]-u[i+1][j]-u[i][j-1]-u[i][j+1])/(h*h)
                    residual = max(residual, abs(f-ahu))
                    error = max(error, abs(u[i][j]-exact))
            self.assertAlmostEqual(d["residual_linf"], residual, places=11)
            self.assertAlmostEqual(d["error_linf"], error, places=13)

    def test_convergence_and_global_stop_decision(self):
        counts = []
        for t in [1, 2, 4, 8]:
            d = json.loads(run(["--n", 32, "--mode", "converge", "--tol", "1e-8"], t).stdout)
            self.assertTrue(d["converged"])
            self.assertLessEqual(d["max_update"], 1e-8)
            counts.append(d["iterations_completed"])
        self.assertEqual(len(set(counts)), 1)
        n = 32
        rho = math.cos(math.pi/(n+1))
        initial = math.pi**2/(2*(n+1)**2) * math.sin(math.pi*16/(n+1))**2
        expected = math.ceil(math.log(1e-8/initial)/math.log(rho)) + 1
        self.assertEqual(counts[0], expected)

    def test_convergence_sizes(self):
        for n in [32, 64, 128]:
            d = json.loads(run(["--n", n, "--mode", "converge"]).stdout)
            self.assertTrue(d["converged"])
            self.assertLessEqual(d["max_update"], 1e-8)

    def test_nonconvergence(self):
        p = run(["--n", 32, "--mode", "converge", "--max-iters", 2], 4, 2)
        d = json.loads(p.stdout)
        self.assertFalse(d["converged"])
        self.assertEqual(d["iterations_completed"], 2)
        self.assertIn("Non-convergence", p.stderr)

    def test_second_order_accuracy(self):
        errors = []
        for n in [15, 31, 63]:
            d = json.loads(run(["--n", n, "--mode", "converge", "--tol", "1e-13"]).stdout)
            self.assertTrue(d["converged"])
            errors.append(d["error_linf"])
        for a, b in zip(errors, errors[1:]):
            self.assertGreater(a/b, 3.9)
            self.assertLess(a/b, 4.1)

    def test_invalid_cli(self):
        cases = [["--n", x] for x in ["0", "-1", "abc", "2.5", "2147483647", "999999999999"]]
        cases += [["--tol", x] for x in ["0", "-1", "nan", "inf", "1x"]]
        cases += [["--mode", "other"], ["--iterations", "-1"], ["--max-iters", "0"],
                  ["--output", ""], ["--wat", "1"], ["--n"], ["--n", "2", "--n", "3"],
                  ["--problem", "other"]]
        for args in cases:
            with self.subTest(args=args):
                p = run(args, expected=1)
                self.assertEqual(p.stdout, "")
                self.assertIn("Error:", p.stderr)

    def test_output_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(["--n", 1, "--mode", "fixed", "--iterations", 0,
                 "--output", Path(tmp)/"missing"/"u.csv"], expected=1)

    def test_help(self):
        self.assertIn("Usage:", run(["--help"]).stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", default="build/openmp")
    args, rest = parser.parse_known_args()
    SOLVER = Path(args.solver).resolve()
    unittest.main(argv=[__file__, *rest], verbosity=2)
