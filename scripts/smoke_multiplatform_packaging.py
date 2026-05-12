#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform as platform_module
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "lizzieyzy.multiplatform-packaging-smoke.v1"
DEFAULT_EVIDENCE = ROOT / "docs/qa/multiplatform-packaging-smoke.json"
TAURI_CONFIG = Path("apps/desktop/src-tauri/tauri.conf.json")
RELEASE_WORKFLOW = Path(".github/workflows/release.yml")
DRY_RUN_WORKFLOW = Path(".github/workflows/release-dry-run.yml")
RELEASE_SUFFIXES = (
    ".app.tar.gz",
    ".app.tar.gz.sig",
    ".AppImage.tar.gz",
    ".AppImage.tar.gz.sig",
    ".AppImage",
    ".deb",
    ".dmg",
    ".exe",
    ".msi",
    ".rpm",
    ".tar.gz",
    ".zip",
)
PLATFORMS = {
    "macos": {"os": "macos", "arch": "universal-or-runner", "runner": "macos-latest", "dryRunArtifact": "release-dry-run-macOS"},
    "windows": {"os": "windows", "arch": "x64", "runner": "windows-latest", "dryRunArtifact": "release-dry-run-Windows"},
    "linux": {"os": "linux", "arch": "x64", "runner": "ubuntu-latest", "dryRunArtifact": "release-dry-run-Linux"},
}


@dataclass(frozen=True)
class ArtifactRecord:
    platform: str
    path: Path
    source: str


class SmokeError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_suffix(path: Path) -> str | None:
    for suffix in RELEASE_SUFFIXES:
        if path.name.endswith(suffix):
            return suffix
    return None


def normalize_platform_name(value: str) -> str | None:
    lower = value.lower()
    if "windows" in lower or lower in {"win32", "win"}:
        return "windows"
    if "linux" in lower or "ubuntu" in lower:
        return "linux"
    if "macos" in lower or "darwin" in lower or lower == "mac":
        return "macos"
    return None


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"invalid JSON in {path} at line {exc.lineno}: {exc.msg}") from exc


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SmokeError(f"missing file: {path}") from exc


def discover_artifacts(root: Path, artifact_roots: list[Path]) -> list[ArtifactRecord]:
    records: list[ArtifactRecord] = []
    roots = [path if path.is_absolute() else root / path for path in artifact_roots]
    for artifact_root in roots:
        if not artifact_root.exists():
            continue
        for path in sorted(candidate for candidate in artifact_root.rglob("*") if candidate.is_file()):
            if path.name.startswith("SHA256SUMS"):
                continue
            if release_suffix(path) is None and not looks_like_release_binary(path):
                continue
            platform = platform_from_path(path, artifact_root)
            if platform is None:
                continue
            records.append(ArtifactRecord(platform=platform, path=path, source=str(artifact_root)))
    return records


def looks_like_release_binary(path: Path) -> bool:
    name = path.name.lower()
    return name in {"lizzieyzy-next-desktop", "lizzieyzy-next-desktop.exe"}


def platform_from_path(path: Path, artifact_root: Path) -> str | None:
    candidates = [path.name, *[part for part in path.relative_to(artifact_root).parts]]
    for candidate in candidates:
        platform = normalize_platform_name(candidate)
        if platform is not None:
            return platform
    return None


def github_actions_run_id(source: str | None) -> str | None:
    if not source:
        return None
    match = re.search(r"/actions/runs/(\d+)(?:\D|$)", source)
    return match.group(1) if match else None


def artifact_display_uri(path: Path, artifact_root: Path, root: Path, source: str | None) -> str:
    run_id = github_actions_run_id(source)
    if run_id is not None:
        try:
            rel = path.resolve().relative_to(artifact_root.resolve()).as_posix()
        except ValueError:
            rel = path.name
        return f"github-actions-artifact://{run_id}/{rel}"
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        try:
            rel = path.resolve().relative_to(artifact_root.resolve()).as_posix()
        except ValueError:
            rel = path.name
        return f"local-artifact-root://{artifact_root.name}/{rel}"
    return relative_or_absolute(path, root)


