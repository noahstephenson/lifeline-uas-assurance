from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import platform
import secrets
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lifeline import __version__
from lifeline.campaign import audit_release, run_fake_campaign
from lifeline.config import PROJECT_ROOT, load_config, validate_sitl_qualification
from lifeline.evidence import (
    attach_run_artifact,
    export_public_run,
    export_run,
    list_runs,
    load_run,
    reserve_evidence_directory,
    verify_run_integrity,
)
from lifeline.figures import generate_timeline_svg
from lifeline.models import AssertionResult
from lifeline.scenarios import load_scenario, load_scenarios, run_px4_scenario, run_scenario
from lifeline.scenarios.runner import ScenarioRun
from lifeline.smoke import finalize_smoke_setup_error, run_px4_smoke
from lifeline.validation import validate_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lifeline", description="Project Lifeline simulation assurance CLI")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit a stable JSON envelope")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="inspect local configuration and optional simulator dependencies")
    sub.add_parser("validate", help="validate requirements, hazards, traceability, config, and scenarios")

    scenarios = sub.add_parser("scenarios", help="discover the controlled mission catalogue")
    scenarios_sub = scenarios.add_subparsers(dest="scenarios_command", required=True)
    scenarios_sub.add_parser("list", help="list scenarios and expected lessons")
    scenario_show = scenarios_sub.add_parser("show", help="show one resolved scenario")
    scenario_show.add_argument("scenario_id")

    run = sub.add_parser("run", help="execute a controlled scenario")
    run.add_argument("--scenario", required=True, help="scenario ID such as T-05")
    run.add_argument("--source", choices=["fake", "px4"], default="fake")
    run.add_argument("--config", help="configuration path under config/")
    run.add_argument("--run-id", help="explicit unique evidence run ID")
    run.add_argument("--allow-sitl-actions", action="store_true")
    run.add_argument("--exploratory", action="store_true")

    campaign = sub.add_parser("campaign", help="run or audit the controlled scenario campaign")
    campaign_sub = campaign.add_subparsers(dest="campaign_command", required=True)
    campaign_run = campaign_sub.add_parser("run", help="run the complete controlled fake-source scenario catalogue")
    campaign_run.add_argument("--id", dest="campaign_id")
    campaign_audit = campaign_sub.add_parser("audit", help="audit release gates against a campaign")
    campaign_audit.add_argument("--id", dest="campaign_id")
    campaign_audit.add_argument("--exported-tree", action="store_true", help="audit a git archive or clean exported tree")

    runs = sub.add_parser("runs", help="discover or inspect evidence runs")
    runs_sub = runs.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_sub.add_parser("list", help="list evidence runs")
    runs_list.add_argument("--scenario")
    runs_list.add_argument("--source", choices=["fake", "px4"])
    runs_list.add_argument("--status")
    show = runs_sub.add_parser("show", help="show one evidence manifest")
    show.add_argument("run_id")

    evidence = sub.add_parser("evidence", help="inspect and verify an evidence bundle")
    evidence.add_argument("--run", required=True, dest="run_id")
    evidence.add_argument("--attach-name", choices=["px4_log", "api_log"])
    evidence.add_argument("--file", type=Path)
    evidence.add_argument("--export-public", type=Path, dest="export_public")

    figure = sub.add_parser("figure", help="generate an SVG assurance timeline")
    figure.add_argument("--run", required=True, dest="run_id")

    replay = sub.add_parser("replay", help="serve one completed run through the live/history API")
    replay.add_argument("--run", required=True, dest="run_id")
    replay.add_argument("--host", default="127.0.0.1")
    replay.add_argument("--port", type=int, default=8000)

    serve = sub.add_parser("serve", help="serve the latest run through the live/history API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    live = sub.add_parser("live", help="hold and stream a PX4 scenario until the loopback launcher releases it")
    live.add_argument("--scenario", required=True)
    live.add_argument("--config", default="config/sitl-qualification.yaml")
    live.add_argument("--run-id")
    live.add_argument("--host", default="127.0.0.1")
    live.add_argument("--port", type=int, default=8000)
    live.add_argument("--setup-error", help=argparse.SUPPRESS)

    smoke = sub.add_parser("px4-smoke", help="qualify stock X500 arm, takeoff, altitude, and landing")
    smoke.add_argument("--config", default="config/sitl-qualification.yaml")
    smoke.add_argument("--run-id")
    smoke.add_argument("--setup-error", help=argparse.SUPPRESS)

    inject = sub.add_parser("inject", help="validate a manual exploratory injection request")
    inject.add_argument(
        "--field",
        required=True,
        choices=["operator_link_available", "navigation_confidence", "energy_margin_wh"],
    )
    inject.add_argument("--value", required=True)
    inject.add_argument("--exploratory", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        data = dispatch(args)
        _emit(args.as_json, True, data)
    except Exception as exc:  # CLI boundary intentionally normalizes failures
        _emit(args.as_json, False, {"type": type(exc).__name__, "message": str(exc)})
        raise SystemExit(1) from None


def dispatch(args: argparse.Namespace) -> Any:
    if args.command == "doctor":
        return doctor()
    if args.command == "validate":
        result = validate_project()
        if not result["valid"]:
            raise ValueError("; ".join(result["errors"]))
        return result
    if args.command == "scenarios":
        if args.scenarios_command == "show":
            return load_scenario(args.scenario_id).model_dump(mode="json")
        return [
            {
                "id": item.id,
                "name": item.name,
                "event_count": len(item.events),
                "expected_terminal_state": item.expect.terminal_state.value,
                "expected_delivery_outcome": (
                    item.expect.delivery_outcome.value if item.expect.delivery_outcome else "NOT_DECLARED"
                ),
                "requirements": item.trace.requirements,
                "hazards": item.trace.hazards,
            }
            for item in load_scenarios()
        ]
    if args.command == "run":
        scenario = load_scenario(args.scenario)
        config = _load_cli_config(args.config, require_qualification=args.source == "px4")
        if args.source == "px4":
            run_id = args.run_id or _run_id(scenario.id, "PX4")
            reserve_evidence_directory(run_id)
            try:
                run = asyncio.run(
                    run_px4_scenario(
                        scenario,
                        config,
                        run_id=run_id,
                        allow_sitl_actions=args.allow_sitl_actions,
                        exploratory=args.exploratory,
                    )
                )
            except Exception as exc:
                run = ScenarioRun(
                    run_id=run_id,
                    scenario=scenario,
                    snapshots=[],
                    decisions=[],
                    assertions=[AssertionResult(name="px4_run_completed", passed=False, expected="complete", observed=str(exc))],
                    source="px4",
                    configuration=config,
                    error=f"{type(exc).__name__}: {exc}",
                )
        else:
            run = run_scenario(scenario, config, run_id=args.run_id, exploratory=args.exploratory)
        manifest = export_run(run)
        return manifest.model_dump(mode="json")
    if args.command == "runs":
        if args.runs_command == "show":
            return load_run(args.run_id)
        runs = list_runs()
        if args.scenario:
            runs = [item for item in runs if item.get("scenario_id") == args.scenario]
        if args.source:
            runs = [item for item in runs if item.get("software_versions", {}).get("source") == args.source]
        if args.status:
            runs = [item for item in runs if item.get("verification_status") == args.status]
        return runs
    if args.command == "campaign":
        if args.campaign_command == "run":
            return run_fake_campaign(campaign_id=args.campaign_id)
        return audit_release(args.campaign_id, exported_tree=args.exported_tree)
    if args.command == "evidence":
        if args.export_public and (args.attach_name or args.file):
            raise ValueError("--export-public cannot be combined with --attach-name or --file")
        if args.export_public:
            return export_public_run(args.run_id, args.export_public)
        if bool(args.attach_name) != bool(args.file):
            raise ValueError("--attach-name and --file must be supplied together")
        if args.attach_name and args.file:
            return attach_run_artifact(args.run_id, args.attach_name, args.file)
        loaded = load_run(args.run_id)
        manifest = loaded["manifest"]
        integrity = verify_run_integrity(args.run_id)
        return {
            "run_id": args.run_id,
            "complete": integrity["complete"],
            "effective_verification_status": integrity["verification_status"],
            "missing": integrity["missing"],
            "mismatched": integrity["mismatched"],
            "unchecked": integrity["unchecked"],
            "manifest": manifest,
        }
    if args.command == "figure":
        output = generate_timeline_svg(args.run_id)
        return {"run_id": args.run_id, "path": str(output), "bytes": output.stat().st_size}
    if args.command in {"serve", "replay"}:
        selected = args.run_id if args.command == "replay" else None
        if selected:
            load_run(selected)
        import uvicorn

        from lifeline.api import create_app

        uvicorn.run(create_app(selected), host=args.host, port=args.port)
        return {"stopped": True}
    if args.command == "live":
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("live qualification API must bind to loopback")
        scenario = load_scenario(args.scenario)
        config = _load_cli_config(args.config, require_qualification=True)
        run_id = args.run_id or _run_id(scenario.id, "LIVE")
        if args.setup_error:
            from lifeline.live import finalize_live_setup_error

            manifest = finalize_live_setup_error(scenario, config, run_id=run_id, error=args.setup_error)
            raise RuntimeError(f"live PX4 run failed; evidence bundle finalized as {run_id}: {manifest['verification_status']}")
        token = os.getenv("LIFELINE_START_TOKEN")
        if not token:
            raise ValueError("LIFELINE_START_TOKEN must be set by the qualification launcher")
        reserve_evidence_directory(run_id)
        import uvicorn

        from lifeline.live import LiveSession, create_live_app

        session = LiveSession(scenario, config, run_id=run_id, start_token=token)
        uvicorn.run(create_live_app(session), host=args.host, port=args.port)
        return {"stopped": True, "run_id": run_id}
    if args.command == "px4-smoke":
        config = _load_cli_config(args.config, require_qualification=True)
        run_id = args.run_id or _run_id("SMOKE", "PX4")
        manifest = (
            finalize_smoke_setup_error(config, run_id=run_id, error=args.setup_error)
            if args.setup_error
            else asyncio.run(run_px4_smoke(config, run_id=run_id))
        )
        if manifest["verification_status"] != "PASS":
            raise RuntimeError(f"PX4 smoke failed; evidence bundle finalized as {run_id}")
        return manifest
    if args.command == "inject":
        value: bool | float
        if args.field == "operator_link_available":
            lowered = args.value.lower()
            if lowered not in {"true", "false"}:
                raise ValueError("operator_link_available must be true or false")
            value = lowered == "true"
        else:
            value = float(args.value)
        return {
            "accepted": True,
            "exploratory": True,
            "injection": {"field": args.field, "value": value},
            "note": "manual injections are not controlled verification evidence",
        }
    raise ValueError(f"unknown command: {args.command}")


def doctor() -> dict[str, Any]:
    modules = {name: bool(importlib.util.find_spec(name)) for name in ["pydantic", "fastapi", "yaml", "uvicorn", "mavsdk"]}
    config = load_config()
    return {
        "lifeline_version": __version__,
        "python": {
            "version": platform.python_version(),
            "supported": (3, 11) <= sys.version_info[:2] < (3, 13),
        },
        "project_root": str(PROJECT_ROOT),
        "offline_mode": True,
        "auth_required": False,
        "modules": modules,
        "tools": {
            "git": shutil.which("git"),
            "node": shutil.which("node"),
            "npm": shutil.which("npm"),
            "wsl": shutil.which("wsl"),
        },
        "px4": {
            "configured": modules["mavsdk"] and shutil.which("wsl") is not None,
            "actions_enabled_by_default": config.sitl.actions_enabled,
            "endpoint": config.sitl.endpoint,
        },
    }


def _load_cli_config(value: str | None, *, require_qualification: bool = False):
    if value is None:
        return load_config()
    path = (PROJECT_ROOT / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    config_root = (PROJECT_ROOT / "config").resolve()
    if path != config_root and config_root not in path.parents:
        raise ValueError("configuration must be located under the project config directory")
    if require_qualification:
        return validate_sitl_qualification(path)
    return load_config(path)


def _run_id(scenario_id: str, source: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = secrets.token_hex(2).upper()
    return f"LFL-{scenario_id.replace('-', '')}-{source}-{stamp}-{suffix}"


def _emit(as_json: bool, ok: bool, data: Any) -> None:
    if as_json:
        key = "data" if ok else "error"
        print(json.dumps({"ok": ok, key: data}, indent=2, default=str))
    elif ok:
        if isinstance(data, str):
            print(data)
        else:
            print(json.dumps(data, indent=2, default=str))
    else:
        print(f"error: {data['message']}", file=sys.stderr)


if __name__ == "__main__":
    main()
