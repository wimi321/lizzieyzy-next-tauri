# Release Checklist

This checklist tracks release readiness for the LizzieYzy Next Tauri 2 + Rust + TypeScript workspace. It is not a statement that a public Tauri release has already shipped.

The existing Java/Swing maintenance line may have its own release process. For the Next workspace, do not publish or describe a release as ready until the checks below pass on the intended platform and the artifact set exists.

## Release Readiness Rules

- Do not claim full legacy parity unless Fox/Yike/readboard, legacy settings, and advanced review workflows have explicit acceptance evidence.
- Do not claim Fox, Yike, or readboard live support in the Next app from offline contracts alone. Repository-level offline contract and runtime path evidence can be reported as implemented, but live support requires the environment smoke checks below.
- Do not claim production packaging is complete until platform artifacts are built and verified.
- Do not claim alpha gate coverage is 100% while `scripts/smoke_user_flows.py --verbose` has failures or pending runtime/external gates.
- Do not claim LegacyShell main-menu parity while `View`, `Engine`, `Tools`, or `Help` entries are disabled-only placeholders instead of actionable, identifiable controls.
- Keep README, migration plan, architecture doc, and release notes aligned with the actual state.
- Every release candidate must include scaffold validation output.

## Required Automated Checks

From the repository root:

