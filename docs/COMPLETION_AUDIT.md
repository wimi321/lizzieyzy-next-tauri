# Completion Audit

Current as of this docs sync: the repository has strong scoped evidence, but LizzieYzy Next is not fully complete and is not ready to be described as full Java/Swing parity or a production release. The central user-flow smoke gate currently reports `60 passed, 0 failed, 0 pending`; that means the recorded scoped gates are internally consistent, not that every legacy workflow, platform, provider, OCR path, signing path, or release path is finished. `docs/qa/release-readiness-preflight.json` still records the preflight baseline that excludes the completion-audit validation gate itself.

## Completion Criteria

LizzieYzy Next can only be called complete when the user-facing legacy workflows, release-target installed apps, production release process, and external integrations have evidence at the same scope as the claim. In practice, completion requires full UI/menu/shortcut/layout comparison, SGF editing round-trip proof on release targets, live KataGo validation on supported platforms, real provider/readboard/OCR validation where claimed, full config migration mapping and rollback exercise, and signed/notarized/updater/release publication evidence before those words appear in release notes.

Passing scoped smoke gates is a prerequisite, not the final definition of completion. A row below may be a scoped pass while still having blockers that prevent a global completion or full parity claim.

## Evidence

Representative committed evidence with `status=pass` includes:

| Evidence file | Scope |
| --- | --- |
| `docs/qa/release-readiness-preflight.json` | Scoped release-readiness preflight with false/external boundaries. |
| `docs/qa/tauri-runtime-ui-smoke-macos.json` | macOS Tauri runtime SGF edit/save/reopen semantics. |
| `docs/qa/installed-app-sgf-workflow-macos.json` | Packaged macOS app SGF workflow automation. |
| `docs/qa/windows-unsigned-installed-app-smoke.json` | Scoped unsigned Windows installed-app launch/window evidence. |
| `docs/qa/linux-unsigned-installed-app-smoke.json` | Scoped unsigned Linux installed-app launch/window evidence. |
| `docs/qa/readboard-target-window-screenshot-smoke-macos.json` | Scoped controlled local target-window screenshot fixture evidence, not real target-client parity. |

## User-Facing Completion Ledger

