#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import shutil
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
    "annotation_edit",
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
    failures.extend(validate_annotation_edit_evidence(check_by_name.get("annotation_edit")))
    failures.extend(validate_edit_move_evidence(check_by_name.get("edit_move")))
    failures.extend(validate_delete_node_evidence(check_by_name.get("delete_node")))
    failures.extend(validate_save_readback_roundtrip_evidence(check_by_name.get("save_readback_roundtrip")))
    failures.extend(validate_board_state_evidence(check_by_name.get("board_state_verified")))
    return failures


def validate_annotation_edit_evidence(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["annotation_edit evidence must be an object"]
    failures: list[str] = []
    annotations = evidence.get("annotations")
    if not isinstance(annotations, dict):
        failures.append("annotation_edit annotations must be an object")
        return failures
    expected_annotations = {
        "TR": ["aa"],
        "SQ": [],
        "CR": ["bb"],
        "MA": ["cc"],
        "SL": ["dd"],
        "AR": ["aa:bb"],
        "LN": ["cc:dd"],
    }
    for key, expected_values in expected_annotations.items():
        values = annotations.get(key)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            failures.append(f"annotation_edit annotations.{key} must be a string list")
            continue
        if values != expected_values:
            failures.append(f"annotation_edit annotations.{key} must equal {expected_values!r}")
    label_values = annotations.get("LB")
    if not isinstance(label_values, list) or any(not isinstance(value, str) for value in label_values):
        failures.append("annotation_edit annotations.LB must be a string list")
    else:
        missing_labels = [value for value in ("aa:A", "ee:E") if value not in label_values]
        if missing_labels:
            failures.append("annotation_edit annotations.LB must include aa:A and ee:E")
    expected_lists = {
        "added": {"TR", "CR", "MA", "SL", "AR", "LN"},
        "updated": {"LB"},
        "removed": {"SQ"},
    }
    for field, expected_values in expected_lists.items():
        values = evidence.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            failures.append(f"annotation_edit {field} must be a string list")
            continue
        actual = set(values)
        if actual != expected_values:
            expected_label = ", ".join(sorted(expected_values))
            failures.append(f"annotation_edit {field} must be exactly {expected_label}")
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


def write_evidence(path: Path, evidence: Any, *, root: Path, temp_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_evidence(evidence, root=root, temp_dir=temp_dir)
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def start_tauri(
    root: Path,
    sgf_path: Path,
    report_path: Path,
    log_path: Path,
    *,
    phase: str,
    expected_report_path: Path | None = None,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE": phase,
            "LIZZIEYZY_RUNTIME_SMOKE": "1",
            "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "LIZZIEYZY_RUNTIME_SMOKE_PHASE": phase,
        }
    )
    if expected_report_path is not None:
        env.update(
            {
                "VITE_LIZZIEYZY_RUNTIME_SMOKE_EXPECTED_REPORT_PATH": str(expected_report_path),
                "LIZZIEYZY_RUNTIME_SMOKE_EXPECTED_REPORT_PATH": str(expected_report_path),
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
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.1)
    if process.poll() is None:
        raise SmokeError(f"failed to stop tauri:dev process group for pid {process.pid}")


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


def launch_runtime_smoke(
    root: Path,
    *,
    phase: str,
    sgf_path: Path,
    report_path: Path,
    log_path: Path,
    expected_report_path: Path | None = None,
    timeout_seconds: float,
) -> dict[str, Any]:
    started_at = time.time()
    process = start_tauri(
        root,
        sgf_path,
        report_path,
        log_path,
        phase=phase,
        expected_report_path=expected_report_path,
    )
    launch: dict[str, Any] = {
        "phase": phase,
        "pid": process.pid,
        "sgfPath": str(sgf_path),
        "reportPath": str(report_path),
        "expectedReportPath": str(expected_report_path) if expected_report_path is not None else None,
        "logPath": str(log_path),
        "startedAtUnix": started_at,
        "stopped": False,
    }
    stop_error: SmokeError | None = None
    try:
        report = wait_for_report(report_path, process, timeout_seconds=timeout_seconds)
        launch["report"] = report
        return launch
    finally:
        try:
            stop_process(process)
            launch["stopped"] = True
            launch["exitCode"] = process.poll()
            launch["stoppedAtUnix"] = time.time()
        except SmokeError as exc:
            launch["stopError"] = str(exc)
            stop_error = exc
        if stop_error is not None:
            raise stop_error


def validate_reopen_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["second launch report root must be an object"]
    failures: list[str] = []
    if report.get("schema") != SCHEMA:
        failures.append(f"second launch schema must be {SCHEMA}")
    if str(report.get("status", "")).lower() != "pass":
        failures.append("second launch status must be pass")
    checks = report.get("checks")
    if not isinstance(checks, list):
        failures.append("second launch checks must be a list")
        return failures
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    for required in ("runtime_started", "sgf_loaded", "reopen_state_verified", "save_reopen_roundtrip"):
        check = check_by_name.get(required)
        if not isinstance(check, dict):
            failures.append(f"second launch missing required check: {required}")
        elif str(check.get("status", "")).lower() != "pass":
            failures.append(f"second launch check not pass: {required}")
    runtime_evidence = check_evidence(check_by_name.get("runtime_started"))
    if runtime_evidence is None or runtime_evidence.get("tauriInternals") is not True:
        failures.append("second launch runtime_started evidence must confirm real Tauri runtime")
    return failures


def validate_save_reopen_proof(first_launch: dict[str, Any], second_launch: dict[str, Any], sgf_path: Path) -> list[str]:
    failures: list[str] = []
    if first_launch.get("phase") != "edit-save":
        failures.append("first launch phase must be edit-save")
    if second_launch.get("phase") != "reopen-verify":
        failures.append("second launch phase must be reopen-verify")
    if first_launch.get("stopped") is not True:
        failures.append("first launch process must be stopped before reopen")
    if second_launch.get("stopped") is not True:
        failures.append("second launch process must be stopped")
    first_pid = first_launch.get("pid")
    second_pid = second_launch.get("pid")
    if not isinstance(first_pid, int) or not isinstance(second_pid, int):
        failures.append("launch evidence must include process ids")
    elif first_pid == second_pid:
        failures.append("second launch must use a different Tauri process id")
    if first_launch.get("reportPath") == second_launch.get("reportPath"):
        failures.append("launches must use distinct report paths")
    if first_launch.get("sgfPath") != str(sgf_path) or second_launch.get("sgfPath") != str(sgf_path):
        failures.append("both launches must use the same SGF path")
    first_stopped_at = first_launch.get("stoppedAtUnix")
    second_started_at = second_launch.get("startedAtUnix")
    if isinstance(first_stopped_at, (int, float)) and isinstance(second_started_at, (int, float)):
        if first_stopped_at > second_started_at:
            failures.append("first launch must stop before second launch starts")
    else:
        failures.append("launch evidence must include stop/start timing")
    return failures


def build_combined_evidence(first_launch: dict[str, Any], second_launch: dict[str, Any]) -> dict[str, Any]:
    first_report = first_launch.get("report")
    second_report = second_launch.get("report")
    compatible_report = first_report if isinstance(first_report, dict) else {}
    evidence = copy.deepcopy(compatible_report)
    evidence["name"] = "ui_tauri_runtime_smoke_save_reopen"
    evidence["firstLaunch"] = first_launch
    evidence["secondLaunch"] = second_launch
    evidence["saveReopenProof"] = {
        "firstPhase": first_launch.get("phase"),
        "secondPhase": second_launch.get("phase"),
        "sameSgfPath": first_launch.get("sgfPath") == second_launch.get("sgfPath"),
        "distinctProcesses": first_launch.get("pid") != second_launch.get("pid"),
        "firstStoppedBeforeSecondStarted": (
            isinstance(first_launch.get("stoppedAtUnix"), (int, float))
            and isinstance(second_launch.get("startedAtUnix"), (int, float))
            and first_launch["stoppedAtUnix"] <= second_launch["startedAtUnix"]
        ),
    }
    enrich_save_readback_check(evidence, second_launch)
    evidence["status"] = "pass"
    return evidence


def enrich_save_readback_check(evidence: dict[str, Any], second_launch: dict[str, Any]) -> None:
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        return
    second_report = second_launch.get("report")
    second_checks = second_report.get("checks") if isinstance(second_report, dict) else None
    reopen_details: dict[str, Any] = {}
    if isinstance(second_checks, list):
        reopen_check = next(
            (
                check
                for check in second_checks
                if isinstance(check, dict) and check.get("name") == "reopen_state_verified"
            ),
            None,
        )
        maybe_details = check_evidence(reopen_check)
        if isinstance(maybe_details, dict):
            reopen_details = maybe_details
    for check in checks:
        if not isinstance(check, dict) or check.get("name") != "save_readback_roundtrip":
            continue
        details = check_evidence(check)
        if details is None:
            details = {}
            check["details"] = details
        details["secondLaunch"] = {
            "launchIndex": 2,
            "status": "pass",
            "phase": second_launch.get("phase"),
            "pid": second_launch.get("pid"),
            "stopped": second_launch.get("stopped"),
            "reportPath": second_launch.get("reportPath"),
        }
        details["reopen"] = {
            "path": second_launch.get("sgfPath"),
            "status": "pass",
            "matchesSaved": True,
            "secondLaunch": True,
        }
        details["afterReopen"] = {
            "treeOrderVerified": reopen_details.get("treeOrderVerified") is True,
            "commentsVerified": reopen_details.get("commentsVerified") is True,
            "propertiesVerified": reopen_details.get("propertiesVerified") is True,
            "annotationsVerified": reopen_details.get("annotationsVerified") is True,
            "moveCountVerified": reopen_details.get("moveCountVerified") is True,
            "boardStateVerified": reopen_details.get("boardStateVerified") is True,
            "deletedTargetAbsent": reopen_details.get("absentAfterReopen") is True,
        }
        return


def print_failure_paths(temp_dir: Path, paths: list[Path]) -> None:
    print(f"failure artifacts retained in: {temp_dir}", file=sys.stderr)
    for path in paths:
        suffix = "" if path.exists() else " (missing)"
        print(f"artifact: {path}{suffix}", file=sys.stderr)


def run(root: Path, *, timeout_seconds: float, evidence_out: Path | None) -> int:
    root = root.resolve()
    if platform.system() != "Darwin":
        print("Tauri runtime UI smoke is currently a macOS local evidence gate.", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2

    temp_dir = Path(tempfile.mkdtemp(prefix="lizzieyzy-runtime-smoke-"))
    keep_temp_dir = True
    try:
        sgf_path = temp_dir / "runtime-smoke.sgf"
        first_report_path = temp_dir / "runtime-smoke-report-a.json"
        second_report_path = temp_dir / "runtime-smoke-report-b.json"
        first_log_path = temp_dir / "tauri-dev-a.log"
        second_log_path = temp_dir / "tauri-dev-b.log"
        write_runtime_sgf(sgf_path)

        try:
            first_launch = launch_runtime_smoke(
                root,
                phase="edit-save",
                sgf_path=sgf_path,
                report_path=first_report_path,
                log_path=first_log_path,
                timeout_seconds=timeout_seconds,
            )
            first_report = first_launch.get("report")
            failures = validate_report(first_report)
            if failures:
                raise SmokeError("first launch report invalid: " + "; ".join(failures))

            second_launch = launch_runtime_smoke(
                root,
                phase="reopen-verify",
                sgf_path=sgf_path,
                report_path=second_report_path,
                log_path=second_log_path,
                expected_report_path=first_report_path,
                timeout_seconds=timeout_seconds,
            )
            second_report = second_launch.get("report")
            failures = validate_reopen_report(second_report)
            if failures:
                raise SmokeError("second launch report invalid: " + "; ".join(failures))
            failures = validate_save_reopen_proof(first_launch, second_launch, sgf_path)
            if failures:
                raise SmokeError("save/reopen proof invalid: " + "; ".join(failures))

            evidence = build_combined_evidence(first_launch, second_launch)
            if evidence_out is not None:
                write_evidence(evidence_out, evidence, root=root, temp_dir=temp_dir)
            print(
                f"PASS Tauri runtime UI smoke: {len(REQUIRED_CHECKS)} required checks passed; "
                "save/reopen verified across two Tauri launches"
            )
            keep_temp_dir = False
            return 0
        except SmokeError as exc:
            print(f"FAIL Tauri runtime UI smoke: {exc}", file=sys.stderr)
            print_failure_paths(temp_dir, [first_report_path, second_report_path, first_log_path, second_log_path])
            return 1
    finally:
        if not keep_temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the macOS Tauri runtime UI smoke and validate its JSON report.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for the runtime report")
    parser.add_argument("--evidence-out", type=Path, help="write sanitized PASS evidence JSON to this path")
    args = parser.parse_args(argv)
    return run(args.root, timeout_seconds=args.timeout, evidence_out=args.evidence_out)


if __name__ == "__main__":
    raise SystemExit(main())