```bash
python3 scripts/validate_scaffold.py --verbose
python3 scripts/validate_release_assets.py --verbose
python3 scripts/smoke_user_flows.py --verbose
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

CI should not run the GUI runtime collector. `scripts/smoke_user_flows.py` validates the committed macOS evidence JSON schema and semantics, including the two-launch save/reopen proof fields.
CI should not run the live KataGo collectors either. `scripts/smoke_user_flows.py` validates committed `docs/qa/katago-live-smoke-macos.json` and `docs/qa/katago-tauri-runtime-smoke-macos.json`; the collectors require a real local KataGo binary, model, config, and, for the Tauri runtime smoke, a GUI-capable macOS runtime.
CI should not run the readboard GUI/runtime collector. `scripts/smoke_user_flows.py` validates committed `docs/qa/readboard-tauri-runtime-smoke-macos.json` when present; the scoped gate requires macOS Tauri runtime startup, sidecar probe ready/unavailable states, protocol-line sync with `snapshotId`, board size, non-negative move number, stone count, and player-to-play, target-state-change sync with distinct before/after snapshots, changed stone count or move number, stable board size, explicit unsupported OCR boundary evidence with an image/OCR message, and explicit `external_client_not_covered` fields for OCR and external client/window capture.
CI should not run the provider GUI/runtime collector. `scripts/smoke_user_flows.py` validates committed `docs/qa/provider-live-smoke-macos.json` when present; the scoped gate requires macOS Tauri runtime startup, controlled-network Yike and Fox fetches, typed provider failure modes, controlled HTTP request observation, explicit non-offline-parser-only evidence, and explicit scope fields showing real account login state, anti-bot stability, and service schema drift are not covered.
CI should not run platform packaging builds inside the repository smoke gate. `scripts/smoke_user_flows.py` validates committed `docs/qa/multiplatform-packaging-smoke.json` when present; the scoped gate requires macOS, Windows, and Linux artifact records, signing-state records, dev-server-absence checks, and SHA-256 checksums. This is not official signing/notarization or release publication proof.

Current alpha-gate status for the repository-local smoke gate:

- `python3 scripts/smoke_user_flows.py --verbose` currently reports `26 passed, 0 failed, 0 pending`; repository-local native SGF save/read-back refresh, existing-move edit surface evidence, scoped macOS two-launch save/reopen runtime evidence, scoped macOS live KataGo evidence, scoped macOS readboard runtime evidence, scoped macOS provider controlled-network evidence, and scoped multiplatform packaging smoke evidence are complete for their current gates.
- The static `legacy_shell_menu_surface` check passes for the LegacyShell `View`, `Engine`, `Tools`, and `Help` menu entries, but this is not runtime UI proof that each entry reaches the expected surface.
- The static `native_sgf_save_readback_surface` check passes for repository-local native SGF save/read-back refresh evidence: save writes through native SGF file I/O, reads the saved SGF back, and refreshes App parse/replay/tree/cache state from the read-back text. This is not real desktop GUI smoke proof.
- The static `sgf_existing_move_edit_surface` and `edit-existing-move` checks pass for repository-local existing-move edit surface evidence: existing SGF node edits are exposed through the command-backed edit surface and covered by repository-local wiring evidence. This is not real desktop GUI smoke proof.
- `docs/qa/tauri-runtime-ui-smoke-macos.json` is the macOS local runtime evidence target from `scripts/smoke_tauri_runtime_ui.py --evidence-out docs/qa/tauri-runtime-ui-smoke-macos.json`. The repository gate requires schema `lizzieyzy.tauri-runtime-ui-smoke.v1`, status `pass`, platform `macos`, all required check names passing, top-level `firstLaunch`/`secondLaunch`/`saveReopenProof`, and semantic `secondLaunch`, `reopen`, and `afterReopen` fields proving save/reopen after a second launch.
- `docs/qa/katago-live-smoke-macos.json` is the macOS live KataGo CLI evidence target from `scripts/smoke_katago_live.py --engine ... --model ... --config ... --evidence-out docs/qa/katago-live-smoke-macos.json`. The repository gate requires schema `lizzieyzy.katago-live-smoke.v1`, status `pass`, platform `macos`, engine/model/config metadata, and passing checks for engine assets, version probe, one-position analysis, batch analysis, and stderr capture.
- `docs/qa/katago-tauri-runtime-smoke-macos.json` is the macOS Tauri runtime KataGo evidence target from `scripts/smoke_tauri_katago_live.py --engine ... --model ... --config ... --evidence-out docs/qa/katago-tauri-runtime-smoke-macos.json`. The repository gate requires schema `lizzieyzy.katago-tauri-runtime-smoke.v1`, status `pass`, platform `macos`, and passing runtime checks for startup, assets, analyze-once, analyze-game, and start/cancel.
- `docs/qa/readboard-tauri-runtime-smoke-macos.json` is the scoped macOS Tauri runtime readboard evidence target from the readboard runtime smoke runner. The repository gate requires schema `lizzieyzy.readboard-tauri-runtime-smoke.v1`, status `pass`, platform `macos`, and passing runtime checks for startup, sidecar probe ready/unavailable states, protocol-line sync with snapshot id, board size, move number, stone count, and player-to-play, target-state-change sync with distinct before/after snapshot ids, changed stone count or move number, and stable board size, unsupported OCR boundary behavior, and explicit markers that OCR and external client/window capture are not covered.
- `docs/qa/provider-live-smoke-macos.json` is the scoped macOS controlled-network Tauri provider evidence target from the provider runtime smoke runner. The repository gate requires schema `lizzieyzy.provider-live-smoke.v1`, status `pass`, platform `macos`, and passing runtime checks for startup, controlled-network Yike fetch, controlled-network Fox fetch, typed failure modes, controlled request observation, offline parser exclusion, and explicit external account/service scope limits.
- `docs/qa/multiplatform-packaging-smoke.json` is the scoped packaging evidence target from the multiplatform packaging smoke runner. The repository gate requires schema `lizzieyzy.multiplatform-packaging-smoke.v1`, status `pass`, and passing checks for macOS, Windows, and Linux artifacts, signing-state recording, dev-server absence, and SHA-256 checksums.
- The repository smoke gate has no pending items after scoped packaging evidence is recorded. Official signing/notarization, release publication, updater readiness, store distribution, platform-specific installed-app release smoke, and full legacy parity remain outside that proof.
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
python3 scripts/smoke_user_flows.py --verbose
```

Pass: the evidence JSON is sanitized, has status `pass`, includes semantic append/edit/reorder/delete SGF checks, has explicit two-launch save/reopen proof through `secondLaunch`, `reopen`, and `afterReopen`, and `smoke_user_flows.py` reports `ui_tauri_runtime_smoke` as PASS. This is macOS local runtime evidence only; it is not native file dialog/manual release proof, full legacy parity, live KataGo/provider/readboard validation, or multiplatform packaging proof.

For the macOS live KataGo evidence, run from the repository root:

