#!/usr/bin/env python3
"""Safety of experiment provenance and resource checks; uses tiny real solves."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


class PipelineTests(unittest.TestCase):
    def command(self, args, expected=0):
        result = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def benchmark(self, output, *extra, expected=0):
        return self.command(["scripts/benchmark.py", "--kind", "openmp", "--site", "local",
            "--solver", "build/openmp", "--allocated-cpus", "1", "--threads", "1",
            "--sizes", "8", "--iterations", "3", "--warmups", "0", "--output", str(output), *extra], expected)

    def test_round_trip_and_provenance_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.benchmark(root/"run")
            raw=root/"run/raw.jsonl"
            rows=[json.loads(line) for line in raw.read_text().splitlines()]
            self.assertEqual(len(rows),3)
            self.assertTrue(all(r["site"]=="local" and r["mode"]=="fixed" for r in rows))
            self.command(["scripts/analyze.py",str(raw),"--output",str(root/"analysis")])
            with (root/"analysis/summary.csv").open() as stream:
                summary=list(csv.DictReader(stream))[0]
            self.assertEqual(summary["serial_speedup"], "")
            self.assertEqual(float(summary["median_seconds"]), sorted(r["solve_seconds"] for r in rows)[1])
            for mutation in ["site", "duplicate", "warmup", "insufficient"]:
                data=[dict(r) for r in rows]
                if mutation=="site": data[0]["site"]="vanda"
                elif mutation=="duplicate": data[0]["repeat"]=data[1]["repeat"]
                elif mutation=="warmup": data[0]["warmup"]=True
                else: data=data[:2]
                bad=root/f"{mutation}.jsonl"
                bad.write_text("\n".join(json.dumps(r) for r in data)+"\n")
                self.command(["scripts/analyze.py",str(bad),"--output",str(root/mutation)], expected=2)

    def test_allocation_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"unused"
            for extra in [("--threads","2"),("--site","vanda"),("--repeats","2"),
                          ("--solver","build/missing"),("--iterations","0")]:
                self.benchmark(out,*extra,expected=2)
                self.assertFalse(out.exists())

    def test_submitted_provenance_needs_no_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"bin").mkdir()
            marker=root/"git-was-called"
            git=root/"bin/git"
            git.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 127\n")
            git.chmod(0o755)
            provenance=root/"source-provenance.json"
            fixture=dict(recorded_on="login_node", git_head={"stdout":"fixture-commit\n"},
                         git_status={"stdout":""}, archive_sha256="fixture-only")
            provenance.write_text(json.dumps(fixture))
            with patch.dict(os.environ, PATH=str(root/"bin")+os.pathsep+os.environ["PATH"]):
                self.benchmark(root/"run","--source-provenance",str(provenance))
            metadata=json.loads((root/"run/metadata.json").read_text())
            self.assertEqual(metadata["git_head"],fixture["git_head"])
            self.assertEqual(metadata["source_provenance"],fixture)
            self.assertFalse(marker.exists(),"benchmark invoked Git despite supplied login-node provenance")


if __name__ == "__main__":
    unittest.main(verbosity=2)
