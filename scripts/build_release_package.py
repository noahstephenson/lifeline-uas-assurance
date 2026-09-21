from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from lifeline.campaign import audit_release
from lifeline.config import PROJECT_ROOT

RELEASE_NAME = "lifeline-evidence-v1.0.0-magazine-demo.zip"
PUBLIC_PX4_RUNS = {
    "LFL-SMOKE-PX4-20260921T022921Z-A837",
    "LFL-T01-PX4-20260921T094403Z-1CE3",
    "LFL-T05-PX4-20260921T095622Z-00F1",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the curated Project Lifeline public evidence attachment")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "dist")
    parser.add_argument("--allow-incomplete-metadata", action="store_true")
    args = parser.parse_args()

    audit = audit_release("CAMPAIGN-20260920-C")
    accepted = audit["release_ready"]
    if args.allow_incomplete_metadata:
        accepted = all(value for key, value in audit["checks"].items() if key != "citation_metadata_complete")
    if not accepted:
        print(json.dumps(audit, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    if set(audit["qualifying_px4_runs"]) | set(audit["qualifying_px4_smoke_runs"]) != PUBLIC_PX4_RUNS:
        raise RuntimeError("the curated PX4 evidence set does not match the approved release set")

    tracked = _tracked_evidence_files()
    if not tracked:
        raise RuntimeError("no tracked evidence files were found")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / RELEASE_NAME
    metadata = {
        "schema_version": "1.0.0",
        "release": "v1.0.0-magazine-demo",
        "commit": _git_output("rev-parse", "HEAD"),
        "simulation_only": True,
        "human_usability_study": False,
        "public_px4_runs": sorted(PUBLIC_PX4_RUNS),
        "tracked_evidence_runs": audit["tracked_evidence_runs"],
    }
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in tracked:
            _write_deterministic(archive, relative, (PROJECT_ROOT / relative).read_bytes())
        _write_deterministic(archive, Path("release-package.json"), (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode())

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    sums_path = output / "SHA256SUMS"
    sums_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8", newline="\n")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("release archive failed CRC verification")
    print(json.dumps({"archive": str(archive_path), "sha256": digest, "sha256sums": str(sums_path)}, indent=2))
    return 0


def _tracked_evidence_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "evidence"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(line) for line in sorted(result.stdout.splitlines()) if line and not line.endswith(".gitkeep")]


def _git_output(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()


def _write_deterministic(archive: zipfile.ZipFile, relative: Path, data: bytes) -> None:
    info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


if __name__ == "__main__":
    raise SystemExit(main())
