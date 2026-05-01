# QA Report

## Batch Scope

This QA report covers the documentation and acceptance contract for the current Tauri 2 + Rust + TypeScript migration batch. It separates repository-level evidence from live external environment evidence:

- Implemented repository claim: offline provider/readboard contracts and runtime path plumbing can be documented when the owning code and tests land. The tracked command boundaries are `provider_fetch_yike`, `provider_fetch_fox`, `readboard_sidecar_probe`, and `readboard_sidecar_sync_snapshot`.
- Not-yet-validated live claim: real Yike/Fox external-network fetches and real readboard sidecar probe/sync require credentials, network, target client state, and sidecar process evidence.
- Release claim limit: do not describe the Next app as a 100% legacy replacement or as fully live-provider-ready from scaffold/preflight checks alone.
- UI claim limit: ProviderPanel is the expected UI surface for provider fetch, readboard probe, and readboard sync. If a build only exposes URL preview or payload import, fetch/probe/sync UI remains pending.

## Ownership Check

- Current branch ownership is multi-worker: Rust workspace, Tauri backend, TypeScript frontend, provider crates, readboard sidecar, release assets, and docs may all appear in the branch diff.
- Worker-C-Fix ownership for this pass is limited to QA/docs claim accuracy in `QA_REPORT.md` and `docs/**`.
- Code changes under `crates/**`, `apps/desktop/**`, package/build files, and workflows are treated as other-worker work; this pass documents their acceptance boundaries without reviewing, editing, or reverting them.

## Validation Matrix

| Area | Repository Evidence | Live Environment Evidence |
| --- | --- | --- |
| Scaffold contract | `python3 scripts/validate_scaffold.py --verbose` | Not applicable. |
| Release metadata/preflight | `python3 scripts/validate_release_assets.py --verbose` | Platform packaging/signing still requires real artifact builds. |
| Yike provider | Offline contract tests and `provider_fetch_yike` runtime command wiring/path checks, with exact package/filter recorded by the owner. | Real Yike account/session, network reachability, resource fetch, auth expiry, timeout, and failure-mode smoke remain pending until manually executed. |
| Fox provider | Offline contract tests and `provider_fetch_fox` runtime command wiring/path checks for `chessid`, `uid`, and `user_name`, with exact package/filter recorded by the owner. | Real Fox prerequisites/client/session, network reachability, resource fetch/capture, unavailable-client/session, timeout, and failure-mode smoke for all supported command shapes remain pending until manually executed. |
| readboard probe | Domain tests plus `readboard_sidecar_probe` runtime command wiring/path checks, with exact package/filter recorded by the owner. | Real sidecar process, version/port/path, target client/window state, probe ready/not-running/incompatible/timeout behavior remain pending until manually executed. |
| readboard sync | Domain tests plus `readboard_sidecar_sync_snapshot` protocol line sync/runtime command wiring checks, with exact package/filter recorded by the owner. | Real sidecar sync, board coordinates, move state, restart/target-state changes, timeout, and crash handling remain pending until manually executed. |
| image OCR | Image-only sync returns a structured unsupported/not-implemented error when OCR is unavailable. | OCR is SKIPPED/UNSUPPORTED unless an OCR-capable runtime and image fixture evidence are available. |
| Legacy parity | Documented as partial migration only. | Full parity requires explicit evidence for providers, settings, packaging, and advanced review workflows. |

## Manual Smoke Additions

The release and development docs now require explicit manual smoke entries for:

- Yike runtime fetch success and auth/network failure modes.
- Fox `chessid`, `uid`, and `user_name` runtime fetch success and unavailable-client/session/network failure modes.
- readboard sidecar probe ready/not-running/incompatible/timeout states.
- readboard protocol line sync from a real board state, including restart or target-state changes.
- image OCR unavailable as a structured unsupported/not-implemented error.
- Boundary-specific failure reporting for provider auth, provider network, sidecar process, sidecar protocol, Tauri command, cache, engine, and DTO normalization errors.

## Manual Smoke Matrix

| Scenario | Required Result |
| --- | --- |
| Yike fetch success | `provider_fetch_yike` returns normalized provider DTOs for a real Yike resource; account/session, network, result count, and latency are recorded. |
| Yike fetch failure | Missing/expired auth, blocked network, timeout, malformed payload, or invalid request returns structured errors and no stale live-success claim. |
| Fox `chessid` fetch success | `provider_fetch_fox` returns normalized DTOs for a real `chessid` path. |
| Fox `uid` fetch success | `provider_fetch_fox` returns normalized DTOs for a real `uid` path. |
| Fox `user_name` fetch success | `provider_fetch_fox` resolves a real nickname path and records found/not-found behavior. |
| Fox fetch failure | Unavailable client/session, blocked network, timeout, bad command, malformed payload, or invalid request returns structured errors. |
| readboard sidecar missing probe | `readboard_sidecar_probe` reports unavailable/not-running/timeout without changing board state. |
| readboard sidecar present probe | `readboard_sidecar_probe` reports ready with sidecar version/path/latency recorded. |
| readboard protocol line sync | `readboard_sidecar_sync_snapshot` normalizes protocol line snapshot data into board state DTOs. |
| image OCR unavailable | Image-only sync returns structured unsupported/not-implemented error; OCR is not claimed live unless separately validated. |

## Local verification

- `python3 scripts/validate_scaffold.py --verbose`: PASS, 10 passed, 0 failed.
- `python3 scripts/validate_release_assets.py --verbose`: PASS, 4 passed, 0 failed.

## Unverified External Conditions

- Real Yike service access, credentials/session behavior, and provider rate-limit/network behavior.
- Real Fox client/session/capture prerequisites and provider network behavior.
- Real readboard sidecar installation, compatible version, target client/window state, and protocol behavior.
- Platform release packaging, signing, notarization, installer behavior, and clean-machine startup.