```bash
python3 scripts/smoke_katago_live.py --engine /path/to/katago --model /path/to/model.bin.gz --config /path/to/analysis.cfg --evidence-out docs/qa/katago-live-smoke-macos.json
python3 scripts/smoke_tauri_katago_live.py --engine /path/to/katago --model /path/to/model.bin.gz --config /path/to/analysis.cfg --evidence-out docs/qa/katago-tauri-runtime-smoke-macos.json
python3 scripts/smoke_user_flows.py --verbose
```

Pass: both evidence JSON files are sanitized and have status `pass`; the CLI evidence records one-position and batch `katago analysis` responses, and the Tauri evidence records runtime startup, assets, analyze-once, analyze-game, and start/cancel. `smoke_user_flows.py` reports `katago_live_smoke` as PASS only after both files pass. This is macOS local live KataGo CLI plus Tauri runtime evidence; it is not cache-hit proof, bundled-engine proof, or multiplatform packaging proof.

For the scoped macOS readboard runtime evidence, run the readboard Tauri runtime smoke collector and then:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `docs/qa/readboard-tauri-runtime-smoke-macos.json` is sanitized, has schema `lizzieyzy.readboard-tauri-runtime-smoke.v1`, status `pass`, platform `macos`, and includes `runtime_started`, `sidecar_probe_ready`, `sidecar_probe_unavailable`, `protocol_line_sync`, `target_state_change_sync`, `unsupported_ocr_path`, and `external_client_not_covered`. The protocol check must include `snapshotId`, `boardSize`, `moveNumber`, `stoneCount`, and `toPlay`; the target-change check must include distinct before/after snapshot ids, changed stone count or move number, and `boardSizeStable`; the OCR/external-client boundary checks must explicitly mark OCR and external client/window capture as not covered. `smoke_user_flows.py` reports `readboard_live_smoke` as PASS only when that evidence is present and semantically valid. This is scoped macOS Tauri runtime evidence for probe/protocol behavior; it is not OCR proof, real external client/window capture proof, or multiplatform packaging proof.

For the scoped macOS provider controlled-network evidence, run the provider Tauri runtime smoke collector and then:

```bash
python3 scripts/smoke_user_flows.py --verbose
```

Pass: `docs/qa/provider-live-smoke-macos.json` is sanitized, has schema `lizzieyzy.provider-live-smoke.v1`, status `pass`, platform `macos`, and includes `runtime_started`, `yike_controlled_fetch`, `fox_controlled_fetch`, `provider_failure_modes`, `controlled_network_observed`, `offline_not_counted_as_external_live`, and `external_account_scope`. The Yike check must use `networkMode: controlled_network`, a 2xx/3xx HTTP status, validated payload, non-negative result count, and `fixtureParserOnly: false`; the Fox check must use `networkMode: controlled_network`, a 2xx/3xx HTTP status, imported payload, positive move count, and `directHttpWarning: true`. This is scoped controlled-network Tauri provider evidence; it is not real Fox/Yike service parity, account login proof, anti-bot stability proof, or service schema drift proof.

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
- Save or Save As, quit or restart the desktop runtime, reopen the saved SGF, and confirm comments, properties, branch order, move count, and replayed board state round-trip.
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
- Edit a comment and a node property on a non-root node.
- Append a child move or pass from the selected node.
- Delete a selected non-root node/subtree and confirm the parent/selection behavior is understandable.
- Reorder sibling variations and confirm the visible tree order changes.
- Save, restart the desktop runtime, reopen the SGF, and confirm comments, properties, appended/deleted nodes, variation order, and board replay persisted.

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

### Image OCR Unsupported Path

- Request image-only readboard sync when the current runtime does not provide OCR.
- Confirm the result is a structured unsupported/not-implemented error that names OCR or readboard image sync.
- Confirm the board is not replaced with guessed, stale, or partial data.

Pass: OCR absence is explicit and recoverable; it is not counted as successful live readboard sync.

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
- image OCR unavailable structured error: PASS/FAIL/SKIPPED:
- npm ci: PASS/FAIL/SKIPPED
- npm run build: PASS/FAIL/SKIPPED
- npm run tauri:build: PASS/FAIL/SKIPPED

Manual smoke:
- SGF open: PASS/FAIL
- SGF branch navigation: PASS/FAIL
- SGF comment/property edit: PASS/FAIL
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
- image OCR unavailable structured error: PASS/FAIL/SKIPPED

Known limitations:
```
