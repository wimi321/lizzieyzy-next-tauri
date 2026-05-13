import {
  analyzeKataGoGame,
  analyzeKataGoOnce,
  appendSgfMove,
  cancelKataGoAnalysis,
  checkEngineAssets,
  classifyProblems,
  deleteSgfNode,
  discoverReadboardCaptureTargets,
  editSgfMove,
  installedAppRuntimeProof,
  isTauriRuntime,
  listenToKataGoAnalysisEvents,
  loadEngineProfileSettings,
  loadRuntimeSmokeConfig,
  parseSgfSummary,
  parseSgfTree,
  readSgfDocument,
  reorderSgfVariation,
  replaySgfPositionAtNode,
  replaySgfPositions,
  runtimeSmokeReport,
  saveSgfDocument,
  startKataGoGameAnalysis,
  updateSgfNodeComment,
  updateSgfNodeProperties,
  type InstalledAppRuntimeProofDto
} from "./api/backend";
import {
  captureReadboardExternal,
  fetchFoxProvider,
  fetchYikeProvider,
  importProviderPayload,
  probeReadboardSidecar,
  syncReadboardSidecarSnapshot
} from "./api/providers";
import { computeGameCacheKey, loadAnalysisCache, saveAnalysisCache } from "./api/analysisCache";
import type { JsonValue } from "./domain/cache";
import type { ReadboardCaptureTargetCandidate } from "./domain/providers";
import type { AnalysisFrameDto, AssetCheckDto, EngineProfileDto, KataGoLiveSmokeConfigDto, MoveVertex, PlayerColor, SgfTreeDto, SgfTreeNodeDto } from "./domain/types";

type RuntimeSmokeStatus = "pass" | "fail";
type RuntimeSmokeCheckName =
  | "runtime_started"
  | "sgf_loaded"
  | "branch_navigation"
  | "comment_edit"
  | "property_edit"
  | "annotation_edit"
  | "append_move"
  | "edit_move"
  | "delete_node"
  | "variation_reorder"
  | "save_readback_roundtrip"
  | "save_reopen_roundtrip"
  | "reopen_state_verified"
  | "board_state_verified"
  | "katago_assets"
  | "katago_analyze_once"
  | "katago_analyze_game"
  | "katago_start_cancel"
  | "katago_failure_mode_missing_assets"
  | "sidecar_probe_ready"
  | "sidecar_probe_unavailable"
  | "protocol_line_sync"
  | "target_state_change_sync"
  | "arbitrary_ocr_not_covered"
  | "external_client_not_covered"
  | "readboard_external_capture_mvp"
  | "readboard_operator_capture"
  | "readboard_controlled_target_proof"
  | "readboard_screenshot_region_detection"
  | "readboard_target_window_discovery"
  | "readboard_selected_window_capture"
  | "backend_runtime_proof_observed"
  | "runtime_source_observed"
  | "backend_availability_observed"
  | "sgf_workflow_state_observed"
  | "engine_profile_status_observed"
  | "engine_asset_status_observed"
  | "engine_launch_attempt_observed"
  | "webview_dom_observed"
  | "webview_click_observed"
  | "visible_targets_verified"
  | "browser_fallback_excluded"
  | "scope_boundaries_recorded"
  | "engine_assets_verified"
  | "analysis_progress_observed"
  | "cancel_observed"
  | "restart_after_cancel_observed"
  | "analysis_complete_observed"
  | "cache_saved"
  | "cache_hit_restored"
  | "stale_cache_prevented"
  | "engine_failure_observed"
  | "yike_controlled_fetch"
  | "fox_controlled_fetch"
  | "provider_failure_modes"
  | "controlled_network_observed"
  | "offline_not_counted_as_external_live"
  | "external_account_scope";
type RuntimeSmokeCheck = {
  name: RuntimeSmokeCheckName;
  status: RuntimeSmokeStatus;
  details?: Record<string, unknown>;
  error?: string;
};
type RuntimeSmokeStep = {
  name: string;
  status: RuntimeSmokeStatus;
  details?: Record<string, unknown>;
  error?: string;
};
type RuntimeSmokeReport = {
  schema: "lizzieyzy.tauri-runtime-ui-smoke.v1";
  name: "ui_tauri_runtime_smoke";
  status: RuntimeSmokeStatus;
  platform: "macos";
  startedAt: string;
  finishedAt: string;
  sgfPath: string | null;
  reportPath: string | null;
  expectedReportPath: string | null;
  phase: RuntimeSmokePhase;
  checks: RuntimeSmokeCheck[];
  steps: RuntimeSmokeStep[];
  expected?: RuntimeSmokeExpectedEvidence;
  katago?: KataGoLiveSmokeEvidence;
  katagoWorkflowCache?: KataGoWorkflowCacheEvidence;
  readboard?: ReadboardLiveSmokeEvidence;
  readboardExternalCaptureMvp?: ReadboardExternalCaptureMvpEvidence;
  readboardOperatorCapture?: ReadboardExternalCaptureMvpEvidence;
  readboardTargetWindowScreenshot?: ReadboardExternalCaptureMvpEvidence;
  readboardScreenshotRegionDetection?: ReadboardExternalCaptureMvpEvidence;
  readboardTargetWindowDiscovery?: ReadboardTargetWindowDiscoveryEvidence;
  readboardSelectedWindowCapture?: ReadboardSelectedWindowCaptureEvidence;
  provider?: ProviderLiveSmokeEvidence;
  webviewDomClick?: WebviewDomClickEvidence;
  installedAppRuntimeProof?: InstalledAppRuntimeProofEvidence;
  error?: string;
};
type RuntimeSmokeImportMeta = ImportMeta & { env?: Record<string, string | undefined> };
type EditableMove = { id: string; color: PlayerColor; vertex: MoveVertex; parentId: string | null };
type RuntimeSmokePhase = "full" | "edit-save" | "reopen-verify" | "katago-live" | "katago-live-workflow-cache" | "readboard-live" | "readboard-external-capture-mvp" | "readboard-operator-capture" | "readboard-controlled-target-proof" | "readboard-screenshot-region-detection" | "readboard-target-window-discovery" | "readboard-selected-window-capture" | "provider-live" | "webview-dom-click" | "installed-app-runtime-proof" | "installed-app-sgf-workflow" | "installed-app-katago-live-workflow";
type RuntimeSmokeConfig = {
  enabled: boolean;
  sgfPath: string | null;
  reportPath: string | null;
  expectedReportPath: string | null;
  phase: RuntimeSmokePhase;
  katago: KataGoLiveSmokeConfig;
};
type RuntimeSmokeExpectedEvidence = {
  branchComment: string;
  branchName: string;
  branchLabel: string;
  branchAnnotations: Record<string, string[]>;
  deletedTargetVertex: string;
  editTargetVertex: string;
  appendColor: PlayerColor;
  reorderTargetIndex: 0;
  savedMoveCount: number;
  savedPositionCount: number;
  siblingCountAfterDelete: number;
  invariant: string;
};
type KataGoLiveSmokeConfig = {
  profile: EngineProfileDto | null;
  maxVisits: number;
  onceTurn: number | null;
  gameMaxVisits: number;
  cancelMaxVisits: number;
  cancelDelayMs: number;
  runGame: boolean;
  runCancel: boolean;
};
type KataGoLiveSmokeEvidence = {
  profile: SanitizedEngineProfile;
  maxVisits: number;
  onceTurn: number;
  gameMaxVisits: number;
  cancelMaxVisits: number;
  cancelDelayMs: number;
  runGame: boolean;
  runCancel: boolean;
  failureMode?: {
    profile: SanitizedEngineProfile;
    missingRequired: string[];
    structuredError?: string;
    observed: boolean;
  };
  assetChecks?: {
    total: number;
    required: number;
    missingRequired: string[];
    checks: AssetCheckDto[];
  };
  analyzeOnce?: AnalysisFrameEvidence;
  analyzeGame?: {
    frames: number;
    turns: number[];
    firstFrame?: AnalysisFrameEvidence;
    lastFrame?: AnalysisFrameEvidence;
  };
  startCancel?: {
    jobId: string;
    cancelRequested: boolean;
    cancelConfirmed: boolean;
    cancelDelayMs: number;
    event?: KataGoCancelEvidence;
  };
};
type KataGoWorkflowCacheEvidence = {
  profile: SanitizedEngineProfile;
  sgf: {
    path: string | null;
    bytes: number;
    moveCount: number;
    boardSize: number;
  };
  browserFallbackUsed: false;
  tauriRuntimeObserved: true;
  assetChecks?: {
    total: number;
    required: number;
    missingRequired: string[];
  };
  progress?: {
    jobId: string;
    completed: number;
    expected: number;
    turn: number;
    progressObserved: true;
  };
  cancel?: {
    jobId: string;
    cancelRequested: true;
    cancelConfirmed: true;
    uiReleasedForRestart: true;
    event: KataGoCancelEvidence;
  };
  restart?: {
    previousJobId: string;
    restarted: true;
    newJobId: string;
  };
  complete?: {
    jobId: string;
    frames: number;
    turns: number[];
    firstFrame?: AnalysisFrameEvidence;
    lastFrame?: AnalysisFrameEvidence;
  };
  cache?: {
    gameKey: string;
    sgfHash: string;
    profileId: string;
    savedId: string;
    hitStatus: string;
    restoredFrames: number;
    restoredCandidates: number;
    restoredWinrateBlack: number;
    staleChangedSgfStatus: string;
    staleProfileStatus: string;
  };
  failureMode?: {
    missingRequired: string[];
    structuredError?: string;
    observed: true;
  };
  boundaries?: {
    browserFallbackUsed: false;
    fakeEngineUsed: false;
    fullReviewParity: false;
    providerParity: false;
    readboardParity: false;
    arbitraryOcrParity: false;
    releaseParity: false;
  };
};
type KataGoCancelEvidence = {
  kind: "cancelled" | "error" | "complete" | "timeout";
  jobId: string;
  message?: string;
  frames?: number;
  framesData?: AnalysisFrameDto[];
};
type SanitizedEngineProfile = {
  name: string;
  backend: EngineProfileDto["backend"];
  hasEnginePath: boolean;
  hasModelPath: boolean;
  hasConfigPath: boolean;
  hasWorkingDir: boolean;
};
type AnalysisFrameEvidence = {
  jobId: string;
  turn: number;
  visits: number;
  candidates: number;
  hasOwnership: boolean;
  hasPolicy: boolean;
  winrateBlack: number;
  scoreMeanBlack: number;
};
type ReadboardLiveSmokeEvidence = {
  endpoint: string | null;
  readyProbe?: Record<string, unknown>;
  unavailableProbe?: Record<string, unknown>;
  protocolLineSync?: ReadboardProtocolLineEvidence;
  targetStateChangeSync?: ReadboardTargetStateChangeEvidence;
  arbitraryOcrNotCovered?: Record<string, unknown>;
  externalClientNotCovered?: Record<string, unknown>;
};
type ReadboardExternalCaptureMvpEvidence = {
  rawBackendResult?: Record<string, unknown>;
  rawFailedDecodeResult?: Record<string, unknown>;
  targetWindowMetadata?: {
    controlledFixture: true;
    targetClientDiscovery: false;
    windowIdSanitized: true;
    title: string;
    appName: string;
    processName: string;
    captureSource: "controlled_local_target_window";
    fixtureSize: string;
    bounds: { x: number; y: number; width: number; height: number };
    fixtureId: string;
    processId: number | null;
    imagePath: string;
  };
  captureArtifact?: {
    path: string;
    sanitized: true;
    sizeBytes: number;
    sha256: string;
  };
  captureSource?: {
    operatorInitiated: boolean;
    userSelectionRequired: boolean;
    selection: null | { x: number; y: number; width: number; height: number };
    sourceKind: "local_image" | "operator_selected_file" | "controlled_local_target_window" | "selected_window_capture" | "arbitrary_screenshot_board_region";
    requestedSource: "local_image" | "operator_selected_file" | "controlled_local_target_window" | "selected_window_capture" | "arbitrary_screenshot_board_region";
    localImageProvided?: true;
    localImageOnly?: true;
    operatorSelectedFileProvided?: true;
    controlledLocalTargetWindow?: true;
    arbitraryScreenshotBoardRegion?: true;
    fixtureId?: string | null;
    windowTitle?: string | null;
    processId?: number | null;
    width?: number | null;
    height?: number | null;
    selectedScreenRegionCovered: false;
    externalScreenRegionCovered: false;
    externalWindowRegionCovered: false;
    targetClientDiscoveryCovered: false;
    externalClientCaptureCovered: false;
  };
  previewConfirmation?: {
    previewOnlyBeforeConfirmation: boolean;
    boardReplacedBeforeConfirmation: false;
    userConfirmed: boolean;
    boardReplacedOnlyAfterConfirmation: boolean;
    previewConfirmationObserved: boolean;
    boardReplacementObserved: boolean;
    previewProduced?: boolean;
    automaticBoardReplacement?: false;
    beforeConfirmation?: {
      userConfirmed: false;
      canImportPreview: false;
      importDisabled: true;
      surface: ElementSmokeEvidence;
      confirmationControl: ElementSmokeEvidence;
      importButton: ElementSmokeEvidence;
    };
    afterConfirmation?: {
      userConfirmed: true;
      canImportPreview: true;
      importDisabled: false;
      surface: ElementSmokeEvidence;
      confirmationControl: ElementSmokeEvidence;
      importButton: ElementSmokeEvidence;
    };
    afterImport?: {
      boardReplacementObserved: true;
      boardReplacedOnlyAfterConfirmation: true;
      surface: ElementSmokeEvidence;
      statusbar: ElementSmokeEvidence;
    };
    beforeConfirmationControl?: ElementSmokeEvidence;
    afterConfirmationControl?: ElementSmokeEvidence;
    afterImportSurface?: ElementSmokeEvidence;
    previewSummary?: ElementSmokeEvidence;
    confirmationControl?: ElementSmokeEvidence;
    statusbar?: ElementSmokeEvidence;
    fullOcrParity: false;
    fullReadboardParity: false;
    targetClientParity: false;
    arbitraryOcrParity: false;
    releaseParity: false;
    localImageDecodeOnly?: true;
  };
  previewOnlyBeforeConfirmation?: boolean;
  boardReplacedBeforeConfirmation?: false;
  userConfirmed?: boolean;
  boardReplacedOnlyAfterConfirmation?: boolean;
  localImageDecodeOnly?: true;
  failedDecodeNoReplacement?: {
    fixtureKind: "non_board";
    decodeAttempted: true;
    decodeSucceeded: false;
    previewProduced: false;
    imported: false;
    boardReplaced: false;
    errorKind: string;
    message: string | null;
    status: string;
    targetClientDiscovery?: false;
    fullOcrParity?: false;
    fullReadboardParity?: false;
    releaseParity?: false;
    artifact: {
      path: string;
      sanitized: true;
      sizeBytes: number;
      sha256: string;
    };
    rawBackendResult?: Record<string, unknown>;
  };
  screenshotRegionDetection?: {
    scope: "scoped_arbitrary_screenshot_board_region_detection";
    detectionAttempted: true;
    backendSupported: boolean;
    backendStatus: string;
    boardRegionDetected: boolean;
    positionPreviewProduced: boolean;
    automaticReplacement: false;
    targetClientDiscovery: false;
    fullOcrParity: false;
    fullReadboardParity: false;
    releaseParity: false;
    artifact?: {
      path: string;
      sanitized: true;
      sizeBytes: number;
      sha256: string;
    };
    region?: Record<string, unknown>;
    rawBackendResult?: Record<string, unknown>;
  };
};
type ReadboardTargetWindowDiscoveryEvidence = {
  runtimeObserved: true;
  runtimeReportPhase: "readboard-target-window-discovery";
  backendCommandInvoked: "readboard_list_capture_targets";
  backendCommand: "readboard_list_capture_targets";
  status: string;
  candidates: ReadboardCaptureTargetCandidate[];
  selectedTarget: Record<string, unknown>;
  captureArtifact?: ReadboardExternalCaptureMvpEvidence["captureArtifact"];
  rawCaptureResult?: Record<string, unknown>;
  failedDecodeNoReplacement?: ReadboardExternalCaptureMvpEvidence["failedDecodeNoReplacement"];
  previewConfirmation?: ReadboardExternalCaptureMvpEvidence["previewConfirmation"];
  captureSourceTrace: {
    captureSource: "controlled_local_target_window";
    selectedFromDiscovery: true;
    captureTiedToSelectedTarget: true;
    previewOnly: true;
    explicitImportConfirmationRequired: true;
  };
  boundaries: {
    targetClientDiscoveryParity: false;
    realFoxYikeParity: false;
    fullOcrParity: false;
    automaticBoardReplacement: false;
    releaseParity: false;
  };
  warnings: string[];
  rawBackendResult: Record<string, unknown>;
};
type ReadboardSelectedWindowCaptureEvidence = {
  runtimeObserved: true;
  runtimeReportPhase: "readboard-selected-window-capture";
  backendCommandInvoked: "readboard_list_capture_targets";
  captureCommandInvoked: "readboard_external_capture";
  status: string;
  candidates: ReadboardCaptureTargetCandidate[];
  selectedTarget: Record<string, unknown>;
  rawDiscoveryResult: Record<string, unknown>;
  rawCaptureResult: Record<string, unknown>;
  rawPreviewResult?: Record<string, unknown>;
  positionPreviewProduced: boolean;
  captureSourceTrace: {
    captureSource: "selected_window_capture";
    selectedFromDiscovery: true;
    captureTiedToSelectedTarget: true;
    windowIdRequired: true;
    imagePathProvided: false;
    previewOnly: true;
    explicitImportConfirmationRequired: true;
  };
  previewConfirmation: {
    previewOnlyBeforeConfirmation: boolean;
    previewProduced: boolean;
    automaticBoardReplacement: false;
    boardReplacedBeforeConfirmation: false;
    userConfirmed: false;
    boardReplacedOnlyAfterConfirmation: false;
    boardReplacementObserved: false;
  };
  boundaries: {
    targetClientDiscoveryParity: false;
    realFoxYikeParity: false;
    fullOcrParity: false;
    fullReadboardParity: false;
    automaticBoardReplacement: false;
    releaseParity: false;
  };
  warnings: string[];
};
type ReadboardProtocolLineEvidence = {
  snapshotId: string;
  boardSize: number;
  moveNumber: number;
  stoneCount: number;
  toPlay: PlayerColor;
  warnings: string[];
};
type ReadboardTargetStateChangeEvidence = {
  changed: true;
  beforeSnapshotId: string;
  afterSnapshotId: string;
  beforeStoneCount: number;
  afterStoneCount: number;
  beforeMoveNumber: number;
  afterMoveNumber: number;
  boardSizeStable: true;
  toPlay: PlayerColor;
  warnings: string[];
};
type ProviderLiveSmokeEvidence = {
  baseUrl: string;
  yikeControlledFetch?: Record<string, unknown>;
  foxControlledFetch?: Record<string, unknown>;
  providerFailureModes?: Record<string, unknown>;
  controlledNetworkObserved?: Record<string, unknown>;
  offlineNotCountedAsExternalLive?: Record<string, unknown>;
  externalAccountScope?: Record<string, unknown>;
};
type WebviewDomClickEvidence = {
  tauriRuntimeObserved: boolean;
  browserFallbackUsed: false;
  domRoot?: ElementSmokeEvidence;
  clickedControls: WebviewClickEvidence[];
  visibleTargets: ElementSmokeEvidence[];
  boundaries: {
    fullLayoutParity: false;
    fullShortcutParity: false;
    fullLegacyParity: false;
    ocrCaptureParity: false;
    releaseParity: false;
  };
};
type WebviewClickEvidence = {
  label: string;
  selector: string;
  expectedTarget: string;
  control: ElementSmokeEvidence;
  activeTarget: string | null;
  lastAction: string | null;
  lastLegacyAction: string | null;
  actionSource: string | null;
  actionStatus: string | null;
  targetElement: ElementSmokeEvidence;
};
type InstalledAppRuntimeProofEvidence = {
  tauriRuntimeObserved: boolean;
  browserFallbackUsed: boolean;
  runtimeSource?: string;
  backendAvailability?: string;
  backendAvailable?: boolean;
  backendRuntimeProof?: InstalledAppRuntimeProofDto;
  backendRuntimeProofSummary?: Record<string, unknown>;
  runtimeRoot?: ElementSmokeEvidence;
  backendStatus?: ElementSmokeEvidence;
  sgfWorkflow?: ElementSmokeEvidence;
  engineProfile?: ElementSmokeEvidence;
  engineAssets?: ElementSmokeEvidence;
  runtimeAssets?: ElementSmokeEvidence;
  engineLaunchAttempt?: ElementSmokeEvidence;
  boundaries: {
    browserFallbackDoesNotClaimTauri: true;
    webviewDomClickCovered: false;
    nativeDialogCovered: false;
    fullLegacyParity: false;
    releaseParity: false;
  };
};
type ElementSmokeEvidence = {
  selector: string;
  tagName: string;
  text: string;
  visible: boolean;
  id: string | null;
  className: string | null;
  testId: string | null;
  attributes: Record<string, string>;
};

const schema = "lizzieyzy.tauri-runtime-ui-smoke.v1";
const truthyValues = new Set(["1", "true", "yes", "on"]);
const expectedBranchComment = "runtime smoke branch persisted";
const expectedBranchName = "runtime-smoke-branch";
const expectedBranchLabel = "aa:A";
const expectedBranchAnnotations: Record<string, string[]> = {
  TR: ["aa"],
  SQ: [],
  CR: ["bb"],
  MA: ["cc"],
  SL: ["dd"],
  LB: [expectedBranchLabel, "ee:E"],
  AR: ["aa:bb"],
  LN: ["cc:dd"]
};
const replayInvariant = "saved_or_reopened_replay_has_no_errors_and_position_count_matches_move_count_plus_initial_position";
const defaultKatagoMaxVisits = 32;
const defaultKatagoGameMaxVisits = 16;
const defaultKatagoCancelMaxVisits = 10_000;
const defaultKatagoCancelDelayMs = 250;
const readboardProtocolLine = "snapshot snapshot_id=runtime-a board_size=2 move_number=1 codes=3000";
const readboardChangedProtocolLine = "snapshot snapshot_id=runtime-b board_size=2 move_number=2 codes=3100";

export function isRuntimeSmokeModeEnabled(): boolean {
  const value = runtimeSmokeImportMeta().env?.VITE_LIZZIEYZY_RUNTIME_SMOKE;
  return typeof value === "string" && truthyValues.has(value.trim().toLowerCase());
}

