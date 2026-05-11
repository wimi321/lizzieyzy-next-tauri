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

## Deferred Runtime Gates

These are not marked complete by the smoke skeleton:

| Gate | Status | Required evidence before completion |
| --- | --- | --- |
| Real Tauri UI flow | Pending | Launch desktop runtime, open a real SGF, navigate/reorder variations, edit comments/properties, append/delete nodes, save, reopen, and verify board state. |
| Runtime save/reopen proof | Pending | Save after comment/property edits plus append/delete/reorder, quit or restart the desktop runtime, reopen the saved SGF, and confirm tree order, node properties, comments, move count, and board state. |
| KataGo analysis flow | Pending | Controlled KataGo binary/model/config evidence, one-shot analysis, full-game analysis, cancellation, cache hit, and failure reporting. |
| Readboard sidecar flow | Pending | Controlled sidecar/runtime evidence for probe and sync paths with unsupported/error states recorded distinctly. |
| Fox/Yike live provider flow | Pending | Real environment, account/session/network evidence, request/response capture, rate-limit/session-expiry behavior, and no claim of live parity from offline contracts alone. |
| Platform packaging smoke | Pending | Per-OS build/install/launch evidence, signing/notarization status where applicable, and installed-app smoke results. |

## Current QA Position

Passing `scripts/smoke_user_flows.py` means the repository still has the local fixture and command surface needed for SGF comment editing, node property editing, append move/pass, delete selected non-root node/subtree, and variation reorder foundations. It does not prove that a user can complete those flows in the native desktop UI, save them, reopen the file, and get identical board/tree state.

The runtime and external gates remain release-blocking for claims beyond repository-local smoke evidence. Do not claim live KataGo, Fox/Yike, readboard, production installer, or full legacy parity until the corresponding desktop/runtime checks above are recorded with environment details.
