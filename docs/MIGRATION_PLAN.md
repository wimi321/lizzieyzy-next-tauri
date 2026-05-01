# Migration Plan

This plan tracks the migration from the Java/Swing maintenance line to the LizzieYzy Next desktop architecture built with Tauri 2, Rust, and TypeScript. The legacy application remains the stable release baseline until the Next workspace proves the required user workflows through tests, fixtures, and smoke checks.

The current state is useful and testable, but it is not full legacy parity. In particular, Fox/Yike providers, readboard integration, and production Tauri release packaging are still pending.

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

## Pending Work

### Legacy Feature Parity

- Fox provider migration.
- Yike provider migration.
- readboard integration.
- Legacy capture/import helpers beyond the SGF flows already present.
- Full settings migration from Java/Swing configuration files.
- Complete layout/theme parity.
- Complete parity for every analysis shortcut and advanced review workflow.

### Production Packaging

- Tauri release packaging for Windows, macOS, and Linux.
- Platform signing, notarization, installer metadata, and update strategy.
- Bundled KataGo/runtime asset layout for the Tauri application.
- Release artifact validation for the Tauri app.
- Platform-specific installer smoke coverage.

### Test And Acceptance Coverage

- Broader Rust fixture coverage for SGF edge cases.
- UI automation for the primary desktop smoke flow.
- Engine integration tests that can run against a controlled KataGo fixture or mock process.
- Cache migration tests once the storage schema stabilizes beyond the current MVP.
- Provider contract tests before Fox/Yike/readboard work is considered done.

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 0: Scaffold Contract | Complete | Structural validator, workspace, frontend, Tauri backend, docs, and golden fixture are present. |
| Phase 1: Core Runtime Parity | Mostly complete | SGF parse/replay/serialize, Go rules, DTOs, and UI rendering are wired. Remaining work is broader fixture coverage and legacy edge cases. |
| Phase 2: KataGo Analysis | Implemented MVP | One-shot and full-game batch analysis exist with progress and cancellation. More resilience and integration coverage are still needed. |
| Phase 3: Storage And Providers | Partial | SQLite analysis cache and engine profile persistence are present. Fox/Yike/readboard providers are not migrated. |
| Phase 4: Packaging And Release | Not complete | Tauri production packaging and release publication are still future work. |

## Acceptance Gates

Baseline structural acceptance:

```bash
python3 scripts/validate_scaffold.py --verbose
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

## Parallel Agent Rules

- Worker-1 owns Rust workspace, Tauri backend, and crates.
- Worker-2 owns TypeScript frontend and package/build files.
- Worker-3 owns README, validation, smoke/release documentation, scaffold tests, and Next architecture/migration docs.
- Reviewers may inspect all files but should not silently rewrite another worker's area.
- Integration should prefer additive fixes and avoid reverting unrelated changes.

## Migration Principle

The Java/Swing codebase is a behavior reference, not the implementation skeleton for the new runtime. Each migrated legacy capability should start from observable behavior, fixtures, and tests, then be implemented behind the Tauri/Rust/TypeScript boundary.
