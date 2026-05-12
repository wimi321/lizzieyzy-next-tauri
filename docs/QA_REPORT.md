# QA Report

This report tracks the repository-local user-flow smoke skeleton for the current SGF annotation/readboard branch. It is intentionally scoped to checks that can run without external KataGo binaries, sidecars, provider accounts, or live network parity.

## Automated Smoke Gate

Run:

```sh
python3 scripts/smoke_user_flows.py --verbose
```

To collect the macOS local Tauri runtime UI evidence, run:

```sh
python3 scripts/smoke_tauri_runtime_ui.py --evidence-out docs/qa/tauri-runtime-ui-smoke-macos.json
```

This runtime script creates a temporary SGF, starts `npm --prefix apps/desktop run tauri:dev` with the `VITE_LIZZIEYZY_RUNTIME_SMOKE*`/`LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH` environment variables, waits for the app-produced report JSON, validates the required check names, and writes sanitized evidence when the report status is `pass`. CI does not run this GUI flow; CI only runs `smoke_user_flows.py` to validate the committed evidence schema and semantics.

To collect the macOS live KataGo evidence, run:

```sh
python3 scripts/smoke_katago_live.py --engine /path/to/katago --model /path/to/model.bin.gz --config /path/to/analysis.cfg --evidence-out docs/qa/katago-live-smoke-macos.json
python3 scripts/smoke_tauri_katago_live.py --engine /path/to/katago --model /path/to/model.bin.gz --config /path/to/analysis.cfg --evidence-out docs/qa/katago-tauri-runtime-smoke-macos.json
```

The CLI runner invokes a real KataGo binary with a real model and config, probes `katago version`, runs one-position and batch `katago analysis` JSONL queries, validates response ids/root info/candidate output, captures stderr byte counts, and writes sanitized evidence. The Tauri runner launches `npm --prefix apps/desktop run tauri:dev` with `VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE=katago-live` and KataGo env vars, then waits for runtime evidence for startup, assets, analyze-once, analyze-game, and start/cancel. CI does not run KataGo or GUI; it only validates committed evidence.

To collect scoped macOS readboard runtime evidence, run the Tauri readboard smoke runner and record:

```sh
docs/qa/readboard-tauri-runtime-smoke-macos.json
```

The repository gate expects schema `lizzieyzy.readboard-tauri-runtime-smoke.v1`, status `pass`, platform `macos`, and passing semantic checks for Tauri runtime startup, sidecar probe ready/unavailable states, protocol-line sync with `snapshotId`, board size, move number, stone count, and player-to-play, target-state-change sync with distinct before/after snapshots and stable board size, explicit unsupported OCR boundary with an image/OCR message, and explicit `external_client_not_covered` fields for OCR and external client/window capture. CI validates the committed JSON only; it does not run the GUI, sidecar, OCR, or any external client/window capture.

To collect scoped macOS provider runtime evidence, run the Tauri provider smoke runner and record:

```sh
docs/qa/provider-live-smoke-macos.json
```

The repository gate expects schema `lizzieyzy.provider-live-smoke.v1`, status `pass`, platform `macos`, and passing semantic checks for Tauri runtime startup, controlled-network Yike fetch, controlled-network Fox fetch, typed provider failure modes, controlled HTTP request observation, explicit non-offline-parser-only evidence, and explicit external account scope limits. CI validates the committed JSON only; this scoped evidence does not cover real Fox/Yike services, account login state, anti-bot stability, or service schema drift.

Covered checks:

