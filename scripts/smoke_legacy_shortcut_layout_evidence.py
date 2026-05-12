#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from smoke_legacy_layout_parity import main  # noqa: E402


if __name__ == "__main__":
    if "--evidence-out" not in sys.argv:
        sys.argv.extend(["--evidence-out", "docs/qa/legacy-shortcut-layout-evidence-macos.json"])
    if "--schema" not in sys.argv:
        sys.argv.extend(["--schema", "lizzieyzy.legacy-shortcut-layout-evidence.v1"])
    if "--name" not in sys.argv:
        sys.argv.extend(["--name", "legacy_shortcut_layout_evidence"])
    raise SystemExit(main())
