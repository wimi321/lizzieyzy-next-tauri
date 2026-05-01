# Migration Plan

This plan tracks the migration from the Java/Swing maintenance line to the LizzieYzy Next desktop architecture built with Tauri 2, Rust, and TypeScript. The legacy application remains the stable release baseline until the Next workspace proves the required user workflows through tests, fixtures, and smoke checks.

The current state is useful and testable, but it is not full legacy parity. Core Tauri/Rust/TypeScript flows can be built and run locally. Provider/readboard work in this batch should be treated as offline contract plus runtime path coverage until Fox/Yike live network behavior, readboard live sidecar behavior, and production Tauri release packaging have environment-specific validation. The relevant command names for this batch are `provider_fetch_yike`, `provider_fetch_fox`, `readboard_sidecar_probe`, and `readboard_sidecar_sync_snapshot`.

## Completed In The Next Workspace

### Scaffold And Validation

- Rust workspace rooted at `Cargo.toml`.
- Tauri 2 desktop backend under `apps/desktop/src-tauri`.
- React + TypeScript + Vite frontend under `apps/desktop`.
- Domain crates under `crates/*`.
- Golden SGF fixtures under `tests/golden`.
- `scripts/validate_scaffold.py --verbose` as the structural validation gate.
- Scaffold tests under `tests/test_validate_scaffold.py`.
- CI-oriented commands for scaffold validation, frontend build, Rust formatting, clippy, and Rust tests.

### SGF And Go Runtime

- SGF parse into normalized DTOs.
- SGF replay into board positions.
- SGF serialization and native save validation.
- Mainline move extraction.
- MVP support for SGF variations, comments, setup stones, player-to-play, captures, pass, suicide, and simple ko behavior through Rust domain logic.
- Golden fixtures for basic 19x19 and compatibility cases.

### Desktop And UI Workflow

- Tauri command gateway for health, SGF parse/replay, native open/save, analysis, engine settings, asset checks, and cache commands.
- React board, analysis panel, winrate chart, cache status, and engine setup UI.
- ProviderPanel is the intended surface for provider fetch, readboard probe, and readboard sync controls. If only URL preview or payload import is available in a given build, fetch/probe/sync UI should remain marked pending.
- Browser-preview fallbacks for local development where native commands are unavailable.
- Native SGF open/save in the Tauri desktop runtime.
- Candidate moves, PV display, ownership and policy data paths, and problem markers.

### KataGo And Engine Management

- Engine profile DTOs and command spec construction.
- Engine picker fields for binary, model, config, working directory, and visits.
- Multiple engine profiles persisted in app data.
- Asset checks for required engine/model/config paths.
- One-shot KataGo analysis through analysis JSONL.
- Full-game batch analysis through analysis JSONL.
- Progress events, cancellation token, stderr/error propagation, timeout handling, and response-turn validation.

### Storage And Cache

- SQLite-backed analysis cache in app data.
- Stable SGF cache key computation.
- Cache lookup, save, and delete commands.
- Frontend cache status integration and browser-preview cache fallback.

### Provider And readboard Runtime Paths

- `provider_fetch_yike` is the runtime fetch entry point for Yike and should return normalized provider DTOs or typed `ProviderError` values.
- `provider_fetch_fox` is the runtime fetch entry point for Fox and should cover `chessid`, `uid`, and `user_name` command shapes.
- `readboard_sidecar_probe` is the sidecar readiness entry point and should distinguish typed success, typed error, runtime unavailable, incompatible, and timeout states.
- `readboard_sidecar_sync_snapshot` is the sidecar sync entry point and should normalize protocol line snapshot data into app DTOs or typed protocol/runtime errors.
- Image OCR is not a completed capability unless an OCR-capable sidecar/runtime is validated. Image-only sync should return a structured unsupported/not-implemented error when OCR is unavailable.

## Pending Work

### Legacy Feature Parity

- Fox provider live external-network validation.
- Yike provider live external-network validation.
- readboard live sidecar validation.
- Legacy capture/import helpers beyond the SGF flows already present.
- Full settings migration from Java/Swing configuration files.
- Complete layout/theme parity.
- Complete parity for every analysis shortcut and advanced review workflow.

### Production Packaging

- Tauri release packaging for Windows, macOS, and Linux.
- Platform signing, notarization, installer metadata, and update strategy.
- Bundled KataGo/runtime asset layout for the Tauri application.
- Release artifact validation for the Tauri app beyond the current dry-run preflight.
- Platform-specific installer smoke coverage.

### Test And Acceptance Coverage