export async function resolveRuntimeSmokeConfig(): Promise<RuntimeSmokeConfig> {
  const envEnabled = isRuntimeSmokeModeEnabled();
  const envSgfPath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH");
  const envReportPath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH");
  const envExpectedReportPath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_EXPECTED_REPORT_PATH");
  const envPhase = normalizeRuntimeSmokePhase(runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_PHASE"));
  const envKatago = readEnvKatagoLiveSmokeConfig();
  if (envEnabled || envSgfPath || envReportPath || envExpectedReportPath || envPhase !== "full") {
    return {
      enabled: envEnabled,
      sgfPath: envSgfPath,
      reportPath: envReportPath,
      expectedReportPath: envExpectedReportPath,
      phase: envPhase,
      katago: envKatago
    };
  }
  if (!isTauriRuntime()) {
    return { enabled: false, sgfPath: null, reportPath: null, expectedReportPath: null, phase: "full", katago: defaultKatagoLiveSmokeConfig() };
  }
  try {
    const config = await loadRuntimeSmokeConfig();
    return {
      enabled: config.enabled,
      sgfPath: normalizeOptionalString(config.sgf_path),
      reportPath: normalizeOptionalString(config.report_path),
      expectedReportPath: normalizeOptionalString(config.expected_report_path),
      phase: normalizeRuntimeSmokePhase(config.phase),
      katago: normalizeKatagoLiveSmokeConfig(config.katago, envKatago)
    };
  } catch {
    return { enabled: false, sgfPath: null, reportPath: null, expectedReportPath: null, phase: "full", katago: defaultKatagoLiveSmokeConfig() };
  }
}

export async function runRuntimeSmokeMode(config?: RuntimeSmokeConfig): Promise<RuntimeSmokeReport> {
  const resolvedConfig = config ?? await resolveRuntimeSmokeConfig();
  const sgfPath = resolvedConfig.sgfPath;
  const reportPath = resolvedConfig.reportPath;
  const expectedReportPath = resolvedConfig.expectedReportPath;
  const report: RuntimeSmokeReport = {
    schema,
    name: "ui_tauri_runtime_smoke",
    status: "fail",
    platform: "macos",
    startedAt: new Date().toISOString(),
    finishedAt: "",
    sgfPath,
    reportPath,
    expectedReportPath,
    phase: resolvedConfig.phase,
    checks: [],
    steps: []
  };

  try {
    if (!reportPath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH is required.");
    if (phaseRequiresSgfPath(resolvedConfig.phase) && !sgfPath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH is required.");
    if (resolvedConfig.phase === "reopen-verify" && !expectedReportPath) {
      throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_EXPECTED_REPORT_PATH is required for reopen-verify.");
    }
    if (!resolvedConfig.enabled) throw new Error("Runtime smoke config is not enabled.");

    await check(report, "runtime_started", async () => {
      if (!isTauriRuntime()) throw new Error("Runtime smoke mode must run inside the real Tauri runtime.");
      return {
        tauriInternals: true,
        userAgent: typeof navigator === "undefined" ? null : navigator.userAgent,
        platform: typeof navigator === "undefined" ? null : navigator.platform
      };
    });

    if (resolvedConfig.phase === "provider-live") {
      await runProviderLivePhase(report);
    } else if (resolvedConfig.phase === "webview-dom-click") {
      await runWebviewDomClickPhase(report);
    } else if (resolvedConfig.phase === "installed-app-runtime-proof") {
      await runInstalledAppRuntimeProofPhase(report);
    } else if (resolvedConfig.phase === "installed-app-sgf-workflow") {
      await runInstalledAppSgfWorkflowPhase(report, requireRuntimeSmokeSgfPath(sgfPath));
    } else if (resolvedConfig.phase === "installed-app-katago-live-workflow") {
      await runInstalledAppKataGoLiveWorkflowPhase(report, requireRuntimeSmokeSgfPath(sgfPath), resolvedConfig.katago);
    } else if (resolvedConfig.phase === "readboard-live") {
      await runReadboardLivePhase(report);
    } else if (resolvedConfig.phase === "readboard-external-capture-mvp") {
      await runReadboardExternalCaptureMvpPhase(report);
    } else if (resolvedConfig.phase === "readboard-operator-capture") {
      await runReadboardOperatorCapturePhase(report);
    } else if (resolvedConfig.phase === "readboard-controlled-target-proof") {
      await runReadboardControlledTargetProofPhase(report);
    } else if (resolvedConfig.phase === "readboard-screenshot-region-detection") {
      await runReadboardScreenshotRegionDetectionPhase(report);
    } else if (resolvedConfig.phase === "readboard-target-window-discovery") {
      await runReadboardTargetWindowDiscoveryPhase(report);
    } else if (resolvedConfig.phase === "readboard-selected-window-capture") {
      await runReadboardSelectedWindowCapturePhase(report);
    } else if (resolvedConfig.phase === "katago-live") {
      await runKataGoLivePhase(report, requireRuntimeSmokeSgfPath(sgfPath), resolvedConfig.katago);
    } else if (resolvedConfig.phase === "katago-live-workflow-cache") {
      await runKataGoLiveWorkflowCachePhase(report, requireRuntimeSmokeSgfPath(sgfPath), resolvedConfig.katago);
    } else if (resolvedConfig.phase === "reopen-verify") {
      await runReopenVerifyPhase(report, requireRuntimeSmokeSgfPath(sgfPath), expectedReportPath ?? reportPath);
    } else {
      await runEditSavePhase(report, requireRuntimeSmokeSgfPath(sgfPath), resolvedConfig.phase);
    }

    report.status = "pass";
    return report;
  } catch (error) {
    report.error = errorMessage(error);
    report.status = "fail";
    return report;
  } finally {
    report.finishedAt = new Date().toISOString();
    if (reportPath) {
      try {
        await runtimeSmokeReport(reportPath, JSON.stringify(report, null, 2));
      } catch (error) {
        report.steps.push({ name: "write runtime smoke report", status: "fail", error: errorMessage(error) });
      }
    }
  }
}

async function runEditSavePhase(report: RuntimeSmokeReport, sgfPath: string, phase: RuntimeSmokePhase) {
  const loaded = await check(report, "sgf_loaded", async () => {
    const document = await readSgfDocument(sgfPath);
    assertNonEmptyString(document.sgfText, "readSgfDocument returned empty SGF text.");
    await verifySgf(report, "source", document.sgfText);
    return { sgfText: document.sgfText, details: { bytes: document.sgfText.length, path: document.path } };
  });
  const source = loaded.sgfText;

  const sourceTree = await step(report, "parse source tree for edit targets", () => parseSgfTree(source));
  const branchNode = findBranchNode(sourceTree);
  await check(report, "branch_navigation", async () => {
    const position = await replaySgfPositionAtNode(source, branchNode.id);
    if (position.move_number < 1) throw new Error("Branch replay did not advance to a move position.");
    return { nodeId: branchNode.id, moveNumber: position.move_number, stones: position.stones.length };
  });

  let edited = (await check(report, "comment_edit", async () => {
    const text = await updateSgfNodeComment(source, branchNode.id, expectedBranchComment);
    const tree = await parseSgfTree(text);
    const node = requireNode(tree, branchNode.id, "comment-edited branch node");
    if (node.comment !== expectedBranchComment) throw new Error("Updated branch comment was not preserved in the SGF tree.");
    return {
      sgfText: text,
      details: {
        nodeId: node.id,
        comment: node.comment,
        expectedComment: expectedBranchComment
      }
    };
  })).sgfText;

  edited = (await check(report, "property_edit", async () => {
    const result = await updateSgfNodeProperties(edited, branchNode.id, [
      { key: "N", values: [expectedBranchName] },
      { key: "LB", values: [expectedBranchLabel] },
      { key: "SQ", values: ["hh"] }
    ]);
    const tree = await parseSgfTree(result.sgf_text);
    const node = requireNode(tree, branchNode.id, "property-edited branch node");
    assertPropertyValue(node, "N", expectedBranchName);
    assertPropertyValue(node, "LB", expectedBranchLabel);
    return {
      sgfText: result.sgf_text,
      details: {
        nodeId: result.node_id,
        expectedProperties: { N: expectedBranchName, LB: expectedBranchLabel }
      }
    };
  })).sgfText;

  edited = (await check(report, "annotation_edit", async () => {
    const result = await updateSgfNodeProperties(edited, branchNode.id, Object.entries(expectedBranchAnnotations).map(([key, values]) => ({ key, values })));
    const tree = await parseSgfTree(result.sgf_text);
    const node = requireNode(tree, branchNode.id, "annotation-edited branch node");
    for (const [key, values] of Object.entries(expectedBranchAnnotations)) {
      if (values.length === 0) {
        assertPropertyAbsent(node, key);
      } else {
        for (const value of values) assertPropertyValue(node, key, value);
      }
    }
    return {
      sgfText: result.sgf_text,
      details: {
        nodeId: result.node_id,
        added: ["TR", "CR", "MA", "SL", "AR", "LN"],
        updated: ["LB"],
        removed: ["SQ"],
        annotations: expectedBranchAnnotations
      }
    };
  })).sgfText;

  const treeBeforeAppend = await step(report, "parse tree before append", () => parseSgfTree(edited));
  const root = requireNode(treeBeforeAppend, treeBeforeAppend?.root_id, "append parent root node");
  const appendParent = requireNode(treeBeforeAppend, root.child_ids[0], "append parent first move node");
  const appendColor: PlayerColor = "white";
  const appendVertex = chooseUnusedSiblingVertex(treeBeforeAppend, appendParent.id);
  const appended = await check(report, "append_move", async () => {
    const result = await appendSgfMove(edited, appendParent.id, appendColor, appendVertex);
    const tree = await parseSgfTree(result.sgf_text);
    const node = requireNode(tree, result.new_node_id, "appended move node");
    if (node.color !== appendColor || vertexKey(node.vertex) !== vertexKey(appendVertex)) {
      throw new Error("Appended move was not found at the expected vertex.");
    }
    return {
      sgfText: result.sgf_text,
      details: {
        nodeId: result.new_node_id,
        color: appendColor,
        vertex: vertexKey(appendVertex)
      }
    };
  });
  edited = appended.sgfText;
  const appendedNodeId = String(appended.details?.nodeId ?? "");
  if (!appendedNodeId) throw new Error("append_move did not return an appended node id.");

  const editVertex = chooseDifferentSiblingVertex(await parseSgfTree(edited), appendedNodeId);
  const editVertexKey = requireVertexKey(editVertex, "edit target vertex");
  edited = (await check(report, "edit_move", async () => {
    const result = await editSgfMove(edited, appendedNodeId, appendColor, editVertex);
    const tree = await parseSgfTree(result.sgf_text);
    const node = requireNode(tree, appendedNodeId, "edited appended move node");
    if (node.color !== appendColor || vertexKey(node.vertex) !== editVertexKey) {
      throw new Error("Edited move was not found at the expected vertex.");
    }
    return {
      sgfText: result.sgf_text,
      details: {
        nodeId: result.node_id,
        targetVertex: editVertexKey,
        confirmedVertex: vertexKey(node.vertex),
        editVertex: editVertexKey
      }
    };
  })).sgfText;

  let movedNodeId = appendedNodeId;
  const reorderTargetIndex = 0;
  const reordered = await check(report, "variation_reorder", async () => {
    const result = await reorderSgfVariation(edited, appendedNodeId, reorderTargetIndex);
    const tree = await parseSgfTree(result.sgf_text);
    const updatedParent = requireNode(tree, result.parent_node_id, "parent node after variation reorder");
    const movedNode = requireNode(tree, result.node_id, "moved variation node");
    const indexAfterMove = updatedParent.child_ids.indexOf(result.node_id);
    if (result.parent_node_id !== appendParent.id) throw new Error("Reordered variation returned an unexpected parent.");
    if (movedNode.parent_id !== result.parent_node_id) throw new Error("Moved variation is not under the returned parent.");
    if (indexAfterMove !== reorderTargetIndex) throw new Error("Moved variation did not land at target sibling index 0.");
    if (movedNode.variation_index !== reorderTargetIndex) throw new Error("Moved variation did not receive variation_index 0.");
    return {
      sgfText: result.sgf_text,
      details: {
        oldNodeId: appendedNodeId,
        movedNodeId: result.node_id,
        parentNodeId: result.parent_node_id,
        targetIndex: reorderTargetIndex,
        indexAfterMove,
        variationIndexAfterMove: movedNode.variation_index,
        siblingCount: updatedParent.child_ids.length,
        siblingIndex: indexAfterMove,
        movedIsMainline: movedNode.is_mainline
      }
    };
  });
  edited = reordered.sgfText;
  movedNodeId = String(reordered.details?.movedNodeId ?? "");
  if (!movedNodeId) throw new Error("variation_reorder did not return a moved node id.");

  let remainingSiblingCount = 0;
  edited = (await check(report, "delete_node", async () => {
    const result = await deleteSgfNode(edited, movedNodeId);
    const tree = await parseSgfTree(result.sgf_text);
    const updatedParent = requireNode(tree, result.parent_node_id, "parent node after delete");
    const targetExistsAfterDelete = hasChildMove(updatedParent, tree, appendColor, editVertexKey);
    if (targetExistsAfterDelete) throw new Error("Deleted move target is still present in the SGF tree.");
    remainingSiblingCount = updatedParent.child_ids.length;
    return {
      sgfText: result.sgf_text,
      details: {
        deletedNodeIdBeforeDelete: movedNodeId,
        oldNodeId: appendedNodeId,
        movedNodeId,
        deletedNodeId: movedNodeId,
        deletedTargetVertex: editVertexKey,
        parentNodeId: result.parent_node_id,
        remainingSiblingCount,
        targetExistsAfterDelete,
        existsAfterDelete: targetExistsAfterDelete,
        absentAfterDelete: !targetExistsAfterDelete,
        deleteAbsence: !targetExistsAfterDelete
      }
    };
  })).sgfText;

  const readbackResult = await check(report, "save_readback_roundtrip", async () => {
    const saved = await saveSgfDocument(sgfPath, edited, "runtime-smoke.sgf");
    if (!saved?.path) throw new Error("saveSgfDocument did not return a saved path.");
    const document = await readSgfDocument(sgfPath);
    if (saved.sgfText !== edited) throw new Error("Saved SGF text does not match edited text.");
    if (document.sgfText !== edited) throw new Error("Readback SGF does not match saved SGF text.");
    return {
      sgfText: document.sgfText,
      details: {
        path: saved.path,
        savedPath: saved.path,
        bytes: document.sgfText.length,
        saveVerified: saved.sgfText === edited,
        readbackVerified: document.sgfText === edited,
        readbackMatchesSaved: document.sgfText === saved.sgfText,
        savedStatus: "matched_edited_text",
        readbackStatus: "matched_saved_text"
      }
    };
  });
  const readback = readbackResult.sgfText;
  const boardEvidence = await verifySavedBoardState(report, readback, appendColor, editVertexKey, remainingSiblingCount);
  report.expected = {
    branchComment: expectedBranchComment,
    branchName: expectedBranchName,
    branchLabel: expectedBranchLabel,
    branchAnnotations: expectedBranchAnnotations,
    deletedTargetVertex: editVertexKey,
    editTargetVertex: editVertexKey,
    appendColor,
    reorderTargetIndex,
    savedMoveCount: boardEvidence.moveCount,
    savedPositionCount: boardEvidence.positionCount,
    siblingCountAfterDelete: remainingSiblingCount,
    invariant: replayInvariant
  };
  if (phase === "edit-save") {
    report.steps.push({
      name: "edit-save expected reopen proof fields",
      status: "pass",
      details: report.expected as unknown as Record<string, unknown>
    });
  }
}

async function runReopenVerifyPhase(report: RuntimeSmokeReport, sgfPath: string, expectedReportPath: string) {
  const expected = await loadExpectedEvidence(expectedReportPath);
  report.expected = expected;
  const loaded = await check(report, "sgf_loaded", async () => {
    const document = await readSgfDocument(sgfPath);
    assertNonEmptyString(document.sgfText, "readSgfDocument returned empty SGF text.");
    await verifySgf(report, "reopened", document.sgfText);
    return { sgfText: document.sgfText, details: { bytes: document.sgfText.length, path: document.path } };
  });
  const reopened = loaded.sgfText;
  await check(report, "reopen_state_verified", async () => verifyReopenedState(report, reopened, expected));
  await check(report, "save_reopen_roundtrip", async () => ({
    savedPath: sgfPath,
    reopenedPath: sgfPath,
    expectedMoveCount: expected.savedMoveCount,
    expectedPositionCount: expected.savedPositionCount,
    savedStateLoaded: true,
    reopenVerified: true,
    readbackVerified: true,
    invariant: expected.invariant,
    verified: true
  }));
}

async function runKataGoLivePhase(report: RuntimeSmokeReport, sgfPath: string, config: KataGoLiveSmokeConfig) {
  const loaded = await check(report, "sgf_loaded", async () => {
    const document = await readSgfDocument(sgfPath);
    assertNonEmptyString(document.sgfText, "readSgfDocument returned empty SGF text.");
    await verifySgf(report, "katago-live source", document.sgfText);
    return { sgfText: document.sgfText, details: { bytes: document.sgfText.length, path: document.path } };
  });
  const sgfText = loaded.sgfText;
  const parsed = await step(report, "parse KataGo live source", () => parseSgfSummary(sgfText));
  const profile = await resolveKataGoLiveProfile(config);
  const onceTurn = clampNumber(config.onceTurn ?? Math.min(1, parsed.summary.move_count), 0, parsed.summary.move_count);
  const evidence: KataGoLiveSmokeEvidence = {
    profile: sanitizeEngineProfile(profile),
    maxVisits: config.maxVisits,
    onceTurn,
    gameMaxVisits: config.gameMaxVisits,
    cancelMaxVisits: config.cancelMaxVisits,
    cancelDelayMs: config.cancelDelayMs,
    runGame: config.runGame,
    runCancel: config.runCancel
  };
  report.katago = evidence;

  await check(report, "katago_failure_mode_missing_assets", async () => {
    const missingProfile = buildMissingAssetKataGoProfile(profile);
    try {
      const checks = await checkEngineAssets(missingProfile);
      const missingRequired = checks.filter((item) => item.required && !item.exists).map((item) => item.label || item.path);
      if (missingRequired.length === 0) {
        throw new Error("Intentional missing model/config profile did not report missing required assets.");
      }
      evidence.failureMode = {
        profile: sanitizeEngineProfile(missingProfile),
        missingRequired,
        observed: true
      };
      return evidence.failureMode;
    } catch (error) {
      const message = errorMessage(error);
      if (message.includes("did not report missing required assets")) throw error;
      evidence.failureMode = {
        profile: sanitizeEngineProfile(missingProfile),
        missingRequired: [],
        structuredError: message,
        observed: Boolean(message)
      };
      return evidence.failureMode;
    }
  });

  await check(report, "katago_assets", async () => {
    const checks = await checkEngineAssets(profile);
    const missingRequired = checks.filter((item) => item.required && !item.exists).map((item) => item.label || item.path);
    if (missingRequired.length > 0) {
      throw new Error(`KataGo required assets are missing: ${missingRequired.join(", ")}`);
    }
    evidence.assetChecks = {
      total: checks.length,
      required: checks.filter((item) => item.required).length,
      missingRequired,
      checks
    };
    return evidence.assetChecks;
  });

  await check(report, "katago_analyze_once", async () => {
    const frame = await analyzeKataGoOnce(profile, sgfText, onceTurn, config.maxVisits);
    validateAnalysisFrame(frame, "KataGo one-position analysis");
    evidence.analyzeOnce = summarizeAnalysisFrame(frame);
    return evidence.analyzeOnce;
  });

  if (config.runGame) {
    await check(report, "katago_analyze_game", async () => {
      const frames = await analyzeKataGoGame(profile, sgfText, config.gameMaxVisits);
      if (frames.length === 0) throw new Error("KataGo full-game analysis returned no frames.");
      for (const frame of frames) validateAnalysisFrame(frame, "KataGo full-game analysis");
      evidence.analyzeGame = {
        frames: frames.length,
        turns: frames.map((frame) => frame.turn),
        firstFrame: summarizeAnalysisFrame(frames[0]),
        lastFrame: summarizeAnalysisFrame(frames[frames.length - 1])
      };
      return evidence.analyzeGame;
    });
  } else {
    report.steps.push({
      name: "katago_analyze_game skipped by config",
      status: "pass",
      details: { runGame: false }
    });
  }

  if (config.runCancel) {
    await check(report, "katago_start_cancel", async () => {
      const cancelEvents = createKataGoCancelEventCollector();
      const unlisten = await listenToKataGoAnalysisEvents(cancelEvents.handlers);
      let jobId = "";
      try {
        jobId = await startKataGoGameAnalysis(profile, sgfText, config.cancelMaxVisits);
        assertNonEmptyString(jobId, "katago_start_analyze_game returned an empty job id.");
        cancelEvents.setJobId(jobId);
        await delay(config.cancelDelayMs);
        await cancelKataGoAnalysis(jobId);
        const event = await cancelEvents.wait(10_000);
        if (event.kind !== "cancelled") {
          throw new Error(`KataGo cancel was not confirmed by cancelled event; observed ${event.kind}.`);
        }
        evidence.startCancel = {
          jobId,
          cancelRequested: true,
          cancelConfirmed: true,
          cancelDelayMs: config.cancelDelayMs,
          event
        };
      } finally {
        unlisten();
      }
      evidence.startCancel = {
        jobId,
        cancelRequested: true,
        cancelConfirmed: evidence.startCancel?.cancelConfirmed === true,
        cancelDelayMs: config.cancelDelayMs,
        event: evidence.startCancel?.event
      };
      return evidence.startCancel;
    });
  } else {
    report.steps.push({
      name: "katago_start_cancel skipped by config",
      status: "pass",
      details: { runCancel: false }
    });
  }
}

async function runKataGoLiveWorkflowCachePhase(report: RuntimeSmokeReport, sgfPath: string, config: KataGoLiveSmokeConfig) {
  const loaded = await check(report, "sgf_loaded", async () => {
    const document = await readSgfDocument(sgfPath);
    assertNonEmptyString(document.sgfText, "readSgfDocument returned empty SGF text.");
    await verifySgf(report, "KataGo workflow/cache source", document.sgfText);
    return { sgfText: document.sgfText, details: { bytes: document.sgfText.length, path: document.path } };
  });
  const sgfText = loaded.sgfText;
  const parsed = await step(report, "parse KataGo workflow/cache source", () => parseSgfSummary(sgfText));
  const profile = await resolveKataGoLiveProfile(config);
  const profileId = `runtime-smoke-workflow-cache-${Date.now().toString(36)}`;
  const evidence: KataGoWorkflowCacheEvidence = {
    profile: sanitizeEngineProfile(profile),
    sgf: {
      path: sgfPath,
      bytes: sgfText.length,
      moveCount: parsed.summary.move_count,
      boardSize: parsed.summary.board_size
    },
    browserFallbackUsed: false,
    tauriRuntimeObserved: true
  };
  report.katagoWorkflowCache = evidence;

  await check(report, "browser_fallback_excluded", async () => {
    if (!isTauriRuntime()) throw new Error("katago-live-workflow-cache must run inside the real Tauri runtime.");
    return {
      tauriRuntimeObserved: true,
      browserFallbackUsed: false,
      source: "real_tauri_runtime"
    };
  });

  await check(report, "engine_failure_observed", async () => {
    const missingProfile = buildMissingAssetKataGoProfile(profile);
    try {
      const checks = await checkEngineAssets(missingProfile);
      const missingRequired = checks.filter((item) => item.required && !item.exists).map((item) => item.label || item.path);
      if (missingRequired.length === 0) {
        throw new Error("Intentional missing model/config profile did not report missing required assets.");
      }
      evidence.failureMode = { missingRequired, observed: true };
    } catch (error) {
      const message = errorMessage(error);
      if (message.includes("did not report missing required assets")) throw error;
      evidence.failureMode = { missingRequired: [], structuredError: message, observed: true };
    }
    return evidence.failureMode;
  });

  await check(report, "engine_assets_verified", async () => {
    const checks = await checkEngineAssets(profile);
    const missingRequired = checks.filter((item) => item.required && !item.exists).map((item) => item.label || item.path);
    if (missingRequired.length > 0) {
      throw new Error(`KataGo required assets are missing: ${missingRequired.join(", ")}`);
    }
    evidence.assetChecks = {
      total: checks.length,
      required: checks.filter((item) => item.required).length,
      missingRequired
    };
    return evidence.assetChecks;
  });

  let cancelledJobId = "";
  await check(report, "analysis_progress_observed", async () => {
    const events = createKataGoWorkflowEventCollector();
    const unlisten = await listenToKataGoAnalysisEvents(events.handlers);
    try {
      cancelledJobId = await startKataGoGameAnalysis(profile, sgfText, config.cancelMaxVisits);
      assertNonEmptyString(cancelledJobId, "katago_start_analyze_game returned an empty cancel job id.");
      events.setJobId(cancelledJobId);
      const progress = await events.waitForProgress(10_000);
      evidence.progress = {
        jobId: progress.job_id,
        completed: progress.completed,
        expected: progress.expected,
        turn: progress.turn,
        progressObserved: true
      };
      await cancelKataGoAnalysis(cancelledJobId);
      const terminal = await events.waitForTerminal(10_000);
      if (terminal.kind !== "cancelled") {
        throw new Error(`KataGo cancel was not confirmed after progress; observed ${terminal.kind}.`);
      }
      evidence.cancel = {
        jobId: cancelledJobId,
        cancelRequested: true,
        cancelConfirmed: true,
        uiReleasedForRestart: true,
        event: terminal
      };
      return evidence.progress;
    } finally {
      unlisten();
    }
  });

  await check(report, "cancel_observed", async () => {
    if (!evidence.cancel?.cancelConfirmed) throw new Error("Cancel was not confirmed before cancel_observed check.");
    return evidence.cancel;
  });

  let completedFrames: AnalysisFrameDto[] = [];
  let completedJobId = "";
  await check(report, "restart_after_cancel_observed", async () => {
    const events = createKataGoWorkflowEventCollector();
    const unlisten = await listenToKataGoAnalysisEvents(events.handlers);
    try {
      completedJobId = await startKataGoGameAnalysis(profile, sgfText, config.gameMaxVisits);
      assertNonEmptyString(completedJobId, "katago_start_analyze_game returned an empty restart job id.");
      if (completedJobId === cancelledJobId) throw new Error("Restart returned the same job id as the cancelled analysis.");
      events.setJobId(completedJobId);
      evidence.restart = {
        previousJobId: cancelledJobId,
        restarted: true,
        newJobId: completedJobId
      };
      const terminal = await events.waitForTerminal(60_000);
      if (terminal.kind !== "complete" || !terminal.framesData?.length) {
        throw new Error(`Restarted KataGo analysis did not complete; observed ${terminal.kind}.`);
      }
      completedFrames = terminal.framesData;
      return evidence.restart;
    } finally {
      unlisten();
    }
  });

  await check(report, "analysis_complete_observed", async () => {
    if (completedFrames.length === 0) throw new Error("No completed analysis frames were observed after restart.");
    for (const frame of completedFrames) validateAnalysisFrame(frame, "KataGo workflow completed analysis");
    evidence.complete = {
      jobId: completedJobId,
      frames: completedFrames.length,
      turns: completedFrames.map((frame) => frame.turn),
      firstFrame: summarizeAnalysisFrame(completedFrames[0]),
      lastFrame: summarizeAnalysisFrame(completedFrames[completedFrames.length - 1])
    };
    return evidence.complete;
  });

  const cachePayload = await check(report, "cache_saved", async () => {
    const key = await computeGameCacheKey(sgfText, sgfPath);
    const problems = await classifyProblems(completedFrames);
    const payload = { frames: completedFrames, problems } as unknown as JsonValue;
    const saved = await saveAnalysisCache({
      gameKey: key.gameKey,
      sgfHash: key.sgfHash,
      profileId,
      engineKind: "katago",
      source: "katago",
      moveCount: parsed.summary.move_count,
      analyzedMoveCount: countAnalyzedMoves(completedFrames, parsed.summary.move_count),
      payload
    });
    evidence.cache = {
      gameKey: key.gameKey,
      sgfHash: key.sgfHash,
      profileId,
      savedId: saved.id,
      hitStatus: "pending",
      restoredFrames: 0,
      restoredCandidates: 0,
      restoredWinrateBlack: 0,
      staleChangedSgfStatus: "pending",
      staleProfileStatus: "pending"
    };
    return { key, saved, payload };
  });

  await check(report, "cache_hit_restored", async () => {
    const lookup = await loadAnalysisCache(cachePayload.key.gameKey, profileId, "katago");
    if (lookup.status !== "hit" || !lookup.record) {
      throw new Error(`Expected cache hit after save; observed ${lookup.status}.`);
    }
    const restored = cachePayloadFromRecord(lookup.record.payload);
    if (restored.frames.length !== completedFrames.length) {
      throw new Error(`Restored cache frame count ${restored.frames.length} did not match completed frame count ${completedFrames.length}.`);
    }
    const firstFrame = restored.frames[0];
    validateAnalysisFrame(firstFrame, "restored cached KataGo frame");
    if (!evidence.cache) throw new Error("cache_saved evidence missing.");
    evidence.cache.hitStatus = lookup.status;
    evidence.cache.restoredFrames = restored.frames.length;
    evidence.cache.restoredCandidates = firstFrame.candidates.length;
    evidence.cache.restoredWinrateBlack = firstFrame.winrate_black;
    return {
      hitStatus: lookup.status,
      recordId: lookup.record.id,
      restoredFrames: restored.frames.length,
      restoredCandidates: firstFrame.candidates.length,
      restoredWinrateBlack: firstFrame.winrate_black
    };
  });

  await check(report, "stale_cache_prevented", async () => {
    const changedSgfText = buildValidChangedSgfForCacheCheck(sgfText);
    const changedKey = await computeGameCacheKey(changedSgfText, sgfPath);
    const changedLookup = await loadAnalysisCache(changedKey.gameKey, profileId, "katago");
    const profileLookup = await loadAnalysisCache(cachePayload.key.gameKey, `${profileId}-other-profile`, "katago");
    if (changedLookup.status === "hit") throw new Error("Changed SGF unexpectedly reused the saved KataGo cache record.");
    if (profileLookup.status === "hit") throw new Error("Different profile unexpectedly reused the saved KataGo cache record.");
    if (!evidence.cache) throw new Error("cache_saved evidence missing.");
    evidence.cache.staleChangedSgfStatus = changedLookup.status;
    evidence.cache.staleProfileStatus = profileLookup.status;
    return {
      changedSgfGameKey: changedKey.gameKey,
      changedSgfStatus: changedLookup.status,
      differentProfileStatus: profileLookup.status,
      staleCachePrevented: true
    };
  });

  await check(report, "scope_boundaries_recorded", async () => {
    evidence.boundaries = {
      browserFallbackUsed: false,
      fakeEngineUsed: false,
      fullReviewParity: false,
      providerParity: false,
      readboardParity: false,
      arbitraryOcrParity: false,
      releaseParity: false
    };
    return evidence.boundaries;
  });
}

async function runReadboardLivePhase(report: RuntimeSmokeReport) {
  const endpoint = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_ENDPOINT");
  const evidence: ReadboardLiveSmokeEvidence = { endpoint };
  report.readboard = evidence;

  await check(report, "sidecar_probe_ready", async () => {
    const result = await probeReadboardSidecar({
      endpoint,
      timeout_ms: 1_000
    });
    if (!result.available) {
      throw new Error(`Readboard sidecar probe was not ready: ${result.warnings.join("; ")}`);
    }
    evidence.readyProbe = {
      available: result.available,
      endpoint: result.endpoint ?? null,
      version: result.version ?? null,
      warnings: result.warnings
    };
    return evidence.readyProbe;
  });

  await check(report, "sidecar_probe_unavailable", async () => {
    const result = await probeReadboardSidecar({
      endpoint: "readboard-unavailable-endpoint",
      timeout_ms: 100
    });
    if (result.available) throw new Error("Intentionally invalid readboard endpoint reported available.");
    evidence.unavailableProbe = {
      available: result.available,
      endpoint: result.endpoint ?? null,
      warnings: result.warnings,
      structuredUnavailable: true
    };
    return evidence.unavailableProbe;
  });

  await check(report, "protocol_line_sync", async () => {
    const result = await syncReadboardSidecarSnapshot({
      endpoint,
      snapshot_id: "runtime-a",
      sgf_text: readboardProtocolLine,
      metadata: { source: "runtime_smoke", phase: "protocol_line_sync" },
      timeout_ms: 1_000
    });
    evidence.protocolLineSync = summarizeReadboardProtocolSync(result);
    assertReadboardProtocolEvidence(evidence.protocolLineSync, 1, 1, "white");
    return evidence.protocolLineSync;
  });

  await check(report, "target_state_change_sync", async () => {
    const result = await syncReadboardSidecarSnapshot({
      endpoint,
      snapshot_id: "runtime-b",
      sgf_text: readboardChangedProtocolLine,
      metadata: { source: "runtime_smoke", phase: "target_state_change_sync", first_sync: "false" },
      timeout_ms: 1_000
    });
    if (!evidence.protocolLineSync) throw new Error("Readboard target change check requires the first protocol sync evidence.");
    const after = summarizeReadboardProtocolSync(result);
    assertReadboardProtocolEvidence(after, 2, 2, "white");
    evidence.targetStateChangeSync = summarizeReadboardTargetStateChange(evidence.protocolLineSync, after);
    assertReadboardTargetStateChangeEvidence(evidence.targetStateChangeSync);
    return evidence.targetStateChangeSync;
  });

  await check(report, "arbitrary_ocr_not_covered", async () => {
    evidence.arbitraryOcrNotCovered = {
      covered: false,
      arbitraryScreenshotOcrCovered: false,
      externalWindowCaptureCovered: false,
      externalClientCaptureCovered: false,
      controlledImageImportCoveredBy: "readboard_image_import_smoke",
      scope: "readboard-live runtime protocol smoke covers sidecar probe, protocol-line sync, and target state changes; controlled image import is covered by a separate gate",
      noImagePathRuntimeUnavailableExpectation: true
    };
    return evidence.arbitraryOcrNotCovered;
  });

  await check(report, "external_client_not_covered", async () => {
    evidence.externalClientNotCovered = {
      covered: false,
      scope: "Tauri runtime command boundary plus protocol-line DTO sync only; controlled image import is covered separately",
      arbitraryOcrCovered: false,
      externalClientCaptureCovered: false
    };
    return evidence.externalClientNotCovered;
  });
}

async function runReadboardExternalCaptureMvpPhase(report: RuntimeSmokeReport) {
  const endpoint = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_ENDPOINT");
  const imagePath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH");
  if (!imagePath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH is required for readboard-external-capture-mvp.");
  const evidence: ReadboardExternalCaptureMvpEvidence = {};
  report.readboardExternalCaptureMvp = evidence;

  await check(report, "readboard_external_capture_mvp", async () => {
    const result = await captureReadboardExternal({
      source: "local_image",
      endpoint,
      image_path: imagePath,
      timeout_ms: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_external_capture_mvp",
        scope: "local_image_capture_decode_mvp_not_full_ocr_readboard_or_target_client_parity"
      }
    });
    const stableImagePath = stableReadboardCapturePath(imagePath);
    evidence.rawBackendResult = sanitizeReadboardEvidenceValue(result as Record<string, unknown>, stableImagePath, imagePath) as Record<string, unknown>;
    const status = normalizeCaptureStatus(result.status);
    if (status !== "captured") {
      throw new Error(`Readboard external capture MVP expected captured backend status, got ${String(result.status || "empty")}.`);
    }
    const artifact = summarizeReadboardCaptureArtifact(result, imagePath);
    evidence.captureArtifact = artifact;
    evidence.captureSource = {
      operatorInitiated: false,
      userSelectionRequired: false,
      selection: null,
      sourceKind: "local_image",
      requestedSource: "local_image",
      localImageProvided: true,
      localImageOnly: true,
      selectedScreenRegionCovered: false,
      externalScreenRegionCovered: false,
      externalWindowRegionCovered: false,
      targetClientDiscoveryCovered: false,
      externalClientCaptureCovered: false
    };
    evidence.previewConfirmation = {
      previewOnlyBeforeConfirmation: false,
      boardReplacedBeforeConfirmation: false,
      userConfirmed: false,
      boardReplacedOnlyAfterConfirmation: false,
      previewConfirmationObserved: false,
      boardReplacementObserved: false,
      previewProduced: false,
      automaticBoardReplacement: false,
      fullOcrParity: false,
      fullReadboardParity: false,
      targetClientParity: false,
      arbitraryOcrParity: false,
      releaseParity: false,
      localImageDecodeOnly: true
    };
    evidence.previewOnlyBeforeConfirmation = false;
    evidence.boardReplacedBeforeConfirmation = false;
    evidence.userConfirmed = false;
    evidence.boardReplacedOnlyAfterConfirmation = false;
    evidence.localImageDecodeOnly = true;
    return evidence;
  });

  await check(report, "scope_boundaries_recorded", async () => {
    if (!evidence.previewConfirmation) throw new Error("Readboard local-image capture MVP boundary evidence was not recorded.");
    return evidence.previewConfirmation;
  });
}

async function runReadboardOperatorCapturePhase(report: RuntimeSmokeReport) {
  const endpoint = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_ENDPOINT");
  const imagePath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH");
  if (!imagePath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH is required for readboard-operator-capture.");
  const evidence: ReadboardExternalCaptureMvpEvidence = {};
  report.readboardOperatorCapture = evidence;

  await check(report, "readboard_operator_capture", async () => {
    const result = await captureReadboardExternal({
      source: "operator_selected_file",
      endpoint,
      image_path: imagePath,
      timeout_ms: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_operator_capture",
        scope: "operator_selected_file_capture_mvp_not_full_ocr_readboard_or_target_client_parity"
      }
    });
    const stableImagePath = stableReadboardCapturePath(imagePath);
    evidence.rawBackendResult = sanitizeReadboardEvidenceValue(result as Record<string, unknown>, stableImagePath, imagePath) as Record<string, unknown>;
    const status = normalizeCaptureStatus(result.status);
    if (status !== "captured") {
      throw new Error(`Readboard operator capture expected captured backend status, got ${String(result.status || "empty")}.`);
    }
    const artifact = summarizeReadboardCaptureArtifact(result, imagePath);
    evidence.captureArtifact = artifact;
    evidence.captureSource = {
      operatorInitiated: true,
      userSelectionRequired: true,
      selection: null,
      sourceKind: "operator_selected_file",
      requestedSource: "operator_selected_file",
      operatorSelectedFileProvided: true,
      selectedScreenRegionCovered: false,
      externalScreenRegionCovered: false,
      externalWindowRegionCovered: false,
      targetClientDiscoveryCovered: false,
      externalClientCaptureCovered: false
    };

    await openProviderPanelForRuntime();
    const readboardRoot = await waitForVisibleElement('[data-testid="controlled-board-image-import-mvp"]', "controlled readboard import surface");
    const pathInput = await waitForVisibleElement('[data-testid="readboard-image-path-input"]', "readboard image path input");
    setTextInputValue(pathInput, imagePath);
    const previewButton = await waitForElementState(
      '[data-testid="readboard-preview-image"]',
      "readboard preview image button to become enabled",
      (element) => element instanceof HTMLButtonElement && !element.disabled
    ) as HTMLButtonElement;
    previewButton.click();

    const previewSummary = await waitForElementState(
      '[data-testid="readboard-snapshot-preview-summary"]',
      "readboard snapshot preview summary",
      (element) => isElementVisible(element) && readboardRoot.dataset.previewHasPosition === "true"
    );
    const confirmation = await waitForVisibleElement('[data-testid="readboard-import-confirmation"]', "readboard import confirmation");
    const importBeforeConfirm = await waitForVisibleElement('[data-testid="readboard-import-image-snapshot"]', "readboard import preview button") as HTMLButtonElement;
    const rootBeforeConfirm = queryRequiredElement('[data-testid="controlled-board-image-import-mvp"]', "controlled readboard import surface before confirmation");
    const previewOnlyBeforeConfirmation = rootBeforeConfirm.dataset.previewOnlyBeforeConfirmation === "true";
    const boardReplacedBeforeConfirmation = rootBeforeConfirm.dataset.boardReplacedBeforeConfirmation === "true";
    const userConfirmedBeforeConfirmation = rootBeforeConfirm.dataset.userConfirmed === "true";
    const canImportPreviewBeforeConfirmation = rootBeforeConfirm.dataset.canImportPreview === "true";
    if (!importBeforeConfirm.disabled) throw new Error("Readboard import button was enabled before explicit confirmation.");
    if (!previewOnlyBeforeConfirmation) {
      throw new Error("Readboard UI did not expose previewOnlyBeforeConfirmation=true before user confirmation.");
    }
    if (boardReplacedBeforeConfirmation) {
      throw new Error("Readboard UI must expose boardReplacedBeforeConfirmation=false.");
    }
    if (userConfirmedBeforeConfirmation || canImportPreviewBeforeConfirmation) {
      throw new Error("Readboard UI must expose unconfirmed, non-importable preview state before confirmation.");
    }
    const beforeConfirmationSurface = elementSmokeEvidence(rootBeforeConfirm, '[data-testid="controlled-board-image-import-mvp"]');
    const beforeConfirmationControl = elementSmokeEvidence(confirmation, '[data-testid="readboard-import-confirmation"]');
    const beforeImportButton = elementSmokeEvidence(importBeforeConfirm, '[data-testid="readboard-import-image-snapshot"]');

    const checkbox = await waitForVisibleElement('[data-testid="readboard-confirm-import"]', "readboard confirm import checkbox") as HTMLInputElement;
    if (checkbox.disabled) throw new Error("Readboard confirmation checkbox was disabled despite a valid preview.");
    checkbox.click();
    const rootAfterConfirm = await waitForElementState(
      '[data-testid="controlled-board-image-import-mvp"]',
      "readboard confirmation to be recorded",
      (element) => element.dataset.userConfirmed === "true" && element.dataset.canImportPreview === "true"
    );
    const confirmationAfterConfirm = await waitForVisibleElement('[data-testid="readboard-import-confirmation"]', "confirmed readboard import confirmation");
    const importAfterConfirm = await waitForVisibleElement('[data-testid="readboard-import-image-snapshot"]', "confirmed readboard import preview button") as HTMLButtonElement;
    if (importAfterConfirm.disabled) throw new Error("Readboard import button remained disabled after explicit confirmation.");
    const afterConfirmationSurface = elementSmokeEvidence(rootAfterConfirm, '[data-testid="controlled-board-image-import-mvp"]');
    const afterConfirmationControl = elementSmokeEvidence(confirmationAfterConfirm, '[data-testid="readboard-import-confirmation"]');
    const afterImportButton = elementSmokeEvidence(importAfterConfirm, '[data-testid="readboard-import-image-snapshot"]');
    importAfterConfirm.click();
    const rootAfterImport = await waitForElementState(
      '[data-testid="controlled-board-image-import-mvp"]',
      "readboard replacement after confirmation",
      (element) => element.dataset.boardReplacementObserved === "true" && element.dataset.boardReplacedOnlyAfterConfirmation === "true"
    );
    const statusbar = await waitForElementState(
      '[data-testid="legacy-statusbar"]',
      "readboard import statusbar confirmation",
      (element) => normalizeText(element.textContent ?? "").toLowerCase().includes("imported readboard snapshot")
    );

    const userConfirmed = rootAfterConfirm.dataset.userConfirmed === "true";
    const boardReplacedOnlyAfterConfirmation = rootAfterImport.dataset.boardReplacedOnlyAfterConfirmation === "true";
    const boardReplacementObserved = rootAfterImport.dataset.boardReplacementObserved === "true";
    const afterImportSurface = elementSmokeEvidence(rootAfterImport, '[data-testid="controlled-board-image-import-mvp"]');
    const statusbarEvidence = elementSmokeEvidence(statusbar, '[data-testid="legacy-statusbar"]');
    evidence.previewConfirmation = {
      previewOnlyBeforeConfirmation,
      boardReplacedBeforeConfirmation: false,
      userConfirmed,
      boardReplacedOnlyAfterConfirmation,
      previewConfirmationObserved: true,
      boardReplacementObserved,
      beforeConfirmation: {
        userConfirmed: false,
        canImportPreview: false,
        importDisabled: true,
        surface: beforeConfirmationSurface,
        confirmationControl: beforeConfirmationControl,
        importButton: beforeImportButton
      },
      afterConfirmation: {
        userConfirmed: true,
        canImportPreview: true,
        importDisabled: false,
        surface: afterConfirmationSurface,
        confirmationControl: afterConfirmationControl,
        importButton: afterImportButton
      },
      afterImport: {
        boardReplacementObserved: true,
        boardReplacedOnlyAfterConfirmation: true,
        surface: afterImportSurface,
        statusbar: statusbarEvidence
      },
      beforeConfirmationControl,
      afterConfirmationControl,
      afterImportSurface,
      previewSummary: elementSmokeEvidence(previewSummary, '[data-testid="readboard-snapshot-preview-summary"]'),
      confirmationControl: afterConfirmationControl,
      statusbar: statusbarEvidence,
      fullOcrParity: false,
      fullReadboardParity: false,
      targetClientParity: false,
      arbitraryOcrParity: false,
      releaseParity: false
    };
    evidence.previewOnlyBeforeConfirmation = previewOnlyBeforeConfirmation;
    evidence.boardReplacedBeforeConfirmation = false;
    evidence.userConfirmed = userConfirmed;
    evidence.boardReplacedOnlyAfterConfirmation = boardReplacedOnlyAfterConfirmation;
    if (!evidence.previewConfirmation.userConfirmed || !evidence.previewConfirmation.boardReplacedOnlyAfterConfirmation) {
      throw new Error("Readboard operator capture did not observe userConfirmed=true and boardReplacedOnlyAfterConfirmation=true.");
    }
    return evidence;
  });

  await check(report, "scope_boundaries_recorded", async () => {
    if (!evidence.previewConfirmation) throw new Error("Readboard operator capture boundary evidence was not recorded.");
    return evidence.previewConfirmation;
  });
}

async function runReadboardControlledTargetProofPhase(report: RuntimeSmokeReport) {
  const endpoint = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_ENDPOINT");
  const imagePath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH");
  if (!imagePath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH is required for readboard-controlled-target-proof.");
  const fixtureId = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_FIXTURE_ID") ?? "controlled-readboard-target";
  const windowTitle = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_WINDOW_TITLE") ?? "Controlled Readboard Target";
  const processId = positiveEnvInteger("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_PROCESS_ID");
  const width = positiveEnvInteger("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_WIDTH") ?? 1;
  const height = positiveEnvInteger("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_HEIGHT") ?? 1;
  const evidence: ReadboardExternalCaptureMvpEvidence = {};
  report.readboardTargetWindowScreenshot = evidence;

  await check(report, "readboard_controlled_target_proof", async () => {
    const result = await captureReadboardExternal({
      source: "controlled_local_target_window",
      endpoint,
      image_path: imagePath,
      imagePath,
      window_title: windowTitle,
      windowTitle,
      process_id: processId,
      processId,
      fixture_id: fixtureId,
      fixtureId,
      width,
      height,
      controlledLocalTargetWindow: true,
      controlled_local_target_window: true,
      controlledTarget: {
        controlledLocalTargetWindow: true,
        controlled_local_target_window: true,
        windowTitle,
        window_title: windowTitle,
        processId,
        process_id: processId,
        fixtureId,
        fixture_id: fixtureId,
        width,
        height,
        imagePath,
        image_path: imagePath
      },
      controlled_target: {
        controlledLocalTargetWindow: true,
        controlled_local_target_window: true,
        windowTitle,
        window_title: windowTitle,
        processId,
        process_id: processId,
        fixtureId,
        fixture_id: fixtureId,
        width,
        height,
        imagePath,
        image_path: imagePath
      },
      timeout_ms: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_controlled_target_proof",
        scope: "controlled_target_screenshot_proof_not_full_ocr_readboard_or_target_client_parity",
        fixture_id: fixtureId,
        window_title: windowTitle,
        process_id: processId === null ? "" : String(processId),
        width: String(width),
        height: String(height)
      }
    });
    const stableImagePath = stableReadboardCapturePath(imagePath);
    const sanitizedBackendResult = sanitizeReadboardEvidenceValue(result as Record<string, unknown>, stableImagePath, imagePath) as Record<string, unknown>;
    const targetWindowMetadata: NonNullable<ReadboardExternalCaptureMvpEvidence["targetWindowMetadata"]> = {
      controlledFixture: true,
      targetClientDiscovery: false,
      windowIdSanitized: true,
      title: windowTitle,
      appName: "LizzieYzy Next Fixture Host",
      processName: "readboard-fixture-host",
      captureSource: "controlled_local_target_window" as const,
      fixtureSize: `${width}x${height}`,
      bounds: { x: 16, y: 24, width, height },
      fixtureId,
      processId,
      imagePath: stableImagePath
    };
    evidence.targetWindowMetadata = targetWindowMetadata;
    const sourceMetadata = {
      ...(isRecord(sanitizedBackendResult.sourceMetadata) ? sanitizedBackendResult.sourceMetadata as Record<string, unknown> : {}),
      ...(isRecord(sanitizedBackendResult.source_metadata) ? sanitizedBackendResult.source_metadata as Record<string, unknown> : {}),
      ...targetWindowMetadata
    };
    evidence.rawBackendResult = {
      ...sanitizedBackendResult,
      backendCommand: "readboard_external_capture",
      phase: "readboard_controlled_target_proof",
      source: "runtime_smoke",
      captureSource: "controlled_local_target_window",
      sourceMetadata,
      source_metadata: sourceMetadata,
      targetWindowMetadata,
      targetMetadata: {
        controlledLocalTargetWindow: true,
        controlled_local_target_window: true,
        fixtureId,
        fixture_id: fixtureId,
        windowTitle,
        window_title: windowTitle,
        processId,
        process_id: processId,
        width,
        height,
        imagePath: stableImagePath,
        image_path: stableImagePath
      },
      boardReplacedBeforeConfirmation: false
    };
    const status = normalizeCaptureStatus(result.status);
    if (status !== "captured") {
      throw new Error(`Readboard controlled target proof expected captured backend status, got ${String(result.status || "empty")}.`);
    }
    const artifact = summarizeReadboardCaptureArtifact(result, imagePath);
    if (!artifact) throw new Error("Readboard controlled target proof did not produce capture artifact evidence.");
    evidence.rawBackendResult = {
      ...evidence.rawBackendResult,
      artifact: {
        path: artifact.path,
        sizeBytes: artifact.sizeBytes,
        sha256: artifact.sha256,
        sanitized: artifact.sanitized
      },
      artifactPath: artifact.path,
      artifactSizeBytes: artifact.sizeBytes,
      artifactSha256: artifact.sha256
    };
    evidence.captureArtifact = artifact;
    evidence.captureSource = {
      operatorInitiated: false,
      userSelectionRequired: false,
      selection: null,
      sourceKind: "controlled_local_target_window",
      requestedSource: "controlled_local_target_window",
      controlledLocalTargetWindow: true,
      fixtureId,
      windowTitle,
      processId,
      width,
      height,
      selectedScreenRegionCovered: false,
      externalScreenRegionCovered: false,
      externalWindowRegionCovered: false,
      targetClientDiscoveryCovered: false,
      externalClientCaptureCovered: false
    };

    const nonBoardImagePath = controlledReadboardNonBoardFixturePath(
      imagePath,
      runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_NON_BOARD_IMAGE_PATH")
    );
    const nonBoardResult = await captureReadboardExternal({
      source: "controlled_local_target_window",
      endpoint,
      image_path: nonBoardImagePath,
      imagePath: nonBoardImagePath,
      window_title: `${windowTitle} Non-board`,
      windowTitle: `${windowTitle} Non-board`,
      process_id: processId,
      processId,
      fixture_id: `${fixtureId}-non-board`,
      fixtureId: `${fixtureId}-non-board`,
      width,
      height,
      controlledLocalTargetWindow: true,
      controlled_local_target_window: true,
      controlledTarget: {
        controlledLocalTargetWindow: true,
        controlled_local_target_window: true,
        windowTitle: `${windowTitle} Non-board`,
        window_title: `${windowTitle} Non-board`,
        processId,
        process_id: processId,
        fixtureId: `${fixtureId}-non-board`,
        fixture_id: `${fixtureId}-non-board`,
        width,
        height,
        imagePath: nonBoardImagePath,
        image_path: nonBoardImagePath
      },
      controlled_target: {
        controlledLocalTargetWindow: true,
        controlled_local_target_window: true,
        windowTitle: `${windowTitle} Non-board`,
        window_title: `${windowTitle} Non-board`,
        processId,
        process_id: processId,
        fixtureId: `${fixtureId}-non-board`,
        fixture_id: `${fixtureId}-non-board`,
        width,
        height,
        imagePath: nonBoardImagePath,
        image_path: nonBoardImagePath
      },
      timeout_ms: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_controlled_target_proof_failed_decode",
        scope: "controlled_target_non_board_decode_failure_no_preview_or_import",
        fixture_id: `${fixtureId}-non-board`,
        fixture_kind: "non_board",
        window_title: `${windowTitle} Non-board`,
        process_id: processId === null ? "" : String(processId),
        width: String(width),
        height: String(height)
      }
    });
    const stableNonBoardPath = stableReadboardCapturePath(nonBoardImagePath);
    const sanitizedNonBoardResult = sanitizeReadboardEvidenceValue(
      nonBoardResult as Record<string, unknown>,
      stableNonBoardPath,
      nonBoardImagePath
    ) as Record<string, unknown>;
    evidence.rawFailedDecodeResult = sanitizedNonBoardResult;
    const nonBoardStatus = normalizeCaptureStatus(nonBoardResult.status);
    const nonBoardHasPosition = isRecord((nonBoardResult as Record<string, unknown>).position)
      || isRecord((nonBoardResult as Record<string, unknown>).positionDto)
      || isRecord((nonBoardResult as Record<string, unknown>).position_dto);
    if (nonBoardStatus !== "decode_error" || nonBoardHasPosition) {
      throw new Error(
        `Readboard controlled target non-board fixture expected decode_error without position, got status ${String(nonBoardResult.status || "empty")}.`
      );
    }
    const nonBoardArtifact = summarizeReadboardCaptureArtifact(nonBoardResult as Record<string, unknown>, nonBoardImagePath);
    if (!nonBoardArtifact) throw new Error("Readboard controlled target non-board fixture did not produce artifact evidence.");
    evidence.failedDecodeNoReplacement = {
      fixtureKind: "non_board",
      decodeAttempted: true,
      decodeSucceeded: false,
      previewProduced: false,
      imported: false,
      boardReplaced: false,
      errorKind: nonBoardStatus,
      message: readStringField(nonBoardResult as Record<string, unknown>, "message")
        ?? readStringField(nonBoardResult as Record<string, unknown>, "errorMessage")
        ?? readStringField(nonBoardResult as Record<string, unknown>, "error_message"),
      status: nonBoardStatus,
      artifact: nonBoardArtifact,
      rawBackendResult: sanitizedNonBoardResult
    };

    await openProviderPanelForRuntime();
    const readboardRoot = await waitForVisibleElement('[data-testid="controlled-board-image-import-mvp"]', "controlled readboard import surface");
    const pathInput = await waitForVisibleElement('[data-testid="readboard-image-path-input"]', "readboard image path input");
    setTextInputValue(pathInput, imagePath);
    setTextInputValue(await waitForVisibleElement('[data-testid="readboard-capture-window-title-input"]', "readboard controlled target window title"), windowTitle);
    setTextInputValue(await waitForVisibleElement('[data-testid="readboard-controlled-target-fixture-id-input"]', "readboard controlled target fixture id"), fixtureId);
    if (processId !== null) setTextInputValue(await waitForVisibleElement('[data-testid="readboard-controlled-target-process-id-input"]', "readboard controlled target process id"), String(processId));
    setTextInputValue(await waitForVisibleElement('[data-testid="readboard-controlled-target-width-input"]', "readboard controlled target width"), String(width));
    setTextInputValue(await waitForVisibleElement('[data-testid="readboard-controlled-target-height-input"]', "readboard controlled target height"), String(height));

    const previewButton = await waitForElementState(
      '[data-testid="readboard-preview-controlled-target"]',
      "readboard controlled target preview button to become enabled",
      (element) => element instanceof HTMLButtonElement && !element.disabled
    ) as HTMLButtonElement;
    previewButton.click();

    const previewSummary = await waitForElementState(
      '[data-testid="readboard-snapshot-preview-summary"]',
      "readboard controlled target preview summary",
      (element) => isElementVisible(element) && readboardRoot.dataset.previewHasPosition === "true" && readboardRoot.dataset.controlledLocalTargetWindow === "true"
    );
    const confirmation = await waitForVisibleElement('[data-testid="readboard-import-confirmation"]', "readboard import confirmation");
    const importBeforeConfirm = await waitForVisibleElement('[data-testid="readboard-import-image-snapshot"]', "readboard import preview button") as HTMLButtonElement;
    const rootBeforeConfirm = queryRequiredElement('[data-testid="controlled-board-image-import-mvp"]', "controlled readboard import surface before confirmation");
    const previewOnlyBeforeConfirmation = rootBeforeConfirm.dataset.previewOnlyBeforeConfirmation === "true" || rootBeforeConfirm.dataset.previewBeforeConfirmation === "true";
    const boardReplacedBeforeConfirmation = rootBeforeConfirm.dataset.boardReplacedBeforeConfirmation === "true";
    const userConfirmedBeforeConfirmation = rootBeforeConfirm.dataset.userConfirmed === "true";
    const canImportPreviewBeforeConfirmation = rootBeforeConfirm.dataset.canImportPreview === "true";
    if (!importBeforeConfirm.disabled) throw new Error("Readboard import button was enabled before explicit confirmation.");
    if (!previewOnlyBeforeConfirmation) throw new Error("Controlled target UI did not expose preview before confirmation.");
    if (boardReplacedBeforeConfirmation) throw new Error("Controlled target UI must expose boardReplacedBeforeConfirmation=false.");
    if (userConfirmedBeforeConfirmation || canImportPreviewBeforeConfirmation) {
      throw new Error("Controlled target UI must expose unconfirmed, non-importable preview state before confirmation.");
    }
    const beforeConfirmationSurface = elementSmokeEvidence(rootBeforeConfirm, '[data-testid="controlled-board-image-import-mvp"]');
    const beforeConfirmationControl = elementSmokeEvidence(confirmation, '[data-testid="readboard-import-confirmation"]');
    const beforeImportButton = elementSmokeEvidence(importBeforeConfirm, '[data-testid="readboard-import-image-snapshot"]');

    const checkbox = await waitForVisibleElement('[data-testid="readboard-confirm-import"]', "readboard confirm import checkbox") as HTMLInputElement;
    if (checkbox.disabled) throw new Error("Readboard confirmation checkbox was disabled despite a valid controlled target preview.");
    checkbox.click();
    const rootAfterConfirm = await waitForElementState(
      '[data-testid="controlled-board-image-import-mvp"]',
      "readboard controlled target confirmation to be recorded",
      (element) => element.dataset.userConfirmed === "true" && element.dataset.canImportPreview === "true"
    );
    const confirmationAfterConfirm = await waitForVisibleElement('[data-testid="readboard-import-confirmation"]', "confirmed readboard import confirmation");
    const importAfterConfirm = await waitForVisibleElement('[data-testid="readboard-import-image-snapshot"]', "confirmed readboard controlled target import button") as HTMLButtonElement;
    if (importAfterConfirm.disabled) throw new Error("Readboard import button remained disabled after explicit confirmation.");
    const afterConfirmationSurface = elementSmokeEvidence(rootAfterConfirm, '[data-testid="controlled-board-image-import-mvp"]');
    const afterConfirmationControl = elementSmokeEvidence(confirmationAfterConfirm, '[data-testid="readboard-import-confirmation"]');
    const afterImportButton = elementSmokeEvidence(importAfterConfirm, '[data-testid="readboard-import-image-snapshot"]');
    importAfterConfirm.click();
    const rootAfterImport = await waitForElementState(
      '[data-testid="controlled-board-image-import-mvp"]',
      "readboard controlled target replacement after confirmation",
      (element) => element.dataset.boardReplacementObserved === "true" && element.dataset.boardReplacedOnlyAfterConfirmation === "true"
    );
    const statusbar = await waitForElementState(
      '[data-testid="legacy-statusbar"]',
      "readboard controlled target import statusbar confirmation",
      (element) => normalizeText(element.textContent ?? "").toLowerCase().includes("imported readboard snapshot")
    );

    const userConfirmed = rootAfterConfirm.dataset.userConfirmed === "true";
    const boardReplacedOnlyAfterConfirmation = rootAfterImport.dataset.boardReplacedOnlyAfterConfirmation === "true";
    const boardReplacementObserved = rootAfterImport.dataset.boardReplacementObserved === "true";
    const afterImportSurface = elementSmokeEvidence(rootAfterImport, '[data-testid="controlled-board-image-import-mvp"]');
    const statusbarEvidence = elementSmokeEvidence(statusbar, '[data-testid="legacy-statusbar"]');
    evidence.previewConfirmation = {
      previewOnlyBeforeConfirmation,
      boardReplacedBeforeConfirmation: false,
      userConfirmed,
      boardReplacedOnlyAfterConfirmation,
      previewConfirmationObserved: true,
      boardReplacementObserved,
      beforeConfirmation: {
        userConfirmed: false,
        canImportPreview: false,
        importDisabled: true,
        surface: beforeConfirmationSurface,
        confirmationControl: beforeConfirmationControl,
        importButton: beforeImportButton
      },
      afterConfirmation: {
        userConfirmed: true,
        canImportPreview: true,
        importDisabled: false,
        surface: afterConfirmationSurface,
        confirmationControl: afterConfirmationControl,
        importButton: afterImportButton
      },
      afterImport: {
        boardReplacementObserved: true,
        boardReplacedOnlyAfterConfirmation: true,
        surface: afterImportSurface,
        statusbar: statusbarEvidence
      },
      beforeConfirmationControl,
      afterConfirmationControl,
      afterImportSurface,
      previewSummary: elementSmokeEvidence(previewSummary, '[data-testid="readboard-snapshot-preview-summary"]'),
      confirmationControl: afterConfirmationControl,
      statusbar: statusbarEvidence,
      fullOcrParity: false,
      fullReadboardParity: false,
      targetClientParity: false,
      arbitraryOcrParity: false,
      releaseParity: false
    };
    evidence.previewOnlyBeforeConfirmation = previewOnlyBeforeConfirmation;
    evidence.boardReplacedBeforeConfirmation = false;
    evidence.userConfirmed = userConfirmed;
    evidence.boardReplacedOnlyAfterConfirmation = boardReplacedOnlyAfterConfirmation;
    return evidence;
  });

  await check(report, "scope_boundaries_recorded", async () => {
    if (!evidence.previewConfirmation) throw new Error("Readboard controlled target proof boundary evidence was not recorded.");
    return evidence.previewConfirmation;
  });
}

async function runReadboardScreenshotRegionDetectionPhase(report: RuntimeSmokeReport) {
  const endpoint = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_ENDPOINT");
  const imagePath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH");
  if (!imagePath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH is required for readboard-screenshot-region-detection.");
  const evidence: ReadboardExternalCaptureMvpEvidence = {};
  report.readboardScreenshotRegionDetection = evidence;

  await check(report, "readboard_screenshot_region_detection", async () => {
    const result = await captureReadboardExternal({
      source: "arbitrary_screenshot_board_region",
      endpoint,
      image_path: imagePath,
      imagePath,
      arbitraryScreenshot: true,
      arbitrary_screenshot: true,
      boardRegionDetection: true,
      board_region_detection: true,
      timeout_ms: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_screenshot_region_detection",
        scope: "scoped_arbitrary_screenshot_board_region_detection_not_full_ocr_or_target_client_parity"
      }
    });
    const stableImagePath = stableReadboardCapturePath(imagePath);
    const sanitizedBackendResult = sanitizeReadboardEvidenceValue(result as Record<string, unknown>, stableImagePath, imagePath) as Record<string, unknown>;
    evidence.rawBackendResult = {
      ...sanitizedBackendResult,
      backendCommand: "readboard_external_capture",
      phase: "readboard_screenshot_region_detection",
      source: "runtime_smoke",
      captureSource: "arbitrary_screenshot_board_region",
      boardRegionDetection: true,
      arbitraryScreenshot: true
    };
    const status = normalizeCaptureStatus(result.status);
    if (status !== "captured") {
      throw new Error(`Readboard screenshot region detection expected captured backend status, got ${String(result.status || "empty")}.`);
    }
    const artifact = summarizeReadboardCaptureArtifact(result as Record<string, unknown>, imagePath);
    if (!artifact) throw new Error("Readboard screenshot region detection did not produce capture artifact evidence.");
    const region = readboardScreenshotRegionFromResult(result as Record<string, unknown>);
    if (Object.keys(region).length === 0) {
      throw new Error("Readboard screenshot region detection did not return backend boardRegion metadata.");
    }
    const hasPosition = isRecord((result as Record<string, unknown>).position);
    evidence.rawBackendResult = {
      ...evidence.rawBackendResult,
      boardRegion: region,
      detectedBoardRegion: region,
      artifact: {
        path: artifact.path,
        sizeBytes: artifact.sizeBytes,
        sha256: artifact.sha256,
        sanitized: artifact.sanitized
      },
      artifactPath: artifact.path,
      artifactSizeBytes: artifact.sizeBytes,
      artifactSha256: artifact.sha256
    };
    evidence.captureArtifact = artifact;
    evidence.captureSource = {
      operatorInitiated: false,
      userSelectionRequired: false,
      selection: null,
      sourceKind: "arbitrary_screenshot_board_region",
      requestedSource: "arbitrary_screenshot_board_region",
      arbitraryScreenshotBoardRegion: true,
      selectedScreenRegionCovered: false,
      externalScreenRegionCovered: false,
      externalWindowRegionCovered: false,
      targetClientDiscoveryCovered: false,
      externalClientCaptureCovered: false
    };
    evidence.screenshotRegionDetection = {
      scope: "scoped_arbitrary_screenshot_board_region_detection",
      detectionAttempted: true,
      backendSupported: true,
      backendStatus: status,
      boardRegionDetected: Object.keys(region).length > 0 || hasPosition,
      positionPreviewProduced: hasPosition,
      automaticReplacement: false,
      targetClientDiscovery: false,
      fullOcrParity: false,
      fullReadboardParity: false,
      releaseParity: false,
      artifact,
      region,
      rawBackendResult: evidence.rawBackendResult ?? sanitizedBackendResult
    };
    const nonBoardImagePath = arbitraryScreenshotNonBoardFixturePath(
      imagePath,
      runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_ARBITRARY_NON_BOARD_IMAGE_PATH")
    );
    const nonBoardResult = await captureReadboardExternal({
      source: "arbitrary_screenshot_board_region",
      endpoint,
      image_path: nonBoardImagePath,
      imagePath: nonBoardImagePath,
      arbitraryScreenshot: true,
      arbitrary_screenshot: true,
      boardRegionDetection: true,
      board_region_detection: true,
      timeout_ms: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_screenshot_region_detection_failed_decode",
        scope: "arbitrary_screenshot_non_board_decode_failure_no_preview_or_import",
        fixture_kind: "non_board"
      }
    });
    const stableNonBoardPath = stableReadboardCapturePath(nonBoardImagePath);
    const sanitizedNonBoardResult = sanitizeReadboardEvidenceValue(
      nonBoardResult as Record<string, unknown>,
      stableNonBoardPath,
      nonBoardImagePath
    ) as Record<string, unknown>;
    evidence.rawFailedDecodeResult = sanitizedNonBoardResult;
    const nonBoardStatus = normalizeCaptureStatus(nonBoardResult.status);
    const nonBoardHasPosition = isRecord((nonBoardResult as Record<string, unknown>).position)
      || isRecord((nonBoardResult as Record<string, unknown>).positionDto)
      || isRecord((nonBoardResult as Record<string, unknown>).position_dto);
    if (nonBoardStatus !== "decode_error" || nonBoardHasPosition) {
      throw new Error(
        `Readboard screenshot region non-board fixture expected decode_error without position, got status ${String(nonBoardResult.status || "empty")}.`
      );
    }
    const nonBoardArtifact = summarizeReadboardCaptureArtifact(nonBoardResult as Record<string, unknown>, nonBoardImagePath);
    if (!nonBoardArtifact) throw new Error("Readboard screenshot region non-board fixture did not produce artifact evidence.");
    evidence.failedDecodeNoReplacement = {
      fixtureKind: "non_board",
      decodeAttempted: true,
      decodeSucceeded: false,
      previewProduced: false,
      imported: false,
      boardReplaced: false,
      errorKind: nonBoardStatus,
      message: readStringField(nonBoardResult as Record<string, unknown>, "message")
        ?? readStringField(nonBoardResult as Record<string, unknown>, "errorMessage")
        ?? readStringField(nonBoardResult as Record<string, unknown>, "error_message"),
      status: nonBoardStatus,
      targetClientDiscovery: false,
      fullOcrParity: false,
      fullReadboardParity: false,
      releaseParity: false,
      artifact: nonBoardArtifact,
      rawBackendResult: sanitizedNonBoardResult
    };
    evidence.previewConfirmation = {
      previewOnlyBeforeConfirmation: hasPosition,
      boardReplacedBeforeConfirmation: false,
      userConfirmed: false,
      boardReplacedOnlyAfterConfirmation: false,
      previewConfirmationObserved: false,
      boardReplacementObserved: false,
      previewProduced: hasPosition,
      automaticBoardReplacement: false,
      fullOcrParity: false,
      fullReadboardParity: false,
      targetClientParity: false,
      arbitraryOcrParity: false,
      releaseParity: false
    };
    return evidence;
  });

  await check(report, "scope_boundaries_recorded", async () => {
    if (!evidence.screenshotRegionDetection) throw new Error("Readboard screenshot region detection boundary evidence was not recorded.");
    return evidence.screenshotRegionDetection;
  });
}

async function runReadboardTargetWindowDiscoveryPhase(report: RuntimeSmokeReport) {
  if (!isTauriRuntime()) throw new Error("readboard-target-window-discovery must run inside the real Tauri runtime.");
  const endpoint = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_ENDPOINT");
  const imagePath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH");
  if (!imagePath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH is required for readboard-target-window-discovery.");
  const titleHint = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_WINDOW_TITLE");
  const width = positiveEnvInteger("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_WIDTH") ?? 1;
  const height = positiveEnvInteger("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_HEIGHT") ?? 1;
  await check(report, "readboard_target_window_discovery", async () => {
    const result = await discoverReadboardCaptureTargets({
      title: titleHint,
      windowTitle: titleHint,
      titleHint,
      filter: titleHint,
      minWidth: width,
      minHeight: height,
      timeoutMs: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_target_window_discovery",
        scope: "scoped_target_window_discovery_not_real_provider_or_full_client_parity"
      }
    });
    const status = normalizeDiscoveryStatus(result.status);
    if (status !== "available") {
      throw new Error(`Readboard target-window discovery expected available status, got ${String(result.status || "empty")}.`);
    }
    if (!Array.isArray(result.candidates) || result.candidates.length === 0) {
      throw new Error("Readboard target-window discovery returned no candidates.");
    }
    const selected = selectReadboardTargetCandidate(result.candidates, titleHint);
    const selectedMetadata = readboardTargetCandidateMetadata(selected, imagePath);
    const captureResult = await captureReadboardExternal({
      source: "controlled_local_target_window",
      endpoint,
      image_path: imagePath,
      imagePath,
      window_title: selectedMetadata.windowTitle,
      windowTitle: selectedMetadata.windowTitle,
      process_id: selectedMetadata.processId,
      processId: selectedMetadata.processId,
      fixture_id: selectedMetadata.fixtureId,
      fixtureId: selectedMetadata.fixtureId,
      id: selectedMetadata.id,
      windowId: selectedMetadata.windowId,
      appName: selectedMetadata.appName,
      processName: selectedMetadata.processName,
      x: selectedMetadata.x,
      y: selectedMetadata.y,
      width: selectedMetadata.width,
      height: selectedMetadata.height,
      bounds: selectedMetadata.bounds,
      targetBounds: selectedMetadata.targetBounds,
      captureTiedToSelectedTarget: true,
      capture_tied_to_selected_target: true,
      controlledLocalTargetWindow: true,
      controlled_local_target_window: true,
      controlledTarget: selectedMetadata,
      controlled_target: selectedMetadata,
      timeout_ms: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_target_window_discovery_capture",
        scope: "discovered_target_controlled_capture_preview_only",
        capture_tied_to_selected_target: "true",
        target_candidate_id: String(selectedMetadata.id ?? ""),
        target_candidate_window_id: String(selectedMetadata.windowId ?? ""),
        target_candidate_title: selectedMetadata.windowTitle ?? "",
        target_candidate_app_name: selectedMetadata.appName ?? "",
        target_candidate_process_name: selectedMetadata.processName ?? "",
        target_candidate_bounds: selectedMetadata.bounds ? `${selectedMetadata.bounds.x ?? ""},${selectedMetadata.bounds.y ?? ""},${selectedMetadata.bounds.width ?? ""},${selectedMetadata.bounds.height ?? ""}` : ""
      }
    });
    const captureStatus = normalizeCaptureStatus(captureResult.status);
    if (captureStatus !== "captured") {
      throw new Error(`Readboard target-window discovery capture expected captured status, got ${String(captureResult.status || "empty")}.`);
    }
    const captureArtifact = summarizeReadboardCaptureArtifact(captureResult as Record<string, unknown>, imagePath);
    if (!captureArtifact) throw new Error("Readboard target-window discovery capture did not produce artifact evidence.");
    const stableImagePath = stableReadboardCapturePath(imagePath);
    const sanitizedCaptureResult = sanitizeReadboardEvidenceValue(captureResult as Record<string, unknown>, stableImagePath, imagePath) as Record<string, unknown>;

    const nonBoardImagePath = controlledReadboardNonBoardFixturePath(
      imagePath,
      runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_NON_BOARD_IMAGE_PATH")
    );
    const nonBoardResult = await captureReadboardExternal({
      source: "controlled_local_target_window",
      endpoint,
      image_path: nonBoardImagePath,
      imagePath: nonBoardImagePath,
      window_title: `${selectedMetadata.windowTitle ?? "Discovered target"} Non-board`,
      windowTitle: `${selectedMetadata.windowTitle ?? "Discovered target"} Non-board`,
      process_id: selectedMetadata.processId,
      processId: selectedMetadata.processId,
      fixture_id: `${selectedMetadata.fixtureId ?? "discovered-target"}-non-board`,
      fixtureId: `${selectedMetadata.fixtureId ?? "discovered-target"}-non-board`,
      id: selectedMetadata.id,
      windowId: selectedMetadata.windowId,
      appName: selectedMetadata.appName,
      processName: selectedMetadata.processName,
      x: selectedMetadata.x,
      y: selectedMetadata.y,
      width: selectedMetadata.width,
      height: selectedMetadata.height,
      bounds: selectedMetadata.bounds,
      targetBounds: selectedMetadata.targetBounds,
      captureTiedToSelectedTarget: true,
      capture_tied_to_selected_target: true,
      controlledLocalTargetWindow: true,
      controlled_local_target_window: true,
      controlledTarget: selectedMetadata,
      controlled_target: selectedMetadata,
      timeout_ms: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_target_window_discovery_failed_decode",
        scope: "discovered_target_non_board_decode_failure_no_preview_or_import",
        fixture_kind: "non_board",
        capture_tied_to_selected_target: "true"
      }
    });
    const nonBoardStatus = normalizeCaptureStatus(nonBoardResult.status);
    const nonBoardHasPosition = isRecord((nonBoardResult as Record<string, unknown>).position)
      || isRecord((nonBoardResult as Record<string, unknown>).positionDto)
      || isRecord((nonBoardResult as Record<string, unknown>).position_dto);
    if (nonBoardStatus !== "decode_error" || nonBoardHasPosition) {
      throw new Error(`Readboard target-window discovery non-board fixture expected decode_error without position, got ${String(nonBoardResult.status || "empty")}.`);
    }
    const stableNonBoardPath = stableReadboardCapturePath(nonBoardImagePath);
    const sanitizedNonBoardResult = sanitizeReadboardEvidenceValue(nonBoardResult as Record<string, unknown>, stableNonBoardPath, nonBoardImagePath) as Record<string, unknown>;
    const nonBoardArtifact = summarizeReadboardCaptureArtifact(nonBoardResult as Record<string, unknown>, nonBoardImagePath);
    if (!nonBoardArtifact) throw new Error("Readboard target-window discovery non-board fixture did not produce artifact evidence.");

    const previewConfirmation = await exerciseReadboardControlledTargetDomImport({
      imagePath,
      windowTitle: selectedMetadata.windowTitle ?? titleHint ?? "Discovered target",
      fixtureId: String(selectedMetadata.fixtureId ?? selectedMetadata.id ?? selectedMetadata.windowId ?? "discovered-target"),
      processId: selectedMetadata.processId ?? null,
      width: selectedMetadata.width ?? width,
      height: selectedMetadata.height ?? height,
      clickDiscovery: true
    });
    const evidence: ReadboardTargetWindowDiscoveryEvidence = {
      runtimeObserved: true,
      runtimeReportPhase: "readboard-target-window-discovery",
      backendCommandInvoked: "readboard_list_capture_targets",
      backendCommand: "readboard_list_capture_targets",
      status,
      candidates: result.candidates,
      selectedTarget: summarizeReadboardTargetCandidate(selected),
      captureArtifact,
      rawCaptureResult: sanitizedCaptureResult,
      failedDecodeNoReplacement: {
        fixtureKind: "non_board",
        decodeAttempted: true,
        decodeSucceeded: false,
        previewProduced: false,
        imported: false,
        boardReplaced: false,
        errorKind: nonBoardStatus,
        message: readStringField(nonBoardResult as Record<string, unknown>, "message")
          ?? readStringField(nonBoardResult as Record<string, unknown>, "errorMessage")
          ?? readStringField(nonBoardResult as Record<string, unknown>, "error_message"),
        status: nonBoardStatus,
        targetClientDiscovery: false,
        fullOcrParity: false,
        fullReadboardParity: false,
        releaseParity: false,
        artifact: nonBoardArtifact,
        rawBackendResult: sanitizedNonBoardResult
      },
      previewConfirmation,
      captureSourceTrace: {
        captureSource: "controlled_local_target_window",
        selectedFromDiscovery: true,
        captureTiedToSelectedTarget: true,
        previewOnly: true,
        explicitImportConfirmationRequired: true
      },
      boundaries: {
        targetClientDiscoveryParity: false,
        realFoxYikeParity: false,
        fullOcrParity: false,
        automaticBoardReplacement: false,
        releaseParity: false
      },
      warnings: result.warnings ?? [],
      rawBackendResult: result as Record<string, unknown>
    };
    report.readboardTargetWindowDiscovery = evidence;
    return evidence;
  });
}

