# Legacy Parity Matrix

This matrix is the machine-checkable parity ledger for LizzieYzy Next against the Java/Swing legacy baseline. It is seeded from the current Planner findings in the architecture, migration, development, and release docs, plus the legacy main feature areas that users depend on.

Status tokens are intentionally narrow:

- `complete`: repository evidence supports the named legacy behavior for the scoped row.
- `partial`: the main path exists, but fixtures, edge cases, UI automation, or migration breadth are incomplete.
- `missing`: no accepted Next implementation or acceptance evidence exists yet.
- `external-validation-needed`: repository evidence may exist, but live provider, sidecar, platform, signing, or environment proof is required before claiming parity.

Do not use this matrix to claim full Java/Swing parity. A row reaches parity only when its acceptance evidence is recorded and any external gate is passed.

## UI

| Legacy Capability | Current Status | Acceptance Evidence | External Gate | Notes |
| --- | --- | --- | --- | --- |
| Main board review view with move navigation and visual board state | `partial` | Browser or Tauri smoke shows SGF load, board render, next/previous navigation, captures, pass moves, comments, and stable coordinates against golden SGF fixtures. | UI automation evidence for the primary desktop smoke flow. | React board and analysis surfaces exist, but complete layout/theme parity and shortcut breadth are not closed. |
| Analysis panel, winrate chart, candidate moves, PV display, and problem markers | `partial` | Tauri smoke records one-position and full-game analysis updating candidate moves, PV, ownership/policy data where available, winrate chart, and review markers without stale state. | Controlled KataGo or mock-process UI integration coverage. | MVP paths are present; advanced review workflows and every legacy shortcut remain open. |
| ProviderPanel as provider/readboard control surface | `partial` | ProviderPanel exposes provider fetch, readboard probe, and readboard sync controls, and shows structured success/unavailable/error states without UI-only shortcuts. | Live Fox/Yike/readboard smoke before live support is claimed. | If a build only offers URL preview or payload import, fetch/probe/sync UI remains pending. |

## SGF And Editing

| Legacy Capability | Current Status | Acceptance Evidence | External Gate | Notes |
| --- | --- | --- | --- | --- |
| SGF parse, replay, and board-state reconstruction | `complete` | Rust SGF and Go-domain tests pass against golden fixtures for FF4, 19x19 play, variations, comments, setup stones, captures, pass, suicide, and simple ko behavior. | None. | Current evidence supports the scoped MVP compatibility set, not every historical SGF edge case. |
| SGF tree, variations, and comments panel | `partial` | Acceptance requires API/DTO tests for stable tree node ids, parent/child variation links, move indexes, selected-node lookup, comment text exposure/save, branch node position replay, append move/pass as child or sibling variation, and UI smoke showing tree navigation, variation selection, comments panel updates, comment save, branch position display, and append move/pass behavior from golden SGF fixtures. | UI automation must prove comment save, branch navigation, append move/pass, and SGF reopen round-trip before broader edit parity is claimed. | Supports comment save, branch position replay, and append move/pass as a child or sibling variation as an SGF editing foundation. Delete/reorder variations, edit existing moves/properties, full annotation editing, legacy import/capture helpers, and broader SGF editing parity remain incomplete. |
| Native SGF open and save workflow | `partial` | Tauri desktop smoke opens a real SGF through native file I/O, replays it, saves it, reopens the saved file, and confirms stable mainline content. | Desktop runtime smoke on each release target. | Browser preview is not native file-dialog evidence. |
| Editing, annotation, and legacy import/capture helpers | `missing` | Acceptance requires tests and smoke evidence for editing moves/properties/comments, annotation persistence, and legacy capture/import helpers beyond the current SGF flows. | Legacy fixture comparison for migrated helper behavior. | Append move/pass foundation is tracked in the SGF tree row only. Delete/reorder variations, edit existing moves/properties, full annotation editing, and legacy import/capture helpers remain incomplete, so this broader row stays missing. |

## KataGo

