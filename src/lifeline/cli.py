from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from lifeline import __version__
from lifeline.config import PROJECT_ROOT, load_config
from lifeline.evidence import export_run, list_runs, load_run
from lifeline.figures import generate_timeline_svg
from lifeline.scenarios import load_scenario, run_px4_scenario, run_scenario
from lifeline.validation import validate_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lifeline", description="Project Lifeline simulation assurance CLI")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit a stable JSON envelope")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="inspect local configuration and optional simulator dependencies")
    sub.add_parser("validate", help="validate requirements, hazards, traceability, config, and scenarios")

    run = sub.add_parser("run", help="execute a controlled scenario")
    run.add_argument("--scenario", required=True, help="scenario ID such as T-05")
    run.add_argument("--source", choices=["fake", "px4"], default="fake")
    run.add_argument("--allow-sitl-actions", action="store_true")
    run.add_argument("--exploratory", action="store_true")

    runs = sub.add_parser("runs", help="discover or inspect evidence runs")
    runs_sub = runs.add_subparsers(dest="runs_command", required=True)
    runs_sub.add_parser("list", help="list evidence runs")
    show = runs_sub.add_parser("show", help="show one evidence manifest")
    show.add_argument("run_id")

    evidence = sub.add_parser("evidence", help="inspect and verify an evidence bundle")
    evidence.add_argument("--run", required=True, dest="run_id")

    figure = sub.add_parser("figure", help="generate an SVG assurance timeline")
    figure.add_argument("--run", required=True, dest="run_id")

    replay = sub.add_parser("replay", help="serve one completed run through the live/history API")
    replay.add_argument("--run", required=True, dest="run_id")
    replay.add_argument("--host", default="127.0.0.1")
    replay.add_argument("--port", type=int, default=8000)

    serve = sub.add_parser("serve", help="serve the latest run through the live/history API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

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
    if args.command == "run":
        scenario = load_scenario(args.scenario)
        config = load_config()
        if args.source == "px4":
            run = asyncio.run(
                run_px4_scenario(
                    scenario,
                    config,
                    allow_sitl_actions=args.allow_sitl_actions,
                    exploratory=args.exploratory,
                )
            )
        else:
            run = run_scenario(scenario, config, exploratory=args.exploratory)
        manifest = export_run(run)
        return manifest.model_dump(mode="json")
    if args.command == "runs":
        return list_runs() if args.runs_command == "list" else load_run(args.run_id)
    if args.command == "evidence":
        loaded = load_run(args.run_id)
        run_dir = Path(loaded["directory"])
        manifest = loaded["manifest"]
        missing = [name for name in manifest["files"].values() if not (run_dir / name).exists()]
        return {
            "run_id": args.run_id,
            "complete": not missing,
            "effective_verification_status": "INCOMPLETE" if missing else manifest["verification_status"],
            "missing": missing,
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
            "supported": sys.version_info[:2] == (3, 11),
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