| Area | Status | Evidence | Boundary | Blocker | Next step |
| --- | --- | --- | --- | --- | --- |
| UI parity, menu, shortcuts, and layout | Scoped partial pass | Browser DOM/click screenshots, LegacyShell menu-action evidence, macOS native menu/shortcut surface evidence, Tauri WebView DOM/click evidence, layout screenshots, and UI/menu/shortcut gap-closure evidence are recorded. | Not pixel-perfect layout parity, not full shortcut parity, not full OS-native menu parity, not full LegacyShell parity, and not full legacy UI parity. | Release-target exploratory UI behavior and complete legacy shortcut/layout comparison are still missing. | Run a release-target UI parity pass on packaged apps, compare legacy screens/workflows, and record remaining shortcut/layout deltas. |
| SGF editing and persistence | Scoped partial pass | SGF parse/replay tests, annotation persistence for TR/SQ/CR/MA/SL/LB/AR/LN, edit/reorder/delete/save-readback runtime evidence, native desktop manual-assisted workflow evidence, packaged SGF workflow automation, and packaged native dialog SGF evidence are recorded. | Not full native dialog parity, not Windows/Linux release-target SGF workflow parity, and not every historical SGF edge case. | Broader cross-platform installed-app SGF workflow evidence and exploratory user editing scenarios remain incomplete. | Re-run SGF workflow smoke on release candidates for macOS/Windows/Linux and add targeted historical SGF edge-case fixtures. |
| KataGo setup, analysis, and cache | Scoped partial pass | Live macOS KataGo CLI/Tauri evidence, live desktop workflow evidence, installed-app live KataGo workflow evidence, scoped CI-verifiable stale-guard evidence for SGF edit-version/job cleanup/stale-result ignore, progress/cancel/restart/cache/error evidence, and setup/asset surface checks are recorded. | Not full legacy analysis parity, not bundled large-model parity, not guaranteed bundled engine launch success, and not Windows/Linux live KataGo proof. | Large models are not bundled; bundled installed-app resources are still allowed to be unavailable; cross-platform live engine validation is incomplete. | Record Windows/Linux live KataGo workflow evidence, decide the bundled-engine/model distribution strategy, and compare legacy analysis workflows feature by feature. |
| Readboard, OCR, and capture | Scoped partial pass | Readboard sidecar probe/protocol evidence, controlled image import path/base64 evidence, controlled OCR corpus evidence, local-image backend decode evidence, operator-selected preview/confirm/import evidence, controlled local target-window screenshot fixture evidence, and runtime-backed controlled arbitrary screenshot board-region OCR evidence are recorded. A standalone selected-window capture validator is prepared, but it is not central PASS evidence until true runtime JSON is recorded. | Not arbitrary live screenshot OCR, not target-client discovery, not real external client/window parity, not full readboard parity, and not full legacy OCR parity. | Real arbitrary capture/OCR, selected-window runtime evidence, and target-client discovery are not proven. | Add runtime gates for arbitrary live screenshots, external windows/clients, selected-window capture evidence, target-client metadata, cross-platform capture, and legacy OCR fixture comparison. |
| Fox/Yike providers | Scoped controlled-network pass, external validation needed | Controlled-network provider smoke records Yike/Fox fetch paths, typed failure modes, request observation, and offline-parser exclusion. | Not real Fox/Yike service parity, not account/session proof, not anti-bot stability, and not service schema drift coverage. | Real service credentials/session states and live service behavior are still external. | Run real-service provider smoke with account/session metadata, rate-limit/session-expiry cases, and current service schema checks. |
| Legacy config migration | Scoped partial pass | Migration UI/API surface, transactional/no-write/rollback fields, and corpus evidence for representative fixture classes are recorded. | Not full Java/Swing config parity, not real-user migration proof, and not real rollback-failure exercise. | Exhaustive historical config corpus and real-user migration testing are incomplete. | Expand fixture corpus from real legacy configs, exercise rollback failures, and document setting-by-setting mapping coverage. |
| Packaging and installed apps | Scoped partial pass | macOS installed app launch/window, installed runtime workflow, installed SGF workflow, installed live KataGo workflow, Windows/Linux unsigned installed-app launch/window evidence, and multiplatform packaging smoke are recorded. | Not production signed/notarized release, not updater readiness, not official release publication, not store distribution, and not full production release validation. | Signing, notarization, updater signing, official publishing, and clean-machine production release testing remain blockers. | Complete signing/notarization/updater plan, run clean-machine release candidate smoke on all platforms, and publish only after release notes preserve unsigned/scoped limitations. |
| Release readiness and claims | Scoped preflight pass | `release_readiness_preflight` records the central smoke baseline and explicit false/external boundaries for signing, notarization, updater, official release, full production, full legacy, provider, readboard, OCR, and bundled large model claims. | Passing scoped evidence is not a full completion claim and not formal release readiness. | Public release claims need production artifacts, signing/notarization decisions, updater policy, and remaining external parity gates. | Keep release notes, README, QA report, and parity matrix aligned with scoped evidence; do not promote to stable release until blockers above are closed. |

## Missing Blockers

- Full legacy UI/layout/menu/shortcut parity has not been proven.
- Full legacy analysis parity has not been proven.
- Arbitrary live screenshot OCR, selected-window runtime capture evidence, target-client discovery, and real external client/window capture have not been proven.
- Real Fox/Yike account/service parity has not been proven.
- Full Java/Swing config migration parity has not been proven.
- Bundled large KataGo models are not included, and bundled engine launch success is not guaranteed by the current scoped evidence.
- Signing, notarization, updater readiness, official release publication, and full production distribution remain incomplete.
- Windows/Linux evidence is currently scoped unsigned installed-app launch/window evidence, not signed production release evidence.

## Next Engineering Route

1. Close release-blocking packaging work: signing/notarization/updater policy, clean-machine smoke, platform artifact naming, and release-note wording.
2. Expand cross-platform installed-app workflow evidence for SGF, KataGo, readboard/capture, and provider surfaces.
3. Convert scoped OCR/capture MVP, controlled target-window fixture evidence, runtime-backed controlled arbitrary screenshot board-region OCR evidence, and selected-window validator preparation into real runtime target-client validation.
4. Run real Fox/Yike service checks with account/session state and failure modes.
5. Grow the legacy config corpus and exercise rollback-failure paths.
6. Perform a deliberate legacy UI/layout/shortcut comparison pass and track remaining user-visible deltas.
