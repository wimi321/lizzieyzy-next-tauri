#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.katago-live-smoke.v1"
REQUIRED_CHECKS = [
    "engine_assets",
    "version_probe",
    "one_position_analysis",
    "batch_analysis",
    "stderr_capture",
]


class SmokeError(RuntimeError):
    pass


def analysis_query(query_id: str, moves: list[list[str]], *, max_visits: int) -> str:
    return json.dumps(
        {
            "id": query_id,
            "rules": "chinese",
            "komi": 7.5,
            "boardXSize": 19,
            "boardYSize": 19,
            "initialStones": [],
            "moves": moves,
            "maxVisits": max_visits,
            "includeOwnership": True,
            "includePolicy": True,
        },
        separators=(",", ":"),
    )


def run_command(command: list[str], *, input_text: str | None, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def parse_jsonl(stdout: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SmokeError(f"KataGo stdout contains invalid JSONL at line {len(rows) + 1}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise SmokeError("KataGo stdout JSONL rows must be objects")
        rows.append(value)
    return rows


def validate_response(response: dict[str, Any], expected_id: str) -> dict[str, Any]:
    if response.get("id") != expected_id:
        raise SmokeError(f"KataGo response id mismatch: expected {expected_id!r}, got {response.get('id')!r}")
    move_infos = response.get("moveInfos")
    if not isinstance(move_infos, list) or not move_infos:
        raise SmokeError("KataGo response missing non-empty moveInfos")
    root_info = response.get("rootInfo")
    if not isinstance(root_info, dict):
        raise SmokeError("KataGo response missing rootInfo")
    return {
        "id": expected_id,
        "moveInfoCount": len(move_infos),
        "hasRootInfo": True,
        "hasOwnership": "ownership" in response,
        "hasPolicy": "policy" in response,
    }


def run_live_smoke(engine: Path, model: Path, config: Path, *, timeout: float, max_visits: int) -> dict[str, Any]:
    start = time.time()
    engine = engine.resolve()
    model = model.resolve()
    config = config.resolve()
    checks: list[dict[str, Any]] = []

    missing = [
        label
        for label, path in (("engine", engine), ("model", model), ("config", config))
        if not path.exists()
    ]
    if missing:
        raise SmokeError("missing KataGo asset(s): " + ", ".join(missing))
    checks.append(
        {
            "name": "engine_assets",
            "status": "pass",
            "details": {
                "enginePath": str(engine),
                "modelPath": str(model),
                "configPath": str(config),
                "engineExecutable": engine.is_file() and os.access(engine, os.X_OK),
                "modelBytes": model.stat().st_size,
                "configBytes": config.stat().st_size,
            },
        }
    )

    version = run_command([str(engine), "version"], input_text=None, timeout=min(timeout, 15.0))
    version_text = (version.stdout + version.stderr).strip()
    if version.returncode != 0:
        raise SmokeError(f"KataGo version probe failed with exit {version.returncode}: {version_text}")
    checks.append(
        {
            "name": "version_probe",
            "status": "pass",
            "details": {
                "exitCode": version.returncode,
                "versionText": version_text.splitlines()[0] if version_text else "version command returned no text",
            },
        }
    )

    analysis_command = [
        str(engine),
        "analysis",
        "-model",
        str(model),
        "-config",
        str(config),
    ]
    one_id = "katago-live-smoke-one"
    one_query = analysis_query(one_id, [["B", "D4"], ["W", "Q16"], ["B", "Q4"]], max_visits=max_visits)
    one = run_command(analysis_command, input_text=one_query + "\n", timeout=timeout)
    if one.returncode != 0:
        raise SmokeError(f"KataGo one-position analysis failed with exit {one.returncode}: {one.stderr.strip()}")
    one_rows = parse_jsonl(one.stdout)
    if len(one_rows) != 1:
        raise SmokeError(f"KataGo one-position analysis returned {len(one_rows)} JSONL rows, expected 1")
    one_details = validate_response(one_rows[0], one_id)
    checks.append({"name": "one_position_analysis", "status": "pass", "details": one_details})

    batch_queries = [
        analysis_query("katago-live-smoke-batch-1", [["B", "D4"]], max_visits=max_visits),
        analysis_query("katago-live-smoke-batch-2", [["B", "D4"], ["W", "Q16"]], max_visits=max_visits),
    ]
    batch = run_command(analysis_command, input_text="\n".join(batch_queries) + "\n", timeout=timeout)
    if batch.returncode != 0:
        raise SmokeError(f"KataGo batch analysis failed with exit {batch.returncode}: {batch.stderr.strip()}")
    batch_rows = parse_jsonl(batch.stdout)
    if len(batch_rows) != len(batch_queries):
        raise SmokeError(f"KataGo batch analysis returned {len(batch_rows)} JSONL rows, expected {len(batch_queries)}")
    batch_details = [
        validate_response(response, f"katago-live-smoke-batch-{index}")
        for index, response in enumerate(batch_rows, start=1)
    ]
    checks.append(
        {
            "name": "batch_analysis",
            "status": "pass",
            "details": {"responseCount": len(batch_details), "responses": batch_details},
        }
    )
    checks.append(
        {
            "name": "stderr_capture",
            "status": "pass",
            "details": {
                "onePositionStderrBytes": len(one.stderr.encode("utf-8")),
                "batchStderrBytes": len(batch.stderr.encode("utf-8")),
                "stderrCaptured": True,
            },
        }
    )

    return {
        "schema": SCHEMA,
        "name": "katago_live_smoke",
        "status": "pass",
        "platform": "macos" if platform.system() == "Darwin" else platform.system().lower(),
        "startedAtEpoch": start,
        "finishedAtEpoch": time.time(),
        "engine": {
            "path": str(engine),
            "modelPath": str(model),
            "configPath": str(config),
            "maxVisits": max_visits,
            "timeoutSeconds": timeout,
        },
        "checks": checks,
    }


def sanitize_evidence(value: Any, replacements: list[tuple[str, str]]) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_evidence(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_evidence(item, replacements) for item in value]
    if isinstance(value, str):
        sanitized = value
        for source, target in replacements:
            sanitized = sanitized.replace(source, target)
            if source.startswith("/private/var/"):
                sanitized = sanitized.replace(source.removeprefix("/private"), target)
            elif source.startswith("/var/"):
                sanitized = sanitized.replace("/private" + source, target)
        return sanitized
    return value


def write_evidence(path: Path, report: dict[str, Any], *, root: Path) -> None:
    engine = report.get("engine", {})
    replacements = [(str(root.resolve()), "<repo>")]
    if isinstance(engine, dict):
        for key, marker in (("path", "<katago-engine>"), ("modelPath", "<katago-model>"), ("configPath", "<katago-config>")):
            value = engine.get(key)
            if isinstance(value, str) and value:
                replacements.append((value, marker))
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_evidence(report, replacements), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a live KataGo analysis smoke and write sanitized evidence.")
    parser.add_argument("--engine", type=Path, required=True, help="KataGo executable path")
    parser.add_argument("--model", type=Path, required=True, help="KataGo model path")
    parser.add_argument("--config", type=Path, required=True, help="KataGo analysis config path")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds per analysis command")
    parser.add_argument("--max-visits", type=int, default=1, help="KataGo maxVisits for smoke queries")
    parser.add_argument("--evidence-out", type=Path, default=ROOT / "docs/qa/katago-live-smoke-macos.json")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    try:
        report = run_live_smoke(args.engine, args.model, args.config, timeout=args.timeout, max_visits=args.max_visits)
        write_evidence(args.evidence_out, report, root=args.root)
    except (SmokeError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"FAIL KataGo live smoke: {exc}", file=sys.stderr)
        return 1
    print(f"PASS KataGo live smoke: {len(REQUIRED_CHECKS)} required checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
