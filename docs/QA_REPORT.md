# QA Report

This report tracks the repository-local user-flow smoke skeleton for the current SGF annotation/readboard branch. It is intentionally scoped to checks that can run without external KataGo binaries, sidecars, provider accounts, or live network parity.

## Automated Smoke Gate

Run:

```sh
python3 scripts/smoke_user_flows.py --verbose
```

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

Current repository-local alpha gate result:

```text
python3 scripts/smoke_user_flows.py --verbose
User-flow smoke: 19 passed, 0 failed, 5 pending.
```

With the native SGF save/read-back gate included, repository-local read-back refresh evidence is complete: `native_sgf_save_readback_surface` passes and verifies that backend save reads the saved file back while App save handling refreshes parse/replay/tree/cache state from the read-back text. This is still not a 100% or release-ready gate because the runtime/external gates listed below remain pending.

## Deferred Runtime Gates

These are not marked complete by the smoke skeleton:

| Gate | Status | Required evidence before completion |
| --- | --- | --- |
| Real Tauri UI flow | Pending | Launch desktop runtime, open a real SGF, navigate/reorder variations, edit comments/properties, append/delete nodes, save, reopen, and verify board state. |
| Runtime save/reopen proof | Pending | Save after comment/property edits plus append/delete/reorder, quit or restart the desktop runtime, reopen the saved SGF, and confirm tree order, node properties, comments, move count, and board state. The static `native_sgf_save_readback_surface` gate is repository-local read-back wiring evidence, not this desktop GUI proof. |
| KataGo analysis flow | Pending | Controlled KataGo binary/model/config evidence, one-shot analysis, full-game analysis, cancellation, cache hit, and failure reporting. |
| Readboard sidecar flow | Pending | Controlled sidecar/runtime evidence for probe and sync paths with unsupported/error states recorded distinctly. |
| Fox/Yike live provider flow | Pending | Real environment, account/session/network evidence, request/response capture, rate-limit/session-expiry behavior, and no claim of live parity from offline contracts alone. |
| Platform packaging smoke | Pending | Per-OS build/install/launch evidence, signing/notarization status where applicable, and installed-app smoke results. |

## Current QA Position

Passing `scripts/smoke_user_flows.py` means the repository still has the local fixture and command surface needed for SGF comment editing, node property editing, append move/pass, delete selected non-root node/subtree, and variation reorder foundations. It does not prove that a user can complete those flows in the native desktop UI, save them, reopen the file, and get identical board/tree state.

As of the current alpha gate, `scripts/smoke_user_flows.py --verbose` reports `19 passed, 0 failed, 5 pending`. Repository-local native SGF save/read-back refresh evidence is complete, but real desktop SGF save/reopen parity remains pending until the native Tauri GUI flow is recorded. Do not claim real desktop SGF save/reopen parity, live KataGo, Fox/Yike, readboard, production installer, full LegacyShell UI parity, or full legacy parity until the corresponding desktop/runtime checks above are recorded with environment details.
