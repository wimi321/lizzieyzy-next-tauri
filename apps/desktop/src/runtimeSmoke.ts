import {
  analyzeKataGoGame,
  analyzeKataGoOnce,
  appendSgfMove,
  cancelKataGoAnalysis,
  checkEngineAssets,
  deleteSgfNode,
  editSgfMove,
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
  updateSgfNodeProperties
} from "./api/backend";
import type { AnalysisFrameDto, AssetCheckDto, EngineProfileDto, KataGoLiveSmokeConfigDto, MoveVertex, PlayerColor, SgfTreeDto, SgfTreeNodeDto } from "./domain/types";

type RuntimeSmokeStatus = "pass" | "fail";
type RuntimeSmokeCheckName =
  | "runtime_started"
  | "sgf_loaded"
  | "branch_navigation"
  | "comment_edit"
  | "property_edit"
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
  | "katago_failure_mode_missing_assets";
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
  error?: string;
};
type RuntimeSmokeImportMeta = ImportMeta & { env?: Record<string, string | undefined> };
type EditableMove = { id: string; color: PlayerColor; vertex: MoveVertex; parentId: string | null };
type RuntimeSmokePhase = "full" | "edit-save" | "reopen-verify" | "katago-live";
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
type KataGoCancelEvidence = {
  kind: "cancelled" | "error" | "complete" | "timeout";
  jobId: string;
  message?: string;
  frames?: number;
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

const schema = "lizzieyzy.tauri-runtime-ui-smoke.v1";
const truthyValues = new Set(["1", "true", "yes", "on"]);
const expectedBranchComment = "runtime smoke branch persisted";
const expectedBranchName = "runtime-smoke-branch";
const expectedBranchLabel = "aa:A";
const replayInvariant = "saved_or_reopened_replay_has_no_errors_and_position_count_matches_move_count_plus_initial_position";
const defaultKatagoMaxVisits = 32;
const defaultKatagoGameMaxVisits = 16;
const defaultKatagoCancelMaxVisits = 10_000;
const defaultKatagoCancelDelayMs = 250;

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
    if (!sgfPath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH is required.");
    if (!reportPath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH is required.");
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

    if (resolvedConfig.phase === "katago-live") {
      await runKataGoLivePhase(report, sgfPath, resolvedConfig.katago);
    } else if (resolvedConfig.phase === "reopen-verify") {
      await runReopenVerifyPhase(report, sgfPath, expectedReportPath ?? reportPath);
    } else {
      await runEditSavePhase(report, sgfPath, resolvedConfig.phase);
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
      { key: "LB", values: [expectedBranchLabel] }
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
  const value = runtimeSmokeImportMeta().env?.[name];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizeRuntimeSmokePhase(value: string | null | undefined): RuntimeSmokePhase {
  if (value === "edit-save" || value === "reopen-verify" || value === "katago-live") return value;
  return "full";
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

function assertNonEmptyString(value: string, message: string) {
  if (!value.trim()) throw new Error(message);
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
  return error instanceof Error ? error.message : String(error);
}