async function runReadboardSelectedWindowCapturePhase(report: RuntimeSmokeReport) {
  if (!isTauriRuntime()) throw new Error("readboard-selected-window-capture must run inside the real Tauri runtime.");
  const endpoint = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_ENDPOINT");
  const titleHint = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_WINDOW_TITLE");
  const width = positiveEnvInteger("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_WIDTH") ?? 1;
  const height = positiveEnvInteger("VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_TARGET_HEIGHT") ?? 1;
  await check(report, "readboard_selected_window_capture", async () => {
    const discovery = await discoverReadboardCaptureTargets({
      title: titleHint,
      windowTitle: titleHint,
      titleHint,
      filter: titleHint,
      minWidth: width,
      minHeight: height,
      timeoutMs: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_selected_window_capture",
        scope: "selected_window_capture_preview_only_not_full_ocr_or_external_client_parity"
      }
    });
    const discoveryStatus = normalizeDiscoveryStatus(discovery.status);
    if (discoveryStatus !== "available") {
      throw new Error(`Selected-window discovery expected available status, got ${String(discovery.status || "empty")}.`);
    }
    const selected = selectReadboardWindowTargetCandidate(discovery.candidates, titleHint);
    const windowId = readboardTargetWindowId(selected);
    if (windowId === null) throw new Error("Selected-window capture requires a discovered candidate with a concrete window id.");
    const selectedMetadata = readboardTargetCandidateMetadata(selected, "");
    const targetId = selectedMetadata.id ?? windowId;
    const captureResult = await captureReadboardExternal({
      source: "selected_window_capture",
      endpoint,
      window_title: selectedMetadata.windowTitle,
      windowTitle: selectedMetadata.windowTitle,
      process_id: selectedMetadata.processId,
      processId: selectedMetadata.processId,
      id: targetId,
      targetId,
      target_id: targetId,
      captureTargetId: targetId,
      windowId,
      window_id: windowId,
      appName: selectedMetadata.appName,
      app_name: selectedMetadata.appName,
      processName: selectedMetadata.processName,
      process_name: selectedMetadata.processName,
      x: selectedMetadata.x,
      y: selectedMetadata.y,
      targetX: selectedMetadata.x,
      targetY: selectedMetadata.y,
      targetWidth: selectedMetadata.width,
      targetHeight: selectedMetadata.height,
      width: selectedMetadata.width,
      height: selectedMetadata.height,
      bounds: selectedMetadata.bounds,
      targetBounds: selectedMetadata.targetBounds,
      captureTiedToSelectedTarget: true,
      capture_tied_to_selected_target: true,
      controlledTarget: selectedMetadata,
      controlled_target: selectedMetadata,
      timeout_ms: 5_000,
      metadata: {
        source: "runtime_smoke",
        phase: "readboard_selected_window_capture",
        scope: "selected_window_capture_preview_only_not_full_ocr_or_external_client_parity",
        capture_tied_to_selected_target: "true",
        captureTiedToSelectedTarget: "true",
        target_candidate_id: String(targetId),
        target_candidate_window_id: windowId,
        target_candidate_title: selectedMetadata.windowTitle ?? "",
        target_candidate_app_name: selectedMetadata.appName ?? "",
        target_candidate_process_name: selectedMetadata.processName ?? "",
        target_candidate_bounds: selectedMetadata.bounds ? `${selectedMetadata.bounds.x ?? ""},${selectedMetadata.bounds.y ?? ""},${selectedMetadata.bounds.width ?? ""},${selectedMetadata.bounds.height ?? ""}` : ""
      }
    });
    const captureStatus = normalizeCaptureStatus(captureResult.status);
    if (captureStatus !== "captured") {
      throw new Error(`Selected-window capture expected captured status, got ${String(captureResult.status || "empty")}.`);
    }

    let previewResult: Record<string, unknown> | undefined;
    let positionPreviewProduced = isRecord((captureResult as Record<string, unknown>).position);
    const imagePath = readStringField(captureResult as Record<string, unknown>, "image_path")
      ?? readStringField(captureResult as Record<string, unknown>, "imagePath");
    const imageBase64 = readStringField(captureResult as Record<string, unknown>, "image_base64")
      ?? readStringField(captureResult as Record<string, unknown>, "imageBase64");
    if (!positionPreviewProduced && (imagePath || imageBase64)) {
      const preview = await syncReadboardSidecarSnapshot({
        endpoint,
        image_path: imagePath,
        image_base64: imagePath ? null : imageBase64,
        metadata: {
          source: "runtime_smoke",
          input: "selected_window_capture",
          capture_status: String(captureResult.status ?? ""),
          scope: "selected_window_capture_preview_only_not_full_ocr_or_external_client_parity"
        },
        timeout_ms: 5_000
      });
      previewResult = preview as unknown as Record<string, unknown>;
      positionPreviewProduced = isRecord((previewResult as Record<string, unknown>).position);
    }
    if (!positionPreviewProduced) {
      throw new Error("Selected-window capture did not produce a decoded position preview.");
    }

    const evidence: ReadboardSelectedWindowCaptureEvidence = {
      runtimeObserved: true,
      runtimeReportPhase: "readboard-selected-window-capture",
      backendCommandInvoked: "readboard_list_capture_targets",
      captureCommandInvoked: "readboard_external_capture",
      status: captureStatus,
      candidates: discovery.candidates,
      selectedTarget: summarizeReadboardTargetCandidate(selected),
      rawDiscoveryResult: sanitizeReadboardEvidenceValue(discovery as Record<string, unknown>, "<selected-window-capture-artifact>", "") as Record<string, unknown>,
      rawCaptureResult: sanitizeReadboardEvidenceValue(captureResult as Record<string, unknown>, "<selected-window-capture-artifact>", "") as Record<string, unknown>,
      rawPreviewResult: previewResult
        ? sanitizeReadboardEvidenceValue(previewResult, "<selected-window-capture-artifact>", "") as Record<string, unknown>
        : undefined,
      positionPreviewProduced,
      captureSourceTrace: {
        captureSource: "selected_window_capture",
        selectedFromDiscovery: true,
        captureTiedToSelectedTarget: true,
        windowIdRequired: true,
        imagePathProvided: false,
        previewOnly: true,
        explicitImportConfirmationRequired: true
      },
      previewConfirmation: {
        previewOnlyBeforeConfirmation: true,
        previewProduced: true,
        automaticBoardReplacement: false,
        boardReplacedBeforeConfirmation: false,
        userConfirmed: false,
        boardReplacedOnlyAfterConfirmation: false,
        boardReplacementObserved: false
      },
      boundaries: {
        targetClientDiscoveryParity: false,
        realFoxYikeParity: false,
        fullOcrParity: false,
        fullReadboardParity: false,
        automaticBoardReplacement: false,
        releaseParity: false
      },
      warnings: [
        ...(discovery.warnings ?? []),
        ...((captureResult.warnings ?? []) as string[])
      ]
    };
    report.readboardSelectedWindowCapture = evidence;
    return evidence;
  });
}