| Legacy Capability | Current Status | Acceptance Evidence | External Gate | Notes |
| --- | --- | --- | --- | --- |
| Engine profile setup and asset validation | `partial` | Tauri smoke records binary, model, config, working directory, visits, asset-check success/failure, persisted profile reload, and clear validation errors. | OS-specific desktop smoke with local or bundled assets. | Multiple engine profiles and asset checks are present; full legacy settings migration is separate. |
| One-shot KataGo analysis | `partial` | `Run KataGo` in Tauri receives normalized JSONL analysis frames for the selected move, updates UI state, and records stderr/error propagation for failure cases. | Controlled KataGo fixture or real engine smoke with version/model details. | Repository DTO/protocol paths exist, but broad integration evidence is still needed. |
| Full-game analysis, progress, cancellation, and cache interaction | `partial` | Full-game batch analysis emits progress, supports cancellation, saves cache records, reloads cache hits, and does not report canceled work as success. | Long-running desktop smoke with cache verification. | MVP batch/cancel/cache paths exist; resilience coverage remains open. |

## Provider And readboard

| Legacy Capability | Current Status | Acceptance Evidence | External Gate | Notes |
| --- | --- | --- | --- | --- |
| Yike provider fetch through `provider_fetch_yike` | `external-validation-needed` | Repository evidence requires offline contract tests and runtime path checks returning normalized DTOs or typed `ProviderError` values without UI-only shortcuts. | Fetch a real Yike resource and record account/session type, network conditions, result count, latency, and login/session-expiry behavior. | Offline path evidence is not live provider parity. |
| Fox provider fetch through `provider_fetch_fox` | `external-validation-needed` | Repository evidence requires contract tests for `chessid`, `uid`, and `user_name`, plus runtime path checks for structured success/error results. | Fetch real Fox resources for each command shape and record target client/session state, blocked/expired-session behavior, result count, and latency. | Live Fox behavior depends on external provider state. |
| readboard sidecar probe through `readboard_sidecar_probe` | `external-validation-needed` | Domain tests and path checks prove structured ready/not-ready/runtime-unavailable/incompatible/timeout states. | Start a real sidecar, probe it through Tauri, and record process version, port/path, timeout behavior, and unavailable-sidecar handling. | A callable probe path is not sidecar parity. |
| readboard protocol sync through `readboard_sidecar_sync_snapshot` | `external-validation-needed` | Domain tests prove protocol-line parsing and DTO normalization for board size, stones, move state, player-to-play, typed protocol errors, and timeout/cancel behavior. | Sync from a real target client/window state, verify board coordinates and move state, then repeat after sidecar restart or target-state change. | OCR image sync remains unsupported unless an OCR-capable sidecar/runtime is validated. |

## Settings

| Legacy Capability | Current Status | Acceptance Evidence | External Gate | Notes |
| --- | --- | --- | --- | --- |
| Engine profile persistence in app data | `partial` | Tauri smoke creates, reloads, edits, and deletes profiles, then verifies persisted fields survive app restart and invalid paths produce clear errors. | Desktop runtime smoke on each supported OS. | Current persistence covers engine profiles, not every legacy preference. |
| Analysis cache storage and lookup | `partial` | Cache tests and smoke verify stable SGF cache keys, profile/engine filtering, save, lookup, delete, cache-hit UI state, and no stale analysis after SGF changes. | Cache migration evidence once storage schema stabilizes. | MVP SQLite cache exists. |
| Full Java/Swing configuration migration | `missing` | Acceptance requires a documented mapping from legacy config files to Next settings, migration tests for representative old configs, and rollback/error behavior. | Real user config migration smoke before release claims. | This remains separate from new app-data settings. |

## Packaging

| Legacy Capability | Current Status | Acceptance Evidence | External Gate | Notes |
| --- | --- | --- | --- | --- |
| Release metadata and dry-run preflight | `complete` | `python3 scripts/validate_release_assets.py --verbose` passes and the release dry-run workflow remains read-only, unsigned, compile-only, and artifact-contract checked. | None for dry-run metadata. | This validates release metadata, not production installers. |
| Production Tauri packaging for Windows, macOS, and Linux | `external-validation-needed` | Acceptance requires `npm run tauri:build` or equivalent release build per platform, artifact inspection, launch smoke, and recorded platform dependencies. | Signing, notarization, installer metadata, updater strategy, and platform-specific installer smoke. | Production packaging is not complete from dry-run evidence. |
| Bundled KataGo/runtime asset layout | `missing` | Acceptance requires documented bundled engine/model/config paths, asset validation, platform packaging inclusion checks, and runtime smoke using bundled assets. | Platform artifact inspection and engine launch from installed app. | Current engine support assumes configured local assets unless bundling is explicitly implemented. |
