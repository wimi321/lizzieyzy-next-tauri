#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


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


def release_suffix(path: Path) -> str | None:
    for suffix in RELEASE_SUFFIXES:
        if path.name.endswith(suffix):
            return suffix
    return None


def safe_asset_name(source: Path, platform: str) -> str:
    suffix = release_suffix(source)
    if suffix is None:
        raise ValueError(f"Unsupported release asset suffix: {source}")
    stem = source.name[: -len(suffix)]
    normalized = "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in stem)
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    normalized = normalized.strip("-._") or "bundle"
    return f"{normalized}-{platform}{suffix}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(bundle_dir: Path, out_dir: Path, platform: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    assets: list[Path] = []
    for candidate in sorted(path for path in bundle_dir.rglob("*") if path.is_file()):
        if release_suffix(candidate) is None:
            continue
        target = out_dir / safe_asset_name(candidate, platform)
        if target.exists():
            raise RuntimeError(f"Duplicate release asset name after normalization: {target.name}")
        shutil.copy2(candidate, target)
        assets.append(target)

    if not assets:
        raise RuntimeError(f"No release assets found under {bundle_dir}")

    checksum_path = out_dir / f"SHA256SUMS-{platform}.txt"
    checksum_lines = [f"{sha256(asset)}  {asset.name}" for asset in assets]
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    assets.append(checksum_path)
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Tauri bundle assets for GitHub Release upload.")
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--platform", required=True)
    args = parser.parse_args()

    assets = collect(args.bundle_dir, args.out_dir, args.platform)
    print("Collected release assets:")
    for asset in assets:
        print(f"  - {asset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