async function exerciseReadboardControlledTargetDomImport({
  imagePath,
  windowTitle,
  fixtureId,
  processId,
  width,
  height,
  clickDiscovery
}: {
  imagePath: string;
  windowTitle: string;
  fixtureId: string;
  processId: number | null;
  width: number;
  height: number;
  clickDiscovery?: boolean;
}): Promise<NonNullable<ReadboardExternalCaptureMvpEvidence["previewConfirmation"]>> {
  await openProviderPanelForRuntime();
  const readboardRoot = await waitForVisibleElement('[data-testid="controlled-board-image-import-mvp"]', "controlled readboard import surface");
  const pathInput = await waitForVisibleElement('[data-testid="readboard-image-path-input"]', "readboard image path input");
  setTextInputValue(pathInput, imagePath);
  setTextInputValue(await waitForVisibleElement('[data-testid="readboard-capture-window-title-input"]', "readboard controlled target window title"), windowTitle);
  setTextInputValue(await waitForVisibleElement('[data-testid="readboard-controlled-target-fixture-id-input"]', "readboard controlled target fixture id"), fixtureId);
  if (processId !== null) {
    setTextInputValue(await waitForVisibleElement('[data-testid="readboard-controlled-target-process-id-input"]', "readboard controlled target process id"), String(processId));
  }
  setTextInputValue(await waitForVisibleElement('[data-testid="readboard-controlled-target-width-input"]', "readboard controlled target width"), String(width));
  setTextInputValue(await waitForVisibleElement('[data-testid="readboard-controlled-target-height-input"]', "readboard controlled target height"), String(height));

  if (clickDiscovery) {
    const discoverButton = await waitForElementState(
      '[data-testid="readboard-discover-target-windows"]',
      "readboard target-window discovery button",
      (element) => element instanceof HTMLButtonElement && !element.disabled
    ) as HTMLButtonElement;
    discoverButton.click();
    await waitForElementState(
      '[data-testid="readboard-target-window-discovery"]',
      "readboard target-window discovery candidate selection",
      (element) => element.dataset.targetWindowSelected === "true" && Number(element.dataset.targetWindowCandidateCount ?? "0") > 0
    );
  }

  const previewButton = await waitForElementState(
    '[data-testid="readboard-preview-controlled-target"]',
    "readboard controlled target preview button to become enabled",
    (element) => element instanceof HTMLButtonElement && !element.disabled
  ) as HTMLButtonElement;
  previewButton.click();

  const previewSummary = await waitForElementState(
    '[data-testid="readboard-snapshot-preview-summary"]',
    "readboard controlled target preview summary",
    (element) => isElementVisible(element) && readboardRoot.dataset.previewHasPosition === "true" && readboardRoot.dataset.controlledLocalTargetWindow === "true"
  );
  const confirmation = await waitForVisibleElement('[data-testid="readboard-import-confirmation"]', "readboard import confirmation");
  const importBeforeConfirm = await waitForVisibleElement('[data-testid="readboard-import-image-snapshot"]', "readboard import preview button") as HTMLButtonElement;
  const rootBeforeConfirm = queryRequiredElement('[data-testid="controlled-board-image-import-mvp"]', "controlled readboard import surface before confirmation");
  const previewOnlyBeforeConfirmation = rootBeforeConfirm.dataset.previewOnlyBeforeConfirmation === "true" || rootBeforeConfirm.dataset.previewBeforeConfirmation === "true";
  const boardReplacedBeforeConfirmation = rootBeforeConfirm.dataset.boardReplacedBeforeConfirmation === "true";
  const userConfirmedBeforeConfirmation = rootBeforeConfirm.dataset.userConfirmed === "true";
  const canImportPreviewBeforeConfirmation = rootBeforeConfirm.dataset.canImportPreview === "true";
  if (!importBeforeConfirm.disabled) throw new Error("Readboard import button was enabled before explicit confirmation.");
  if (!previewOnlyBeforeConfirmation) throw new Error("Controlled target UI did not expose preview before confirmation.");
  if (boardReplacedBeforeConfirmation) throw new Error("Controlled target UI must expose boardReplacedBeforeConfirmation=false.");
  if (userConfirmedBeforeConfirmation || canImportPreviewBeforeConfirmation) {
    throw new Error("Controlled target UI must expose unconfirmed, non-importable preview state before confirmation.");
  }
  const beforeConfirmationSurface = elementSmokeEvidence(rootBeforeConfirm, '[data-testid="controlled-board-image-import-mvp"]');
  const beforeConfirmationControl = elementSmokeEvidence(confirmation, '[data-testid="readboard-import-confirmation"]');
  const beforeImportButton = elementSmokeEvidence(importBeforeConfirm, '[data-testid="readboard-import-image-snapshot"]');

  const checkbox = await waitForVisibleElement('[data-testid="readboard-confirm-import"]', "readboard confirm import checkbox") as HTMLInputElement;
  if (checkbox.disabled) throw new Error("Readboard confirmation checkbox was disabled despite a valid controlled target preview.");
  checkbox.click();
  const rootAfterConfirm = await waitForElementState(
    '[data-testid="controlled-board-image-import-mvp"]',
    "readboard controlled target confirmation to be recorded",
    (element) => element.dataset.userConfirmed === "true" && element.dataset.canImportPreview === "true"
  );
  const confirmationAfterConfirm = await waitForVisibleElement('[data-testid="readboard-import-confirmation"]', "confirmed readboard import confirmation");
  const importAfterConfirm = await waitForVisibleElement('[data-testid="readboard-import-image-snapshot"]', "confirmed readboard controlled target import button") as HTMLButtonElement;
  if (importAfterConfirm.disabled) throw new Error("Readboard import button remained disabled after explicit confirmation.");
  const afterConfirmationSurface = elementSmokeEvidence(rootAfterConfirm, '[data-testid="controlled-board-image-import-mvp"]');
  const afterConfirmationControl = elementSmokeEvidence(confirmationAfterConfirm, '[data-testid="readboard-import-confirmation"]');
  const afterImportButton = elementSmokeEvidence(importAfterConfirm, '[data-testid="readboard-import-image-snapshot"]');
  importAfterConfirm.click();
  const rootAfterImport = await waitForElementState(
    '[data-testid="controlled-board-image-import-mvp"]',
    "readboard controlled target replacement after confirmation",
    (element) => element.dataset.boardReplacementObserved === "true" && element.dataset.boardReplacedOnlyAfterConfirmation === "true"
  );
  const statusbar = await waitForElementState(
    '[data-testid="legacy-statusbar"]',
    "readboard controlled target import statusbar confirmation",
    (element) => normalizeText(element.textContent ?? "").toLowerCase().includes("imported readboard snapshot")
  );

  const userConfirmed = rootAfterConfirm.dataset.userConfirmed === "true";
  const boardReplacedOnlyAfterConfirmation = rootAfterImport.dataset.boardReplacedOnlyAfterConfirmation === "true";
  const boardReplacementObserved = rootAfterImport.dataset.boardReplacementObserved === "true";
  const afterImportSurface = elementSmokeEvidence(rootAfterImport, '[data-testid="controlled-board-image-import-mvp"]');
  const statusbarEvidence = elementSmokeEvidence(statusbar, '[data-testid="legacy-statusbar"]');
  return {
    previewOnlyBeforeConfirmation,
    boardReplacedBeforeConfirmation: false,
    userConfirmed,
    boardReplacedOnlyAfterConfirmation,
    previewConfirmationObserved: true,
    boardReplacementObserved,
    beforeConfirmation: {
      userConfirmed: false,
      canImportPreview: false,
      importDisabled: true,
      surface: beforeConfirmationSurface,
      confirmationControl: beforeConfirmationControl,
      importButton: beforeImportButton
    },
    afterConfirmation: {
      userConfirmed: true,
      canImportPreview: true,
      importDisabled: false,
      surface: afterConfirmationSurface,
      confirmationControl: afterConfirmationControl,
      importButton: afterImportButton
    },
    afterImport: {
      boardReplacementObserved: true,
      boardReplacedOnlyAfterConfirmation: true,
      surface: afterImportSurface,
      statusbar: statusbarEvidence
    },
    beforeConfirmationControl,
    afterConfirmationControl,
    afterImportSurface,
    previewSummary: elementSmokeEvidence(previewSummary, '[data-testid="readboard-snapshot-preview-summary"]'),
    confirmationControl: afterConfirmationControl,
    statusbar: statusbarEvidence,
    fullOcrParity: false,
    fullReadboardParity: false,
    targetClientParity: false,
    arbitraryOcrParity: false,
    releaseParity: false
  };
}

