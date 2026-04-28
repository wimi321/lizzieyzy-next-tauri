# LizzieYzy Next Tauri

LizzieYzy Next Tauri is the next-generation desktop foundation for a Go AI review tool powered by KataGo. The project moves the app toward a production Tauri 2 architecture with a Rust domain core, a TypeScript/React desktop shell, and local-first persistence.

This repository is the initial refactor baseline. It keeps the shape of a real application instead of a demo: domain crates are separated, the Tauri bridge has typed command boundaries, the frontend contains board and analysis surfaces, and CI validates both Node and Rust paths.

## Tech Stack

- Tauri 2 desktop runtime
- Rust workspace crates for Go rules, SGF, analysis, engine orchestration, shared DTOs, and storage
- TypeScript, React, and Vite for the desktop UI
- SQLite via `rusqlite` for planned local cache and persisted analysis state

## Current Features

- SGF import foundation through `crates/sgf`
- Board state and move legality primitives through `crates/go-core`
- KataGo analysis protocol DTOs through `crates/katago-protocol`
- Candidate move sorting and problem marker classification through `crates/analysis-core`
- React board canvas, winrate chart, and analysis panel shell
- Tauri backend bridge for local desktop integration
- Scaffold validation and GitHub Actions CI

## Planned Features

- Full KataGo analysis pipeline and engine lifecycle management
- Winrate graph backed by persisted analysis frames
- Candidate point overlays with visits, winrate, and score deltas
- Local SQLite cache for games, analysis jobs, and engine metadata
- Import/export workflows for richer SGF review sessions

## Repository Layout

```text
apps/desktop/        Tauri 2 + React desktop application
crates/              Rust workspace crates
docs/                Architecture and migration notes
scripts/             Validation and maintenance scripts
tests/               Golden fixtures and integration assets
```

The architecture overview lives in [docs/ARCHITECTURE_NEXT.md](docs/ARCHITECTURE_NEXT.md), with the migration path documented in [docs/MIGRATION_PLAN.md](docs/MIGRATION_PLAN.md).

## Local Development

Install the desktop dependencies:

```bash
npm --prefix apps/desktop install
```

Build the frontend:

```bash
npm --prefix apps/desktop run build
```

Build and test Rust:

```bash
cargo build --workspace
cargo test --workspace
```

Run the Tauri app in development mode:

```bash
npm --prefix apps/desktop run tauri:dev
```

Validate the scaffold:

```bash
python3 scripts/validate_scaffold.py
```

## CI

GitHub Actions runs on `main` and `dev`:

- Node dependency installation and frontend production build
- Rust formatting check
- Rust clippy with warnings denied
- Rust workspace tests
- Scaffold validation script

## Branch Strategy

- `main`: stable baseline
- `dev`: development integration branch

Feature work should branch from `dev` and return through pull requests.