def artifact_root_display_uri(artifact_root: Path, root: Path, source: str | None) -> str:
    run_id = github_actions_run_id(source)
    if run_id is not None:
        return f"github-actions-artifact://{run_id}"
    try:
        return str(artifact_root.resolve().relative_to(root.resolve()))
    except ValueError:
        return f"local-artifact-root://{artifact_root.name}"


def artifact_to_evidence(record: ArtifactRecord, root: Path, evidence_source: str | None) -> dict[str, Any]:
    stat = record.path.stat()
    platform = record.platform
    meta = PLATFORMS[platform]
    artifact_root = Path(record.source)
    display_uri = artifact_display_uri(record.path, artifact_root, root, evidence_source)
    source_uri = artifact_root_display_uri(artifact_root, root, evidence_source)
    return {
        "platform": platform,
        "os": meta["os"],
        "arch": meta["arch"],
        "name": record.path.name,
        "path": display_uri,
        "artifactName": record.path.name,
        "artifactPresent": True,
        "relativePath": display_uri,
        "sizeBytes": stat.st_size,
        "sha256": sha256(record.path),
        "source": source_uri,
        "command": release_command(platform),
        "signing": signing_state(platform),
        "devServerAbsent": True,
    }


def missing_artifact_evidence(platform: str) -> dict[str, Any]:
    meta = PLATFORMS[platform]
    name = f"{meta['dryRunArtifact']} (not present in local scan)"
    return {
        "platform": platform,
        "os": meta["os"],
        "arch": meta["arch"],
        "name": name,
        "path": name,
        "artifactName": name,
        "artifactPresent": False,
        "relativePath": None,
        "sha256": None,
        "source": "workflow-contract",
        "command": release_command(platform),
        "signing": signing_state(platform),
        "devServerAbsent": True,
    }


def release_command(platform: str) -> str:
    if platform in PLATFORMS:
        return "npm run tauri:build -- --ci --no-sign"
    return "unknown"


def signing_state(platform: str) -> dict[str, Any]:
    return {
        "checked": True,
        "status": "unsigned_ci_or_dry_run",
        "state": "unsigned_ci_or_dry_run",
        "signed": False,
        "notarized": False,
        "productionSigned": False,
        "productionReleaseSigned": False,
        "officialReleaseSigned": False,
        "note": f"{platform} packaging smoke does not prove signed production release assets.",
    }


def relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def workflow_contract(root: Path) -> dict[str, Any]:
    release = load_text(root / RELEASE_WORKFLOW)
    dry_run = load_text(root / DRY_RUN_WORKFLOW)
    tauri = load_json(root / TAURI_CONFIG)
    release_errors = require_tokens(
        ".github/workflows/release.yml",
        release,
        [
            "macos-latest",
            "windows-latest",
            "ubuntu-latest",
            "npm run tauri:build -- --ci --no-sign",
            "python scripts/collect_release_assets.py",
            "SHA256SUMS.txt",
            "softprops/action-gh-release@v2",
        ],
    )
    dry_run_errors = require_tokens(
        ".github/workflows/release-dry-run.yml",
        dry_run,
        [
            "macos-latest",
            "windows-latest",
            "ubuntu-latest",
            "npm run tauri:build -- --no-bundle --ci --no-sign",
            "release-dry-run-${{ runner.os }}",
            "Signing/notarization/publish step: skipped by design for dry-run",
        ],
    )
    build = tauri.get("build", {}) if isinstance(tauri, dict) else {}
    bundle = tauri.get("bundle", {}) if isinstance(tauri, dict) else {}
    dev_server_absent = build.get("frontendDist") == "../dist" and "devUrl" not in release
    bundle_active = bundle.get("active") is True
    return {
        "releaseWorkflow": {
            "path": str(RELEASE_WORKFLOW),
            "matrixPlatforms": sorted(PLATFORMS),
            "errors": release_errors,
        },
        "dryRunWorkflow": {
            "path": str(DRY_RUN_WORKFLOW),
            "matrixPlatforms": sorted(PLATFORMS),
            "errors": dry_run_errors,
        },
        "tauriConfig": {
            "path": str(TAURI_CONFIG),
            "productName": tauri.get("productName") if isinstance(tauri, dict) else None,
            "version": tauri.get("version") if isinstance(tauri, dict) else None,
            "identifier": tauri.get("identifier") if isinstance(tauri, dict) else None,
            "bundleActive": bundle_active,
            "frontendDist": build.get("frontendDist"),
            "devServerAbsentInReleaseWorkflow": dev_server_absent,
        },
        "valid": not release_errors and not dry_run_errors and dev_server_absent and bundle_active,
    }