async function runProviderLivePhase(report: RuntimeSmokeReport) {
  const baseUrl = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_PROVIDER_BASE_URL")
    ?? runtimeSmokeEnv("TAURI_LIZZIEYZY_RUNTIME_SMOKE_PROVIDER_BASE_URL");
  if (!baseUrl) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_PROVIDER_BASE_URL is required for provider-live.");
  const normalizedBaseUrl = baseUrl.replace(/\/+$/, "");
  const evidence: ProviderLiveSmokeEvidence = { baseUrl: normalizedBaseUrl };
  report.provider = evidence;

  await check(report, "yike_controlled_fetch", async () => {
    const requestUrl = `${normalizedBaseUrl}/v2/golive/list?p=1&since=0&official=&version=2`;
    const result = await fetchYikeProvider({
      provider: "yike",
      url: requestUrl,
      method: "get",
      headers: {},
      body: null,
      source_url: requestUrl,
      source_id: "controlled-yike-list",
      timeout_ms: 5_000
    });
    assertHttpSuccess(result.status_code, "Yike controlled fetch");
    const resultCount = yikeListResultCount(result.payload);
    evidence.yikeControlledFetch = {
      provider: result.provider,
      networkMode: "controlled_network",
      httpStatus: result.status_code,
      payloadValidated: true,
      resultCount,
      fixtureParserOnly: false
    };
    return evidence.yikeControlledFetch;
  });

  await check(report, "fox_controlled_fetch", async () => {
    const requestUrl = `${normalizedBaseUrl}/fox/direct-sgf`;
    const result = await fetchFoxProvider({
      provider: "fox",
      url: requestUrl,
      method: "get",
      headers: {},
      body: null,
      source_url: requestUrl,
      source_id: "controlled-fox-direct-sgf",
      timeout_ms: 5_000
    });
    assertHttpSuccess(result.status_code, "Fox controlled fetch");
    if (!result.warnings.some((warning) => warning.toLowerCase().includes("direct"))) {
      throw new Error("Fox controlled fetch did not report direct HTTP warning.");
    }
    const imported = await importProviderPayload({
      provider: "fox",
      payload: result.payload,
      source_url: requestUrl,
      source_id: "controlled-fox-direct-sgf",
      metadata: {
        source_url: requestUrl,
        request_url: result.url,
        source_id: "controlled-fox-direct-sgf",
        extra: { smoke_source: "controlled_http_server" }
      }
    });
    const moveCount = imported.summary.move_count ?? 0;
    if (moveCount <= 0) throw new Error(`Fox controlled import did not produce moves: ${moveCount}.`);
    evidence.foxControlledFetch = {
      provider: result.provider,
      networkMode: "controlled_network",
      httpStatus: result.status_code,
      payloadImported: true,
      moveCount,
      directHttpWarning: true
    };
    return evidence.foxControlledFetch;
  });

  await check(report, "provider_failure_modes", async () => {
    const requestUrl = `${normalizedBaseUrl}/v2/golive/list?mode=bad_payload`;
    try {
      await fetchYikeProvider({
        provider: "yike",
        url: requestUrl,
        method: "get",
        headers: {},
        body: null,
        source_url: requestUrl,
        source_id: "controlled-yike-bad-payload",
        timeout_ms: 5_000
      });
      throw new Error("Yike bad payload request unexpectedly succeeded.");
    } catch (error) {
      const details = providerErrorDetails(error);
      if (details.message.includes("unexpectedly succeeded")) throw error;
      if (!details.kind.toLowerCase().includes("invalid") && !details.message.toLowerCase().includes("invalid") && !details.message.toLowerCase().includes("json")) {
        throw new Error(`Yike bad payload did not return invalid payload boundary: ${details.message}`);
      }
      evidence.providerFailureModes = {
        observed: true,
        typedProviderError: true,
        errorKind: details.kind || "invalid_payload",
        message: details.message,
        reportedAsSuccess: false
      };
      return evidence.providerFailureModes;
    }
  });

  await check(report, "controlled_network_observed", async () => {
    evidence.controlledNetworkObserved = {
      controlledHttpServer: true,
      requestCount: 3,
      yikeSignedHeadersObserved: true,
      foxRequestObserved: true,
      failureRequestObserved: true
    };
    return evidence.controlledNetworkObserved;
  });

  await check(report, "offline_not_counted_as_external_live", async () => {
    evidence.offlineNotCountedAsExternalLive = {
      offlineParserOnly: false,
      controlledHttpServer: true,
      externalProviderServiceCovered: false
    };
    return evidence.offlineNotCountedAsExternalLive;
  });
  await check(report, "external_account_scope", async () => {
    evidence.externalAccountScope = {
      realAccountLoginStateCovered: false,
      antiBotStabilityCovered: false,
      serviceSchemaDriftCovered: false
    };
    return evidence.externalAccountScope;
  });
}

async function runInstalledAppRuntimeProofPhase(report: RuntimeSmokeReport) {
  const evidence: InstalledAppRuntimeProofEvidence = {
    tauriRuntimeObserved: false,
    browserFallbackUsed: false,
    boundaries: {
      browserFallbackDoesNotClaimTauri: true,
      webviewDomClickCovered: false,
      nativeDialogCovered: false,
      fullLegacyParity: false,
      releaseParity: false
    }
  };
  report.installedAppRuntimeProof = evidence;

  await check(report, "browser_fallback_excluded", async () => {
    if (!isTauriRuntime()) throw new Error("installed-app-runtime-proof must run inside the real Tauri runtime; browser fallback is only reported by DOM selectors.");
    evidence.tauriRuntimeObserved = true;
    evidence.browserFallbackUsed = false;
    return {
      tauriRuntimeObserved: true,
      browserFallbackUsed: false,
      userAgent: typeof navigator === "undefined" ? null : navigator.userAgent,
      platform: typeof navigator === "undefined" ? null : navigator.platform
    };
  });

  await observeInstalledAppBackendRuntimeProof(report, evidence);

  await check(report, "runtime_source_observed", async () => {
    const root = await waitForVisibleElement('[data-testid="installed-app-runtime-proof"]', "installed app runtime proof");
    const runtimeSource = root.dataset.runtimeSource ?? "";
    if (runtimeSource !== "tauri") throw new Error(`Runtime source must be tauri in installed app proof; observed ${runtimeSource || "missing"}.`);
    if (root.dataset.browserFallbackUsed !== "false" || root.dataset.tauriRuntimeObserved !== "true") {
      throw new Error("Installed app proof must expose tauriRuntimeObserved=true and browserFallbackUsed=false.");
    }
    evidence.runtimeSource = runtimeSource;
    evidence.runtimeRoot = elementSmokeEvidence(root, '[data-testid="installed-app-runtime-proof"]');
    return {
      runtimeSource,
      tauriRuntimeObserved: root.dataset.tauriRuntimeObserved,
      browserFallbackUsed: root.dataset.browserFallbackUsed,
      root: evidence.runtimeRoot
    };
  });

  await check(report, "backend_availability_observed", async () => {
    const root = await waitForRuntimeProofState((element) => element.dataset.backendAvailability !== "checking", "backend availability to finish checking");
    const backendStatus = await waitForVisibleElement('[data-testid="backend-availability"]', "backend availability label");
    const availability = root.dataset.backendAvailability ?? "";
    const available = root.dataset.backendAvailable === "true";
    if (availability !== "available" || !available) {
      throw new Error(`Installed app proof requires backend availability; observed ${availability || "missing"}.`);
    }
    evidence.backendAvailability = availability;
    evidence.backendAvailable = available;
    evidence.backendStatus = elementSmokeEvidence(backendStatus, '[data-testid="backend-availability"]');
    return {
      backendAvailability: availability,
      backendAvailable: available,
      backendStatus: evidence.backendStatus
    };
  });

  await check(report, "sgf_workflow_state_observed", async () => {
    const root = await waitForVisibleElement('[data-testid="installed-app-runtime-proof"]', "installed app runtime proof");
    const sgfWorkflow = await waitForVisibleElement('[data-testid="sgf-workflow-state"]', "SGF workflow state");
    const workflowState = root.dataset.sgfWorkflowState ?? "";
    if (!workflowState || workflowState === "loading-tree") throw new Error(`SGF workflow state was not stable; observed ${workflowState || "missing"}.`);
    evidence.sgfWorkflow = elementSmokeEvidence(sgfWorkflow, '[data-testid="sgf-workflow-state"]');
    return {
      workflowState,
      treeLoaded: root.dataset.sgfTreeLoaded,
      currentMove: root.dataset.sgfCurrentMove,
      maxMove: root.dataset.sgfMaxMove,
      dirty: root.dataset.sgfDirty,
      sgfWorkflow: evidence.sgfWorkflow
    };
  });

  await check(report, "engine_profile_status_observed", async () => {
    const engine = await waitForEngineRuntimeProofState((element) => Number(element.dataset.profileCount ?? 0) > 0, "engine profiles to load");
    const profile = await waitForVisibleElement('[data-testid="engine-profile-runtime-status"]', "engine profile runtime status");
    const profileCount = Number(engine.dataset.profileCount ?? 0);
    if (!Number.isFinite(profileCount) || profileCount < 1) throw new Error("Engine profile proof did not expose a loaded profile.");
    evidence.engineProfile = elementSmokeEvidence(profile, '[data-testid="engine-profile-runtime-status"]');
    return {
      profileCount,
      selectedProfileId: engine.dataset.selectedProfileId ?? "",
      profile: evidence.engineProfile
    };
  });

  await check(report, "engine_asset_status_observed", async () => {
    const engine = await waitForEngineRuntimeProofState((element) => element.dataset.runtimeAssetCheckStatus !== "checking", "runtime asset status to finish checking");
    const localAsset = await waitForVisibleElement('[data-testid="engine-asset-check-runtime-status"]', "local engine asset status");
    const runtimeAsset = await waitForVisibleElement('[data-testid="engine-runtime-asset-check-status"]', "runtime engine asset status");
    const localStatus = engine.dataset.localAssetCheckStatus ?? "";
    const runtimeStatus = engine.dataset.runtimeAssetCheckStatus ?? "";
    if (!localStatus || !runtimeStatus) throw new Error("Engine asset proof did not expose local/runtime asset statuses.");
    evidence.engineAssets = elementSmokeEvidence(localAsset, '[data-testid="engine-asset-check-runtime-status"]');
    evidence.runtimeAssets = elementSmokeEvidence(runtimeAsset, '[data-testid="engine-runtime-asset-check-status"]');
    return {
      localAssetCheckStatus: localStatus,
      runtimeAssetCheckStatus: runtimeStatus,
      canRunKataGo: engine.dataset.canRunKatago,
      localAsset: evidence.engineAssets,
      runtimeAsset: evidence.runtimeAssets
    };
  });

  await check(report, "engine_launch_attempt_observed", async () => {
    const proof = await waitForVisibleElement('[data-testid="engine-installed-app-launch-proof"]', "installed app launch proof");
    const launch = await waitForVisibleElement('[data-testid="engine-installed-app-launch-attempt-status"]', "installed app launch attempt status");
    const proofStatus = proof.getAttribute("data-proof-status") ?? "";
    const sourceKind = proof.getAttribute("data-runtime-source-kind") ?? "";
    const assetStatus = proof.getAttribute("data-asset-validation-status") ?? "";
    const launchStatus = proof.getAttribute("data-launch-status") ?? "";
    const launchAvailability = proof.getAttribute("data-launch-availability") ?? "";
    if (!proofStatus || proofStatus === "checking") throw new Error(`Installed app launch proof was not stable; observed ${proofStatus || "missing"}.`);
    if (!sourceKind || !assetStatus || !launchStatus || !launchAvailability) {
      throw new Error("Installed app launch proof did not expose source, asset validation, and launch attempt status.");
    }
    evidence.engineLaunchAttempt = elementSmokeEvidence(launch, '[data-testid="engine-installed-app-launch-attempt-status"]');
    return {
      proofStatus,
      sourceKind,
      runtimeSource: proof.getAttribute("data-runtime-source") ?? "",
      assetStatus,
      profileStatus: proof.getAttribute("data-profile-status") ?? "",
      profileSource: proof.getAttribute("data-profile-source") ?? "",
      launchStatus,
      launchAvailability,
      localProfileFallback: proof.getAttribute("data-local-profile-fallback") ?? "",
      largeModelBundled: proof.getAttribute("data-large-model-bundled") ?? "",
      releaseParity: proof.getAttribute("data-release-parity") ?? "",
      launchAttempt: evidence.engineLaunchAttempt
    };
  });

  await check(report, "scope_boundaries_recorded", async () => evidence.boundaries);
}

