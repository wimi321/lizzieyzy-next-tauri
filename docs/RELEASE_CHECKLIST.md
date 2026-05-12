# Release Checklist

This checklist tracks release readiness for the LizzieYzy Next Tauri 2 + Rust + TypeScript workspace. It is not a statement that a public Tauri release has already shipped.

The existing Java/Swing maintenance line may have its own release process. For the Next workspace, do not publish or describe a release as ready until the checks below pass on the intended platform and the artifact set exists.

## Truth Sync Summary

Current state: scoped evidence is strong, but this is not fully complete and not a production release-ready claim. The central smoke gate currently reports `56 passed, 0 failed, 0 pending`, including scoped release-readiness preflight evidence, scoped macOS installed-app evidence, scoped Windows/Linux unsigned installed-app evidence, scoped SGF/KataGo/readboard/provider/config evidence, and strict false boundaries. Those PASS results do not replace signing, notarization, updater readiness, official release publication, clean-machine production release testing, real Fox/Yike account validation, arbitrary OCR/capture proof, full readboard parity, full Java/Swing config migration parity, full UI/layout/shortcut parity, or full legacy parity.

Use `docs/COMPLETION_AUDIT.md` as the user-facing completion summary. Release notes and handoffs must preserve the same scoped language.

## Release Readiness Rules

- Do not claim full legacy parity unless Fox/Yike/readboard, legacy settings, and advanced review workflows have explicit acceptance evidence.
- Do not claim Fox, Yike, or readboard live support in the Next app from offline contracts alone. Repository-level offline contract and runtime path evidence can be reported as implemented, but live support requires the environment smoke checks below.
- Do not claim production packaging is complete until platform artifacts are built and verified.
- Do not claim production release readiness while signing, notarization, updater readiness, official release publication, and clean-machine production release tests remain open.
- Do not claim alpha gate coverage is 100% while `scripts/smoke_user_flows.py --verbose` has failures or pending runtime/external gates.
- Do not claim LegacyShell main-menu parity while `View`, `Engine`, `Tools`, or `Help` entries are disabled-only placeholders instead of actionable, identifiable controls.
- Treat CI Node action runtime hygiene as validation-covered only; it does not replace signing, notarization, updater, publication, or installed-app release proof.
- Keep README, migration plan, architecture doc, and release notes aligned with the actual state.
- Every release candidate must include scaffold validation output.

## Required Automated Checks

From the repository root:

```bash
python3 scripts/validate_scaffold.py --verbose
python3 scripts/validate_release_assets.py --verbose
python3 scripts/validate_release_workflow.py --verbose
python3 scripts/smoke_user_flows.py --verbose
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

`scripts/validate_release_workflow.py --verbose` covers CI release workflow hygiene, including Node action runtime declarations for GitHub Actions. This is scoped validation evidence only; it is not signing/notarization, updater readiness, official release publication, Windows/Linux installed-app proof, provider/readboard/OCR parity, or full legacy parity.
CI should not run the GUI runtime collector. `scripts/smoke_user_flows.py` validates the committed macOS evidence JSON schema and semantics, including the two-launch save/reopen proof fields.
CI may run `scripts/smoke_desktop_sgf_editing_ux.py --check-only` or rely on `scripts/smoke_user_flows.py` to validate committed `docs/qa/desktop-sgf-editing-ux-smoke-macos.json`; this scoped evidence records source-surface/source-visible desktop SGF editing UX fields and committed Tauri runtime-chain coverage, but explicitly keeps `collectionMethod=source_static_plus_tauri_runtime_chain`, `runtimeDomObserved=false`, `screenshotObserved=false`, and `nativeDialogClickCovered=false`.
CI validates `docs/qa/desktop-ui-click-smoke-macos.json` through `scripts/smoke_user_flows.py`; the scoped gate requires browser DOM observation, screenshot observation, click observation, multiple SHA-256 screenshot records with stable non-local paths, clicked controls, visible assertions, and boundaries with `nativeFileDialogCovered=false` and `tauriWebviewDomObserved=false` unless explicit Tauri WebView proof is recorded. The same evidence must include `legacyShellMenuActionSmoke` for scoped browser-rendered LegacyShell menu actions, active targets, visible assertions, and boundaries that keep OS-native menu proof, full shortcut/layout parity, native dialogs, and Tauri WebView DOM proof out of scope.
CI validates `docs/qa/native-menu-shortcut-smoke-macos.json` through `scripts/smoke_user_flows.py`; the scoped gate requires schema `lizzieyzy.native-menu-shortcut-smoke.v1`, status `pass`, platform `macos`, `nativeMenuSurface=true`, `nativeMenuEventBridge=true`, `keyboardShortcutSurface=true`, `actionIdsAligned=true`, `inputEditingSafe=true`, and explicit false boundaries for full shortcut parity, full legacy menu parity, WebView DOM proof, full OS-native menu parity, release publication, production signing, notarization, provider/readboard/OCR coverage, and Windows/Linux coverage.
CI validates `docs/qa/tauri-window-runtime-smoke-macos.json` through `scripts/smoke_user_flows.py`; the scoped gate requires Tauri runtime observation, Tauri window screenshot observation, no browser fallback, no WebView DOM click coverage, no native dialog click coverage, stable non-local screenshot paths with SHA-256 hashes, valid source runtime evidence schema/status, and save/reopen semantic proof.
CI validates `docs/qa/tauri-webview-dom-click-smoke-macos.json` through `scripts/smoke_user_flows.py`; the scoped gate requires schema `lizzieyzy.tauri-webview-dom-click-smoke.v1`, status `pass`, platform `macos`/`darwin`, `tauriRuntimeObserved=true`, `webviewDomObserved=true`, `webviewClickObserved=true`, `browserFallbackUsed=false`, required runtime/DOM/click/visible-target/boundary checks, at least four clicked controls, at least four visible target assertions, and false boundaries for full layout parity, full shortcut parity, full legacy parity, release parity, and OCR capture parity.
CI validates `docs/qa/legacy-layout-parity-smoke-macos.json` through `scripts/smoke_user_flows.py` when present; the scoped gate requires schema `lizzieyzy.legacy-layout-parity-smoke.v1`, status `pass`, platform `macos`/`darwin`, stable screenshot paths and SHA-256 hashes for default review, SGF editing, KataGo analysis, provider/readboard, and engine/preferences, at least three viewports including `1280x840`, narrow desktop, and short window, visible assertions for board, toolbar/menu, SGF tree, annotation/comment/properties, analysis panel, winrate, candidates/PV, cache/status, provider/readboard, and engine/preferences, no critical overlap/clipping, and false boundaries for pixel-perfect parity, full legacy UI parity, full shortcut parity, release parity, OCR capture parity, and full legacy parity.
CI should not run the live KataGo collectors either. `scripts/smoke_user_flows.py` validates committed `docs/qa/katago-live-smoke-macos.json` and `docs/qa/katago-tauri-runtime-smoke-macos.json`; the collectors require a real local KataGo binary, model, config, and, for the Tauri runtime smoke, a GUI-capable macOS runtime.
CI may run the repository-local runtime asset layout surface check. `runtime_asset_layout_surface` validates frontend/API wiring for bundled/runtime asset status and local asset configuration only; it does not prove large model bundling, installed-app bundled-engine launch, signing, notarization, or release inclusion.
CI should not run the readboard GUI/runtime collector. `scripts/smoke_user_flows.py` validates committed `docs/qa/readboard-tauri-runtime-smoke-macos.json` when present; the scoped gate requires macOS Tauri runtime startup, sidecar probe ready/unavailable states, protocol-line sync with `snapshotId`, board size, non-negative move number, stone count, and player-to-play, target-state-change sync with distinct before/after snapshots, changed stone count or move number, stable board size, `arbitrary_ocr_not_covered`, and `external_capture_not_covered` fields. `scripts/smoke_user_flows.py` also validates committed `docs/qa/readboard-image-import-smoke-macos.json` for scoped controlled image import MVP evidence and `docs/qa/readboard-image-ocr-corpus-smoke-macos.json` for scoped controlled image OCR corpus evidence only; those gates must keep full OCR/readboard/external capture parity claims false.
CI should not run the provider GUI/runtime collector. `scripts/smoke_user_flows.py` validates committed `docs/qa/provider-live-smoke-macos.json` when present; the scoped gate requires macOS Tauri runtime startup, controlled-network Yike and Fox fetches, typed provider failure modes, controlled HTTP request observation, explicit non-offline-parser-only evidence, and explicit scope fields showing real account login state, anti-bot stability, and service schema drift are not covered.
CI should not run platform packaging builds inside the repository smoke gate. `scripts/smoke_user_flows.py` validates committed `docs/qa/multiplatform-packaging-smoke.json` when present; the scoped gate requires macOS, Windows, and Linux artifact records, signing-state records, dev-server-absence checks, and SHA-256 checksums. This is not official signing/notarization or release publication proof.
CI validates `docs/qa/installed-macos-app-smoke.json` through `scripts/smoke_user_flows.py`; the scoped gate requires macOS `.app` bundle exists metadata with size and SHA-256 hash, installed app launch success, window observation, screenshot observation with stable non-local paths and SHA-256 hashes, dev-server absence, explicit `productionSigned=false`, `notarized=false`, `releasePublished=false`, and exit/terminate success. This is not signed/notarized release, updater, Windows/Linux installed-app, native dialog, WebView DOM, OCR/capture, provider/readboard, or full parity proof.
Windows/Linux installed-app smoke is recorded as per-platform scoped evidence at `docs/qa/windows-unsigned-installed-app-smoke.json` and `docs/qa/linux-unsigned-installed-app-smoke.json` from `wimi321/lizzieyzy-next-tauri` run `25764095000` artifacts `release-dry-run-Windows` and `release-dry-run-Linux`. The central smoke gate passes for artifact hash/size, launch command, process/window observation, dev-server absence, exit/terminate success, display mode, and explicit false boundaries for production signing, updater readiness, official release publication, Windows/Linux installed-app parity, full release parity, and full legacy parity.
CI validates `docs/qa/native-desktop-sgf-workflow-macos.json` through `scripts/smoke_user_flows.py`; the scoped gate requires schema `lizzieyzy.native-desktop-sgf-workflow.v1`, status `pass`, platform `macos`/`darwin`, app mode `tauri-dev` or `packaged-macos-app`, explicit collection method, native open/save dialog step records with operator/method metadata, sanitized SGF paths, stable screenshot paths and SHA-256 hashes, persisted edit evidence, board/tree reopen invariants, and explicit false boundaries for WebView DOM automation, full automation when manual-assisted, full legacy parity, release publication, signing, notarization, Windows/Linux, OCR/capture, provider, and readboard claims. The recorded evidence passes as scoped manual-assisted native desktop SGF workflow proof and must not be described as full native desktop automation, WebView DOM proof, signed/notarized release proof, OCR/capture/provider/readboard proof, Windows/Linux installed-app proof, release publication, or full legacy parity.

Current alpha-gate status for the repository-local smoke gate:

- `python3 scripts/smoke_user_flows.py --verbose` currently reports `56 passed, 0 failed, 0 pending`; repository-local native SGF save/read-back refresh, existing-move edit surface evidence, scoped annotation UI/API evidence, scoped legacy import/capture helper surface evidence, scoped Desktop SGF Editing UX source-surface/runtime-chain evidence, scoped browser-rendered DOM/click/screenshot/menu-action evidence, scoped Tauri runtime/window screenshot evidence, scoped Tauri WebView DOM/click evidence, scoped legacy layout evidence, scoped installed macOS `.app` launch/window evidence, scoped Windows/Linux unsigned installed-app launch/window evidence from GitHub run `25764095000`, scoped manual-assisted native desktop SGF workflow evidence, scoped legacy config migration transactional/rollback safety surface evidence, scoped legacy config corpus migration evidence, scoped bundled/runtime asset layout surface evidence, scoped macOS local Tauri runtime UI evidence, scoped macOS live KataGo evidence, scoped KataGo review workflow UX resilience evidence, scoped live KataGo desktop workflow evidence, scoped macOS readboard runtime evidence, scoped readboard controlled image import MVP evidence, scoped controlled image OCR corpus evidence, scoped macOS provider controlled-network evidence, scoped multiplatform packaging smoke evidence, scoped release readiness preflight evidence, and CI Node action runtime hygiene validation are complete for their current gates; scoped macOS native menu/shortcut evidence is complete for its current gate. The legacy layout evidence remains scoped and keeps pixel-perfect parity, full legacy UI parity, shortcut parity, release parity, OCR capture parity, and full legacy parity false.
- The static `legacy_shell_menu_surface` check passes for the LegacyShell `View`, `Engine`, `Tools`, and `Help` menu entries, and `legacy_shell_menu_action_smoke` passes for scoped browser-rendered clicks that focus View/Candidates, View/Ownership, View/Policy, Engine/Profiles, Engine/Assets, Tools/Providers, Tools/Preferences, and Help/Backend status targets. This is not Tauri WebView DOM proof, OS-native menu proof, native dialog proof, full shortcut/layout parity, or full LegacyShell parity.
- The static `native_sgf_save_readback_surface` check passes for repository-local native SGF save/read-back refresh evidence: save writes through native SGF file I/O, reads the saved SGF back, and refreshes App parse/replay/tree/cache state from the read-back text. This is not real desktop GUI smoke proof.
- The static `sgf_existing_move_edit_surface` and `edit-existing-move` checks pass for repository-local existing-move edit surface evidence: existing SGF node edits are exposed through the command-backed edit surface and covered by repository-local wiring evidence. This is not real desktop GUI smoke proof.
- The static `sgf_annotation_surface` check passes for scoped SGF annotation persistence evidence: SgfAnnotationPanel exposes TR/SQ/CR/MA/SL/LB/AR/LN add/update/remove controls, App saves through `updateSgfNodeProperties`, and runtime smoke records `annotation_edit` add/update/remove semantics. This is not legacy capture/import, OCR, or external client/window capture proof.
- The static `legacy_import_capture_helper_surface` check passes for scoped legacy helper visibility: ProviderPanel exposes SGF/payload and protocol snapshot helper paths, and OCR/image plus external window/client capture helpers return structured recoverable unsupported state with no SGF import and no board replacement. This is not real OCR proof, real external client/window capture proof, or full legacy helper migration.
- The scoped `desktop_sgf_editing_ux_smoke` evidence passes for source/static desktop SGF editing UX surface plus committed Tauri runtime-chain coverage: source-visible LegacyShell, toolbar/menu controls, tree panel, annotation editor, selected-node UX state, dirty/saved status, tree navigation, comment/property/annotation, append/edit/reorder/delete, and save/readback/reopen. This is not runtime-rendered DOM/screenshot/click proof, native dialog click proof, OCR, external client/window capture, or full legacy parity proof.
- The `desktop_ui_click_smoke` and `legacy_shell_menu_action_smoke` gates pass for scoped browser-rendered DOM/click/screenshot/menu-action evidence at `docs/qa/desktop-ui-click-smoke-macos.json`. They must not be described as Tauri WebView DOM, OS-native menu, native file dialog, full shortcut/layout parity, or full parity proof.
- The `native_menu_shortcut_smoke` gate passes for scoped macOS OS-native menu and keyboard shortcut surface evidence at `docs/qa/native-menu-shortcut-smoke-macos.json`. It must not be described as full shortcut parity, full legacy menu parity, WebView DOM proof, release/signing/notarization proof, provider/readboard/OCR proof, Windows/Linux parity, or full legacy parity.
- The `tauri_window_runtime_smoke` gate passes for scoped Tauri runtime/window screenshot evidence at `docs/qa/tauri-window-runtime-smoke-macos.json`. It must not be described as WebView DOM click proof, native dialog proof, installed packaged app/signing/release proof, OCR/capture proof, provider/readboard parity, or full legacy parity proof.
- The `tauri_webview_dom_click_smoke` gate passes for scoped Tauri WebView DOM/click evidence at `docs/qa/tauri-webview-dom-click-smoke-macos.json`. It must not be described as full layout parity, full shortcut parity, full legacy parity, release parity, OCR capture parity, native dialog proof, or full release-target desktop parity.
- The `installed_macos_app_smoke` gate passes for scoped macOS packaged app launch/window evidence at `docs/qa/installed-macos-app-smoke.json`. It must not be described as signed/notarized release proof, updater proof, Windows/Linux installed-app proof, native dialog proof, WebView DOM proof, OCR/capture proof, provider/readboard parity, or full legacy parity proof.
- The static `legacy_config_migration_surface` check passes for repository-local legacy Java/Swing config migration safety-surface evidence: backend wrappers expose structured apply status/error/written-label/transactional/no-write/rollback fields, App keeps failed applies non-applied and avoids reload, and PreferencesPanel exposes migration safety, written target labels, rollback paths, and rollback errors. `legacy_config_corpus_migration_smoke` also passes for scoped repository corpus evidence at `docs/qa/legacy-config-corpus-migration-smoke.json`: at least eight fixture records cover minimal, full-engine, multi/conflict, UI review, Windows path, Unix path, Unicode/space, malformed partial, and unknown/deprecated classes, with preview no-write, intended apply targets, preserved existing Next settings, invalid no-write, unsupported-key warnings, deterministic duplicate/conflict handling, rollback metadata, and false boundaries for full historical config parity, real-user config smoke, external account needs, release parity, and full legacy parity. This is not real-user migration proof, real rollback-failure exercise, or full Java/Swing config parity.
- The static `runtime_asset_layout_surface` check passes for repository-local bundled/runtime asset layout surface evidence: frontend backend wrappers call the existing Tauri layout commands, and EngineSetupPanel displays bundled/runtime asset status while preserving local engine/model/config fields. This is not large-model bundling proof, installed-app bundled-engine launch proof, signing/notarization proof, or release inclusion proof.
- `docs/qa/tauri-runtime-ui-smoke-macos.json` is the macOS local runtime evidence target from `scripts/smoke_tauri_runtime_ui.py --evidence-out docs/qa/tauri-runtime-ui-smoke-macos.json`. The repository gate requires schema `lizzieyzy.tauri-runtime-ui-smoke.v1`, status `pass`, platform `macos`, all required check names passing including `annotation_edit`, top-level `firstLaunch`/`secondLaunch`/`saveReopenProof`, and semantic `secondLaunch`, `reopen`, and `afterReopen` fields proving save/reopen after a second launch.
- `docs/qa/desktop-sgf-editing-ux-smoke-macos.json` is the scoped Desktop SGF Editing UX evidence target from `scripts/smoke_desktop_sgf_editing_ux.py --evidence-out docs/qa/desktop-sgf-editing-ux-smoke-macos.json`. The repository gate requires schema `lizzieyzy.desktop-sgf-editing-ux-smoke.v1`, status `pass`, platform `macos`, `collectionMethod=source_static_plus_tauri_runtime_chain`, `runtimeDomObserved=false`, `screenshotObserved=false`, required source/static UI surface checks, source-visible fields for LegacyShell, toolbar/menu controls, tree panel, annotation editor, selected-node UX state, dirty/saved status, and explicit `nativeDialogClickCovered=false`.
- `docs/qa/desktop-ui-click-smoke-macos.json` is the scoped browser-rendered desktop UI click evidence target from Worker-1. The repository gate requires schema `lizzieyzy.desktop-ui-click-smoke.v1`, status `pass`, platform `macos`, `browserDomObserved=true`, `screenshotObserved=true`, `clickObserved=true`, at least two screenshot records with stable non-local paths and SHA-256 hashes, clicked controls, visible assertions, and boundaries with `nativeFileDialogCovered=false`; `tauriWebviewDomObserved` must remain false unless explicit proof is recorded. The `legacy_shell_menu_action_smoke` gate also requires `legacyShellMenuActionSmoke.status=pass`, clicked controls, active targets, visible assertions, and false boundaries for native file dialog, Tauri WebView DOM, OS-native menu, full shortcut parity, full layout parity, and full legacy parity.
- `docs/qa/native-menu-shortcut-smoke-macos.json` is the scoped macOS OS-native menu and keyboard shortcut evidence target. The repository gate requires schema `lizzieyzy.native-menu-shortcut-smoke.v1`, status `pass`, platform `macos`, native menu surface, native-menu event bridge, keyboard shortcut surface, action-id alignment, input-editing safety, and strict false boundaries for full shortcut parity, full legacy menu parity, WebView DOM proof, full OS-native menu parity, release publication, production signing, notarization, provider/readboard/OCR coverage, and Windows/Linux coverage.
- `docs/qa/tauri-window-runtime-smoke-macos.json` is the scoped Tauri desktop window/runtime screenshot evidence target from Worker-1. The repository gate requires schema `lizzieyzy.tauri-window-runtime-smoke.v1`, status `pass`, platform `macos`/`darwin`, `tauriRuntimeObserved=true`, `tauriWindowScreenshotObserved=true`, `browserFallbackUsed=false`, `webviewDomClickCovered=false`, `nativeDialogClickCovered=false`, at least one screenshot record with a stable non-local path and SHA-256 hash, source runtime evidence with schema `lizzieyzy.tauri-runtime-ui-smoke.v1` and status `pass`, and save/reopen semantic proof.
- `docs/qa/tauri-webview-dom-click-smoke-macos.json` is the scoped Tauri WebView DOM/click evidence target. The repository gate requires schema `lizzieyzy.tauri-webview-dom-click-smoke.v1`, status `pass`, platform `macos`/`darwin`, `tauriRuntimeObserved=true`, `webviewDomObserved=true`, `webviewClickObserved=true`, `browserFallbackUsed=false`, required checks for runtime startup, WebView DOM observation, WebView click observation, visible targets, browser fallback exclusion, and scope boundaries, at least four clicked controls, at least four visible assertions, and false boundaries for full layout parity, full shortcut parity, full legacy parity, release parity, and OCR capture parity.
- `docs/qa/legacy-layout-parity-smoke-macos.json` is the recorded scoped legacy layout evidence target. The repository gate requires schema `lizzieyzy.legacy-layout-parity-smoke.v1`, status `pass`, platform `macos`/`darwin`, screenshots for default review, SGF editing, KataGo analysis, provider/readboard, and engine/preferences with stable non-local paths and SHA-256 hashes, at least three viewports including `1280x840`, narrow desktop, and short window, visible assertions for the primary board/menu/tree/editing/analysis/provider/engine surfaces, no critical overlap or clipping, and false parity/release/OCR boundaries.
- `docs/qa/installed-macos-app-smoke.json` is the scoped installed macOS `.app` launch/window evidence target from Worker-1. The repository gate requires schema `lizzieyzy.installed-macos-app-smoke.v1`, status `pass`, platform `macos`/`darwin`, app bundle exists metadata with size and SHA-256 hash, `launched=true`, `windowObserved=true`, `screenshotObserved=true`, `devServerAbsent=true`, `productionSigned=false`, `notarized=false`, `releasePublished=false`, at least one stable non-local screenshot path with SHA-256 hash, and exit/terminate success.
- `docs/qa/windows-unsigned-installed-app-smoke.json` and `docs/qa/linux-unsigned-installed-app-smoke.json` are recorded scoped unsigned installed-app smoke evidence from `wimi321/lizzieyzy-next-tauri` run `25764095000` artifacts `release-dry-run-Windows` and `release-dry-run-Linux`. They record each platform's artifact path/hash/size, launch command, process/window observation, dev-server absence, exit/terminate success, and display mode. This is release-dry-run installed-app smoke only; it is not signing, updater readiness, official release publication, Windows/Linux installed-app parity, full release parity, or full legacy parity.
- `docs/qa/native-desktop-sgf-workflow-macos.json` is the recorded scoped native desktop SGF open/edit/save/reopen workflow evidence. The repository gate requires schema `lizzieyzy.native-desktop-sgf-workflow.v1`, status `pass`, platform `macos`/`darwin`, `appMode` of `tauri-dev` or `packaged-macos-app`, an explicit collection method, all required checks passing, concrete native open/save dialog records with operator/method/SGF path/screenshot metadata, stable screenshot paths and SHA-256 hashes, persisted edit evidence, board/tree reopen invariants, sanitized SGF/screenshot/app/log paths, and boundaries that exclude WebView DOM automation, full automation for manual-assisted evidence, full legacy parity, release publication, signing, notarization, Windows/Linux installed-app, OCR/capture, provider, and readboard claims.
- `docs/qa/katago-live-smoke-macos.json` is the macOS live KataGo CLI evidence target from `scripts/smoke_katago_live.py --engine ... --model ... --config ... --evidence-out docs/qa/katago-live-smoke-macos.json`. The repository gate requires schema `lizzieyzy.katago-live-smoke.v1`, status `pass`, platform `macos`, engine/model/config metadata, and passing checks for engine assets, version probe, one-position analysis, batch analysis, and stderr capture.
- `docs/qa/katago-tauri-runtime-smoke-macos.json` is the macOS Tauri runtime KataGo evidence target from `scripts/smoke_tauri_katago_live.py --engine ... --model ... --config ... --evidence-out docs/qa/katago-tauri-runtime-smoke-macos.json`. The repository gate requires schema `lizzieyzy.katago-tauri-runtime-smoke.v1`, status `pass`, platform `macos`, and passing runtime checks for startup, assets, analyze-once, analyze-game, and start/cancel.
- `docs/qa/katago-review-workflow-ux-smoke-macos.json` is the scoped KataGo review workflow UX resilience evidence target. The repository gate requires schema `lizzieyzy.katago-review-workflow-ux-smoke.v1`, status `pass`, platform `macos`, `collectionMethod=source_static_plus_stubbed_ui_flow`, source facts for visible progress/current/total/job id/session, cancel/restart, cache-hit restore source, engine failure messaging, and stale-analysis guard, true proof fields for progress/cancel/restart/cache/failure/stale/source validation, `liveKataGoObserved=false`, and false boundaries for full legacy analysis parity, release/signing/notarization, provider/readboard/OCR, and Windows/Linux.
- `docs/qa/katago-live-desktop-workflow-smoke-macos.json` is the scoped live KataGo desktop workflow evidence target. The repository gate requires schema `lizzieyzy.katago-live-desktop-workflow-smoke.v1`, status `pass`, platform `macos`/`darwin`, `liveKataGoObserved=true`, `browserFallbackUsed=false`, required checks for runtime startup, engine assets, analysis progress, cancel, restart after cancel, analysis complete, cache save, cache-hit restore, stale-cache prevention, engine failure, browser fallback exclusion, and scope boundaries. Cache-hit restore must include frame, candidate, and winrate evidence. Boundaries must keep `fullLegacyAnalysisParity=false`, `providerReadboardParity=false`, `releaseParity=false`, and `arbitraryOcrParity=false`.
- `docs/qa/readboard-tauri-runtime-smoke-macos.json` is the scoped macOS Tauri runtime readboard evidence target from the readboard runtime smoke runner. The repository gate requires schema `lizzieyzy.readboard-tauri-runtime-smoke.v1`, status `pass`, platform `macos`, and passing runtime checks for startup, sidecar probe ready/unavailable states, protocol-line sync with snapshot id, board size, move number, stone count, and player-to-play, target-state-change sync with distinct before/after snapshot ids, changed stone count or move number, stable board size, `arbitrary_ocr_not_covered`, and `external_capture_not_covered`.
- `docs/qa/readboard-image-import-smoke-macos.json` is the scoped controlled readboard image import MVP evidence target. The repository gate requires schema `lizzieyzy.readboard-image-import-smoke.v1`, status `pass`, platform `macos`, `collectionMethod=controlled_fixture_image_import`, `imagePathImportVerified=true`, `imageBase64ImportVerified=true`, invalid image rejection, non-board image rejection, snapshot/board-size/stone-count/to-play verification, protocol regression verification, repo-relative image artifact existence, matching `imageSha256`, matching `imageBytes`, `fullOcrParity=false`, and `externalCaptureCovered=false`. This is not arbitrary screenshot OCR, external window/client capture, or full legacy OCR parity.
- `docs/qa/readboard-image-ocr-corpus-smoke-macos.json` is the scoped controlled readboard image OCR corpus evidence target. The repository gate requires schema `lizzieyzy.readboard-image-ocr-corpus-smoke.v1`, status `pass`, platform `macos`, `collectionMethod=controlled_fixture_image_ocr_corpus`, fixture manifest paths that are repo-relative and sanitized with matching SHA-256 and `sizeBytes`, path/base64 equivalence, invalid/non-board/truncated rejection, board-size and stone-count coverage, hash invariants, external capture unsupported contract, and false boundaries for `fullOcrParity`, `externalWindowCaptureCovered`, `realClientCaptureCovered`, and `fullReadboardParity`. This is not arbitrary screenshot OCR, external window/client capture, real client capture, full legacy OCR parity, or full readboard parity.
- `docs/qa/provider-live-smoke-macos.json` is the scoped macOS controlled-network Tauri provider evidence target from the provider runtime smoke runner. The repository gate requires schema `lizzieyzy.provider-live-smoke.v1`, status `pass`, platform `macos`, and passing runtime checks for startup, controlled-network Yike fetch, controlled-network Fox fetch, typed failure modes, controlled request observation, offline parser exclusion, and explicit external account/service scope limits.
- `docs/qa/multiplatform-packaging-smoke.json` is the scoped packaging evidence target from the multiplatform packaging smoke runner. The repository gate requires schema `lizzieyzy.multiplatform-packaging-smoke.v1`, status `pass`, and passing checks for macOS, Windows, and Linux artifacts, signing-state recording, dev-server absence, and SHA-256 checksums.
- The repository smoke gate currently reports `56 passed, 0 failed, 0 pending`, including scoped controlled readboard image OCR corpus evidence, scoped Windows/Linux unsigned installed-app evidence at `docs/qa/windows-unsigned-installed-app-smoke.json` and `docs/qa/linux-unsigned-installed-app-smoke.json`, and scoped release readiness preflight evidence. Signed/notarized release proof, updater readiness, official release publication, store distribution, Windows/Linux signed/release installed-app proof, full production release validation, bundled large-model parity, full Tauri WebView layout/shortcut/release parity, full legacy UI/layout parity, full legacy analysis parity, arbitrary screenshot OCR, external window/client capture, real client capture, provider/readboard parity, full legacy OCR parity, full readboard parity, and full legacy parity remain outside the existing recorded proof.
- The scoped legacy import/capture helper surface and scoped controlled image import MVP do not change release readiness for arbitrary screenshot OCR or external capture. External window/client capture, arbitrary screenshot OCR, and full legacy helper/OCR parity remain external gates.
- This status must be recorded with the scoped evidence boundaries in release notes and handoff material; do not present it as formal release publication or full parity.

Frontend build:

```bash
cd apps/desktop
npm ci
npm run build
```

Tauri build, once release packaging is in scope:

```bash
cd apps/desktop
npm run tauri:build
```

If `npm run tauri:build` is not being run for the current handoff, document that packaging was not validated.

Release engineering dry-run:

```bash
cd apps/desktop
npm run tauri:build -- --no-bundle --ci --no-sign
```

The GitHub Actions dry-run workflow is `.github/workflows/release-dry-run.yml`. It can be triggered manually or by pushing a `v*` tag, validates macOS/Linux/Windows setup, runs release preflight, and uploads dry-run summaries without creating a GitHub release.

Provider/readboard acceptance:

- Provider contract tests must run through the Rust workspace test gate, with the exact package or filter recorded in the handoff. A zero-test focused filter is not evidence.
- Provider runtime path checks must record whether `provider_fetch_yike` and `provider_fetch_fox` were exercised offline only, against a controlled-network smoke server, or against real services.
- Fox runtime path checks must cover the supported `chessid`, `uid`, and `user_name` command shapes.
- Readboard domain tests must run through the Rust workspace test gate, with `readboard_sidecar_probe` and `readboard_sidecar_sync_snapshot` path checks recorded separately.
- ProviderPanel is the expected UI surface for provider fetch, readboard probe, and readboard sync controls. If the controls are absent in a candidate, mark that UI path as pending.
- Offline provider/readboard contracts and runtime path checks are not the same as live Fox/Yike external-network or readboard sidecar validation.

## Manual Desktop Smoke

Run under the native desktop runtime:

```bash
cd apps/desktop
npm run tauri:dev
```

Record the OS, CPU architecture, KataGo version, model path, config path, and whether the engine is bundled or local.

For the scripted macOS local runtime UI evidence, run from the repository root:

```bash
python3 scripts/smoke_tauri_runtime_ui.py --evidence-out docs/qa/tauri-runtime-ui-smoke-macos.json
python3 scripts/smoke_desktop_sgf_editing_ux.py --evidence-out docs/qa/desktop-sgf-editing-ux-smoke-macos.json
python3 scripts/smoke_user_flows.py --verbose
```

Pass: the runtime evidence JSON is sanitized, has status `pass`, includes semantic append/edit/reorder/delete SGF checks, has explicit two-launch save/reopen proof through `secondLaunch`, `reopen`, and `afterReopen`; the Desktop SGF Editing UX evidence records source-surface/source-visible LegacyShell, toolbar/menu, tree panel, annotation editor, selected-node state, dirty/saved status, runtime-chain coverage, `collectionMethod=source_static_plus_tauri_runtime_chain`, `runtimeDomObserved=false`, `screenshotObserved=false`, and `nativeDialogClickCovered=false`; and `smoke_user_flows.py` reports both `ui_tauri_runtime_smoke` and `desktop_sgf_editing_ux_smoke` as PASS. This is macOS local scoped runtime-chain plus source/static UX evidence only; it is not runtime-rendered DOM/screenshot/click proof, native file dialog/manual release proof, full legacy parity, live KataGo/provider/readboard validation, or multiplatform packaging proof.

For the scoped browser-rendered desktop UI click evidence, validate the committed JSON with:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `desktop_ui_click_smoke` reports PASS only when the committed evidence proves browser DOM observation, screenshots with stable non-local paths and SHA-256 hashes, clicked controls, and visible assertions while keeping `nativeFileDialogCovered=false` and `tauriWebviewDomObserved=false` unless explicit Tauri WebView proof is recorded. `legacy_shell_menu_action_smoke` reports PASS only when the same evidence proves browser-rendered LegacyShell menu clicks for View/Candidates, View/Ownership, View/Policy, Engine/Profiles, Engine/Assets, Tools/Providers, Tools/Preferences, and Help/Backend status with matching active targets and visible target selectors. This is not native file dialog, OS-native menu, Tauri WebView DOM, full shortcut/layout parity, or full parity proof.

For the scoped macOS OS-native menu and keyboard shortcut evidence, validate the committed JSON with:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `native_menu_shortcut_smoke` reports PASS only when the committed evidence proves scoped macOS native menu surface, native-menu event bridge, keyboard shortcut surface, action-id alignment, and input-editing safety while keeping full shortcut parity, full legacy menu parity, WebView DOM proof, full OS-native menu parity, release publication, production signing, notarization, provider/readboard/OCR coverage, and Windows/Linux coverage false. This is not full shortcut parity, full legacy menu parity, Tauri WebView DOM proof, release proof, provider/readboard/OCR proof, Windows/Linux parity, or full legacy parity.

For the scoped Tauri desktop window/runtime screenshot evidence, validate the committed JSON with:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `tauri_window_runtime_smoke` reports PASS only when the committed evidence proves Tauri runtime observation, Tauri window screenshot observation, stable non-local screenshot paths with SHA-256 hashes, source runtime evidence schema/status, and save/reopen semantic proof while keeping `browserFallbackUsed=false`, `webviewDomClickCovered=false`, and `nativeDialogClickCovered=false`. This is not WebView DOM click proof, native dialog proof, installed packaged app/signing/release proof, OCR/capture proof, provider/readboard parity, or full legacy parity proof.

For the scoped Tauri WebView DOM/click evidence, validate the committed JSON with:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `tauri_webview_dom_click_smoke` reports PASS only when the committed evidence proves Tauri runtime observation, WebView DOM observation, WebView click observation, at least four clicked controls, at least four visible target assertions, browser fallback exclusion, and scope boundaries while keeping full layout parity, full shortcut parity, full legacy parity, release parity, and OCR capture parity false. This is not native dialog proof, full release-target desktop parity, full layout/shortcut parity, OCR/capture parity, or full legacy parity proof.

For the scoped installed macOS `.app` launch/window evidence, validate the committed JSON with:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `installed_macos_app_smoke` reports PASS only when the committed evidence proves app bundle existence metadata, app size/hash, installed `.app` launch, window observation, screenshot observation with stable non-local path and SHA-256 hash, dev-server absence, and exit/terminate success while keeping `productionSigned=false`, `notarized=false`, and `releasePublished=false`. This is not signed/notarized release proof, updater proof, Windows/Linux installed-app proof, native dialog proof, WebView DOM proof, OCR/capture proof, provider/readboard parity, or full legacy parity proof.

For the scoped native desktop SGF open/edit/save/reopen workflow evidence, validate the committed JSON with:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `native_desktop_sgf_workflow` reports PASS only when the committed evidence proves the app started, native open dialog, SGF open, edit operations, save/Save As, reopened saved SGF, persisted edits, board/tree reopen invariants, screenshot records, sanitized paths, and scope boundaries while keeping WebView DOM automation, full automation for manual-assisted evidence, full legacy parity, release publication, production signing, notarization, Windows/Linux, OCR/capture, provider, and readboard coverage claims false. This is not full native desktop automation, Tauri WebView DOM proof, signed/notarized release proof, OCR/capture/provider/readboard proof, or full legacy parity.

For the macOS live KataGo evidence, run from the repository root:

```bash
python3 scripts/smoke_katago_live.py --engine /path/to/katago --model /path/to/model.bin.gz --config /path/to/analysis.cfg --evidence-out docs/qa/katago-live-smoke-macos.json
python3 scripts/smoke_tauri_katago_live.py --engine /path/to/katago --model /path/to/model.bin.gz --config /path/to/analysis.cfg --evidence-out docs/qa/katago-tauri-runtime-smoke-macos.json
python3 scripts/smoke_user_flows.py --verbose
```

Pass: both live evidence JSON files are sanitized and have status `pass`; the CLI evidence records one-position and batch `katago analysis` responses, and the Tauri evidence records runtime startup, assets, analyze-once, analyze-game, and start/cancel. The scoped UX resilience evidence is separately sanitized with `liveKataGoObserved=false` and proves only source-static plus stubbed UI-flow behavior for progress, cancel/restart, cache restore, engine failure message, and stale-analysis guard. The scoped live desktop workflow evidence is separately validated when `docs/qa/katago-live-desktop-workflow-smoke-macos.json` is recorded; it must prove live progress, cancel/restart, completion, cache save, cache-hit restore with frame/candidate/winrate evidence, stale-cache prevention, engine failure observation, no browser fallback, and false full-analysis/provider/readboard/release/OCR boundaries. `smoke_user_flows.py` reports `katago_live_smoke`, `katago_review_workflow_ux_smoke`, and `katago_live_desktop_workflow_smoke` as PASS only after their respective evidence files pass. This is scoped macOS local KataGo evidence only; it is not full legacy analysis parity, provider/readboard parity, release parity, arbitrary OCR parity, bundled-engine proof, or multiplatform packaging proof.

For the scoped bundled/runtime asset layout surface evidence, run:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `runtime_asset_layout_surface` reports PASS, proving the frontend can display bundled/runtime asset layout status from the Tauri layout commands and still exposes local engine, model, config, working directory, visits, save profile, and `Check assets` configuration. Large KataGo models are not bundled by this repository. Installed-app bundled engine launch, release artifact inclusion, signing, and notarization remain separate release gates.

For the scoped macOS readboard runtime evidence, run the readboard Tauri runtime smoke collector and then:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `docs/qa/readboard-tauri-runtime-smoke-macos.json` is sanitized, has schema `lizzieyzy.readboard-tauri-runtime-smoke.v1`, status `pass`, platform `macos`, and includes `runtime_started`, `sidecar_probe_ready`, `sidecar_probe_unavailable`, `protocol_line_sync`, `target_state_change_sync`, `arbitrary_ocr_not_covered`, and `external_capture_not_covered`. The protocol check must include `snapshotId`, `boardSize`, `moveNumber`, `stoneCount`, and `toPlay`; the target-change check must include distinct before/after snapshot ids, changed stone count or move number, and `boardSizeStable`; the arbitrary/external boundary checks must explicitly mark arbitrary OCR and external window/client capture as not covered. `docs/qa/readboard-image-import-smoke-macos.json` is also sanitized and validates controlled image path/base64 import, invalid/non-board rejection, snapshot fields, protocol regression, and the checked PNG artifact with `fullOcrParity=false` and `externalCaptureCovered=false`. `docs/qa/readboard-image-ocr-corpus-smoke-macos.json` validates the scoped controlled image OCR corpus manifest, artifact SHA/size checks, path/base64 equivalence, invalid/non-board/truncated rejection, board-size/stone-count coverage, hash invariants, unsupported external capture contract, and false full OCR/readboard/external-capture boundaries. `smoke_user_flows.py` reports `readboard_live_smoke`, `readboard_image_import_smoke`, and `readboard_image_ocr_corpus_smoke` as PASS only when those evidence files are present and semantically valid. This is scoped macOS Tauri runtime evidence for probe/protocol behavior plus scoped controlled image import/corpus evidence; it is not arbitrary screenshot OCR, real external client/window capture proof, full legacy OCR parity, full readboard parity, or multiplatform packaging proof.

For the scoped macOS provider controlled-network evidence, run the provider Tauri runtime smoke collector and then:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `docs/qa/provider-live-smoke-macos.json` is sanitized, has schema `lizzieyzy.provider-live-smoke.v1`, status `pass`, platform `macos`, and includes `runtime_started`, `yike_controlled_fetch`, `fox_controlled_fetch`, `provider_failure_modes`, `controlled_network_observed`, `offline_not_counted_as_external_live`, and `external_account_scope`. The Yike check must use `networkMode: controlled_network`, a 2xx/3xx HTTP status, validated payload, non-negative result count, and `fixtureParserOnly: false`; the Fox check must use `networkMode: controlled_network`, a 2xx/3xx HTTP status, imported payload, positive move count, and `directHttpWarning: true`. This is scoped controlled-network Tauri provider evidence; it is not real Fox/Yike service parity, account login proof, anti-bot stability proof, or service schema drift proof.

For scoped legacy Java/Swing config migration transactional/rollback safety-surface and repository corpus evidence, verify the Preferences panel exposes the migration controls, confirm `docs/qa/legacy-config-corpus-migration-smoke.json`, and run:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `legacy_config_migration_surface` reports PASS, proving repository-local frontend/API wiring for legacy config path input, Preview, Apply, status, warnings, migrated fields, structured apply status/error, written target labels, transactional/no-write flags, rollback state, rollback paths/errors, and backend calls to `preview_legacy_config_migration`/`apply_legacy_config_migration`. `legacy_config_corpus_migration_smoke` reports PASS only when the scoped corpus evidence has schema `lizzieyzy.legacy-config-corpus-migration-smoke.v1`, status `pass`, at least eight fixtures, all required fixture classes, true no-write/apply/preserve/warn/conflict/rollback metadata fields, and false boundaries for full historical config parity, real-user config smoke, external account needs, release parity, and full legacy parity. This is scoped safety-surface plus repository corpus evidence; it is not real-user migration proof, real rollback-failure exercise, or a claim that every Java/Swing setting migrates.

For scoped multiplatform packaging smoke evidence, run the packaging smoke collector and then:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `docs/qa/multiplatform-packaging-smoke.json` is sanitized, has schema `lizzieyzy.multiplatform-packaging-smoke.v1`, status `pass`, and includes `macos_artifacts`, `windows_artifacts`, `linux_artifacts`, `signing_recorded`, `dev_server_absent`, and `checksums`. Each platform must record at least one artifact and signing state; `dev_server_absent` must be true for macOS, Windows, and Linux; checksums must include SHA-256 values for all three platforms. This is scoped packaging smoke evidence; it is not official signing/notarization proof, release publication proof, updater readiness proof, or full legacy parity.

### Required User-Facing Retest Before Local Release

Run this as one continuous user flow before release notes claim SGF editing, desktop runtime, KataGo, provider, or readboard support:

- Start the native desktop app with `npm run tauri:dev` or the packaged candidate, and record the exact build/commit.
- Open a real SGF through native file open, then open at least one fixture from `tests/golden`.
- Navigate the mainline and at least one branch; confirm board state, move number, comments, captures/pass moves where present, and variation selection update together.
- Edit a node comment and at least one node property through the intended UI or command-backed surface.
- Append a move or pass, delete a selected non-root node/subtree, and reorder sibling variations.
- Save or Save As, quit or restart the desktop runtime, reopen the saved SGF, and confirm comments, properties, annotations, branch order, move count, and replayed board state round-trip.
- Run a fake or controlled review path if a mock/fixture engine is the candidate evidence; label it as fake/controlled and do not count it as live KataGo.
- Run the KataGo external gate only with recorded binary, model, config, OS, and success/failure output.
- Run readboard/provider external gates only with recorded sidecar/provider environment; mark unavailable environments `SKIPPED` and keep claims limited to offline/runtime path evidence.

Pass: the user can complete the whole SGF edit/save/reopen path in the desktop runtime, and any KataGo/readboard/provider claims are backed by the matching external gate evidence.

### SGF Open

- Open an SGF through native file open.
- Also paste or load a fixture from `tests/golden`.
- Confirm board size, move count, players, komi/result where present, and replay positions.

Pass: the game loads without falling back to stale demo data.

### Engine Profile

- Create or update a profile with engine, model, config, optional working directory, and visits.
- Save it.
- Restart the app.
- Confirm the profile list and selected profile persist.
- Add a second profile and switch selection if multi-profile behavior is part of the candidate.

Pass: profile data survives restart in app data.

### Asset Check

- Run `Check assets`.
- Confirm engine, model, and config are present.
- Test one missing required path and confirm analysis is blocked with an actionable message.

Pass: asset checks distinguish present and missing required inputs.

### One-Position Analysis

- Select a mid-game move.
- Run one-position KataGo analysis.
- Confirm candidates, PV, winrate, score, ownership/policy-backed data paths, and markers update.

Pass: the app receives normalized analysis frames from KataGo JSONL and updates the review UI.

### Full-Game Analysis

- Run full-game analysis.
- Observe progress events.
- Confirm completion produces frames across the game and the winrate/candidate views update.

Pass: the batch job completes and validates response turns.

### Cancellation

- Start a full-game run with enough visits to observe progress.
- Cancel it.
- Confirm cancellation message appears and a subsequent analysis can start.

Pass: cancellation releases the active job and does not leave the UI permanently disabled.

### Cache Hit

- Complete an analysis run.
- Reopen or reparse the same SGF with the same profile/engine kind.
- Confirm cache status reports a hit and cached frames/problems load.

Pass: the SQLite analysis cache can be reused for the same game key.

### SGF Save

- Save or Save As the current SGF.
- Confirm the repository-local smoke gate has already passed `native_sgf_save_readback_surface`; this only proves save/read-back refresh wiring.
- Reopen the saved file.
- Confirm parse/replay and move count match expectations.

Pass: saved SGF is parseable and round-trips through native open.

### SGF Tree Editing

- Navigate from mainline into at least one variation and back.
- Edit a comment, a node property, and TR/SQ/CR/MA/SL/LB/AR/LN annotations on a non-root node.
- Append a child move or pass from the selected node.
- Delete a selected non-root node/subtree and confirm the parent/selection behavior is understandable.
- Reorder sibling variations and confirm the visible tree order changes.
- Save, restart the desktop runtime, reopen the SGF, and confirm comments, properties, annotations, appended/deleted nodes, variation order, and board replay persisted.

Pass: tree editing behaves as a user-visible desktop workflow, not only as repository command-surface evidence.

## Provider And Sidecar Manual Smoke

These checks are required before release notes claim live Fox, Yike, or readboard support. Mark them `SKIPPED` when the environment is unavailable and keep the release claim limited to offline contract/runtime path status.

### Yike Runtime Fetch

- Record Yike account/session type, network environment, provider endpoint or resource type, and app build.
- Fetch a real supported Yike resource through `provider_fetch_yike` from ProviderPanel or the intended test/debug harness.
- Confirm normalized DTOs match the fetched resource and are not stale fallback data.
- Repeat with missing/expired auth or blocked network.

Pass: real fetch succeeds when the environment is valid, and auth/network failures return structured errors.

### Fox Runtime Fetch

- Record Fox account/session or client prerequisites, target client state, network environment, and app build.
- Fetch or capture real supported Fox resources through `provider_fetch_fox` for `chessid`, `uid`, and `user_name`.
- Confirm normalized DTOs match the fetched/captured resource and are not stale fallback data.
- Repeat with unavailable client/session or blocked network.

Pass: real fetch/capture succeeds when prerequisites are valid, and unavailable-client/session/network failures return structured errors.

### readboard Sidecar Probe

- Record sidecar version, launch method, port/path, target client/window state, OS, and app build.
- Probe the sidecar through `readboard_sidecar_probe` while it is running.
- Probe again when the sidecar is stopped or unreachable.
- Confirm timeout handling by using an invalid port/path or blocked process if practical.

Pass: probe distinguishes ready, not running, incompatible, and timeout states.

### readboard Sync

- With the sidecar running, sync from a real target board state.
- Exercise protocol line sync through `readboard_sidecar_sync_snapshot`.
- Confirm board size, stone coordinates, move state, and player-to-play where available.
- Restart the sidecar or alter the target board state and sync again.

Pass: sync reflects the live board state and recovers cleanly after sidecar restart or target-state changes.

### Controlled Image Import MVP Boundary

- Validate the controlled image path and image base64 import evidence before claiming the MVP path.
- Confirm invalid images and non-board images are rejected recoverably.
- Confirm the resulting snapshot records board size, stone count, and player-to-play.
- Confirm `fullOcrParity=false` and `externalCaptureCovered=false`.

Pass: controlled board image import is scoped to the MVP evidence; arbitrary screenshot OCR, external window/client capture, and full legacy OCR parity remain pending.

### Failure Modes

- Exercise bad provider credentials/session, network loss, provider timeout, malformed provider payload, missing sidecar, sidecar crash, sidecar timeout, cancellation, and retry.
- Confirm logs and UI distinguish provider auth, provider network, sidecar process, sidecar protocol, Tauri command, engine, cache, and DTO normalization failures.

Pass: failures are explicit, recoverable where expected, and never reported as successful live provider/sidecar support.

## Packaging Checklist

When production packaging becomes in scope, verify:

- App identifier remains `org.lizzieyzy.next`.
- Frontend output is built from `apps/desktop/dist`.
- Required icons and metadata are present.
- `docs/qa/multiplatform-packaging-smoke.json` validates through `python3 scripts/smoke_user_flows.py --verbose` for scoped artifact/signing-state/dev-server/checksum evidence.
- `python3 scripts/validate_release_assets.py --verbose` passes.
- `.github/workflows/release-dry-run.yml` passes on macOS, Linux, and Windows.
- `.github/workflows/release.yml` is validated by `python3 scripts/validate_release_workflow.py --verbose`.
- A `v*` tag release produces macOS, Windows, and Linux assets plus checksum files.
- Missing signing secrets are reported as unsigned dry-run state, not treated as a publish failure.
- Bundled KataGo/runtime assets, if included, match documented paths.
- Large KataGo models are either intentionally excluded and documented, or included only with explicit artifact-size and license review.
- Any bundled engine starts from the installed app on each target platform before it is claimed in release notes.
- The app starts without a development server.
- Windows installer or portable package opens on a clean machine.
- macOS app handles Gatekeeper/signing/notarization according to the documented release policy.
- Linux package includes required runtime dependencies or clearly documents them.
- Logs and error messages distinguish UI errors, Tauri command errors, engine errors, and storage/cache errors.
- The full release process, secrets, artifact policy, and rollback plan are recorded in `docs/RELEASE_PROCESS.md`.
- GitHub Release notes include English and Chinese summaries, signing state, checksum guidance, and known limitations.

## Release Notes Guardrails

Release notes for the Next workspace should state:

- The exact release candidate or tag.
- The platform artifacts included.
- The validation commands run and their results.
- The manual smoke result, including OS and KataGo details.
- Known limitations.

Release notes should not state:

- that the Tauri app is a full replacement for the Java/Swing app,
- that Fox/Yike/readboard are migrated,
- that a platform package exists when it was not built,
- that cache/profile persistence covers every legacy setting.

## Handoff Template

Use this shape when handing off a release candidate:

```text
Candidate:
Commit:
Platform:
KataGo:
Model:
Config:

