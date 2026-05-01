# Release Checklist

This checklist tracks release readiness for the LizzieYzy Next Tauri 2 + Rust + TypeScript workspace. It is not a statement that a public Tauri release has already shipped.

The existing Java/Swing maintenance line may have its own release process. For the Next workspace, do not publish or describe a release as ready until the checks below pass on the intended platform and the artifact set exists.

## Release Readiness Rules

- Do not claim full legacy parity unless Fox/Yike/readboard, legacy settings, and advanced review workflows have explicit acceptance evidence.
- Do not claim Fox, Yike, or readboard support in the Next app until those providers are implemented and smoke-tested.
- Do not claim production packaging is complete until platform artifacts are built and verified.
- Keep README, migration plan, architecture doc, and release notes aligned with the actual state.
- Every release candidate must include scaffold validation output.

## Required Automated Checks

From the repository root:

```bash
python3 scripts/validate_scaffold.py --verbose
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

The GitHub Actions dry-run workflow is `.github/workflows/release-dry-run.yml`. It can be triggered manually or by pushing a `v*` tag, validates macOS/Linux/Windows setup, and uploads dry-run summaries without creating a GitHub release.

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

## Packaging Checklist

When production packaging becomes in scope, verify:

- App identifier remains `org.lizzieyzy.next`.
- Frontend output is built from `apps/desktop/dist`.
- Required icons and metadata are present.
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
- cargo fmt --all --check: PASS/FAIL/SKIPPED
- cargo clippy --workspace --all-targets -- -D warnings: PASS/FAIL/SKIPPED
- cargo test --workspace: PASS/FAIL/SKIPPED
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

Known limitations:
```
