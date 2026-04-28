#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "Cargo.toml", "apps/desktop/package.json", "apps/desktop/tsconfig.json", "apps/desktop/vite.config.ts", "apps/desktop/index.html",
    "apps/desktop/src/App.tsx", "apps/desktop/src/components/BoardCanvas.tsx", "apps/desktop/src-tauri/Cargo.toml", "apps/desktop/src-tauri/tauri.conf.json",
    "apps/desktop/src-tauri/capabilities/default.json", "crates/app-model/src/lib.rs", "crates/go-core/src/lib.rs", "crates/sgf/src/lib.rs",
    "crates/katago-protocol/src/lib.rs", "crates/analysis-core/src/lib.rs", "crates/engine-manager/src/lib.rs", "crates/storage/src/lib.rs",
    "docs/ARCHITECTURE_NEXT.md", "docs/MIGRATION_PLAN.md", "docs/AGENT_EXECUTION_SUMMARY.md"
]
JSON_FILES = ["apps/desktop/package.json", "apps/desktop/tsconfig.json", "apps/desktop/src-tauri/tauri.conf.json", "apps/desktop/src-tauri/capabilities/default.json"]

def main() -> int:
    missing = [p for p in REQUIRED_FILES if not (ROOT / p).exists()]
    if missing:
        print("Missing required files:")
        for p in missing: print(f"  - {p}")
        return 1
    for rel in JSON_FILES:
        with (ROOT / rel).open("r", encoding="utf-8") as fh:
            json.load(fh)
    conf = json.loads((ROOT / "apps/desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    assert conf["identifier"] == "org.lizzieyzy.next"
    assert conf["build"]["devUrl"].startswith("http://127.0.0.1")
    package = json.loads((ROOT / "apps/desktop/package.json").read_text(encoding="utf-8"))
    assert "tauri:dev" in package["scripts"]
    assert "@tauri-apps/api" in package["dependencies"]
    rust_files = list((ROOT / "crates").glob("*/src/lib.rs"))
    assert len(rust_files) >= 7
    print("Scaffold validation passed.")
    print(f"Checked {len(REQUIRED_FILES)} required files, {len(JSON_FILES)} JSON files, {len(rust_files)} Rust crates.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
