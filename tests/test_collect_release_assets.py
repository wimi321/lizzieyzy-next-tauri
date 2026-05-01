from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collect_release_assets.py"


def load_module():
    spec = importlib.util.spec_from_file_location("collect_release_assets", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load collect_release_assets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CollectReleaseAssetsTests(unittest.TestCase):
    def test_collects_assets_and_writes_checksum_file(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle" / "dmg"
            out = root / "out"
            bundle.mkdir(parents=True)
            (bundle / "LizzieYzy Next_0.1.0_aarch64.dmg").write_bytes(b"release")

            assets = module.collect(bundle, out, "macos")

            names = sorted(path.name for path in assets)
            self.assertEqual(names, ["LizzieYzy-Next_0.1.0_aarch64-macos.dmg", "SHA256SUMS-macos.txt"])
            checksums = (out / "SHA256SUMS-macos.txt").read_text(encoding="utf-8")
            self.assertIn("LizzieYzy-Next_0.1.0_aarch64-macos.dmg", checksums)

    def test_rejects_empty_bundle_directory(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle"
            bundle.mkdir()
            with self.assertRaises(RuntimeError):
                module.collect(bundle, root / "out", "linux-x64")


if __name__ == "__main__":
    unittest.main()
