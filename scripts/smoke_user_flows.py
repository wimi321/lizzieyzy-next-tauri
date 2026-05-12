#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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
TAURI_WEBVIEW_DOM_CLICK_SMOKE_EVIDENCE = "docs/qa/tauri-webview-dom-click-smoke-macos.json"
TAURI_WEBVIEW_DOM_CLICK_SMOKE_SCHEMA = "lizzieyzy.tauri-webview-dom-click-smoke.v1"
TAURI_WEBVIEW_DOM_CLICK_REQUIRED_CHECKS = [
    "tauri_runtime_started",
    "webview_dom_observed",
    "webview_click_observed",
    "visible_targets_verified",
    "browser_fallback_excluded",
    "scope_boundaries_recorded",
]
TAURI_WEBVIEW_DOM_CLICK_REQUIRED_FALSE_FIELDS = [
    "fullLayoutParity",
    "fullShortcutParity",
    "fullLegacyParity",
    "releaseParity",
    "ocrCaptureParity",
]
LEGACY_LAYOUT_PARITY_SMOKE_EVIDENCE = "docs/qa/legacy-layout-parity-smoke-macos.json"
LEGACY_LAYOUT_PARITY_SMOKE_SCHEMA = "lizzieyzy.legacy-layout-parity-smoke.v1"
LEGACY_SHORTCUT_LAYOUT_EVIDENCE = "docs/qa/legacy-shortcut-layout-evidence-macos.json"
LEGACY_SHORTCUT_LAYOUT_SCHEMA = "lizzieyzy.legacy-shortcut-layout-evidence.v1"
LEGACY_LAYOUT_REQUIRED_SCREENSHOTS = [
    "default review",
    "sgf editing",
    "katago analysis",
    "provider/readboard",
    "engine/preferences",
]
LEGACY_LAYOUT_REQUIRED_VISIBLE_TARGETS = [
    ("board", ["board"]),
    ("toolbar/menu", ["toolbar", "menu", "menubar"]),
    ("SGF tree", ["sgf tree", "tree"]),
    ("annotation/comment/properties", ["annotation", "comment", "properties", "property"]),
    ("analysis panel", ["analysis panel", "analysis"]),
    ("winrate", ["winrate"]),
    ("candidates/PV", ["candidate", "pv", "variation"]),
    ("cache/status", ["cache", "status"]),
    ("provider/readboard", ["provider", "readboard"]),
    ("engine/preferences", ["engine", "preferences", "preference"]),
]
LEGACY_LAYOUT_REQUIRED_FALSE_FIELDS = [
    "pixelPerfectParity",
    "fullLegacyUiParity",
    "fullShortcutParity",
    "releaseParity",
    "ocrCaptureParity",
    "fullLegacyParity",
]
LEGACY_SHORTCUT_LAYOUT_REQUIRED_FALSE_FIELDS = [
    *LEGACY_LAYOUT_REQUIRED_FALSE_FIELDS,
    "fullLayoutParity",
    "pixelPerfectLayoutParity",
    "osNativeMenuParity",
    "nativeDialogParity",
]
LEGACY_ACTION_LAYOUT_REQUIRED_GROUPS = ["File", "Game", "Analysis", "View", "Engine", "Tools", "Help"]
INSTALLED_MACOS_APP_SMOKE_EVIDENCE = "docs/qa/installed-macos-app-smoke.json"
INSTALLED_MACOS_APP_SMOKE_SCHEMA = "lizzieyzy.installed-macos-app-smoke.v1"
INSTALLED_APP_RUNTIME_WORKFLOW_EVIDENCE = "docs/qa/installed-app-runtime-workflow-macos.json"
INSTALLED_APP_RUNTIME_WORKFLOW_SCHEMA = "lizzieyzy.installed-app-runtime-workflow.v1"
INSTALLED_APP_RUNTIME_PROOF_SCHEMA = "lizzieyzy.installed-app-runtime-proof.v1"
INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_CHECKS = [
    "app_bundle_verified",
    "installed_app_launched",
    "runtime_process_observed",
    "window_observed",
    "workflow_action_executed",
    "backend_runtime_proof_observed",
    "screenshot_recorded",
    "dev_server_absent",
    "quit_or_terminate_observed",
    "scope_boundaries_recorded",
]
INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_TRUE_FIELDS = [
    "runtimeObserved",
    "installedAppLaunched",
    "runtimeProcessObserved",
    "windowObserved",
    "workflowExecuted",
    "screenshotObserved",
    "devServerAbsent",
]
INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_FALSE_FIELDS = [
    "browserFallbackUsed",
    "sourceStaticOnly",
    "artifactOnly",
    "runnerStartedDevServer",
    "runnerStartedViteDevServer",
    "productionSigned",
    "signed",
    "notarized",
    "updaterReady",
    "updaterCovered",
    "releasePublished",
    "windowsInstalledAppCovered",
    "linuxInstalledAppCovered",
    "windowsLinuxInstalledAppCovered",
    "fullInstalledAppParity",
    "fullLegacyParity",
    "fullShortcutParity",
    "fullLayoutParity",
    "providerReadboardOcrParity",
    "providerReadboardOCRParity",
]
INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_ACTIONS = [
    "launch_installed_app",
    "observe_main_window",
    "execute_runtime_action",
    "terminate_installed_app",
]
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
KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE = "docs/qa/katago-review-workflow-ux-smoke-macos.json"
KATAGO_REVIEW_WORKFLOW_UX_SMOKE_SCHEMA = "lizzieyzy.katago-review-workflow-ux-smoke.v1"
KATAGO_REVIEW_WORKFLOW_UX_COLLECTION_METHODS = {
    "source_static_plus_stubbed_ui_flow",
    "source_static_plus_stubbed_katago_review_ui_flow",
}
KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_CHECKS = [
    "progress_verified",
    "cancel_verified",
    "restart_after_cancel_verified",
    "cache_restore_verified",
    "engine_failure_verified",
    "stale_analysis_prevented",
    "source_facts_validated",
    "scope_boundaries",
]
KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_TRUE_FIELDS = [
    "progressVerified",
    "cancelVerified",
    "restartAfterCancelVerified",
    "cacheRestoreVerified",
    "engineFailureVerified",
    "staleAnalysisPrevented",
    "sourceFactsValidated",
]
KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_FALSE_FIELDS = [
    "liveKataGoObserved",
    "fullLegacyAnalysisParity",
    "fullLegacyParity",
    "releasePublished",
    "productionSigned",
    "notarized",
    "providerParityCovered",
    "readboardParityCovered",
    "ocrExternalCaptureCovered",
    "windowsLinuxCovered",
]
LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE = "docs/qa/legacy-config-corpus-migration-smoke.json"
LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_SCHEMA = "lizzieyzy.legacy-config-corpus-migration-smoke.v1"
LEGACY_CONFIG_CORPUS_REQUIRED_FIXTURE_CLASSES = [
    "minimal",
    "full-engine",
    "multi/conflict",
    "ui-review",
    "windows-path",
    "unix-path",
    "unicode-space",
    "malformed-partial",
    "unknown-deprecated",
]
LEGACY_CONFIG_CORPUS_REQUIRED_TRUE_FIELDS = [
    "previewNoWrite",
    "applyWritesIntendedTargets",
    "preservesExistingNextSettings",
    "invalidNoWrite",
    "unsupportedKeysWarned",
    "duplicateConflictDeterministic",
    "rollbackMetadataObserved",
]
LEGACY_CONFIG_CORPUS_REQUIRED_FALSE_FIELDS = [
    "fullHistoricalConfigParity",
    "realUserConfigSmoke",
    "externalAccountNeeded",
    "releaseParity",
    "fullLegacyParity",
]
KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_EVIDENCE = "docs/qa/katago-live-desktop-workflow-smoke-macos.json"
KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_SCHEMA = "lizzieyzy.katago-live-desktop-workflow-smoke.v1"
KATAGO_LIVE_DESKTOP_WORKFLOW_REQUIRED_CHECKS = [
    "runtime_started",
    "engine_assets_verified",
    "analysis_progress_observed",
    "cancel_observed",
    "restart_after_cancel_observed",
    "analysis_complete_observed",
    "cache_saved",
    "cache_hit_restored",
    "stale_cache_prevented",
    "engine_failure_observed",
    "browser_fallback_excluded",
    "scope_boundaries_recorded",
]
KATAGO_LIVE_DESKTOP_WORKFLOW_REQUIRED_FALSE_FIELDS = [
    "fullLegacyAnalysisParity",
    "providerReadboardParity",
    "releaseParity",
    "arbitraryOcrParity",
]
READBOARD_TAURI_RUNTIME_SMOKE_EVIDENCE = "docs/qa/readboard-tauri-runtime-smoke-macos.json"
READBOARD_TAURI_RUNTIME_SMOKE_SCHEMA = "lizzieyzy.readboard-tauri-runtime-smoke.v1"
READBOARD_TAURI_RUNTIME_SMOKE_REQUIRED_CHECKS = [
    "runtime_started",
    "sidecar_probe_ready",
    "sidecar_probe_unavailable",
    "protocol_line_sync",
    "target_state_change_sync",
    "arbitrary_ocr_not_covered",
    "external_capture_not_covered",
]
READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE = "docs/qa/readboard-image-import-smoke-macos.json"
READBOARD_IMAGE_IMPORT_SMOKE_SCHEMA = "lizzieyzy.readboard-image-import-smoke.v1"
READBOARD_IMAGE_IMPORT_REQUIRED_CHECKS = [
    "image_path_import",
    "image_base64_import",
    "invalid_image_rejected",
    "non_board_image_rejected",
    "snapshot_verified",
    "protocol_regression",
    "scope_boundaries",
]
READBOARD_IMAGE_IMPORT_REQUIRED_TRUE_FIELDS = [
    "imagePathImportVerified",
    "imageBase64ImportVerified",
    "invalidImageRejected",
    "nonBoardImageRejected",
    "snapshotVerified",
    "boardSizeVerified",
    "stoneCountVerified",
    "toPlayVerified",
    "protocolRegressionVerified",
]
READBOARD_IMAGE_IMPORT_REQUIRED_FALSE_FIELDS = [
    "fullOcrParity",
    "externalCaptureCovered",
]
READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE = "docs/qa/readboard-image-ocr-corpus-smoke-macos.json"
READBOARD_IMAGE_OCR_CORPUS_SMOKE_SCHEMA = "lizzieyzy.readboard-image-ocr-corpus-smoke.v1"
READBOARD_IMAGE_OCR_CORPUS_MIN_FIXTURES = 4
READBOARD_IMAGE_OCR_CORPUS_REQUIRED_CHECKS = [
    "fixture_manifest",
    "path_base64_equivalence",
    "invalid_image_rejected",
    "non_board_image_rejected",
    "truncated_image_rejected",
    "board_size_coverage",
    "stone_count_coverage",
    "hash_invariants",
    "external_capture_unsupported_contract",
    "scope_boundaries",
]
READBOARD_IMAGE_OCR_CORPUS_REQUIRED_TRUE_FIELDS = [
    "pathBase64EquivalenceVerified",
    "invalidImageRejected",
    "nonBoardImageRejected",
    "truncatedImageRejected",
    "boardSizeCoverageVerified",
    "stoneCountCoverageVerified",
    "hashInvariantsVerified",
    "externalCaptureUnsupportedContractVerified",
]
READBOARD_IMAGE_OCR_CORPUS_REQUIRED_FALSE_FIELDS = [
    "fullOcrParity",
    "externalWindowCaptureCovered",
    "realClientCaptureCovered",
    "fullReadboardParity",
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
                    "External window/client capture",
                    "imported: false",
                    "boardReplacement",
                    "No stale, guessed, or partial board replacement",
                ],
            ),
            *missing_any_required_token(
                api_text,
                "provider API",
                "controlled image/OCR helper",
                ["OCR/image helper", "Controlled board image import MVP"],
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
            *missing_any_required_token(
                panel_text,
                "ProviderPanel",
                "controlled image/OCR helper",
                ["OCR/image helper", "Controlled board image import"],
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
        self.check_tauri_webview_dom_click_smoke_evidence()
        self.check_legacy_layout_parity_smoke_evidence()
        self.check_legacy_shortcut_layout_evidence()
        self.check_installed_macos_app_smoke_evidence()
        self.check_installed_app_runtime_workflow_evidence()
        self.check_native_desktop_sgf_workflow_evidence()
        self.check_katago_live_smoke_evidence()
        self.check_katago_review_workflow_ux_smoke_evidence()
        self.check_legacy_config_corpus_migration_smoke_evidence()
        self.check_katago_live_desktop_workflow_smoke_evidence()
        self.check_readboard_live_smoke_evidence()
        self.check_readboard_image_import_smoke_evidence()
        self.check_readboard_image_ocr_corpus_smoke_evidence()
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

    def check_tauri_webview_dom_click_smoke_evidence(self) -> None:
        evidence_path = self.path(TAURI_WEBVIEW_DOM_CLICK_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "tauri_webview_dom_click_smoke",
                f"TODO gate: run Tauri WebView DOM/click smoke and record {TAURI_WEBVIEW_DOM_CLICK_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(TAURI_WEBVIEW_DOM_CLICK_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_tauri_webview_dom_click_smoke_evidence(evidence)
        if failures:
            self.pending(
                "tauri_webview_dom_click_smoke",
                f"{TAURI_WEBVIEW_DOM_CLICK_SMOKE_EVIDENCE} is present but not valid scoped Tauri WebView DOM/click PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "tauri_webview_dom_click_smoke",
            "scoped Tauri WebView DOM/click evidence passes with runtime, DOM, click, visible-target, and boundary checks",
        )

    def check_legacy_layout_parity_smoke_evidence(self) -> None:
        evidence_path = self.path(LEGACY_LAYOUT_PARITY_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "legacy_layout_parity_smoke",
                f"TODO gate: record scoped legacy layout evidence at {LEGACY_LAYOUT_PARITY_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(LEGACY_LAYOUT_PARITY_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_legacy_layout_parity_smoke_evidence(evidence)
        if failures:
            self.pending(
                "legacy_layout_parity_smoke",
                f"{LEGACY_LAYOUT_PARITY_SMOKE_EVIDENCE} is present but not valid scoped legacy layout PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "legacy_layout_parity_smoke",
            "scoped legacy layout evidence passes with required screenshots, viewports, visible targets, overlap/clipping, and boundary checks",
        )

    def check_legacy_shortcut_layout_evidence(self) -> None:
        evidence_path = self.path(LEGACY_SHORTCUT_LAYOUT_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "legacy_shortcut_layout_evidence",
                f"TODO gate: record scoped legacy action/shortcut/layout runtime evidence at {LEGACY_SHORTCUT_LAYOUT_EVIDENCE}",
            )
            return
        evidence = self.load_json(LEGACY_SHORTCUT_LAYOUT_EVIDENCE)
        if evidence is None:
            return
        failures = validate_legacy_shortcut_layout_evidence(evidence)
        if failures:
            self.pending(
                "legacy_shortcut_layout_evidence",
                f"{LEGACY_SHORTCUT_LAYOUT_EVIDENCE} is present but not valid scoped legacy action/shortcut/layout runtime evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "legacy_shortcut_layout_evidence",
            "scoped legacy action/shortcut/layout runtime evidence passes with action matrix, screenshots, input-editing, and boundary checks",
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

    def check_installed_app_runtime_workflow_evidence(self) -> None:
        evidence_path = self.path(INSTALLED_APP_RUNTIME_WORKFLOW_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "installed_app_runtime_workflow",
                f"TODO gate: record scoped installed app runtime workflow evidence at {INSTALLED_APP_RUNTIME_WORKFLOW_EVIDENCE}",
            )
            return
        evidence = self.load_json(INSTALLED_APP_RUNTIME_WORKFLOW_EVIDENCE)
        if evidence is None:
            return
        failures = validate_installed_app_runtime_workflow_evidence(evidence)
        if failures:
            self.pending(
                "installed_app_runtime_workflow",
                f"{INSTALLED_APP_RUNTIME_WORKFLOW_EVIDENCE} is present but not valid scoped installed app runtime workflow PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "installed_app_runtime_workflow",
            "scoped installed app runtime workflow evidence passes with runtime actions, process/window/screenshot proof, dev-server exclusion, and release-boundary checks",
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

    def check_katago_review_workflow_ux_smoke_evidence(self) -> None:
        source_failures = validate_katago_review_workflow_ux_source_facts(self.root)
        if source_failures:
            if all(failure.startswith("missing source file(s):") for failure in source_failures):
                self.pending(
                    "katago_review_workflow_ux_smoke",
                    "TODO gate: validate scoped KataGo review workflow UX source facts before accepting evidence: "
                    + "; ".join(source_failures),
                )
                return
            self.fail(
                "katago_review_workflow_ux_smoke",
                "KataGo review workflow UX source facts are broken: " + "; ".join(source_failures),
            )
            return
        evidence_path = self.path(KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "katago_review_workflow_ux_smoke",
                f"TODO gate: record scoped KataGo review workflow UX resilience evidence at {KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_katago_review_workflow_ux_smoke_evidence(evidence)
        if failures:
            self.pending(
                "katago_review_workflow_ux_smoke",
                f"{KATAGO_REVIEW_WORKFLOW_UX_SMOKE_EVIDENCE} is present but not valid scoped KataGo review workflow UX resilience PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "katago_review_workflow_ux_smoke",
            "scoped KataGo review workflow UX resilience evidence passes with progress, cancel/restart, cache restore, failure, stale-guard, and boundary checks",
        )

    def check_legacy_config_corpus_migration_smoke_evidence(self) -> None:
        evidence_path = self.path(LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "legacy_config_corpus_migration_smoke",
                f"TODO gate: record scoped legacy config corpus migration evidence at {LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_legacy_config_corpus_migration_smoke_evidence(evidence)
        if failures:
            self.pending(
                "legacy_config_corpus_migration_smoke",
                f"{LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_EVIDENCE} is present but not valid scoped legacy config corpus migration PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "legacy_config_corpus_migration_smoke",
            "scoped legacy config corpus migration evidence passes with fixture coverage, no-write/apply/rollback, deterministic conflict, and boundary checks",
        )

    def check_katago_live_desktop_workflow_smoke_evidence(self) -> None:
        evidence_path = self.path(KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "katago_live_desktop_workflow_smoke",
                f"TODO gate: record scoped live KataGo desktop workflow evidence at {KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_katago_live_desktop_workflow_smoke_evidence(evidence)
        if failures:
            self.pending(
                "katago_live_desktop_workflow_smoke",
                f"{KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_EVIDENCE} is present but not valid scoped live KataGo desktop workflow PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "katago_live_desktop_workflow_smoke",
            "scoped live KataGo desktop workflow evidence passes with progress, cancel/restart, completion, cache, stale-guard, failure, and boundary checks",
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

    def check_readboard_image_import_smoke_evidence(self) -> None:
        evidence_path = self.path(READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "readboard_image_import_smoke",
                f"TODO gate: record scoped controlled readboard image import MVP evidence at {READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_readboard_image_import_smoke_evidence(evidence, self.root)
        if failures:
            self.pending(
                "readboard_image_import_smoke",
                f"{READBOARD_IMAGE_IMPORT_SMOKE_EVIDENCE} is present but not valid scoped controlled image import MVP PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "readboard_image_import_smoke",
            "scoped controlled readboard image import MVP evidence passes with path/base64 import, rejection, snapshot, and boundary checks",
        )

    def check_readboard_image_ocr_corpus_smoke_evidence(self) -> None:
        evidence_path = self.path(READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE)
        if not evidence_path.is_file():
            self.pending(
                "readboard_image_ocr_corpus_smoke",
                f"TODO gate: record scoped controlled readboard image OCR corpus evidence at {READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE}",
            )
            return
        evidence = self.load_json(READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE)
        if evidence is None:
            return
        failures = validate_readboard_image_ocr_corpus_smoke_evidence(evidence, self.root)
        if failures:
            self.pending(
                "readboard_image_ocr_corpus_smoke",
                f"{READBOARD_IMAGE_OCR_CORPUS_SMOKE_EVIDENCE} is present but not valid scoped controlled image OCR corpus PASS evidence: "
                + "; ".join(failures),
            )
            return
        self.pass_(
            "readboard_image_ocr_corpus_smoke",
            "scoped controlled readboard image OCR corpus evidence passes with manifest, path/base64 equivalence, rejection, coverage, hash, and unsupported external-capture boundary checks",
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
    if katago_live_browser_fallback_used(evidence) is not False:
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


def validate_tauri_webview_dom_click_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != TAURI_WEBVIEW_DOM_CLICK_SMOKE_SCHEMA:
        failures.append(f"schema must be {TAURI_WEBVIEW_DOM_CLICK_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    if evidence.get("tauriRuntimeObserved") is not True:
        failures.append("tauriRuntimeObserved must be true")
    if evidence.get("webviewDomObserved") is not True:
        failures.append("webviewDomObserved must be true")
    if evidence.get("webviewClickObserved") is not True:
        failures.append("webviewClickObserved must be true")
    if evidence.get("browserFallbackUsed") is not False:
        failures.append("browserFallbackUsed must be false")
    for key in TAURI_WEBVIEW_DOM_CLICK_REQUIRED_FALSE_FIELDS:
        if evidence.get(key) is True:
            failures.append(f"{key} must be false")

    check_by_name = tauri_webview_dom_click_check_by_name(evidence)
    missing = [name for name in TAURI_WEBVIEW_DOM_CLICK_REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in TAURI_WEBVIEW_DOM_CLICK_REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))

    failures.extend(validate_tauri_webview_dom_click_checks(check_by_name))
    failures.extend(validate_tauri_webview_click_records(evidence.get("clickedControls")))
    failures.extend(validate_tauri_webview_visible_assertions(evidence.get("visibleAssertions")))
    boundary_candidates = tauri_webview_dom_click_boundary_candidates(evidence, check_by_name)
    if not any(not validate_tauri_webview_scope_boundaries(candidate) for candidate in boundary_candidates):
        failures.append("boundaries must include fullLayoutParity/fullShortcutParity/fullLegacyParity/releaseParity/ocrCaptureParity=false")
    for candidate in boundary_candidates:
        if isinstance(candidate, dict):
            for key in TAURI_WEBVIEW_DOM_CLICK_REQUIRED_FALSE_FIELDS:
                if candidate.get(key) is True:
                    failures.append(f"boundaries.{key} must be false")
    return failures


def tauri_webview_dom_click_check_by_name(evidence: dict[str, Any]) -> dict[str, Any]:
    checks: list[Any] = []
    for candidate in (
        evidence.get("checks"),
        evidence.get("runtimeReport", {}).get("checks") if isinstance(evidence.get("runtimeReport"), dict) else None,
    ):
        if isinstance(candidate, list):
            checks.extend(candidate)
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    if "tauri_runtime_started" not in check_by_name and "runtime_started" in check_by_name:
        check_by_name["tauri_runtime_started"] = check_by_name["runtime_started"]
    return check_by_name


def validate_tauri_webview_dom_click_checks(check_by_name: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    runtime = check_evidence(check_by_name.get("tauri_runtime_started"))
    if runtime is None:
        failures.append("tauri_runtime_started evidence must be an object")
    elif runtime.get("tauriRuntimeObserved") is not True and runtime.get("tauriInternals") is not True:
        failures.append("tauri_runtime_started.tauriRuntimeObserved must be true")

    dom = check_evidence(check_by_name.get("webview_dom_observed"))
    if dom is None:
        failures.append("webview_dom_observed evidence must be an object")
    else:
        dom_root = first_present(dom, "root", "domRoot")
        initial_targets = dom.get("initialTargets")
        if (
            dom.get("webviewDomObserved") is not True
            and not isinstance(dom_root, dict)
            and not isinstance(initial_targets, list)
        ):
            failures.append("webview_dom_observed.webviewDomObserved must be true")

    click = check_evidence(check_by_name.get("webview_click_observed"))
    if click is None:
        failures.append("webview_click_observed evidence must be an object")
    else:
        click_records = first_present(click, "clickedControls", "controls")
        if click.get("webviewClickObserved") is not True and validate_tauri_webview_click_records(click_records):
            failures.append("webview_click_observed.webviewClickObserved must be true")
        failures.extend(validate_tauri_webview_click_records(first_present(click, "clickedControls", "controls")))

    visible = check_evidence(check_by_name.get("visible_targets_verified"))
    if visible is None:
        failures.append("visible_targets_verified evidence must be an object")
    else:
        failures.extend(
            validate_tauri_webview_visible_assertions(
                first_present(visible, "visibleAssertions", "visibleTargets", "targets")
            )
        )

    fallback = check_evidence(check_by_name.get("browser_fallback_excluded"))
    if fallback is None:
        failures.append("browser_fallback_excluded evidence must be an object")
    elif fallback.get("browserFallbackUsed") is not False:
        failures.append("browser_fallback_excluded.browserFallbackUsed must be false")
    return failures


def validate_tauri_webview_click_records(value: Any) -> list[str]:
    failures = validate_desktop_ui_click_clicked_controls(value)
    if isinstance(value, list) and len(value) < 4:
        failures.append("clickedControls must include at least four controls")
    return failures


def validate_tauri_webview_visible_assertions(value: Any) -> list[str]:
    failures = validate_desktop_ui_click_visible_assertions(value)
    if isinstance(value, list) and len(value) < 4:
        failures.append("visibleAssertions must include at least four assertions")
    return failures


def validate_tauri_webview_scope_boundaries(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["boundaries must be an object"]
    failures: list[str] = []
    if "browserFallbackUsed" in value and value.get("browserFallbackUsed") is not False:
        failures.append("boundaries.browserFallbackUsed must be false")
    for key in TAURI_WEBVIEW_DOM_CLICK_REQUIRED_FALSE_FIELDS:
        if value.get(key) is not False:
            failures.append(f"boundaries.{key} must be false")
    return failures


def tauri_webview_dom_click_boundary_candidates(
    evidence: dict[str, Any], check_by_name: dict[str, Any]
) -> list[Any]:
    candidates: list[Any] = [evidence.get("boundaries")]
    scope_boundaries = check_evidence(check_by_name.get("scope_boundaries_recorded"))
    if scope_boundaries is not None:
        candidates.append(scope_boundaries)
    runtime_report = evidence.get("runtimeReport")
    if isinstance(runtime_report, dict):
        webview_dom_click = runtime_report.get("webviewDomClick")
        if isinstance(webview_dom_click, dict):
            candidates.append(webview_dom_click.get("boundaries"))
    return candidates


def validate_legacy_layout_parity_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != LEGACY_LAYOUT_PARITY_SMOKE_SCHEMA:
        failures.append(f"schema must be {LEGACY_LAYOUT_PARITY_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    failures.extend(validate_legacy_layout_screenshots(evidence.get("screenshots")))
    failures.extend(validate_legacy_layout_viewports(evidence))
    failures.extend(validate_legacy_layout_visible_assertions(evidence.get("visibleAssertions")))
    failures.extend(validate_legacy_layout_no_critical_overlap_or_clipping(evidence))
    failures.extend(validate_legacy_layout_boundaries(evidence))
    return failures


def validate_legacy_shortcut_layout_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != LEGACY_SHORTCUT_LAYOUT_SCHEMA:
        failures.append(f"schema must be {LEGACY_SHORTCUT_LAYOUT_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    failures.extend(validate_legacy_layout_runtime_observed(evidence))
    failures.extend(validate_legacy_action_shortcut_matrix(evidence))
    failures.extend(validate_legacy_shortcut_layout_screenshots(evidence.get("screenshots")))
    failures.extend(validate_legacy_layout_viewports(evidence))
    failures.extend(validate_legacy_layout_visible_assertions(evidence.get("visibleAssertions")))
    failures.extend(validate_legacy_layout_no_critical_overlap_or_clipping(evidence))
    failures.extend(validate_legacy_shortcut_layout_boundaries(evidence))
    return failures


def validate_legacy_layout_runtime_observed(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if evidence.get("runtimeObserved") is not True:
        failures.append("runtimeObserved must be true")
    collection_method = str(evidence.get("collectionMethod", "")).lower()
    if evidence.get("sourceStaticOnly") is True or "source_static" in collection_method or "static-only" in collection_method:
        failures.append("evidence must not be static-source-only")
    return failures


def validate_legacy_action_shortcut_matrix(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    action_matrix = first_present(evidence, "actionMatrix", "legacyActionMatrix", "actions")
    if not isinstance(action_matrix, list):
        return ["actionMatrix must be a list"]
    if not action_matrix:
        failures.append("actionMatrix must include action entries")

    clicked_count = int_or_none(first_present(evidence, "clickedObservedCount", "clickObservedCount"))
    shortcut_count = int_or_none(first_present(evidence, "shortcutObservedCount", "keyboardShortcutObservedCount"))
    visible_target_count = int_or_none(first_present(evidence, "visibleTargetCount", "visibleTargetsCount"))
    if clicked_count is None or clicked_count < 4:
        failures.append("clickedObservedCount must be at least 4")
    if shortcut_count is None or shortcut_count < 4:
        failures.append("shortcutObservedCount must be at least 4")
    if visible_target_count is None or visible_target_count < 6:
        failures.append("visibleTargetCount must be at least 6")

    observed_groups: set[str] = set()
    for index, entry in enumerate(action_matrix):
        if not isinstance(entry, dict):
            failures.append(f"actionMatrix[{index}] must be an object")
            continue
        action_id = entry.get("actionId")
        if not isinstance(action_id, str) or not action_id.strip():
            failures.append(f"actionMatrix[{index}].actionId must be non-empty")
        menu_path = entry.get("menuPath")
        if not isinstance(menu_path, str) or "/" not in menu_path.strip():
            failures.append(f"actionMatrix[{index}].menuPath must include a group/action path")
        else:
            observed_groups.add(menu_path.split("/", 1)[0].strip())
        shortcut = entry.get("shortcut")
        if not isinstance(shortcut, str) or not shortcut.strip():
            failures.append(f"actionMatrix[{index}].shortcut must be non-empty")
        target_selector = entry.get("targetSelector")
        if not isinstance(target_selector, str) or not target_selector.strip():
            failures.append(f"actionMatrix[{index}].targetSelector must be non-empty")
        disabled_or_availability = entry.get("disabledOrAvailability")
        if not non_empty_proof(disabled_or_availability):
            failures.append(f"actionMatrix[{index}].disabledOrAvailability must be present")
        observed_by = entry.get("observedBy")
        if not observed_by_mentions_runtime(observed_by):
            failures.append(f"actionMatrix[{index}].observedBy must include runtime observation")
        input_editing = entry.get("inputEditingBehavior")
        if not input_editing_is_safe(input_editing):
            failures.append(f"actionMatrix[{index}].inputEditingBehavior must prove input editing safety")
        visible_assertion = entry.get("visibleTargetAssertion")
        if not visible_target_assertion_passes(visible_assertion):
            failures.append(f"actionMatrix[{index}].visibleTargetAssertion must prove target visible")

    for group in LEGACY_ACTION_LAYOUT_REQUIRED_GROUPS:
        if group not in observed_groups:
            failures.append(f"actionMatrix missing {group} group")
    return failures


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def observed_by_mentions_runtime(value: Any) -> bool:
    if isinstance(value, str):
        haystack = value.lower()
    elif isinstance(value, list):
        haystack = " ".join(str(item).lower() for item in value)
    else:
        return False
    return "runtime" in haystack and ("click" in haystack or "shortcut" in haystack or "keyboard" in haystack or "visible" in haystack)


def input_editing_is_safe(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("inputEditingSafe") is True or value.get("suppressedInTextInput") is True:
            return True
        status = str(value.get("status", "")).lower()
        return status in {"pass", "passed"} and value.get("triggeredWhileEditing") is False
    if isinstance(value, str):
        lowered = value.lower()
        return ("input" in lowered or "textarea" in lowered or "editing" in lowered) and (
            "safe" in lowered or "suppressed" in lowered or "not trigger" in lowered
        )
    return False


def visible_target_assertion_passes(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if not isinstance(value, dict):
        return False
    if value.get("visible") is False:
        return False
    status = str(value.get("status", "pass")).lower()
    if status not in {"pass", "passed"}:
        return False
    label = first_present(value, "label", "name", "selector", "text", "testId")
    return isinstance(label, str) and bool(label.strip())


def validate_legacy_layout_screenshots(value: Any) -> list[str]:
    failures = validate_desktop_ui_click_screenshots(value)
    if not isinstance(value, list):
        return failures
    labels = [
        str(first_present(screenshot, "label", "name", "step", "scenario")).lower()
        for screenshot in value
        if isinstance(screenshot, dict)
    ]
    for required in LEGACY_LAYOUT_REQUIRED_SCREENSHOTS:
        if not any(required in label or required.replace("/", " ") in label.replace("/", " ") for label in labels):
            failures.append(f"screenshots missing {required}")
    return failures


def validate_legacy_shortcut_layout_screenshots(value: Any) -> list[str]:
    failures = validate_legacy_layout_screenshots(value)
    if not isinstance(value, list):
        return failures
    for index, screenshot in enumerate(value):
        if not isinstance(screenshot, dict):
            continue
        if not isinstance(screenshot.get("source"), str) or not screenshot.get("source", "").strip():
            failures.append(f"screenshots[{index}].source must be non-empty")
        size_bytes = int_or_none(first_present(screenshot, "sizeBytes", "bytes"))
        if size_bytes is None or size_bytes <= 0:
            failures.append(f"screenshots[{index}].sizeBytes must be positive")
        captured_after = screenshot.get("capturedAfterActionId")
        if not isinstance(captured_after, str) or not captured_after.strip():
            failures.append(f"screenshots[{index}].capturedAfterActionId must be non-empty")
    return failures


def validate_legacy_layout_viewports(evidence: dict[str, Any]) -> list[str]:
    screenshots = evidence.get("screenshots")
    viewports = first_present(evidence, "viewports", "viewportMatrix")
    candidates: list[Any] = []
    if isinstance(viewports, list):
        candidates.extend(viewports)
    if isinstance(screenshots, list):
        for screenshot in screenshots:
            if isinstance(screenshot, dict):
                viewport = first_present(screenshot, "viewport", "window", "size")
                if viewport is not None:
                    candidates.append(viewport)
    normalized = [normalize_viewport(candidate) for candidate in candidates]
    normalized = [viewport for viewport in normalized if viewport is not None]
    failures: list[str] = []
    unique = {(width, height) for width, height in normalized}
    if len(unique) < 3:
        failures.append("viewports must include at least three sizes")
    if (1280, 840) not in unique:
        failures.append("viewports must include 1280x840")
    if not any(width < 1000 and height >= 700 for width, height in unique):
        failures.append("viewports must include narrow desktop")
    if not any(height < 700 and width >= 1000 for width, height in unique):
        failures.append("viewports must include short window")
    return failures


def normalize_viewport(value: Any) -> tuple[int, int] | None:
    if isinstance(value, dict):
        width = first_present(value, "width", "w")
        height = first_present(value, "height", "h")
    elif isinstance(value, str):
        match = re.search(r"(\d{3,5})\s*x\s*(\d{3,5})", value.lower())
        if not match:
            return None
        width, height = int(match.group(1)), int(match.group(2))
        return (width, height)
    else:
        return None
    if isinstance(width, int) and isinstance(height, int):
        return (width, height)
    return None


def validate_legacy_layout_visible_assertions(value: Any) -> list[str]:
    failures = validate_desktop_ui_click_visible_assertions(value)
    if not isinstance(value, list):
        return failures
    assertion_labels: list[str] = []
    for assertion in value:
        if isinstance(assertion, str):
            assertion_labels.append(assertion.lower())
        elif isinstance(assertion, dict):
            assertion_labels.append(str(first_present(assertion, "label", "name", "selector", "text", "testId")).lower())
    haystack = " ".join(assertion_labels)
    for label, tokens in LEGACY_LAYOUT_REQUIRED_VISIBLE_TARGETS:
        if not any(token in haystack for token in tokens):
            failures.append(f"visibleAssertions missing {label}")
    return failures


def validate_legacy_layout_no_critical_overlap_or_clipping(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    forbidden_true_fields = [
        "criticalOverlap",
        "criticalOverlapDetected",
        "hasCriticalOverlap",
        "criticalClipping",
        "criticalClippingDetected",
        "hasCriticalClipping",
    ]
    for key in forbidden_true_fields:
        if evidence.get(key) is True:
            failures.append(f"{key} must not be true")
    checks = evidence.get("checks")
    if isinstance(checks, list):
        for check in checks:
            details = check_evidence(check)
            if isinstance(details, dict):
                for key in forbidden_true_fields:
                    if details.get(key) is True:
                        failures.append(f"{check.get('name', 'check')}.{key} must not be true")
    assertions = evidence.get("visibleAssertions")
    if isinstance(assertions, list):
        for index, assertion in enumerate(assertions):
            if isinstance(assertion, dict):
                if assertion.get("overlap") is True or assertion.get("clipped") is True:
                    failures.append(f"visibleAssertions[{index}] must not be overlapped or clipped")
    return failures


def validate_legacy_layout_boundaries(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    boundaries = evidence.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries must be an object")
        boundaries = {}
    for key in LEGACY_LAYOUT_REQUIRED_FALSE_FIELDS:
        top_value = evidence.get(key)
        boundary_value = boundaries.get(key)
        if top_value is True:
            failures.append(f"{key} must be false")
        if boundary_value is not False:
            failures.append(f"boundaries.{key} must be false")
    return failures


def validate_legacy_shortcut_layout_boundaries(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    boundaries = evidence.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries must be an object")
        boundaries = {}
    for key in LEGACY_SHORTCUT_LAYOUT_REQUIRED_FALSE_FIELDS:
        top_value = evidence.get(key)
        boundary_value = boundaries.get(key)
        if top_value is True:
            failures.append(f"{key} must be false")
        if boundary_value is not False:
            failures.append(f"boundaries.{key} must be false")
    return failures


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


def validate_installed_app_runtime_workflow_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != INSTALLED_APP_RUNTIME_WORKFLOW_SCHEMA:
        failures.append(f"schema must be {INSTALLED_APP_RUNTIME_WORKFLOW_SCHEMA}")
    if str(evidence.get("name", "installed_app_runtime_workflow")) != "installed_app_runtime_workflow":
        failures.append("name must be installed_app_runtime_workflow")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")

    collection_method = str(evidence.get("collectionMethod", "")).lower()
    if not collection_method.strip():
        failures.append("collectionMethod must be recorded")
    if "static" in collection_method and "runtime" not in collection_method:
        failures.append("collectionMethod must not be static-only")
    if "artifact" in collection_method and "runtime" not in collection_method:
        failures.append("collectionMethod must not be artifact-only")

    for key in INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_TRUE_FIELDS:
        if evidence.get(key) is not True:
            failures.append(f"{key} must be true")
    failures.extend(validate_installed_app_runtime_workflow_false_boundaries(evidence))
    failures.extend(validate_installed_macos_app_bundle(evidence.get("appBundle"), evidence))
    failures.extend(validate_installed_macos_app_artifact_paths(evidence))
    failures.extend(validate_installed_app_runtime_workflow_process(evidence.get("runtimeProcess")))
    failures.extend(validate_installed_app_runtime_workflow_actions(evidence))
    failures.extend(validate_installed_app_runtime_workflow_screenshots(evidence))
    failures.extend(validate_installed_app_backend_runtime_proof(evidence.get("backendRuntimeProof")))
    failures.extend(validate_installed_macos_app_dev_server_boundaries(evidence))
    failures.extend(validate_installed_macos_app_termination(evidence))

    check_by_name = installed_app_runtime_workflow_check_by_name(evidence)
    missing = [name for name in INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_CHECKS if name not in check_by_name]
    not_pass = [
        name
        for name in INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_CHECKS
        if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
    ]
    if missing:
        failures.append("missing required checks: " + ", ".join(missing))
    if not_pass:
        failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_installed_app_runtime_workflow_check_details(check_by_name))
    return failures


def validate_installed_app_runtime_workflow_false_boundaries(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    boundaries = evidence.get("boundaries")
    if not isinstance(boundaries, dict):
        return ["boundaries must be an object"]
    for key in INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_FALSE_FIELDS:
        if evidence.get(key) is not False:
            failures.append(f"{key} must be false")
        if boundaries.get(key) is not False:
            failures.append(f"boundaries.{key} must be false")
    return failures


def validate_installed_app_runtime_workflow_process(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["runtimeProcess must be an object"]
    failures: list[str] = []
    if first_present(value, "observed", "runtimeProcessObserved", "processObserved") is not True:
        failures.append("runtimeProcess.observed must be true")
    name = first_present(value, "name", "processName", "binaryName")
    if not isinstance(name, str) or not name.strip():
        failures.append("runtimeProcess must include process name")
    pid = first_present(value, "pid", "pidObserved", "processId")
    if pid is not None and not positive_number(pid):
        failures.append("runtimeProcess.pid must be positive when present")
    return failures


def validate_installed_app_runtime_workflow_actions(evidence: dict[str, Any]) -> list[str]:
    actions = first_present(evidence, "workflowActions", "runtimeActions", "actions")
    if not isinstance(actions, list):
        return ["workflowActions must be a list"]
    failures: list[str] = []
    if len(actions) < len(INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_ACTIONS):
        failures.append("workflowActions must include launch, window, runtime action, and termination records")
    seen_action_ids: list[str] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            failures.append(f"workflowActions[{index}] must be an object")
            continue
        action_id = first_present(action, "actionId", "id", "name")
        if not isinstance(action_id, str) or not action_id.strip():
            failures.append(f"workflowActions[{index}] must include actionId/id/name")
        else:
            seen_action_ids.append(action_id)
        if str(first_present(action, "status", "result") or "").lower() != "pass":
            failures.append(f"workflowActions[{index}].status must be pass")
        if first_present(action, "runtimeObserved", "observed", "verified") is not True:
            failures.append(f"workflowActions[{index}].runtimeObserved must be true")
        evidence_detail = first_present(action, "evidence", "details", "assertions")
        if not non_empty_proof(evidence_detail):
            failures.append(f"workflowActions[{index}] must include evidence/details")
        elif action_id == "execute_runtime_action" and isinstance(evidence_detail, dict):
            backend_command = first_present(evidence_detail, "backendCommand", "command")
            proof_schema = first_present(evidence_detail, "proofSchema", "schema")
            if backend_command != "installed_app_runtime_proof":
                failures.append("workflowActions execute_runtime_action must cite installed_app_runtime_proof backend command")
            if proof_schema != INSTALLED_APP_RUNTIME_PROOF_SCHEMA:
                failures.append(f"workflowActions execute_runtime_action proofSchema must be {INSTALLED_APP_RUNTIME_PROOF_SCHEMA}")
    missing_actions = [
        required
        for required in INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_ACTIONS
        if required not in seen_action_ids
    ]
    if missing_actions:
        failures.append("workflowActions missing: " + ", ".join(missing_actions))
    return failures


def validate_installed_app_runtime_workflow_screenshots(evidence: dict[str, Any]) -> list[str]:
    screenshots = first_present(evidence, "screenshots", "windowScreenshots", "appScreenshots")
    if screenshots is None and isinstance(evidence.get("screenshot"), dict):
        screenshots = [evidence["screenshot"]]
    if not isinstance(screenshots, list):
        return ["screenshots must be a list"]
    failures: list[str] = []
    if not screenshots:
        failures.append("screenshots must include at least one installed app runtime screenshot")
    for index, screenshot in enumerate(screenshots):
        if not isinstance(screenshot, dict):
            failures.append(f"screenshots[{index}] must be an object")
            continue
        sha256 = screenshot.get("sha256")
        if not is_sha256_hex(sha256):
            failures.append(f"screenshots[{index}].sha256 must be a 64-character hex sha256")
        size = first_present(screenshot, "sizeBytes", "bytes")
        if not positive_number(size):
            failures.append(f"screenshots[{index}].sizeBytes must be positive")
        label = first_present(screenshot, "label", "name", "step")
        if not isinstance(label, str) or not label.strip():
            failures.append(f"screenshots[{index}] must include label/name/step")
        path = screenshot.get("path")
        if not isinstance(path, str) or not path.strip():
            failures.append(f"screenshots[{index}].path must be a stable repo-relative or non-local path")
        elif not is_stable_artifact_path(path):
            failures.append(f"screenshots[{index}].path must not be a local absolute path")
        source = first_present(screenshot, "source", "captureSource")
        if source not in {"installed_app_runtime", "tauri_installed_app_runtime", "macos_installed_app"}:
            failures.append(f"screenshots[{index}].source must be installed app runtime")
        captured_after = first_present(screenshot, "capturedAfterActionId", "afterActionId")
        if captured_after not in INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_ACTIONS:
            failures.append(f"screenshots[{index}].capturedAfterActionId must reference a required runtime action")
    return failures


def validate_installed_app_backend_runtime_proof(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["backendRuntimeProof must be an object"]
    failures: list[str] = []
    if value.get("schema") != INSTALLED_APP_RUNTIME_PROOF_SCHEMA:
        failures.append(f"backendRuntimeProof.schema must be {INSTALLED_APP_RUNTIME_PROOF_SCHEMA}")
    status = str(value.get("status", "")).lower()
    if status not in {"ok", "pass", "passed", "observed"}:
        failures.append("backendRuntimeProof.status must be ok/pass/observed")

    runtime = value.get("runtime")
    if not isinstance(runtime, dict):
        failures.append("backendRuntimeProof.runtime must be an object")
    else:
        runtime_source = first_present(runtime, "source", "runtimeSource")
        if not isinstance(runtime_source, str) or not runtime_source.strip():
            failures.append("backendRuntimeProof.runtime.source must be recorded")
        elif "browser" in runtime_source.lower() or "static" in runtime_source.lower():
            failures.append("backendRuntimeProof.runtime.source must be a Tauri runtime source")
        if first_present(runtime, "tauriRuntimeObserved", "tauri_runtime_observed") is not True:
            failures.append("backendRuntimeProof.runtime.tauriRuntimeObserved must be true")
        if first_present(runtime, "devServerRequired", "dev_server_required") is not False:
            failures.append("backendRuntimeProof.runtime.devServerRequired must be false")
        resource_dir = first_present(runtime, "resourceDir", "resource_dir")
        app_data_dir = first_present(runtime, "appDataDir", "app_data_dir")
        if not isinstance(resource_dir, str) or not resource_dir.strip():
            failures.append("backendRuntimeProof.runtime.resourceDir must be recorded")
        if not isinstance(app_data_dir, str) or not app_data_dir.strip():
            failures.append("backendRuntimeProof.runtime.appDataDir must be recorded")

    bundle = value.get("bundle")
    if not isinstance(bundle, dict):
        failures.append("backendRuntimeProof.bundle must be an object")
    else:
        if first_present(bundle, "appBundleExists", "app_bundle_exists", "exists") is not True:
            failures.append("backendRuntimeProof.bundle.appBundleExists must be true")
        if first_present(bundle, "executableExists", "executable_exists") is not True:
            failures.append("backendRuntimeProof.bundle.executableExists must be true")
        if first_present(bundle, "resourceDirExists", "resource_dir_exists") is not True:
            failures.append("backendRuntimeProof.bundle.resourceDirExists must be true")
        bundle_path = first_present(bundle, "appBundlePath", "app_bundle_path", "path")
        if isinstance(bundle_path, str) and bundle_path.strip() and not is_stable_or_sanitized_path(bundle_path):
            failures.append("backendRuntimeProof.bundle.appBundlePath must be sanitized or repo-relative")

    failures.extend(validate_installed_app_backend_asset_validation(value.get("assets")))
    failures.extend(validate_installed_app_backend_profile_status(value.get("profileStatus")))
    failures.extend(validate_installed_app_backend_engine_launch_attempt(value.get("engineLaunchAttempt")))

    boundaries = value.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("backendRuntimeProof.boundaries must be an object")
    else:
        for key in ("browserFallbackUsed", "devServerStarted", "realReleasePublished", "productionSigned", "notarized", "fullLegacyParity"):
            if boundaries.get(key) is not False:
                failures.append(f"backendRuntimeProof.boundaries.{key} must be false")
    return failures


def validate_installed_app_backend_asset_validation(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["backendRuntimeProof.assets must be an object"]
    failures: list[str] = []
    status = str(value.get("status", "")).lower()
    missing_count = installed_app_asset_count(value, "missing")
    placeholder_count = installed_app_asset_count(value, "placeholders")
    observed_count = installed_app_asset_count(value, "checks") + installed_app_asset_count(value, "exists")
    if status in {"ready", "ok", "pass", "passed", "success", "available"} and (missing_count > 0 or placeholder_count > 0):
        failures.append("backendRuntimeProof.assets must not be ready when missing/placeholders are present")
    if observed_count <= 0 and missing_count <= 0 and placeholder_count <= 0:
        failures.append("backendRuntimeProof.assets must include observed checks/exists entries")
    return failures


def installed_app_asset_count(value: dict[str, Any], key: str) -> int:
    field = value.get(key)
    if isinstance(field, list):
        return len(field)
    if isinstance(field, (int, float)):
        return int(field)
    return 0


def validate_installed_app_backend_profile_status(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["backendRuntimeProof.profileStatus must be an object"]
    failures: list[str] = []
    status = str(value.get("status", "")).lower()
    if not status:
        failures.append("backendRuntimeProof.profileStatus.status must be recorded")
    if status in {"error", "failed", "invalid"}:
        failures.append("backendRuntimeProof.profileStatus must not be error for pass evidence")
    profile_count = first_present(value, "profileCount", "profile_count")
    if profile_count is not None and not positive_number(profile_count):
        failures.append("backendRuntimeProof.profileStatus.profileCount must be positive when present")
    if value.get("loaded") is False and status == "loaded":
        failures.append("backendRuntimeProof.profileStatus.loaded cannot be false when status is loaded")
    return failures


def validate_installed_app_backend_engine_launch_attempt(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["backendRuntimeProof.engineLaunchAttempt must be an object"]
    failures: list[str] = []
    status = str(first_present(value, "status", "result", "outcome") or "").lower()
    if not status:
        failures.append("backendRuntimeProof.engineLaunchAttempt.status must be recorded")
    if first_present(value, "attempted", "launchAttempted") is not True:
        failures.append("backendRuntimeProof.engineLaunchAttempt.attempted must be true")
    success_claim = first_present(value, "success", "launched", "engineAvailable")
    unavailable = bool(re.search(r"unavailable|missing|not[_ -]?found|not[_ -]?configured|skipped", status))
    problem = bool(re.search(r"error|fail|problem|invalid", status))
    if (unavailable or problem) and success_claim is True:
        failures.append("backendRuntimeProof.engineLaunchAttempt unavailable/problem status must not be counted as success")
    if status in {"success", "launched", "available", "ok"} and success_claim is False:
        failures.append("backendRuntimeProof.engineLaunchAttempt success status cannot have success=false")
    return failures


def is_stable_or_sanitized_path(value: str) -> bool:
    path = value.strip()
    if path.startswith(("<repo>/", "<home>/", "<app-data>/", "<resource>/")):
        return True
    return is_stable_artifact_path(path)


def installed_app_runtime_workflow_check_by_name(evidence: dict[str, Any]) -> dict[str, Any]:
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        return {}
    return {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }


def validate_installed_app_runtime_workflow_check_details(check_by_name: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    def require_detail(name: str) -> dict[str, Any] | None:
        detail = check_evidence(check_by_name.get(name))
        if detail is None:
            failures.append(f"{name} evidence must be an object")
            return None
        return detail

    bundle = require_detail("app_bundle_verified")
    if bundle is not None:
        failures.extend(validate_installed_macos_app_bundle(bundle.get("appBundle", bundle), bundle))
    launch = require_detail("installed_app_launched")
    if launch is not None and first_present(launch, "installedAppLaunched", "launched") is not True:
        failures.append("installed_app_launched.installedAppLaunched must be true")
    process = require_detail("runtime_process_observed")
    if process is not None:
        failures.extend(validate_installed_app_runtime_workflow_process(process.get("runtimeProcess", process)))
    window = require_detail("window_observed")
    if window is not None and first_present(window, "windowObserved", "observed") is not True:
        failures.append("window_observed.windowObserved must be true")
    workflow = require_detail("workflow_action_executed")
    if workflow is not None:
        if first_present(workflow, "workflowExecuted", "runtimeActionObserved") is not True:
            failures.append("workflow_action_executed.workflowExecuted must be true")
        action_id = first_present(workflow, "actionId", "runtimeActionId")
        if action_id == "launch_installed_app":
            failures.append("workflow_action_executed must record a non-launch runtime action")
        backend_command = first_present(workflow, "backendCommand", "command")
        proof_schema = first_present(workflow, "proofSchema", "schema")
        if backend_command != "installed_app_runtime_proof":
            failures.append("workflow_action_executed must cite installed_app_runtime_proof backend command")
        if proof_schema != INSTALLED_APP_RUNTIME_PROOF_SCHEMA:
            failures.append(f"workflow_action_executed proofSchema must be {INSTALLED_APP_RUNTIME_PROOF_SCHEMA}")
    backend = require_detail("backend_runtime_proof_observed")
    if backend is not None:
        proof = first_present(backend, "backendRuntimeProof", "runtimeProof", "proof")
        if proof is None:
            proof = backend
        failures.extend(validate_installed_app_backend_runtime_proof(proof))
    screenshot = require_detail("screenshot_recorded")
    if screenshot is not None:
        screenshot_records = first_present(screenshot, "screenshots", "windowScreenshots")
        if not isinstance(screenshot_records, list) or not screenshot_records:
            failures.append("screenshot_recorded must include screenshot records")
    dev_server = require_detail("dev_server_absent")
    if dev_server is not None and first_present(dev_server, "devServerAbsent", "absent") is not True:
        failures.append("dev_server_absent.devServerAbsent must be true")
    termination = require_detail("quit_or_terminate_observed")
    if termination is not None:
        failures.extend(validate_installed_macos_app_termination({"termination": termination}))
    boundaries = require_detail("scope_boundaries_recorded")
    if boundaries is not None:
        boundary_detail = boundaries.get("boundaries", boundaries)
        if not isinstance(boundary_detail, dict):
            failures.append("scope_boundaries_recorded.boundaries must be an object")
        else:
            for key in INSTALLED_APP_RUNTIME_WORKFLOW_REQUIRED_FALSE_FIELDS:
                if boundary_detail.get(key) is not False:
                    failures.append(f"scope_boundaries_recorded.boundaries.{key} must be false")
    return failures


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


def validate_katago_review_workflow_ux_source_facts(root: Path) -> list[str]:
    app_path = root / APP_SOURCE
    engine_panel_path = root / ENGINE_SETUP_PANEL_SOURCE
    backend_path = root / BACKEND_SOURCE
    missing = [
        label
        for label, path in (
            ("App source", app_path),
            ("EngineSetupPanel source", engine_panel_path),
            ("backend source", backend_path),
        )
        if not path.is_file()
    ]
    if missing:
        return ["missing source file(s): " + ", ".join(missing)]
    app_text = app_path.read_text(encoding="utf-8")
    engine_text = engine_panel_path.read_text(encoding="utf-8")
    backend_text = backend_path.read_text(encoding="utf-8")
    return [
        *missing_required_tokens(
            app_text,
            "App KataGo review workflow",
            [
                "handleAnalyzeKataGoGame",
                "listenToKataGoAnalysisEvents",
                "setAnalysisProgress",
                "payload.job_id",
                "completed",
                "expected",
                "payload.turn",
                "activeJobIdRef",
                "setActiveJobId",
                "Full-game KataGo analysis started",
                "handleCancelKataGoAnalysis",
                "cancelKataGoAnalysis",
                "Full-game KataGo analysis cancelled",
                "finishStoppedAnalysis",
                "finishCompletedAnalysis",
                "KataGo analysis failed",
                "saveAnalysisCacheForGame",
                "checkAnalysisCacheForGame",
                "loadPreferredAnalysisCache",
                "Restored",
                "isCurrentAnalysisJob",
                "pendingAnalysisProgressRef",
                "pendingAnalysisTerminalEventsRef",
                "activeJobIdRef.current === jobId",
                "computeGameCacheKey",
            ],
        ),
        *missing_required_tokens(
            engine_text,
            "EngineSetupPanel KataGo review UX",
            [
                "analysisProgress",
                "activeJobId",
                "progressLabel",
                "completed",
                "expected",
                "turn",
                "analysis-progress",
                "progressPercent",
                "Analyze game",
                "Cancel",
                "onCancelAnalysis",
            ],
        ),
        *missing_required_tokens(
            backend_text,
            "backend KataGo review workflow",
            [
                "startKataGoGameAnalysis",
                "katago_start_analyze_game",
                "cancelKataGoAnalysis",
                "katago_cancel_analysis",
                "listenToKataGoAnalysisEvents",
                "katago://analysis-progress",
                "katago://analysis-complete",
                "katago://analysis-error",
                "katago://analysis-cancelled",
            ],
        ),
    ]


def validate_katago_review_workflow_ux_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != KATAGO_REVIEW_WORKFLOW_UX_SMOKE_SCHEMA:
        failures.append(f"schema must be {KATAGO_REVIEW_WORKFLOW_UX_SMOKE_SCHEMA}")
    if evidence.get("name") != "scoped_katago_review_workflow_ux_resilience":
        failures.append("name must be scoped_katago_review_workflow_ux_resilience")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    if evidence.get("collectionMethod") not in KATAGO_REVIEW_WORKFLOW_UX_COLLECTION_METHODS:
        failures.append("collectionMethod must be source_static_plus_stubbed_ui_flow")
    for key in KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_TRUE_FIELDS:
        if evidence.get(key) is not True:
            failures.append(f"{key} must be true")
    for key in KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_FALSE_FIELDS:
        if evidence.get(key) is not False:
            failures.append(f"{key} must be false")
    runtime_metadata = evidence.get("runtimeMetadata")
    if evidence.get("liveKataGoObserved") is True:
        if not isinstance(runtime_metadata, dict) or not runtime_metadata:
            failures.append("liveKataGoObserved true requires runtimeMetadata")
        else:
            for key in ("enginePath", "modelPath", "configPath", "katagoVersion"):
                if not isinstance(runtime_metadata.get(key), str) or not runtime_metadata.get(key):
                    failures.append(f"runtimeMetadata.{key} must be non-empty when liveKataGoObserved is true")
    elif runtime_metadata not in (None, False):
        failures.append("runtimeMetadata must be absent/null unless liveKataGoObserved is true")

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
        missing = [name for name in KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_CHECKS if name not in check_by_name]
        not_pass = [
            name
            for name in KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_CHECKS
            if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
        ]
        if missing:
            failures.append("missing required checks: " + ", ".join(missing))
        if not_pass:
            failures.append("required checks not pass: " + ", ".join(not_pass))
        for name in KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_CHECKS:
            details = check_evidence(check_by_name.get(name))
            if details is None:
                failures.append(f"{name} evidence must be an object")
            elif len(details) == 0:
                failures.append(f"{name} evidence must not be empty")
    failures.extend(validate_katago_review_workflow_ux_check_details(check_by_name))
    failures.extend(validate_katago_review_workflow_ux_boundaries(evidence))
    return failures


def validate_katago_review_workflow_ux_check_details(check_by_name: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_flags = {
        "progress_verified": "progressVerified",
        "cancel_verified": "cancelVerified",
        "restart_after_cancel_verified": "restartAfterCancelVerified",
        "cache_restore_verified": "cacheRestoreVerified",
        "engine_failure_verified": "engineFailureVerified",
        "stale_analysis_prevented": "staleAnalysisPrevented",
        "source_facts_validated": "sourceFactsValidated",
    }
    for check_name, flag in expected_flags.items():
        details = check_evidence(check_by_name.get(check_name))
        if not isinstance(details, dict):
            continue
        if details.get(flag) is not True:
            failures.append(f"{check_name}.{flag} must be true")
    progress = check_evidence(check_by_name.get("progress_verified"))
    if isinstance(progress, dict):
        for key in ("jobIdVisible", "currentVisible", "totalVisible", "sessionVisible"):
            if progress.get(key) is not True:
                failures.append(f"progress_verified.{key} must be true")
    stale = check_evidence(check_by_name.get("stale_analysis_prevented"))
    if isinstance(stale, dict) and not any(stale.get(key) is True for key in ("jobIdGuard", "generationGuard", "hashGuard")):
        failures.append("stale_analysis_prevented must include jobIdGuard, generationGuard, or hashGuard")
    return failures


def validate_katago_review_workflow_ux_boundaries(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    boundaries = evidence.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries must be an object")
        boundaries = {}
    for key in KATAGO_REVIEW_WORKFLOW_UX_REQUIRED_FALSE_FIELDS:
        if boundaries.get(key) is not False:
            failures.append(f"boundaries.{key} must be false")
    source_evidence = evidence.get("sourceEvidence")
    if isinstance(source_evidence, dict):
        referenced = source_evidence.get("referencedEvidence")
        if isinstance(referenced, list):
            live_refs = {KATAGO_LIVE_SMOKE_EVIDENCE, KATAGO_TAURI_RUNTIME_SMOKE_EVIDENCE}
            if any(ref in live_refs for ref in referenced) and evidence.get("liveKataGoObserved") is True:
                failures.append("existing live evidence must not be reused to claim new live review workflow behavior")
        if source_evidence.get("existingLiveEvidenceUsedForNewLiveBehavior") is True:
            failures.append("existing live evidence must not be used for new live behavior claims")
    return failures


def validate_legacy_config_corpus_migration_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_SCHEMA:
        failures.append(f"schema must be {LEGACY_CONFIG_CORPUS_MIGRATION_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    count = first_present(evidence, "corpusFixtureCount", "fixtureCount", "fixturesCount")
    if not isinstance(count, int) or count < 8:
        failures.append("corpus fixture count must be at least 8")
    failures.extend(
        missing_string_members(
            first_present(evidence, "fixtureClasses", "requiredFixtureClasses", "classes"),
            LEGACY_CONFIG_CORPUS_REQUIRED_FIXTURE_CLASSES,
            "fixtureClasses",
        )
    )
    for key in LEGACY_CONFIG_CORPUS_REQUIRED_TRUE_FIELDS:
        if evidence.get(key) is not True:
            failures.append(f"{key} must be true")
    boundaries = evidence.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries must be an object")
        boundaries = {}
    for key in LEGACY_CONFIG_CORPUS_REQUIRED_FALSE_FIELDS:
        if evidence.get(key) is True:
            failures.append(f"{key} must be false")
        if boundaries.get(key) is not False:
            failures.append(f"boundaries.{key} must be false")
    checks = evidence.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict) and str(check.get("status", "")).lower() not in {"pass", "passed"}:
                failures.append(f"{check.get('name', 'check')} must be pass")
    return failures


def validate_katago_live_desktop_workflow_smoke_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_SCHEMA:
        failures.append(f"schema must be {KATAGO_LIVE_DESKTOP_WORKFLOW_SMOKE_SCHEMA}")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    if katago_live_desktop_observed(evidence) is not True:
        failures.append("liveKataGoObserved must be true")
    if katago_live_browser_fallback_used(evidence) is not False:
        failures.append("browserFallbackUsed must be false")
    for key in KATAGO_LIVE_DESKTOP_WORKFLOW_REQUIRED_FALSE_FIELDS:
        if evidence.get(key) is True:
            failures.append(f"{key} must be false")

    check_by_name = katago_live_desktop_workflow_check_by_name(evidence)
    raw_checks = evidence.get("checks")
    runtime_checks = evidence.get("runtimeReport", {}).get("checks") if isinstance(evidence.get("runtimeReport"), dict) else None
    if not isinstance(raw_checks, list) and not isinstance(runtime_checks, list):
        failures.append("checks must be a list")
    else:
        missing = [name for name in KATAGO_LIVE_DESKTOP_WORKFLOW_REQUIRED_CHECKS if name not in check_by_name]
        not_pass = [
            name
            for name in KATAGO_LIVE_DESKTOP_WORKFLOW_REQUIRED_CHECKS
            if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
        ]
        if missing:
            failures.append("missing required checks: " + ", ".join(missing))
        if not_pass:
            failures.append("required checks not pass: " + ", ".join(not_pass))
        for name in KATAGO_LIVE_DESKTOP_WORKFLOW_REQUIRED_CHECKS:
            details = check_evidence(check_by_name.get(name))
            if details is None:
                failures.append(f"{name} evidence must be an object")
            elif not details:
                failures.append(f"{name} evidence must not be empty")

    failures.extend(validate_katago_live_desktop_workflow_check_details(check_by_name))
    failures.extend(validate_katago_live_desktop_workflow_boundaries(evidence, check_by_name))
    return failures


def katago_live_desktop_workflow_check_by_name(evidence: dict[str, Any]) -> dict[str, Any]:
    checks: list[Any] = []
    for candidate in (
        evidence.get("checks"),
        evidence.get("runtimeReport", {}).get("checks") if isinstance(evidence.get("runtimeReport"), dict) else None,
    ):
        if isinstance(candidate, list):
            checks.extend(candidate)
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    aliases = {
        "tauriRuntimeObserved": "runtime_started",
        "realKataGoAssetsObserved": "engine_assets_verified",
        "analysisProgressObserved": "analysis_progress_observed",
        "cancelObserved": "cancel_observed",
        "restartAfterCancelObserved": "restart_after_cancel_observed",
        "analysisCompleteObserved": "analysis_complete_observed",
        "cacheSaved": "cache_saved",
        "cacheHitRestored": "cache_hit_restored",
        "staleCachePrevented": "stale_cache_prevented",
        "engineFailureObserved": "engine_failure_observed",
    }
    for alias, canonical in aliases.items():
        if canonical not in check_by_name and alias in check_by_name:
            check_by_name[canonical] = check_by_name[alias]
    return check_by_name


def katago_live_browser_fallback_used(evidence: dict[str, Any]) -> Any:
    for candidate in (evidence, evidence.get("proofs"), evidence.get("boundaries")):
        if isinstance(candidate, dict) and "browserFallbackUsed" in candidate:
            return candidate.get("browserFallbackUsed")
    return None


def katago_live_desktop_observed(evidence: dict[str, Any]) -> bool:
    if evidence.get("liveKataGoObserved") is True:
        return True
    if evidence.get("liveKataGoObserved") is False:
        return False
    proofs = evidence.get("proofs")
    if isinstance(proofs, dict):
        return proofs.get("tauriRuntimeObserved") is True and proofs.get("realKataGoAssetsObserved") is True
    return False


def validate_katago_live_desktop_workflow_check_details(check_by_name: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    failures.extend(validate_katago_runtime_started(check_by_name.get("runtime_started")))
    failures.extend(validate_katago_live_desktop_assets(check_by_name.get("engine_assets_verified")))
    progress = check_evidence(check_by_name.get("analysis_progress_observed"))
    if isinstance(progress, dict):
        if progress.get("progressObserved") is not True and progress.get("analysisProgressObserved") is not True:
            failures.append("analysis_progress_observed.progressObserved must be true")
        if not isinstance(first_present(progress, "jobId", "job_id", "activeJobId"), str):
            failures.append("analysis_progress_observed must include job id")
        if not positive_number(first_present(progress, "completed", "current", "framesObserved", "frameCount")):
            failures.append("analysis_progress_observed must include positive progress/frame count")
        if not positive_number(first_present(progress, "expected", "total", "totalPositions")):
            failures.append("analysis_progress_observed must include positive expected/total count")

    cancel = check_evidence(check_by_name.get("cancel_observed"))
    if isinstance(cancel, dict):
        if cancel.get("cancelRequested") is not True:
            failures.append("cancel_observed must confirm cancellation was requested")
        if cancel.get("cancelObserved") is not True and cancel.get("cancelConfirmed") is not True:
            failures.append("cancel_observed must confirm cancellation was observed")

    restart = check_evidence(check_by_name.get("restart_after_cancel_observed"))
    if isinstance(restart, dict):
        if restart.get("restartAfterCancelObserved") is not True and restart.get("restartObserved") is not True and restart.get("restarted") is not True:
            failures.append("restart_after_cancel_observed.restartAfterCancelObserved must be true")
        first_job = first_present(restart, "cancelledJobId", "firstJobId")
        second_job = first_present(restart, "restartJobId", "secondJobId", "newJobId")
        if not isinstance(second_job, str) or not second_job:
            failures.append("restart_after_cancel_observed must include restart job id")
        if isinstance(first_job, str) and isinstance(second_job, str) and first_job == second_job:
            failures.append("restart_after_cancel_observed must use a new job id")

    complete = check_evidence(check_by_name.get("analysis_complete_observed"))
    if isinstance(complete, dict):
        if (
            complete.get("analysisCompleteObserved") is not True
            and complete.get("completeObserved") is not True
            and validate_katago_live_frame_candidate_winrate(complete, "analysis_complete_observed")
        ):
            failures.append("analysis_complete_observed.analysisCompleteObserved must be true")
        failures.extend(validate_katago_live_frame_candidate_winrate(complete, "analysis_complete_observed"))

    cache_saved = check_evidence(check_by_name.get("cache_saved"))
    if isinstance(cache_saved, dict):
        if cache_saved.get("cacheSaved") is not True and cache_saved.get("saved") is not True and not isinstance(cache_saved.get("saved"), dict):
            failures.append("cache_saved.cacheSaved must be true")
        if not isinstance(first_present(cache_saved, "cacheKey", "gameHash", "cacheHash", "recordId"), str) and not isinstance(cache_saved.get("key"), dict):
            failures.append("cache_saved must include cache key/hash")

    cache_hit = check_evidence(check_by_name.get("cache_hit_restored"))
    if isinstance(cache_hit, dict):
        if (
            cache_hit.get("cacheHitRestored") is not True
            and cache_hit.get("cacheRestored") is not True
            and cache_hit.get("hitStatus") != "hit"
        ):
            failures.append("cache_hit_restored.cacheHitRestored must be true")
        failures.extend(validate_katago_live_frame_candidate_winrate(cache_hit, "cache_hit_restored"))

    stale = check_evidence(check_by_name.get("stale_cache_prevented"))
    if isinstance(stale, dict):
        if stale.get("staleCachePrevented") is not True and stale.get("observed") is not True:
            failures.append("stale_cache_prevented.staleCachePrevented must be true")
        if stale.get("observed") is not True and not any(
            stale.get(key) is True or isinstance(stale.get(key), str)
            for key in (
                "jobIdGuard",
                "generationGuard",
                "hashGuard",
                "cacheKeyGuard",
                "changedSgfGameKey",
                "changedSgfStatus",
                "differentProfileStatus",
            )
        ):
            failures.append("stale_cache_prevented must include jobIdGuard, generationGuard, hashGuard, or cacheKeyGuard")

    failure = check_evidence(check_by_name.get("engine_failure_observed"))
    if isinstance(failure, dict):
        if failure.get("engineFailureObserved") is not True and failure.get("failureObserved") is not True and failure.get("observed") is not True:
            failures.append("engine_failure_observed.engineFailureObserved must be true")
        message = first_present(failure, "message", "error", "stderr", "statusText")
        missing_required = failure.get("missingRequired")
        if (not isinstance(message, str) or not message.strip()) and not (isinstance(missing_required, list) and missing_required):
            failures.append("engine_failure_observed must include failure message")

    fallback = check_evidence(check_by_name.get("browser_fallback_excluded"))
    if isinstance(fallback, dict) and fallback.get("browserFallbackUsed") is not False:
        failures.append("browser_fallback_excluded.browserFallbackUsed must be false")
    return failures


def validate_katago_live_desktop_assets(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["engine_assets_verified evidence must be an object"]
    failures: list[str] = []
    missing_required = evidence.get("missingRequired")
    if isinstance(missing_required, list):
        if missing_required:
            failures.append("engine_assets_verified must have no missing required assets")
        return failures
    if evidence.get("observed") is True:
        return failures
    if evidence.get("engineExists") is not True and evidence.get("engineExecutable") is not True:
        failures.append("engine_assets_verified must confirm engine exists")
    if not positive_number(first_present(evidence, "modelBytes", "modelSizeBytes")):
        failures.append("engine_assets_verified must include positive model bytes")
    if not positive_number(first_present(evidence, "configBytes", "configSizeBytes")):
        failures.append("engine_assets_verified must include positive config bytes")
    return failures


def validate_katago_live_frame_candidate_winrate(evidence: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    frame_count = first_present(evidence, "frameCount", "frames", "framesRestored", "restoredFrames")
    if not positive_number(frame_count):
        frames = evidence.get("frames")
        if not isinstance(frames, list) or not frames:
            failures.append(f"{label} must include frame evidence")
    candidate_count = first_present(
        evidence,
        "candidateCount",
        "candidateMoveCount",
        "moveInfoCount",
        "candidatesRestored",
        "restoredCandidates",
    )
    if not positive_number(candidate_count):
        candidates = first_present(evidence, "candidates", "moveInfos", "moveInfo")
        first_frame = evidence.get("firstFrame")
        first_frame_candidates = first_frame.get("candidates") if isinstance(first_frame, dict) else None
        if not isinstance(candidates, list) and not positive_number(first_frame_candidates):
            failures.append(f"{label} must include candidate evidence")
    if not any(
        key in evidence and evidence.get(key) not in (None, False, "")
        for key in ("winrate", "winrateRestored", "restoredWinrateBlack", "rootWinrate", "hasWinrate", "rootInfo")
    ):
        first_frame = evidence.get("firstFrame")
        if not isinstance(first_frame, dict) or first_present(first_frame, "winrate", "winrateBlack") in (None, False, ""):
            failures.append(f"{label} must include winrate evidence")
    return failures


def validate_katago_live_desktop_workflow_boundaries(
    evidence: dict[str, Any], check_by_name: dict[str, Any]
) -> list[str]:
    failures: list[str] = []
    candidates: list[Any] = [evidence.get("boundaries"), check_evidence(check_by_name.get("scope_boundaries_recorded"))]
    valid_boundary = False
    for boundaries in candidates:
        if not isinstance(boundaries, dict):
            continue
        boundary_failures: list[str] = []
        if "browserFallbackUsed" in boundaries and boundaries.get("browserFallbackUsed") is not False:
            failures.append("boundaries.browserFallbackUsed must be false")
        for key in KATAGO_LIVE_DESKTOP_WORKFLOW_REQUIRED_FALSE_FIELDS:
            if boundaries.get(key) is not False:
                boundary_failures.append(f"boundaries.{key} must be false")
            if boundaries.get(key) is True:
                failures.append(f"boundaries.{key} must be false")
        if not boundary_failures:
            valid_boundary = True
    if not valid_boundary:
        failures.append(
            "boundaries must include fullLegacyAnalysisParity/providerReadboardParity/releaseParity/arbitraryOcrParity=false"
        )
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
    failures.extend(validate_readboard_arbitrary_ocr_not_covered(check_by_name.get("arbitrary_ocr_not_covered")))
    failures.extend(validate_readboard_external_capture_not_covered(check_by_name.get("external_capture_not_covered")))
    return failures


def validate_readboard_image_import_smoke_evidence(evidence: Any, root: Path = ROOT) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != READBOARD_IMAGE_IMPORT_SMOKE_SCHEMA:
        failures.append(f"schema must be {READBOARD_IMAGE_IMPORT_SMOKE_SCHEMA}")
    if evidence.get("name") != "readboard_image_import_smoke":
        failures.append("name must be readboard_image_import_smoke")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    collection_method = evidence.get("collectionMethod")
    if collection_method not in {"controlled_fixture_image_import", "controlled_image_import_mvp"}:
        failures.append("collectionMethod must be controlled_fixture_image_import")
    for key in READBOARD_IMAGE_IMPORT_REQUIRED_TRUE_FIELDS:
        if evidence.get(key) is not True:
            failures.append(f"{key} must be true")
    for key in READBOARD_IMAGE_IMPORT_REQUIRED_FALSE_FIELDS:
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
        missing = [name for name in READBOARD_IMAGE_IMPORT_REQUIRED_CHECKS if name not in check_by_name]
        not_pass = [
            name
            for name in READBOARD_IMAGE_IMPORT_REQUIRED_CHECKS
            if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
        ]
        if missing:
            failures.append("missing required checks: " + ", ".join(missing))
        if not_pass:
            failures.append("required checks not pass: " + ", ".join(not_pass))
    failures.extend(validate_readboard_image_path_import(check_by_name.get("image_path_import"), root))
    failures.extend(validate_readboard_image_base64_import(check_by_name.get("image_base64_import")))
    failures.extend(validate_readboard_invalid_image_rejected(check_by_name.get("invalid_image_rejected")))
    failures.extend(validate_readboard_non_board_image_rejected(check_by_name.get("non_board_image_rejected")))
    failures.extend(validate_readboard_image_snapshot(check_by_name.get("snapshot_verified")))
    failures.extend(validate_readboard_image_protocol_regression(check_by_name.get("protocol_regression")))
    failures.extend(validate_readboard_image_scope_boundaries(check_by_name.get("scope_boundaries"), evidence))
    return failures


def validate_readboard_image_ocr_corpus_smoke_evidence(evidence: Any, root: Path = ROOT) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != READBOARD_IMAGE_OCR_CORPUS_SMOKE_SCHEMA:
        failures.append(f"schema must be {READBOARD_IMAGE_OCR_CORPUS_SMOKE_SCHEMA}")
    if evidence.get("name") != "readboard_image_ocr_corpus_smoke":
        failures.append("name must be readboard_image_ocr_corpus_smoke")
    if str(evidence.get("status", "")).lower() != "pass":
        failures.append("status must be pass")
    platform = str(evidence.get("platform", "")).lower()
    if platform not in {"macos", "darwin"}:
        failures.append("platform must be macos/darwin")
    collection_method = evidence.get("collectionMethod")
    if collection_method not in {"controlled_fixture_image_ocr_corpus", "controlled_image_ocr_corpus"}:
        failures.append("collectionMethod must be controlled_fixture_image_ocr_corpus")
    for key in READBOARD_IMAGE_OCR_CORPUS_REQUIRED_TRUE_FIELDS:
        if evidence.get(key) is not True:
            failures.append(f"{key} must be true")
    for key in READBOARD_IMAGE_OCR_CORPUS_REQUIRED_FALSE_FIELDS:
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
        missing = [name for name in READBOARD_IMAGE_OCR_CORPUS_REQUIRED_CHECKS if name not in check_by_name]
        not_pass = [
            name
            for name in READBOARD_IMAGE_OCR_CORPUS_REQUIRED_CHECKS
            if name in check_by_name and str(check_by_name[name].get("status", "")).lower() != "pass"
        ]
        if missing:
            failures.append("missing required checks: " + ", ".join(missing))
        if not_pass:
            failures.append("required checks not pass: " + ", ".join(not_pass))

    manifest = first_present(evidence, "fixtureManifest", "fixtures")
    failures.extend(validate_readboard_ocr_fixture_manifest(manifest, root))
    failures.extend(validate_readboard_ocr_path_base64_equivalence(check_by_name.get("path_base64_equivalence")))
    failures.extend(validate_readboard_invalid_image_rejected(check_by_name.get("invalid_image_rejected")))
    failures.extend(validate_readboard_non_board_image_rejected(check_by_name.get("non_board_image_rejected")))
    failures.extend(validate_readboard_truncated_image_rejected(check_by_name.get("truncated_image_rejected")))
    failures.extend(validate_readboard_ocr_board_size_coverage(check_by_name.get("board_size_coverage"), manifest))
    failures.extend(validate_readboard_ocr_stone_count_coverage(check_by_name.get("stone_count_coverage"), manifest))
    failures.extend(validate_readboard_ocr_hash_invariants(check_by_name.get("hash_invariants")))
    failures.extend(validate_readboard_external_capture_unsupported_contract(check_by_name.get("external_capture_unsupported_contract")))
    failures.extend(validate_readboard_ocr_scope_boundaries(check_by_name.get("scope_boundaries"), evidence))
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


def validate_readboard_arbitrary_ocr_not_covered(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["arbitrary_ocr_not_covered evidence must be an object"]
    failures: list[str] = []
    if evidence.get("covered") is not False:
        failures.append("arbitrary_ocr_not_covered.covered must be false")
    if evidence.get("controlledImageImportCoveredBySeparateGate") is not True:
        failures.append("arbitrary_ocr_not_covered.controlledImageImportCoveredBySeparateGate must be true")
    if evidence.get("fullOcrParity") is not False:
        failures.append("arbitrary_ocr_not_covered.fullOcrParity must be false")
    message = evidence.get("message")
    if not isinstance(message, str) or not message:
        failures.append("arbitrary_ocr_not_covered.message must be non-empty")
    elif "arbitrary" not in message.lower() and "ocr" not in message.lower():
        failures.append("arbitrary_ocr_not_covered.message must mention arbitrary OCR")
    return failures


def validate_readboard_external_capture_not_covered(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["external_capture_not_covered evidence must be an object"]
    failures: list[str] = []
    if evidence.get("covered") is not False:
        failures.append("external_capture_not_covered.covered must be false")
    if evidence.get("externalWindowCaptureCovered") is not False:
        failures.append("external_capture_not_covered.externalWindowCaptureCovered must be false")
    if evidence.get("externalClientCaptureCovered") is not False:
        failures.append("external_capture_not_covered.externalClientCaptureCovered must be false")
    return failures


def validate_readboard_image_path_import(check: Any, root: Path) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["image_path_import evidence must be an object"]
    failures: list[str] = []
    if evidence.get("imagePathImportVerified") is not True:
        failures.append("image_path_import.imagePathImportVerified must be true")
    source = first_present(evidence, "source", "sourceKind")
    if source not in {"path", "image_path", "file_path"}:
        failures.append("image_path_import.source must be path")
    image_path = first_present(evidence, "imagePath", "path")
    if not isinstance(image_path, str) or not image_path:
        failures.append("image_path_import.imagePath must be non-empty")
    else:
        failures.extend(validate_repo_relative_artifact(root, image_path, evidence, "image_path_import"))
    failures.extend(validate_readboard_image_snapshot_fields(evidence, "image_path_import"))
    return failures


def validate_readboard_image_base64_import(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["image_base64_import evidence must be an object"]
    failures: list[str] = []
    if evidence.get("imageBase64ImportVerified") is not True:
        failures.append("image_base64_import.imageBase64ImportVerified must be true")
    source = first_present(evidence, "source", "sourceKind")
    if source not in {"base64", "image_base64"}:
        failures.append("image_base64_import.source must be base64")
    if not positive_number(first_present(evidence, "base64Bytes", "decodedBytes", "decoded_bytes")):
        failures.append("image_base64_import.base64Bytes must be positive")
    failures.extend(validate_readboard_image_snapshot_fields(evidence, "image_base64_import"))
    return failures


def validate_readboard_invalid_image_rejected(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["invalid_image_rejected evidence must be an object"]
    failures: list[str] = []
    if evidence.get("invalidImageRejected") is not True:
        failures.append("invalid_image_rejected.invalidImageRejected must be true")
    if evidence.get("reportedAsSuccess") is not False:
        failures.append("invalid_image_rejected.reportedAsSuccess must be false")
    error_kind = first_present(evidence, "errorKind", "kind")
    if not isinstance(error_kind, str) or not error_kind:
        failures.append("invalid_image_rejected.errorKind must be non-empty")
    message = evidence.get("message")
    if not isinstance(message, str) or not message:
        failures.append("invalid_image_rejected.message must be non-empty")
    return failures


def validate_readboard_non_board_image_rejected(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["non_board_image_rejected evidence must be an object"]
    failures: list[str] = []
    if evidence.get("nonBoardImageRejected") is not True:
        failures.append("non_board_image_rejected.nonBoardImageRejected must be true")
    if evidence.get("reportedAsSuccess") is not False:
        failures.append("non_board_image_rejected.reportedAsSuccess must be false")
    message = evidence.get("message")
    if not isinstance(message, str) or not message:
        failures.append("non_board_image_rejected.message must be non-empty")
    elif "board" not in message.lower():
        failures.append("non_board_image_rejected.message must mention board")
    return failures


def validate_readboard_image_snapshot(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["snapshot_verified evidence must be an object"]
    failures: list[str] = []
    if evidence.get("snapshotVerified") is not True:
        failures.append("snapshot_verified.snapshotVerified must be true")
    failures.extend(validate_readboard_image_snapshot_fields(evidence, "snapshot_verified"))
    return failures


def validate_readboard_image_protocol_regression(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["protocol_regression evidence must be an object"]
    failures: list[str] = []
    if evidence.get("protocolRegressionVerified") is not True:
        failures.append("protocol_regression.protocolRegressionVerified must be true")
    if evidence.get("protocolLineCompatible") is not True:
        failures.append("protocol_regression.protocolLineCompatible must be true")
    if evidence.get("snapshotMatchesProtocol") is not True:
        failures.append("protocol_regression.snapshotMatchesProtocol must be true")
    return failures


def validate_readboard_image_scope_boundaries(check: Any, root_evidence: dict[str, Any]) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["scope_boundaries evidence must be an object"]
    failures: list[str] = []
    for key in READBOARD_IMAGE_IMPORT_REQUIRED_FALSE_FIELDS:
        if evidence.get(key) is not False:
            failures.append(f"scope_boundaries.{key} must be false")
        if root_evidence.get(key) is not False:
            failures.append(f"{key} must be false")
    return failures


def validate_readboard_ocr_fixture_manifest(manifest: Any, root: Path) -> list[str]:
    if not isinstance(manifest, list):
        return ["fixtureManifest must be a list"]
    failures: list[str] = []
    if len(manifest) < READBOARD_IMAGE_OCR_CORPUS_MIN_FIXTURES:
        failures.append(
            f"fixtureManifest must include at least {READBOARD_IMAGE_OCR_CORPUS_MIN_FIXTURES} fixtures"
        )
    outcomes: set[str] = set()
    valid_paths: set[str] = set()
    fixture_records: list[tuple[str, str, str]] = []
    for index, fixture in enumerate(manifest):
        label = f"fixtureManifest[{index}]"
        if not isinstance(fixture, dict):
            failures.append(f"{label} must be an object")
            continue
        name = fixture.get("name")
        if not isinstance(name, str) or not name.strip():
            failures.append(f"{label}.name must be non-empty")
        path_value = fixture.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            failures.append(f"{label}.path must be non-empty")
        else:
            failures.extend(validate_repo_relative_path_artifact(root, path_value, fixture, label))
        outcome = normalize_readboard_ocr_fixture_outcome(first_present(fixture, "expectedOutcome", "outcome", "class", "kind"))
        if outcome:
            outcomes.add(outcome)
            if isinstance(path_value, str):
                fixture_records.append((label, outcome, path_value))
        if outcome == "valid":
            if isinstance(path_value, str):
                valid_paths.add(path_value)
            if not positive_number(first_present(fixture, "boardSize", "board_size")):
                failures.append(f"{label}.boardSize must be positive for valid fixtures")
            stone_count = first_present(fixture, "stoneCount", "stone_count")
            if not isinstance(stone_count, (int, float)) or stone_count < 0:
                failures.append(f"{label}.stoneCount must be non-negative for valid fixtures")
            if not isinstance(fixture.get("sha256"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", fixture.get("sha256", "")):
                failures.append(f"{label}.sha256 must provide a hash invariant for valid fixtures")
        elif outcome in {"invalid", "non-board", "truncated"}:
            expected_error = first_present(fixture, "expectedError", "errorKind")
            if not isinstance(expected_error, str) or not expected_error.strip():
                failures.append(f"{label}.expectedError must be non-empty for {outcome} fixtures")
            if first_present(fixture, "boardSize", "board_size") is not None:
                failures.append(f"{label}.boardSize must be absent for {outcome} fixtures")
            if first_present(fixture, "stoneCount", "stone_count") is not None:
                failures.append(f"{label}.stoneCount must be absent for {outcome} fixtures")
        elif outcome:
            failures.append(f"{label}.expectedOutcome is unsupported: {outcome}")
    required_outcomes = {"valid", "invalid", "non-board", "truncated"}
    missing_outcomes = [outcome for outcome in required_outcomes if outcome not in outcomes]
    if missing_outcomes:
        failures.append("fixtureManifest missing outcomes: " + ", ".join(missing_outcomes))
    for label, outcome, path_value in fixture_records:
        if outcome in {"invalid", "non-board", "truncated"} and path_value in valid_paths:
            failures.append(f"{label}.path must not reuse a valid fixture artifact")
    return failures


def normalize_readboard_ocr_fixture_outcome(value: Any) -> str:
    outcome = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "valid-controlled-board": "valid",
        "board": "valid",
        "success": "valid",
        "invalid-image": "invalid",
        "image-decode": "invalid",
        "non-board-image": "non-board",
        "nonboard": "non-board",
        "low-confidence": "non-board",
        "image-low-confidence": "non-board",
        "truncated-corrupt": "truncated",
        "truncated-image": "truncated",
        "corrupt": "truncated",
    }
    return aliases.get(outcome, outcome)


def validate_readboard_ocr_path_base64_equivalence(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["path_base64_equivalence evidence must be an object"]
    failures: list[str] = []
    if evidence.get("pathBase64EquivalenceVerified") is not True:
        failures.append("path_base64_equivalence.pathBase64EquivalenceVerified must be true")
    if evidence.get("sameSnapshot") is not True:
        failures.append("path_base64_equivalence.sameSnapshot must be true")
    if evidence.get("sameBoardSize") is not True:
        failures.append("path_base64_equivalence.sameBoardSize must be true")
    if evidence.get("sameStoneCount") is not True:
        failures.append("path_base64_equivalence.sameStoneCount must be true")
    if evidence.get("sameHash") is not True:
        failures.append("path_base64_equivalence.sameHash must be true")
    return failures


def validate_readboard_truncated_image_rejected(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["truncated_image_rejected evidence must be an object"]
    failures: list[str] = []
    if evidence.get("truncatedImageRejected") is not True:
        failures.append("truncated_image_rejected.truncatedImageRejected must be true")
    if evidence.get("reportedAsSuccess") is not False:
        failures.append("truncated_image_rejected.reportedAsSuccess must be false")
    error_kind = first_present(evidence, "errorKind", "kind")
    if not isinstance(error_kind, str) or not error_kind:
        failures.append("truncated_image_rejected.errorKind must be non-empty")
    message = evidence.get("message")
    if not isinstance(message, str) or not message:
        failures.append("truncated_image_rejected.message must be non-empty")
    return failures


def validate_readboard_ocr_board_size_coverage(check: Any, manifest: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["board_size_coverage evidence must be an object"]
    failures: list[str] = []
    if evidence.get("boardSizeCoverageVerified") is not True:
        failures.append("board_size_coverage.boardSizeCoverageVerified must be true")
    board_sizes = evidence.get("boardSizes")
    if not isinstance(board_sizes, list) or len({item for item in board_sizes if item in {9, 13, 19}}) < 2:
        failures.append("board_size_coverage.boardSizes must include at least two of 9, 13, 19")
    if isinstance(manifest, list):
        manifest_sizes = {
            first_present(item, "boardSize", "board_size")
            for item in manifest
            if isinstance(item, dict)
            and normalize_readboard_ocr_fixture_outcome(first_present(item, "expectedOutcome", "outcome", "class", "kind")) == "valid"
            and first_present(item, "boardSize", "board_size") in {9, 13, 19}
        }
        if board_sizes and not set(board_sizes).issubset(manifest_sizes):
            failures.append("board_size_coverage.boardSizes must be represented by valid fixtureManifest entries")
    return failures


def validate_readboard_ocr_stone_count_coverage(check: Any, manifest: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["stone_count_coverage evidence must be an object"]
    failures: list[str] = []
    if evidence.get("stoneCountCoverageVerified") is not True:
        failures.append("stone_count_coverage.stoneCountCoverageVerified must be true")
    stone_counts = evidence.get("stoneCounts")
    if not isinstance(stone_counts, list) or len({item for item in stone_counts if isinstance(item, int) and item >= 0}) < 2:
        failures.append("stone_count_coverage.stoneCounts must include at least two non-negative counts")
    if isinstance(manifest, list):
        manifest_counts = {
            first_present(item, "stoneCount", "stone_count")
            for item in manifest
            if isinstance(item, dict)
            and normalize_readboard_ocr_fixture_outcome(first_present(item, "expectedOutcome", "outcome", "class", "kind")) == "valid"
            and isinstance(first_present(item, "stoneCount", "stone_count"), int)
        }
        if stone_counts and not set(stone_counts).issubset(manifest_counts):
            failures.append("stone_count_coverage.stoneCounts must be represented by valid fixtureManifest entries")
    return failures


def validate_readboard_ocr_hash_invariants(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["hash_invariants evidence must be an object"]
    failures: list[str] = []
    if evidence.get("hashInvariantsVerified") is not True:
        failures.append("hash_invariants.hashInvariantsVerified must be true")
    for key in ("pathSha256Stable", "base64Sha256Stable", "pathBase64Sha256Equal"):
        if evidence.get(key) is not True:
            failures.append(f"hash_invariants.{key} must be true")
    return failures


def validate_readboard_external_capture_unsupported_contract(check: Any) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["external_capture_unsupported_contract evidence must be an object"]
    failures: list[str] = []
    if evidence.get("externalCaptureUnsupportedContractVerified") is not True:
        failures.append(
            "external_capture_unsupported_contract.externalCaptureUnsupportedContractVerified must be true"
        )
    if evidence.get("externalWindowCaptureCovered") is not False:
        failures.append("external_capture_unsupported_contract.externalWindowCaptureCovered must be false")
    if evidence.get("realClientCaptureCovered") is not False:
        failures.append("external_capture_unsupported_contract.realClientCaptureCovered must be false")
    if evidence.get("reportedAsSuccess") is not False:
        failures.append("external_capture_unsupported_contract.reportedAsSuccess must be false")
    message = evidence.get("message")
    if not isinstance(message, str) or "unsupported" not in message.lower():
        failures.append("external_capture_unsupported_contract.message must mention unsupported")
    return failures


def validate_readboard_ocr_scope_boundaries(check: Any, root_evidence: dict[str, Any]) -> list[str]:
    evidence = check_evidence(check)
    if evidence is None:
        return ["scope_boundaries evidence must be an object"]
    failures: list[str] = []
    for key in READBOARD_IMAGE_OCR_CORPUS_REQUIRED_FALSE_FIELDS:
        if evidence.get(key) is not False:
            failures.append(f"scope_boundaries.{key} must be false")
        if root_evidence.get(key) is not False:
            failures.append(f"{key} must be false")
    return failures


def validate_readboard_image_snapshot_fields(evidence: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    snapshot_id = first_present(evidence, "snapshotId", "snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        failures.append(f"{label}.snapshotId must be non-empty")
    board_size = first_present(evidence, "boardSize", "board_size")
    if not positive_number(board_size):
        failures.append(f"{label}.boardSize must be positive")
    elif board_size not in {9, 13, 19}:
        failures.append(f"{label}.boardSize must be 9, 13, or 19")
    if evidence.get("boardSizeVerified") is not True:
        failures.append(f"{label}.boardSizeVerified must be true")
    if evidence.get("stoneCountVerified") is not True:
        failures.append(f"{label}.stoneCountVerified must be true")
    stone_count = first_present(evidence, "stoneCount", "stone_count")
    if not isinstance(stone_count, (int, float)) or stone_count < 0:
        failures.append(f"{label}.stoneCount must be non-negative")
    if evidence.get("toPlayVerified") is not True:
        failures.append(f"{label}.toPlayVerified must be true")
    to_play = first_present(evidence, "toPlay", "to_play")
    if str(to_play).lower() not in {"black", "white"}:
        failures.append(f"{label}.toPlay must be black or white")
    return failures


def validate_repo_relative_artifact(root: Path, path_value: str, evidence: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        return [f"{label}.imagePath must be repo-relative"]
    artifact = root / path
    if not artifact.is_file():
        return [f"{label}.imagePath does not exist: {path_value}"]
    data = artifact.read_bytes()
    expected_bytes = evidence.get("imageBytes")
    if not isinstance(expected_bytes, int) or expected_bytes <= 0:
        failures.append(f"{label}.imageBytes must be positive")
    elif expected_bytes != len(data):
        failures.append(f"{label}.imageBytes must match artifact size")
    expected_sha = evidence.get("imageSha256")
    actual_sha = hashlib.sha256(data).hexdigest()
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha):
        failures.append(f"{label}.imageSha256 must be a 64-character hex sha256")
    elif expected_sha.lower() != actual_sha:
        failures.append(f"{label}.imageSha256 must match artifact sha256")
    return failures


def validate_repo_relative_path_artifact(root: Path, path_value: str, evidence: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    path_text = path_value.strip()
    path = Path(path_text)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path_text.startswith("~")
        or path_text.startswith("/Users")
        or path_text.startswith("/tmp")
    ):
        return [f"{label}.path must be repo-relative and sanitized"]
    artifact = root / path
    if not artifact.is_file():
        return [f"{label}.path does not exist: {path_value}"]
    data = artifact.read_bytes()
    expected_bytes = evidence.get("sizeBytes")
    if not isinstance(expected_bytes, int) or expected_bytes <= 0:
        failures.append(f"{label}.sizeBytes must be positive")
    elif expected_bytes != len(data):
        failures.append(f"{label}.sizeBytes must match artifact size")
    expected_sha = evidence.get("sha256")
    actual_sha = hashlib.sha256(data).hexdigest()
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha):
        failures.append(f"{label}.sha256 must be a 64-character hex sha256")
    elif expected_sha.lower() != actual_sha:
        failures.append(f"{label}.sha256 must match artifact sha256")
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


def missing_any_required_token(text: str, source_label: str, requirement_label: str, tokens: list[str]) -> list[str]:
    if any(re.search(r"\b" + re.escape(token) + r"\b", text) for token in tokens):
        return []
    return [f"{source_label} missing {requirement_label} ({' or '.join(tokens)})"]


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
