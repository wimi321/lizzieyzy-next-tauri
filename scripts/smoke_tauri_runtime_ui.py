#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
REQUIRED_CHECKS = [
    "runtime_started",
    "sgf_loaded",
    "branch_navigation",
    "comment_edit",
    "property_edit",
    "append_move",
    "edit_move",
    "delete_node",
    "variation_reorder",
    "save_readback_roundtrip",
    "board_state_verified",
]
SMOKE_SGF = """(;FF[4]GM[1]CA[UTF-8]AP[LizzieYzyNextSmoke]SZ[9]KM[6.5]PB[Black]PW[White]C[root]
;B[dd]C[main one]LB[dd:A]
(;W[ee]C[first branch]TR[ee];B[de]C[branch child])
(;W[fd]C[second branch]SQ[fd])
(;W[]C[pass branch]))
"""


class SmokeError(RuntimeError):
    pass


def write_runtime_sgf(path: Path) -> None:
    path.write_text(SMOKE_SGF, encoding="utf-8")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"report was not created: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"report is invalid JSON at line {exc.lineno}: {exc.msg}") from exc


def validate_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["report root must be an object"]
    failures: list[str] = []
    if report.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    if str(report.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    checks = report.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    statuses: dict[str, str] = {}
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            failures.append(f"checks[{index}] must be an object")
            continue
        name = check.get("name")
        if not isinstance(name, str) or not name:
            failures.append(f"checks[{index}].name must be a non-empty string")
            continue
        statuses[name] = str(check.get("status", "")).lower()
    missing = [name for name in REQUIRED_CHECKS if name not in statuses]
    not_pass = [name for name in REQUIRED_CHECKS if name in statuses and statuses[name] != "pass"]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_semantic_checks(checks))
    return failures


def validate_semantic_checks(checks: list[Any]) -> list[str]:
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    failures: list[str] = []
    failures.extend(validate_variation_reorder_evidence(check_by_name.get("variation_reorder")))
    failures.extend(validate_edit_move_evidence(check_by_name.get("edit_move")))
    failures.extend(validate_delete_node_evidence(check_by_name.get("delete_node")))
    failures.extend(validate_save_readback_roundtrip_evidence(check_by_name.get("save_readback_roundtrip")))
    failures.extend(validate_board_state_evidence(check_by_name.get("board_state_verified")))
    return failures


