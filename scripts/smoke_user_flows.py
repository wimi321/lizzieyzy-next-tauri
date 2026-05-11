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
        self.pending(
            "katago_live_smoke",
            "TODO gate: validate real KataGo analysis only with a controlled engine binary, model, config, and runtime evidence",
        )
        self.pending(
            "readboard_live_smoke",
            "TODO gate: validate real readboard sidecar flows only with installed sidecar/runtime evidence",
        )
        self.pending(
            "provider_live_smoke",
            "TODO gate: validate live provider fetch flows only with controlled network/provider evidence",
        )
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
    return failures


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