| Area | Status | Evidence |
| --- | --- | --- |
| Golden SGF fixtures | Automated | Verifies `tests/golden/basic_19x19.sgf`, `tests/golden/sgf_compat_variations.sgf`, `tests/golden/sgf_ff4_compat.sgf`, and `tests/golden/sgf_reorder_variations.sgf` exist and are non-empty. |
| SGF compatibility fixture shape | Automated | Verifies the FF4 compatibility fixture contains variations, comments, setup properties, and labels. |
| SGF variation reorder fixture shape | Automated | Verifies the reorder fixture has three sibling variations under one parent, comments, an unknown property, labels/annotations, and a nested subtree. |
| Package entry points | Automated | Verifies root and desktop package scripts expose dev/build/Tauri entry points. |
| SGF edit Tauri commands | Automated | Verifies `update_sgf_node_comment`, `append_sgf_move`, `delete_sgf_node`, `update_sgf_node_properties`, and `reorder_sgf_variation` are defined as Tauri commands and registered in `generate_handler!`. |
| SGF node property editing command | Automated | Verifies the local command surface for updating SGF node properties is present. This is command/fixture evidence only, not a reopened-file desktop proof. |
| SGF variation reorder command | Automated | Verifies the local command surface for sibling variation reorder is present and the reorder fixture can represent the target tree shape. This is not interactive UI smoke evidence. |
| LegacyShell main menu surface | Automated | Statically verifies the `View`, `Engine`, `Tools`, and `Help` menu entries in `LegacyShell.tsx` are present, identifiable by label or `data-testid`, and are not disabled-only placeholders. This is static menu-surface evidence only; runtime UI automation still needs to prove each entry reaches the expected surface. |
| Native SGF save/read-back refresh surface | Automated | Statically verifies native SGF save writes through `write_sgf_file`, reads the saved file back through `read_sgf_file`/`readSgfDocument`, and refreshes App state by parsing, replaying, rebuilding the tree, and checking cache from the read-back SGF text. This is repository-local evidence only; it is not real desktop GUI save/reopen smoke. |
| SGF existing move edit surface | Automated | Statically verifies `sgf_existing_move_edit_surface`: `edit_sgf_move` is defined/registered and the repository-local backend/App/SgfTreePanel edit-existing-move surface is wired. This is repository-local evidence only; it is not interactive desktop edit/save/reopen proof. |
| macOS Tauri runtime UI smoke evidence | Scoped evidence gate | `smoke_user_flows.py` marks `ui_tauri_runtime_smoke` PASS only when `docs/qa/tauri-runtime-ui-smoke-macos.json` has schema `lizzieyzy.tauri-runtime-ui-smoke.v1`, status `pass`, platform `macos`, all required checks passing, semantic evidence for existing-move edit, variation reorder target index, delete absence, save/read-back, board-state invariants, and two-launch save/reopen proof fields: `secondLaunch`, `reopen`, and `afterReopen`. |
| macOS live KataGo smoke evidence | Scoped evidence gate recorded | `smoke_user_flows.py` marks `katago_live_smoke` PASS only when both evidence files pass: `docs/qa/katago-live-smoke-macos.json` for real CLI `katago analysis`, and `docs/qa/katago-tauri-runtime-smoke-macos.json` for the Tauri runtime path with startup, assets, analyze-once, analyze-game, failure-mode, and confirmed start/cancel checks. |
| macOS scoped readboard runtime evidence | Scoped evidence gate recorded | `smoke_user_flows.py` marks `readboard_live_smoke` PASS only when `docs/qa/readboard-tauri-runtime-smoke-macos.json` validates the scoped Tauri runtime probe/protocol evidence, including snapshot/change semantics, and explicitly records that OCR and external client/window capture are not covered. |
| macOS scoped provider controlled-network evidence | Scoped evidence gate recorded | `smoke_user_flows.py` marks `provider_live_smoke` PASS only when `docs/qa/provider-live-smoke-macos.json` validates controlled-network Yike/Fox runtime fetches, typed failure modes, and explicit external account/service scope exclusions. |

Current repository-local alpha gate result:

```text
python3 scripts/smoke_user_flows.py --verbose
User-flow smoke: 25 passed, 0 failed, 1 pending.
```

With the native SGF save/read-back, existing-move-edit, macOS local Tauri runtime UI smoke, macOS live KataGo smoke, scoped macOS readboard runtime evidence, and scoped macOS provider controlled-network evidence included, repository-local read-back refresh, edit-existing-move surface evidence, scoped macOS save/reopen runtime evidence, real KataGo CLI evidence, Tauri runtime KataGo evidence, scoped readboard probe/protocol evidence, and controlled-network provider fetch evidence are complete for their current gates. This is still not a 100% or release-ready gate because multiplatform packaging, native file-dialog/manual release, OCR readboard capture, real external client/window capture, real Fox/Yike service/account parity, and broader legacy parity remain pending.

