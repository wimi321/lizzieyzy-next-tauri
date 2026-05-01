#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]

WORKSPACE_MEMBERS = [
    "apps/desktop/src-tauri",
    "crates/app-model",
    "crates/go-core",
    "crates/sgf",
    "crates/katago-protocol",
    "crates/analysis-core",
    "crates/engine-manager",
    "crates/storage",
]

REQUIRED_PATHS = {
    "workspace": [
        "Cargo.toml",
    ],
    "desktop_frontend": [
        "apps/desktop/package.json",
        "apps/desktop/tsconfig.json",
        "apps/desktop/vite.config.ts",
        "apps/desktop/index.html",
        "apps/desktop/src/App.tsx",
        "apps/desktop/src/main.tsx",
    ],
    "desktop_tauri": [
        "apps/desktop/src-tauri/Cargo.toml",
        "apps/desktop/src-tauri/build.rs",
        "apps/desktop/src-tauri/tauri.conf.json",
        "apps/desktop/src-tauri/capabilities/default.json",
        "apps/desktop/src-tauri/src/lib.rs",
        "apps/desktop/src-tauri/src/main.rs",
    ],
    "rust_crates": [
        "crates/app-model/Cargo.toml",
        "crates/app-model/src/lib.rs",
        "crates/go-core/Cargo.toml",
        "crates/go-core/src/lib.rs",
        "crates/sgf/Cargo.toml",
        "crates/sgf/src/lib.rs",
        "crates/katago-protocol/Cargo.toml",
        "crates/katago-protocol/src/lib.rs",
        "crates/analysis-core/Cargo.toml",
        "crates/analysis-core/src/lib.rs",
        "crates/engine-manager/Cargo.toml",
        "crates/engine-manager/src/lib.rs",
        "crates/storage/Cargo.toml",
        "crates/storage/src/lib.rs",
    ],
    "docs_and_tests": [
        "docs/ARCHITECTURE_NEXT.md",
        "docs/MIGRATION_PLAN.md",
        "docs/AGENT_EXECUTION_SUMMARY.md",
        "tests/golden/basic_19x19.sgf",
    ],
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class Validator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.results: list[CheckResult] = []

    def pass_(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, True, detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append(CheckResult(name, False, detail))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def load_json(self, rel: str) -> Any | None:
        try:
            return json.loads(self.path(rel).read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.fail(f"json:{rel}", "file is missing")
        except json.JSONDecodeError as exc:
            self.fail(f"json:{rel}", f"invalid JSON at line {exc.lineno}: {exc.msg}")
        return None

    def load_toml(self, rel: str) -> Any | None:
        try:
            text = self.path(rel).read_text(encoding="utf-8")
            if tomllib is not None:
                return tomllib.loads(text)
            return parse_minimal_toml(text)
        except FileNotFoundError:
            self.fail(f"toml:{rel}", "file is missing")
        except ValueError as exc:
            self.fail(f"toml:{rel}", f"invalid TOML: {exc}")
        return None

    def check_required_paths(self) -> None:
        for group, paths in REQUIRED_PATHS.items():
            missing = [rel for rel in paths if not self.path(rel).is_file()]
            if missing:
                self.fail(group, "missing files: " + ", ".join(missing))
            else:
                self.pass_(group, f"{len(paths)} required files present")

    def check_workspace(self) -> None:
        cargo = self.load_toml("Cargo.toml")
        if not cargo:
            return
        members = cargo.get("workspace", {}).get("members", [])
        missing_members = [member for member in WORKSPACE_MEMBERS if member not in members]
        extra_missing_manifests = [
            f"{member}/Cargo.toml"
            for member in members
            if isinstance(member, str) and not self.path(f"{member}/Cargo.toml").is_file()
        ]
        rust_version = cargo.get("workspace", {}).get("package", {}).get("rust-version")
        if missing_members or extra_missing_manifests:
            detail = []
            if missing_members:
                detail.append("workspace members missing: " + ", ".join(missing_members))
            if extra_missing_manifests:
                detail.append("member manifests missing: " + ", ".join(extra_missing_manifests))
            self.fail("workspace", "; ".join(detail))
        elif not rust_version:
            self.fail("workspace", "workspace.package.rust-version is required")
        else:
            self.pass_("workspace", f"{len(members)} members declared; rust-version {rust_version}")

    def check_crates(self) -> None:
        crate_errors: list[str] = []
        for member in WORKSPACE_MEMBERS[1:]:
            manifest = self.load_toml(f"{member}/Cargo.toml")
            lib_rs = self.path(f"{member}/src/lib.rs")
            if not manifest:
                continue
            package = manifest.get("package", {})
            if package.get("edition", {}).get("workspace") is not True:
                crate_errors.append(f"{member}: package.edition must inherit workspace")
            if not package.get("name"):
                crate_errors.append(f"{member}: package.name is required")
            if not lib_rs.is_file() or not lib_rs.read_text(encoding="utf-8").strip():
                crate_errors.append(f"{member}: src/lib.rs must exist and be non-empty")
        if crate_errors:
            self.fail("rust_crates", "; ".join(crate_errors))
        else:
            self.pass_("rust_crates", f"{len(WORKSPACE_MEMBERS) - 1} Rust library crates validated")

    def check_tauri(self) -> None:
        conf = self.load_json("apps/desktop/src-tauri/tauri.conf.json")
        caps = self.load_json("apps/desktop/src-tauri/capabilities/default.json")
        manifest = self.load_toml("apps/desktop/src-tauri/Cargo.toml")
        if not conf or not caps or not manifest:
            return
        errors: list[str] = []
        build = conf.get("build", {})
        if conf.get("identifier") != "org.lizzieyzy.next":
            errors.append("identifier must be org.lizzieyzy.next")
        if not str(build.get("devUrl", "")).startswith("http://127.0.0.1"):
            errors.append("build.devUrl must use 127.0.0.1")
        if build.get("beforeDevCommand") != "npm run dev":
            errors.append("build.beforeDevCommand must be npm run dev")
        if build.get("beforeBuildCommand") != "npm run build":
            errors.append("build.beforeBuildCommand must be npm run build")
        if build.get("frontendDist") != "../dist":
            errors.append("build.frontendDist must be ../dist")
        permissions = set(caps.get("permissions", []))
        if not {"core:default", "opener:default"}.issubset(permissions):
            errors.append("default capability must include core:default and opener:default")
        deps = manifest.get("dependencies", {})
        for dep in ["tauri", "tauri-plugin-opener", "sgf", "analysis-core", "engine-manager"]:
            if dep not in deps:
                errors.append(f"desktop Cargo.toml missing dependency {dep}")
        if errors:
            self.fail("desktop_tauri", "; ".join(errors))
        else:
            self.pass_("desktop_tauri", "Tauri 2 config, capabilities, and gateway dependencies validated")

    def check_frontend_package(self) -> None:
        package = self.load_json("apps/desktop/package.json")
        if not package:
            return
        scripts = package.get("scripts", {})
        deps = package.get("dependencies", {})
        dev_deps = package.get("devDependencies", {})
        errors: list[str] = []
        for script in ["dev", "build", "tauri:dev", "tauri:build"]:
            if script not in scripts:
                errors.append(f"scripts.{script} is required")
        for dep in ["@tauri-apps/api", "react", "react-dom"]:
            if dep not in deps:
                errors.append(f"dependencies.{dep} is required")
        all_deps = {**deps, **dev_deps}
        for dep in ["@tauri-apps/cli", "typescript", "vite"]:
            if dep not in all_deps:
                errors.append(f"{dep} is required in dependencies or devDependencies")
        if errors:
            self.fail("desktop_frontend", "; ".join(errors))
        else:
            self.pass_("desktop_frontend", "package scripts and Tauri/React dependencies validated")

    def check_docs_and_golden(self) -> None:
        errors: list[str] = []
        for rel in REQUIRED_PATHS["docs_and_tests"][:3]:
            text = self.path(rel).read_text(encoding="utf-8") if self.path(rel).is_file() else ""
            if len(text.strip()) < 800:
                errors.append(f"{rel} is too thin for production handoff")
            for keyword in ["Tauri", "Rust", "TypeScript"]:
                if keyword not in text:
                    errors.append(f"{rel} must mention {keyword}")
        sgf = self.path("tests/golden/basic_19x19.sgf")
        if not sgf.is_file():
            errors.append("tests/golden/basic_19x19.sgf is missing")
        else:
            text = sgf.read_text(encoding="utf-8").strip()
            for token in ["GM[1]", "FF[4]", "SZ[19]", ";B[", ";W["]:
                if token not in text:
                    errors.append(f"golden SGF missing token {token}")
        if errors:
            self.fail("docs_and_tests", "; ".join(errors))
        else:
            self.pass_("docs_and_tests", "architecture docs and golden SGF fixture validated")

    def run(self) -> list[CheckResult]:
        self.check_required_paths()
        self.check_workspace()
        self.check_crates()
        self.check_tauri()
        self.check_frontend_package()
        self.check_docs_and_golden()
        return self.results


def print_results(results: list[CheckResult], *, verbose: bool) -> None:
    failures = [result for result in results if not result.ok]
    passes = [result for result in results if result.ok]
    if verbose:
        for result in results:
            prefix = "PASS" if result.ok else "FAIL"
            print(f"{prefix} {result.name}: {result.detail}")
    elif failures:
        for result in failures:
            print(f"FAIL {result.name}: {result.detail}")
    else:
        for result in passes:
            print(f"PASS {result.name}: {result.detail}")
    print(f"Scaffold validation: {len(passes)} passed, {len(failures)} failed.")


def parse_minimal_toml(text: str) -> dict[str, Any]:
    """Parse the TOML subset used by this scaffold's manifests on Python 3.9/3.10."""
    root: dict[str, Any] = {}
    current = root
    lines = iter(enumerate(text.splitlines(), start=1))
    for lineno, raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            table_path = line[1:-1].strip().split(".")
            current = root
            for part in table_path:
                current = current.setdefault(part, {})
            continue
        if "=" not in line:
            raise ValueError(f"line {lineno}: expected key/value")
        key, value = [part.strip() for part in line.split("=", 1)]
        if value == "[":
            values: list[Any] = []
            for array_lineno, array_raw in lines:
                array_line = array_raw.split("#", 1)[0].strip()
                if not array_line:
                    continue
                if array_line == "]":
                    break
                values.append(parse_toml_scalar(array_line.rstrip(","), array_lineno))
            else:
                raise ValueError(f"line {lineno}: unterminated array")
            assign_toml_key(current, key, values)
        else:
            assign_toml_key(current, key, parse_toml_scalar(value.rstrip(","), lineno))
    return root


def assign_toml_key(table: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    target = table
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def parse_toml_scalar(value: str, lineno: int) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("{") and value.endswith("}"):
        result: dict[str, Any] = {}
        inner = value[1:-1].strip()
        if not inner:
            return result
        for part in split_toml_items(inner):
            if "=" not in part:
                raise ValueError(f"line {lineno}: invalid inline table")
            key, raw = [item.strip() for item in part.split("=", 1)]
            result[key] = parse_toml_scalar(raw, lineno)
        return result
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_toml_scalar(part.strip(), lineno) for part in split_toml_items(inner) if part.strip()]
    if value.replace(".", "", 1).isdigit():
        return float(value) if "." in value else int(value)
    raise ValueError(f"line {lineno}: unsupported value {value!r}")


def split_toml_items(value: str) -> list[str]:
    items: list[str] = []
    start = 0
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(value):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(value[start:index].strip())
            start = index + 1
    items.append(value[start:].strip())
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the LizzieYzy Next Tauri 2 scaffold.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to validate")
    parser.add_argument("--verbose", action="store_true", help="print passing checks as well as failures")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Repository root does not exist: {root}", file=sys.stderr)
        return 2
    results = Validator(root).run()
    print_results(results, verbose=args.verbose)
    return 1 if any(not result.ok for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
