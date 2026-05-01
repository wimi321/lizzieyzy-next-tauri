# Development Guide

This guide is for contributors working on the LizzieYzy Next Tauri 2 + Rust + TypeScript workspace. The existing Java/Swing application remains the maintenance release line; this document focuses on validating the Next scaffold and its current desktop workflows.

## Scope

Use this guide when changing:

- `README.md` and Next architecture/migration docs,
- scaffold validation and smoke documentation,
- the Tauri desktop app under `apps/desktop`,
- Rust crates under `crates/*`,
- SGF, KataGo, engine profile, asset check, and cache behavior.

Do not treat a passing Next smoke run as full legacy parity. Fox/Yike providers, readboard integration, and Tauri production release packaging are still pending.

## Required Local Baseline

From the repository root, always run:

```bash
python3 scripts/validate_scaffold.py --verbose
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

## Documentation Acceptance

When updating docs for this handoff package, keep these claims accurate:

- Do not claim a Tauri release has been published unless release artifacts exist.
- Do not claim full Java/Swing parity.
- Do not claim Fox/Yike/readboard migration is complete.
- Distinguish browser preview behavior from native Tauri desktop behavior.
- Report the exact validation command and result in the handoff.

## Suggested Reading

- [Next architecture](ARCHITECTURE_NEXT.md)
- [Migration plan](MIGRATION_PLAN.md)
- [Release checklist](RELEASE_CHECKLIST.md)
- [Troubleshooting](TROUBLESHOOTING.md)