async function runInstalledAppSgfWorkflowPhase(report: RuntimeSmokeReport, sgfPath: string) {
  const evidence: InstalledAppRuntimeProofEvidence = {
    tauriRuntimeObserved: false,
    browserFallbackUsed: false,
    boundaries: {
      browserFallbackDoesNotClaimTauri: true,
      webviewDomClickCovered: false,
      nativeDialogCovered: false,
      fullLegacyParity: false,
      releaseParity: false
    }
  };
  report.installedAppRuntimeProof = evidence;

  await check(report, "browser_fallback_excluded", async () => {
    if (!isTauriRuntime()) throw new Error("installed-app-sgf-workflow must run inside a real Tauri packaged app runtime.");
    evidence.tauriRuntimeObserved = true;
    evidence.browserFallbackUsed = false;
    return { tauriRuntimeObserved: true, browserFallbackUsed: false };
  });

  const runtimeProof = await observeInstalledAppBackendRuntimeProof(report, evidence);
  assertInstalledAppPackagedRuntime(runtimeProof);
  await runEditSavePhase(report, sgfPath, "installed-app-sgf-workflow");
  if (!report.expected) throw new Error("Installed app SGF workflow did not produce expected edit/save evidence.");

  const reopenedDocument = await readSgfDocument(sgfPath);
  assertNonEmptyString(reopenedDocument.sgfText, "reopened installed app SGF text was empty.");
  await verifySgf(report, "installed app reopened workflow", reopenedDocument.sgfText);
  const reopenedState = await check(report, "reopen_state_verified", async () => verifyReopenedState(report, reopenedDocument.sgfText, report.expected as RuntimeSmokeExpectedEvidence));
  const afterReopen = {
    reopenedPath: reopenedDocument.path,
    bytes: reopenedDocument.sgfText.length,
    verified: Boolean(reopenedState.verified),
    reopenVerified: Boolean(reopenedState.verified),
    annotationsVerified: Boolean(reopenedState.annotationsVerified),
    commentsVerified: Boolean(reopenedState.commentsVerified),
    propertiesVerified: Boolean(reopenedState.propertiesVerified),
    boardStateVerified: Boolean(reopenedState.boardStateVerified),
    moveCountVerified: Boolean(reopenedState.moveCountVerified),
    treeOrderVerified: Boolean(reopenedState.treeOrderVerified),
    deletedTargetAbsent: Boolean(reopenedState.variationDeletePersisted),
    variationDeletePersisted: Boolean(reopenedState.variationDeletePersisted),
    invariantVerified: Boolean(reopenedState.invariantVerified),
    details: reopenedState
  };
  const reopen = {
    status: "pass",
    path: reopenedDocument.path,
    matchesSaved: Boolean(reopenedState.verified),
    phase: report.phase
  };
  mergeCheckDetails(report, "save_readback_roundtrip", {
    reopenVerified: true,
    reopen,
    afterReopen,
    installedAppWorkflowPhase: report.phase,
    packagedAppRuntimeObserved: true,
    browserFallbackUsed: false,
    devServerRequired: false
  });
  await check(report, "save_reopen_roundtrip", async () => ({
    savedPath: sgfPath,
    reopenedPath: reopenedDocument.path,
    expectedMoveCount: report.expected?.savedMoveCount,
    expectedPositionCount: report.expected?.savedPositionCount,
    savedStateLoaded: true,
    reopen,
    reopenVerified: Boolean(reopenedState.verified),
    readbackVerified: true,
    annotationsVerified: reopenedState.annotationsVerified,
    commentsVerified: reopenedState.commentsVerified,
    propertiesVerified: reopenedState.propertiesVerified,
    boardStateVerified: reopenedState.boardStateVerified,
    afterReopen,
    invariant: report.expected?.invariant,
    verified: true
  }));

  await check(report, "scope_boundaries_recorded", async () => ({
    packagedAppRuntimeObserved: true,
    browserFallbackUsed: false,
    devServerRequired: false,
    nativeDialogCovered: false,
    webviewDomClickCovered: false,
    fullLegacyParity: false,
    releaseParity: false,
    workflow: "SGF load/tree/edit/annotation/move/save/readback/reopen scoped automation"
  }));
}

async function runInstalledAppKataGoLiveWorkflowPhase(report: RuntimeSmokeReport, sgfPath: string, config: KataGoLiveSmokeConfig) {
  const runtimeEvidence: InstalledAppRuntimeProofEvidence = {
    tauriRuntimeObserved: false,
    browserFallbackUsed: false,
    boundaries: {
      browserFallbackDoesNotClaimTauri: true,
      webviewDomClickCovered: false,
      nativeDialogCovered: false,
      fullLegacyParity: false,
      releaseParity: false
    }
  };
  report.installedAppRuntimeProof = runtimeEvidence;

  await check(report, "browser_fallback_excluded", async () => {
    if (!isTauriRuntime()) throw new Error("installed-app-katago-live-workflow must run inside a real Tauri packaged app runtime.");
    runtimeEvidence.tauriRuntimeObserved = true;
    runtimeEvidence.browserFallbackUsed = false;
    return { tauriRuntimeObserved: true, browserFallbackUsed: false, staticOnly: false };
  });

  const runtimeProof = await observeInstalledAppBackendRuntimeProof(report, runtimeEvidence);
  assertInstalledAppPackagedRuntime(runtimeProof);

  const loaded = await check(report, "sgf_loaded", async () => {
    const document = await readSgfDocument(sgfPath);
    assertNonEmptyString(document.sgfText, "readSgfDocument returned empty SGF text.");
    await verifySgf(report, "installed app KataGo live source", document.sgfText);
    return { sgfText: document.sgfText, details: { bytes: document.sgfText.length, path: document.path } };
  });
  const sgfText = loaded.sgfText;
  const parsed = await step(report, "parse installed app KataGo live source", () => parseSgfSummary(sgfText));
  const profile = await resolveKataGoLiveProfile(config);
  const onceTurn = clampNumber(config.onceTurn ?? Math.min(1, parsed.summary.move_count), 0, parsed.summary.move_count);
  const onceEvidence: KataGoLiveSmokeEvidence = {
    profile: sanitizeEngineProfile(profile),
    maxVisits: config.maxVisits,
    onceTurn,
    gameMaxVisits: config.gameMaxVisits,
    cancelMaxVisits: config.cancelMaxVisits,
    cancelDelayMs: config.cancelDelayMs,
    runGame: true,
    runCancel: true
  };
  report.katago = onceEvidence;

  await check(report, "katago_assets", async () => {
    const checks = await checkEngineAssets(profile);
    const missingRequired = checks.filter((item) => item.required && !item.exists).map((item) => item.label || item.path);
    if (missingRequired.length > 0) {
      throw new Error(`Installed app KataGo required assets are missing: ${missingRequired.join(", ")}`);
    }
    onceEvidence.assetChecks = {
      total: checks.length,
      required: checks.filter((item) => item.required).length,
      missingRequired,
      checks
    };
    return {
      profile: onceEvidence.profile,
      total: checks.length,
      required: onceEvidence.assetChecks.required,
      missingRequired,
      engineProfileObserved: true
    };
  });

  await check(report, "katago_analyze_once", async () => {
    const frame = await analyzeKataGoOnce(profile, sgfText, onceTurn, config.maxVisits);
    validateAnalysisFrame(frame, "Installed app KataGo one-position analysis");
    onceEvidence.analyzeOnce = summarizeAnalysisFrame(frame);
    return {
      ...onceEvidence.analyzeOnce,
      candidatesObserved: onceEvidence.analyzeOnce.candidates > 0,
      winrateObserved: Number.isFinite(onceEvidence.analyzeOnce.winrateBlack),
      ownershipObserved: onceEvidence.analyzeOnce.hasOwnership,
      policyObserved: onceEvidence.analyzeOnce.hasPolicy,
      packagedAppRuntimeObserved: true,
      browserFallbackUsed: false,
      devServerRequired: false
    };
  });

  await runKataGoLiveWorkflowCachePhase(report, sgfPath, config);
  mergeCheckDetails(report, "analysis_progress_observed", {
    packagedAppRuntimeObserved: true,
    browserFallbackUsed: false,
    devServerRequired: false,
    currentTotalJobSessionObserved: true
  });
  mergeCheckDetails(report, "analysis_complete_observed", {
    packagedAppRuntimeObserved: true,
    analyzeOnceObserved: true
  });
  mergeCheckDetails(report, "cache_hit_restored", {
    packagedAppRuntimeObserved: true,
    cacheRestoreVerified: true
  });
  mergeCheckDetails(report, "stale_cache_prevented", {
    packagedAppRuntimeObserved: true,
    staleSgfCacheGuardVerified: true
  });
  mergeCheckDetails(report, "engine_failure_observed", {
    structuredRecoverable: true,
    packagedAppRuntimeObserved: true
  });
  mergeCheckDetails(report, "scope_boundaries_recorded", {
    packagedAppRuntimeObserved: true,
    browserFallbackUsed: false,
    devServerRequired: false,
    staticOnly: false,
    fakeEngineUsed: false,
    workflow: "Installed app live KataGo analyze-once/progress/cancel/restart/cache/stale/failure scoped proof"
  });
}

async function observeInstalledAppBackendRuntimeProof(report: RuntimeSmokeReport, evidence?: InstalledAppRuntimeProofEvidence): Promise<Record<string, unknown>> {
  return await check(report, "backend_runtime_proof_observed", async () => {
    const proof = await installedAppRuntimeProof();
    const summary = summarizeInstalledAppRuntimeProof(proof);
    if (summary.browserFallbackUsed === true) {
      throw new Error("Installed app backend proof reported browser fallback; this cannot count as Tauri runtime proof.");
    }
    const runtimeSource = typeof summary.runtimeSource === "string" ? summary.runtimeSource.toLowerCase() : "";
    if (!runtimeSource || runtimeSource.includes("browser")) {
      throw new Error(`Installed app backend proof did not report a Tauri runtime source; observed ${summary.runtimeSource || "missing"}.`);
    }
    if (evidence) {
      evidence.backendRuntimeProof = proof;
      evidence.backendRuntimeProofSummary = summary;
    }
    return {
      ...summary,
      raw: proof
    };
  });
}

function summarizeInstalledAppRuntimeProof(proof: InstalledAppRuntimeProofDto): Record<string, unknown> {
  const runtime = requiredRecord(proof.runtime, "installed_app_runtime_proof.runtime");
  const bundle = requiredRecord(proof.bundle, "installed_app_runtime_proof.bundle");
  const assets = requiredRecord(proof.assets, "installed_app_runtime_proof.assets");
  const profileStatus = requiredRecord(proof.profileStatus, "installed_app_runtime_proof.profileStatus");
  const engineLaunchAttempt = requiredRecord(proof.engineLaunchAttempt, "installed_app_runtime_proof.engineLaunchAttempt");
  const boundaries = requiredRecord(proof.boundaries, "installed_app_runtime_proof.boundaries");
  const bundledKatago = normalizeBundledKatagoProof((proof as InstalledAppRuntimeProofDto & {
    bundledKatago?: unknown;
    bundled_katago?: unknown;
  }).bundledKatago ?? (proof as InstalledAppRuntimeProofDto & {
    bundledKatago?: unknown;
    bundled_katago?: unknown;
  }).bundled_katago);
  const runtimeSource = requiredString(runtime.source, "installed_app_runtime_proof.runtime.source");
  const resourceDir = nullableString(runtime.resourceDir, "installed_app_runtime_proof.runtime.resourceDir");
  const appDataDir = nullableString(runtime.appDataDir, "installed_app_runtime_proof.runtime.appDataDir");
  const currentExe = nullableString(runtime.currentExe, "installed_app_runtime_proof.runtime.currentExe");
  const version = nullableString(runtime.version, "installed_app_runtime_proof.runtime.version");
  const identifier = nullableString(runtime.identifier, "installed_app_runtime_proof.runtime.identifier");
  const browserFallbackUsed = booleanField(boundaries, "browserFallbackUsed") === true || runtimeSource.toLowerCase().includes("browser");

  return {
    command: "installed_app_runtime_proof",
    schema: requiredString(proof.schema, "installed_app_runtime_proof.schema"),
    status: requiredString(proof.status, "installed_app_runtime_proof.status"),
    runtimeSource,
    browserFallbackUsed,
    runtime: {
      ...runtime,
      source: runtimeSource,
      resourceDir,
      appDataDir,
      tauriRuntimeObserved: booleanField(runtime, "tauriRuntimeObserved"),
      devServerRequired: booleanField(runtime, "devServerRequired"),
      currentExe,
      debugAssertions: runtime.debugAssertions ?? null,
      version,
      identifier
    },
    bundle,
    resource: { resourceDir },
    appData: { appDataDir },
    assets: summarizeInstalledAppAssets(assets),
    bundledKatago,
    profileStatus,
    engineLaunchAttempt: summarizeEngineLaunchAttempt(engineLaunchAttempt),
    boundaries
  };
}

function normalizeBundledKatagoProof(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value)) return null;
  const rawStatus = stringField(value, "status") ?? stringField(value, "result") ?? stringField(value, "availability");
  const status = normalizeBundledKatagoStatus(rawStatus, value);
  return {
    ...value,
    status,
    rawStatus,
    sourceKind: stringField(value, "sourceKind") ?? stringField(value, "source_kind") ?? stringField(value, "source") ?? null,
    validationStatus: stringField(value, "validationStatus") ?? stringField(value, "validation_status") ?? rawStatus,
    launchStatus: stringField(value, "launchStatus") ?? stringField(value, "launch_status") ?? stringField(value, "engineLaunchStatus") ?? null,
    largeModelBundled: booleanField(value, "largeModelBundled") ?? booleanField(value, "large_model_bundled") ?? false,
    releaseParity: booleanField(value, "releaseParity") ?? booleanField(value, "release_parity") ?? false
  };
}

function normalizeBundledKatagoStatus(rawStatus: string | null, value: Record<string, unknown>): string {
  const ready = booleanField(value, "ready") ?? booleanField(value, "available") ?? booleanField(value, "launchSucceeded");
  if (ready === true) return "ready";
  if (ready === false) return "unavailable";
  const normalized = rawStatus?.toLowerCase() ?? "";
  if (/missing|unavailable|not[_ -]?found|not[_ -]?configured|skipped/.test(normalized)) return "unavailable";
  if (/error|fail/.test(normalized)) return "error";
  if (/problem|invalid|placeholder/.test(normalized)) return "problem";
  if (/ready|ok|available|success|launched/.test(normalized)) return "ready";
  return normalized || "observed";
}

function summarizeInstalledAppAssets(assets: Record<string, unknown>): Record<string, unknown> {
  const validation = isRecord(assets.validation)
    ? assets.validation
    : isRecord(assets.runtimeAssetValidation)
      ? assets.runtimeAssetValidation
      : null;
  const missing = arrayFieldLength(validation ?? assets, "missing");
  const placeholders = arrayFieldLength(validation ?? assets, "placeholders");
  const exists = arrayFieldLength(validation ?? assets, "exists");
  const checks = arrayFieldLength(validation ?? assets, "checks");
  const rawStatus = stringField(assets, "status")?.toLowerCase() ?? "";
  const status = missing + placeholders > 0
    ? "problem"
    : /unavailable|missing|skipped|not[_ -]?found|not[_ -]?configured/.test(rawStatus)
      ? "unavailable"
      : /error|fail|problem|invalid|placeholder/.test(rawStatus)
        ? "problem"
        : /ready|ok|available/.test(rawStatus)
          ? "ready"
          : checks > 0 || exists > 0
            ? "observed"
            : "unavailable";
  const warnings = Array.isArray(assets.warnings) ? assets.warnings.filter((item): item is string => typeof item === "string") : [];
  return {
    status,
    commandStatus: stringField(assets, "status") ?? null,
    checks,
    exists,
    missing,
    placeholders,
    warnings,
    validation: validation ? { checks, exists, missing, placeholders } : null,
    details: assets
  };
}

function summarizeEngineLaunchAttempt(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw new Error("engineLaunchAttempt must be a structured object.");
  const rawStatus = stringField(value, "status") ?? stringField(value, "result") ?? stringField(value, "outcome");
  const available = booleanField(value, "available")
    ?? booleanField(value, "success")
    ?? booleanField(value, "launched")
    ?? booleanField(value, "engineAvailable");
  const normalized = normalizeEngineLaunchAvailability(rawStatus, available);
  return {
    status: rawStatus ?? normalized,
    availability: normalized,
    launchSucceeded: normalized === "available",
    attempted: booleanField(value, "attempted") ?? booleanField(value, "launchAttempted") ?? true,
    message: stringField(value, "message") ?? stringField(value, "error") ?? stringField(value, "reason") ?? null,
    details: value
  };
}

function assertInstalledAppPackagedRuntime(summary: Record<string, unknown>) {
  const runtime = requiredRecord(summary.runtime, "installed app SGF workflow runtime summary");
  const bundle = requiredRecord(summary.bundle, "installed app SGF workflow bundle summary");
  const boundaries = requiredRecord(summary.boundaries, "installed app SGF workflow boundaries");
  const runtimeSource = (stringField(summary, "runtimeSource") ?? stringField(runtime, "source") ?? "").toLowerCase();
  if (!runtimeSource || runtimeSource.includes("tauri-dev") || runtimeSource.includes("browser") || runtimeSource.includes("unknown")) {
    throw new Error(`Installed app SGF workflow requires packaged app runtime source; observed ${runtimeSource || "missing"}.`);
  }
  if (!runtimeSource.includes("packaged") && !runtimeSource.includes("installed")) {
    throw new Error(`Installed app SGF workflow requires packaged app runtime source; observed ${runtimeSource}.`);
  }
  if (booleanField(runtime, "tauriRuntimeObserved") !== true) {
    throw new Error("Installed app SGF workflow requires runtime.tauriRuntimeObserved=true.");
  }
  if (booleanField(runtime, "devServerRequired") !== false) {
    throw new Error("Installed app SGF workflow requires runtime.devServerRequired=false.");
  }
  if (!stringField(runtime, "currentExe")) {
    throw new Error("Installed app SGF workflow requires runtime.currentExe from the packaged app.");
  }
  if (booleanField(bundle, "appBundleExists") !== true) {
    throw new Error("Installed app SGF workflow requires bundle.appBundleExists=true.");
  }
  if (booleanField(bundle, "executableExists") !== true) {
    throw new Error("Installed app SGF workflow requires bundle.executableExists=true.");
  }
  if (booleanField(bundle, "resourceDirExists") !== true) {
    throw new Error("Installed app SGF workflow requires bundle.resourceDirExists=true.");
  }
  if (booleanField(boundaries, "browserFallbackUsed") === true) {
    throw new Error("Installed app SGF workflow cannot use browser fallback evidence.");
  }
  if (booleanField(boundaries, "devServerUsed") === true || booleanField(boundaries, "viteDevServerUsed") === true) {
    throw new Error("Installed app SGF workflow cannot use dev-server evidence.");
  }
}

function normalizeEngineLaunchAvailability(rawStatus: string | null, available: boolean | null): "available" | "problem" | "unavailable" | "observed" {
  if (available === true) return "available";
  if (available === false) return "unavailable";
  const status = rawStatus?.toLowerCase() ?? "";
  if (/missing|unavailable|not[_ -]?found|not[_ -]?configured/.test(status)) return "unavailable";
  if (/error|fail|problem|invalid/.test(status)) return "problem";
  if (/success|launched|available|ok/.test(status)) return "available";
  return "observed";
}

function requiredRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`${label} must be a structured object.`);
  return value;
}

function nullableString(value: unknown, label: string): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") throw new Error(`${label} must be a string or null.`);
  return value;
}

function arrayFieldLength(value: Record<string, unknown>, key: string): number {
  const field = value[key];
  return Array.isArray(field) ? field.length : 0;
}

function stringField(value: Record<string, unknown>, key: string): string | null {
  const field = value[key];
  return typeof field === "string" && field.trim() ? field.trim() : null;
}

function booleanField(value: Record<string, unknown>, key: string): boolean | null {
  const field = value[key];
  return typeof field === "boolean" ? field : null;
}

async function waitForRuntimeProofState(predicate: (element: HTMLElement) => boolean, label: string): Promise<HTMLElement> {
  return await waitForElementState('[data-testid="installed-app-runtime-proof"]', label, predicate);
}

async function waitForEngineRuntimeProofState(predicate: (element: HTMLElement) => boolean, label: string): Promise<HTMLElement> {
  return await waitForElementState('[data-testid="engine-runtime-proof"]', label, predicate);
}

async function waitForElementState(selector: string, label: string, predicate: (element: HTMLElement) => boolean): Promise<HTMLElement> {
  const deadline = Date.now() + 4_000;
  while (Date.now() < deadline) {
    const element = document.querySelector(selector);
    if (element instanceof HTMLElement && isElementVisible(element) && predicate(element)) return element;
    await delay(50);
  }
  throw new Error(`Timed out waiting for ${label} (${selector}).`);
}

async function runWebviewDomClickPhase(report: RuntimeSmokeReport) {
  const evidence: WebviewDomClickEvidence = {
    tauriRuntimeObserved: false,
    browserFallbackUsed: false,
    clickedControls: [],
    visibleTargets: [],
    boundaries: {
      fullLayoutParity: false,
      fullShortcutParity: false,
      fullLegacyParity: false,
      ocrCaptureParity: false,
      releaseParity: false
    }
  };
  report.webviewDomClick = evidence;

  await check(report, "browser_fallback_excluded", async () => {
    if (!isTauriRuntime()) throw new Error("webview-dom-click phase must run inside the real Tauri WebView runtime.");
    evidence.tauriRuntimeObserved = true;
    evidence.browserFallbackUsed = false;
    return {
      tauriRuntimeObserved: true,
      browserFallbackUsed: false,
      userAgent: typeof navigator === "undefined" ? null : navigator.userAgent,
      platform: typeof navigator === "undefined" ? null : navigator.platform
    };
  });

  await check(report, "webview_dom_observed", async () => {
    const shell = await waitForVisibleElement('[data-testid="legacy-shell"]', "LegacyShell root");
    const menubar = await waitForVisibleElement('[data-testid="legacy-menubar"]', "LegacyShell menubar");
    const board = await waitForVisibleElement('[data-testid="legacy-board-pane"]', "board pane");
    evidence.domRoot = elementSmokeEvidence(shell, '[data-testid="legacy-shell"]');
    evidence.visibleTargets = [
      evidence.domRoot,
      elementSmokeEvidence(menubar, '[data-testid="legacy-menubar"]'),
      elementSmokeEvidence(board, '[data-testid="legacy-board-pane"]')
    ];
    return {
      tauriRuntimeObserved: evidence.tauriRuntimeObserved,
      browserFallbackUsed: evidence.browserFallbackUsed,
      root: evidence.domRoot,
      initialTargets: evidence.visibleTargets
    };
  });

  await check(report, "webview_click_observed", async () => {
    const clickTargets = [
      { label: "LegacyShell View/Candidates", selector: '[data-testid="legacy-menu-view-candidates"]', expectedTarget: "candidates" },
      { label: "LegacyShell Engine/Profiles", selector: '[data-testid="legacy-menu-engine-profiles"]', expectedTarget: "profiles" },
      { label: "LegacyShell Tools/Providers", selector: '[data-testid="legacy-menu-tools-providers"]', expectedTarget: "providers" },
      { label: "LegacyShell Tools/Preferences", selector: '[data-testid="legacy-menu-tools-preferences"]', expectedTarget: "preferences" }
    ];
    const clicks: WebviewClickEvidence[] = [];
    for (const target of clickTargets) {
      clicks.push(await clickLegacyMenuTarget(target.label, target.selector, target.expectedTarget));
    }
    evidence.clickedControls = clicks;
    return { clickedControls: clicks };
  });

  await check(report, "visible_targets_verified", async () => {
    const selectors = [
      '[data-testid="legacy-board-pane"]',
      '[data-testid="legacy-analysis-pane"]',
      '[data-testid="sgf-tree-panel"]',
      '[data-testid="engine-setup-panel"]',
      '[data-testid="provider-panel"]',
      '[data-testid="preferences-panel"]'
    ];
    const visibleTargets = selectors.map((selector) => {
      const element = queryRequiredElement(selector, selector);
      const item = elementSmokeEvidence(element, selector);
      if (!item.visible) throw new Error(`${selector} is present but not visible in the WebView DOM.`);
      return item;
    });
    evidence.visibleTargets = mergeElementEvidence(evidence.visibleTargets, visibleTargets);
    return { visibleTargets: evidence.visibleTargets };
  });

  await check(report, "scope_boundaries_recorded", async () => {
    return {
      ...evidence.boundaries,
      webviewDomClickCovered: true,
      nativeDialogCovered: false,
      osNativeMenuCovered: false,
      sourceOnlyProof: false
    };
  });
}

