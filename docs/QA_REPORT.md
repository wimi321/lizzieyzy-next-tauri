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

To collect the scoped Desktop SGF Editing UX evidence after the macOS local Tauri runtime UI evidence is present, run:

```sh
python3 scripts/smoke_desktop_sgf_editing_ux.py --evidence-out docs/qa/desktop-sgf-editing-ux-smoke-macos.json
```

This evidence reuses the committed two-launch Tauri runtime UI smoke for tree navigation, comment/property/annotation editing, append/edit/reorder/delete, and save/readback/reopen semantics, then records source-surface/source-visible fields for the LegacyShell, toolbar/menu controls, SGF tree panel, annotation editor, selected-node state, dirty/saved status, and `nativeDialogClickCovered=false`. Its `collectionMethod` is `source_static_plus_tauri_runtime_chain`, with `runtimeDomObserved=false` and `screenshotObserved=false`. CI validates the committed JSON only; this scoped proof does not observe rendered DOM, take screenshots, click the OS-native dialog, cover OCR/external client/window capture, or prove full native desktop interactive UX parity.

The scoped browser-rendered DOM/click/screenshot evidence is recorded at:

```sh
docs/qa/desktop-ui-click-smoke-macos.json
```

The repository gate expects schema `lizzieyzy.desktop-ui-click-smoke.v1`, status `pass`, platform `macos`, `browserDomObserved=true`, `screenshotObserved=true`, `clickObserved=true`, at least two screenshot records with stable non-local paths and SHA-256 hashes, clicked controls, visible assertions, and boundaries with `nativeFileDialogCovered=false`. `tauriWebviewDomObserved` must remain false unless the evidence includes explicit Tauri WebView proof. This is scoped browser-rendered click proof only; it is not Tauri WebView DOM proof, native file-dialog proof, or full parity evidence.

To validate scoped Tauri desktop window/runtime screenshot evidence after Worker-1 records it, commit:

```sh
docs/qa/tauri-window-runtime-smoke-macos.json
```

The repository gate expects schema `lizzieyzy.tauri-window-runtime-smoke.v1`, status `pass`, platform `macos`/`darwin`, `tauriRuntimeObserved=true`, `tauriWindowScreenshotObserved=true`, `browserFallbackUsed=false`, `webviewDomClickCovered=false`, `nativeDialogClickCovered=false`, at least one Tauri window screenshot with a stable non-local path and SHA-256 hash, source runtime evidence with schema `lizzieyzy.tauri-runtime-ui-smoke.v1` and status `pass`, and save/reopen semantic proof. This is scoped Tauri runtime/window screenshot proof only; it is not WebView DOM click proof, native dialog proof, installed packaged app/signing/release proof, OCR/capture proof, provider/readboard parity, or full legacy parity evidence.

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

To collect scoped multiplatform packaging smoke evidence, run the packaging smoke runner and record:

```sh
docs/qa/multiplatform-packaging-smoke.json
```