def validate_variation_reorder_evidence(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["variation_reorder evidence must be an object"]
    failures: list[str] = []
    target_index = first_present(evidence, "targetIndex", "target_index", "newIndex", "new_index")
    if target_index != 0:
        failures.append("variation_reorder target index must be 0")
    index_after_move = first_present(evidence, "indexAfterMove", "index_after_move", "siblingIndex", "sibling_index")
    if index_after_move != target_index:
        failures.append("variation_reorder moved node index must match target index")
    moved_node_id = first_present(evidence, "movedNodeId", "moved_node_id", "nodeId", "node_id")
    if not isinstance(moved_node_id, str) or not moved_node_id:
        failures.append("variation_reorder evidence must include moved node id")
    variation_index = first_present(evidence, "variationIndexAfterMove", "variation_index_after_move", "variationIndex", "variation_index")
    if variation_index is not None and variation_index != target_index:
        failures.append("variation_reorder variation index must match target index")
    return failures


def validate_edit_move_evidence(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["edit_move evidence must be an object"]
    target_vertex = first_present(evidence, "targetVertex", "target_vertex", "expectedVertex", "expected_vertex")
    confirmed_vertex = first_present(evidence, "confirmedVertex", "confirmed_vertex", "actualVertex", "actual_vertex", "readbackVertex", "readback_vertex")
    if target_vertex is None:
        return ["edit_move evidence must include target vertex"]
    if confirmed_vertex is None:
        return ["edit_move evidence must include confirmed vertex"]
    if normalize_json_value(target_vertex) != normalize_json_value(confirmed_vertex):
        return ["edit_move confirmed vertex must match target vertex"]
    return []


def validate_delete_node_evidence(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["delete_node evidence must be an object"]
    deleted_node_id = first_present(evidence, "deletedNodeId", "deleted_node_id", "nodeId", "node_id")
    if not isinstance(deleted_node_id, str) or not deleted_node_id:
        return ["delete_node evidence must include deleted node id"]
    exists_after_delete = first_present(
        evidence,
        "existsAfterDelete",
        "exists_after_delete",
        "deletedNodeExistsAfter",
        "deleted_node_exists_after",
    )
    absent_after_delete = first_present(evidence, "absentAfterDelete", "absent_after_delete", "deleteAbsence", "delete_absence")
    if exists_after_delete is False or absent_after_delete is True:
        return []
    return ["delete_node evidence must confirm deleted node is absent after delete"]


def validate_save_readback_roundtrip_evidence(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["save_readback_roundtrip evidence must be an object"]
    failures: list[str] = []
    save_verified = first_present(evidence, "saveVerified", "save_verified")
    saved_path = first_present(evidence, "savedPath", "saved_path", "path")
    if save_verified is not True and not (isinstance(saved_path, str) and saved_path):
        failures.append("save_readback_roundtrip evidence must include save verification")
    readback_verified = first_present(
        evidence,
        "readbackVerified",
        "readback_verified",
        "readbackMatchesSaved",
        "readback_matches_saved",
    )
    saved_hash = first_present(evidence, "savedHash", "saved_hash", "savedSgfHash", "saved_sgf_hash")
    readback_hash = first_present(evidence, "readbackHash", "readback_hash", "readbackSgfHash", "readback_sgf_hash")
    readback_status = first_present(evidence, "readbackStatus", "readback_status")
    if readback_verified is True or readback_status == "matched_saved_text":
        return failures
    if isinstance(saved_hash, str) and saved_hash and saved_hash == readback_hash:
        return failures
    failures.append("save_readback_roundtrip evidence must include readback verification")
    return failures


def validate_board_state_evidence(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["board_state_verified evidence must be an object"]
    invariant = first_present(evidence, "invariant", "invariants", "boardInvariant", "board_invariant")
    if isinstance(invariant, str):
        has_invariant = bool(invariant.strip())
    elif isinstance(invariant, list):
        has_invariant = any(isinstance(item, str) and item.strip() for item in invariant)
    else:
        has_invariant = False
    verified = first_present(
        evidence,
        "verified",
        "invariantVerified",
        "invariant_verified",
        "passed",
        "replayErrorsAbsent",
        "replay_errors_absent",
    )
    if not has_invariant:
        return ["board_state_verified evidence must include an explicit invariant"]
    if verified is not True:
        return ["board_state_verified evidence must confirm invariant passed"]
    return []


def check_evidence(check: Any) -> dict[str, Any] | None:
    if not isinstance(check, dict):
        return None
    for key in ("evidence", "details"):
        value = check.get(key)
        if isinstance(value, dict):
            return value
    return check


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def normalize_json_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sanitize_evidence(value: Any, *, root: Path, temp_dir: Path) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_evidence(item, root=root, temp_dir=temp_dir) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_evidence(item, root=root, temp_dir=temp_dir) for item in value]
    if isinstance(value, str):
        return sanitize_string(value, root=root, temp_dir=temp_dir)
    return value


def sanitize_string(value: str, *, root: Path, temp_dir: Path) -> str:
    replacement_pairs = [
        (temp_dir, "<tmp>"),
        (temp_dir.resolve(), "<tmp>"),
        (root, "<repo>"),
        (root.resolve(), "<repo>"),
    ]
    replacements: set[tuple[str, str]] = set()
    for source, target in replacement_pairs:
        source_text = str(source)
        replacements.add((source_text, target))
        if source_text.startswith("/private/var/"):
            replacements.add((source_text.removeprefix("/private"), target))
        elif source_text.startswith("/var/"):
            replacements.add(("/private" + source_text, target))
    ordered_replacements = sorted(replacements, key=lambda item: len(item[0]), reverse=True)
    sanitized = value
    for source, target in ordered_replacements:
        sanitized = sanitized.replace(source, target)
    return sanitized


def write_evidence(path: Path, report: Any, *, root: Path, temp_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_evidence(report, root=root, temp_dir=temp_dir)
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def start_tauri(root: Path, sgf_path: Path, report_path: Path, log_path: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "LIZZIEYZY_RUNTIME_SMOKE": "1",
            "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
        }
    )
    log_file = log_path.open("wb")
    try:
        process = subprocess.Popen(
            ["npm", "--prefix", "apps/desktop", "run", "tauri:dev"],
            cwd=root,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_file.close()
        return process
    except Exception:
        log_file.close()
        raise


def stop_process(process: subprocess.Popen[bytes], *, grace_seconds: float = 5.0) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.1)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def wait_for_report(report_path: Path, process: subprocess.Popen[bytes], *, timeout_seconds: float) -> Any:
    deadline = time.monotonic() + timeout_seconds
    last_size = -1
    stable_since: float | None = None
    while time.monotonic() < deadline:
        if report_path.is_file():
            size = report_path.stat().st_size
            if size > 0 and size == last_size:
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= 0.25:
                    return load_json(report_path)
            else:
                stable_since = None
                last_size = size
        if process.poll() is not None and not report_path.is_file():
            raise SmokeError(f"tauri:dev exited before writing report (exit {process.returncode})")
        time.sleep(0.25)
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for runtime smoke report")


def run(root: Path, *, timeout_seconds: float, evidence_out: Path | None) -> int:
    root = root.resolve()
    if platform.system() != "Darwin":
        print("Tauri runtime UI smoke is currently a macOS local evidence gate.", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="lizzieyzy-runtime-smoke-") as temp:
        temp_dir = Path(temp)
        sgf_path = temp_dir / "runtime-smoke.sgf"
        report_path = temp_dir / "runtime-smoke-report.json"
        log_path = temp_dir / "tauri-dev.log"
        write_runtime_sgf(sgf_path)
        process = start_tauri(root, sgf_path, report_path, log_path)
        try:
            report = wait_for_report(report_path, process, timeout_seconds=timeout_seconds)
            failures = validate_report(report)
            if failures:
                raise SmokeError("; ".join(failures))
            if evidence_out is not None:
                write_evidence(evidence_out, report, root=root, temp_dir=temp_dir)
            print(f"PASS Tauri runtime UI smoke: {len(REQUIRED_CHECKS)} required checks passed")
            return 0
        except SmokeError as exc:
            print(f"FAIL Tauri runtime UI smoke: {exc}", file=sys.stderr)
            if log_path.is_file():
                print(f"tauri:dev log: {log_path}", file=sys.stderr)
            return 1
        finally:
            stop_process(process)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the macOS Tauri runtime UI smoke and validate its JSON report.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for the runtime report")
    parser.add_argument("--evidence-out", type=Path, help="write sanitized PASS evidence JSON to this path")
    args = parser.parse_args(argv)
    return run(args.root, timeout_seconds=args.timeout, evidence_out=args.evidence_out)


if __name__ == "__main__":
    raise SystemExit(main())
