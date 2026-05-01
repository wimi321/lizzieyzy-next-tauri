# Development Guide

This guide is for contributors working on the LizzieYzy Next Tauri 2 + Rust + TypeScript workspace. The existing Java/Swing application remains the maintenance release line; this document focuses on validating the Next scaffold and its current desktop workflows.

## Scope

Use this guide when changing:

- `README.md` and Next architecture/migration docs,
- scaffold validation and smoke documentation,
- the Tauri desktop app under `apps/desktop`,
- Rust crates under `crates/*`,
- SGF, KataGo, engine profile, asset check, and cache behavior.

Do not treat a passing Next smoke run as full legacy parity. Provider/readboard work in this batch may provide offline contracts and runtime path plumbing, but live Fox/Yike network behavior, live readboard sidecar operation, and Tauri production release packaging still require environment-specific validation.

## Required Local Baseline

From the repository root, always run:

```bash
python3 scripts/validate_scaffold.py --verbose
python3 scripts/validate_release_assets.py --verbose
```

For code changes, also run the relevant checks:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

For frontend or Tauri UI changes:

```bash
cd apps/desktop
npm ci
npm run build
```

For documentation-only changes, scaffold validation is still required because it is the shared acceptance gate for the current handoff package.

Provider/readboard acceptance entry points:

- Provider contract tests: run the Rust workspace tests that own the provider contract modules and record the exact package or filter. `cargo test --workspace` is the baseline; a focused filter only counts if it runs non-zero provider tests.
- Provider runtime path checks: verify `provider_fetch_yike` and `provider_fetch_fox` return structured success/error results through the intended Rust/TypeScript boundary. This is still offline/local evidence unless real provider services are contacted.
- Readboard domain tests: run the Rust workspace tests that own readboard parsing/command behavior and record the exact package or filter.
- Readboard sidecar path checks: verify `readboard_sidecar_probe` and `readboard_sidecar_sync_snapshot` return structured ready/not-ready/sync results through the intended boundary. Live sidecar checks require a real readboard environment and should be listed separately.
- UI path checks: ProviderPanel is the expected UI surface for provider fetch, readboard probe, and readboard sync controls. If a batch only exposes payload import or URL preview, record fetch/probe/sync UI as pending rather than implying live support.
- Release dry-run: run `python3 scripts/validate_release_assets.py --verbose` locally and use `.github/workflows/release-dry-run.yml` for the cross-platform compile-only dry-run.

## Running The Next App

Desktop runtime:

```bash
cd apps/desktop
npm run tauri:dev
```

Browser preview:

```bash
cd apps/desktop
npm run dev
```

The browser preview is useful for layout and fallback checks. Real KataGo execution, native file dialogs, app-data engine profile persistence, asset inspection, and SQLite cache commands require `npm run tauri:dev`.

## Repository Structure

- `apps/desktop`: React + TypeScript frontend.
- `apps/desktop/src/api`: frontend wrappers around Tauri commands and browser fallbacks.
- `apps/desktop/src/components`: board, analysis, chart, cache, and engine setup UI.
- `apps/desktop/src-tauri`: Tauri 2 command gateway and native app integration.
- `crates/app-model`: shared DTOs.
- `crates/go-core`: board/rules logic.
- `crates/sgf`: SGF parsing, replay, and serialization.
- `crates/katago-protocol`: KataGo analysis JSONL query/response modeling.
- `crates/analysis-core`: derived analysis markers.
- `crates/engine-manager`: engine command specs, asset checks, process execution, progress, timeout, and cancellation.
- `crates/storage`: SQLite storage/cache helpers.
- `tests/golden`: SGF fixtures for migration and regression checks.

## Local Smoke Flow

Use the desktop runtime for this flow:

```bash
cd apps/desktop
npm run tauri:dev
```

### 1. Open Or Load SGF

- Start from the bundled sample SGF or paste a fixture from `tests/golden/basic_19x19.sgf`.
- Click the parse/import action and confirm the board, move count, player names, and move slider update.
- Use native Open to load an `.sgf` file when running under Tauri.

Expected result: the status message reports a loaded/opened game and the board can move through replayed positions.

