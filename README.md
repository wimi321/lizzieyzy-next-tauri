# LizzieYzy Next

LizzieYzy Next is the in-progress next-generation desktop architecture for the LizzieYzy Go review application. The new line is being built in parallel with the existing Java/Swing maintenance line, using Tauri 2, Rust, and TypeScript so SGF handling, KataGo analysis, engine setup, and local persistence can be tested in smaller modules.

This repository currently contains a functional Next workspace that can be built and run locally, not a published full-parity replacement for the legacy application. The Java/Swing line remains the stable user-facing release path while the Tauri app gains coverage and parity.

## Current Status

Implemented in the Next workspace:

- Tauri 2 desktop shell under `apps/desktop/src-tauri`.
- React + TypeScript + Vite frontend under `apps/desktop`.
- Rust workspace crates for app DTOs, Go rules, SGF parsing/replay/serialization, KataGo protocol normalization, analysis classification, engine management, and SQLite-backed storage/cache.
- SGF parse, replay, serialize, comments, variations, and setup stones MVP.
- Native SGF open/save through the Tauri desktop backend, with browser-preview fallbacks where possible.
- KataGo one-position analysis and full-game batch analysis through analysis JSONL.
- Analysis progress events, cancellation, candidate moves, ownership, policy, and winrate/progress overlays.
- Engine path/model/config pickers, asset checks, and multiple engine profiles persisted in app data.
- SQLite analysis cache with cache key computation, lookup, save, and delete commands.
- Scaffold validation, Rust tests, and frontend build checks wired for local and CI use.
- Release preflight validation for Tauri metadata and the safe dry-run workflow.
- Multi-platform GitHub Release workflow for macOS, Windows, and Linux CI-built assets.
- Bilingual English/Chinese release notes for `v0.1.0`.

Not yet claimed as complete in the Next workspace:

- Full legacy Java/Swing feature parity.
- Fox/Yike online game providers as live external-network integrations.
- readboard live sidecar integration in a real target environment.
- Production signing/notarization for macOS and Windows unless maintainer secrets are configured.
- End-to-end clean-machine installer smoke coverage across all target platforms.
- Complete migration of every legacy setting, layout preference, and analysis workflow.

Provider and readboard work in this batch should be treated as offline contract/domain-command coverage until the owning implementation has live environment evidence. Do not describe live provider login, external network capture, or readboard sidecar operation as shipped from this repository alone.

## Technology Stack

- Desktop runtime: Tauri 2.
- Backend: Rust workspace, Tauri commands, SQLite via `rusqlite`.
- Frontend: React, TypeScript, Vite, `@tauri-apps/api`.
- Core domains: SGF, Go rules, KataGo analysis JSONL, engine profiles, analysis cache.
- Validation: `scripts/validate_scaffold.py`, Rust unit tests, frontend build, and smoke checks.

## Repository Map

- `apps/desktop`: Next React desktop UI.
- `apps/desktop/src-tauri`: Tauri 2 command gateway and native desktop integration.
- `crates/app-model`: Shared DTOs used across Rust and TypeScript boundaries.
- `crates/go-core`: Board state and Go rule logic.
- `crates/sgf`: SGF parsing, replay, and serialization.
- `crates/katago-protocol`: KataGo analysis query/response models.
- `crates/analysis-core`: Candidate/problem classification helpers.
- `crates/engine-manager`: Engine command specs, asset checks, process execution, and cancellation.
- `crates/storage`: SQLite storage/cache schema helpers.
- `docs/ARCHITECTURE_NEXT.md`: Current Next architecture and module boundaries.
- `docs/MIGRATION_PLAN.md`: Completed and pending migration work.
- `docs/DEVELOPMENT.md`: Local development and smoke validation commands.
- `docs/RELEASE_CHECKLIST.md`: Release-readiness checklist and manual acceptance flow.

## Development Commands

Run scaffold validation from the repository root:

```bash
python3 scripts/validate_scaffold.py --verbose
```

Run release asset preflight from the repository root:

```bash
python3 scripts/validate_release_assets.py --verbose
python3 scripts/validate_release_workflow.py --verbose
```

Run the Rust checks:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Run the frontend build:

```bash
cd apps/desktop
npm ci
npm run build
```

Run the Next app in development:

```bash
cd apps/desktop
npm run tauri:dev
```

For a browser-only preview without native Tauri commands:

```bash
cd apps/desktop
npm run dev
```

The browser preview can exercise UI fallback paths, local SGF parsing fallback, fake review frames, and browser-local cache. Real KataGo execution, native file open/save, asset inspection, and app-data profile persistence require the Tauri desktop runtime.

## Local Smoke Flow

Use `docs/DEVELOPMENT.md` for the full checklist. The short acceptance path is:

1. Run `python3 scripts/validate_scaffold.py --verbose`.
2. Start `npm run tauri:dev` in `apps/desktop`.
3. Open an SGF file or paste one from `tests/golden`.
4. Configure a KataGo engine profile with engine, model, config, optional working directory, and max visits.
5. Run `Check assets` and confirm required assets are present.
6. Run one-position KataGo analysis.
7. Run full-game analysis, observe progress, and cancel a second run to verify cancellation.
8. Reopen or reparse the same SGF and confirm analysis cache hit status.
9. Save or Save As the SGF and reopen it to confirm round-trip behavior.

## CI Status

CI should be read as scaffold and regression coverage for the Next workspace, not as proof of full legacy parity. The important gates are:

- scaffold validation,
- release asset preflight and production release workflow contract validation,
- frontend dependency install and build,
- Rust formatting,
- Rust clippy,
- Rust tests.

Provider contract tests and readboard domain tests are accepted through the Rust workspace test gate when those modules land; the handoff should name the exact package or test filter and must not count a zero-test filter as evidence. Release dry-run acceptance is `.github/workflows/release-dry-run.yml` plus `python3 scripts/validate_release_assets.py --verbose`; the workflow uploads diagnostic artifacts and must not create a GitHub release.

Passing CI means the current Tauri/Rust/TypeScript baseline is structurally healthy. It does not mean live Fox/Yike/readboard integrations, platform signing, notarization, or clean-machine installer smoke checks have completed.

## Releases

`v0.1.0` is the first public Tauri release candidate for this repository. Release notes are bilingual:

- [Release notes v0.1.0](.github/RELEASE_NOTES_v0.1.0.md)
- [Changelog](CHANGELOG.md)

The production release workflow is `.github/workflows/release.yml`. It runs on `v*` tags, builds macOS, Windows, and Linux Tauri bundles, collects assets, writes SHA-256 checksum files, and publishes a GitHub Release. Assets generated without signing or notarization secrets are clearly marked as unsigned release-candidate artifacts.

## Documentation

- [Next architecture](docs/ARCHITECTURE_NEXT.md)
- [Migration plan](docs/MIGRATION_PLAN.md)
- [Development guide](docs/DEVELOPMENT.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Acknowledgements

- Original project: [yzyray/lizzieyzy](https://github.com/yzyray/lizzieyzy)
- KataGo: [lightvector/KataGo](https://github.com/lightvector/KataGo)
- Historical Fox references:
  - [yzyray/FoxRequest](https://github.com/yzyray/FoxRequest)
  - [FuckUbuntu/Lizzieyzy-Helper](https://github.com/FuckUbuntu/Lizzieyzy-Helper)