Automated checks:
- python3 scripts/validate_scaffold.py --verbose: PASS/FAIL
- python3 scripts/validate_release_assets.py --verbose: PASS/FAIL
- cargo fmt --all --check: PASS/FAIL/SKIPPED
- cargo clippy --workspace --all-targets -- -D warnings: PASS/FAIL/SKIPPED
- cargo test --workspace: PASS/FAIL/SKIPPED
- provider contract tests: PASS/FAIL/SKIPPED, package/filter:
- Yike runtime fetch: PASS/FAIL/SKIPPED, offline/live:
- Fox chessid fetch: PASS/FAIL/SKIPPED, offline/live:
- Fox uid fetch: PASS/FAIL/SKIPPED, offline/live:
- Fox user_name fetch: PASS/FAIL/SKIPPED, offline/live:
- readboard domain tests: PASS/FAIL/SKIPPED, package/filter:
- readboard sidecar probe: PASS/FAIL/SKIPPED, offline/live:
- readboard protocol line sync: PASS/FAIL/SKIPPED, offline/live:
- controlled image import MVP and OCR parity boundary: PASS/FAIL/SKIPPED:
- npm ci: PASS/FAIL/SKIPPED
- npm run build: PASS/FAIL/SKIPPED
- npm run tauri:build: PASS/FAIL/SKIPPED

Manual smoke:
- SGF open: PASS/FAIL
- SGF branch navigation: PASS/FAIL
- SGF comment/property/annotation edit: PASS/FAIL
- SGF append/delete/reorder: PASS/FAIL
- SGF save/restart/reopen round-trip: PASS/FAIL
- Engine profile persistence: PASS/FAIL
- Asset check: PASS/FAIL
- Fake/controlled review path: PASS/FAIL/SKIPPED, evidence type:
- One-position analysis: PASS/FAIL
- Full-game analysis: PASS/FAIL
- Cancel analysis: PASS/FAIL
- Cache hit: PASS/FAIL
- SGF save: PASS/FAIL
- Yike live fetch: PASS/FAIL/SKIPPED
- Fox chessid live fetch: PASS/FAIL/SKIPPED
- Fox uid live fetch: PASS/FAIL/SKIPPED
- Fox user_name live fetch: PASS/FAIL/SKIPPED
- readboard live probe: PASS/FAIL/SKIPPED
- readboard live protocol line sync: PASS/FAIL/SKIPPED
- controlled image import MVP and OCR parity boundary: PASS/FAIL/SKIPPED

Known limitations:
```