The repository gate expects schema `lizzieyzy.multiplatform-packaging-smoke.v1`, status `pass`, macOS/Windows/Linux artifact checks, signing-state records, dev-server-absence checks, and SHA-256 checksums. CI validates the committed JSON only; this scoped evidence records packaging smoke state and does not claim official signing, notarized release distribution, updater readiness, or full legacy parity.

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
| SGF annotation surface | Automated | Statically verifies `sgf_annotation_surface`: SgfAnnotationPanel exposes TR/SQ/CR/MA/SL/LB/AR/LN add/update/remove controls, App routes saves through `updateSgfNodeProperties`, save failures surface as annotation errors, and runtime smoke includes `annotation_edit` add/update/remove semantics. This is scoped SGF annotation persistence evidence only. |
| Legacy Java/Swing config migration surface | Automated | Statically verifies `legacy_config_migration_surface`: backend API wrappers call `preview_legacy_config_migration`/`apply_legacy_config_migration`, App wires path/preview/apply state, and PreferencesPanel exposes path input, Preview/Apply actions, status, warnings, and migrated fields. This is UI/API surface evidence only; it is not broad migrated-config corpus or rollback proof. |
| macOS Tauri runtime UI smoke evidence | Scoped evidence gate | `smoke_user_flows.py` marks `ui_tauri_runtime_smoke` PASS only when `docs/qa/tauri-runtime-ui-smoke-macos.json` has schema `lizzieyzy.tauri-runtime-ui-smoke.v1`, status `pass`, platform `macos`, all required checks passing, semantic evidence for annotation add/update/remove, existing-move edit, variation reorder target index, delete absence, save/read-back, board-state invariants, and two-launch save/reopen proof fields: `secondLaunch`, `reopen`, and `afterReopen`. |
| Desktop SGF editing UX smoke evidence | Scoped evidence gate recorded | `smoke_user_flows.py` marks `desktop_sgf_editing_ux_smoke` PASS only when `docs/qa/desktop-sgf-editing-ux-smoke-macos.json` has schema `lizzieyzy.desktop-sgf-editing-ux-smoke.v1`, status `pass`, platform `macos`, `collectionMethod=source_static_plus_tauri_runtime_chain`, `runtimeDomObserved=false`, `screenshotObserved=false`, all required source/static UI surface checks passing, source-visible fields for LegacyShell, toolbar/menu controls, tree panel, annotation editor, selected-node state, dirty/saved status, `nativeDialogClickCovered=false`, and runtime-chain coverage for tree navigation, comment/property/annotation, append/edit/reorder/delete, and save/readback/reopen. This is source-surface plus runtime-chain evidence only, not runtime-rendered DOM/screenshot/click proof. |
| Desktop browser-rendered UI click smoke | Scoped evidence gate recorded | `smoke_user_flows.py` marks `desktop_ui_click_smoke` PASS only when `docs/qa/desktop-ui-click-smoke-macos.json` has schema `lizzieyzy.desktop-ui-click-smoke.v1`, status `pass`, platform `macos`, browser DOM/click/screenshot observation flags, multiple SHA-256 screenshot records with stable non-local paths and SHA-256 hashes, clicked controls, visible assertions, and boundaries that keep native file dialog coverage false and Tauri WebView DOM coverage false unless explicit proof is recorded. This is scoped browser-rendered click evidence only. |
| Tauri window/runtime screenshot smoke | Scoped evidence gate recorded | `smoke_user_flows.py` marks `tauri_window_runtime_smoke` PASS only when `docs/qa/tauri-window-runtime-smoke-macos.json` has schema `lizzieyzy.tauri-window-runtime-smoke.v1`, status `pass`, platform `macos`/`darwin`, Tauri runtime and Tauri window screenshot observation flags, no browser fallback, no WebView DOM click claim, no native dialog click claim, stable non-local screenshot path with SHA-256, source runtime evidence schema/status, and save/reopen semantic proof. This is scoped Tauri runtime/window screenshot evidence only. |
| macOS live KataGo smoke evidence | Scoped evidence gate recorded | `smoke_user_flows.py` marks `katago_live_smoke` PASS only when both evidence files pass: `docs/qa/katago-live-smoke-macos.json` for real CLI `katago analysis`, and `docs/qa/katago-tauri-runtime-smoke-macos.json` for the Tauri runtime path with startup, assets, analyze-once, analyze-game, failure-mode, and confirmed start/cancel checks. |
| Bundled/runtime asset layout surface | Scoped repository surface recorded | `smoke_user_flows.py` marks `runtime_asset_layout_surface` PASS when frontend backend wrappers call `resolve_runtime_asset_layout`/`validate_runtime_asset_layout` and EngineSetupPanel shows bundled/runtime asset status while preserving local engine/model/config asset fields. Large KataGo models are not bundled, and this is not installed-app bundled-engine launch proof. |
| macOS scoped readboard runtime evidence | Scoped evidence gate recorded | `smoke_user_flows.py` marks `readboard_live_smoke` PASS only when `docs/qa/readboard-tauri-runtime-smoke-macos.json` validates the scoped Tauri runtime probe/protocol evidence, including snapshot/change semantics, and explicitly records that OCR and external client/window capture are not covered. |
| macOS scoped provider controlled-network evidence | Scoped evidence gate recorded | `smoke_user_flows.py` marks `provider_live_smoke` PASS only when `docs/qa/provider-live-smoke-macos.json` validates controlled-network Yike/Fox runtime fetches, typed failure modes, and explicit external account/service scope exclusions. |
| Multiplatform packaging smoke evidence | Scoped evidence gate recorded | `smoke_user_flows.py` marks `multiplatform_packaging_smoke` PASS only when `docs/qa/multiplatform-packaging-smoke.json` validates scoped macOS/Windows/Linux artifact, signing-state, dev-server-absence, and checksum evidence. This is not official signing, notarization, release publication, updater readiness, or full legacy parity proof. |

