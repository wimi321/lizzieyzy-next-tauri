from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_tauri_provider_live.py"
SPEC = importlib.util.spec_from_file_location("smoke_tauri_provider_live", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_tauri_provider_live = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_tauri_provider_live"] = smoke_tauri_provider_live
SPEC.loader.exec_module(smoke_tauri_provider_live)

USER_FLOWS_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_user_flows.py"
USER_FLOWS_SPEC = importlib.util.spec_from_file_location("smoke_user_flows", USER_FLOWS_SCRIPT)
assert USER_FLOWS_SPEC is not None and USER_FLOWS_SPEC.loader is not None
smoke_user_flows = importlib.util.module_from_spec(USER_FLOWS_SPEC)
sys.modules["smoke_user_flows"] = smoke_user_flows
USER_FLOWS_SPEC.loader.exec_module(smoke_user_flows)


class FakeProcess:
    returncode = None

    def __init__(self, pid: int = 12345) -> None:
        self.pid = pid

    def poll(self) -> int | None:
        return self.returncode


class FakeServer:
    base_url = "http://127.0.0.1:39091"

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def snapshot(self) -> list[dict[str, object]]:
        return valid_requests()


class SmokeTauriProviderLiveTests(unittest.TestCase):
    def test_validate_report_accepts_required_pass_checks(self) -> None:
        self.assertEqual([], smoke_tauri_provider_live.validate_report(valid_report()))

    def test_validate_report_rejects_non_tauri_runtime(self) -> None:
        report = valid_report()
        find_check(report, "runtime_started")["details"]["tauriInternals"] = False

        failures = smoke_tauri_provider_live.validate_report(report)

        self.assertIn("runtime_started must confirm real Tauri runtime", failures)

    def test_validate_report_rejects_missing_controlled_network_observation(self) -> None:
        report = valid_report()
        find_check(report, "controlled_network_observed")["details"]["foxRequestObserved"] = False

        failures = smoke_tauri_provider_live.validate_report(report)

        self.assertIn("controlled_network_observed must report foxRequestObserved true", failures)

    def test_build_evidence_requires_provider_live_raw_report(self) -> None:
        raw = valid_raw_tauri_report()
        raw["phase"] = "readboard-live"

        with self.assertRaises(smoke_tauri_provider_live.SmokeError) as caught:
            smoke_tauri_provider_live.build_evidence(
                raw,
                base_url="http://127.0.0.1:1",
                requests=valid_requests(),
                timeout_seconds=1.0,
            )

        self.assertIn("phase must be provider-live", str(caught.exception))

    def test_build_evidence_merges_server_request_observations(self) -> None:
        evidence = smoke_tauri_provider_live.build_evidence(
            valid_raw_tauri_report(),
            base_url="http://127.0.0.1:39091",
            requests=valid_requests(),
            timeout_seconds=1.5,
        )

        self.assertEqual("lizzieyzy.provider-live-smoke.v1", evidence["schema"])
        self.assertEqual("provider-live", evidence["phase"])
        self.assertEqual([], smoke_tauri_provider_live.validate_report(evidence))
        controlled = find_check(evidence, "controlled_network_observed")["details"]
        self.assertTrue(controlled["yikeSignedHeadersObserved"])
        self.assertEqual(3, controlled["requestCount"])

    def test_build_evidence_matches_smoke_user_flows_validator(self) -> None:
        evidence = smoke_tauri_provider_live.build_evidence(
            valid_raw_tauri_report(),
            base_url="http://127.0.0.1:39091",
            requests=valid_requests(),
            timeout_seconds=1.5,
        )

        self.assertEqual([], smoke_user_flows.validate_provider_live_smoke_evidence(evidence))

    def test_controlled_server_serves_provider_payloads_and_logs_requests(self) -> None:
        server = smoke_tauri_provider_live.ControlledProviderServer()
        server.start()
        try:
            yike = json.loads(read_url(f"{server.base_url}/v2/golive/list?p=1&since=0&official=&version=2"))
            bad_payload = read_url(f"{server.base_url}/v2/golive/list?mode=bad_payload")
            fox = read_url(f"{server.base_url}/fox/direct-sgf")
            with self.assertRaises(urllib.error.HTTPError):
                read_url(f"{server.base_url}/missing")
        finally:
            server.stop()

        self.assertEqual(1200, yike["Status"])
        self.assertEqual(1, len(yike["Result"]["list"]))
        self.assertEqual("{", bad_payload)
        self.assertIn(";B[dd];W[pp]", fox)
        paths = [request["path"] for request in server.snapshot()]
        self.assertIn("/v2/golive/list", paths)
        self.assertIn("/fox/direct-sgf", paths)

    def test_run_writes_sanitized_evidence_after_valid_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            evidence_out = Path(tmp) / "evidence.json"
            process = FakeProcess()

            with (
                patch.object(smoke_tauri_provider_live.platform, "system", return_value="Darwin"),
                patch.object(smoke_tauri_provider_live, "ControlledProviderServer", return_value=FakeServer()),
                patch.object(smoke_tauri_provider_live, "start_tauri", return_value=process),
                patch.object(smoke_tauri_provider_live, "wait_for_report", return_value=valid_raw_tauri_report(str(root))),
                patch.object(smoke_tauri_provider_live, "stop_process") as stop_process,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                exit_code = smoke_tauri_provider_live.run(
                    root,
                    timeout_seconds=0.1,
                    evidence_out=evidence_out,
                )

            self.assertEqual(0, exit_code)
            stop_process.assert_called_once_with(process)
            written_text = evidence_out.read_text(encoding="utf-8")
            self.assertNotIn(str(root), written_text)
            written = json.loads(written_text)
            self.assertEqual("pass", written["status"])
            self.assertEqual([], smoke_tauri_provider_live.validate_report(written))


def read_url(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def valid_report() -> dict[str, object]:
    return {
        "schema": smoke_tauri_provider_live.SCHEMA,
        "name": "provider_live_smoke",
        "status": "pass",
        "platform": "macos",
        "phase": "provider-live",
        "checks": valid_checks(),
    }


def valid_raw_tauri_report(root: str = "/repo") -> dict[str, object]:
    return {
        "schema": smoke_tauri_provider_live.TAURI_RUNTIME_SCHEMA,
        "name": "ui_tauri_runtime_smoke",
        "status": "pass",
        "platform": "macos",
        "phase": "provider-live",
        "startedAt": "2026-05-12T00:00:00Z",
        "finishedAt": "2026-05-12T00:00:01Z",
        "checks": valid_checks(root),
    }


def valid_checks(root: str = "/repo") -> list[dict[str, object]]:
    base = f"{root}/controlled-provider"
    return [
        {
            "name": "runtime_started",
            "status": "pass",
            "details": {"tauriInternals": True, "platform": "MacIntel"},
        },
        {
            "name": "yike_controlled_fetch",
            "status": "pass",
            "details": {
                "provider": "yike",
                "networkMode": "controlled_network",
                "httpStatus": 200,
                "payloadValidated": True,
                "resultCount": 1,
                "fixtureParserOnly": False,
            },
        },
        {
            "name": "fox_controlled_fetch",
            "status": "pass",
            "details": {
                "provider": "fox",
                "networkMode": "controlled_network",
                "httpStatus": 200,
                "payloadImported": True,
                "moveCount": 2,
                "directHttpWarning": True,
            },
        },
        {
            "name": "provider_failure_modes",
            "status": "pass",
            "details": {
                "observed": True,
                "typedProviderError": True,
                "errorKind": "invalid_payload",
                "message": "failed to parse Yike live list JSON",
                "reportedAsSuccess": False,
            },
        },
        {
            "name": "controlled_network_observed",
            "status": "pass",
            "details": {
                "controlledHttpServer": True,
                "requestCount": 3,
                "foxRequestObserved": True,
                "failureRequestObserved": True,
                "yikeSignedHeadersObserved": True,
                "requests": [
                    {"method": "GET", "path": "/v2/golive/list", "query": "p=1", "bodyBytes": 0, "headerNames": ["appkey"]},
                    {"method": "GET", "path": "/fox/direct-sgf", "query": "", "bodyBytes": 0, "headerNames": []},
                    {"method": "GET", "path": "/v2/golive/list", "query": "mode=bad_payload", "bodyBytes": 0, "headerNames": ["appkey"]},
                ],
            },
        },
        {
            "name": "offline_not_counted_as_external_live",
            "status": "pass",
            "details": scope_details(),
        },
        {
            "name": "external_account_scope",
            "status": "pass",
            "details": scope_details(),
        },
    ]


def scope_details() -> dict[str, object]:
    return {
        "offlineParserOnly": False,
        "externalProviderServiceCovered": False,
        "realAccountLoginStateCovered": False,
        "antiBotStabilityCovered": False,
        "controlledHttpServer": True,
        "serviceSchemaDriftCovered": False,
    }


def valid_requests() -> list[dict[str, object]]:
    headers = {
        "appkey": "k",
        "curtime": "1",
        "nonce": "2",
        "checksum": "s",
        "accesstoken": "t",
    }
    return [
        {"method": "GET", "path": "/v2/golive/list", "query": "p=1&since=0&official=&version=2", "headers": headers, "bodyBytes": 0},
        {"method": "GET", "path": "/fox/direct-sgf", "query": "", "headers": {"user-agent": "ua"}, "bodyBytes": 0},
        {"method": "GET", "path": "/v2/golive/list", "query": "mode=bad_payload", "headers": headers, "bodyBytes": 0},
    ]


def find_check(report: dict[str, object], name: str) -> dict[str, object]:
    checks = report["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check.get("name") == name:
            return check
    raise AssertionError(f"missing check {name}")


if __name__ == "__main__":
    unittest.main()