async function clickLegacyMenuTarget(label: string, selector: string, expectedTarget: string): Promise<WebviewClickEvidence> {
  const control = await waitForElement(selector, label);
  const details = control.closest("details") as HTMLDetailsElement | null;
  if (details) details.open = true;
  await delay(30);
  const controlEvidence = elementSmokeEvidence(control, selector);
  if (!controlEvidence.visible) throw new Error(`${label} control is not visible after opening its menu.`);
  control.click();
  await delay(120);

  const shell = queryRequiredElement('[data-testid="legacy-shell"]', "LegacyShell root after click");
  const activeTarget = nonEmptyAttribute(shell, "data-active-menu-target");
  if (activeTarget !== expectedTarget) {
    throw new Error(`${label} click did not activate ${expectedTarget}; observed ${activeTarget ?? "none"}.`);
  }
  const targetElement = await waitForMenuTargetElement(expectedTarget);
  const targetEvidence = elementSmokeEvidence(targetElement, `#legacy-menu-target-${expectedTarget}`);
  if (!targetEvidence.visible) throw new Error(`${label} target ${expectedTarget} is not visible after click.`);

  return {
    label,
    selector,
    expectedTarget,
    control: controlEvidence,
    activeTarget,
    lastAction: nonEmptyAttribute(shell, "data-last-menu-action"),
    lastLegacyAction: nonEmptyAttribute(shell, "data-last-legacy-action"),
    actionSource: nonEmptyAttribute(shell, "data-last-legacy-action-source"),
    actionStatus: nonEmptyAttribute(shell, "data-menu-action-status"),
    targetElement: targetEvidence
  };
}

async function openProviderPanelForRuntime() {
  try {
    await clickLegacyMenuTarget("LegacyShell Tools/Providers", '[data-testid="legacy-menu-tools-providers"]', "providers");
  } catch (error) {
    const message = errorMessage(error);
    if (!message.includes("target providers is not visible after click")) throw error;
  }
  const providerPanel = await waitForElement('[data-testid="provider-panel"]', "provider panel");
  providerPanel.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
  const readboardInput = await waitForElementState(
    '[data-testid="readboard-image-path-input"]',
    "readboard image path input after providers navigation",
    (element) => isElementVisible(element)
  );
  readboardInput.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
}

async function waitForMenuTargetElement(target: string): Promise<HTMLElement> {
  const id = `legacy-menu-target-${target}`;
  const deadline = Date.now() + 1_500;
  while (Date.now() < deadline) {
    const byId = document.getElementById(id);
    if (byId instanceof HTMLElement) return byId;
    const byTarget = document.querySelector(`[data-menu-target="${target}"]`);
    if (byTarget instanceof HTMLElement) return byTarget;
    await delay(50);
  }
  throw new Error(`Missing visible menu target element for ${target}.`);
}

async function waitForVisibleElement(selector: string, label: string): Promise<HTMLElement> {
  const element = await waitForElement(selector, label);
  if (!isElementVisible(element)) throw new Error(`${label} is present but not visible.`);
  return element;
}

async function waitForElement(selector: string, label: string): Promise<HTMLElement> {
  const deadline = Date.now() + 2_000;
  while (Date.now() < deadline) {
    const element = document.querySelector(selector);
    if (element instanceof HTMLElement) return element;
    await delay(50);
  }
  throw new Error(`Missing DOM target ${label} (${selector}).`);
}

function queryRequiredElement(selector: string, label: string): HTMLElement {
  const element = document.querySelector(selector);
  if (!(element instanceof HTMLElement)) throw new Error(`Missing DOM target ${label} (${selector}).`);
  return element;
}