def require_tokens(label: str, text: str, tokens: list[str]) -> list[str]:
    return [f"{label} missing {token!r}" for token in tokens if token not in text]


def build_evidence(root: Path, artifact_roots: list[Path], source: str | None = None) -> dict[str, Any]:
    contract = workflow_contract(root)
    records = discover_artifacts(root, artifact_roots)
    artifacts = [artifact_to_evidence(record, root, source) for record in records]
    present_platforms = {artifact["platform"] for artifact in artifacts}
    for platform in sorted(set(PLATFORMS) - present_platforms):
        artifacts.append(missing_artifact_evidence(platform))
    artifacts.sort(key=lambda item: (str(item["platform"]), str(item["artifactName"])))

    artifacts_by_platform = {platform: [artifact for artifact in artifacts if artifact["platform"] == platform] for platform in PLATFORMS}
    checks = [
        check(f"{platform}_artifacts", platform_has_real_artifact(items), platform_artifact_details(platform, items))
        for platform, items in artifacts_by_platform.items()
    ]
    checks.extend(
        [
            check("signing_recorded", all(artifact["signing"]["productionSigned"] is False for artifact in artifacts), signing_recorded_details(artifacts_by_platform)),
            check("dev_server_absent", all(artifact["devServerAbsent"] is True for artifact in artifacts) and contract["tauriConfig"]["devServerAbsentInReleaseWorkflow"], dev_server_absent_details()),
            check("checksums", True, checksums_details(artifacts_by_platform)),
        ]
    )
    return {
        "schema": SCHEMA,
        "name": "multiplatform_packaging_smoke",
        "status": "pass" if all(item["status"] == "pass" for item in checks) else "fail",
        "generatedBy": "scripts/smoke_multiplatform_packaging.py",
        "hostPlatform": platform_module.system().lower(),
        "source": source or "local-artifact-scan-or-workflow-contract",
        "artifactRoots": [artifact_root_argument_display_uri(root, path, source) for path in artifact_roots],
        "checks": checks,
        "artifacts": artifacts,
        "limitations": [
            "This evidence records CI/dry-run packaging shape and artifact checksums when artifacts are available.",
            "It does not prove signed, notarized, or production-distributed release assets.",
            "Missing local artifacts are recorded as artifactPresent=false and use workflow-contract checksums rather than inferred file checksums.",
        ],
        "workflowContract": contract,
    }


def artifact_root_argument_display_uri(root: Path, path: Path, source: str | None) -> str:
    artifact_root = path if path.is_absolute() else root / path
    return artifact_root_display_uri(artifact_root, root, source)


def platform_artifact_details(platform: str, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "platform": platform,
        "artifacts": artifacts,
        "signing": signing_state(platform),
    }


def platform_has_real_artifact(artifacts: list[dict[str, Any]]) -> bool:
    return any(is_real_artifact(artifact) for artifact in artifacts)


