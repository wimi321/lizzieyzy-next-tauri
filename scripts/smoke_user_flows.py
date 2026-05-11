#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[1]

Status = Literal["PASS", "FAIL", "PENDING"]

GOLDEN_SGF_FIXTURES = [
    "tests/golden/basic_19x19.sgf",
    "tests/golden/sgf_compat_variations.sgf",
    "tests/golden/sgf_ff4_compat.sgf",
    "tests/golden/sgf_reorder_variations.sgf",
]
COMPAT_FIXTURE = "tests/golden/sgf_ff4_compat.sgf"
REORDER_FIXTURE = "tests/golden/sgf_reorder_variations.sgf"
ROOT_PACKAGE_SCRIPTS = ["desktop:dev", "desktop:build", "desktop:tauri-build", "validate"]
DESKTOP_PACKAGE_SCRIPTS = ["dev", "build", "preview", "tauri:dev", "tauri:build"]
TAURI_RUNTIME_UI_SMOKE_EVIDENCE = "docs/qa/tauri-runtime-ui-smoke-macos.json"
TAURI_RUNTIME_UI_SMOKE_SCHEMA = "lizzieyzy.tauri-runtime-ui-smoke.v1"
TAURI_RUNTIME_UI_SMOKE_REQUIRED_CHECKS = [
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
KATAGO_LIVE_SMOKE_EVIDENCE = "docs/qa/katago-live-smoke-macos.json"
KATAGO_LIVE_SMOKE_SCHEMA = "lizzieyzy.katago-live-smoke.v1"
KATAGO_LIVE_SMOKE_REQUIRED_CHECKS = [
    "engine_assets",
    "version_probe",
    "one_position_analysis",
    "batch_analysis",
    "stderr_capture",
]
KATAGO_TAURI_RUNTIME_SMOKE_EVIDENCE = "docs/qa/katago-tauri-runtime-smoke-macos.json"
KATAGO_TAURI_RUNTIME_SMOKE_SCHEMA = "lizzieyzy.katago-tauri-runtime-smoke.v1"
KATAGO_TAURI_RUNTIME_SMOKE_REQUIRED_CHECKS = [
    "runtime_started",
    "katago_failure_mode_missing_assets",
    "katago_assets",
    "katago_analyze_once",
    "katago_analyze_game",
    "katago_start_cancel",
]
READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE = "docs/qa/readboard-tauri-runtime-smoke-macos.json"
READBOARD_TAURI_RUNTIME_SMOKE_SCHEMA = "lizzieyzy.readboard-tauri-runtime-smoke.v1"
READBOARD_TAURI_RUNTIME_SMOKE_REQUIRED_CHECKS = [
    "runtime_started",
    "sidecar_probe_ready",
    "sidecar_probe_unavailable",
    "protocol_line_sync",
    "target_state_change_sync",
    "unsupported_ocr_path",
    "external_client_not_covered",
]
PROVIDER_LIVE_SMOKE_EVIDENCE = "docs/qa/provider-live-smoke-macos.json"
PROVIDER_LIVE_SMOKE_SCHEMA = "lizzieyzy.provider-live-smoke.v1"
PROVIDER_LIVE_SMOKE_REQUIRED_CHECKS = [
    "runtime_started",
    "yike_controlled_fetch",
    "fox_controlled_fetch",
    "provider_failure_modes",
    "controlled_network_observed",
    "offline_not_counted_as_external_live",
    "external_account_scope",
]
TAURI_COMMANDS = [
    "update_sgf_node_comment",
    "append_sgf_move",
    "delete_sgf_node",
]
TAURI_COMMAND_GROUPS = {
    "tauri_sgf_properties_command": ["update_sgf_node_properties"],
    "tauri_sgf_reorder_command": ["reorder_sgf_variation"],
    "tauri_sgf_existing_move_edit_command": ["edit_sgf_move"],
    "tauri_sgf_file_commands": ["read_sgf_file", "write_sgf_file"],
    "tauri_preferences_commands": ["load_app_preferences", "save_app_preferences"],
    "tauri_engine_profile_commands": [
        "load_engine_profiles_settings",
        "save_engine_profiles_settings",
    ],
    "tauri_engine_asset_command": ["engine_asset_checks"],
    "tauri_katago_job_commands": ["katago_start_analyze_game", "katago_cancel_analysis"],
    "tauri_analysis_cache_commands": [
        "get_analysis_cache",
        "save_analysis_cache",
        "delete_analysis_cache",
    ],
    "tauri_readboard_sidecar_commands": [
        "readboard_sidecar_probe",
        "readboard_sidecar_sync_snapshot",
    ],
    "tauri_provider_fetch_commands": ["provider_fetch_yike", "provider_fetch_fox"],
    "tauri_legacy_config_migration_commands": [
        "preview_legacy_config_migration",
        "apply_legacy_config_migration",
    ],
    "tauri_runtime_asset_layout_commands": [
        "resolve_runtime_asset_layout",
        "validate_runtime_asset_layout",
    ],
}
LEGACY_SHELL_SOURCE = "apps/desktop/src/components/LegacyShell.tsx"
APP_SOURCE = "apps/desktop/src/App.tsx"
BACKEND_SOURCE = "apps/desktop/src/api/backend.ts"
SGF_TREE_PANEL_SOURCE = "apps/desktop/src/components/SgfTreePanel.tsx"
LEGACY_SHELL_MENU_SURFACE = {
    "View": ["Candidates", "Ownership", "Policy"],
    "Engine": ["Profiles", "Assets"],
    "Tools": ["Providers", "Preferences"],
    "Help": ["Backend status"],
}


@dataclass
class SmokeResult:
    name: str
    status: Status
    detail: str

    @property
    def ok(self) -> bool:
        return self.status != "FAIL"


class UserFlowSmoke:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.results: list[SmokeResult] = []

    def pass_(self, name: str, detail: str) -> None:
        self.results.append(SmokeResult(name, "PASS", detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append(SmokeResult(name, "FAIL", detail))

    def pending(self, name: str, detail: str) -> None:
        self.results.append(SmokeResult(name, "PENDING", detail))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read_text(self, rel: str) -> str | None:
        try:
            return self.path(rel).read_text(encoding="utf-8")
        except FileNotFoundError:
            self.fail(f"file:{rel}", "file is missing")
        return None

    def load_json(self, rel: str) -> Any | None:
        try:
            return json.loads(self.path(rel).read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.fail(f"json:{rel}", "file is missing")
        except json.JSONDecodeError as exc:
            self.fail(f"json:{rel}", f"invalid JSON at line {exc.lineno}: {exc.msg}")
        return None

    def check_golden_sgf_fixtures(self) -> None:
        missing = [rel for rel in GOLDEN_SGF_FIXTURES if not self.path(rel).is_file()]
        empty = [
            rel
            for rel in GOLDEN_SGF_FIXTURES
            if self.path(rel).is_file() and not self.path(rel).read_text(encoding="utf-8").strip()
        ]
        if missing or empty:
            details: list[str] = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if empty:
                details.append("empty: " + ", ".join(empty))
            self.fail("golden_sgf_presence", "; ".join(details))
            return
        self.pass_("golden_sgf_presence", f"{len(GOLDEN_SGF_FIXTURES)} golden SGF fixtures are present")

    def check_sgf_compat_fixture(self) -> None:
        text = self.read_text(COMPAT_FIXTURE)
        if text is None:
            return
        required_tokens = {
            "FF[4]": "FF4 marker",
            "(;B[": "variation branch",
            "C[": "comments",
            "AB[": "black setup stones",
            "AW[": "white setup stones",
            "AE[": "empty setup stones",
            "PL[": "player-to-play setup",
            "LB[": "labels",
        }
        missing = [label for token, label in required_tokens.items() if token not in text]
        if missing:
            self.fail("sgf_compat_fixture", "fixture missing coverage tokens: " + ", ".join(missing))
            return
        self.pass_(
            "sgf_compat_fixture",
            f"{COMPAT_FIXTURE} includes variations, comments, setup properties, and labels",
        )

    def check_sgf_reorder_fixture(self) -> None:
        text = self.read_text(REORDER_FIXTURE)
        if text is None:
            return
        required_tokens = {
            "C[": "comments",
            "ZZ[": "unknown property",
            "LB[": "labels",
            "TR[": "annotations",
        }
        missing = [label for token, label in required_tokens.items() if token not in text]
        sibling_count = count_variation_children_at_depth(text, 1)
        subtree_count = count_variation_children_at_depth(text, 2)
        if sibling_count < 3:
            missing.append(f"3 sibling variations under one parent (found {sibling_count})")
        if subtree_count < 1:
            missing.append("nested subtree below a sibling variation")
        if missing:
            self.fail("sgf_reorder_fixture", "fixture missing reorder coverage: " + ", ".join(missing))
            return
        self.pass_(
            "sgf_reorder_fixture",
            f"{REORDER_FIXTURE} covers sibling variation reorder shape, comments, unknown properties, labels, annotations, and a subtree",
        )

    def check_package_scripts(self) -> None:
        root_package = self.load_json("package.json")
        desktop_package = self.load_json("apps/desktop/package.json")
        if not root_package or not desktop_package:
            return
        root_scripts = root_package.get("scripts", {})
        desktop_scripts = desktop_package.get("scripts", {})
        missing_root = [script for script in ROOT_PACKAGE_SCRIPTS if script not in root_scripts]
        missing_desktop = [script for script in DESKTOP_PACKAGE_SCRIPTS if script not in desktop_scripts]
        if missing_root or missing_desktop:
            details: list[str] = []
            if missing_root:
                details.append("package.json missing scripts: " + ", ".join(missing_root))
            if missing_desktop:
                details.append("apps/desktop/package.json missing scripts: " + ", ".join(missing_desktop))
            self.fail("package_scripts", "; ".join(details))
            return
        self.pass_("package_scripts", "root and desktop package scripts cover dev/build/Tauri entry points")

    def check_tauri_commands(self) -> None:
        text = self.read_text("apps/desktop/src-tauri/src/lib.rs")
        if text is None:
            return
        failures = missing_tauri_command_surface(text, TAURI_COMMANDS)
        if failures:
            self.fail("tauri_sgf_edit_commands", "missing command surface: " + ", ".join(failures))
        else:
            self.pass_(
                "tauri_sgf_edit_commands",
                "comment update, append move, and delete node commands are defined and registered",
            )

        for name, commands in TAURI_COMMAND_GROUPS.items():
            failures = missing_tauri_command_surface(text, commands)
            if failures:
                self.fail(name, "missing command surface: " + ", ".join(failures))
            else:
                self.pass_(name, ", ".join(commands) + " are defined and registered")

    def check_legacy_shell_menu_surface(self) -> None:
        text = self.read_text(LEGACY_SHELL_SOURCE)
        if text is None:
            return
        failures = missing_legacy_shell_menu_surface(text, LEGACY_SHELL_MENU_SURFACE)
        if failures:
            self.fail("legacy_shell_menu_surface", "; ".join(failures))
            return
        item_count = sum(len(items) for items in LEGACY_SHELL_MENU_SURFACE.values())
        self.pass_(
            "legacy_shell_menu_surface",
            f"LegacyShell exposes {item_count} View/Engine/Tools/Help menu entries as actionable, identifiable controls",
        )

    def check_native_sgf_save_readback_surface(self) -> None:
        backend_path = self.path(BACKEND_SOURCE)
        app_path = self.path(APP_SOURCE)
        if not backend_path.is_file() and not app_path.is_file():
            self.pending(
                "native_sgf_save_readback_surface",
                "source files absent in reduced fixture; full repository smoke must include App/backend save read-back refresh evidence",
            )
            return
        if not backend_path.is_file() or not app_path.is_file():
            missing = [rel for rel, path in ((BACKEND_SOURCE, backend_path), (APP_SOURCE, app_path)) if not path.is_file()]
            self.fail("native_sgf_save_readback_surface", "missing source file(s): " + ", ".join(missing))
            return
        backend_text = self.read_text(BACKEND_SOURCE)
        app_text = self.read_text(APP_SOURCE)
        if backend_text is None or app_text is None:
            return
        failures = [
            *missing_backend_sgf_save_readback_surface(backend_text),
            *missing_app_sgf_save_readback_refresh_surface(app_text),
        ]
        if failures:
            self.fail("native_sgf_save_readback_surface", "; ".join(failures))
            return
        self.pass_(
            "native_sgf_save_readback_surface",
            "saveSgfDocument writes through Tauri, reads the saved SGF back, and handleSaveSgfDocument reparses/replays/tree-syncs/cache-checks the read-back text",
        )

    def check_sgf_existing_move_edit_surface(self) -> None:
        tauri_path = self.path("apps/desktop/src-tauri/src/lib.rs")
        frontend_sources = {
            "backend source": self.path(BACKEND_SOURCE),
            "App source": self.path(APP_SOURCE),
            "SgfTreePanel source": self.path(SGF_TREE_PANEL_SOURCE),
        }
        if not any(path.is_file() for path in frontend_sources.values()):
            self.pending(
                "sgf_existing_move_edit_surface",
                "backend/App/SgfTreePanel source files absent in reduced fixture; full repository smoke must include edit-existing-move command and frontend surface evidence",
            )
            return
        sources = {
            "Tauri command source": tauri_path,
            **frontend_sources,
        }
        missing_sources = [label for label, path in sources.items() if not path.is_file()]
        if missing_sources:
            self.fail("sgf_existing_move_edit_surface", "missing source file(s): " + ", ".join(missing_sources))
            return

        tauri_text = self.read_text("apps/desktop/src-tauri/src/lib.rs")
        backend_text = self.read_text(BACKEND_SOURCE)
        app_text = self.read_text(APP_SOURCE)
        panel_text = self.read_text(SGF_TREE_PANEL_SOURCE)
        if tauri_text is None or backend_text is None or app_text is None or panel_text is None:
            return

        failures = [
            *missing_tauri_command_surface(tauri_text, ["edit_sgf_move"]),
            *missing_required_tokens(
                backend_text,
                "backend",
                ["editSgfMove", "edit_sgf_move"],
            ),
            *missing_required_tokens(
                app_text,
                "App",
                ["handleEditExistingMove", "callEditSgfMove", "normalizeEditSgfMoveResult", "sgfMoveEditMode"],
            ),
            *missing_required_tokens(
                panel_text,
                "SgfTreePanel",
                ["moveEditMode", "canEditSelectedMove", "onEditSelectedMovePass"],
            ),
        ]
        if failures:
            self.fail("sgf_existing_move_edit_surface", "missing edit-existing-move surface: " + ", ".join(failures))
            return
        self.pass_(
            "sgf_existing_move_edit_surface",
            "edit_sgf_move is defined/registered and frontend backend/App/SgfTreePanel edit-existing-move surface is wired",
        )

    def check_external_runtime_gates(self) -> None:
        self.check_tauri_runtime_ui_smoke_evidence()
        self.check_katago_live_smoke_evidence()
        self.check_readboard_live_smoke_evidence()
        self.check_provider_live_smoke_evidence()
        self.pending(
            "multiplatform_packaging_smoke",
            "TODO gate: validate macOS/Windows/Linux packaging in platform-specific build environments",
        )

    def check_tauri_runtime_ui_smoke_evidence(self) -> None:
        evidence_path = self.path(TAURI_RUNTIME_UI_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "ui_tauri_runtime_smoke",
                f"TODO gate: run scripts/smoke_tauri_runtime_ui.py on macOS and record {TAURI_RUNTIME_UI_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(TAURI_RUNTIME_UI_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_tauri_runtime_ui_smoke_evidence(evidence)
        if failures:
            self.pending(
                "ui_tauri_runtime_smoke",
                f"{TAURI_RUNTIME_UI_SMOKE_EVIDENCE} is present but not valid runtime PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "ui_tauri_runtime_smoke",
            f"macOS local Tauri runtime UI smoke evidence passes with {len(TAURI_RUNTIME_UI_SMOKE_REQUIRED_CHECKS)} required checks",
        )

    def check_katago_live_smoke_evidence(self) -> None:
        failures: list[str] = []

        cli_path = self.path(KATAGO_LIVE_SMOKE_EVIDENCE)
        if not cli_path.is_file():
            failures.append(f"run scripts/smoke_katago_live.py and record {KATAGO_LIVE_SMOKE_EVIDENCE}")
        else:
            cli_evidence = self.load_json(KATAGO_LIVE_SMOKE_EVIDENCE)
            if cli_evidence is None:
                return
            failures.extend("CLI evidence: " + failure for failure in validate_katago_live_smoke_evidence(cli_evidence))

        runtime_path = self.path(KATAGO_TAURI_RUNTIME_SMOKE_EVIDENCE)
        if not runtime_path.is_file():
            failures.append(
                f"run scripts/smoke_tauri_katago_live.py and record {KATAGO_TAURI_RUNTIME_SMOKE_EVIDENCE}"
            )
        else:
            runtime_evidence = self.load_json(KATAGO_TAURI_RUNTIME_SMOKE_EVIDENCE)
            if runtime_evidence is None:
                return
            failures.extend(
                "Tauri runtime evidence: " + failure
                for failure in validate_katago_tauri_runtime_smoke_evidence(runtime_evidence)
            )

        if failures:
            self.pending(
                "katago_live_smoke",
                "KataGo live smoke requires both CLI and Tauri runtime PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "katago_live_smoke",
            "macOS live KataGo CLI and Tauri runtime smoke evidence both pass",
        )

    def check_readboard_live_smoke_evidence(self) -> None:
        evidence_path = self.path(READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "readboard_live_smoke",
                f"TODO gate: run scripts/smoke_tauri_readboard_live.py on macOS and record {READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_readboard_tauri_runtime_smoke_evidence(evidence)
        if failures:
            self.pending(
                "readboard_live_smoke",
                f"{READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE} is present but not valid scoped readboard runtime PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "readboard_live_smoke",
            f"macOS scoped readboard Tauri runtime smoke evidence passes with {len(READBOARD_TAURI_RUNTIME_SMOKE_REQUIRED_CHECKS)} required checks",
        )

    def check_provider_live_smoke_evidence(self) -> None:
        evidence_path = self.path(PROVIDER_LIVE_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "provider_live_smoke",
                f"TODO gate: run scripts/smoke_tauri_provider_live.py on macOS and record {PROVIDER_LIVE_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(PROVIDER_LIVE_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_provider_live_smoke_evidence(evidence)
        if failures:
            self.pending(
                "provider_live_smoke",
                f"{PROVIDER_LIVE_SMOKE_EVIDENCE} is present but not valid scoped provider PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "provider_live_smoke",
            f"macOS scoped controlled-network Tauri provider smoke evidence passes with {len(PROVIDER_LIVE_SMOKE_REQUIRED_CHECKS)} required checks",
        )

    def run(self) -> list[SmokeResult]:
        self.check_golden_sgf_fixtures()
        self.check_sgf_compat_fixture()
        self.check_sgf_reorder_fixture()
        self.check_package_scripts()
        self.check_tauri_commands()
        self.check_legacy_shell_menu_surface()
        self.check_native_sgf_save_readback_surface()
        self.check_sgf_existing_move_edit_surface()
        self.check_external_runtime_gates()
        return self.results


def missing_tauri_command_surface(text: str, commands: list[str]) -> list[str]:
    failures: list[str] = []
    for command in commands:
        if not has_tauri_command_function(text, command):
            failures.append(f"{command} function")
        if not command_registered_in_handler(text, command):
            failures.append(f"{command} invoke handler")
    return failures


def validate_tauri_runtime_ui_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != TAURI_RUNTIME_UI_SMOKE_SCHEMA:
        failures.append(f"schema must be {TAURI_RUNTIME_UI_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    check_status_by_name: dict[str, str] = {}
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            failures.append(f"checks[{index}] must be an object")
            continue
        name = check.get("name")
        if not isinstance(name, str) or not name:
            failures.append(f"checks[{index}].name must be a non-empty string")
            continue
        check_status_by_name[name] = str(check.get("status", "")).lower()
    missing = [name for name in TAURI_RUNTIME_UI_SMOKE_REQUIRED_CHECKS if name not in check_status_by_name]
    not_pass = [
        name
        for name in TAURI_RUNTIME_UI_SMOKE_REQUIRED_CHECKS
        if name in check_status_by_name and check_status_by_name[name] != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_tauri_runtime_ui_semantic_checks(checks))
    failures.extend(validate_top_level_save_reopen_proof(evidence))
    return failures


def validate_katago_live_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != KATAGO_LIVE_SMOKE_SCHEMA:
        failures.append(f"schema must be {KATAGO_LIVE_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    engine = evidence.get("engine")
    if not isinstance(engine, dict):
        failures.append("engine must be an object")
    else:
        for key in ("path", "modelPath", "configPath"):
            value = engine.get(key)
            if not isinstance(value, str) or not value:
                failures.append(f"engine.{key} must be a non-empty string")
        if not positive_number(engine.get("maxVisits")):
            failures.append("engine.maxVisits must be positive")
        if not positive_number(engine.get("timeoutSeconds")):
            failures.append("engine.timeoutSeconds must be positive")
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    missing = [name for name in KATAGO_LIVE_SMOKE_REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in KATAGO_LIVE_SMOKE_REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_katago_engine_assets(check_by_name.get("engine_assets")))
    failures.extend(validate_katago_analysis_check(check_by_name.get("one_position_analysis"), "one_position_analysis"))
    failures.extend(validate_katago_batch_check(check_by_name.get("batch_analysis")))
    failures.extend(validate_katago_stderr_check(check_by_name.get("stderr_capture")))
    return failures


def validate_katago_tauri_runtime_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != KATAGO_TAURI_RUNTIME_SMOKE_SCHEMA:
        failures.append(f"schema must be {KATAGO_TAURI_RUNTIME_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    missing = [name for name in KATAGO_TAURI_RUNTIME_SMOKE_REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in KATAGO_TAURI_RUNTIME_SMOKE_REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_katago_runtime_started(check_by_name.get("runtime_started")))
    failures.extend(validate_katago_runtime_failure_mode(check_by_name.get("katago_failure_mode_missing_assets")))
    failures.extend(validate_katago_runtime_assets(check_by_name.get("katago_assets")))
    failures.extend(validate_katago_runtime_analysis(check_by_name.get("katago_analyze_once"), "katago_analyze_once"))
    failures.extend(validate_katago_runtime_analysis(check_by_name.get("katago_analyze_game"), "katago_analyze_game"))
    failures.extend(validate_katago_runtime_cancel(check_by_name.get("katago_start_cancel")))
    return failures


def validate_readboard_tauri_runtime_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != READBOARD_TAURI_RUNTIME_SMOKE_SCHEMA:
        failures.append(f"schema must be {READBOARD_TAURI_RUNTIME_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    missing = [name for name in READBOARD_TAURI_RUNTIME_SMOKE_REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in READBOARD_TAURI_RUNTIME_SMOKE_REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_readboard_runtime_started(check_by_name.get("runtime_started")))
    failures.extend(validate_readboard_probe_ready(check_by_name.get("sidecar_probe_ready")))
    failures.extend(validate_readboard_probe_unavailable(check_by_name.get("sidecar_probe_unavailable")))
    failures.extend(validate_readboard_protocol_line_sync(check_by_name.get("protocol_line_sync")))
    failures.extend(validate_readboard_target_state_change_sync(check_by_name.get("target_state_change_sync")))
    failures.extend(validate_readboard_unsupported_ocr_path(check_by_name.get("unsupported_ocr_path")))
    failures.extend(validate_readboard_external_client_not_covered(check_by_name.get("external_client_not_covered")))
    return failures


def validate_provider_live_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != PROVIDER_LIVE_SMOKE_SCHEMA:
        failures.append(f"schema must be {PROVIDER_LIVE_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    missing = [name for name in PROVIDER_LIVE_SMOKE_REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in PROVIDER_LIVE_SMOKE_REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_provider_runtime_started(check_by_name.get("runtime_started")))
    failures.extend(validate_yike_controlled_fetch(check_by_name.get("yike_controlled_fetch")))
    failures.extend(validate_fox_controlled_fetch(check_by_name.get("fox_controlled_fetch")))
    failures.extend(validate_provider_failure_modes(check_by_name.get("provider_failure_modes")))
    failures.extend(validate_controlled_network_observed(check_by_name.get("controlled_network_observed")))
    failures.extend(validate_offline_not_counted_as_external_live(check_by_name.get("offline_not_counted_as_external_live")))
    failures.extend(validate_external_account_scope(check_by_name.get("external_account_scope")))
    return failures


def validate_provider_runtime_started(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["runtime_started evidence must be an object"]
    if evidence.get("tauriInternals") is not True:
        return ["runtime_started.tauriInternals must be true"]
    return []


def validate_yike_controlled_fetch(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["yike_controlled_fetch evidence must be an object"]
    failures: list[str] = []
    if evidence.get("provider") != "yike":
        failures.append("yike_controlled_fetch.provider must be yike")
    if evidence.get("networkMode") != "controlled_network":
        failures.append("yike_controlled_fetch.networkMode must be controlled_network")
    if not http_status_success_or_redirect(evidence.get("httpStatus")):
        failures.append("yike_controlled_fetch.httpStatus must be 2xx/3xx")
    if evidence.get("payloadValidated") is not True:
        failures.append("yike_controlled_fetch.payloadValidated must be true")
    result_count = evidence.get("resultCount")
    if not isinstance(result_count, (int, float)) or result_count < 0:
        failures.append("yike_controlled_fetch.resultCount must be non-negative")
    if evidence.get("fixtureParserOnly") is not False:
        failures.append("yike_controlled_fetch.fixtureParserOnly must be false")
    return failures


def validate_fox_controlled_fetch(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["fox_controlled_fetch evidence must be an object"]
    failures: list[str] = []
    if evidence.get("provider") != "fox":
        failures.append("fox_controlled_fetch.provider must be fox")
    if evidence.get("networkMode") != "controlled_network":
        failures.append("fox_controlled_fetch.networkMode must be controlled_network")
    if not http_status_success_or_redirect(evidence.get("httpStatus")):
        failures.append("fox_controlled_fetch.httpStatus must be 2xx/3xx")
    if evidence.get("payloadImported") is not True:
        failures.append("fox_controlled_fetch.payloadImported must be true")
    if not positive_number(evidence.get("moveCount")):
        failures.append("fox_controlled_fetch.moveCount must be positive")
    if evidence.get("directHttpWarning") is not True:
        failures.append("fox_controlled_fetch.directHttpWarning must be true")
    return failures


def validate_provider_failure_modes(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["provider_failure_modes evidence must be an object"]
    failures: list[str] = []
    if evidence.get("observed") is not True:
        failures.append("provider_failure_modes.observed must be true")
    if evidence.get("typedProviderError") is not True:
        failures.append("provider_failure_modes.typedProviderError must be true")
    error_kind = evidence.get("errorKind")
    if not isinstance(error_kind, str) or not error_kind:
        failures.append("provider_failure_modes.errorKind must be non-empty")
    message = evidence.get("message")
    if not isinstance(message, str) or not message:
        failures.append("provider_failure_modes.message must be non-empty")
    if evidence.get("reportedAsSuccess") is not False:
        failures.append("provider_failure_modes.reportedAsSuccess must be false")
    return failures


def validate_controlled_network_observed(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["controlled_network_observed evidence must be an object"]
    failures: list[str] = []
    if evidence.get("controlledHttpServer") is not True:
        failures.append("controlled_network_observed.controlledHttpServer must be true")
    request_count = evidence.get("requestCount")
    if not isinstance(request_count, (int, float)) or request_count < 3:
        failures.append("controlled_network_observed.requestCount must be at least 3")
    if evidence.get("yikeSignedHeadersObserved") is not True:
        failures.append("controlled_network_observed.yikeSignedHeadersObserved must be true")
    if evidence.get("foxRequestObserved") is not True:
        failures.append("controlled_network_observed.foxRequestObserved must be true")
    if evidence.get("failureRequestObserved") is not True:
        failures.append("controlled_network_observed.failureRequestObserved must be true")
    return failures


def validate_offline_not_counted_as_external_live(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["offline_not_counted_as_external_live evidence must be an object"]
    failures: list[str] = []
    if evidence.get("offlineParserOnly") is not False:
        failures.append("offline_not_counted_as_external_live.offlineParserOnly must be false")
    if evidence.get("controlledHttpServer") is not True:
        failures.append("offline_not_counted_as_external_live.controlledHttpServer must be true")
    if evidence.get("externalProviderServiceCovered") is not False:
        failures.append("offline_not_counted_as_external_live.externalProviderServiceCovered must be false")
    return failures


def validate_external_account_scope(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["external_account_scope evidence must be an object"]
    failures: list[str] = []
    if evidence.get("realAccountLoginStateCovered") is not False:
        failures.append("external_account_scope.realAccountLoginStateCovered must be false")
    if evidence.get("antiBotStabilityCovered") is not False:
        failures.append("external_account_scope.antiBotStabilityCovered must be false")
    if evidence.get("serviceSchemaDriftCovered") is not False:
        failures.append("external_account_scope.serviceSchemaDriftCovered must be false")
    return failures


def validate_readboard_runtime_started(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["runtime_started evidence must be an object"]
    if evidence.get("tauriInternals") is not True:
        return ["runtime_started.tauriInternals must be true"]
    return []


def validate_readboard_probe_ready(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["sidecar_probe_ready evidence must be an object"]
    if evidence.get("available") is not True:
        return ["sidecar_probe_ready.available must be true"]
    return []


def validate_readboard_probe_unavailable(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["sidecar_probe_unavailable evidence must be an object"]
    if evidence.get("available") is not False:
        return ["sidecar_probe_unavailable.available must be false"]
    return []


def validate_readboard_protocol_line_sync(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["protocol_line_sync evidence must be an object"]
    failures: list[str] = []
    snapshot_id = first_present(evidence, "snapshotId", "snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        failures.append("protocol_line_sync.snapshotId must be non-empty")
    if not positive_number(first_present(evidence, "boardSize", "board_size")):
        failures.append("protocol_line_sync.boardSize must be positive")
    move_number = first_present(evidence, "moveNumber", "move_number")
    if not isinstance(move_number, (int, float)) or move_number < 0:
        failures.append("protocol_line_sync.moveNumber must be non-negative")
    if not positive_number(first_present(evidence, "stoneCount", "stone_count")):
        failures.append("protocol_line_sync.stoneCount must be positive")
    to_play = first_present(evidence, "toPlay", "to_play")
    if str(to_play).lower() not in {"black", "white"}:
        failures.append("protocol_line_sync.toPlay must be black or white")
    return failures


def validate_readboard_target_state_change_sync(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["target_state_change_sync evidence must be an object"]
    failures: list[str] = []
    if evidence.get("changed") is not True:
        failures.append("target_state_change_sync.changed must be true")
    before_snapshot_id = first_present(evidence, "beforeSnapshotId", "before_snapshot_id")
    after_snapshot_id = first_present(evidence, "afterSnapshotId", "after_snapshot_id")
    if not isinstance(before_snapshot_id, str) or not before_snapshot_id:
        failures.append("target_state_change_sync.beforeSnapshotId must be non-empty")
    if not isinstance(after_snapshot_id, str) or not after_snapshot_id:
        failures.append("target_state_change_sync.afterSnapshotId must be non-empty")
    if isinstance(before_snapshot_id, str) and before_snapshot_id and before_snapshot_id == after_snapshot_id:
        failures.append("target_state_change_sync snapshot ids must differ")
    before_stone_count = first_present(evidence, "beforeStoneCount", "before_stone_count")
    after_stone_count = first_present(evidence, "afterStoneCount", "after_stone_count")
    before_move_number = first_present(evidence, "beforeMoveNumber", "before_move_number")
    after_move_number = first_present(evidence, "afterMoveNumber", "after_move_number")
    stone_counts_numeric = isinstance(before_stone_count, (int, float)) and isinstance(after_stone_count, (int, float))
    move_numbers_numeric = isinstance(before_move_number, (int, float)) and isinstance(after_move_number, (int, float))
    if not stone_counts_numeric:
        failures.append("target_state_change_sync stone counts must be numeric")
    if not move_numbers_numeric:
        failures.append("target_state_change_sync move numbers must be numeric")
    if stone_counts_numeric and move_numbers_numeric and before_stone_count == after_stone_count and before_move_number == after_move_number:
        failures.append("target_state_change_sync stone count or move number must change")
    if evidence.get("boardSizeStable") is not True:
        failures.append("target_state_change_sync.boardSizeStable must be true")
    return failures


def validate_readboard_unsupported_ocr_path(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["unsupported_ocr_path evidence must be an object"]
    failures: list[str] = []
    if evidence.get("observed") is not True:
        failures.append("unsupported_ocr_path.observed must be true")
    if evidence.get("unsupported") is not True:
        failures.append("unsupported_ocr_path.unsupported must be true")
    if first_present(evidence, "messageIncludesBoundary", "message_includes_boundary") is not True:
        failures.append("unsupported_ocr_path.messageIncludesBoundary must be true")
    message = evidence.get("message")
    if not isinstance(message, str) or not message:
        failures.append("unsupported_ocr_path.message must be non-empty")
    elif "image" not in message.lower() and "ocr" not in message.lower():
        failures.append("unsupported_ocr_path.message must mention image or ocr")
    return failures


def validate_readboard_external_client_not_covered(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["external_client_not_covered evidence must be an object"]
    failures: list[str] = []
    if evidence.get("covered") is not False:
        failures.append("external_client_not_covered.covered must be false")
    if evidence.get("ocrCovered") is not False:
        failures.append("external_client_not_covered.ocrCovered must be false")
    if evidence.get("externalClientCaptureCovered") is not False:
        failures.append("external_client_not_covered.externalClientCaptureCovered must be false")
    return failures


def validate_katago_runtime_started(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["runtime_started evidence must be an object"]
    if evidence.get("tauriInternals") is not True:
        return ["runtime_started must confirm real Tauri runtime"]
    return []


def validate_katago_runtime_assets(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["katago_assets evidence must be an object"]
    failures: list[str] = []
    if evidence.get("engineExists") is not True and evidence.get("engineExecutable") is not True:
        failures.append("katago_assets must confirm engine exists")
    if not positive_number(first_present(evidence, "modelBytes", "modelSizeBytes")):
        failures.append("katago_assets must include positive model bytes")
    if not positive_number(first_present(evidence, "configBytes", "configSizeBytes")):
        failures.append("katago_assets must include positive config bytes")
    return failures


def validate_katago_runtime_failure_mode(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["katago_failure_mode_missing_assets evidence must be an object"]
    if evidence.get("observed") is not True:
        return ["katago_failure_mode_missing_assets must confirm observed failure"]
    missing_required = evidence.get("missingRequired")
    if not isinstance(missing_required, list) or not missing_required:
        structured_error = evidence.get("structuredError")
        if not isinstance(structured_error, str) or not structured_error.strip():
            return ["katago_failure_mode_missing_assets must include missing assets or structured error"]
    return []


def validate_katago_runtime_analysis(check: Any, name: str) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return [f"{name} evidence must be an object"]
    failures: list[str] = []
    if not positive_number(first_present(evidence, "frameCount", "frames", "responseCount", "visits")):
        failures.append(f"{name} must include positive frame count")
    if not positive_number(first_present(evidence, "candidateCount", "moveInfoCount", "candidateMoveCount", "candidates")):
        failures.append(f"{name} must include positive candidate count")
    if (
        evidence.get("rootInfo") is not True
        and evidence.get("hasRootInfo") is not True
        and not positive_number(evidence.get("visits"))
    ):
        failures.append(f"{name} must confirm root info or positive visits")
    return failures


def validate_katago_runtime_cancel(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["katago_start_cancel evidence must be an object"]
    failures: list[str] = []
    if not isinstance(first_present(evidence, "jobId", "job_id"), str):
        failures.append("katago_start_cancel must include job id")
    event = evidence.get("event")
    event_kind = event.get("kind") if isinstance(event, dict) else None
    if evidence.get("cancelRequested") is not True:
        failures.append("katago_start_cancel must confirm cancellation was requested")
    if evidence.get("cancelConfirmed") is not True and event_kind != "cancelled":
        failures.append("katago_start_cancel must confirm cancellation event")
    return failures


def validate_katago_engine_assets(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["engine_assets details must be an object"]
    failures: list[str] = []
    if evidence.get("engineExecutable") is not True:
        failures.append("engine_assets must confirm executable engine")
    if not positive_number(evidence.get("modelBytes")):
        failures.append("engine_assets must include positive modelBytes")
    if not positive_number(evidence.get("configBytes")):
        failures.append("engine_assets must include positive configBytes")
    return failures


def validate_katago_analysis_check(check: Any, name: str) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return [f"{name} details must be an object"]
    failures: list[str] = []
    if not isinstance(evidence.get("id"), str) or not evidence.get("id"):
        failures.append(f"{name} must include response id")
    if not positive_number(evidence.get("moveInfoCount")):
        failures.append(f"{name} must include positive moveInfoCount")
    if evidence.get("hasRootInfo") is not True:
        failures.append(f"{name} must confirm rootInfo")
    return failures


def validate_katago_batch_check(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["batch_analysis details must be an object"]
    failures: list[str] = []
    responses = evidence.get("responses")
    if not isinstance(responses, list) or len(responses) < 2:
        return ["batch_analysis must include at least two responses"]
    if evidence.get("responseCount") != len(responses):
        failures.append("batch_analysis responseCount must match responses")
    for index, response in enumerate(responses):
        for failure in validate_katago_analysis_check(response, f"batch_analysis.responses[{index}]"):
            failures.append(failure)
    return failures


def validate_katago_stderr_check(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["stderr_capture details must be an object"]
    if evidence.get("stderrCaptured") is not True:
        return ["stderr_capture must confirm stderr capture"]
    return []


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and value > 0


def http_status_success_or_redirect(value: Any) -> bool:
    return isinstance(value, (int, float)) and 200 <= value < 400


def validate_tauri_runtime_ui_semantic_checks(checks: list[Any]) -> list[str]:
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
    has_readback = False
    if readback_verified is True or readback_status == "matched_saved_text":
        has_readback = True
    if isinstance(saved_hash, str) and saved_hash and saved_hash == readback_hash:
        has_readback = True
    if not has_readback:
        failures.append("save_readback_roundtrip evidence must include readback verification")
    failures.extend(validate_two_launch_save_reopen_evidence(evidence))
    return failures


def validate_two_launch_save_reopen_evidence(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    second_launch = first_present(evidence, "secondLaunch", "second_launch")
    if not isinstance(second_launch, dict):
        failures.append("save_readback_roundtrip evidence must include secondLaunch object")
    elif not evidence_status_passed(second_launch):
        failures.append("save_readback_roundtrip secondLaunch must be verified")

    reopen = first_present(evidence, "reopen", "reopenProof", "reopen_proof")
    if not isinstance(reopen, dict):
        failures.append("save_readback_roundtrip evidence must include reopen object")
    else:
        reopen_path = first_present(reopen, "path", "reopenedPath", "reopened_path", "savedPath", "saved_path")
        if not isinstance(reopen_path, str) or not reopen_path:
            failures.append("save_readback_roundtrip reopen evidence must include reopened path")
        if not evidence_status_passed(reopen) and first_present(reopen, "matchesSaved", "matches_saved", "reopenedMatchesSaved", "reopened_matches_saved") is not True:
            failures.append("save_readback_roundtrip reopen must be verified")

    after_reopen = first_present(evidence, "afterReopen", "after_reopen", "reopenedState", "reopened_state")
    if not isinstance(after_reopen, dict):
        failures.append("save_readback_roundtrip evidence must include afterReopen object")
        return failures
    required_after_reopen = {
        "treeOrderVerified": ("treeOrderVerified", "tree_order_verified"),
        "commentsVerified": ("commentsVerified", "comments_verified"),
        "propertiesVerified": ("propertiesVerified", "properties_verified"),
        "moveCountVerified": ("moveCountVerified", "move_count_verified"),
        "boardStateVerified": ("boardStateVerified", "board_state_verified"),
    }
    missing = [
        label
        for label, keys in required_after_reopen.items()
        if first_present(after_reopen, *keys) is not True
    ]
    if missing:
        failures.append("save_readback_roundtrip afterReopen must verify " + ", ".join(missing))
    return failures


def validate_top_level_save_reopen_proof(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    first_launch = first_present(evidence, "firstLaunch", "first_launch")
    second_launch = first_present(evidence, "secondLaunch", "second_launch")
    proof = first_present(evidence, "saveReopenProof", "save_reopen_proof")
    if not isinstance(first_launch, dict):
        failures.append("evidence must include firstLaunch object")
    elif first_launch.get("phase") != "edit-save" or first_launch.get("stopped") is not True:
        failures.append("firstLaunch must record stopped edit-save phase")
    if not isinstance(second_launch, dict):
        failures.append("evidence must include secondLaunch object")
    elif second_launch.get("phase") != "reopen-verify" or second_launch.get("stopped") is not True:
        failures.append("secondLaunch must record stopped reopen-verify phase")
    if not isinstance(proof, dict):
        failures.append("evidence must include saveReopenProof object")
        return failures
    if proof.get("sameSgfPath") is not True:
        failures.append("saveReopenProof must confirm same SGF path")
    if proof.get("distinctProcesses") is not True:
        failures.append("saveReopenProof must confirm distinct Tauri processes")
    if proof.get("firstStoppedBeforeSecondStarted") is not True:
        failures.append("saveReopenProof must confirm first launch stopped before second started")
    return failures


def evidence_status_passed(evidence: dict[str, Any]) -> bool:
    status = first_present(evidence, "status", "result")
    verified = first_present(evidence, "verified", "passed", "ok", "started")
    launch_index = first_present(evidence, "launchIndex", "launch_index")
    return status == "pass" or verified is True or launch_index == 2


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


def missing_required_tokens(text: str, source_label: str, tokens: list[str]) -> list[str]:
    return [f"{source_label} missing {token}" for token in tokens if not re.search(r"\b" + re.escape(token) + r"\b", text)]


def has_tauri_command_function(text: str, command: str) -> bool:
    pattern = re.compile(
        r"#\[tauri::command\](?:\s*#\[[^\]]+\])*\s*(?:pub\s+)?fn\s+"
        + re.escape(command)
        + r"\s*\("
    )
    return bool(pattern.search(text))


def command_registered_in_handler(text: str, command: str) -> bool:
    for match in re.finditer(r"tauri::generate_handler!\s*\[", text):
        start = match.end()
        end = find_matching_bracket(text, start - 1)
        if end is not None and re.search(r"\b" + re.escape(command) + r"\b", text[start:end]):
            return True
    return False


def missing_legacy_shell_menu_surface(text: str, menu_surface: dict[str, list[str]]) -> list[str]:
    failures: list[str] = []
    for group_label, item_labels in menu_surface.items():
        group_body = find_legacy_menu_group_body(text, group_label)
        if group_body is None:
            failures.append(f"{group_label} menu group missing")
            continue
        for item_label in item_labels:
            item_body = find_legacy_menu_item_body(group_body, item_label)
            if item_body is None:
                failures.append(f"{group_label}/{item_label} menu entry missing")
                continue
            if has_literal_disabled_true(item_body):
                failures.append(f"{group_label}/{item_label} has literal disabled: true")
            if not has_identifiable_menu_entry(item_body, item_label):
                failures.append(f"{group_label}/{item_label} lacks data-testid or recognizable label")
    return failures


def find_legacy_menu_group_body(text: str, group_label: str) -> str | None:
    label_match = re.search(r"\blabel\s*:\s*" + re.escape(quote_ts_string(group_label)), text)
    if not label_match:
        return None
    object_start = text.rfind("{", 0, label_match.start())
    if object_start < 0:
        return None
    object_end = find_matching_delimiter(text, object_start, "{", "}")
    if object_end is None:
        return None
    return text[object_start + 1 : object_end]


def find_legacy_menu_item_body(group_body: str, item_label: str) -> str | None:
    items_match = re.search(r"\bitems\s*:\s*\[", group_body)
    if not items_match:
        return None
    items_start = items_match.end() - 1
    items_end = find_matching_delimiter(group_body, items_start, "[", "]")
    if items_end is None:
        return None
    items_body = group_body[items_start + 1 : items_end]
    label_match = re.search(r"\blabel\s*:\s*" + re.escape(quote_ts_string(item_label)), items_body)
    if not label_match:
        return None
    item_start = items_body.rfind("{", 0, label_match.start())
    if item_start < 0:
        return None
    item_end = find_matching_delimiter(items_body, item_start, "{", "}")
    if item_end is None:
        return None
    return items_body[item_start + 1 : item_end]


def has_literal_disabled_true(item_body: str) -> bool:
    return bool(re.search(r"\bdisabled\s*:\s*true\b", item_body))


def has_identifiable_menu_entry(item_body: str, item_label: str) -> bool:
    return bool(re.search(r"\bdata-testid\s*:", item_body)) or bool(
        re.search(r"\blabel\s*:\s*" + re.escape(quote_ts_string(item_label)), item_body)
    )


def missing_backend_sgf_save_readback_surface(text: str) -> list[str]:
    failures: list[str] = []
    if not re.search(r"\bexport\s+async\s+function\s+readSgfDocument\s*\(", text) and not re.search(
        r"\binvoke\s*<\s*string\s*>\s*\(\s*['\"]read_sgf_file['\"]", text
    ):
        failures.append("backend lacks readSgfDocument/read_sgf_file read surface")

    body = find_function_body(text, "saveSgfDocument")
    if body is None:
        return failures + ["backend saveSgfDocument function missing"]
    if not re.search(r"\binvoke\s*<\s*void\s*>\s*\(\s*['\"]write_sgf_file['\"]", body):
        failures.append("backend saveSgfDocument does not invoke write_sgf_file")
    if not (
        re.search(r"\binvoke\s*<\s*string\s*>\s*\(\s*['\"]read_sgf_file['\"]", body)
        or re.search(r"\breadSgfDocument\s*\(", body)
    ):
        failures.append("backend saveSgfDocument does not read back the saved SGF")
    if not re.search(r"\breturn\s*\{[^}]*path\s*:\s*targetPath[^}]*sgfText\s*:", body, re.S):
        failures.append("backend saveSgfDocument does not return a document with the read-back SGF text")
    return failures


def missing_app_sgf_save_readback_refresh_surface(text: str) -> list[str]:
    failures: list[str] = []
    body = find_function_body(text, "handleSaveSgfDocument")
    if body is None:
        return ["App handleSaveSgfDocument function missing"]
    required_patterns = {
        "uses saved.sgfText/read-back text": r"\bsaved\.sgfText\b",
        "updates SGF text from read-back": r"\bsetSgfText\s*\(\s*saved\.sgfText\s*\)",
        "marks SGF edit version refreshed": r"\bsgfTextEditVersionRef\.current\s*\+=",
        "parses read-back SGF summary": r"\bparseSgfSummary\s*\(\s*saved\.sgfText\s*\)",
        "replays read-back SGF positions": r"\breplaySgfPositions\s*\(\s*saved\.sgfText\s*\)",
        "rebuilds read-back SGF tree": r"\bparseSgfTree\s*\(\s*saved\.sgfText\s*\)",
        "updates parsed game state": r"\bsetGame\s*\(",
        "updates replayed positions": r"\bsetPositions\s*\(",
        "applies refreshed SGF tree": r"\bapplySgfTree\s*\(",
        "refreshes analysis cache status": r"\bcheckAnalysisCacheForGame\s*\(",
    }
    for label, pattern in required_patterns.items():
        if not re.search(pattern, body):
            failures.append(f"App handleSaveSgfDocument missing {label}")
    return failures


def find_function_body(text: str, function_name: str) -> str | None:
    match = re.search(
        r"(?:\bexport\s+)?(?:\basync\s+)?\bfunction\s+"
        + re.escape(function_name)
        + r"\s*\([^)]*\)\s*(?::[^{]+)?\{",
        text,
    )
    if not match:
        return None
    open_index = match.end() - 1
    close_index = find_matching_delimiter(text, open_index, "{", "}")
    if close_index is None:
        return None
    return text[open_index + 1 : close_index]


def quote_ts_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def count_variation_children_at_depth(text: str, parent_depth: int) -> int:
    count = 0
    depth = 0
    escaped = False
    in_value = False
    for index, char in enumerate(text):
        if in_value:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "]":
                in_value = False
            continue
        if char == "[":
            in_value = True
        elif char == "(":
            if depth == parent_depth and text[index + 1 : index + 2] == ";":
                count += 1
            depth += 1
        elif char == ")":
            depth -= 1
    return count


def find_matching_bracket(text: str, open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
    return None


def find_matching_delimiter(text: str, open_index: int, open_char: str, close_char: str) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
    return None


def print_results(results: list[SmokeResult], *, verbose: bool) -> None:
    failures = [result for result in results if result.status == "FAIL"]
    pending = [result for result in results if result.status == "PENDING"]
    passes = [result for result in results if result.status == "PASS"]
    if verbose or failures:
        for result in results:
            if verbose or result.status == "FAIL":
                print(f"{result.status} {result.name}: {result.detail}")
    else:
        print("PASS user-flow smoke skeleton: repository-local checks passed")
        if pending:
            print(f"PENDING user-flow smoke gates: {len(pending)} deferred external/runtime checks")
    print(f"User-flow smoke: {len(passes)} passed, {len(failures)} failed, {len(pending)} pending.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run repository-local smoke checks for LizzieYzy Next user flows.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to validate")
    parser.add_argument("--verbose", action="store_true", help="print passing and pending checks as well as failures")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2
    results = UserFlowSmoke(root).run()
    print_results(results, verbose=args.verbose)
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
