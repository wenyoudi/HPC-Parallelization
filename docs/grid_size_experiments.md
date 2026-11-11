# Grid-size experiments

## Scope and ownership

This stage analyses serial runtime as grid size increases and spatial error as the
grid is refined. MPI and hybrid scaling remain with their implementation owners.
No local timing is presented as an HPC measurement.

## Fixed-work runtime: existing Vanda evidence

Reuse the serial measurements from hybrid job 1541184 on CN-140, supplied by the
hybrid contributor. The source archive is retained under results/validation/stage2.
There are three measured repeats per N=128/256/512/1024, symmetric forcing and
K=1000. The serial process was bound to one core within an eight-core allocation.
These are existing team measurements, not a new run by the reviewer. The serial
core source matches the reference used for hybrid integration.

The analysis preserves the 12 selected records and archive hash, computes medians
and min/max ranges, and plots an N-squared reference anchored at the smallest N.
It does not imply that fixed K converges, nor that runtime follows exactly N-squared.
Do not combine these timings with earlier GN-A40-075 runs for speedup calculations.

```bash
python3 scripts/analyze_grid_size.py \
  --runtime-archive results/validation/stage2/hybrid-vanda-results-1541184.tar.gz \
  --output-dir results/experiments/grid-size-runtime
```

Plotting requires matplotlib (`python3 -m pip install matplotlib` in your chosen
local plotting environment). Use a fresh output directory; existing figures are
not overwritten. Figures are generated as PNG and PDF.

### Recorded runtime result

| N | Median solver time (s) |
| --- | --- |
| 128 | 0.022219 |
| 256 | 0.090415 |
| 512 | 0.404777 |
| 1024 | 1.516331 |

At fixed K=1000, doubling N increases runtime by approximately 4.07, 4.48 and
3.75 times. This broadly follows the fourfold increase in interior points. Three
repeats provide only a small sample; plotted bars show min/max, not confidence
intervals. The N-squared curve is a reference, not a fitted complexity estimate.

## Spatial refinement: submit to Vanda

The experiment uses N=15/31/63/127 (h halves at each step), both manufactured
solutions, tol=1e-13 and max_iters=500000. Full grids, stdout/stderr, metrics,
commands, executable hash and a summary are retained. No full validation suite
is repeated by this job. Each job gets a separate build and output directory.

```bash
cd ~/HPC-Parallelization
qsub jobs/grid_refinement_vanda.pbs
```

The solver's update tolerance is not accepted alone as proof of accuracy. For
these sine forcings, the exact solution of the discrete stencil is known:

```text
lambda_h = 4/h^2 * [sin(pi*h/2)^2 + sin(m*pi*h/2)^2]
u_discrete = [(1+m^2)*pi^2/lambda_h] * sin(pi*x)*sin(m*pi*y)
m = 1 (symmetric) or 2 (asymmetric)
```

The collector separately computes error against the continuous solution, error
against this discrete solution (iteration error), and spatial discretization
error. It requires iteration error <=1% of discretization error before accepting
a result. Solver-reported continuum error is checked independently. Exhausting
the iteration limit fails the experiment and preserves diagnostics; failed runs
are not plotted as successful refinement data. Observed order uses actual h ratios.
These checks specifically apply to the agreed manufactured problems.

Runtime in the refinement records is diagnostic; it is not a repeated fixed-work
benchmark. The serial accuracy computation can be performed in one allocated CPU
without MPI or OpenMP. Formal numerical experiments run on a Vanda compute node.

## Retrieve and plot

After a successful job, results are under
`results/hpc/grid-refinement-JOB_ID/`. Replace JOB_ID with the full PBS ID.
`measurements/status.json` must report passed=true. Download `results.tar.gz`
from that directory to your local machine. It includes measurements and allocation/
source records, excluding the build directory. Keep the PBS log as supporting evidence.

Extract into a new directory, then plot the measurements:

```bash
python3 scripts/analyze_grid_size.py \
  --refinement-dir PATH_TO_EXTRACTED_RESULTS/measurements \
  --output-dir results/experiments/grid-size-accuracy
```

Archive the returned Vanda results and resulting figures before writing the final
accuracy discussion. The completed Vanda refinement evidence and figures are archived in
`results/experiments/grid-size-accuracy/`.

## AI assistance

AI assisted with experiment scripts, evidence analysis and documentation. A small
local smoke run checks collection logic only; it is not an HPC result. Formal
accuracy conclusions must use returned Vanda outputs and independently checked errors.

## Completed Vanda refinement results

Job 1543242.stdct-mgmt-02 ran on CN-148 with one CPU and 6 GB allocated memory.
All eight cases converged. The original result archive, its checksum, independent
review results, summary CSV and PNG/PDF figure are retained. Git metadata was not
available in the source-only Vanda directory; the archive contains source and
binary hashes instead. The allocation file is an in-run scheduler snapshot, not
an exit-status receipt; measurements/status.json records experimental completion.

| N | Symmetric maximum error | Asymmetric maximum error |
| --- | --- | --- |
| 15 | 3.218964e-3 | 1.098931e-2 |
| 31 | 8.035777e-4 | 2.734955e-3 |
| 63 | 2.008217e-4 | 6.829684e-4 |
| 127 | 5.020058e-5 | 1.706939e-4 |

Halving grid spacing reduces error by approximately fourfold. Observed orders are
2.00209, 2.00052 and 2.00014 for the symmetric problem, and 2.00651, 2.00163 and
2.00041 for the asymmetric problem. This supports second-order spatial convergence
for these manufactured solutions over the tested grids.

The largest iteration-error/discretization-error ratio is 6.61e-6 (0.000661%),
well below the 1% acceptance limit. Thus the observed refinement trend is dominated
by spatial discretization rather than an insufficiently converged iteration.
The finest symmetric grid required 72,459 iterations and the asymmetric grid
30,202, demonstrating why fixed K=1000 should not be interpreted as a converged
accuracy experiment. Update tolerance, residual and continuum error remain distinct.

All eight exported grids were independently checked for shape, finite values,
zero boundaries, continuum error, discrete-solution error and five-point residual.
These checks used existing outputs and did not rerun the solver. The returned
accuracy timings are not mixed with CN-140 fixed-work timings or used for scaling.

The planned serial grid-size work is complete: fixed-work runtime analysis uses
team-provided Vanda measurements; spatial accuracy uses job 1543242. MPI/hybrid
performance interpretation and the final shared report remain separate tasks.