- Broader Rust fixture coverage for SGF edge cases.
- UI automation for the primary desktop smoke flow.
- Engine integration tests that can run against a controlled KataGo fixture or mock process.
- Cache migration tests once the storage schema stabilizes beyond the current MVP.
- Provider contract tests and runtime fetch path checks before Fox/Yike repository work is considered implemented.
- Readboard domain tests and sidecar probe/sync path checks before readboard repository work is considered implemented.
- Live environment smoke checks before provider/readboard work is described as externally validated or shipped.

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 0: Scaffold Contract | Complete | Structural validator, workspace, frontend, Tauri backend, docs, and golden fixture are present. |
| Phase 1: Core Runtime Parity | Mostly complete | SGF parse/replay/serialize, Go rules, DTOs, and UI rendering are wired. Remaining work is broader fixture coverage and legacy edge cases. |
| Phase 2: KataGo Analysis | Implemented MVP | One-shot and full-game batch analysis exist with progress and cancellation. More resilience and integration coverage are still needed. |
| Phase 3: Storage And Providers | Partial | SQLite analysis cache and engine profile persistence are present. Provider/readboard command boundaries and runtime paths are tracked through `provider_fetch_yike`, `provider_fetch_fox`, `readboard_sidecar_probe`, and `readboard_sidecar_sync_snapshot`; live Fox/Yike network and readboard sidecar validation are still pending. |
| Phase 4: Packaging And Release | Not complete | Release preflight and dry-run checks exist. Tauri production packaging and release publication are still future work. |

## Acceptance Gates

Baseline structural acceptance:

```bash
python3 scripts/validate_scaffold.py --verbose
python3 scripts/validate_release_assets.py --verbose
```

Recommended local engineering acceptance:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cd apps/desktop
npm ci
npm run build
```

Manual smoke acceptance is tracked in [DEVELOPMENT.md](DEVELOPMENT.md) and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). The smoke flow must include SGF open, engine profile configuration, asset checks, one-shot analysis, full-game analysis, cancellation, cache hit verification, and SGF save.

Provider/readboard acceptance must name the concrete Rust package or test filter used for provider contract tests, runtime path checks, and readboard domain tests. A focused filter that runs zero tests is not acceptance evidence. Release acceptance starts with `python3 scripts/validate_release_assets.py --verbose` and the `.github/workflows/release-dry-run.yml` compile-only dry-run; neither path publishes production artifacts.

## Provider And Sidecar Acceptance Matrix

| Capability | Repository Acceptance | Manual Environment Smoke |
| --- | --- | --- |
| Yike runtime fetch | Offline contract tests pass and `provider_fetch_yike` returns structured success/error results without UI-only shortcuts. | Fetch a real game/list from Yike, record account/session type, network conditions, result count, latency, and login/session-expiry behavior. |
| Fox `chessid` fetch | Offline contract tests pass and `provider_fetch_fox` accepts the `chessid` command shape. | Fetch a real Fox `chessid`, record prerequisites, target client/session state, result count, latency, and blocked/expired-session behavior. |
| Fox `uid` fetch | Offline contract tests pass and `provider_fetch_fox` accepts the `uid` command shape. | Fetch a real Fox `uid` path and verify normalized DTOs plus unavailable-session behavior. |
| Fox `user_name` fetch | Offline contract tests pass and `provider_fetch_fox` accepts the `user_name` command shape. | Fetch a real Fox nickname path and verify found, not-found, ambiguous, and network failure behavior. |
| readboard sidecar probe | Domain tests pass and `readboard_sidecar_probe` reports structured ready/not-ready states. | Start the sidecar, probe it from the Tauri runtime, then record process version, port/path, timeout behavior, and unavailable-sidecar handling. |
| readboard protocol line sync | Domain tests pass and `readboard_sidecar_sync_snapshot` parses protocol line data and normalizes sync responses into DTOs. | Sync from a real target board/client state, verify board coordinates and move state, then repeat after sidecar restart or target-state change. |
| image OCR unavailable | Image-only sync returns a structured unsupported/not-implemented error when OCR is unavailable. | Mark OCR live smoke as SKIPPED/UNSUPPORTED unless an OCR-capable sidecar/runtime and image fixture evidence are available. |
| Failure modes | Unit/contract tests cover missing configuration, malformed payloads, timeout, cancellation, and typed errors. | Manually exercise bad credentials/session, network loss, missing sidecar, sidecar crash, malformed response, and retry/recovery messaging. |

## Parallel Agent Rules

- Worker-1 owns Rust workspace, Tauri backend, and crates.
- Worker-2 owns TypeScript frontend and package/build files.
- Worker-3 owns README, validation, smoke/release documentation, scaffold tests, and Next architecture/migration docs.
- Worker-4 owns release workflows, release preflight, release docs, and CI acceptance documentation.
- Reviewers may inspect all files but should not silently rewrite another worker's area.
- Integration should prefer additive fixes and avoid reverting unrelated changes.

## Migration Principle

The Java/Swing codebase is a behavior reference, not the implementation skeleton for the new runtime. Each migrated legacy capability should start from observable behavior, fixtures, and tests, then be implemented behind the Tauri/Rust/TypeScript boundary.
