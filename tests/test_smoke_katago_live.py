from __future__ import annotations

import importlib.util
import json
import os
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_katago_live.py"
SPEC = importlib.util.spec_from_file_location("smoke_katago_live", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke_katago_live = importlib.util.module_from_spec(SPEC)
sys.modules["smoke_katago_live"] = smoke_katago_live
SPEC.loader.exec_module(smoke_katago_live)


class SmokeKatagoLiveTests(unittest.TestCase):
    def test_parse_jsonl_rejects_invalid_stdout(self) -> None:
        with self.assertRaises(smoke_katago_live.SmokeError):
            smoke_katago_live.parse_jsonl("{not json}\n")

    def test_validate_response_requires_move_infos(self) -> None:
        with self.assertRaises(smoke_katago_live.SmokeError):
            smoke_katago_live.validate_response({"id": "q", "rootInfo": {}}, "q")

    def test_run_live_smoke_with_fake_katago_writes_sanitized_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "katago-fake"
            model = root / "model.bin.gz"
            config = root / "analysis.cfg"
            evidence_out = root / "docs/qa/katago-live-smoke-macos.json"
            write_fake_katago(engine)
            model.write_text("fake model", encoding="utf-8")
            config.write_text("fake config", encoding="utf-8")

            report = smoke_katago_live.run_live_smoke(engine, model, config, timeout=5.0, max_visits=1)
            smoke_katago_live.write_evidence(evidence_out, report, root=root)

            self.assertEqual("pass", report["status"])
            checks = {check["name"]: check for check in report["checks"]}
            self.assertIn("one_position_analysis", checks)
            self.assertIn("batch_analysis", checks)
            written = json.loads(evidence_out.read_text(encoding="utf-8"))
            self.assertEqual("<katago-engine>", written["engine"]["path"])
            self.assertEqual("<katago-model>", written["engine"]["modelPath"])
            self.assertEqual("<katago-config>", written["engine"]["configPath"])


def write_fake_katago(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import sys

            if len(sys.argv) > 1 and sys.argv[1] == "version":
                print("KataGo fake 1.0")
                raise SystemExit(0)

            if len(sys.argv) > 1 and sys.argv[1] == "analysis":
                for line in sys.stdin:
                    if not line.strip():
                        continue
                    query = json.loads(line)
                    print(json.dumps({
                        "id": query["id"],
                        "moveInfos": [{"move": "D4", "visits": 1}],
                        "rootInfo": {"visits": 1},
                        "ownership": [0.0],
                        "policy": [0.1]
                    }), flush=True)
                raise SystemExit(0)

            print("unexpected args", sys.argv, file=sys.stderr)
            raise SystemExit(2)
            """
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o755)


if __name__ == "__main__":
    unittest.main()
