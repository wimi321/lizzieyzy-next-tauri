#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.provider-live-smoke.v1"
TAURI_RUNTIME_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
REQUIRED_CHECKS = [
    "runtime_started",
    "yike_controlled_fetch",
    "fox_controlled_fetch",
    "provider_failure_modes",
    "controlled_network_observed",
    "offline_not_counted_as_external_live",
    "external_account_scope",
]
FOX_DIRECT_SGF = "(;GM[1]FF[4]SZ[19]KM[6.5]PB[Black]PW[White];B[dd];W[pp])\n"


class SmokeError(RuntimeError):
    pass


class ControlledProviderServer:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self.requests]

    def _record(self, handler: BaseHTTPRequestHandler, body_bytes: int = 0) -> None:
        parsed = urlparse(handler.path)
        headers = {key.lower(): value for key, value in handler.headers.items()}
        with self._lock:
            self.requests.append(
                {
                    "method": handler.command,
                    "path": parsed.path,
                    "query": parsed.query,
                    "headers": headers,
                    "bodyBytes": body_bytes,
                }
            )

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner._record(self)
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if parsed.path == "/v2/golive/list" and query.get("mode") == ["bad_payload"]:
                    self._send(200, b"{", "application/json")
                    return
                if parsed.path == "/v2/golive/list":
                    self._send_json(yike_list_payload())
                    return
                if parsed.path == "/fox/direct-sgf":
                    self._send(200, FOX_DIRECT_SGF.encode("utf-8"), "application/x-go-sgf; charset=utf-8")
                    return
                self._send(404, b"not found", "text/plain; charset=utf-8")

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _send_json(self, payload: dict[str, Any]) -> None:
                self._send(200, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

            def _send(self, status: int, payload: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler


def yike_list_payload() -> dict[str, Any]:
    return {
        "Status": 1200,
        "Result": {
            "since": 42,
            "list": [
                {
                    "Id": 186031,
                    "Version": 2,
                    "hall": 7,
                    "room": 9,
                    "Status": 3,
                    "GameName": "Controlled provider smoke",
                    "BlackName": "Black",
                    "WhiteName": "White",
                    "BlackCounty": "CN",
                    "WhiteCounty": "JP",
                    "GameDate": "2026-05-12",
                    "BroadcastTime": "09:00",
                    "FinishOrder": "",
                    "GameResult": "B+R",
                    "LiveMember": "runner",
                    "HandsCount": 123,
                    "PersonTimes": 4567,
                    "TopFlag": 1,
                    "RealtimeAnalysisFlag": 1,
                    "BlackWinRate": 64.25,
                    "Delta": 1.04,
                }
            ],
        },
    }


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"report was not created: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"report is invalid JSON at line {exc.lineno}: {exc.msg}") from exc


def check_evidence(check: Any) -> dict[str, Any] | None:
    if not isinstance(check, dict):
        return None
    value = check.get("details")
    return value if isinstance(value, dict) else None


def runtime_check(raw_report: dict[str, Any], name: str) -> dict[str, Any]:
    checks = raw_report.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict) and check.get("name") == name:
                return check
    return {"name": name, "status": "fail", "details": {"missing": True}}


def normalize_runtime_check(raw_report: dict[str, Any], name: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = runtime_check(raw_report, name)
    normalized: dict[str, Any] = {
        "name": name,
        "status": str(raw.get("status", "")).lower() or "fail",
        "details": details if details is not None else (check_evidence(raw) or {}),
    }
    if isinstance(raw.get("error"), str):
        normalized["error"] = raw["error"]
    return normalized


def validate_raw_tauri_report(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["raw Tauri report root must be an object"]
    failures: list[str] = []
    if report.get("schema") != TAURI_RUNTIME_SCHEMA:
        failures.append(f"raw Tauri report schema must be {TAURI_RUNTIME_SCHEMA}")
    if report.get("phase") != "provider-live":
        failures.append("raw Tauri report phase must be provider-live")
    if str(report.get("status", "")).lower() != "pass":
        failures.append("raw Tauri report status must be pass")
    return failures


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
    check_by_name = {check.get("name"): check for check in checks if isinstance(check, dict)}
    missing = [name for name in REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_runtime_started(check_by_name.get("runtime_started")))
    failures.extend(validate_yike_fetch(check_by_name.get("yike_controlled_fetch")))
    failures.extend(validate_fox_fetch(check_by_name.get("fox_controlled_fetch")))
    failures.extend(validate_failure_modes(check_by_name.get("provider_failure_modes")))
    failures.extend(validate_controlled_network(check_by_name.get("controlled_network_observed")))
    failures.extend(validate_scope(check_by_name.get("offline_not_counted_as_external_live"), "offline_not_counted_as_external_live"))
    failures.extend(validate_scope(check_by_name.get("external_account_scope"), "external_account_scope"))
    return failures


def validate_runtime_started(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["runtime_started evidence must be an object"]
    return [] if evidence.get("tauriInternals") is True else ["runtime_started must confirm real Tauri runtime"]


def validate_yike_fetch(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["yike_controlled_fetch evidence must be an object"]
    failures: list[str] = []
    if evidence.get("provider") != "yike":
        failures.append("yike_controlled_fetch must report provider yike")
    if evidence.get("networkMode") != "controlled_network":
        failures.append("yike_controlled_fetch.networkMode must be controlled_network")
    if not http_success(evidence.get("httpStatus")):
        failures.append("yike_controlled_fetch must report 2xx/3xx httpStatus")
    if evidence.get("payloadValidated") is not True:
        failures.append("yike_controlled_fetch.payloadValidated must be true")
    result_count = evidence.get("resultCount")
    if not isinstance(result_count, (int, float)) or result_count < 0:
        failures.append("yike_controlled_fetch.resultCount must be non-negative")
    if evidence.get("fixtureParserOnly") is not False:
        failures.append("yike_controlled_fetch.fixtureParserOnly must be false")
    return failures


def validate_fox_fetch(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["fox_controlled_fetch evidence must be an object"]
    failures: list[str] = []
    if evidence.get("provider") != "fox":
        failures.append("fox_controlled_fetch must report provider fox")
    if evidence.get("networkMode") != "controlled_network":
        failures.append("fox_controlled_fetch.networkMode must be controlled_network")
    if not http_success(evidence.get("httpStatus")):
        failures.append("fox_controlled_fetch must report 2xx/3xx httpStatus")
    if evidence.get("payloadImported") is not True:
        failures.append("fox_controlled_fetch.payloadImported must be true")
    if not positive_int(evidence.get("moveCount")):
        failures.append("fox_controlled_fetch must import move_count > 0")
    if evidence.get("directHttpWarning") is not True:
        failures.append("fox_controlled_fetch.directHttpWarning must be true")
    return failures


def validate_failure_modes(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["provider_failure_modes evidence must be an object"]
    failures: list[str] = []
    if evidence.get("observed") is not True:
        failures.append("provider_failure_modes must report observed true")
    if evidence.get("typedProviderError") is not True:
        failures.append("provider_failure_modes.typedProviderError must be true")
    if not isinstance(evidence.get("errorKind"), str) or not evidence.get("errorKind"):
        failures.append("provider_failure_modes.errorKind must be non-empty")
    if not isinstance(evidence.get("message"), str) or not evidence.get("message"):
        failures.append("provider_failure_modes.message must be non-empty")
    if evidence.get("reportedAsSuccess") is not False:
        failures.append("provider_failure_modes.reportedAsSuccess must be false")
    return failures


def validate_controlled_network(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["controlled_network_observed evidence must be an object"]
    failures: list[str] = []
    request_count = evidence.get("requestCount")
    if not isinstance(request_count, (int, float)) or request_count < 3:
        failures.append("controlled_network_observed.requestCount must be at least 3")
    for key in ("controlledHttpServer", "foxRequestObserved", "failureRequestObserved", "yikeSignedHeadersObserved"):
        if evidence.get(key) is not True:
            failures.append(f"controlled_network_observed must report {key} true")
    return failures


def validate_scope(check: Any, name: str) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return [f"{name} evidence must be an object"]
    failures: list[str] = []
    if name == "offline_not_counted_as_external_live":
        if evidence.get("offlineParserOnly") is not False:
            failures.append(f"{name}.offlineParserOnly must be false")
        if evidence.get("controlledHttpServer") is not True:
            failures.append(f"{name}.controlledHttpServer must be true")
        if evidence.get("externalProviderServiceCovered") is not False:
            failures.append(f"{name}.externalProviderServiceCovered must be false")
    if name == "external_account_scope":
        for key in ("realAccountLoginStateCovered", "antiBotStabilityCovered", "serviceSchemaDriftCovered"):
            if evidence.get(key) is not False:
                failures.append(f"{name}.{key} must be false")
    return failures


def http_success(value: Any) -> bool:
    return isinstance(value, int) and 200 <= value < 400


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def request_log_details(requests: list[dict[str, Any]]) -> dict[str, Any]:
    yike_requests = [request for request in requests if request.get("path") == "/v2/golive/list" and "mode=bad_payload" not in str(request.get("query", ""))]
    failure_requests = [request for request in requests if request.get("path") == "/v2/golive/list" and "mode=bad_payload" in str(request.get("query", ""))]
    fox_requests = [request for request in requests if request.get("path") == "/fox/direct-sgf"]
    return {
        "controlledHttpServer": True,
        "requestCount": len(requests),
        "foxRequestObserved": bool(fox_requests),
        "failureRequestObserved": bool(failure_requests),
        "yikeSignedHeadersObserved": any(has_yike_signed_headers(request) for request in yike_requests + failure_requests),
        "requests": [sanitize_request_log_item(request) for request in requests],
    }


def has_yike_signed_headers(request: dict[str, Any]) -> bool:
    headers = request.get("headers")
    if not isinstance(headers, dict):
        return False
    return all(key in headers for key in ("appkey", "curtime", "nonce", "checksum", "accesstoken"))


def sanitize_request_log_item(request: dict[str, Any]) -> dict[str, Any]:
    headers = request.get("headers") if isinstance(request.get("headers"), dict) else {}
    assert isinstance(headers, dict)
    return {
        "method": request.get("method"),
        "path": request.get("path"),
        "query": request.get("query"),
        "bodyBytes": request.get("bodyBytes"),
        "headerNames": sorted(headers.keys()),
    }


def build_evidence(raw_report: Any, *, base_url: str, requests: list[dict[str, Any]], timeout_seconds: float) -> dict[str, Any]:
    if not isinstance(raw_report, dict):
        raise SmokeError("raw Tauri report root must be an object")
    raw_failures = validate_raw_tauri_report(raw_report)
    if raw_failures:
        raise SmokeError("; ".join(raw_failures))
    controlled_details = {
        **(check_evidence(runtime_check(raw_report, "controlled_network_observed")) or {}),
        **request_log_details(requests),
    }
    checks = [
        normalize_runtime_check(raw_report, "runtime_started"),
        normalize_runtime_check(raw_report, "yike_controlled_fetch"),
        normalize_runtime_check(raw_report, "fox_controlled_fetch"),
        normalize_runtime_check(raw_report, "provider_failure_modes"),
        normalize_runtime_check(raw_report, "controlled_network_observed", controlled_details),
        normalize_runtime_check(raw_report, "offline_not_counted_as_external_live"),
        normalize_runtime_check(raw_report, "external_account_scope"),
    ]
    return {
        "schema": SCHEMA,
        "name": "provider_live_smoke",
        "status": "pass",
        "platform": "macos" if platform.system() == "Darwin" else platform.system().lower(),
        "phase": "provider-live",
        "baseUrl": base_url,
        "timeoutSeconds": timeout_seconds,
        "runtimeReport": {
            "schema": raw_report.get("schema"),
            "phase": raw_report.get("phase"),
            "status": raw_report.get("status"),
            "startedAt": raw_report.get("startedAt"),
            "finishedAt": raw_report.get("finishedAt"),
        },
        "checks": checks,
    }


def write_smoke_sgf(path: Path) -> None:
    path.write_text("(;FF[4]GM[1]SZ[19]C[provider runtime smoke])\n", encoding="utf-8")


def start_tauri(
    root: Path,
    sgf_path: Path,
    report_path: Path,
    log_path: Path,
    work_dir: Path,
    *,
    base_url: str,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "VITE_LIZZIEYZY_RUNTIME_SMOKE": "1",
            "LIZZIEYZY_RUNTIME_SMOKE": "1",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE": "provider-live",
            "LIZZIEYZY_RUNTIME_SMOKE_PHASE": "provider-live",
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH": str(sgf_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH": str(report_path),
            "VITE_LIZZIEYZY_RUNTIME_SMOKE_PROVIDER_BASE_URL": base_url,
            "TAURI_LIZZIEYZY_RUNTIME_SMOKE_PROVIDER_BASE_URL": base_url,
        }
    )
    config_path = work_dir / "tauri-provider-live-override.json"
    config_path.write_text(json.dumps({"build": {"beforeDevCommand": ""}}), encoding="utf-8")
    log_file = log_path.open("wb")
    try:
        command = (
            'npm --prefix "$1/apps/desktop" run dev & '
            'vite_pid=$!; '
            'trap "kill $vite_pid 2>/dev/null || true" EXIT INT TERM; '
            'for i in $(seq 1 100); do '
            'curl -fsS http://127.0.0.1:1420 >/dev/null 2>&1 && break; '
            'sleep 0.2; '
            'done; '
            'cd "$1/apps/desktop" && npx tauri dev --no-dev-server-wait --no-watch -c "$2"'
        )
        process = subprocess.Popen(
            ["sh", "-c", command, "provider-runtime-smoke", str(root), str(config_path)],
            cwd=work_dir,
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
    raise SmokeError(f"timed out after {timeout_seconds:g}s waiting for Tauri provider runtime report")


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


def write_evidence(path: Path, report: Any, *, root: Path, temp_dir: Path) -> None:
    replacements = [
        (str(root.resolve()), "<repo>"),
        (str(temp_dir.resolve()), "<tmp>"),
    ]
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_evidence(report, replacements), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(root: Path, *, timeout_seconds: float, evidence_out: Path | None) -> int:
    root = root.resolve()
    if platform.system() != "Darwin":
        print("Tauri provider runtime smoke is currently a macOS local evidence gate.", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2

    temp_dir = Path(tempfile.mkdtemp(prefix="lizzieyzy-tauri-provider-smoke-"))
    keep_temp_dir = True
    server = ControlledProviderServer()
    server.start()
    try:
        sgf_path = temp_dir / "provider-smoke.sgf"
        report_path = temp_dir / "provider-tauri-runtime-report.json"
        log_path = temp_dir / "tauri-dev.log"
        work_dir = temp_dir / "work"
        work_dir.mkdir()
        write_smoke_sgf(sgf_path)
        process = start_tauri(root, sgf_path, report_path, log_path, work_dir, base_url=server.base_url)
        try:
            raw_report = wait_for_report(report_path, process, timeout_seconds=timeout_seconds)
            report = build_evidence(raw_report, base_url=server.base_url, requests=server.snapshot(), timeout_seconds=timeout_seconds)
            failures = validate_report(report)
            if failures:
                raise SmokeError("; ".join(failures))
            if evidence_out is not None:
                write_evidence(evidence_out, report, root=root, temp_dir=temp_dir)
            print(f"PASS Tauri provider runtime smoke: {len(REQUIRED_CHECKS)} required checks passed")
            keep_temp_dir = False
            return 0
        except SmokeError as exc:
            print(f"FAIL Tauri provider runtime smoke: {exc}", file=sys.stderr)
            print(f"failure artifacts retained in: {temp_dir}", file=sys.stderr)
            if report_path.is_file():
                print(f"runtime report: {report_path}", file=sys.stderr)
            if log_path.is_file():
                print(f"tauri:dev log: {log_path}", file=sys.stderr)
            return 1
        finally:
            stop_process(process)
            if not keep_temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
    finally:
        server.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the macOS Tauri runtime provider controlled-network smoke.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for the runtime report")
    parser.add_argument("--evidence-out", type=Path, default=ROOT / "docs/qa/provider-live-smoke-macos.json")
    args = parser.parse_args(argv)
    return run(args.root, timeout_seconds=args.timeout, evidence_out=args.evidence_out)


if __name__ == "__main__":
    raise SystemExit(main())