## Deferred Runtime Gates

These are not marked complete by the smoke skeleton:

| Gate | Status | Required evidence before completion |
| --- | --- | --- |
| macOS local runtime save/reopen proof | Recorded locally on macOS | `docs/qa/tauri-runtime-ui-smoke-macos.json` was produced from the two-launch macOS runtime smoke. The JSON proves a second launch and reopen with explicit `firstLaunch`, `secondLaunch`, `saveReopenProof`, `reopen`, and `afterReopen` fields, including tree order, comments, properties, move count, and board-state verification after reopen. This is not native file dialog/manual release proof. |
| Broader real Tauri UI flow | Pending | Record any additional manual desktop runtime coverage beyond the macOS local smoke, including native file dialog open/save paths and exploratory UI behavior. |
| KataGo analysis flow | Scoped macOS evidence recorded | `docs/qa/katago-live-smoke-macos.json` and `docs/qa/katago-tauri-runtime-smoke-macos.json` were produced with a real KataGo binary, model, and config. The CLI evidence covers version probe plus one-position and batch `katago analysis`; the Tauri runtime evidence covers real desktop backend startup, assets, analyze-once, analyze-game, missing-asset failure mode, and confirmed start/cancel. Cache-hit and broader review workflow evidence still need desktop workflow coverage. |
| Readboard sidecar flow | Scoped macOS evidence recorded | `docs/qa/readboard-tauri-runtime-smoke-macos.json` records scoped macOS Tauri runtime evidence for sidecar probe ready/unavailable states, protocol-line sync with snapshot/move/stone semantics, target-state-change sync with distinct before/after snapshots and stable board size, and unsupported OCR boundary behavior. This gate is deliberately scoped: it does not prove OCR, real external client/window capture, or cross-platform packaging. |
| Fox/Yike provider flow | Scoped controlled-network evidence recorded | `docs/qa/provider-live-smoke-macos.json` records scoped macOS Tauri runtime evidence for controlled-network Yike/Fox fetches, request observation, and typed provider failure modes. Real Fox/Yike service coverage, account/session login state, anti-bot stability, rate-limit/session-expiry behavior, and service schema drift remain pending and must not be inferred from controlled-network evidence. |
| Platform packaging smoke | Pending | Per-OS build/install/launch evidence, signing/notarization status where applicable, and installed-app smoke results. |

## Current QA Position

Passing `scripts/smoke_user_flows.py` means the repository still has the local fixture and command surface needed for SGF comment editing, node property editing, append move/pass, delete selected non-root node/subtree, and variation reorder foundations. It does not prove that a user can complete those flows in the native desktop UI, save them, reopen the file, and get identical board/tree state.

As of this gate, `scripts/smoke_user_flows.py --verbose` reports `25 passed, 0 failed, 1 pending`, and `ui_tauri_runtime_smoke` passes from committed macOS local runtime evidence with two-launch save/reopen semantics. `katago_live_smoke` also passes from paired macOS CLI and Tauri runtime evidence. `readboard_live_smoke` passes from scoped macOS Tauri runtime evidence for probe/protocol behavior. `provider_live_smoke` passes from scoped macOS controlled-network provider evidence. Repository-local native SGF save/read-back refresh, edit-existing-move surface evidence, scoped macOS save/reopen runtime evidence, scoped macOS KataGo runtime evidence, scoped readboard runtime evidence, and scoped provider controlled-network evidence are complete for their current gates. OCR readboard capture, real external client/window capture, real Fox/Yike service/account coverage, anti-bot stability, service schema drift, and cross-platform packaging remain outside that scoped proof. Do not claim Fox/Yike full parity, full readboard parity, production installer, full LegacyShell UI parity, or full legacy parity until the corresponding desktop/runtime checks above are recorded with environment details.
