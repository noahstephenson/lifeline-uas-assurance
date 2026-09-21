from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_qualifier_keeps_wsl_process_arguments_structured():
    script = (ROOT / "scripts" / "qualify-px4.ps1").read_text(encoding="utf-8")
    assert '"--cd", "$WslHome/PX4-Autopilot", "--", "make"' in script
    assert '"--", "env", "LIFELINE_START_TOKEN=$Token"' in script
    assert '"--", "bash", "-lc", "cd ~/PX4-Autopilot' not in script