### 2. Configure Engine Profile

- In the engine setup panel, set a profile name.
- Pick or type the KataGo engine binary path.
- Pick or type the model path.
- Pick or type the analysis config path.
- Optionally set a working directory.
- Set a positive max visits value.
- Save the profile.
- Add a second profile and switch between profiles if profile persistence is part of the change.

Expected result: profiles reload after app restart and the selected profile remains selected.

### 3. Check Assets

- Click `Check assets`.
- Confirm required engine, model, and config checks report `OK`.
- If testing an error path, temporarily point one required path at a missing file and confirm the UI blocks analysis and reports the missing asset.

Expected result: analysis buttons only become usable when required assets are known to exist.

### 4. Run One-Position Analysis

- Select a move on the board.
- Click `Run KataGo`.
- Confirm candidates, PV, winrate/score data, ownership/policy-backed overlays, and problem markers update for that move.

Expected result: the status message reports completed KataGo analysis for the selected move.

### 5. Run Full-Game Analysis

- Click `Analyze game`.
- Watch progress update with completed/expected positions and current move.
- Confirm winrate/candidate data accumulates across the game.

Expected result: completion produces frames for the requested turns and stores analysis in the cache.

### 6. Cancel Analysis

- Start a full-game analysis with enough visits to observe progress.
- Click `Cancel`.
- Confirm progress stops and the status message reports cancellation.
- Start another analysis afterwards to ensure the job registry recovered.

Expected result: a cancelled job does not keep the UI locked and does not prevent a later run.

### 7. Verify Cache Hit

- Analyze a game.
- Reparse or reopen the same SGF.
- Confirm cache status changes to hit for the same game/profile/engine kind.
- If needed, clear the cache path through the UI or a targeted cache command and verify miss behavior.

Expected result: repeated loading of the same SGF can reuse cached analysis instead of starting from an empty review state.

### 8. Save SGF

- Use Save or Save As under the Tauri desktop runtime.
- Reopen the saved file.
- Confirm parse/replay still succeeds and move count remains stable.

Expected result: SGF write validates parseability and can round-trip through native open.

## Provider And Sidecar Smoke Flow

Run this only in an environment with the required provider accounts, network access, target client state, and readboard sidecar installed. Record skipped items explicitly; skipped live checks do not invalidate offline contract work, but they do block live-support claims.

Repository-level checks may show that the commands and UI route exist and return typed success, typed error, or runtime unavailable results. Live checks require real services or processes. Keep those two result columns separate in the handoff.

### 1. Yike Runtime Fetch

- Start the Tauri desktop runtime and configure the Yike provider inputs required by the implementation.
- Trigger `provider_fetch_yike` from ProviderPanel or the intended debug/test harness for a real Yike game, game list, or supported provider resource.
- Record account/session type, network path, request target, result count, and latency.
- Repeat with an expired or missing session if the implementation supports that state.

Expected result: successful fetches return normalized DTOs, and auth/network failures return structured errors without stale cached data being presented as live data.

### 2. Fox Runtime Fetch

- Start the Tauri desktop runtime with the real Fox prerequisites in place.
- Trigger `provider_fetch_fox` from ProviderPanel or the intended debug/test harness for each supported command shape: `chessid`, `uid`, and `user_name`.
- Record target client/session state, result count, latency, and any provider-specific prerequisites.
- Repeat with the target client unavailable or credentials/session invalid.

Expected result: successful fetches return normalized DTOs, and unavailable client/session/network states produce actionable errors.

### 3. readboard Sidecar Probe

- Start the readboard sidecar expected by the current implementation.
- Probe the sidecar from the Tauri runtime.
- Record sidecar version, port/path, process state, and probe latency.
- Stop the sidecar and repeat the probe.

Expected result: the app distinguishes ready, not running, incompatible, and timeout states.

### 4. readboard Sync

- With the sidecar running, sync against a real target board/client state.
- Exercise protocol line sync through `readboard_sidecar_sync_snapshot` using the supported protocol-line input or sidecar response path.
- Confirm board size, stones, move state, coordinates, and player-to-play if available.
- Restart the sidecar or change the target board state and sync again.