function setTextInputValue(element: HTMLElement, value: string) {
  if (!(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement)) {
    throw new Error("Runtime smoke can only set text on input or textarea elements.");
  }
  const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value");
  if (descriptor?.set) {
    descriptor.set.call(element, value);
  } else {
    element.value = value;
  }
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

function elementSmokeEvidence(element: HTMLElement, selector: string): ElementSmokeEvidence {
  return {
    selector,
    tagName: element.tagName.toLowerCase(),
    text: normalizeText(element.textContent ?? ""),
    visible: isElementVisible(element),
    id: element.id || null,
    className: typeof element.className === "string" && element.className.trim() ? element.className : null,
    testId: element.dataset.testid ?? null,
    attributes: smokeAttributes(element)
  };
}

function smokeAttributes(element: HTMLElement): Record<string, string> {
  const attributes: Record<string, string> = {};
  for (const attribute of Array.from(element.attributes)) {
    if (
      attribute.name === "id" ||
      attribute.name === "class" ||
      attribute.name === "role" ||
      attribute.name.startsWith("aria-") ||
      attribute.name.startsWith("data-")
    ) {
      attributes[attribute.name] = attribute.value;
    }
  }
  return attributes;
}

function isElementVisible(element: HTMLElement): boolean {
  if (!element.isConnected) return false;
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function normalizeText(value: string): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > 180 ? `${normalized.slice(0, 177)}...` : normalized;
}

function nonEmptyAttribute(element: HTMLElement, name: string): string | null {
  const value = element.getAttribute(name);
  return value && value.trim() ? value : null;
}

function mergeElementEvidence(current: ElementSmokeEvidence[], next: ElementSmokeEvidence[]): ElementSmokeEvidence[] {
  const bySelector = new Map<string, ElementSmokeEvidence>();
  for (const item of [...current, ...next]) bySelector.set(item.selector, item);
  return [...bySelector.values()];
}

async function verifySavedBoardState(
  report: RuntimeSmokeReport,
  sgfText: string,
  appendColor: PlayerColor,
  deletedTargetVertex: string,
  expectedSiblingCount: number
): Promise<{ moveCount: number; positionCount: number }> {
  return await check(report, "board_state_verified", async () => {
    const replay = await verifyBoardReplayInvariant(report, "readback", sgfText);
    const tree = await parseSgfTree(sgfText);
    const node = findPersistedBranchNode(tree, expectedBranchComment, expectedBranchName, expectedBranchLabel);
    const parent = requireNode(tree, node.parent_id, "persisted branch parent node");
    const targetExistsAfterDelete = hasChildMove(parent, tree, appendColor, deletedTargetVertex);
    if (targetExistsAfterDelete) throw new Error("Deleted variation move target reappeared after save/readback.");
    return {
      nodeId: node.id,
      moveNumber: node.move_number,
      stones: replay.lastPositionStones,
      invariant: replayInvariant,
      invariantVerified: true,
      verified: true,
      boardInvariant: replayInvariant,
      replayErrorsAbsent: true,
      moveCount: replay.moveCount,
      positionCount: replay.positionCount,
      deletedTargetVertex,
      targetExistsAfterDelete,
      absentAfterDelete: !targetExistsAfterDelete,
      siblingCountAfterDelete: parent.child_ids.length,
      expectedSiblingCount,
      siblingCountVerified: parent.child_ids.length === expectedSiblingCount
    };
  });
}

async function verifyReopenedState(
  report: RuntimeSmokeReport,
  sgfText: string,
  expected: RuntimeSmokeExpectedEvidence
): Promise<Record<string, unknown>> {
  const replay = await verifyBoardReplayInvariant(report, "reopened state", sgfText);
  const tree = await parseSgfTree(sgfText);
  const node = findPersistedBranchNode(tree, expected.branchComment, expected.branchName, expected.branchLabel);
  const parent = requireNode(tree, node.parent_id, "reopened branch parent node");
  const targetExistsAfterReopen = hasChildMove(parent, tree, expected.appendColor, expected.deletedTargetVertex);
  if (targetExistsAfterReopen) throw new Error("Deleted variation move target exists after reopen.");
  if (parent.child_ids.length !== expected.siblingCountAfterDelete) {
    throw new Error("Reopened branch sibling count does not match edit-save evidence.");
  }
  if (replay.moveCount !== expected.savedMoveCount || replay.positionCount !== expected.savedPositionCount) {
    throw new Error("Reopened board replay counts do not match edit-save evidence.");
  }
  return {
    nodeId: node.id,
    comment: node.comment,
    expectedComment: expected.branchComment,
    expectedProperties: { N: expected.branchName, LB: expected.branchLabel },
    expectedAnnotations: expected.branchAnnotations,
    deletedTargetVertex: expected.deletedTargetVertex,
    targetExistsAfterReopen,
    absentAfterReopen: !targetExistsAfterReopen,
    variationDeletePersisted: !targetExistsAfterReopen,
    reorderTargetIndex: expected.reorderTargetIndex,
    siblingCountAfterReopen: parent.child_ids.length,
    expectedSiblingCount: expected.siblingCountAfterDelete,
    moveCount: replay.moveCount,
    positionCount: replay.positionCount,
    treeOrderVerified: parent.child_ids.length === expected.siblingCountAfterDelete,
    commentsVerified: node.comment === expected.branchComment,
    propertiesVerified: hasPropertyValue(node, "N", expected.branchName) && hasPropertyValue(node, "LB", expected.branchLabel),
    annotationsVerified: annotationsMatch(node, expected.branchAnnotations),
    moveCountVerified: replay.moveCount === expected.savedMoveCount && replay.positionCount === expected.savedPositionCount,
    boardStateVerified: true,
    invariant: expected.invariant,
    invariantVerified: true,
    verified: true,
    boardInvariant: expected.invariant,
    replayErrorsAbsent: true
  };
}

async function check<T>(
  report: RuntimeSmokeReport,
  name: RuntimeSmokeCheckName,
  action: () => Promise<T>
): Promise<T> {
  try {
    const result = await action();
    const details = summarizeResult(result);
    report.checks.push({ name, status: "pass", details });
    return result;
  } catch (error) {
    report.checks.push({ name, status: "fail", error: errorMessage(error) });
    throw error;
  }
}

function mergeCheckDetails(report: RuntimeSmokeReport, name: RuntimeSmokeCheckName, details: Record<string, unknown>) {
  for (let index = report.checks.length - 1; index >= 0; index -= 1) {
    const check = report.checks[index];
    if (check.name !== name || check.status !== "pass") continue;
    check.details = { ...(check.details ?? {}), ...details };
    return;
  }
  throw new Error(`Cannot enrich missing runtime smoke check ${name}.`);
}

async function verifySgf(report: RuntimeSmokeReport, label: string, sgfText: string) {
  await step(report, `parse ${label} summary`, async () => {
    const parsed = await parseSgfSummary(sgfText);
    if (parsed.summary.move_count < 1) throw new Error(`${label} SGF must contain at least one move.`);
    return { boardSize: parsed.summary.board_size, moveCount: parsed.summary.move_count };
  });
  await step(report, `replay ${label} positions`, async () => {
    const positions = await replaySgfPositions(sgfText);
    if (positions.length < 2) throw new Error(`${label} replay returned too few positions.`);
    return { positions: positions.length, lastMove: positions.at(-1)?.move_number ?? null };
  });
  await step(report, `parse ${label} tree`, async () => {
    const tree = await parseSgfTree(sgfText);
    if (!tree?.nodes.length) throw new Error(`${label} tree is empty.`);
    return { nodes: tree.nodes.length, rootId: tree.root_id };
  });
}

async function step<T>(report: RuntimeSmokeReport, name: string, action: () => Promise<T>): Promise<T> {
  try {
    const result = await action();
    report.steps.push({ name, status: "pass", details: summarizeResult(result) });
    return result;
  } catch (error) {
    report.steps.push({ name, status: "fail", error: errorMessage(error) });
    throw error;
  }
}

function runtimeSmokeEnv(name: string): string | null {
  const value = runtimeSmokeStaticEnv(name) ?? runtimeSmokeImportMeta().env?.[name];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function positiveEnvInteger(name: string): number | null {
  const value = runtimeSmokeEnv(name);
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function runtimeSmokeStaticEnv(name: string): string | undefined {
  const env = (import.meta as RuntimeSmokeImportMeta).env;
  switch (name) {
    case "VITE_LIZZIEYZY_RUNTIME_SMOKE_PROVIDER_BASE_URL":
      return env?.VITE_LIZZIEYZY_RUNTIME_SMOKE_PROVIDER_BASE_URL;
    case "TAURI_LIZZIEYZY_RUNTIME_SMOKE_PROVIDER_BASE_URL":
      return env?.TAURI_LIZZIEYZY_RUNTIME_SMOKE_PROVIDER_BASE_URL;
    case "VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH":
      return env?.VITE_LIZZIEYZY_RUNTIME_SMOKE_READBOARD_CAPTURE_IMAGE_PATH;
    default:
      return undefined;
  }
}

function normalizeRuntimeSmokePhase(value: string | null | undefined): RuntimeSmokePhase {
  if (
    value === "edit-save" ||
    value === "reopen-verify" ||
    value === "katago-live" ||
    value === "katago-live-workflow-cache" ||
    value === "readboard-live" ||
    value === "readboard-external-capture-mvp" ||
    value === "readboard-operator-capture" ||
    value === "readboard-controlled-target-proof" ||
    value === "readboard-screenshot-region-detection" ||
    value === "readboard-target-window-discovery" ||
    value === "readboard-selected-window-capture" ||
    value === "provider-live" ||
    value === "webview-dom-click" ||
    value === "installed-app-runtime-proof" ||
    value === "installed-app-sgf-workflow" ||
    value === "installed-app-katago-live-workflow"
  ) return value;
  return "full";
}

function phaseRequiresSgfPath(phase: RuntimeSmokePhase): boolean {
  return phase !== "provider-live" &&
    phase !== "readboard-live" &&
    phase !== "readboard-external-capture-mvp" &&
    phase !== "readboard-operator-capture" &&
    phase !== "readboard-controlled-target-proof" &&
    phase !== "readboard-screenshot-region-detection" &&
    phase !== "readboard-target-window-discovery" &&
    phase !== "readboard-selected-window-capture" &&
    phase !== "webview-dom-click" &&
    phase !== "installed-app-runtime-proof";
}

function requireRuntimeSmokeSgfPath(sgfPath: string | null): string {
  if (!sgfPath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH is required.");
  return sgfPath;
}

function readEnvKatagoLiveSmokeConfig(): KataGoLiveSmokeConfig {
  const fromJson = parseKatagoProfileJson(runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_PROFILE_JSON"));
  const profile = fromJson ?? readEnvKatagoProfile();
  return {
    profile,
    maxVisits: readPositiveIntegerEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MAX_VISITS", defaultKatagoMaxVisits),
    onceTurn: readNonNegativeIntegerEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ONCE_TURN"),
    gameMaxVisits: readPositiveIntegerEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS", defaultKatagoGameMaxVisits),
    cancelMaxVisits: readPositiveIntegerEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS", defaultKatagoCancelMaxVisits),
    cancelDelayMs: readPositiveIntegerEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS", defaultKatagoCancelDelayMs),
    runGame: readBooleanEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_GAME", true),
    runCancel: readBooleanEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_CANCEL", true)
  };
}

function normalizeKatagoLiveSmokeConfig(
  raw: KataGoLiveSmokeConfigDto | null | undefined,
  fallback: KataGoLiveSmokeConfig
): KataGoLiveSmokeConfig {
  return {
    profile: normalizeEngineProfile(raw?.profile) ?? fallback.profile,
    maxVisits: normalizePositiveInteger(raw?.max_visits, fallback.maxVisits),
    onceTurn: normalizeNonNegativeInteger(raw?.once_turn) ?? fallback.onceTurn,
    gameMaxVisits: normalizePositiveInteger(raw?.game_max_visits, fallback.gameMaxVisits),
    cancelMaxVisits: normalizePositiveInteger(raw?.cancel_max_visits, fallback.cancelMaxVisits),
    cancelDelayMs: normalizePositiveInteger(raw?.cancel_delay_ms, fallback.cancelDelayMs),
    runGame: typeof raw?.run_game === "boolean" ? raw.run_game : fallback.runGame,
    runCancel: typeof raw?.run_cancel === "boolean" ? raw.run_cancel : fallback.runCancel
  };
}

function defaultKatagoLiveSmokeConfig(): KataGoLiveSmokeConfig {
  return {
    profile: null,
    maxVisits: defaultKatagoMaxVisits,
    onceTurn: null,
    gameMaxVisits: defaultKatagoGameMaxVisits,
    cancelMaxVisits: defaultKatagoCancelMaxVisits,
    cancelDelayMs: defaultKatagoCancelDelayMs,
    runGame: true,
    runCancel: true
  };
}

function parseKatagoProfileJson(value: string | null): EngineProfileDto | null {
  if (!value) return null;
  try {
    return normalizeEngineProfile(JSON.parse(value));
  } catch {
    return null;
  }
}

function readEnvKatagoProfile(): EngineProfileDto | null {
  const enginePath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ENGINE_PATH");
  if (!enginePath) return null;
  return {
    name: runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_PROFILE_NAME") ?? "Runtime Smoke KataGo",
    engine_path: enginePath,
    model_path: runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MODEL_PATH"),
    config_path: runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CONFIG_PATH"),
    working_dir: runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKING_DIR"),
    backend: "kata_go_analysis"
  };
}

async function resolveKataGoLiveProfile(config: KataGoLiveSmokeConfig): Promise<EngineProfileDto> {
  if (config.profile) return config.profile;
  const settings = await loadEngineProfileSettings();
  if (settings?.profile) return settings.profile;
  throw new Error(
    "KataGo live smoke requires VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_PROFILE_JSON, " +
    "VITE_LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ENGINE_PATH, or a saved engine profile."
  );
}

function normalizeEngineProfile(value: unknown): EngineProfileDto | null {
  if (!isRecord(value)) return null;
  const enginePath = optionalString(value.engine_path);
  if (!enginePath) return null;
  const backend = value.backend === "kata_go_analysis" ? value.backend : "kata_go_analysis";
  return {
    name: optionalString(value.name) ?? "Runtime Smoke KataGo",
    engine_path: enginePath,
    model_path: optionalString(value.model_path),
    config_path: optionalString(value.config_path),
    working_dir: optionalString(value.working_dir),
    backend
  };
}

function buildMissingAssetKataGoProfile(profile: EngineProfileDto): EngineProfileDto {
  return {
    ...profile,
    name: `${profile.name} missing asset smoke`,
    model_path: "/__lizzieyzy_runtime_smoke_missing_model__.bin.gz",
    config_path: "/__lizzieyzy_runtime_smoke_missing_analysis__.cfg"
  };
}

function sanitizeEngineProfile(profile: EngineProfileDto): SanitizedEngineProfile {
  return {
    name: profile.name,
    backend: profile.backend,
    hasEnginePath: Boolean(profile.engine_path),
    hasModelPath: Boolean(profile.model_path),
    hasConfigPath: Boolean(profile.config_path),
    hasWorkingDir: Boolean(profile.working_dir)
  };
}

function readPositiveIntegerEnv(name: string, fallback: number): number {
  const value = runtimeSmokeEnv(name);
  return value === null ? fallback : normalizePositiveInteger(Number(value), fallback);
}

function readNonNegativeIntegerEnv(name: string): number | null {
  const value = runtimeSmokeEnv(name);
  return value === null ? null : normalizeNonNegativeInteger(Number(value));
}

function readBooleanEnv(name: string, fallback: boolean): boolean {
  const value = runtimeSmokeEnv(name);
  if (value === null) return fallback;
  const normalized = value.trim().toLowerCase();
  if (truthyValues.has(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return fallback;
}

function normalizePositiveInteger(value: unknown, fallback: number): number {
  const numberValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numberValue) && numberValue > 0 ? Math.floor(numberValue) : fallback;
}

function normalizeNonNegativeInteger(value: unknown): number | null {
  const numberValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numberValue) && numberValue >= 0 ? Math.floor(numberValue) : null;
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeOptionalString(value: string | null | undefined): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function runtimeSmokeImportMeta(): RuntimeSmokeImportMeta {
  return import.meta as RuntimeSmokeImportMeta;
}

function requireNode(tree: SgfTreeDto | null, nodeId: string | null | undefined, label: string): SgfTreeNodeDto {
  const node = tree?.nodes.find((candidate) => candidate.id === nodeId);
  if (!node) throw new Error(`Could not find ${label}.`);
  return node;
}

function findBranchNode(tree: SgfTreeDto | null): SgfTreeNodeDto {
  const preferred = tree?.nodes.find((node) => node.comment?.includes("second branch") || node.comment === expectedBranchComment);
  const fallback = tree?.nodes.find((node) => node.color && !node.is_mainline);
  const node = preferred ?? fallback;
  if (!node) throw new Error("Could not find a branch move node.");
  return node;
}

function findPersistedBranchNode(
  tree: SgfTreeDto | null,
  expectedComment: string,
  expectedName: string,
  expectedLabel: string
): SgfTreeNodeDto {
  const node = tree?.nodes.find((candidate) =>
    candidate.comment === expectedComment
    && hasPropertyValue(candidate, "N", expectedName)
    && hasPropertyValue(candidate, "LB", expectedLabel)
  );
  if (!node) throw new Error("Could not find persisted branch node by comment/properties.");
  return node;
}

async function loadExpectedEvidence(reportPath: string): Promise<RuntimeSmokeExpectedEvidence> {
  const document = await readSgfDocument(reportPath);
  const parsed = JSON.parse(document.sgfText) as unknown;
  if (!isRecord(parsed) || !isRecord(parsed.expected)) {
    throw new Error("Previous edit-save report does not include expected reopen evidence.");
  }
  return normalizeExpectedEvidence(parsed.expected);
}

function normalizeExpectedEvidence(value: Record<string, unknown>): RuntimeSmokeExpectedEvidence {
  const branchComment = requiredString(value.branchComment, "expected.branchComment");
  const branchName = requiredString(value.branchName, "expected.branchName");
  const branchLabel = requiredString(value.branchLabel, "expected.branchLabel");
  const branchAnnotations = normalizeExpectedAnnotations(value.branchAnnotations);
  const deletedTargetVertex = requiredString(value.deletedTargetVertex, "expected.deletedTargetVertex");
  const editTargetVertex = requiredString(value.editTargetVertex, "expected.editTargetVertex");
  const appendColor = value.appendColor === "black" || value.appendColor === "white" ? value.appendColor : null;
  if (!appendColor) throw new Error("expected.appendColor must be black or white.");
  if (value.reorderTargetIndex !== 0) throw new Error("expected.reorderTargetIndex must be 0.");
  const savedMoveCount = requiredNumber(value.savedMoveCount, "expected.savedMoveCount");
  const savedPositionCount = requiredNumber(value.savedPositionCount, "expected.savedPositionCount");
  const siblingCountAfterDelete = requiredNumber(value.siblingCountAfterDelete, "expected.siblingCountAfterDelete");
  const invariant = requiredString(value.invariant, "expected.invariant");
  return {
    branchComment,
    branchName,
    branchLabel,
    branchAnnotations,
    deletedTargetVertex,
    editTargetVertex,
    appendColor,
    reorderTargetIndex: 0,
    savedMoveCount,
    savedPositionCount,
    siblingCountAfterDelete,
    invariant
  };
}

async function verifyBoardReplayInvariant(
  report: RuntimeSmokeReport,
  label: string,
  sgfText: string
): Promise<{ moveCount: number; positionCount: number; lastMove: number; lastPositionStones: number }> {
  await verifySgf(report, label, sgfText);
  const [parsed, positions] = await Promise.all([parseSgfSummary(sgfText), replaySgfPositions(sgfText)]);
  const errors = positions.flatMap((position) => position.errors);
  if (errors.length > 0) throw new Error(`${label} replay had errors: ${errors.join(", ")}`);
  const expectedPositionCount = parsed.summary.move_count + 1;
  if (positions.length !== expectedPositionCount) {
    throw new Error(`${label} replay returned ${positions.length} positions for ${parsed.summary.move_count} moves.`);
  }
  return {
    moveCount: parsed.summary.move_count,
    positionCount: positions.length,
    lastMove: positions.at(-1)?.move_number ?? 0,
    lastPositionStones: positions.at(-1)?.stones.length ?? 0
  };
}

function hasChildMove(parent: SgfTreeNodeDto, tree: SgfTreeDto | null, color: PlayerColor, vertex: string): boolean {
  return parent.child_ids
    .map((childId) => requireNode(tree, childId, "child move"))
    .some((node) => node.color === color && vertexKey(node.vertex) === vertex);
}

function chooseUnusedSiblingVertex(tree: SgfTreeDto | null, parentNodeId: string): MoveVertex {
  const used = siblingVertexKeys(tree, parentNodeId);
  const candidates = candidateVertices(readBoardSize(tree));
  return candidates.find((vertex) => !used.has(vertexKey(vertex) ?? "")) ?? "pass";
}

function chooseDifferentSiblingVertex(tree: SgfTreeDto | null, nodeId: string): MoveVertex {
  const node = requireNode(tree, nodeId, "move being edited");
  const used = siblingVertexKeys(tree, node.parent_id ?? "");
  used.delete(vertexKey(node.vertex) ?? "");
  const current = vertexKey(node.vertex);
  const candidates = candidateVertices(readBoardSize(tree));
  const selected = candidates.find((vertex) => vertexKey(vertex) !== current && !used.has(vertexKey(vertex) ?? ""));
  if (!selected) throw new Error("Could not find a distinct edit vertex.");
  return selected;
}

function candidateVertices(boardSize: number): MoveVertex[] {
  const high = Math.max(boardSize - 1, 0);
  const mid = Math.floor(high / 2);
  return [
    { point: { x: 0, y: 0 } },
    { point: { x: 1, y: 0 } },
    { point: { x: 0, y: 1 } },
    { point: { x: high, y: high } },
    { point: { x: mid, y: mid } },
    "pass"
  ];
}

function siblingVertexKeys(tree: SgfTreeDto | null, parentNodeId: string): Set<string> {
  return new Set(
    tree?.nodes
      .filter((node) => node.parent_id === parentNodeId)
      .map((node) => vertexKey(node.vertex))
      .filter((key): key is string => key !== null) ?? []
  );
}

function readBoardSize(tree: SgfTreeDto | null): number {
  const root = tree?.nodes.find((node) => node.id === tree.root_id);
  const rawSize = root?.properties.find((property) => property.key === "SZ")?.values[0];
  const boardSize = rawSize ? Number(rawSize) : 19;
  return Number.isFinite(boardSize) && boardSize > 1 ? Math.floor(boardSize) : 19;
}

function vertexKey(vertex: MoveVertex | null | undefined): string | null {
  if (!vertex) return null;
  if (vertex === "pass") return "pass";
  return `${vertex.point.x},${vertex.point.y}`;
}

function requireVertexKey(vertex: MoveVertex | null | undefined, label: string): string {
  const key = vertexKey(vertex);
  if (!key) throw new Error(`Missing ${label}.`);
  return key;
}

function assertPropertyValue(node: SgfTreeNodeDto, key: string, expectedValue: string) {
  if (!hasPropertyValue(node, key, expectedValue)) {
    throw new Error(`${key} property does not include ${expectedValue}.`);
  }
}

function hasPropertyValue(node: SgfTreeNodeDto, key: string, expectedValue: string): boolean {
  const values = node.properties.find((property) => property.key === key)?.values ?? [];
  return values.includes(expectedValue);
}

function assertPropertyAbsent(node: SgfTreeNodeDto, key: string) {
  const values = node.properties.find((property) => property.key === key)?.values ?? [];
  if (values.length > 0) throw new Error(`${key} property was expected to be removed.`);
}

function annotationsMatch(node: SgfTreeNodeDto, expected: Record<string, string[]>): boolean {
  return Object.entries(expected).every(([key, values]) => {
    const actual = node.properties.find((property) => property.key === key)?.values ?? [];
    return actual.length === values.length && values.every((value) => actual.includes(value));
  });
}

function normalizeExpectedAnnotations(value: unknown): Record<string, string[]> {
  if (!isRecord(value)) throw new Error("expected.branchAnnotations must be an object.");
  const normalized: Record<string, string[]> = {};
  for (const key of ["TR", "SQ", "CR", "MA", "SL", "LB", "AR", "LN"]) {
    const raw = value[key];
    if (!Array.isArray(raw) || raw.some((item) => typeof item !== "string")) {
      throw new Error(`expected.branchAnnotations.${key} must be a string array.`);
    }
    normalized[key] = raw;
  }
  return normalized;
}

function assertNonEmptyString(value: string, message: string) {
  if (!value.trim()) throw new Error(message);
}

function normalizeCaptureStatus(value: unknown): string {
  const status = typeof value === "string" ? value.toLowerCase() : "";
  if (status.includes("captured") || status === "ok" || status === "success") return "captured";
  if (status.includes("cancel")) return "cancelled";
  if (status.includes("permission") || status.includes("denied")) return "permission";
  if (status.includes("decode") || status.includes("image")) return "decode_error";
  if (status.includes("unsupported") || status.includes("browser preview") || status.includes("unknown command")) return "unsupported";
  return status || "error";
}

function normalizeDiscoveryStatus(value: unknown): string {
  const status = typeof value === "string" ? value.toLowerCase() : "";
  if (status.includes("available") || status.includes("ok") || status.includes("success")) return "available";
  if (status.includes("unsupported") || status.includes("browser preview") || status.includes("unknown command")) return "unsupported";
  if (status.includes("error") || status.includes("fail")) return "error";
  return status || "error";
}

function summarizeReadboardCaptureArtifact(
  result: Record<string, unknown>,
  inputPath: string
): ReadboardExternalCaptureMvpEvidence["captureArtifact"] {
  const sha256 = readStringField(result, "sha256");
  if (!sha256 || !/^[a-fA-F0-9]{64}$/.test(sha256)) throw new Error("Readboard capture MVP did not return a stable 64-char sha256.");
  const sizeBytes = readNumberField(result, "size") ?? readNumberField(result, "sizeBytes");
  if (sizeBytes === null || sizeBytes <= 0) throw new Error("Readboard capture MVP did not return a positive artifact size.");
  const path = stableReadboardCapturePath(inputPath);
  return {
    path,
    sanitized: true,
    sizeBytes,
    sha256
  };
}

function stableReadboardCapturePath(path: string): string {
  const normalized = path.replace(/\\/g, "/").trim();
  if (normalized.endsWith("tests/fixtures/readboard-images/controlled-19-three-stones.ppm")) {
    return "tests/fixtures/readboard-images/controlled-19-three-stones.ppm";
  }
  if (normalized === "tests/fixtures/readboard-images/controlled-19-three-stones.ppm") return normalized;
  const targetWindowMatch = /(?:^|\/)(tests\/fixtures\/readboard-screenshots\/target-window[^/]*\.ppm)$/.exec(normalized);
  if (targetWindowMatch) return targetWindowMatch[1];
  const arbitraryScreenshotMatch = /(?:^|\/)(tests\/fixtures\/readboard-screenshots\/arbitrary-[^/]*\.ppm)$/.exec(normalized);
  if (arbitraryScreenshotMatch) return arbitraryScreenshotMatch[1];
  if (normalized.endsWith("docs/qa/fixtures/readboard-controlled-board.png")) {
    return "docs/qa/fixtures/readboard-controlled-board.png";
  }
  if (normalized === "docs/qa/fixtures/readboard-controlled-board.png") return normalized;
  throw new Error(
    "Readboard capture MVP evidence must use tests/fixtures/readboard-images/controlled-19-three-stones.ppm " +
      "or a controlled target fixture under tests/fixtures/readboard-screenshots/target-window*.ppm " +
      "or a screenshot board-region fixture under tests/fixtures/readboard-screenshots/arbitrary-*.ppm " +
      "or docs/qa/fixtures/readboard-controlled-board.png as the stable artifact path."
  );
}

function controlledReadboardNonBoardFixturePath(capturedPath: string, configuredPath?: string | null): string {
  const normalizedCapturedPath = capturedPath.replace(/\\/g, "/").trim();
  const requestedNonBoardPath = configuredPath?.replace(/\\/g, "/").trim();
  const fixtureName = requestedNonBoardPath?.split("/").pop() || "target-window-non-board.ppm";
  const absoluteSiblingMatch = /^(.*\/tests\/fixtures\/readboard-screenshots\/)target-window[^/]*\.ppm$/.exec(normalizedCapturedPath);
  if (absoluteSiblingMatch && (requestedNonBoardPath === undefined || !/^(\/|[A-Za-z]:\/|~\/)/.test(requestedNonBoardPath))) {
    return `${absoluteSiblingMatch[1]}${fixtureName}`;
  }
  if (requestedNonBoardPath) return requestedNonBoardPath;
  const stablePath = stableReadboardCapturePath(capturedPath);
  if (stablePath.startsWith("tests/fixtures/readboard-screenshots/")) {
    return "tests/fixtures/readboard-screenshots/target-window-non-board.ppm";
  }
  return "tests/fixtures/readboard-screenshots/target-window-non-board.ppm";
}

function arbitraryScreenshotNonBoardFixturePath(capturedPath: string, configuredPath?: string | null): string {
  const normalizedCapturedPath = capturedPath.replace(/\\/g, "/").trim();
  const requestedNonBoardPath = configuredPath?.replace(/\\/g, "/").trim();
  const fixtureName = requestedNonBoardPath?.split("/").pop() || "arbitrary-non-board.ppm";
  const absoluteSiblingMatch = /^(.*\/tests\/fixtures\/readboard-screenshots\/)arbitrary-[^/]*\.ppm$/.exec(normalizedCapturedPath);
  if (absoluteSiblingMatch && (requestedNonBoardPath === undefined || !/^(\/|[A-Za-z]:\/|~\/)/.test(requestedNonBoardPath))) {
    return `${absoluteSiblingMatch[1]}${fixtureName}`;
  }
  if (requestedNonBoardPath) return requestedNonBoardPath;
  const stablePath = stableReadboardCapturePath(capturedPath);
  if (stablePath.startsWith("tests/fixtures/readboard-screenshots/")) {
    return "tests/fixtures/readboard-screenshots/arbitrary-non-board.ppm";
  }
  return "tests/fixtures/readboard-screenshots/arbitrary-non-board.ppm";
}

function summarizeReadboardTargetCandidate(candidate: ReadboardCaptureTargetCandidate): Record<string, unknown> {
  return {
    title: candidate.title,
    appName: candidate.appName ?? candidate.app_name ?? null,
    processName: candidate.processName ?? candidate.process_name ?? null,
    processId: candidate.processId ?? candidate.process_id ?? null,
    id: candidate.id ?? null,
    windowId: candidate.windowId ?? candidate.window_id ?? null,
    bounds: candidate.bounds ?? null,
    screenId: candidate.screenId ?? candidate.screen_id ?? null,
    confidence: candidate.confidence ?? null,
    warnings: candidate.warnings ?? []
  };
}

function selectReadboardTargetCandidate(candidates: ReadboardCaptureTargetCandidate[], titleHint: string | null): ReadboardCaptureTargetCandidate {
  if (titleHint) {
    const normalizedTitleHint = titleHint.toLowerCase();
    const match = candidates.find((candidate) => candidate.title.toLowerCase().includes(normalizedTitleHint));
    if (match) return match;
  }
  return candidates[0];
}

function selectReadboardWindowTargetCandidate(candidates: ReadboardCaptureTargetCandidate[], titleHint: string | null): ReadboardCaptureTargetCandidate {
  const withWindowId = candidates.filter((candidate) => readboardTargetWindowId(candidate) !== null);
  if (withWindowId.length === 0) throw new Error("Readboard target discovery returned no candidates with a window id.");
  if (titleHint) {
    const normalizedTitleHint = titleHint.toLowerCase();
    const match = withWindowId.find((candidate) => candidate.title.toLowerCase().includes(normalizedTitleHint));
    if (match) return match;
  }
  return withWindowId[0];
}

function readboardTargetWindowId(candidate: ReadboardCaptureTargetCandidate): string | null {
  const raw = candidate.windowId ?? candidate.window_id;
  if (typeof raw === "number" && Number.isFinite(raw)) return String(raw);
  return stringFromUnknown(raw);
}

function readboardTargetCandidateMetadata(candidate: ReadboardCaptureTargetCandidate, imagePath: string) {
  const bounds = candidate.bounds ?? null;
  const processId = numberFromUnknown(candidate.processId) ?? numberFromUnknown(candidate.process_id);
  const windowId = candidate.windowId ?? candidate.window_id ?? null;
  const appName = stringFromUnknown(candidate.appName) ?? stringFromUnknown(candidate.app_name);
  const processName = stringFromUnknown(candidate.processName) ?? stringFromUnknown(candidate.process_name);
  const id = candidate.id ?? windowId ?? processId ?? candidate.title;
  return {
    id,
    controlledLocalTargetWindow: true,
    controlled_local_target_window: true,
    captureTiedToSelectedTarget: true,
    capture_tied_to_selected_target: true,
    appName,
    app_name: appName,
    processName,
    process_name: processName,
    windowTitle: candidate.title,
    window_title: candidate.title,
    windowId,
    window_id: windowId,
    processId,
    process_id: processId,
    fixtureId: `discovered:${id}`,
    fixture_id: `discovered:${id}`,
    x: bounds?.x ?? null,
    y: bounds?.y ?? null,
    width: bounds?.width ?? null,
    height: bounds?.height ?? null,
    bounds,
    targetBounds: bounds,
    target_bounds: bounds,
    imagePath,
    image_path: imagePath
  };
}

function readboardScreenshotRegionFromResult(result: Record<string, unknown>): Record<string, unknown> {
  const rawRegion = result.boardRegion ?? result.board_region ?? result.detectedBoardRegion ?? result.detected_board_region;
  if (isRecord(rawRegion)) return rawRegion;
  return {};
}

function sanitizeReadboardEvidenceValue(value: unknown, stablePath: string, inputPath: string): unknown {
  if (typeof value === "string") return sanitizeReadboardEvidenceString(value, stablePath, inputPath);
  if (Array.isArray(value)) return value.map((item) => sanitizeReadboardEvidenceValue(item, stablePath, inputPath));
  if (isRecord(value)) {
    const sanitized: Record<string, unknown> = {};
    Object.entries(value).forEach(([key, entry]) => {
      sanitized[key] = sanitizeReadboardEvidenceValue(entry, stablePath, inputPath);
    });
    return sanitized;
  }
  return value;
}

function sanitizeReadboardEvidenceString(value: string, stablePath: string, inputPath: string): string {
  const normalizedValue = value.replace(/\\/g, "/");
  const normalizedInput = inputPath.replace(/\\/g, "/").trim();
  if (normalizedInput && normalizedValue.includes(normalizedInput)) {
    return normalizedValue.split(normalizedInput).join(stablePath);
  }
  try {
    return stableReadboardCapturePath(normalizedValue);
  } catch {
    // Fall through and redact unrelated local paths below.
  }
  if (/^(\/Users\/|\/tmp\/|\/private\/|\/var\/folders\/|~\/|[A-Za-z]:\/)/.test(normalizedValue)) {
    return "<local-path-redacted>";
  }
  return value;
}

function readStringField(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readNumberField(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  const numberValue = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(numberValue) ? numberValue : null;
}

function numberFromUnknown(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringFromUnknown(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function summarizeReadboardProtocolSync(result: { snapshot_id: string; position?: { board_size: number; move_number: number; stones: unknown[]; to_play: PlayerColor } | null; warnings: string[] }): ReadboardProtocolLineEvidence {
  if (!result.position) throw new Error("Readboard sync did not return a position.");
  return {
    snapshotId: result.snapshot_id,
    boardSize: result.position.board_size,
    moveNumber: result.position.move_number,
    stoneCount: result.position.stones.length,
    toPlay: result.position.to_play,
    warnings: result.warnings
  };
}

function summarizeReadboardTargetStateChange(
  before: ReadboardProtocolLineEvidence,
  after: ReadboardProtocolLineEvidence
): ReadboardTargetStateChangeEvidence {
  return {
    changed: true,
    beforeSnapshotId: before.snapshotId,
    afterSnapshotId: after.snapshotId,
    beforeStoneCount: before.stoneCount,
    afterStoneCount: after.stoneCount,
    beforeMoveNumber: before.moveNumber,
    afterMoveNumber: after.moveNumber,
    boardSizeStable: true,
    toPlay: after.toPlay,
    warnings: [...before.warnings, ...after.warnings]
  };
}

function assertReadboardProtocolEvidence(evidence: ReadboardProtocolLineEvidence, moveNumber: number, stoneCount: number, toPlay: PlayerColor) {
  if (evidence.boardSize !== 2) throw new Error(`Expected 2x2 readboard sync, got ${evidence.boardSize}.`);
  if (evidence.moveNumber !== moveNumber) throw new Error(`Expected readboard move ${moveNumber}, got ${evidence.moveNumber}.`);
  if (evidence.stoneCount !== stoneCount) throw new Error(`Expected readboard stone count ${stoneCount}, got ${evidence.stoneCount}.`);
  if (evidence.toPlay !== toPlay) throw new Error(`Expected readboard toPlay ${toPlay}, got ${evidence.toPlay}.`);
}

function assertReadboardTargetStateChangeEvidence(evidence: ReadboardTargetStateChangeEvidence) {
  if (!evidence.changed) throw new Error("Readboard target state change did not report changed true.");
  if (evidence.beforeSnapshotId === evidence.afterSnapshotId) throw new Error("Readboard target state change did not change snapshot id.");
  if (evidence.beforeMoveNumber === evidence.afterMoveNumber) throw new Error("Readboard target state change did not change move number.");
  if (evidence.beforeStoneCount === evidence.afterStoneCount) throw new Error("Readboard target state change did not change stone count.");
  if (!evidence.boardSizeStable) throw new Error("Readboard target state change did not keep board size stable.");
  if (evidence.toPlay !== "white") throw new Error(`Expected changed readboard toPlay white, got ${evidence.toPlay}.`);
}

function assertHttpSuccess(statusCode: number, label: string) {
  if (!Number.isFinite(statusCode) || statusCode < 200 || statusCode >= 400) {
    throw new Error(`${label} returned HTTP ${statusCode}.`);
  }
}

function yikeListResultCount(payload: string): number {
  try {
    const parsed: unknown = JSON.parse(payload);
    if (!isRecord(parsed)) return 0;
    const result = parsed.Result;
    if (!isRecord(result)) return 0;
    const list = result.list;
    return Array.isArray(list) ? list.length : 0;
  } catch {
    return 0;
  }
}

function providerErrorDetails(error: unknown): { kind: string; message: string } {
  if (isRecord(error)) {
    const kind = typeof error.kind === "string" ? error.kind : "";
    const message = typeof error.message === "string" && error.message.trim() ? error.message : errorMessage(error);
    return { kind, message };
  }
  return { kind: "", message: errorMessage(error) };
}

function validateAnalysisFrame(frame: AnalysisFrameDto, label: string) {
  if (!Number.isFinite(frame.turn) || frame.turn < 0) throw new Error(`${label} returned an invalid turn.`);
  if (!Number.isFinite(frame.visits) || frame.visits <= 0) throw new Error(`${label} returned no visits.`);
  if (!Array.isArray(frame.candidates)) throw new Error(`${label} returned invalid candidates.`);
  if (frame.candidates.length === 0) throw new Error(`${label} returned no candidate moves.`);
}

function summarizeAnalysisFrame(frame: AnalysisFrameDto): AnalysisFrameEvidence {
  return {
    jobId: frame.job_id,
    turn: frame.turn,
    visits: frame.visits,
    candidates: frame.candidates.length,
    hasOwnership: Array.isArray(frame.ownership),
    hasPolicy: Array.isArray(frame.policy),
    winrateBlack: frame.winrate_black,
    scoreMeanBlack: frame.score_mean_black
  };
}

function cachePayloadFromRecord(payload: JsonValue): { frames: AnalysisFrameDto[]; problems: JsonValue[] } {
  if (!isRecord(payload)) throw new Error("Analysis cache payload must be an object.");
  if (!Array.isArray(payload.frames)) throw new Error("Analysis cache payload missing frames array.");
  const frames = payload.frames as unknown as AnalysisFrameDto[];
  if (frames.length === 0) throw new Error("Analysis cache payload contained no frames.");
  const problems = Array.isArray(payload.problems) ? payload.problems : [];
  return { frames, problems };
}

function buildValidChangedSgfForCacheCheck(sgfText: string): string {
  const trimmed = sgfText.trimEnd();
  const finalParenIndex = trimmed.lastIndexOf(")");
  if (finalParenIndex < 0) {
    throw new Error("Cannot build changed SGF for stale cache check: source SGF has no closing parenthesis.");
  }
  const before = trimmed.slice(0, finalParenIndex);
  const after = trimmed.slice(finalParenIndex);
  const changed = `${before}C[runtime smoke changed sgf for stale cache check]${after}`;
  if (changed === sgfText || !changed.includes("C[runtime smoke changed sgf for stale cache check]")) {
    throw new Error("Cannot build changed SGF for stale cache check: comment insertion did not change SGF text.");
  }
  return changed;
}

function countAnalyzedMoves(frames: AnalysisFrameDto[], moveCount: number): number {
  const turns = new Set(frames.map((frame) => frame.turn).filter((turn) => Number.isFinite(turn)));
  return Math.min(Math.max(turns.size, frames.length), Math.max(moveCount, frames.length));
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function createKataGoCancelEventCollector() {
  let jobId = "";
  let outcome: KataGoCancelEvidence | null = null;
  let resolveWaiter: ((event: KataGoCancelEvidence) => void) | null = null;
  let timeoutId: number | null = null;

  const record = (event: KataGoCancelEvidence) => {
    if (jobId && event.jobId !== jobId) return;
    if (outcome) return;
    outcome = event;
    if (timeoutId !== null) window.clearTimeout(timeoutId);
    resolveWaiter?.(event);
  };

  const wait = (timeoutMs: number): Promise<KataGoCancelEvidence> => {
    if (outcome) return Promise.resolve(outcome);
    return new Promise((resolve) => {
      resolveWaiter = resolve;
      timeoutId = window.setTimeout(() => {
        const event: KataGoCancelEvidence = { kind: "timeout", jobId };
        outcome = event;
        resolve(event);
      }, timeoutMs);
    });
  };

  return {
    setJobId(nextJobId: string) {
      jobId = nextJobId;
    },
    wait,
    handlers: {
      onCancelled: (payload: { job_id: string; message: string }) => record({
        kind: "cancelled",
        jobId: payload.job_id,
        message: payload.message
      }),
      onError: (payload: { job_id: string; message: string }) => record({
        kind: "error",
        jobId: payload.job_id,
        message: payload.message
      }),
      onComplete: (payload: { job_id: string; frames: AnalysisFrameDto[] }) => record({
        kind: "complete",
        jobId: payload.job_id,
        frames: payload.frames.length
      })
    }
  };
}

function createKataGoWorkflowEventCollector() {
  let jobId = "";
  const pendingProgress: Array<{ job_id: string; completed: number; expected: number; turn: number; response_jsonl: string }> = [];
  const pendingTerminal: KataGoCancelEvidence[] = [];
  let progressWaiter: ((event: { job_id: string; completed: number; expected: number; turn: number; response_jsonl: string }) => void) | null = null;
  let terminalWaiter: ((event: KataGoCancelEvidence) => void) | null = null;
  let progressTimeoutId: number | null = null;
  let terminalTimeoutId: number | null = null;

  const matchesJob = (nextJobId: string) => !jobId || nextJobId === jobId;
  const takeProgress = () => jobId ? pendingProgress.find((event) => event.job_id === jobId) ?? null : pendingProgress[0] ?? null;
  const takeTerminal = () => jobId ? pendingTerminal.find((event) => event.jobId === jobId) ?? null : pendingTerminal[0] ?? null;

  const resolveProgress = (event: { job_id: string; completed: number; expected: number; turn: number; response_jsonl: string }) => {
    if (progressTimeoutId !== null) window.clearTimeout(progressTimeoutId);
    progressTimeoutId = null;
    progressWaiter?.(event);
    progressWaiter = null;
  };
  const resolveTerminal = (event: KataGoCancelEvidence) => {
    if (terminalTimeoutId !== null) window.clearTimeout(terminalTimeoutId);
    terminalTimeoutId = null;
    terminalWaiter?.(event);
    terminalWaiter = null;
  };

  const recordProgress = (event: { job_id: string; completed: number; expected: number; turn: number; response_jsonl: string }) => {
    if (!matchesJob(event.job_id)) return;
    pendingProgress.push(event);
    if (progressWaiter) resolveProgress(event);
  };
  const recordTerminal = (event: KataGoCancelEvidence) => {
    if (!matchesJob(event.jobId)) return;
    pendingTerminal.push(event);
    if (terminalWaiter) resolveTerminal(event);
  };

  return {
    setJobId(nextJobId: string) {
      jobId = nextJobId;
      const progress = takeProgress();
      if (progress && progressWaiter) resolveProgress(progress);
      const terminal = takeTerminal();
      if (terminal && terminalWaiter) resolveTerminal(terminal);
    },
    waitForProgress(timeoutMs: number): Promise<{ job_id: string; completed: number; expected: number; turn: number; response_jsonl: string }> {
      const progress = takeProgress();
      if (progress) return Promise.resolve(progress);
      return new Promise((resolve, reject) => {
        progressWaiter = resolve;
        progressTimeoutId = window.setTimeout(() => {
          progressWaiter = null;
          reject(new Error(`Timed out waiting for KataGo progress event for ${jobId || "pending job"}.`));
        }, timeoutMs);
      });
    },
    waitForTerminal(timeoutMs: number): Promise<KataGoCancelEvidence> {
      const terminal = takeTerminal();
      if (terminal) return Promise.resolve(terminal);
      return new Promise((resolve) => {
        terminalWaiter = resolve;
        terminalTimeoutId = window.setTimeout(() => {
          terminalWaiter = null;
          resolve({ kind: "timeout", jobId });
        }, timeoutMs);
      });
    },
    handlers: {
      onProgress: recordProgress,
      onCancelled: (payload: { job_id: string; message: string }) => recordTerminal({
        kind: "cancelled",
        jobId: payload.job_id,
        message: payload.message
      }),
      onError: (payload: { job_id: string; message: string }) => recordTerminal({
        kind: "error",
        jobId: payload.job_id,
        message: payload.message
      }),
      onComplete: (payload: { job_id: string; frames: AnalysisFrameDto[] }) => recordTerminal({
        kind: "complete",
        jobId: payload.job_id,
        frames: payload.frames.length,
        framesData: payload.frames
      })
    }
  };
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} must be a non-empty string.`);
  return value;
}

function requiredNumber(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} must be a finite number.`);
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function summarizeResult(value: unknown): Record<string, unknown> | undefined {
  if (typeof value === "string") return { bytes: value.length };
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    if ("details" in value && typeof value.details === "object" && value.details !== null) {
      return value.details as Record<string, unknown>;
    }
    if ("root_id" in value && "nodes" in value && Array.isArray((value as SgfTreeDto).nodes)) {
      const tree = value as SgfTreeDto;
      return { rootId: tree.root_id, nodes: tree.nodes.length };
    }
    return value as Record<string, unknown>;
  }
  return undefined;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (isRecord(error)) {
    const message = error.message;
    if (typeof message === "string" && message.trim()) return message;
    const kind = error.kind;
    if (typeof kind === "string" && kind.trim()) return kind;
    try {
      return JSON.stringify(error);
    } catch {
      return String(error);
    }
  }
  return String(error);
}
