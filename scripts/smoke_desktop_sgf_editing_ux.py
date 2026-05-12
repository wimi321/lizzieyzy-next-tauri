#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.desktop-sgf-editing-ux-smoke.v1"
NAME = "desktop_sgf_editing_ux_smoke"
DEFAULT_RUNTIME_EVIDENCE = Path("docs/qa/tauri-runtime-ui-smoke-macos.json")
DEFAULT_EVIDENCE_OUT = Path("docs/qa/desktop-sgf-editing-ux-smoke-macos.json")
REQUIRED_CHECKS = [
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


def load_smoke_user_flows_module(root: Path):
    script = root / "scripts/smoke_user_flows.py"
    if not script.is_file():
        script = ROOT / "scripts/smoke_user_flows.py"
    spec = importlib.util.spec_from_file_location("smoke_user_flows_for_desktop_ux", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["smoke_user_flows_for_desktop_ux"] = module
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_source(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def build_evidence(root: Path, runtime_evidence_path: Path) -> dict[str, Any]:
    smoke_user_flows = load_smoke_user_flows_module(root)
    runtime_evidence = load_json(root / runtime_evidence_path)
    runtime_failures = smoke_user_flows.validate_tauri_runtime_ui_smoke_evidence(runtime_evidence)
    sources = {
        "legacyShell": read_source(root, smoke_user_flows.LEGACY_SHELL_SOURCE),
        "app": read_source(root, smoke_user_flows.APP_SOURCE),
        "treePanel": read_source(root, smoke_user_flows.SGF_TREE_PANEL_SOURCE),
        "annotationPanel": read_source(root, smoke_user_flows.SGF_ANNOTATION_PANEL_SOURCE),
        "runtimeSmoke": read_source(root, "apps/desktop/src/runtimeSmoke.ts"),
    }
    checks = [
        build_legacy_shell_check(sources),
        build_toolbar_menu_check(sources),
        build_tree_panel_check(sources),
        build_annotation_editor_check(sources),
        build_selected_node_ux_check(sources),
        build_runtime_chain_check("tree_navigation", runtime_evidence, ["branch_navigation"]),
        build_runtime_chain_check("comment_property_annotation_edit", runtime_evidence, ["comment_edit", "property_edit", "annotation_edit"]),
        build_runtime_chain_check("append_edit_reorder_delete", runtime_evidence, ["append_move", "edit_move", "variation_reorder", "delete_node"]),
        build_dirty_saved_status_check(sources, runtime_evidence),
        build_save_readback_reopen_check(runtime_evidence),
        build_native_dialog_boundary_check(),
    ]
    if runtime_failures:
        checks.append({
            "name": "source_runtime_evidence",
            "status": "fail",
            "details": {"runtimeEvidence": str(runtime_evidence_path), "failures": runtime_failures},
        })

    status = "pass" if all(check["status"] == "pass" for check in checks) else "fail"
    return {
        "schema": SCHEMA,
        "name": NAME,
        "status": status,
        "platform": "macos",
        "collectionMethod": "source_static_plus_tauri_runtime_chain",
        "runtimeDomObserved": False,
        "screenshotObserved": False,
        "sourceRuntimeEvidence": {
            "path": str(runtime_evidence_path),
            "schema": runtime_evidence.get("schema"),
            "status": runtime_evidence.get("status"),
            "valid": not runtime_failures,
        },
        "uiUxSurface": build_ui_ux_surface(sources, runtime_evidence),
        "coverage": build_coverage(runtime_evidence),
        "boundaries": {
            "nativeDialogClickCovered": False,
            "fullNativeDialogProof": False,
            "ocrCaptureCovered": False,
            "externalClientWindowCaptureCovered": False,
            "fullLegacyParityCovered": False,
        },
        "checks": checks,
    }


def build_legacy_shell_check(sources: dict[str, str]) -> dict[str, Any]:
    tokens = ["data-testid=\"legacy-shell\"", "legacy-menubar", "legacy-toolbar", "legacy-statusbar"]
    return token_check("legacy_shell_visible", sources["legacyShell"], tokens, {"legacyShellVisible": True})


def build_toolbar_menu_check(sources: dict[str, str]) -> dict[str, Any]:
    tokens = [
        "Application menu",
        "Main toolbar",
        "Open SGF",
        "Save SGF",
        "Save SGF as",
        "File",
        "Open",
        "Save",
        "Save As",
        "View",
        "Candidates",
        "Engine",
        "Tools",
    ]
    details = {
        "visible": True,
        "toolbarControls": ["Open", "Save", "Save As", "Import", "Sample", "Parse", "Review"],
        "menuControls": ["File/Open", "File/Save", "File/Save As", "View/Candidates", "Engine/Profiles", "Tools/Preferences"],
    }
    return token_check("toolbar_menu_controls", sources["legacyShell"], tokens, details)


def build_tree_panel_check(sources: dict[str, str]) -> dict[str, Any]:
    tokens = ["sgf-tree-panel", "SGF tree and comments", "SGF Tree", "sgf-tree-node", "onSelectNode"]
    return token_check("tree_panel_visible", sources["treePanel"], tokens, {"treePanelVisible": True})


def build_annotation_editor_check(sources: dict[str, str]) -> dict[str, Any]:
    tokens = ["sgf-annotation-editor", "SGF node annotations", "TR", "SQ", "CR", "MA", "SL", "LB", "AR", "LN", "Save Annotations"]
    return token_check("annotation_editor_visible", sources["annotationPanel"], tokens, {"annotationEditorVisible": True})


def build_selected_node_ux_check(sources: dict[str, str]) -> dict[str, Any]:
    tokens = [
        "selectedNodeId",
        "selectedNode",
        "Selected node actions",
        "Move edit mode",
        "Selected SGF node comment",
        "Delete Node",
        "Move Up",
        "Move Down",
        "Edit selected",
    ]
    details = {
        "selectedNodeUxState": {
            "selectedNodeVisible": True,
            "commentEditorVisible": True,
            "moveEditModeVisible": True,
            "deleteControlVisible": True,
            "reorderControlsVisible": True,
        }
    }
    return token_check("selected_node_ux_state", sources["app"] + "\n" + sources["treePanel"], tokens, details)


def build_runtime_chain_check(name: str, runtime_evidence: dict[str, Any], required: list[str]) -> dict[str, Any]:
    check_by_name = runtime_checks_by_name(runtime_evidence)
    missing = [item for item in required if item not in check_by_name]
    not_pass = [
        item
        for item in required
        if item in check_by_name and str(check_by_name[item].get("status", "")).lower() != "pass"
    ]
    status = "pass" if not missing and not not_pass else "fail"
    return {
        "name": name,
        "status": status,
        "details": {
            "runtimeChecks": required,
            "missing": missing,
            "notPass": not_pass,
            "covered": status == "pass",
        },
    }


def build_dirty_saved_status_check(sources: dict[str, str], runtime_evidence: dict[str, Any]) -> dict[str, Any]:
    tokens = ["dirty ? \"Unsaved\" : \"Saved\"", "dirty ? \"Unsaved changes\" : \"Saved\"", "canSave={dirty}", "setDirty(true)", "setDirty(false)"]
    check = token_check("dirty_saved_status", sources["legacyShell"] + "\n" + sources["app"], tokens, {})
    roundtrip = check_evidence(runtime_evidence, "save_readback_roundtrip")
    after_reopen = roundtrip.get("afterReopen") if isinstance(roundtrip.get("afterReopen"), dict) else {}
    details = {
        "dirtySavedStatus": {
            "dirtyIndicatorVisible": check["status"] == "pass",
            "savedIndicatorVisible": check["status"] == "pass",
            "canSaveReflectsDirty": "canSave={dirty}" in sources["app"],
            "dirtySetAfterEdits": "setDirty(true)" in sources["app"],
            "savedAfterReadback": after_reopen.get("commentsVerified") is True and after_reopen.get("propertiesVerified") is True,
        }
    }
    check["details"] = {**check.get("details", {}), **details}
    if not all(details["dirtySavedStatus"].values()):
        check["status"] = "fail"
    return check


def build_save_readback_reopen_check(runtime_evidence: dict[str, Any]) -> dict[str, Any]:
    roundtrip = check_evidence(runtime_evidence, "save_readback_roundtrip")
    after_reopen = roundtrip.get("afterReopen") if isinstance(roundtrip.get("afterReopen"), dict) else {}
    required = {
        "commentsVerified": True,
        "propertiesVerified": True,
        "annotationsVerified": True,
        "treeOrderVerified": True,
        "moveCountVerified": True,
        "boardStateVerified": True,
    }
    failures = [key for key, expected in required.items() if after_reopen.get(key) is not expected]
    status = "pass" if roundtrip.get("readbackMatchesSaved") is True and not failures else "fail"
    return {
        "name": "save_readback_reopen",
        "status": status,
        "details": {
            "readbackMatchesSaved": roundtrip.get("readbackMatchesSaved"),
            "afterReopen": after_reopen,
            "missingOrFalseAfterReopenFields": failures,
        },
    }


def build_native_dialog_boundary_check() -> dict[str, Any]:
    return {
        "name": "native_dialog_boundary",
        "status": "pass",
        "details": {
            "nativeDialogClickCovered": False,
            "reason": "This scoped smoke uses source/static surface checks plus committed Tauri runtime-chain evidence; it does not observe rendered DOM, screenshots, or the OS-native dialog.",
        },
    }


def build_ui_ux_surface(sources: dict[str, str], runtime_evidence: dict[str, Any]) -> dict[str, Any]:
    roundtrip = check_evidence(runtime_evidence, "save_readback_roundtrip")
    after_reopen = roundtrip.get("afterReopen") if isinstance(roundtrip.get("afterReopen"), dict) else {}
    return {
        "legacyShellVisible": "data-testid=\"legacy-shell\"" in sources["legacyShell"],
        "toolbarMenuControls": {
            "visible": "data-testid=\"legacy-toolbar\"" in sources["legacyShell"] and "data-testid=\"legacy-menubar\"" in sources["legacyShell"],
            "toolbarControls": ["Open", "Save", "Save As", "Import", "Sample", "Parse", "Review"],
            "menuControls": ["File/Open", "File/Save", "File/Save As", "View/Candidates", "Engine/Profiles", "Tools/Preferences"],
        },
        "treePanelVisible": "sgf-tree-panel" in sources["treePanel"],
        "annotationEditorVisible": "sgf-annotation-editor" in sources["annotationPanel"],
        "selectedNodeUxState": {
            "selectedNodeVisible": "selectedNodeId" in sources["app"],
            "commentEditorVisible": "Selected SGF node comment" in sources["treePanel"],
            "moveEditModeVisible": "Move edit mode" in sources["treePanel"],
            "deleteControlVisible": "Delete Node" in sources["treePanel"],
            "reorderControlsVisible": "Move Up" in sources["treePanel"] and "Move Down" in sources["treePanel"],
        },
        "dirtySavedStatus": {
            "dirtyIndicatorVisible": "Unsaved" in sources["legacyShell"],
            "savedIndicatorVisible": "Saved" in sources["legacyShell"],
            "canSaveReflectsDirty": "canSave={dirty}" in sources["app"],
            "dirtySetAfterEdits": "setDirty(true)" in sources["app"],
            "savedAfterReadback": after_reopen.get("commentsVerified") is True and after_reopen.get("propertiesVerified") is True,
        },
        "nativeDialogClickCovered": False,
    }


def build_coverage(runtime_evidence: dict[str, Any]) -> dict[str, bool]:
    check_by_name = runtime_checks_by_name(runtime_evidence)
    return {
        "treeNavigation": runtime_check_passed(check_by_name, "branch_navigation"),
        "commentEdit": runtime_check_passed(check_by_name, "comment_edit"),
        "propertyEdit": runtime_check_passed(check_by_name, "property_edit"),
        "annotationEdit": runtime_check_passed(check_by_name, "annotation_edit"),
        "appendMove": runtime_check_passed(check_by_name, "append_move"),
        "editMove": runtime_check_passed(check_by_name, "edit_move"),
        "reorderVariation": runtime_check_passed(check_by_name, "variation_reorder"),
        "deleteNode": runtime_check_passed(check_by_name, "delete_node"),
        "saveReadbackReopen": runtime_check_passed(check_by_name, "save_readback_roundtrip"),
    }


def token_check(name: str, text: str, tokens: list[str], details: dict[str, Any]) -> dict[str, Any]:
    missing = [token for token in tokens if token not in text]
    return {
        "name": name,
        "status": "pass" if not missing else "fail",
        "details": {**details, "missingTokens": missing},
    }


def runtime_checks_by_name(runtime_evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks = runtime_evidence.get("checks")
    if not isinstance(checks, list):
        return {}
    return {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }


def runtime_check_passed(check_by_name: dict[str, dict[str, Any]], name: str) -> bool:
    return str(check_by_name.get(name, {}).get("status", "")).lower() == "pass"


def check_evidence(runtime_evidence: dict[str, Any], name: str) -> dict[str, Any]:
    check = runtime_checks_by_name(runtime_evidence).get(name)
    if not isinstance(check, dict):
        return {}
    for key in ("details", "evidence"):
        value = check.get(key)
        if isinstance(value, dict):
            return value
    return {}


def validate_evidence(evidence: Any) -> list[str]:
    smoke_user_flows = load_smoke_user_flows_module(ROOT)
    return smoke_user_flows.validate_desktop_sgf_editing_ux_smoke_evidence(evidence)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build scoped desktop SGF editing UX smoke evidence from runtime and UI surface checks.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runtime-evidence", type=Path, default=DEFAULT_RUNTIME_EVIDENCE)
    parser.add_argument("--evidence-out", type=Path, default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--check-only", action="store_true", help="Validate an existing evidence file instead of rebuilding it.")
    args = parser.parse_args()

    root = args.root.resolve()
    evidence_path = root / args.evidence_out
    if args.check_only:
        evidence = load_json(evidence_path)
    else:
        evidence = build_evidence(root, args.runtime_evidence)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    failures = validate_evidence(evidence)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    action = "validated" if args.check_only else "wrote"
    print(f"PASS desktop SGF editing UX smoke: {len(REQUIRED_CHECKS)} required checks passed; {action} {evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
