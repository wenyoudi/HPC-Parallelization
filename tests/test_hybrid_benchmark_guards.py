#!/usr/bin/env python3
"""Fixture checks: failed/incompatible validation must prevent any benchmark launch."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import benchmark


class ValidationGateTests(unittest.TestCase):
    def test_missing_failed_changed_or_uncovered_validation_stops_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            serial=root/"serial-fixture"
            hybrid=root/"hybrid-fixture"
            serial.write_bytes(b"serial fixture, not executable")
            hybrid.write_bytes(b"hybrid fixture, not executable")
            log=root/"fixture-build.log"
            log.write_text("unit test fixture; no compilation or measurements\n")
            valid=dict(passed=True,site="vanda",launcher_mode="single-node",binary_sha256={
                "serial":hashlib.sha256(serial.read_bytes()).hexdigest(),
                "hybrid":hashlib.sha256(hybrid.read_bytes()).hexdigest()},
                checks=[dict(passed=True,implementation="hybrid",mpi_ranks=4,omp_threads=2)])
            failures=[None,dict(valid,passed=False),dict(valid,site="local"),dict(valid,launcher_mode="pbs"),
                      dict(valid,binary_sha256={}),dict(valid,checks=[dict(passed=True,implementation="hybrid",mpi_ranks=1,omp_threads=8)])]
            for i,report in enumerate(failures):
                argv=["benchmark.py","--kind","hybrid","--site","vanda","--solver",str(hybrid),
                      "--serial",str(serial),"--allocated-cpus","8","--configs","4x2","--sizes","10",
                      "--build-log",str(log),"--output",str(root/f"unused-{i}"),"--launcher-mode","single-node"]
                if report is not None:
                    evidence=root/f"fixture-{i}.json"
                    evidence.write_text(json.dumps(report))
                    argv += ["--validation-evidence",str(evidence)]
                allocation=dict(resources={"Resource_List.ncpus":"8"},nodes=["fixture-node"],
                                hostname="fixture-node",allowed_os_cpus=list(range(8)))
                with patch.object(sys,"argv",argv),patch.object(benchmark,"inspect_allocation",return_value=allocation), \
                     patch.object(benchmark.subprocess,"run",side_effect=AssertionError("unexpected process launch")), \
                     contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as exited:
                    benchmark.main()
                self.assertEqual(exited.exception.code,2)
                self.assertFalse((root/f"unused-{i}").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
