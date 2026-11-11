"""Synthetic tooling fixtures only; these are not measured performance data."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_mpi import summarize

def fixture():
    records=[]
    for kind,ranks,times in [('serial',1,[8,10,12]), ('mpi',1,[10,12,14]), ('mpi',2,[4,5,6])]:
        for repeat,t in enumerate(times):
            records.append(dict(n=32,implementation=kind,ranks=ranks,repeat=repeat,
                metrics=dict(n=32,implementation=kind,mpi_ranks=ranks,omp_threads=1,
                    problem='asymmetric',mode='fixed',iterations_completed=100,solve_seconds=t)))
    return records

class AnalysisTests(unittest.TestCase):
    def test_hand_calculated_scaling(self):
        summary,_=summarize(fixture())
        row=next(r for r in summary if r['implementation']=='mpi' and r['ranks']==2)
        self.assertEqual(row['median_seconds'],5)
        self.assertEqual(row['min_seconds'],4)
        self.assertEqual(row['max_seconds'],6)
        self.assertEqual(row['speedup_vs_serial'],2)
        self.assertEqual(row['efficiency_vs_serial'],1)
        self.assertEqual(row['speedup_vs_mpi1'],2.4)

    def test_missing_serial_or_repeats(self):
        rows=fixture()
        for broken in [[],rows[3:],rows[:-1],rows+[copy.deepcopy(rows[-1])]]:
            with self.assertRaises(ValueError): summarize(broken)

    def test_mixed_workloads_and_nonfinite_times(self):
        for key,value in [('iterations_completed',101),('mode','converge'),('solve_seconds',0),
                          ('solve_seconds',float('nan')),('mpi_ranks',9),('omp_threads',2)]:
            rows=fixture(); rows[-1]['metrics'][key]=value
            with self.assertRaises(ValueError): summarize(rows)

    def test_incomplete_grid_sweep(self):
        rows=fixture(); partial=copy.deepcopy(rows[:3])
        for row in partial: row['n']=64; row['metrics']['n']=64
        with self.assertRaises(ValueError): summarize(rows+partial)

if __name__=='__main__': unittest.main()
