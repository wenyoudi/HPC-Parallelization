#!/usr/bin/env python3
"""Local PBS-rendering/provenance fixtures. No scheduler or Vanda jobs are used."""
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class SubmissionTests(unittest.TestCase):
    def test_provenance_snapshot_and_pbs_placement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/"checkout with spaces"
            (root/"scripts").mkdir(parents=True)
            qsub = Path(tmp)/"qsub-fixture"
            qsub.write_text("#!/bin/sh\nprintf 'fixture.server\\n'\n")
            qsub.chmod(0o755)
            # Replace only external site checks/submission in the fixture copy.
            script = (REPO/"scripts/submit_vanda.sh").read_text()
            script = script.replace("source scripts/vanda-env.sh", ": # fixture module environment")
            script = script.replace("/opt/pbs/bin/qsub",shlex.quote(str(qsub)))
            (root/"scripts/submit_vanda.sh").write_text(script)
            (root/"scripts/run_vanda_job.sh").write_text(
                '#!/bin/bash\ncd "$(dirname "${BASH_SOURCE[0]}")/.."\n'
                'pwd -P > "$VANDA_JOB_DIR/source-launch-cwd.txt"\n')
            (root/".gitignore").write_text("/results/\n/.vanda-openmp-workspace\n")
            (root/"source.txt").write_text("submitted source\n")
            subprocess.run(["git","init","-b","feature/openmp-hybrid"],cwd=root,capture_output=True,check=True)
            subprocess.run(["git","add","."],cwd=root,check=True)
            subprocess.run(["git","-c","user.name=Fixture","-c","user.email=fixture@example.invalid",
                            "commit","-m","fixture"],cwd=root,capture_output=True,check=True)
            commit = subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True)
            (root/".vanda-openmp-workspace").write_text(str(root.resolve())+"\n")
            jobs = []
            for kind, placement, slots, threads in [("openmp-validate","shared",1,8),
                                                     ("mpi-smoke","shared",8,1),("openmp","excl",1,8),
                                                     ("serial-compare","shared",1,8)]:
                env = dict(os.environ)
                env.pop("VANDA_PLACEMENT",None)
                subprocess.run(["bash","scripts/submit_vanda.sh",kind],cwd=root,env=env,
                               capture_output=True,text=True,check=True)
                out = root/(root/f"results/vanda/latest-{kind}.txt").read_text().strip()
                job = out/"job.pbs"
                subprocess.run(["bash","-n",str(job)],check=True)
                body = job.read_text()
                self.assertIn(f"#PBS -l place={placement}",body)
                self.assertIn(f"ncpus=8:mpiprocs={slots}:ompthreads={threads}",body)
                self.assertIn("source source/scripts/run_vanda_job.sh",body)
                self.assertEqual((out/"source-commit.txt").read_text(),commit)
                self.assertEqual((out/"source-status.txt").read_text(),"")
                jobs.append(out)
            # Four-CPU smoke allocations carry the selected launch mode to the
            # compute job. Runtime host slots still come from qstat, not this input.
            env=dict(os.environ,VANDA_CPUS="4",VANDA_MPI_LAUNCHER="pbs")
            subprocess.run(["bash","scripts/submit_vanda.sh","mpi-smoke"],cwd=root,env=env,
                           capture_output=True,text=True,check=True)
            out=root/(root/"results/vanda/latest-mpi-smoke.txt").read_text().strip()
            body=(out/"job.pbs").read_text()
            self.assertIn("ncpus=4:mpiprocs=4:ompthreads=1",body)
            self.assertIn("export VANDA_MPI_LAUNCHER=pbs",body)
            jobs.append(out)
            for kind in ["mpi-validate","hybrid-validate","hybrid"]:
                blocked=subprocess.run(["bash","scripts/submit_vanda.sh",kind],cwd=root,env=dict(env,VANDA_CPUS="8"),
                                       capture_output=True,text=True)
                self.assertNotEqual(blocked.returncode,0)
                self.assertIn("integration is pending",blocked.stderr)
                self.assertFalse((root/f"results/vanda/latest-{kind}.txt").exists())
            # A subsequent working-tree edit cannot change an already submitted snapshot.
            (root/"source.txt").write_text("later edit\n")
            for out in jobs:
                with tarfile.open(out/"source.tar.gz") as archive:
                    self.assertEqual(archive.extractfile("source.txt").read(),b"submitted source\n")
            # Execute the generated bootstrap with a fixture payload, not a PBS
            # workload. Git is deliberately unusable in this compute-like PATH.
            (Path(tmp)/"bin").mkdir()
            git_marker=Path(tmp)/"unexpected-git-call"
            git=Path(tmp)/"bin/git"
            git.write_text(f"#!/bin/sh\ntouch '{git_marker}'\nexit 127\n")
            git.chmod(0o755)
            env=dict(os.environ,PATH=str(git.parent)+os.pathsep+os.environ["PATH"])
            for out in jobs:
                subprocess.run(["bash",str(out/"job.pbs")],env=env,capture_output=True,check=True)
                self.assertEqual((out/"source-launch-cwd.txt").read_text().strip(),str((out/"source").resolve()))
            self.assertFalse(git_marker.exists())
            with (jobs[0]/"source.tar.gz").open("ab") as archive:
                archive.write(b"tampered")
            corrupt=subprocess.run(["bash",str(jobs[0]/"job.pbs")],env=env,capture_output=True,text=True)
            self.assertNotEqual(corrupt.returncode,0)
            self.assertIn("checksum mismatch",corrupt.stderr)
            failed = subprocess.run(["bash","scripts/submit_vanda.sh","mpi-smoke"],cwd=root,
                                    capture_output=True,text=True)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn("Commit or preserve local changes",failed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
