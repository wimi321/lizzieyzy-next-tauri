# Release Process

This process covers production release preparation for the LizzieYzy Next Tauri 2 desktop workspace. The repository keeps a safe dry-run workflow for readiness checks and a tag-driven release workflow for public release-candidate assets.

## Truth Sync Summary

Current evidence supports scoped release-candidate validation, not a stable production release. `scripts/smoke_user_flows.py --verbose` currently reports `60 passed, 0 failed, 0 pending`, but the completion audit still marks production release readiness as blocked by signing, notarization, updater policy, official publication, clean-machine release testing, and remaining external parity gates. Do not use unsigned or scoped evidence to imply full production readiness, full Java/Swing parity, real provider/readboard/OCR parity, bundled large-model parity, or full legacy UI/layout/shortcut parity.

The added KataGo analysis stale-guard gate is scoped CI-verifiable evidence for edit-version guarded analysis cleanup and stale-result suppression. It does not change production release readiness, full legacy analysis parity, bundled large-model parity, or release parity.

The user-facing completion summary is `docs/COMPLETION_AUDIT.md`; release notes should mirror that scoped status.

## Release Gates

Run these checks from the repository root before tagging a candidate:

```bash
python3 scripts/validate_scaffold.py --verbose
python3 scripts/validate_release_assets.py --verbose
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Build the desktop frontend:

```bash
cd apps/desktop
npm ci
npm run build
```

For a compile-only Tauri release dry-run:

```bash
cd apps/desktop
npm run tauri:build -- --no-bundle --ci --no-sign
```

Only run a bundled, signed release after the dry-run is green on macOS, Linux, and Windows and the signing credentials below are present.

## GitHub Actions Dry-Run

Workflow: `.github/workflows/release-dry-run.yml`

Triggers:

- Manual `workflow_dispatch`, with switches for the Tauri compile dry-run and artifact upload.
- Tag push matching `v*`.

The workflow runs a macOS, Linux, and Windows matrix that checks out the repository, installs Node/Rust tooling, installs Linux Tauri system dependencies where needed, validates `tauri.conf.json`, runs `python3 scripts/validate_scaffold.py --verbose`, runs `python3 scripts/validate_release_assets.py --verbose`, builds the frontend, and runs `npm run tauri:build -- --no-bundle --ci --no-sign` unless disabled for a manual run.

The workflow deliberately uses `contents: read` and does not create or mutate releases. Missing signing secrets are reported in the dry-run summary and do not fail the job.

## GitHub Actions Release

Workflow: `.github/workflows/release.yml`

Trigger:

- Push a tag matching `v*`.

The release workflow runs macOS, Linux, and Windows jobs, installs platform dependencies, validates scaffold/release contracts, builds Tauri bundles with `npm run tauri:build -- --ci --no-sign`, collects installer artifacts from `target/release/bundle`, generates per-platform SHA-256 checksum files, and publishes a GitHub Release with aggregate checksums.

Release assets built without signing/notarization secrets are public validation artifacts. Do not present them as signed production installers. Configure platform signing and notarization before promoting a candidate to a stable production release.

## Version and Tag Policy

- Keep `apps/desktop/package.json`, `apps/desktop/package-lock.json`, `apps/desktop/src-tauri/Cargo.toml`, and `apps/desktop/src-tauri/tauri.conf.json` versions aligned before a real release.
- Use annotated tags in the form `vMAJOR.MINOR.PATCH` for public candidates.
- Do not create a public tag until CI, local smoke checks, and release workflow validation pass for the target commit.
- Do not retarget or force-push a published release tag. Create a new patch tag instead.

## Required Secrets

The dry-run workflow can run without any of these secrets. A real signed release needs platform credentials configured by repository administrators.

macOS signing and notarization:

- `APPLE_CERTIFICATE`
- `APPLE_CERTIFICATE_PASSWORD`
- `APPLE_SIGNING_IDENTITY`
- `APPLE_ID`
- `APPLE_PASSWORD`
- `APPLE_TEAM_ID`
- `APPLE_PROVIDER_SHORT_NAME`, if the Apple account requires it

Windows signing:

- `WINDOWS_CERTIFICATE`
- `WINDOWS_CERTIFICATE_PASSWORD`
- `WINDOWS_CERTIFICATE_THUMBPRINT`, if using certificate store based signing
- `WINDOWS_TIMESTAMP_URL`, if overriding the default timestamp service

Tauri updater signing, when updater artifacts become in scope:

- `TAURI_SIGNING_PRIVATE_KEY`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, if the key is encrypted

GitHub publishing for a future release workflow:

- Prefer the default `GITHUB_TOKEN` with the minimum required `contents: write` permission.
- Use a fine-grained PAT only if repository policy requires it.

## Artifacts

The dry-run uploads:

- `release-dry-run/release-preflight.md`
- `release-dry-run/release-preflight.json`
- `release-dry-run/<runner>-summary.md`
- `apps/desktop/dist/**`
- any compile-only desktop binary matching `target/release/lizzieyzy-next-desktop*`
- `target/release/bundle/**` if a future workflow enables bundling

For the `v0.1.0` public validation release, expected platform artifacts are unsigned CI-built bundles:

- macOS: `.app` inside `.dmg`, unsigned and not notarized unless signing secrets are configured.
- Windows: NSIS/MSI installer or portable executable, unsigned unless signing secrets are configured.
- Linux: AppImage, deb, or rpm, with runtime dependencies documented.

Every uploaded artifact should be tied to the exact tag, commit SHA, platform, and signing state in the release notes.

The production workflow also uploads `SHA256SUMS.txt` and `SHA256SUMS-<platform>.txt` files for download verification.

The expected dry-run artifact contract is `lizzieyzy-next-desktop-<version>-<platform>-dry-run` as a naming stem for handoff records, plus metadata for commit SHA and signing state. Current workflow uploads diagnostic artifacts only; production installer naming must be verified again before a public release workflow is introduced.

## Windows/Linux Installed-App Smoke Evidence

`docs/qa/windows-unsigned-installed-app-smoke.json` and `docs/qa/linux-unsigned-installed-app-smoke.json` record scoped unsigned Windows/Linux installed-app launch smoke from `wimi321/lizzieyzy-next-tauri` GitHub run `25764095000` artifacts `release-dry-run-Windows` and `release-dry-run-Linux`. The central smoke gate passes for these per-platform records.

A valid scoped PASS record, as used for the current Windows/Linux evidence, must record for each platform:

- artifact path, SHA-256 hash, and size,
- exact launch command,
- process observation,
- window observation or explicit display-mode observation,
- dev-server absence,
- exit or terminate success,
- display mode such as physical display, VM display, Xvfb, or headless runner mode,
- false boundaries for production signing, notarization, updater readiness, official release publication, full release parity, and full legacy parity.

This evidence is unsigned release-dry-run installed-app smoke only. It does not replace Authenticode signing, macOS notarization, updater signing, official release publication, full production release validation, clean-machine manual release testing, provider/readboard/OCR parity, or full legacy parity.

## Signing and Notarization Policy

Unsigned dry-run artifacts are for engineering validation only. The `v0.1.0` tag workflow may publish unsigned public validation artifacts, but the release notes must keep them marked as unsigned prerelease assets.

macOS production artifacts must use hardened runtime and notarization. After notarization, staple the ticket and smoke-test the app on a clean macOS machine before publishing.

Windows production artifacts must be Authenticode signed and timestamped. Smoke-test installer launch, install, uninstall, and first app launch on a clean Windows VM.

Linux artifacts may remain unsigned until a repository/package signing path exists, but the release notes must state the packaging format and dependency expectations.

## Rollback Strategy

If a release candidate fails before public publication:

- Delete only draft release artifacts generated for that candidate.
- Keep the failed tag only if external automation has already consumed it; otherwise delete the unpublished local/remote tag according to maintainer policy.
- Fix forward on a new commit and rerun the dry-run.

If a public release must be rolled back:

- Mark the GitHub release as withdrawn or pre-release, depending on repository policy.
- Publish a new patch tag with the last known good code or a forward fix.
- Keep the original release notes and add a visible rollback notice with affected platforms, checksums, and replacement version.
- Do not overwrite installers in place; users and caches need immutable artifacts.

## Release Notes

Use `.github/release.yml` for generated note grouping, then manually add:

- tag and commit SHA,
- artifact list with platform and signing state,
- automated check results,
- manual smoke-test results,
- known limitations and migration notes.

Release notes must not claim full legacy parity or live Fox/Yike/readboard support until provider contract tests, readboard domain tests, and the relevant external-network or sidecar smoke checks have explicit acceptance evidence.
