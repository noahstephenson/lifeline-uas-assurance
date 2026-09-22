from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify release evidence from a fresh git archive of HEAD")
    parser.add_argument("--campaign", default="CAMPAIGN-20260922-PRESENTATION-V11")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="lifeline-release-export-") as temporary:
        temporary_path = Path(temporary)
        archive_path = temporary_path / "head.tar"
        export_root = temporary_path / "checkout"
        export_root.mkdir()
        archive = subprocess.run(
            ["git", "archive", "--format=tar", "-o", str(archive_path), "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if archive.returncode:
            print(archive.stderr, file=sys.stderr)
            return archive.returncode
        with tarfile.open(archive_path) as stream:
            stream.extractall(export_root)

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(export_root / "src")
        audit = subprocess.run(
            [
                sys.executable,
                "-m",
                "lifeline.cli",
                "--json",
                "campaign",
                "audit",
                "--id",
                args.campaign,
                "--exported-tree",
            ],
            cwd=export_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if audit.returncode:
            print(audit.stdout)
            print(audit.stderr, file=sys.stderr)
            return audit.returncode
        envelope = json.loads(audit.stdout)
        result = envelope["data"]
        accepted = result["release_ready"]
        print(json.dumps({"accepted": accepted, "exported_tree_audit": result}, indent=2, sort_keys=True))
        return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