Current repository-local alpha gate result:

```text
python3 scripts/smoke_user_flows.py --verbose
User-flow smoke: 32 passed, 0 failed, 0 pending.
```

With the native SGF save/read-back, existing-move-edit, scoped annotation editor surface, scoped Desktop SGF Editing UX evidence, scoped browser-rendered DOM/click/screenshot evidence, scoped Tauri runtime/window screenshot evidence, legacy config migration UI/API surface, bundled/runtime asset layout surface, macOS local Tauri runtime UI smoke, macOS live KataGo smoke, scoped macOS readboard runtime evidence, scoped macOS provider controlled-network evidence, and scoped multiplatform packaging smoke evidence included, repository-local read-back refresh, edit-existing-move surface evidence, scoped SGF annotation UI/API evidence, scoped desktop SGF editing source-surface/runtime-chain evidence, scoped browser-rendered click evidence, scoped Tauri runtime/window screenshot evidence, scoped legacy migration entrypoint evidence, scoped runtime asset layout/status evidence, macOS local save/reopen runtime evidence, real KataGo CLI evidence, Tauri runtime KataGo evidence, scoped readboard probe/protocol evidence, controlled-network provider fetch evidence, and scoped artifact/signing-state/dev-server/checksum packaging evidence are complete for their current gates. The macOS local Tauri runtime UI smoke evidence is recorded with `annotation_edit` and reopened `afterReopen.annotationsVerified` semantics; the desktop SGF editing UX evidence records source-visible fields with `nativeDialogClickCovered=false`, `runtimeDomObserved=false`, and `screenshotObserved=false`; the browser click evidence records browser DOM, screenshot, and click observation while keeping native file dialog and Tauri WebView DOM boundaries explicit; and the Tauri window evidence records scoped runtime/window screenshot observation while keeping browser fallback, WebView DOM click coverage, and native dialog click coverage false. This is still not a 100% or release-ready gate because broad legacy config corpus coverage, rollback behavior, WebView DOM click proof, native file-dialog/manual release, installed packaged app/signing/release proof, legacy capture/import helpers, OCR readboard capture, real external client/window capture, real Fox/Yike service/account parity, official signing/notarization/release publication/updater readiness, and broader legacy parity remain pending.

## Deferred Runtime Gates

These are the scoped/runtime gates and the remaining evidence boundaries:

| Gate | Status | Required evidence before completion |
| --- | --- | --- |
| macOS local runtime save/reopen proof | Scoped evidence recorded | `docs/qa/tauri-runtime-ui-smoke-macos.json` records the two-launch macOS runtime smoke with `annotation_edit` and `afterReopen.annotationsVerified` alongside `firstLaunch`, `secondLaunch`, `saveReopenProof`, `reopen`, comments, properties, move count, and board-state verification. This is not native file dialog/manual release proof. |
| Desktop SGF editing UX proof | Scoped evidence recorded | `docs/qa/desktop-sgf-editing-ux-smoke-macos.json` records source-surface/source-visible fields for LegacyShell, toolbar/menu, SGF tree, annotation editor, selected-node UX state, dirty/saved status, and runtime-chain coverage for tree navigation, comment/property/annotation, append/edit/reorder/delete, and save/readback/reopen. It explicitly records `collectionMethod=source_static_plus_tauri_runtime_chain`, `runtimeDomObserved=false`, `screenshotObserved=false`, and `nativeDialogClickCovered=false`, so runtime-rendered DOM/screenshot/click proof and native dialog/manual release proof remain pending. |
| Desktop browser-rendered click proof | Scoped evidence recorded | `docs/qa/desktop-ui-click-smoke-macos.json` records scoped browser DOM observation, screenshots with stable non-local paths and SHA-256 hashes, clicked controls, visible assertions, and boundaries with `nativeFileDialogCovered=false`. `tauriWebviewDomObserved` remains false unless explicit Tauri WebView proof is recorded. This is not native file dialog, Tauri WebView, or full parity proof. |
| Tauri runtime/window screenshot proof | Scoped evidence recorded | `docs/qa/tauri-window-runtime-smoke-macos.json` records scoped Tauri runtime/window screenshot observation with no browser fallback, no WebView DOM click coverage, no native dialog click coverage, stable non-local screenshot paths, valid source runtime evidence, and save/reopen semantic proof. This is not WebView DOM click proof, native dialog proof, installed packaged app/signing/release proof, OCR/capture proof, provider/readboard parity, or full legacy parity. |
| Broader real Tauri UI flow | Pending | Record any additional manual desktop runtime coverage beyond the macOS local smoke, including native file dialog open/save paths and exploratory UI behavior. |
| KataGo analysis flow | Scoped macOS evidence recorded | `docs/qa/katago-live-smoke-macos.json` and `docs/qa/katago-tauri-runtime-smoke-macos.json` were produced with a real KataGo binary, model, and config. The CLI evidence covers version probe plus one-position and batch `katago analysis`; the Tauri runtime evidence covers real desktop backend startup, assets, analyze-once, analyze-game, missing-asset failure mode, and confirmed start/cancel. Cache-hit and broader review workflow evidence still need desktop workflow coverage. |
| Bundled/runtime asset layout | Scoped repository surface recorded | EngineSetupPanel displays bundled/runtime asset layout status from the Tauri runtime layout commands and keeps local engine/model/config asset configuration visible. This scoped gate does not bundle large KataGo models, does not prove installed-app bundled-engine launch, and does not prove signing, notarization, or release asset inclusion. |
| Readboard sidecar flow | Scoped macOS evidence recorded | `docs/qa/readboard-tauri-runtime-smoke-macos.json` records scoped macOS Tauri runtime evidence for sidecar probe ready/unavailable states, protocol-line sync with snapshot/move/stone semantics, target-state-change sync with distinct before/after snapshots and stable board size, and unsupported OCR boundary behavior. This gate is deliberately scoped: it does not prove OCR, real external client/window capture, or cross-platform packaging. |
| Fox/Yike provider flow | Scoped controlled-network evidence recorded | `docs/qa/provider-live-smoke-macos.json` records scoped macOS Tauri runtime evidence for controlled-network Yike/Fox fetches, request observation, and typed provider failure modes. Real Fox/Yike service coverage, account/session login state, anti-bot stability, rate-limit/session-expiry behavior, and service schema drift remain pending and must not be inferred from controlled-network evidence. |
| Platform packaging smoke | Scoped evidence recorded | `docs/qa/multiplatform-packaging-smoke.json` records scoped macOS/Windows/Linux packaging smoke evidence for artifacts, signing-state recording, dev-server absence, and SHA-256 checksums. This gate does not prove official signing, notarization, release publication, updater readiness, store distribution, or full release parity. |
| Legacy Java/Swing config migration | Scoped repository surface recorded | PreferencesPanel now exposes a migration entrypoint with path input, Preview/Apply actions, status, warnings, and migrated-field output, wired through frontend API calls to the existing Tauri commands. Representative migrated config corpus tests, rollback/error recovery breadth, and real-user migration smoke remain outside this scoped proof. |

