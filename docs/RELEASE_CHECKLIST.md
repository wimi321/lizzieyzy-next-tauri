# Release Checklist

This checklist tracks release readiness for the LizzieYzy Next Tauri 2 + Rust + TypeScript workspace. It is not a statement that a public Tauri release has already shipped.

The existing Java/Swing maintenance line may have its own release process. For the Next workspace, do not publish or describe a release as ready until the checks below pass on the intended platform and the artifact set exists.

## Release Readiness Rules

- Do not claim full legacy parity unless Fox/Yike/readboard, legacy settings, and advanced review workflows have explicit acceptance evidence.
- Do not claim Fox, Yike, or readboard live support in the Next app from offline contracts alone. Repository-level offline contract and runtime path evidence can be reported as implemented, but live support requires the environment smoke checks below.
- Do not claim production packaging is complete until platform artifacts are built and verified.
- Keep README, migration plan, architecture doc, and release notes aligned with the actual state.
- Every release candidate must include scaffold validation output.

## Required Automated Checks

From the repository root:

```bash
python3 scripts/validate_scaffold.py --verbose
python3 scripts/validate_release_assets.py --verbose
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

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
- Provider runtime path checks must record whether `provider_fetch_yike` and `provider_fetch_fox` were exercised offline only or against real services.
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
- Reopen the saved file.
- Confirm parse/replay and move count match expectations.

Pass: saved SGF is parseable and round-trips through native open.

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
- `python3 scripts/validate_release_assets.py --verbose` passes.
- `.github/workflows/release-dry-run.yml` passes on macOS, Linux, and Windows.
- Missing signing secrets are reported as unsigned dry-run state, not treated as a publish failure.
- Bundled KataGo/runtime assets, if included, match documented paths.
- The app starts without a development server.
- Windows installer or portable package opens on a clean machine.
- macOS app handles Gatekeeper/signing/notarization according to the documented release policy.
- Linux package includes required runtime dependencies or clearly documents them.
- Logs and error messages distinguish UI errors, Tauri command errors, engine errors, and storage/cache errors.
- The full release process, secrets, artifact policy, and rollback plan are recorded in `docs/RELEASE_PROCESS.md`.

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
- Engine profile persistence: PASS/FAIL
- Asset check: PASS/FAIL
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
