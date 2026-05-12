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
    "annotation_edit",
    "append_move",
    "edit_move",
    "delete_node",
    "variation_reorder",
    "save_readback_roundtrip",
    "board_state_verified",
]
DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE = "docs/qa/desktop-sgf-editing-ux-smoke-macos.json"
DESKTOP_SGF_EDITING_UX_SMOKE_SCHEMA = "lizzieyzy.desktop-sgf-editing-ux-smoke.v1"
DESKTOP_SGF_EDITING_UX_SMOKE_REQUIRED_CHECKS = [
    "legacy_shell_visible",
    "toolbar_menu_controls",
    "tree_panel_visible",
    "annotation_editor_visible",
    "selected_node_ux_state",
    "tree_navigation",
    "comment_property_annotation_edit",
    "append_edit_reorder_delete",
    "dirty_saved_status",
    "save_readback_reopen",
    "native_dialog_boundary",
]
DESKTOP_UI_CLICK_SMOKE_EVIDENCE = "docs/qa/desktop-ui-click-smoke-macos.json"
DESKTOP_UI_CLICK_SMOKE_SCHEMA = "lizzieyzy.desktop-ui-click-smoke.v1"
NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE = "docs/qa/native-menu-shortcut-smoke-macos.json"
NATIVE_MENU_SHORTCUT_SMOKE_SCHEMA = "lizzieyzy.native-menu-shortcut-smoke.v1"
NATIVE_MENU_SHORTCUT_SMOKE_REQUIRED_CHECKS = [
    "native_menu_surface",
    "native_menu_event_bridge",
    "keyboard_shortcut_surface",
    "action_ids_aligned",
    "input_editing_safe",
    "scope_boundaries",
]
NATIVE_MENU_SHORTCUT_REQUIRED_TRUE_FIELDS = [
    "nativeMenuSurface",
    "nativeMenuEventBridge",
    "keyboardShortcutSurface",
    "actionIdsAligned",
    "inputEditingSafe",
]
NATIVE_MENU_SHORTCUT_REQUIRED_FALSE_FIELDS = [
    "fullShortcutParity",
    "fullLegacyMenuParity",
    "webviewDomProof",
    "osNativeMenuFullParity",
    "releasePublished",
    "productionSigned",
    "notarized",
    "providerParityCovered",
    "readboardParityCovered",
    "ocrExternalCaptureCovered",
    "windowsLinuxCovered",
]
NATIVE_MENU_SHORTCUT_FORBIDDEN_TRUE_FIELDS = {
    "fullShortcutParity": "fullShortcutParity must be false",
    "fullLegacyMenuParity": "fullLegacyMenuParity must be false",
    "fullLegacyParity": "fullLegacyParity must be false",
    "fullLegacyParityCovered": "fullLegacyParityCovered must be false",
    "webviewDomProof": "webviewDomProof must be false",
    "webviewDomCovered": "webviewDomCovered must be false",
    "webviewDomAutomationCovered": "webviewDomAutomationCovered must be false",
    "osNativeMenuFullParity": "osNativeMenuFullParity must be false",
    "releasePublished": "releasePublished must be false",
    "productionSigned": "productionSigned must be false",
    "notarized": "notarized must be false",
    "providerCompleted": "providerCompleted must be false",
    "providerCovered": "providerCovered must be false",
    "providerParityCovered": "providerParityCovered must be false",
    "readboardCompleted": "readboardCompleted must be false",
    "readboardCovered": "readboardCovered must be false",
    "readboardParityCovered": "readboardParityCovered must be false",
    "ocrCompleted": "ocrCompleted must be false",
    "ocrCovered": "ocrCovered must be false",
    "ocrCaptureCovered": "ocrCaptureCovered must be false",
    "ocrExternalCaptureCovered": "ocrExternalCaptureCovered must be false",
    "externalClientCaptureCovered": "externalClientCaptureCovered must be false",
    "windowsLinuxCovered": "windowsLinuxCovered must be false",
    "windowsCovered": "windowsCovered must be false",
    "windowsParityCovered": "windowsParityCovered must be false",
    "linuxCovered": "linuxCovered must be false",
    "linuxParityCovered": "linuxParityCovered must be false",
}
LEGACY_SHELL_MENU_ACTION_REQUIRED_TARGETS = [
    ("View:Candidates", "candidates"),
    ("View:Ownership", "ownership"),
    ("View:Policy", "policy"),
    ("Engine:Profiles", "profiles"),
    ("Engine:Assets", "assets"),
    ("Tools:Providers", "providers"),
    ("Tools:Preferences", "preferences"),
    ("Help:Backend status", "backend-status"),
]
TAURI_WINDOW_RUNTIME_SMOKE_EVIDENCE = "docs/qa/tauri-window-runtime-smoke-macos.json"
TAURI_WINDOW_RUNTIME_SMOKE_SCHEMA = "lizzieyzy.tauri-window-runtime-smoke.v1"
INSTALLED_MACOS_APP_SMOKE_EVIDENCE = "docs/qa/installed-macos-app-smoke.json"
INSTALLED_MACOS_APP_SMOKE_SCHEMA = "lizzieyzy.installed-macos-app-smoke.v1"
NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE = "docs/qa/native-desktop-sgf-workflow-macos.json"
NATIVE_DESKTOP_SGF_WORKFLOW_SCHEMA = "lizzieyzy.native-desktop-sgf-workflow.v1"
NATIVE_DESKTOP_SGF_WORKFLOW_COLLECTION_METHODS = {
    "manual_assisted_native_desktop_workflow",
    "automated_native_desktop_workflow",
    "automated_native_desktop_sgf_workflow",
}
NATIVE_DESKTOP_SGF_WORKFLOW_REQUIRED_BOOLEANS = [
    "nativeDialogOpenCovered",
    "nativeDialogSaveCovered",
    "webviewDomAutomationCovered",
    "fullAutomationCovered",
    "fullLegacyParityCovered",
    "releasePublished",
    "productionSigned",
    "notarized",
]
NATIVE_DESKTOP_SGF_WORKFLOW_REQUIRED_CHECKS = [
    "app_started",
    "native_open_dialog",
    "sgf_opened",
    "edit_operations_applied",
    "save_or_save_as",
    "reopen_saved_sgf",
    "reopen_state_verified",
    "screenshots_recorded",
    "scope_boundaries",
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
MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE = "docs/qa/multiplatform-packaging-smoke.json"
MULTIPLATFORM_PACKAGING_SMOKE_SCHEMA = "lizzieyzy.multiplatform-packaging-smoke.v1"
PACKAGING_PLATFORMS = ["macos", "windows", "linux"]
MULTIPLATFORM_PACKAGING_SMOKE_REQUIRED_CHECKS = [
    "macos_artifacts",
    "windows_artifacts",
    "linux_artifacts",
    "signing_recorded",
    "dev_server_absent",
    "checksums",
]
TAURI_COMMANDS = [
    "update_sgf_node_comment",
    "append_sgf_move",
    "delete_sgf_node",
]
LEGACY_IMPORT_CAPTURE_HELPER_COMMAND = "legacy_import_capture_helper"
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
LEGACY_ACTIONS_SOURCE = "apps/desktop/src/domain/legacyActions.ts"
APP_SOURCE = "apps/desktop/src/App.tsx"
BACKEND_SOURCE = "apps/desktop/src/api/backend.ts"
PROVIDER_API_SOURCE = "apps/desktop/src/api/providers.ts"
PROVIDER_DOMAIN_SOURCE = "apps/desktop/src/domain/providers.ts"
PROVIDER_PANEL_SOURCE = "apps/desktop/src/components/ProviderPanel.tsx"
SGF_TREE_PANEL_SOURCE = "apps/desktop/src/components/SgfTreePanel.tsx"
SGF_ANNOTATION_PANEL_SOURCE = "apps/desktop/src/components/SgfAnnotationPanel.tsx"
PREFERENCES_PANEL_SOURCE = "apps/desktop/src/components/PreferencesPanel.tsx"
ENGINE_SETUP_PANEL_SOURCE = "apps/desktop/src/components/EngineSetupPanel.tsx"
LEGACY_SHELL_MENU_SURFACE = {
    "View": ["Candidates", "Ownership", "Policy"],
    "Engine": ["Profiles", "Assets"],
    "Tools": ["Providers", "Preferences"],
    "Help": ["Backend status"],
}
NATIVE_MENU_GROUPS = ["File", "Game", "Analysis", "View", "Engine", "Tools", "Help"]
NATIVE_MENU_EVENT_NAME = "legacy://native-menu-action"


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
        shell_text = self.read_text(LEGACY_SHELL_SOURCE)
        actions_text = self.read_text(LEGACY_ACTIONS_SOURCE)
        if shell_text is None or actions_text is None:
            return
        failures = missing_legacy_shell_menu_surface(shell_text, actions_text, LEGACY_SHELL_MENU_SURFACE)
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

    def check_sgf_annotation_surface(self) -> None:
        sources = {
            "backend source": self.path(BACKEND_SOURCE),
            "App source": self.path(APP_SOURCE),
            "SgfTreePanel source": self.path(SGF_TREE_PANEL_SOURCE),
            "SgfAnnotationPanel source": self.path(SGF_ANNOTATION_PANEL_SOURCE),
            "runtime smoke source": self.path("apps/desktop/src/runtimeSmoke.ts"),
            "Tauri command source": self.path("apps/desktop/src-tauri/src/lib.rs"),
        }
        frontend_paths = [path for label, path in sources.items() if label != "Tauri command source"]
        if not any(path.is_file() for path in frontend_paths):
            self.pending(
                "sgf_annotation_surface",
                "annotation source files absent in reduced fixture; full repository smoke must include SGF annotation editor and runtime smoke evidence",
            )
            return
        missing_sources = [label for label, path in sources.items() if not path.is_file()]
        if missing_sources:
            self.fail("sgf_annotation_surface", "missing source file(s): " + ", ".join(missing_sources))
            return

        backend_text = self.read_text(BACKEND_SOURCE)
        app_text = self.read_text(APP_SOURCE)
        tree_panel_text = self.read_text(SGF_TREE_PANEL_SOURCE)
        annotation_panel_text = self.read_text(SGF_ANNOTATION_PANEL_SOURCE)
        runtime_smoke_text = self.read_text("apps/desktop/src/runtimeSmoke.ts")
        tauri_text = self.read_text("apps/desktop/src-tauri/src/lib.rs")
        if None in (backend_text, app_text, tree_panel_text, annotation_panel_text, runtime_smoke_text, tauri_text):
            return

        failures = [
            *missing_tauri_command_surface(tauri_text or "", ["update_sgf_node_properties"]),
            *missing_required_tokens(backend_text or "", "backend", ["updateSgfNodeProperties", "update_sgf_node_properties"]),
            *missing_required_tokens(
                app_text or "",
                "App",
                ["handleSaveAnnotations", "annotationError", "setAnnotationError", "isAnnotationSaving", "updateSgfNodeProperties"],
            ),
            *missing_required_tokens(
                tree_panel_text or "",
                "SgfTreePanel",
                ["SgfAnnotationPanel", "onSaveAnnotations", "isAnnotationSaving", "annotationError"],
            ),
            *missing_required_tokens(
                annotation_panel_text or "",
                "SgfAnnotationPanel",
                [
                    "TR",
                    "SQ",
                    "CR",
                    "MA",
                    "SL",
                    "LB",
                    "AR",
                    "LN",
                    "Save Annotations",
                    "Remove",
                    "Clear",
                    "role",
                    "alert",
                    "SgfPropertyUpdate",
                ],
            ),
            *missing_required_tokens(
                runtime_smoke_text or "",
                "runtimeSmoke",
                ["annotation_edit", "expectedBranchAnnotations", "annotationsVerified", "assertPropertyAbsent"],
            ),
        ]
        if failures:
            self.fail("sgf_annotation_surface", "missing SGF annotation surface: " + ", ".join(failures))
            return
        self.pass_(
            "sgf_annotation_surface",
            "SGF annotation editor and runtime smoke evidence cover TR/SQ/CR/MA/SL/LB/AR/LN add/update/remove through update_sgf_node_properties",
        )

    def check_legacy_config_migration_surface(self) -> None:
        sources = {
            "backend source": self.path(BACKEND_SOURCE),
            "App source": self.path(APP_SOURCE),
            "PreferencesPanel source": self.path(PREFERENCES_PANEL_SOURCE),
            "Tauri command source": self.path("apps/desktop/src-tauri/src/lib.rs"),
        }
        if not any(path.is_file() for label, path in sources.items() if label != "Tauri command source"):
            self.pending(
                "legacy_config_migration_surface",
                "backend/App/PreferencesPanel source files absent in reduced fixture; full repository smoke must include legacy config migration UI and API wiring evidence",
            )
            return
        missing_sources = [label for label, path in sources.items() if not path.is_file()]
        if missing_sources:
            self.fail("legacy_config_migration_surface", "missing source file(s): " + ", ".join(missing_sources))
            return

        backend_text = self.read_text(BACKEND_SOURCE)
        app_text = self.read_text(APP_SOURCE)
        panel_text = self.read_text(PREFERENCES_PANEL_SOURCE)
        tauri_text = self.read_text("apps/desktop/src-tauri/src/lib.rs")
        if backend_text is None or app_text is None or panel_text is None or tauri_text is None:
            return
        failures = [
            *missing_tauri_command_surface(tauri_text, ["preview_legacy_config_migration", "apply_legacy_config_migration"]),
            *missing_required_tokens(
                backend_text,
                "backend",
                [
                    "LegacyConfigMigrationPreviewDto",
                    "LegacyConfigMigrationApplyDto",
                    "status",
                    "errorMessage",
                    "rollbackErrors",
                    "writtenPathLabels",
                    "transactional",
                    "noWriteOnError",
                    "rollbackPerformed",
                    "rollbackSucceeded",
                    "rollbackPaths",
                    "writtenPaths",
                    "previewLegacyConfigMigration",
                    "applyLegacyConfigMigration",
                    "preview_legacy_config_migration",
                    "apply_legacy_config_migration",
                ],
            ),
            *missing_required_tokens(
                app_text,
                "App",
                [
                    "legacyConfigPath",
                    "legacyConfigStatus",
                    "legacyConfigPreview",
                    "legacyConfigApplyResult",
                    "handlePreviewLegacyConfigMigration",
                    "handleApplyLegacyConfigMigration",
                    "result.status",
                    "failed",
                    "legacyConfigApplyFailureSummary",
                    "legacyConfigApplySuccessSummary",
                    "noWriteOnError",
                    "rollbackPerformed",
                    "rollbackSucceeded",
                    "writtenPathLabels",
                    "previewLegacyConfigMigration",
                    "applyLegacyConfigMigration",
                    "loadAppPreferences",
                    "loadEngineProfilesSettings",
                ],
            ),
            *missing_required_tokens(
                panel_text,
                "PreferencesPanel",
                [
                    "legacyConfigPath",
                    "legacyConfigStatus",
                    "legacyConfigPreview",
                    "legacyConfigApplyResult",
                    "onPreviewLegacyConfigMigration",
                    "onApplyLegacyConfigMigration",
                    "Legacy config path",
                    "Preview",
                    "Apply",
                    "Migrated fields",
                    "Warnings",
                    "Migration safety",
                    "migrationSafetySummary",
                    "migrationWriteStatus",
                    "error protection enabled",
                    "written then rolled back",
                    "write attempted",
                    "legacy-config-safety-status",
                    "legacy-config-written-path-labels",
                    "legacy-config-rollback-paths",
                    "legacy-config-rollback-errors",
                    "writtenPathLabels",
                    "rollbackPaths",
                    "rollbackErrors",
                ],
            ),
        ]
        if failures:
            self.fail("legacy_config_migration_surface", "missing legacy config migration surface: " + ", ".join(failures))
            return
        self.pass_(
            "legacy_config_migration_surface",
            "legacy Java/Swing config migration exposes backend wrappers, App handlers, and PreferencesPanel transactional/rollback safety UI",
        )

    def check_runtime_asset_layout_surface(self) -> None:
        sources = {
            "backend source": self.path(BACKEND_SOURCE),
            "EngineSetupPanel source": self.path(ENGINE_SETUP_PANEL_SOURCE),
            "Tauri command source": self.path("apps/desktop/src-tauri/src/lib.rs"),
        }
        if not any(path.is_file() for label, path in sources.items() if label != "Tauri command source"):
            self.pending(
                "runtime_asset_layout_surface",
                "backend/EngineSetupPanel source files absent in reduced fixture; full repository smoke must include runtime asset layout UI and API wiring evidence",
            )
            return
        missing_sources = [label for label, path in sources.items() if not path.is_file()]
        if missing_sources:
            self.fail("runtime_asset_layout_surface", "missing source file(s): " + ", ".join(missing_sources))
            return

        backend_text = self.read_text(BACKEND_SOURCE)
        panel_text = self.read_text(ENGINE_SETUP_PANEL_SOURCE)
        tauri_text = self.read_text("apps/desktop/src-tauri/src/lib.rs")
        if backend_text is None or panel_text is None or tauri_text is None:
            return
        failures = [
            *missing_tauri_command_surface(tauri_text, ["resolve_runtime_asset_layout", "validate_runtime_asset_layout"]),
            *missing_required_tokens(
                backend_text,
                "backend",
                [
                    "RuntimeAssetPathDto",
                    "RuntimeAssetLayoutDto",
                    "RuntimeAssetValidationEntryDto",
                    "RuntimeAssetValidationDto",
                    "resourceRoots",
                    "checks",
                    "exists",
                    "placeholders",
                    "status",
                    "message",
                    "resolveRuntimeAssetLayout",
                    "validateRuntimeAssetLayout",
                    "resolve_runtime_asset_layout",
                    "validate_runtime_asset_layout",
                ],
            ),
            *missing_required_tokens(
                panel_text,
                "EngineSetupPanel",
                [
                    "validateRuntimeAssetLayout",
                    "runtimeAssetValidation",
                    "runtimeAssetStatus",
                    "runtimeAssetSummary",
                    "runtimeAssetMessages",
                    "handleCheckRuntimeAssets",
                    "Bundled/runtime assets",
                    "Refresh runtime assets",
                    "Large KataGo models are not bundled",
                    "placeholders",
                    "warnings",
                    "placeholderCount",
                    "Local asset configuration",
                    "enginePath",
                    "modelPath",
                    "configPath",
                    "checkEngineAssets",
                ],
            ),
        ]
        if failures:
            self.fail("runtime_asset_layout_surface", "missing runtime asset layout surface: " + ", ".join(failures))
            return
        self.pass_(
            "runtime_asset_layout_surface",
            "runtime asset layout backend wrappers and EngineSetupPanel bundled/runtime status surface are wired while local engine/model/config asset fields remain available",
        )

    def check_legacy_import_capture_helper_surface(self) -> None:
        frontend_sources = {
            "provider API source": self.path(PROVIDER_API_SOURCE),
            "provider domain source": self.path(PROVIDER_DOMAIN_SOURCE),
            "ProviderPanel source": self.path(PROVIDER_PANEL_SOURCE),
            "App source": self.path(APP_SOURCE),
        }
        if not any(path.is_file() for path in frontend_sources.values()):
            self.pending(
                "legacy_import_capture_helper_surface",
                "provider/App source files absent in reduced fixture; full repository smoke must include legacy import/capture helper UI and API wiring evidence",
            )
            return
        sources = {
            "Tauri command source": self.path("apps/desktop/src-tauri/src/lib.rs"),
            **frontend_sources,
        }
        missing_sources = [label for label, path in sources.items() if not path.is_file()]
        if missing_sources:
            self.fail("legacy_import_capture_helper_surface", "missing source file(s): " + ", ".join(missing_sources))
            return

        tauri_text = self.read_text("apps/desktop/src-tauri/src/lib.rs")
        api_text = self.read_text(PROVIDER_API_SOURCE)
        domain_text = self.read_text(PROVIDER_DOMAIN_SOURCE)
        panel_text = self.read_text(PROVIDER_PANEL_SOURCE)
        app_text = self.read_text(APP_SOURCE)
        if tauri_text is None or api_text is None or domain_text is None or panel_text is None or app_text is None:
            return
        failures = [
            *missing_tauri_command_surface(tauri_text, [LEGACY_IMPORT_CAPTURE_HELPER_COMMAND]),
            *missing_required_tokens(
                domain_text,
                "provider domain",
                [
                    "LegacyImportCaptureHelperKind",
                    "LegacyImportCaptureHelperStatus",
                    "LegacyImportCaptureHelperRequest",
                    "LegacyImportCaptureHelperResult",
                    "recoverable_unsupported",
                    "image_ocr",
                    "external_window_capture",
                    "external_client_capture",
                    "imported",
                    "boardReplacement",
                    "payload",
                    "image_path",
                    "image_base64",
                    "window_title",
                    "client_name",
                    "process_id",
                    "timeout_ms",
                    "metadata",
                ],
            ),
            *missing_required_tokens(
                api_text,
                "provider API",
                [
                    "previewLegacyImportCaptureHelper",
                    "legacy_import_capture_helper",
                    "legacyImportCaptureHelperFallback",
                    "recoverable_unsupported",
                    "OCR/image helper",
                    "External window/client capture",
                    "imported: false",
                    "boardReplacement",
                    "No stale, guessed, or partial board replacement",
                ],
            ),
            *missing_provider_api_invoke_command(
                api_text,
                "provider API",
                "previewLegacyImportCaptureHelper",
                LEGACY_IMPORT_CAPTURE_HELPER_COMMAND,
            ),
            *missing_required_tokens(
                panel_text,
                "ProviderPanel",
                [
                    "legacy-import-capture-helper-surface",
                    "legacy-helper-sgf-payload",
                    "legacy-helper-protocol-snapshot",
                    "legacy-helper-ocr-unsupported",
                    "legacy-helper-external-capture-unsupported",
                    "legacy-helper-status",
                    "legacy-helper-no-board-replacement",
                    "SGF/payload helper",
                    "Protocol snapshot helper",
                    "OCR/image helper",
                    "External window/client capture",
                    "recoverable unsupported",
                    "not imported",
                    "not replaced",
                    "board was not replaced",
                    "previewLegacyImportCaptureHelper",
                    "handleLegacyHelperStatus",
                    "legacyHelperResult",
                ],
            ),
            *missing_required_tokens(
                app_text,
                "App",
                ["ProviderPanel", "handleProviderImport"],
            ),
        ]
        if failures:
            self.fail("legacy_import_capture_helper_surface", "missing legacy import/capture helper surface: " + ", ".join(failures))
            return
        self.pass_(
            "legacy_import_capture_helper_surface",
            "ProviderPanel exposes scoped SGF/payload and protocol snapshot helpers plus structured recoverable unsupported OCR/external capture boundaries without board replacement claims",
        )

    def check_external_runtime_gates(self) -> None:
        self.check_tauri_runtime_ui_smoke_evidence()
        self.check_desktop_sgf_editing_ux_smoke_evidence()
        self.check_desktop_ui_click_smoke_evidence()
        self.check_legacy_shell_menu_action_smoke_evidence()
        self.check_native_menu_shortcut_smoke_evidence()
        self.check_tauri_window_runtime_smoke_evidence()
        self.check_installed_macos_app_smoke_evidence()
        self.check_native_desktop_sgf_workflow_evidence()
        self.check_katago_live_smoke_evidence()
        self.check_readboard_live_smoke_evidence()
        self.check_provider_live_smoke_evidence()
        self.check_multiplatform_packaging_smoke_evidence()

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

    def check_desktop_sgf_editing_ux_smoke_evidence(self) -> None:
        evidence_path = self.path(DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "desktop_sgf_editing_ux_smoke",
                f"TODO gate: run scripts/smoke_desktop_sgf_editing_ux.py on macOS and record {DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_desktop_sgf_editing_ux_smoke_evidence(evidence)
        if failures:
            self.pending(
                "desktop_sgf_editing_ux_smoke",
                f"{DESKTOP_SGF_EDITING_UX_SMOKE_EVIDENCE} is present but not valid scoped desktop SGF editing UX PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "desktop_sgf_editing_ux_smoke",
            f"scoped desktop SGF editing UX smoke evidence passes with {len(DESKTOP_SGF_EDITING_UX_SMOKE_REQUIRED_CHECKS)} required checks",
        )

    def check_desktop_ui_click_smoke_evidence(self) -> None:
        evidence_path = self.path(DESKTOP_UI_CLICK_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "desktop_ui_click_smoke",
                f"TODO gate: run Worker-1 browser-rendered DOM/click/screenshot smoke and record {DESKTOP_UI_CLICK_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(DESKTOP_UI_CLICK_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_desktop_ui_click_smoke_evidence(evidence)
        if failures:
            self.pending(
                "desktop_ui_click_smoke",
                f"{DESKTOP_UI_CLICK_SMOKE_EVIDENCE} is present but not valid scoped browser-rendered DOM/click/screenshot PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "desktop_ui_click_smoke",
            "scoped browser-rendered desktop UI click smoke evidence passes with DOM, click, screenshot, and boundary checks",
        )

    def check_legacy_shell_menu_action_smoke_evidence(self) -> None:
        evidence_path = self.path(DESKTOP_UI_CLICK_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "legacy_shell_menu_action_smoke",
                f"TODO gate: run Worker-1 browser-rendered LegacyShell menu action smoke and record {DESKTOP_UI_CLICK_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(DESKTOP_UI_CLICK_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = [
            *validate_desktop_ui_click_smoke_evidence(evidence),
            *validate_legacy_shell_menu_action_smoke_evidence(evidence),
        ]
        if failures:
            self.pending(
                "legacy_shell_menu_action_smoke",
                f"{DESKTOP_UI_CLICK_SMOKE_EVIDENCE} is present but not valid scoped browser-rendered LegacyShell menu action PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "legacy_shell_menu_action_smoke",
            f"scoped browser-rendered LegacyShell menu action smoke evidence passes with {len(LEGACY_SHELL_MENU_ACTION_REQUIRED_TARGETS)} menu targets",
        )

    def check_native_menu_shortcut_smoke_evidence(self) -> None:
        evidence_path = self.path(NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "native_menu_shortcut_smoke",
                f"TODO gate: record scoped macOS OS-native menu and keyboard shortcut evidence at {NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_native_menu_shortcut_smoke_evidence(evidence, self.root)
        if failures:
            self.pending(
                "native_menu_shortcut_smoke",
                f"{NATIVE_MENU_SHORTCUT_SMOKE_EVIDENCE} is present but not valid scoped macOS native menu/shortcut PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "native_menu_shortcut_smoke",
            "scoped macOS OS-native menu and keyboard shortcut evidence passes with action-id, event-bridge, input-editing, and boundary checks",
        )

    def check_tauri_window_runtime_smoke_evidence(self) -> None:
        evidence_path = self.path(TAURI_WINDOW_RUNTIME_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "tauri_window_runtime_smoke",
                f"TODO gate: run Worker-1 Tauri desktop window/runtime screenshot smoke and record {TAURI_WINDOW_RUNTIME_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(TAURI_WINDOW_RUNTIME_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_tauri_window_runtime_smoke_evidence(evidence)
        if failures:
            self.pending(
                "tauri_window_runtime_smoke",
                f"{TAURI_WINDOW_RUNTIME_SMOKE_EVIDENCE} is present but not valid scoped Tauri runtime/window screenshot PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "tauri_window_runtime_smoke",
            "scoped Tauri desktop window/runtime screenshot smoke evidence passes with source runtime save/reopen proof and boundary checks",
        )

    def check_installed_macos_app_smoke_evidence(self) -> None:
        evidence_path = self.path(INSTALLED_MACOS_APP_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "installed_macos_app_smoke",
                f"TODO gate: run Worker-1 installed macOS .app launch smoke and record {INSTALLED_MACOS_APP_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(INSTALLED_MACOS_APP_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_installed_macos_app_smoke_evidence(evidence)
        if failures:
            self.pending(
                "installed_macos_app_smoke",
                f"{INSTALLED_MACOS_APP_SMOKE_EVIDENCE} is present but not valid scoped installed macOS app launch PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "installed_macos_app_smoke",
            "scoped installed macOS .app launch smoke evidence passes with app bundle, window, screenshot, dev-server, and release-boundary checks",
        )

    def check_native_desktop_sgf_workflow_evidence(self) -> None:
        evidence_path = self.path(NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "native_desktop_sgf_workflow",
                f"TODO gate: record scoped native desktop SGF open/edit/save/reopen workflow evidence at {NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE}",
            )
            return
        evidence = self.load_json(NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE)
        if evidence is None:
            return
        failures = validate_native_desktop_sgf_workflow_evidence(evidence)
        if failures:
            self.pending(
                "native_desktop_sgf_workflow",
                f"{NATIVE_DESKTOP_SGF_WORKFLOW_EVIDENCE} is present but not valid scoped native desktop SGF workflow PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "native_desktop_sgf_workflow",
            "scoped native desktop SGF open/edit/save/reopen workflow evidence passes with native dialog, persistence, screenshot, and boundary checks",
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

    def check_multiplatform_packaging_smoke_evidence(self) -> None:
        evidence_path = self.path(MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "multiplatform_packaging_smoke",
                f"TODO gate: run scripts/smoke_multiplatform_packaging.py and record {MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_multiplatform_packaging_smoke_evidence(evidence)
        if failures:
            self.pending(
                "multiplatform_packaging_smoke",
                f"{MULTIPLATFORM_PACKAGING_SMOKE_EVIDENCE} is present but not valid scoped packaging PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "multiplatform_packaging_smoke",
            f"scoped macOS/Windows/Linux packaging smoke evidence passes with {len(MULTIPLATFORM_PACKAGING_SMOKE_REQUIRED_CHECKS)} required checks",
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
        self.check_sgf_annotation_surface()
        self.check_legacy_config_migration_surface()
        self.check_runtime_asset_layout_surface()
        self.check_legacy_import_capture_helper_surface()
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


def missing_provider_api_invoke_command(text: str, source_label: str, function_name: str, command: str) -> list[str]:
    function_match = re.search(r"\b" + re.escape(function_name) + r"\s*\([^)]*\)\s*(?::[^{]+)?\{", text)
    if not function_match:
        return [f"{source_label} missing {function_name}"]
    body_start = text.find("{", function_match.start())
    body_end = find_matching_delimiter(text, body_start, "{", "}")
    if body_end is None:
        return [f"{source_label} {function_name} body is not balanced"]
    body = text[body_start:body_end]
    invoke_pattern = re.compile(r"\binvoke(?:\s*<[^>]+>)?\s*\(\s*['\"]" + re.escape(command) + r"['\"]")
    if not invoke_pattern.search(body):
        return [f"{source_label} {function_name} must invoke {command}"]
    return []


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


def validate_desktop_sgf_editing_ux_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != DESKTOP_SGF_EDITING_UX_SMOKE_SCHEMA:
        failures.append(f"schema must be {DESKTOP_SGF_EDITING_UX_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    if evidence.get("collectionMethod") != "source_static_plus_tauri_runtime_chain":
        failures.append("collectionMethod must be source_static_plus_tauri_runtime_chain")
    if evidence.get("runtimeDomObserved") is not False:
        failures.append("runtimeDomObserved must be false")
    if evidence.get("screenshotObserved") is not False:
        failures.append("screenshotObserved must be false")
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    missing = [name for name in DESKTOP_SGF_EDITING_UX_SMOKE_REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in DESKTOP_SGF_EDITING_UX_SMOKE_REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_desktop_sgf_editing_ux_surface(evidence))
    failures.extend(validate_desktop_sgf_editing_ux_coverage(evidence))
    failures.extend(validate_desktop_sgf_editing_ux_boundaries(evidence))
    return failures


def validate_desktop_sgf_editing_ux_surface(evidence: dict[str, Any]) -> list[str]:
    surface = evidence.get("uiUxSurface")
    if not isinstance(surface, dict):
        return ["uiUxSurface must be an object"]
    failures: list[str] = []
    for key in ("legacyShellVisible", "treePanelVisible", "annotationEditorVisible"):
        if surface.get(key) is not True:
            failures.append(f"uiUxSurface.{key} must be true")
    toolbar = surface.get("toolbarMenuControls")
    if not isinstance(toolbar, dict):
        failures.append("uiUxSurface.toolbarMenuControls must be an object")
    else:
        if toolbar.get("visible") is not True:
            failures.append("uiUxSurface.toolbarMenuControls.visible must be true")
        failures.extend(
            missing_string_members(
                toolbar.get("toolbarControls"),
                ["Open", "Save", "Save As", "Import", "Sample", "Parse", "Review"],
                "uiUxSurface.toolbarMenuControls.toolbarControls",
            )
        )
        failures.extend(
            missing_string_members(
                toolbar.get("menuControls"),
                ["File/Open", "File/Save", "File/Save As", "View/Candidates", "Engine/Profiles", "Tools/Preferences"],
                "uiUxSurface.toolbarMenuControls.menuControls",
            )
        )
    selected = surface.get("selectedNodeUxState")
    if not isinstance(selected, dict):
        failures.append("uiUxSurface.selectedNodeUxState must be an object")
    else:
        for key in ("selectedNodeVisible", "commentEditorVisible", "moveEditModeVisible", "deleteControlVisible", "reorderControlsVisible"):
            if selected.get(key) is not True:
                failures.append(f"uiUxSurface.selectedNodeUxState.{key} must be true")
    dirty_saved = surface.get("dirtySavedStatus")
    if not isinstance(dirty_saved, dict):
        failures.append("uiUxSurface.dirtySavedStatus must be an object")
    else:
        for key in ("dirtyIndicatorVisible", "savedIndicatorVisible", "canSaveReflectsDirty", "dirtySetAfterEdits", "savedAfterReadback"):
            if dirty_saved.get(key) is not True:
                failures.append(f"uiUxSurface.dirtySavedStatus.{key} must be true")
    if surface.get("nativeDialogClickCovered") is not False:
        failures.append("uiUxSurface.nativeDialogClickCovered must be false")
    return failures


def validate_desktop_sgf_editing_ux_coverage(evidence: dict[str, Any]) -> list[str]:
    coverage = evidence.get("coverage")
    if not isinstance(coverage, dict):
        return ["coverage must be an object"]
    failures: list[str] = []
    for key in (
        "treeNavigation",
        "commentEdit",
        "propertyEdit",
        "annotationEdit",
        "appendMove",
        "editMove",
        "reorderVariation",
        "deleteNode",
        "saveReadbackReopen",
    ):
        if coverage.get(key) is not True:
            failures.append(f"coverage.{key} must be true")
    return failures


def validate_desktop_sgf_editing_ux_boundaries(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    source = evidence.get("sourceRuntimeEvidence")
    if not isinstance(source, dict):
        failures.append("sourceRuntimeEvidence must be an object")
    else:
        if source.get("valid") is not True:
            failures.append("sourceRuntimeEvidence.valid must be true")
        if source.get("schema") != TAURI_RUNTIME_UI_SMOKE_SCHEMA:
            failures.append(f"sourceRuntimeEvidence.schema must be {TAURI_RUNTIME_UI_SMOKE_SCHEMA}")
    boundaries = evidence.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries must be an object")
    else:
        for key in (
            "nativeDialogClickCovered",
            "fullNativeDialogProof",
            "ocrCaptureCovered",
            "externalClientWindowCaptureCovered",
            "fullLegacyParityCovered",
        ):
            if boundaries.get(key) is not False:
                failures.append(f"boundaries.{key} must be false")
    return failures


def validate_desktop_ui_click_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != DESKTOP_UI_CLICK_SMOKE_SCHEMA:
        failures.append(f"schema must be {DESKTOP_UI_CLICK_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    if evidence.get("browserDomObserved") is not True:
        failures.append("browserDomObserved must be true")
    if evidence.get("screenshotObserved") is not True:
        failures.append("screenshotObserved must be true")
    if evidence.get("clickObserved") is not True:
        failures.append("clickObserved must be true")
    failures.extend(validate_desktop_ui_click_screenshots(evidence.get("screenshots")))
    failures.extend(validate_desktop_ui_click_clicked_controls(evidence.get("clickedControls")))
    failures.extend(validate_desktop_ui_click_visible_assertions(evidence.get("visibleAssertions")))
    failures.extend(validate_desktop_ui_click_boundaries(evidence.get("boundaries")))
    return failures


def validate_native_menu_shortcut_smoke_evidence(evidence: Any, root: Path = ROOT) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != NATIVE_MENU_SHORTCUT_SMOKE_SCHEMA:
        failures.append(f"schema must be {NATIVE_MENU_SHORTCUT_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    if evidence.get("eventName") != NATIVE_MENU_EVENT_NAME:
        failures.append(f"eventName must be {NATIVE_MENU_EVENT_NAME}")
    for key in NATIVE_MENU_SHORTCUT_REQUIRED_TRUE_FIELDS:
        if evidence.get(key) is not True:
            failures.append(f"{key} must be true")
    for key in NATIVE_MENU_SHORTCUT_REQUIRED_FALSE_FIELDS:
        if evidence.get(key) is not False:
            failures.append(f"{key} must be false")

    checks = evidence.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        check_by_name: dict[str, Any] = {}
    else:
        check_by_name = {
            check.get("name"): check
            for check in checks
            if isinstance(check, dict) and isinstance(check.get("name"), str)
        }
        missing = [name for name in NATIVE_MENU_SHORTCUT_SMOKE_REQUIRED_CHECKS if name not in check_by_name]
        not_pass = [
            name
            for name in NATIVE_MENU_SHORTCUT_SMOKE_REQUIRED_CHECKS
            if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
        ]
        if missing:
            failures.append("missing required checks: " + ", ".join(missing))
        if not_pass:
            failures.append("required checks not pass: " + ", ".join(not_pass))

    failures.extend(validate_native_menu_shortcut_checks(check_by_name))
    failures.extend(validate_native_menu_shortcut_evidence_groups(evidence))
    failures.extend(validate_native_menu_shortcut_source_facts(evidence, root))
    failures.extend(validate_native_menu_shortcut_forbidden_claims(evidence))
    return failures


def validate_native_menu_shortcut_checks(check_by_name: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_flags = {
        "native_menu_surface": "nativeMenuSurface",
        "native_menu_event_bridge": "nativeMenuEventBridge",
        "keyboard_shortcut_surface": "keyboardShortcutSurface",
        "action_ids_aligned": "actionIdsAligned",
        "input_editing_safe": "inputEditingSafe",
    }
    for check_name, flag in expected_flags.items():
        evidence = check_evidence(check_by_name.get(check_name))
        if evidence is None:
            failures.append(f"{check_name} evidence must be an object")
            continue
        if evidence.get(flag) is not True:
            failures.append(f"{check_name}.{flag} must be true")
    boundary_evidence = check_evidence(check_by_name.get("scope_boundaries"))
    if boundary_evidence is None:
        failures.append("scope_boundaries evidence must be an object")
    else:
        for key in NATIVE_MENU_SHORTCUT_REQUIRED_FALSE_FIELDS:
            if boundary_evidence.get(key) is not False:
                failures.append(f"scope_boundaries.{key} must be false")
    return failures


def validate_native_menu_shortcut_evidence_groups(evidence: dict[str, Any]) -> list[str]:
    groups = evidence.get("groups")
    if not isinstance(groups, list) or not all(isinstance(group, str) for group in groups):
        return ["groups must be a list of strings"]
    if groups != NATIVE_MENU_GROUPS:
        return ["groups must exactly equal " + ", ".join(NATIVE_MENU_GROUPS)]
    return []


def validate_native_menu_shortcut_source_facts(evidence: dict[str, Any], root: Path) -> list[str]:
    failures: list[str] = []
    rust_path = root / "apps/desktop/src-tauri/src/lib.rs"
    frontend_path = root / BACKEND_SOURCE
    actions_path = root / LEGACY_ACTIONS_SOURCE
    rust_text = rust_path.read_text(encoding="utf-8") if rust_path.is_file() else ""
    frontend_text = frontend_path.read_text(encoding="utf-8") if frontend_path.is_file() else ""
    actions_text = actions_path.read_text(encoding="utf-8") if actions_path.is_file() else ""
    if not rust_text:
        return ["Rust Tauri source missing for native menu source-fact validation"]
    if not frontend_text:
        return ["frontend backend source missing for native menu source-fact validation"]
    if not actions_text:
        return ["legacyActions source missing for native menu source-fact validation"]

    rust_event_name = extract_rust_string_const(rust_text, "NATIVE_MENU_EVENT_NAME")
    if rust_event_name != NATIVE_MENU_EVENT_NAME:
        failures.append(f"Rust NATIVE_MENU_EVENT_NAME must be {NATIVE_MENU_EVENT_NAME}")
    frontend_event_names = extract_frontend_legacy_menu_event_names(frontend_text)
    if NATIVE_MENU_EVENT_NAME not in frontend_event_names:
        failures.append(f"frontend listener must include {NATIVE_MENU_EVENT_NAME}")
    if rust_event_name and rust_event_name not in frontend_event_names:
        failures.append("Rust NATIVE_MENU_EVENT_NAME must equal a frontend listened event name")
    if not has_tauri_command_function(rust_text, "native_menu_contract"):
        failures.append("native_menu_contract command function missing")
    if not command_registered_in_handler(rust_text, "native_menu_contract"):
        failures.append("native_menu_contract invoke handler missing")

    rust_actions = parse_rust_native_menu_actions(rust_text)
    frontend_actions = parse_legacy_action_matrix(actions_text)
    if not rust_actions:
        failures.append("Rust native menu actions missing")
    if not frontend_actions:
        failures.append("frontend legacyActionMatrix actions missing")
    if rust_actions and frontend_actions:
        rust_ids = [action["action_id"] for action in rust_actions]
        frontend_ids = [action["id"] for action in frontend_actions]
        if rust_ids != frontend_ids:
            failures.append("Rust native menu action ids must exactly align with frontend legacyActionMatrix action ids")
        rust_groups = unique_ordered([action["group"] for action in rust_actions])
        frontend_groups = unique_ordered([action["group"] for action in frontend_actions])
        if rust_groups != NATIVE_MENU_GROUPS:
            failures.append("Rust native menu groups must exactly equal " + ", ".join(NATIVE_MENU_GROUPS))
        if frontend_groups != NATIVE_MENU_GROUPS:
            failures.append("frontend legacyActionMatrix groups must exactly equal " + ", ".join(NATIVE_MENU_GROUPS))
        evidence_ids = evidence.get("actionIds")
        if not isinstance(evidence_ids, list) or not all(isinstance(action_id, str) for action_id in evidence_ids):
            failures.append("actionIds must be a list of strings")
        elif evidence_ids != rust_ids:
            failures.append("actionIds must exactly match Rust/frontend canonical action ids")
    return failures


def validate_native_menu_shortcut_forbidden_claims(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    def walk(value: Any, key_path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                next_path = f"{key_path}.{key}" if key_path else str(key)
                if key in NATIVE_MENU_SHORTCUT_FORBIDDEN_TRUE_FIELDS and child is True:
                    failures.append(f"{next_path} {NATIVE_MENU_SHORTCUT_FORBIDDEN_TRUE_FIELDS[key]}")
                walk(child, next_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{key_path}[{index}]")

    walk(evidence, "")
    return failures


def validate_desktop_ui_click_screenshots(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["screenshots must be a list"]
    failures: list[str] = []
    if len(value) < 2:
        failures.append("screenshots must include at least two records")
    for index, screenshot in enumerate(value):
        if not isinstance(screenshot, dict):
            failures.append(f"screenshots[{index}] must be an object")
            continue
        sha256 = screenshot.get("sha256")
        if not is_sha256_hex(sha256):
            failures.append(f"screenshots[{index}].sha256 must be a 64-character hex sha256")
        label = first_present(screenshot, "label", "name", "step")
        if not isinstance(label, str) or not label.strip():
            failures.append(f"screenshots[{index}] must include label/name/step")
        path = screenshot.get("path")
        if not isinstance(path, str) or not path.strip():
            failures.append(f"screenshots[{index}].path must be a stable repo-relative or non-local path")
        elif not is_stable_artifact_path(path):
            failures.append(f"screenshots[{index}].path must not be a local absolute path")
    return failures


def validate_desktop_ui_click_clicked_controls(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["clickedControls must be a list"]
    failures: list[str] = []
    if not value:
        failures.append("clickedControls must include at least one control")
    for index, control in enumerate(value):
        if isinstance(control, str):
            if not control.strip():
                failures.append(f"clickedControls[{index}] must be non-empty")
            continue
        if not isinstance(control, dict):
            failures.append(f"clickedControls[{index}] must be a string or object")
            continue
        label = first_present(control, "label", "name", "control", "testId", "selector")
        if not isinstance(label, str) or not label.strip():
            failures.append(f"clickedControls[{index}] must include label/name/control/testId/selector")
        if "clicked" in control and control.get("clicked") is not True:
            failures.append(f"clickedControls[{index}].clicked must be true when present")
    return failures


def validate_desktop_ui_click_visible_assertions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["visibleAssertions must be a list"]
    failures: list[str] = []
    if not value:
        failures.append("visibleAssertions must include at least one assertion")
    for index, assertion in enumerate(value):
        if isinstance(assertion, str):
            if not assertion.strip():
                failures.append(f"visibleAssertions[{index}] must be non-empty")
            continue
        if not isinstance(assertion, dict):
            failures.append(f"visibleAssertions[{index}] must be a string or object")
            continue
        label = first_present(assertion, "label", "name", "selector", "text", "testId")
        if not isinstance(label, str) or not label.strip():
            failures.append(f"visibleAssertions[{index}] must include label/name/selector/text/testId")
        status = str(assertion.get("status", "pass")).lower()
        if status not in {"pass", "passed"}:
            failures.append(f"visibleAssertions[{index}].status must be pass when present")
        if "visible" in assertion and assertion.get("visible") is not True:
            failures.append(f"visibleAssertions[{index}].visible must be true when present")
    return failures


def validate_desktop_ui_click_boundaries(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["boundaries must be an object"]
    failures: list[str] = []
    if value.get("nativeFileDialogCovered") is not False:
        failures.append("boundaries.nativeFileDialogCovered must be false")
    tauri_webview_observed = value.get("tauriWebviewDomObserved")
    if tauri_webview_observed is False:
        return failures
    if tauri_webview_observed is not True:
        failures.append("boundaries.tauriWebviewDomObserved must be false unless true proof is recorded")
        return failures
    if value.get("tauriWebviewProof") is not True:
        failures.append("boundaries.tauriWebviewProof must be true when tauriWebviewDomObserved is true")
    proof_detail = first_present(value, "tauriWebviewProofDetail", "tauriWebviewEvidence", "tauriWebviewDomEvidence")
    if not non_empty_proof(proof_detail):
        failures.append("boundaries.tauriWebview proof detail must be non-empty when tauriWebviewDomObserved is true")
    return failures


def validate_legacy_shell_menu_action_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    section = legacy_shell_menu_action_section(evidence)
    if section is None:
        return ["legacyShellMenuActionSmoke section or legacy_shell_menu_action_smoke check details must be present"]
    if not isinstance(section, dict):
        return ["legacyShellMenuActionSmoke must be an object"]
    failures: list[str] = []
    if str(section.get("status", "")).lower() != "pass":
        failures.append("legacyShellMenuActionSmoke.status must be pass")
    failures.extend(validate_legacy_shell_menu_clicked_controls(section.get("clickedControls")))
    failures.extend(validate_legacy_shell_menu_active_targets(section.get("activeTargets")))
    failures.extend(validate_legacy_shell_menu_visible_assertions(section.get("visibleAssertions")))
    failures.extend(validate_legacy_shell_menu_boundaries(section.get("boundaries")))
    check_status = check_status_by_name(evidence.get("checks")).get("legacy_shell_menu_action_smoke")
    if check_status is not None and check_status not in {"pass", "passed"}:
        failures.append("checks.legacy_shell_menu_action_smoke status must be pass when present")
    return failures


def legacy_shell_menu_action_section(evidence: dict[str, Any]) -> Any:
    section = evidence.get("legacyShellMenuActionSmoke")
    if section is not None:
        return section
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        return None
    for check in checks:
        if isinstance(check, dict) and check.get("name") == "legacy_shell_menu_action_smoke":
            details = check.get("details")
            if isinstance(details, dict) and any(key in details for key in ("clickedControls", "activeTargets", "visibleAssertions", "boundaries")):
                return details
    return None


def validate_legacy_shell_menu_clicked_controls(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["legacyShellMenuActionSmoke.clickedControls must be a list"]
    failures: list[str] = []
    action_to_control = {legacy_menu_action_key(control): control for control in value if isinstance(control, dict)}
    for action, _target in LEGACY_SHELL_MENU_ACTION_REQUIRED_TARGETS:
        control = action_to_control.get(legacy_menu_key(action))
        if not isinstance(control, dict):
            failures.append(f"legacyShellMenuActionSmoke.clickedControls missing {action}")
            continue
        if control.get("clicked") is not True:
            failures.append(f"legacyShellMenuActionSmoke.clickedControls.{action}.clicked must be true")
        if "visible" in control and control.get("visible") is not True:
            failures.append(f"legacyShellMenuActionSmoke.clickedControls.{action}.visible must be true when present")
    return failures


def validate_legacy_shell_menu_active_targets(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["legacyShellMenuActionSmoke.activeTargets must be a list"]
    failures: list[str] = []
    target_to_entry = {entry.get("target"): entry for entry in value if isinstance(entry, dict)}
    for action, target in LEGACY_SHELL_MENU_ACTION_REQUIRED_TARGETS:
        entry = target_to_entry.get(target)
        if not isinstance(entry, dict):
            failures.append(f"legacyShellMenuActionSmoke.activeTargets missing {target}")
            continue
        if entry.get("visible") is not True:
            failures.append(f"legacyShellMenuActionSmoke.activeTargets.{target}.visible must be true")
        if entry.get("active") is not True:
            failures.append(f"legacyShellMenuActionSmoke.activeTargets.{target}.active must be true")
        if entry.get("status") != "focused":
            failures.append(f"legacyShellMenuActionSmoke.activeTargets.{target}.status must be focused")
        if entry.get("lastAction") != action:
            failures.append(f"legacyShellMenuActionSmoke.activeTargets.{target}.lastAction must be {action}")
        selector = entry.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            failures.append(f"legacyShellMenuActionSmoke.activeTargets.{target}.selector must be non-empty")
    return failures


def validate_legacy_shell_menu_visible_assertions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["legacyShellMenuActionSmoke.visibleAssertions must be a list"]
    failures: list[str] = []
    text = "\n".join(normalize_legacy_menu_assertion_text(assertion) for assertion in value)
    for action, target in LEGACY_SHELL_MENU_ACTION_REQUIRED_TARGETS:
        if legacy_menu_key(action) not in legacy_menu_key(text) and legacy_menu_key(target) not in legacy_menu_key(text):
            failures.append(f"legacyShellMenuActionSmoke.visibleAssertions missing {action} target")
    for index, assertion in enumerate(value):
        if not isinstance(assertion, dict):
            failures.append(f"legacyShellMenuActionSmoke.visibleAssertions[{index}] must be an object")
            continue
        if assertion.get("visible") is not True:
            failures.append(f"legacyShellMenuActionSmoke.visibleAssertions[{index}].visible must be true")
        status = str(assertion.get("status", "pass")).lower()
        if status not in {"pass", "passed"}:
            failures.append(f"legacyShellMenuActionSmoke.visibleAssertions[{index}].status must be pass when present")
    return failures


def validate_legacy_shell_menu_boundaries(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["legacyShellMenuActionSmoke.boundaries must be an object"]
    failures: list[str] = []
    if value.get("browserRenderedDomObserved") is not True:
        failures.append("legacyShellMenuActionSmoke.boundaries.browserRenderedDomObserved must be true")
    for key in ("nativeFileDialogCovered", "tauriWebviewDomObserved", "tauriNativeDialogProof", "fullLegacyParityCovered"):
        if value.get(key) is not False:
            failures.append(f"legacyShellMenuActionSmoke.boundaries.{key} must be false")
    for key in ("osNativeMenuCovered", "fullShortcutParityCovered", "fullLayoutParityCovered"):
        if value.get(key) is not False:
            failures.append(f"legacyShellMenuActionSmoke.boundaries.{key} must be false")
    return failures


def legacy_menu_action_key(control: dict[str, Any]) -> str:
    action = control.get("action")
    if isinstance(action, str) and action.strip():
        return legacy_menu_key(action)
    group = control.get("group")
    label = control.get("label")
    if isinstance(group, str) and isinstance(label, str):
        return legacy_menu_key(f"{group}:{label}")
    return legacy_menu_key(first_present(control, "name", "control", "testId", "selector") or "")


def legacy_menu_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def normalize_legacy_menu_assertion_text(assertion: Any) -> str:
    if isinstance(assertion, str):
        return assertion
    if not isinstance(assertion, dict):
        return ""
    parts = [first_present(assertion, "name", "label", "target", "selector", "testId"), assertion.get("text")]
    return " ".join(part for part in parts if isinstance(part, str))


def check_status_by_name(checks: Any) -> dict[str, str]:
    if not isinstance(checks, list):
        return {}
    statuses: dict[str, str] = {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = check.get("name")
        if isinstance(name, str) and name:
            statuses[name] = str(check.get("status", "")).lower()
    return statuses


def validate_tauri_window_runtime_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != TAURI_WINDOW_RUNTIME_SMOKE_SCHEMA:
        failures.append(f"schema must be {TAURI_WINDOW_RUNTIME_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    if evidence.get("tauriRuntimeObserved") is not True:
        failures.append("tauriRuntimeObserved must be true")
    if evidence.get("tauriWindowScreenshotObserved") is not True:
        failures.append("tauriWindowScreenshotObserved must be true")
    if evidence.get("browserFallbackUsed") is not False:
        failures.append("browserFallbackUsed must be false")
    if evidence.get("webviewDomClickCovered") is not False:
        failures.append("webviewDomClickCovered must be false")
    if evidence.get("nativeDialogClickCovered") is not False:
        failures.append("nativeDialogClickCovered must be false")
    failures.extend(validate_tauri_window_runtime_boundaries(evidence.get("boundaries")))
    failures.extend(validate_tauri_window_runtime_screenshots(evidence))
    failures.extend(validate_tauri_window_runtime_source_evidence(evidence.get("sourceRuntimeEvidence")))
    failures.extend(validate_tauri_window_runtime_save_reopen_proof(evidence))
    return failures


def validate_tauri_window_runtime_boundaries(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, dict):
        return ["boundaries must be an object when present"]
    failures: list[str] = []
    for key in ("browserFallbackUsed", "webviewDomClickCovered", "nativeDialogClickCovered"):
        if value.get(key) is not False:
            failures.append(f"boundaries.{key} must be false")
    if "nativeFileDialogCovered" in value and value.get("nativeFileDialogCovered") is not False:
        failures.append("boundaries.nativeFileDialogCovered must be false when present")
    return failures


def validate_tauri_window_runtime_screenshots(evidence: dict[str, Any]) -> list[str]:
    screenshots = first_present(evidence, "screenshots", "windowScreenshots", "tauriWindowScreenshots")
    if screenshots is None and isinstance(evidence.get("screenshot"), dict):
        screenshots = [evidence["screenshot"]]
    if not isinstance(screenshots, list):
        return ["screenshots must be a list"]
    failures: list[str] = []
    if not screenshots:
        failures.append("screenshots must include at least one Tauri window screenshot")
    for index, screenshot in enumerate(screenshots):
        if not isinstance(screenshot, dict):
            failures.append(f"screenshots[{index}] must be an object")
            continue
        sha256 = screenshot.get("sha256")
        if not is_sha256_hex(sha256):
            failures.append(f"screenshots[{index}].sha256 must be a 64-character hex sha256")
        label = first_present(screenshot, "label", "name", "step")
        if not isinstance(label, str) or not label.strip():
            failures.append(f"screenshots[{index}] must include label/name/step")
        path = screenshot.get("path")
        if not isinstance(path, str) or not path.strip():
            failures.append(f"screenshots[{index}].path must be a stable repo-relative or non-local path")
        elif not is_stable_artifact_path(path):
            failures.append(f"screenshots[{index}].path must not be a local absolute path")
    return failures


def validate_tauri_window_runtime_source_evidence(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["sourceRuntimeEvidence must be an object"]
    failures: list[str] = []
    if value.get("schema") != TAURI_RUNTIME_UI_SMOKE_SCHEMA:
        failures.append(f"sourceRuntimeEvidence.schema must be {TAURI_RUNTIME_UI_SMOKE_SCHEMA}")
    if str(value.get("status", "")).lower() != "pass":
        failures.append("sourceRuntimeEvidence.status must be pass")
    if "valid" in value and value.get("valid") is not True:
        failures.append("sourceRuntimeEvidence.valid must be true when present")
    return failures


def validate_tauri_window_runtime_save_reopen_proof(evidence: dict[str, Any]) -> list[str]:
    candidates: list[dict[str, Any]] = []
    for candidate in (
        evidence,
        evidence.get("saveReopenSemanticProof"),
        evidence.get("saveReopenRuntimeProof"),
        evidence.get("sourceRuntimeEvidence"),
    ):
        if isinstance(candidate, dict):
            candidates.append(candidate)
    for candidate in candidates:
        top_level_failures = validate_top_level_save_reopen_proof(candidate)
        semantic_failures = validate_two_launch_save_reopen_evidence(candidate)
        if not top_level_failures and not semantic_failures:
            return []
    return [
        "save/reopen semantic proof must include valid firstLaunch, secondLaunch, saveReopenProof, reopen, and afterReopen fields"
    ]


def validate_installed_macos_app_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != INSTALLED_MACOS_APP_SMOKE_SCHEMA:
        failures.append(f"schema must be {INSTALLED_MACOS_APP_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    if evidence.get("launched") is not True:
        failures.append("launched must be true")
    if evidence.get("windowObserved") is not True:
        failures.append("windowObserved must be true")
    if evidence.get("screenshotObserved") is not True:
        failures.append("screenshotObserved must be true")
    for key in ("devServerAbsent", "productionSigned", "notarized", "releasePublished"):
        expected = True if key == "devServerAbsent" else False
        if evidence.get(key) is not expected:
            failures.append(f"{key} must be {str(expected).lower()}")
    failures.extend(validate_installed_macos_app_bundle(evidence.get("appBundle"), evidence))
    failures.extend(validate_installed_macos_app_artifact_paths(evidence))
    failures.extend(validate_installed_macos_app_dev_server_boundaries(evidence))
    failures.extend(validate_installed_macos_app_boundaries(evidence.get("boundaries")))
    failures.extend(validate_installed_macos_app_screenshots(evidence))
    failures.extend(validate_installed_macos_app_termination(evidence))
    return failures


def validate_installed_macos_app_bundle(value: Any, evidence: dict[str, Any]) -> list[str]:
    if not isinstance(value, dict):
        return ["appBundle must be an object"]
    failures: list[str] = []
    if first_present(value, "exists", "present", "bundleExists", "artifactPresent") is not True:
        failures.append("appBundle.exists must be true")
    path = first_present(value, "path", "bundlePath", "name", "fileName")
    if not isinstance(path, str) or not path.strip():
        failures.append("appBundle must include path/name metadata")
    size = first_present(value, "sizeBytes", "size_bytes", "appSizeBytes", "app_size_bytes", "bundleSizeBytes")
    if size is None:
        size = first_present(evidence, "appSizeBytes", "app_size_bytes", "bundleSizeBytes")
    if not positive_number(size):
        failures.append("appBundle must include positive app size")
    checksum = first_present(value, "sha256", "appSha256", "bundleSha256", "hash")
    if checksum is None:
        checksum = first_present(evidence, "appSha256", "app_sha256", "bundleSha256", "sha256")
    if not is_sha256_hex(checksum):
        failures.append("appBundle must include 64-character hex sha256")
    return failures


def validate_installed_macos_app_artifact_paths(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    def check_path(label: str, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, str) or not value.strip():
            failures.append(f"{label} must be a stable repo-relative or non-local path")
        elif not is_stable_artifact_path(value):
            failures.append(f"{label} must not be a local absolute path")

    check_path("appBundlePath", evidence.get("appBundlePath"))
    app_bundle = evidence.get("appBundle")
    if isinstance(app_bundle, dict):
        check_path("appBundle.path", first_present(app_bundle, "path", "bundlePath"))
    bundle = evidence.get("bundle")
    if isinstance(bundle, dict):
        for key in ("app", "binary", "dmg", "infoPlist"):
            artifact = bundle.get(key)
            if isinstance(artifact, dict):
                check_path(f"bundle.{key}.path", artifact.get("path"))
        dmgs = bundle.get("dmgs")
        if isinstance(dmgs, list):
            for index, dmg in enumerate(dmgs):
                if isinstance(dmg, dict):
                    check_path(f"bundle.dmgs[{index}].path", dmg.get("path"))
    return failures


def validate_installed_macos_app_dev_server_boundaries(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    preflight = evidence.get("devServerPreflight")
    if isinstance(preflight, dict):
        if preflight.get("reachableBeforeLaunch") is True:
            failures.append("devServerPreflight.reachableBeforeLaunch must be false")
        if preflight.get("runnerStartedDevServer") is True:
            failures.append("devServerPreflight.runnerStartedDevServer must be false")
    if evidence.get("runnerStartedDevServer") is True:
        failures.append("runnerStartedDevServer must be false")
    if evidence.get("runnerStartedViteDevServer") is True:
        failures.append("runnerStartedViteDevServer must be false")
    boundaries = evidence.get("boundaries")
    if isinstance(boundaries, dict) and boundaries.get("viteDevServerStarted") is True:
        failures.append("boundaries.viteDevServerStarted must be false")
    return failures


def validate_installed_macos_app_boundaries(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, dict):
        return ["boundaries must be an object when present"]
    failures: list[str] = []
    for key in ("nativeDialogClickCovered", "webviewDomClickCovered"):
        if value.get(key) is not False:
            failures.append(f"boundaries.{key} must be false")
    return failures


def validate_installed_macos_app_screenshots(evidence: dict[str, Any]) -> list[str]:
    screenshots = first_present(evidence, "screenshots", "windowScreenshots", "appScreenshots")
    if screenshots is None and isinstance(evidence.get("screenshot"), dict):
        screenshots = [evidence["screenshot"]]
    if not isinstance(screenshots, list):
        return ["screenshots must be a list"]
    failures: list[str] = []
    if not screenshots:
        failures.append("screenshots must include at least one installed app screenshot")
    for index, screenshot in enumerate(screenshots):
        if not isinstance(screenshot, dict):
            failures.append(f"screenshots[{index}] must be an object")
            continue
        sha256 = screenshot.get("sha256")
        if not is_sha256_hex(sha256):
            failures.append(f"screenshots[{index}].sha256 must be a 64-character hex sha256")
        label = first_present(screenshot, "label", "name", "step")
        if not isinstance(label, str) or not label.strip():
            failures.append(f"screenshots[{index}] must include label/name/step")
        path = screenshot.get("path")
        if not isinstance(path, str) or not path.strip():
            failures.append(f"screenshots[{index}].path must be a stable repo-relative or non-local path")
        elif not is_stable_artifact_path(path):
            failures.append(f"screenshots[{index}].path must not be a local absolute path")
    return failures


def validate_installed_macos_app_termination(evidence: dict[str, Any]) -> list[str]:
    termination = first_present(evidence, "termination", "terminate", "exit", "processExit")
    if isinstance(termination, dict):
        if first_present(termination, "success", "terminated", "exited", "ok") is True:
            return []
        status = str(first_present(termination, "status", "result") or "").lower()
        exit_code = first_present(termination, "exitCode", "exit_code", "code")
        if status in {"pass", "passed", "success"} and (exit_code in (None, 0)):
            return []
        if exit_code == 0 and first_present(termination, "forced", "forceKilled", "force_killed") is not True:
            return []
    if first_present(evidence, "terminated", "terminateSuccess", "exitSuccess", "exited") is True:
        return []
    return ["exit/terminate success must be recorded"]


def validate_native_desktop_sgf_workflow_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != NATIVE_DESKTOP_SGF_WORKFLOW_SCHEMA:
        failures.append(f"schema must be {NATIVE_DESKTOP_SGF_WORKFLOW_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    app_mode = evidence.get("appMode")
    if app_mode not in {"tauri-dev", "packaged-macos-app"}:
        failures.append("appMode must be tauri-dev or packaged-macos-app")
    collection_method = evidence.get("collectionMethod")
    if collection_method not in NATIVE_DESKTOP_SGF_WORKFLOW_COLLECTION_METHODS:
        failures.append("collectionMethod must be explicit")

    for key in NATIVE_DESKTOP_SGF_WORKFLOW_REQUIRED_BOOLEANS:
        if evidence.get(key) not in {True, False}:
            failures.append(f"{key} must be a boolean")
    for key in ("nativeDialogOpenCovered", "nativeDialogSaveCovered"):
        if evidence.get(key) is not True:
            failures.append(f"{key} must be true")
    for key in ("fullLegacyParityCovered", "productionSigned", "notarized", "releasePublished"):
        if evidence.get(key) is not False:
            failures.append(f"{key} must be false")
    if evidence.get("webviewDomAutomationCovered") is not False:
        failures.append("webviewDomAutomationCovered must be false for this scoped batch")
    if evidence.get("fullAutomationCovered") is True and native_workflow_has_manual_assisted_step(evidence):
        failures.append("fullAutomationCovered must be false when manual-assisted steps are present")

    checks = evidence.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        check_by_name: dict[str, Any] = {}
    else:
        check_by_name = {
            check.get("name"): check
            for check in checks
            if isinstance(check, dict) and isinstance(check.get("name"), str)
        }
        missing = [name for name in NATIVE_DESKTOP_SGF_WORKFLOW_REQUIRED_CHECKS if name not in check_by_name]
        not_pass = [
            name
            for name in NATIVE_DESKTOP_SGF_WORKFLOW_REQUIRED_CHECKS
            if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
        ]
        if missing:
            failures.append("missing required checks: " + ", ".join(missing))
        if not_pass:
            failures.append("required checks not pass: " + ", ".join(not_pass))

    failures.extend(validate_native_desktop_workflow_dialog_coverage(evidence, check_by_name))
    failures.extend(validate_native_desktop_workflow_screenshots(evidence))
    failures.extend(validate_native_desktop_workflow_reopen_state(check_by_name.get("reopen_state_verified")))
    failures.extend(validate_native_desktop_workflow_scope_boundaries(evidence))
    failures.extend(validate_native_desktop_workflow_paths(evidence))
    return failures


def native_workflow_has_manual_assisted_step(evidence: dict[str, Any]) -> bool:
    if evidence.get("collectionMethod") == "manual_assisted_native_desktop_workflow":
        return True
    for value in (evidence.get("steps"), evidence.get("checks")):
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            details = check_evidence(item) or item
            method = first_present(details, "method", "collectionMethod", "interactionMethod")
            if isinstance(method, str) and "manual" in method.lower():
                return True
            operator = first_present(details, "operator", "operatorId", "operatorName")
            if isinstance(operator, str) and operator.strip():
                return True
    return False


def validate_native_desktop_workflow_dialog_coverage(
    evidence: dict[str, Any],
    check_by_name: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if evidence.get("nativeDialogOpenCovered") is True:
        failures.extend(
            validate_native_desktop_workflow_dialog_step(
                check_by_name.get("native_open_dialog"),
                "native_open_dialog",
                ("openedPath", "openedSgfPath", "opened_sgf_path", "sgfPath", "inputSgfPath"),
            )
        )
    if evidence.get("nativeDialogSaveCovered") is True:
        failures.extend(
            validate_native_desktop_workflow_dialog_step(
                check_by_name.get("save_or_save_as"),
                "save_or_save_as",
                ("savedPath", "savedSgfPath", "saved_sgf_path", "outputSgfPath", "sgfPath"),
            )
        )
    return failures


def validate_native_desktop_workflow_dialog_step(check: Any, name: str, path_keys: tuple[str, ...]) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return [f"{name} must include concrete native dialog step evidence"]
    failures: list[str] = []
    operator = first_present(evidence, "operator", "operatorId", "operatorName")
    if not has_operator_metadata(operator):
        failures.append(f"{name} must include operator metadata")
    method = first_present(evidence, "method", "dialogMethod", "interactionMethod")
    if not isinstance(method, str) or not method.strip():
        failures.append(f"{name} must include method metadata")
    sgf_path = first_present(evidence, *path_keys)
    if not isinstance(sgf_path, str) or not sgf_path.strip():
        failures.append(f"{name} must include SGF path metadata")
    elif not is_allowed_evidence_path(sgf_path):
        failures.append(f"{name} SGF path must not be a local absolute path")
    screenshot = first_present(evidence, "screenshot", "screenshotPath", "screenshot_path", "screenshotRef")
    if isinstance(screenshot, dict):
        screenshot_path = screenshot.get("path")
        if not isinstance(screenshot_path, str) or not screenshot_path.strip():
            failures.append(f"{name} screenshot.path must be present")
        elif not is_allowed_evidence_path(screenshot_path):
            failures.append(f"{name} screenshot.path must not be a local absolute path")
    elif not isinstance(screenshot, str) or not screenshot.strip():
        failures.append(f"{name} must include screenshot evidence")
    elif not is_allowed_evidence_path(screenshot):
        failures.append(f"{name} screenshot path must not be a local absolute path")
    return failures


def has_operator_metadata(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value)
    return False


def validate_native_desktop_workflow_screenshots(evidence: dict[str, Any]) -> list[str]:
    screenshots = evidence.get("screenshots")
    if not isinstance(screenshots, list):
        return ["screenshots must be a list"]
    failures: list[str] = []
    if not screenshots:
        failures.append("screenshots must include at least one record")
    for index, screenshot in enumerate(screenshots):
        if not isinstance(screenshot, dict):
            failures.append(f"screenshots[{index}] must be an object")
            continue
        path = screenshot.get("path")
        if not isinstance(path, str) or not path.strip():
            failures.append(f"screenshots[{index}].path must be a stable repo-relative or <tmp> path")
        elif not is_allowed_evidence_path(path):
            failures.append(f"screenshots[{index}].path must not be a local absolute path")
        bytes_value = first_present(screenshot, "bytes", "sizeBytes", "size_bytes")
        if not positive_number(bytes_value):
            failures.append(f"screenshots[{index}].bytes must be positive")
        if not is_sha256_hex(screenshot.get("sha256")):
            failures.append(f"screenshots[{index}].sha256 must be a 64-character hex sha256")
    return failures


def validate_native_desktop_workflow_reopen_state(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["reopen_state_verified evidence must be an object"]
    failures: list[str] = []
    invariants = evidence.get("invariants")
    if invariants is not None and not isinstance(invariants, dict):
        failures.append("reopen_state_verified.invariants must be an object when present")
        invariants = None
    persisted = first_present(
        evidence,
        "persistedEditsVerified",
        "persisted_edit_evidence",
        "persistedEditEvidence",
        "editsPersisted",
    )
    nested_persisted = False
    if isinstance(invariants, dict) and invariants.get("verified") is True:
        content_hash = invariants.get("contentHash")
        content_invariant = invariants.get("contentInvariant")
        nested_persisted = (isinstance(content_hash, str) and bool(content_hash.strip())) or (
            isinstance(content_invariant, dict) and bool(content_invariant)
        )
    if persisted is not True and not isinstance(persisted, dict) and not nested_persisted:
        failures.append("reopen_state_verified must include persisted edit evidence")
    if (
        first_present(evidence, "boardInvariantVerified", "boardStateVerified", "board_state_verified") is not True
        and not nested_board_invariant_verified(invariants)
    ):
        failures.append("reopen_state_verified must verify board invariant")
    if (
        first_present(evidence, "treeInvariantVerified", "treeStateVerified", "tree_state_verified") is not True
        and not nested_tree_invariant_verified(invariants)
    ):
        failures.append("reopen_state_verified must verify tree invariant")
    return failures


def nested_board_invariant_verified(invariants: Any) -> bool:
    if not isinstance(invariants, dict) or invariants.get("verified") is not True:
        return False
    board = invariants.get("boardInvariant")
    if not isinstance(board, dict):
        return False
    return board.get("verifiedByContent") is True or board.get("verified") is True


def nested_tree_invariant_verified(invariants: Any) -> bool:
    if not isinstance(invariants, dict) or invariants.get("verified") is not True:
        return False
    tree = invariants.get("treeInvariant")
    if not isinstance(tree, dict):
        return False
    if tree.get("verified") is True:
        return True
    move_count = tree.get("moveCountAtLeast")
    move_tokens = tree.get("moveTokens")
    return tree.get("rootPresent") is True and isinstance(move_count, (int, float)) and move_count >= 2 and (
        isinstance(move_tokens, list) and bool(move_tokens)
    )


def validate_native_desktop_workflow_scope_boundaries(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    boundaries = evidence.get("boundaries")
    if boundaries is not None and not isinstance(boundaries, dict):
        return ["boundaries must be an object when present"]
    boundary_map = boundaries if isinstance(boundaries, dict) else {}
    forbidden_true = [
        "windowsCovered",
        "windowsInstalledAppCovered",
        "linuxCovered",
        "linuxInstalledAppCovered",
        "ocrCovered",
        "ocrCaptureCovered",
        "captureCovered",
        "externalClientCaptureCovered",
        "providerCovered",
        "providerParityCovered",
        "readboardCovered",
        "readboardParityCovered",
    ]
    for key in forbidden_true:
        if boundary_map.get(key) is True:
            failures.append(f"boundaries.{key} must be false")
    for key in ("fullLegacyParityCovered", "productionSigned", "notarized", "releasePublished"):
        if key in boundary_map and boundary_map.get(key) is not False:
            failures.append(f"boundaries.{key} must be false")
    if boundary_map.get("webviewDomAutomationCovered") is True:
        failures.append("boundaries.webviewDomAutomationCovered must be false")
    return failures


def validate_native_desktop_workflow_paths(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    def walk(value: Any, key_path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                next_path = f"{key_path}.{key}" if key_path else str(key)
                walk(child, next_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{key_path}[{index}]")
        elif isinstance(value, str) and key_path:
            key_name = key_path.rsplit(".", 1)[-1].lower()
            if "path" not in key_name:
                return
            if not is_allowed_evidence_path(value):
                failures.append(f"{key_path} must not be a local absolute path")

    walk(evidence, "")
    return failures


def is_allowed_evidence_path(value: str) -> bool:
    return value.startswith("<tmp>/") or is_stable_artifact_path(value)


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


def validate_multiplatform_packaging_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != MULTIPLATFORM_PACKAGING_SMOKE_SCHEMA:
        failures.append(f"schema must be {MULTIPLATFORM_PACKAGING_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        return failures
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    missing = [name for name in MULTIPLATFORM_PACKAGING_SMOKE_REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in MULTIPLATFORM_PACKAGING_SMOKE_REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    for platform in PACKAGING_PLATFORMS:
        failures.extend(validate_packaging_platform_artifacts(check_by_name.get(f"{platform}_artifacts"), platform))
    failures.extend(validate_packaging_signing_recorded(check_by_name.get("signing_recorded")))
    failures.extend(validate_packaging_dev_server_absent(check_by_name.get("dev_server_absent")))
    failures.extend(validate_packaging_checksums(check_by_name.get("checksums")))
    return failures


def validate_packaging_platform_artifacts(check: Any, platform: str) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return [f"{platform}_artifacts evidence must be an object"]
    failures: list[str] = []
    if evidence.get("platform") != platform:
        failures.append(f"{platform}_artifacts.platform must be {platform}")
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        failures.append(f"{platform}_artifacts.artifacts must be a non-empty list")
    else:
        present_count = 0
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                failures.append(f"{platform}_artifacts.artifacts[{index}] must be an object")
                continue
            if artifact.get("artifactPresent") is not True:
                continue
            present_count += 1
            artifact_path = first_present(artifact, "path", "name", "fileName", "file_name")
            if not isinstance(artifact_path, str) or not artifact_path:
                failures.append(f"{platform}_artifacts.artifacts[{index}] with artifactPresent true must include path/name")
            size = first_present(artifact, "sizeBytes", "size_bytes")
            if not positive_number(size):
                failures.append(f"{platform}_artifacts.artifacts[{index}] with artifactPresent true must include positive sizeBytes")
            checksum = artifact.get("sha256")
            if not is_sha256_hex(checksum):
                failures.append(f"{platform}_artifacts.artifacts[{index}] with artifactPresent true must include 64-character hex sha256")
        if present_count < 1:
            failures.append(f"{platform}_artifacts.artifacts must include at least one artifactPresent true entry")
    signing = evidence.get("signing")
    if isinstance(signing, dict):
        failures.extend(validate_packaging_signing_state(signing, f"{platform}_artifacts.signing"))
    else:
        failures.append(f"{platform}_artifacts.signing must be an object")
    return failures


def validate_packaging_signing_recorded(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["signing_recorded evidence must be an object"]
    failures: list[str] = []
    for platform in PACKAGING_PLATFORMS:
        signing = evidence.get(platform)
        if not isinstance(signing, dict):
            failures.append(f"signing_recorded.{platform} must be an object")
            continue
        failures.extend(validate_packaging_signing_state(signing, f"signing_recorded.{platform}"))
    if evidence.get("officialSigningCovered") is not False:
        failures.append("signing_recorded.officialSigningCovered must be false")
    return failures


def validate_packaging_signing_state(signing: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    if signing.get("checked") is not True:
        failures.append(f"{label}.checked must be true")
    status = signing.get("status")
    if not isinstance(status, str) or not status:
        failures.append(f"{label}.status must be non-empty")
    if signing.get("productionSigned") is not False:
        failures.append(f"{label}.productionSigned must be false")
    if signing.get("officialReleaseSigned") is True:
        failures.append(f"{label}.officialReleaseSigned must not be true")
    return failures


def validate_packaging_dev_server_absent(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["dev_server_absent evidence must be an object"]
    failures: list[str] = []
    for platform in PACKAGING_PLATFORMS:
        if evidence.get(platform) is not True:
            failures.append(f"dev_server_absent.{platform} must be true")
    if evidence.get("viteDevServerReferenced") is not False:
        failures.append("dev_server_absent.viteDevServerReferenced must be false")
    return failures


def validate_packaging_checksums(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["checksums evidence must be an object"]
    entries = evidence.get("entries")
    if not isinstance(entries, list) or not entries:
        return ["checksums.entries must be a non-empty list"]
    failures: list[str] = []
    platforms_with_checksum: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            failures.append(f"checksums.entries[{index}] must be an object")
            continue
        platform = entry.get("platform")
        if platform in PACKAGING_PLATFORMS:
            if entry.get("artifactPresent") is True:
                platforms_with_checksum.add(platform)
            else:
                failures.append(f"checksums.entries[{index}].artifactPresent must be true")
        else:
            failures.append(f"checksums.entries[{index}].platform must be macos/windows/linux")
        algorithm = str(entry.get("algorithm", "")).lower()
        if algorithm != "sha256":
            failures.append(f"checksums.entries[{index}].algorithm must be sha256")
        value = entry.get("value")
        if not is_sha256_hex(value):
            failures.append(f"checksums.entries[{index}].value must be a 64-character hex sha256")
    missing_platforms = [platform for platform in PACKAGING_PLATFORMS if platform not in platforms_with_checksum]
    if missing_platforms:
        failures.append("checksums missing platforms: " + ", ".join(missing_platforms))
    return failures


def is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-fA-F]{64}", value))


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
        "annotationsVerified": ("annotationsVerified", "annotations_verified"),
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


def missing_string_members(value: Any, required: list[str], label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return [f"{label} must be a string list"]
    missing = [item for item in required if item not in value]
    if missing:
        return [f"{label} missing: " + ", ".join(missing)]
    return []


def non_empty_proof(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return False


def is_stable_artifact_path(value: str) -> bool:
    path = value.strip()
    if not path:
        return False
    if path.startswith(("/Users/", "/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/", "~")):
        return False
    if re.match(r"^[A-Za-z]:[\\/]", path):
        return False
    if path.startswith("/"):
        return False
    return True


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


def parse_legacy_action_matrix(text: str) -> list[dict[str, str]]:
    matrix_match = re.search(r"\blegacyActionMatrix\b[^=]*=\s*\[", text)
    if not matrix_match:
        return []
    start = matrix_match.end() - 1
    end = find_matching_delimiter(text, start, "[", "]")
    if end is None:
        return []
    matrix_body = text[start + 1 : end]
    actions: list[dict[str, str]] = []
    for object_body in top_level_object_bodies(matrix_body):
        action = {
            "body": object_body,
            "id": extract_ts_object_string_field(object_body, "id"),
            "group": extract_ts_object_string_field(object_body, "group"),
            "label": extract_ts_object_string_field(object_body, "label"),
            "disabled": extract_ts_object_boolean_field(object_body, "disabled"),
        }
        if action["id"] and action["group"] and action["label"]:
            actions.append(action)
    return actions


def parse_rust_native_menu_actions(text: str) -> list[dict[str, str]]:
    actions_match = re.search(r"\bNATIVE_MENU_ACTIONS\s*:\s*&\[[^\]]+\]\s*=\s*&\[", text)
    if not actions_match:
        return []
    start = actions_match.end() - 1
    end = find_matching_delimiter(text, start, "[", "]")
    if end is None:
        return []
    actions_body = text[start + 1 : end]
    actions: list[dict[str, str]] = []
    for object_body in top_level_rust_struct_bodies(actions_body, "NativeMenuActionSpec"):
        menu_path = extract_rust_menu_path(object_body)
        action = {
            "body": object_body,
            "action_id": extract_rust_object_string_field(object_body, "action_id"),
            "group": menu_path[0] if menu_path else "",
            "label": extract_rust_object_string_field(object_body, "label"),
        }
        if action["action_id"] and action["group"] and action["label"]:
            actions.append(action)
    return actions


def extract_rust_string_const(text: str, const_name: str) -> str | None:
    match = re.search(r"\bconst\s+" + re.escape(const_name) + r"\s*:\s*&str\s*=\s*\"([^\"]+)\"", text)
    return match.group(1) if match else None


def extract_frontend_legacy_menu_event_names(text: str) -> list[str]:
    function_body = find_ts_function_body(text, "listenToLegacyMenuActionEvents")
    if function_body is None:
        return []
    event_names = re.findall(r"[\"']([^\"']+)[\"']", function_body)
    helper_names = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", function_body)
    for helper_name in helper_names:
        if helper_name in {"listen", "Promise", "map", "onAction", "legacyActionFromPayload"}:
            continue
        helper_body = find_ts_function_body(text, helper_name)
        if helper_body is None:
            continue
        event_names.extend(re.findall(r"[\"']([^\"']+)[\"']", helper_body))
    return unique_ordered(event_names)


def find_ts_function_body(text: str, function_name: str) -> str | None:
    starts = [
        text.find("function " + function_name),
        text.find("async function " + function_name),
        text.find("export function " + function_name),
        text.find("export async function " + function_name),
        text.find("const " + function_name),
        text.find("let " + function_name),
    ]
    start = min((index for index in starts if index >= 0), default=-1)
    if start < 0:
        return None
    open_index = text.find("{", start)
    if open_index < 0:
        return None
    close_index = find_matching_delimiter(text, open_index, "{", "}")
    if close_index is None:
        return None
    return text[open_index + 1 : close_index]


def top_level_object_bodies(text: str) -> list[str]:
    bodies: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        end = find_matching_delimiter(text, index, "{", "}")
        if end is None:
            break
        bodies.append(text[index + 1 : end])
        index = end + 1
    return bodies


def top_level_rust_struct_bodies(text: str, struct_name: str) -> list[str]:
    bodies: list[str] = []
    pattern = re.compile(r"\b" + re.escape(struct_name) + r"\s*\{")
    for match in pattern.finditer(text):
        start = text.find("{", match.start())
        end = find_matching_delimiter(text, start, "{", "}")
        if end is not None:
            bodies.append(text[start + 1 : end])
    return bodies


def extract_ts_object_string_field(text: str, field: str) -> str:
    match = re.search(r"\b" + re.escape(field) + r"\s*:\s*([\"'])(.*?)\1", text)
    return match.group(2) if match else ""


def extract_ts_object_boolean_field(text: str, field: str) -> str:
    match = re.search(r"\b" + re.escape(field) + r"\s*:\s*(true|false)\b", text)
    return match.group(1) if match else ""


def extract_rust_object_string_field(text: str, field: str) -> str:
    match = re.search(r"\b" + re.escape(field) + r"\s*:\s*\"([^\"]+)\"", text)
    return match.group(1) if match else ""


def extract_rust_menu_path(text: str) -> list[str]:
    match = re.search(r"\bmenu_path\s*:\s*&\[(.*?)\]", text, re.S)
    if not match:
        return []
    return re.findall(r"\"([^\"]+)\"", match.group(1))


def unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def missing_legacy_shell_menu_surface(shell_text: str, actions_text: str, menu_surface: dict[str, list[str]]) -> list[str]:
    failures: list[str] = []
    if "legacyActionMatrix" not in shell_text:
        failures.append("LegacyShell must render menuGroups from legacyActionMatrix")
    if "menuGroups.map" not in shell_text:
        failures.append("LegacyShell must render mapped menu groups")
    actions = parse_legacy_action_matrix(actions_text)
    if not actions:
        return failures + ["legacyActionMatrix actions missing"]
    actions_by_group_label = {
        (action["group"], action["label"]): action
        for action in actions
    }
    for group_label, item_labels in menu_surface.items():
        if group_label not in {action["group"] for action in actions}:
            failures.append(f"{group_label} menu group missing")
            continue
        for item_label in item_labels:
            action = actions_by_group_label.get((group_label, item_label))
            if action is None:
                failures.append(f"{group_label}/{item_label} menu entry missing")
                continue
            if action.get("disabled") == "true":
                failures.append(f"{group_label}/{item_label} has literal disabled: true")
            if not has_identifiable_menu_entry(action.get("body", ""), item_label) and "data-legacy-action" not in shell_text:
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