Expected result: sync responses normalize into app DTOs and do not leave stale board state after restart, target change, or timeout.

### 5. Image OCR Unsupported Path

- Request a sync with image-only input when image OCR is not available in the current runtime.
- Confirm the response is a structured unsupported/not-implemented error that names the readboard/OCR boundary.
- Confirm no board state is replaced by stale or guessed data.

Expected result: image OCR unavailability is explicit and recoverable. It is not reported as a successful sidecar sync.

### 6. Failure Modes

- Exercise missing provider configuration, bad credentials/session, network loss, provider timeout, malformed provider payload, missing sidecar, sidecar crash, sidecar timeout, and cancellation/retry.
- Confirm logs and UI messages identify the failing boundary: provider auth, provider network, sidecar process, sidecar protocol, Tauri command, or DTO normalization.

Expected result: failure states are structured, recoverable where expected, and not described as successful live support.

## Provider And Sidecar Manual Matrix

| Scenario | Repository/Local Expected Result | Live Environment Expected Result |
| --- | --- | --- |
| Yike fetch success | `provider_fetch_yike` validates provider/timeout and reaches the Yike runtime path with typed success, typed error, or runtime unavailable results. | Real Yike resource fetch returns normalized DTOs with source metadata, result count, and latency recorded. |
| Yike fetch failure | Missing URL, wrong provider, timeout, malformed payload, or unavailable runtime returns `ProviderError` without stale success data. | Bad auth/session, blocked network, provider timeout, or malformed live response returns structured auth/network/payload errors. |
| Fox `chessid` fetch success | `provider_fetch_fox` accepts the `chessid` command shape and reaches the Fox runtime path with typed success, typed error, or runtime unavailable results. | Real `chessid` fetch returns normalized SGF/provider DTOs and records prerequisites and latency. |
| Fox `uid` fetch success | `provider_fetch_fox` accepts the `uid` command shape and reaches the Fox runtime path with typed success, typed error, or runtime unavailable results. | Real `uid` fetch resolves the expected game/list payload and normalizes it without UI-only shortcuts. |
| Fox `user_name` fetch success | `provider_fetch_fox` accepts the `user_name` command shape and reaches the Fox runtime path with typed success, typed error, or runtime unavailable results. | Real nickname lookup resolves to the expected account/game payload and records ambiguous/not-found behavior. |
| Fox fetch failure | Missing URL/command, wrong provider, timeout, bad command, malformed payload, or unavailable runtime returns `ProviderError`. | Unavailable client/session, bad account, blocked network, timeout, or provider payload change returns structured errors. |
| readboard probe missing | `readboard_sidecar_probe` validates timeout and reports not-ready/runtime unavailable as a structured result or error. | Stopped or unreachable sidecar reports not running/unreachable/timeout without changing board state. |
| readboard probe present | Probe path is callable through the intended boundary. | Running sidecar reports ready with version/path/latency recorded. |
| readboard protocol line sync | `readboard_sidecar_sync_snapshot` validates input and protocol-line parsing returns DTOs or typed protocol errors. | Sidecar sync reflects board size, stones, move state, and player-to-play from the real target board. |
| image OCR unavailable | Image-only sync returns a structured unsupported/not-implemented error when OCR is unavailable. | Live OCR may only be marked PASS with an OCR-capable runtime and image fixture evidence; otherwise mark SKIPPED/UNSUPPORTED. |

## Documentation Acceptance

When updating docs for this handoff package, keep these claims accurate:

- Do not claim a Tauri release has been published unless release artifacts exist.
- Do not claim full Java/Swing parity.
- Do not claim Fox/Yike/readboard live migration is complete without external-network or sidecar evidence.
- Distinguish browser preview behavior from native Tauri desktop behavior.
- Report the exact validation command and result in the handoff.

## Suggested Reading

- [Next architecture](ARCHITECTURE_NEXT.md)
- [Migration plan](MIGRATION_PLAN.md)
- [Release checklist](RELEASE_CHECKLIST.md)
- [Troubleshooting](TROUBLESHOOTING.md)