## Current QA Position

Passing `scripts/smoke_user_flows.py` means the repository still has the local fixture and command surface needed for SGF comment editing, node property editing, append move/pass, delete selected non-root node/subtree, and variation reorder foundations. It does not prove that a user can complete those flows in the native desktop UI, save them, reopen the file, and get identical board/tree state.

As of this gate, `scripts/smoke_user_flows.py --verbose` reports `32 passed, 0 failed, 0 pending`. `ui_tauri_runtime_smoke` passes from committed macOS local runtime evidence recorded with `annotation_edit` and reopened `afterReopen.annotationsVerified` fields. `desktop_sgf_editing_ux_smoke` passes from committed scoped source/static UX evidence with source-visible LegacyShell, toolbar/menu controls, tree panel, annotation editor, selected-node state, dirty/saved status, runtime-chain coverage for tree navigation/comment/property/annotation/append/edit/reorder/delete/save-readback-reopen, `collectionMethod=source_static_plus_tauri_runtime_chain`, `runtimeDomObserved=false`, `screenshotObserved=false`, and `nativeDialogClickCovered=false`. `desktop_ui_click_smoke` passes from committed scoped browser-rendered DOM/click/screenshot evidence with stable screenshot paths, clicked controls, visible assertions, and boundaries excluding native file dialog and Tauri WebView DOM proof. `tauri_window_runtime_smoke` passes from committed scoped Tauri runtime/window screenshot evidence with stable screenshot paths, valid source runtime evidence, save/reopen semantic proof, `browserFallbackUsed=false`, `webviewDomClickCovered=false`, and `nativeDialogClickCovered=false`. `katago_live_smoke` passes from paired macOS CLI and Tauri runtime evidence. `runtime_asset_layout_surface` passes as scoped repository UI/API evidence for bundled/runtime asset layout status while preserving local asset configuration. `sgf_annotation_surface` passes as scoped repository UI/API evidence for TR/SQ/CR/MA/SL/LB/AR/LN persistence through the SGF property update path. `readboard_live_smoke` passes from scoped macOS Tauri runtime evidence for probe/protocol behavior. `provider_live_smoke` passes from scoped macOS controlled-network provider evidence. `multiplatform_packaging_smoke` passes from scoped macOS/Windows/Linux artifact, signing-state, dev-server-absence, and checksum evidence. `legacy_config_migration_surface` passes as repository-local UI/API surface evidence. Repository-local native SGF save/read-back refresh, edit-existing-move surface evidence, scoped annotation UI/API evidence, scoped desktop SGF editing source-surface/runtime-chain evidence, scoped browser-rendered DOM/click/screenshot evidence, scoped Tauri runtime/window screenshot evidence, scoped legacy migration entrypoint evidence, scoped runtime asset layout/status evidence, scoped macOS local runtime UI evidence, scoped macOS KataGo runtime evidence, scoped readboard runtime evidence, scoped provider controlled-network evidence, and scoped packaging smoke evidence are complete for their current gates. Broad legacy config corpus migration, rollback behavior, WebView DOM click proof, native file dialog click coverage, installed packaged app/signing/release proof, bundled installed-app engine launch, large-model bundling, release asset inclusion, legacy capture/import helpers, OCR readboard capture, real external client/window capture, real Fox/Yike service/account coverage, anti-bot stability, service schema drift, official signing/notarization/release publication/updater readiness, and full production distribution remain outside that scoped proof. Do not claim bundled KataGo runtime parity, Fox/Yike full parity, full readboard parity, formal production release, native desktop interactive UX parity, Tauri WebView DOM parity, full native-dialog desktop release parity, full LegacyShell UI parity, full Java/Swing config migration parity, full capture/import/OCR parity, or full legacy parity until the corresponding desktop/runtime/release checks above are recorded with environment details.