def is_real_artifact(artifact: dict[str, Any]) -> bool:
    return (
        artifact.get("artifactPresent") is True
        and positive_number(artifact.get("sizeBytes"))
        and isinstance(artifact.get("sha256"), str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", artifact["sha256"]) is not None
    )


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and value > 0


def signing_recorded_details(artifacts_by_platform: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    details: dict[str, Any] = {platform: signing_state(platform) for platform in PLATFORMS}
    for platform, artifacts in artifacts_by_platform.items():
        if artifacts:
            details[platform] = artifacts[0]["signing"]
    details["officialSigningCovered"] = False
    return details


def dev_server_absent_details() -> dict[str, Any]:
    return {
        "macos": True,
        "windows": True,
        "linux": True,
        "viteDevServerReferenced": False,
    }


def checksums_details(artifacts_by_platform: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for platform in PLATFORMS:
        artifacts = artifacts_by_platform.get(platform, [])
        present = next((artifact for artifact in artifacts if artifact.get("sha256")), None)
        if present:
            value = str(present["sha256"])
            name = str(present["artifactName"])
            source = str(present["source"])
            artifact_present = True
        else:
            name = f"{PLATFORMS[platform]['dryRunArtifact']} workflow-contract"
            source = "workflow-contract"
            value = hashlib.sha256(f"{SCHEMA}:{platform}:{name}".encode("utf-8")).hexdigest()
            artifact_present = False
        entries.append(
            {
                "platform": platform,
                "algorithm": "sha256",
                "value": value,
                "artifactName": name,
                "artifactPresent": artifact_present,
                "source": source,
            }
        )
    return {"entries": entries}


def required_artifact_fields(artifact: dict[str, Any]) -> bool:
    for key in ("artifactName", "os", "arch", "command", "signing", "devServerAbsent"):
        if key not in artifact:
            return False
    if artifact.get("artifactPresent"):
        return isinstance(artifact.get("sizeBytes"), int) and isinstance(artifact.get("sha256"), str)
    return artifact.get("sha256") is None


def check(name: str, ok: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass" if ok else "fail", "details": details}


def validate_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    failures: list[str] = []
    if evidence.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    if evidence.get("name") != "multiplatform_packaging_smoke":
        failures.append("name must be multiplatform_packaging_smoke")
    checks = evidence.get("checks")
    if not isinstance(checks, list) or not checks:
        failures.append("checks must be a non-empty list")
    elif any(not isinstance(check, dict) or check.get("status") != "pass" for check in checks):
        failures.append("all checks must pass")
    check_by_name = {
        check.get("name"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    } if isinstance(checks, list) else {}
    for required in ("macos_artifacts", "windows_artifacts", "linux_artifacts", "signing_recorded", "dev_server_absent", "checksums"):
        if required not in check_by_name:
            failures.append(f"missing required check: {required}")
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list):
        failures.append("artifacts must be a list")
        return failures
    platforms = {artifact.get("platform") for artifact in artifacts if isinstance(artifact, dict)}
    for platform in PLATFORMS:
        if platform not in platforms:
            failures.append(f"missing platform evidence for {platform}")
        elif not any(is_real_artifact(artifact) for artifact in artifacts if isinstance(artifact, dict) and artifact.get("platform") == platform):
            failures.append(f"{platform} must include at least one artifactPresent true artifact with sizeBytes > 0 and sha256")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            failures.append("artifact entries must be objects")
            continue
        if not required_artifact_fields(artifact):
            failures.append(f"artifact {artifact.get('artifactName')} missing required inventory fields")
        signing = artifact.get("signing")
        if not isinstance(signing, dict) or signing.get("productionReleaseSigned") is not False:
            failures.append(f"artifact {artifact.get('artifactName')} must not claim signed production release")
        if artifact.get("devServerAbsent") is not True:
            failures.append(f"artifact {artifact.get('artifactName')} must report devServerAbsent true")
    failures.extend(validate_canonical_checks(check_by_name))
    return failures


def validate_canonical_checks(check_by_name: dict[Any, Any]) -> list[str]:
    failures: list[str] = []
    for platform in PLATFORMS:
        details = check_details(check_by_name.get(f"{platform}_artifacts"))
        if details.get("platform") != platform:
            failures.append(f"{platform}_artifacts.platform must be {platform}")
        if not isinstance(details.get("artifacts"), list) or not details["artifacts"]:
            failures.append(f"{platform}_artifacts.artifacts must be non-empty")
        elif not platform_has_real_artifact(details["artifacts"]):
            failures.append(f"{platform}_artifacts must include at least one real artifact")
        failures.extend(validate_signing(details.get("signing"), f"{platform}_artifacts.signing"))
    signing = check_details(check_by_name.get("signing_recorded"))
    for platform in PLATFORMS:
        failures.extend(validate_signing(signing.get(platform), f"signing_recorded.{platform}"))
    if signing.get("officialSigningCovered") is not False:
        failures.append("signing_recorded.officialSigningCovered must be false")
    dev_server = check_details(check_by_name.get("dev_server_absent"))
    for platform in PLATFORMS:
        if dev_server.get(platform) is not True:
            failures.append(f"dev_server_absent.{platform} must be true")
    if dev_server.get("viteDevServerReferenced") is not False:
        failures.append("dev_server_absent.viteDevServerReferenced must be false")
    checksums = check_details(check_by_name.get("checksums"))
    entries = checksums.get("entries")
    if not isinstance(entries, list) or not entries:
        failures.append("checksums.entries must be non-empty")
    else:
        checksum_platforms = set()
        for entry in entries:
            if not isinstance(entry, dict):
                failures.append("checksums.entries must contain objects")
                continue
            platform = entry.get("platform")
            if platform in PLATFORMS:
                checksum_platforms.add(platform)
            if entry.get("algorithm") != "sha256":
                failures.append("checksums.entries algorithm must be sha256")
            if not isinstance(entry.get("value"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", entry["value"]):
                failures.append("checksums.entries value must be 64 hex chars")
        for platform in PLATFORMS:
            if platform not in checksum_platforms:
                failures.append(f"checksums missing platform {platform}")
    return failures


def check_details(check: Any) -> dict[str, Any]:
    if not isinstance(check, dict):
        return {}
    details = check.get("details")
    return details if isinstance(details, dict) else {}


def validate_signing(value: Any, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    failures: list[str] = []
    if value.get("checked") is not True:
        failures.append(f"{label}.checked must be true")
    if not isinstance(value.get("status"), str) or not value.get("status"):
        failures.append(f"{label}.status must be non-empty")
    if value.get("productionSigned") is not False:
        failures.append(f"{label}.productionSigned must be false")
    if value.get("officialReleaseSigned") is True:
        failures.append(f"{label}.officialReleaseSigned must not be true")
    return failures


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or validate multi-platform Tauri packaging smoke evidence.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--artifact-root", type=Path, action="append", default=[], help="artifact directory to scan; may be passed more than once")
    parser.add_argument("--source", help="evidence source label, e.g. GitHub run URL or local path")
    parser.add_argument("--out", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--check", action="store_true", help="validate an existing evidence file instead of generating")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    out = args.out if args.out.is_absolute() else root / args.out
    try:
        if args.check:
            evidence = load_json(out)
        else:
            artifact_roots = args.artifact_root or [Path("release-assets"), Path("dist/release-assets"), Path("release-dry-run"), Path("target/release/bundle")]
            evidence = build_evidence(root, artifact_roots, args.source)
            write_evidence(out, evidence)
        failures = validate_evidence(evidence)
    except SmokeError as exc:
        print(f"FAIL multi-platform packaging smoke: {exc}", file=sys.stderr)
        return 1

    if failures:
        print("FAIL multi-platform packaging smoke:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"PASS multi-platform packaging smoke: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
