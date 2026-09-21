from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RETIRED_IDENTIFIERS = (
    "maga" + "zine",
    "manu" + "script",
    "IEEE " + "AESS",
    "advi" + "sor",
    "project " + "photograph",
    "editor" + "ial",
    "publi" + "cation submission",
    "citation_" + "metadata_complete",
    "verified-" + "publi" + "cation-review",
    "v1.0.0-" + "maga" + "zine-demo",
)


def test_retired_identifiers_are_absent_from_tracked_content():
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
    )
    findings: list[str] = []
    for name in result.stdout.decode().split("\0"):
        path = PROJECT_ROOT / name
        if not name or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.casefold()
        for identifier in RETIRED_IDENTIFIERS:
            pattern = rf"(?<!\w){re.escape(identifier.casefold())}(?!\w)"
            if re.search(pattern, lowered):
                findings.append(f"{name}: {identifier}")

    assert findings == []
