import { useEffect, useMemo, useRef, useState, type ComponentProps, type ComponentType } from "react";
import { BoardCanvas } from "./components/BoardCanvas";
import { WinrateChart } from "./components/WinrateChart";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { EngineSetupPanel } from "./components/EngineSetupPanel";
import { CacheStatusBadge } from "./components/CacheStatusBadge";
import { PreferencesPanel } from "./components/PreferencesPanel";
import { ProviderPanel } from "./components/ProviderPanel";
import { LegacyShell } from "./components/LegacyShell";
import { SgfTreePanel } from "./components/SgfTreePanel";
import * as backendApi from "./api/backend";
import {
  analyzeKataGoOnce,
  cancelKataGoAnalysis,
  classifyProblems,
  fakeAnalyze,
  getHealth,
  listenToKataGoAnalysisEvents,
  openSgfDocument,
  parseSgfTree,
  parseSgfSummary,
  replaySgfPositionAtNode,
  replaySgfPositions,
  saveSgfDocument,
  startKataGoGameAnalysis,
  updateSgfNodeComment,
  updateSgfNodeProperties,
  previewLegacyConfigMigration,
  applyLegacyConfigMigration,
  loadEngineProfilesSettings,
  type SgfPropertyUpdate
} from "./api/backend";
import { computeGameCacheKey, loadAnalysisCache, saveAnalysisCache } from "./api/analysisCache";
import { loadAppPreferences, saveAppPreferences } from "./api/preferences";
import { clampMoveNumberToPositions, createDemoGame, replayGamePositions, selectExactPosition } from "./domain/board";
import type { AnalysisCacheRecord, CacheStatus, GameCacheKey, JsonValue } from "./domain/cache";
import { defaultAppPreferences, normalizeAppPreferences, type AppPreferences } from "./domain/preferences";
import { providerDocumentName, providerLabel, providerSourceLabel, type ProviderImportResult } from "./domain/providers";
import type { AnalysisFrameDto, AppHealthDto, EngineProfileDto, GameDto, MoveVertex, PlayerColor, PositionDto, ProblemMarkerDto, SgfTreeDto, SgfTreeNodeDto } from "./domain/types";
import { resolveRuntimeSmokeConfig, runRuntimeSmokeMode } from "./runtimeSmoke";

const demoSgf = "(;GM[1]FF[4]SZ[19]KM[7.5]PB[Lee Changho]PW[Rui Naiwei]RE[B+R];B[pd];W[dd];B[pp];W[dp];B[jq];W[qj];B[nc];W[fc];B[qf];W[cn];B[cp];W[do];B[co];W[dn];B[fq];W[eq];B[fp];W[gp];B[gq];W[hp])";
const demoGame = createDemoGame();
type AnalysisProgress = { jobId: string; completed: number; expected: number; turn: number; responseJsonl: string };
type PendingAnalysisTerminalEvent =
  | { kind: "complete"; frames: AnalysisFrameDto[] }
  | { kind: "error" | "cancelled"; message: string };
type CacheEngineKind = "fake" | "katago";
type CachedAnalysisPayload = { frames: AnalysisFrameDto[]; problems: ProblemMarkerDto[] };
type ReviewWorkflowPhase = "idle" | "starting" | "running" | "completed" | "cancelling" | "cancelled" | "error" | "cache-restored";
type ReviewWorkflowSource = "none" | "fake" | "katago" | "cache";
type ReviewWorkflowStatus = {
  phase: ReviewWorkflowPhase;
  source: ReviewWorkflowSource;
  message: string;
  sessionToken: string;
  activeJobId: string | null;
  completed: number;
  expected: number;
  currentTurn: number | null;
  progressVerified: boolean;
  cancelVerified: boolean;
  restartAfterCancelVerified: boolean;
  cacheRestoreVerified: boolean;
  engineFailureVerified: boolean;
  staleAnalysisPrevented: boolean;
};
type PendingPreferencesSave = { version: number; preferences: AppPreferences };
type NativeSgfDialogAction = "none" | "open" | "save" | "save-as";
type NativeSgfDialogStatus = "idle" | "opening" | "saving" | "cancelled" | "opened" | "saved" | "error" | "readback-error";
type NativeSgfDialogWorkflow = {
  action: NativeSgfDialogAction;
  status: NativeSgfDialogStatus;
  source: "native-dialog" | "native-backend" | "browser-fallback" | "unknown";
  path: string | null;
  message: string;
  readbackVerified: boolean;
  reparseVerified: boolean;
  dirtyAfter: boolean;
};
type AppendSgfMove = (sgfText: string, parentNodeId: string, color: PlayerColor, vertex: MoveVertex) => Promise<unknown>;
type EditSgfMove = (sgfText: string, nodeId: string, color: PlayerColor, vertex: MoveVertex) => Promise<unknown>;
type DeleteSgfNode = (sgfText: string, nodeId: string) => Promise<unknown>;
type ReorderSgfVariation = (sgfText: string, nodeId: string, targetIndex: number) => Promise<unknown>;
type SgfMoveEditMode = "append" | "edit";
type SgfTreeMoveEditProps = {
  moveEditMode?: SgfMoveEditMode;
  canEditSelectedMove?: boolean;
  onMoveEditModeChange?: (mode: SgfMoveEditMode) => void;
  onEditSelectedMovePass?: () => void;
};
type AnalysisCacheLoadResult =
  | { status: "hit"; record: AnalysisCacheRecord; engineKind: CacheEngineKind }
  | { status: "miss" }
  | { status: "error"; message: string };

const SgfTreePanelWithMoveEdit = SgfTreePanel as ComponentType<ComponentProps<typeof SgfTreePanel> & SgfTreeMoveEditProps>;
const initialReviewWorkflowStatus: ReviewWorkflowStatus = {
  phase: "idle",
  source: "none",
  message: "No review analysis is running.",
  sessionToken: "review-session-0",
  activeJobId: null,
  completed: 0,
  expected: 0,
  currentTurn: null,
  progressVerified: false,
  cancelVerified: false,
  restartAfterCancelVerified: false,
  cacheRestoreVerified: false,
  engineFailureVerified: false,
  staleAnalysisPrevented: false
};
const initialNativeSgfDialogWorkflow: NativeSgfDialogWorkflow = {
  action: "none",
  status: "idle",
  source: "unknown",
  path: null,
  message: "Native SGF dialog workflow idle.",
  readbackVerified: false,
  reparseVerified: false,
  dirtyAfter: false
};

export function App() {
  const [health, setHealth] = useState<AppHealthDto | null>(null);
  const [game, setGame] = useState<GameDto>(() => demoGame);
  const [positions, setPositions] = useState<PositionDto[]>(() => replayGamePositions(demoGame));
  const [currentMove, setCurrentMove] = useState(0);
  const [frames, setFrames] = useState<AnalysisFrameDto[]>([]);
  const [problems, setProblems] = useState<ProblemMarkerDto[]>([]);
  const [sgfText, setSgfText] = useState(demoSgf);
  const [message, setMessage] = useState("Preview workspace ready. Parse the sample SGF or import a local game to start reviewing.");
  const [isKataGoRunning, setIsKataGoRunning] = useState(false);
  const [selectedCandidateIndex, setSelectedCandidateIndex] = useState<number | null>(null);
  const [currentFilePath, setCurrentFilePath] = useState<string | null>(null);
  const [fallbackFileName, setFallbackFileName] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgress | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [cacheStatus, setCacheStatus] = useState<CacheStatus>("idle");
  const [cacheRecord, setCacheRecord] = useState<AnalysisCacheRecord | null>(null);
  const [cacheError, setCacheError] = useState<string | null>(null);
  const [currentCacheKey, setCurrentCacheKey] = useState<GameCacheKey | null>(null);
  const [sgfTree, setSgfTree] = useState<SgfTreeDto | null>(null);
  const [selectedSgfNodeId, setSelectedSgfNodeId] = useState<string | null>(null);
  const [sgfTreeError, setSgfTreeError] = useState<string | null>(null);
  const [isSgfTreeLoading, setIsSgfTreeLoading] = useState(false);
  const [commentDraft, setCommentDraft] = useState("");
  const [isCommentSaving, setIsCommentSaving] = useState(false);
  const [isPropertySaving, setIsPropertySaving] = useState(false);
  const [isAnnotationSaving, setIsAnnotationSaving] = useState(false);
  const [annotationError, setAnnotationError] = useState<string | null>(null);
  const [isMoveAppending, setIsMoveAppending] = useState(false);
  const [isNodeDeleting, setIsNodeDeleting] = useState(false);
  const [isNodeReordering, setIsNodeReordering] = useState(false);
  const [editColor, setEditColor] = useState<PlayerColor>("black");
  const [sgfMoveEditMode, setSgfMoveEditMode] = useState<SgfMoveEditMode>("append");
  const [nativeSgfDialogWorkflow, setNativeSgfDialogWorkflow] = useState<NativeSgfDialogWorkflow>(initialNativeSgfDialogWorkflow);
  const [treeNodePositionOverride, setTreeNodePositionOverride] = useState<PositionDto | null>(null);
  const [preferences, setPreferences] = useState<AppPreferences>(() => defaultAppPreferences);
  const [preferencesStatus, setPreferencesStatus] = useState("Loading preferences...");
  const [legacyConfigPath, setLegacyConfigPath] = useState("");
  const [legacyConfigStatus, setLegacyConfigStatus] = useState("No legacy config selected.");
  const [legacyConfigPreview, setLegacyConfigPreview] = useState<backendApi.LegacyConfigMigrationPreviewDto | null>(null);
  const [legacyConfigApplyResult, setLegacyConfigApplyResult] = useState<backendApi.LegacyConfigMigrationApplyDto | null>(null);
  const [isLegacyConfigMigrating, setIsLegacyConfigMigrating] = useState(false);
  const [reviewWorkflowStatus, setReviewWorkflowStatus] = useState<ReviewWorkflowStatus>(() => initialReviewWorkflowStatus);
  const activeJobIdRef = useRef<string | null>(null);
  const analysisSessionCounterRef = useRef(0);
  const startingAnalysisRef = useRef(false);
  const userChangedPreferencesRef = useRef(false);
  const preferencesSaveInFlightRef = useRef(false);
  const preferencesSaveVersionRef = useRef(0);
  const pendingPreferencesSaveRef = useRef<PendingPreferencesSave | null>(null);
  const pendingAnalysisProgressRef = useRef<Map<string, AnalysisProgress>>(new Map());
  const pendingAnalysisTerminalEventsRef = useRef<Map<string, PendingAnalysisTerminalEvent>>(new Map());
  const analysisCleanupRef = useRef<(() => void) | null>(null);
  const sgfTreeRequestVersionRef = useRef(0);
  const treeNodeReplayRequestVersionRef = useRef(0);
  const sgfTextEditVersionRef = useRef(0);
  const runtimeSmokeStartedRef = useRef(false);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((error: unknown) => setMessage(errorMessage(error)));
  }, []);

  useEffect(() => {
    let isMounted = true;
    loadAppPreferences()
      .then((loaded) => {
        if (!isMounted || userChangedPreferencesRef.current) return;
        setPreferences(loaded);
        setPreferencesStatus("Preferences loaded.");
      })
      .catch((error: unknown) => {
        if (isMounted && !userChangedPreferencesRef.current) setPreferencesStatus(`Load failed: ${errorMessage(error)}`);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    return () => cleanupAnalysisListeners();
  }, []);

  useEffect(() => {
    void refreshSgfTree(demoSgf, demoGame.moves.length, false);
  }, []);

  useEffect(() => {
    if (runtimeSmokeStartedRef.current) return;
    resolveRuntimeSmokeConfig()
      .then((config) => {
        if (runtimeSmokeStartedRef.current || !config.enabled) return;
        runtimeSmokeStartedRef.current = true;
        setMessage("Runtime smoke mode is running...");
        return runRuntimeSmokeMode(config)
          .then((report) => setMessage(`Runtime smoke mode ${report.status}: report written to ${report.reportPath ?? "configured report path"}.`));
      })
      .catch((error: unknown) => setMessage(`Runtime smoke mode failed before reporting: ${errorMessage(error)}`));
  }, []);

  const currentFrame = useMemo(() => frames.find((f) => f.turn === currentMove) ?? frames.at(-1), [frames, currentMove]);
  const visibleCurrentFrame = useMemo(() => applyPreferencesToFrame(currentFrame, preferences), [currentFrame, preferences]);
  const currentPosition = useMemo(
    () => treeNodePositionOverride ?? selectExactPosition(positions, currentMove, game.summary.board_size),
    [treeNodePositionOverride, positions, currentMove, game.summary.board_size]
  );
  const maxMove = Math.max(positions.at(-1)?.move_number ?? 0, 1);
  const documentName = useMemo(() => currentFilePath ? fileNameFromPath(currentFilePath) : fallbackFileName ?? "Untitled SGF", [currentFilePath, fallbackFileName]);
  const saveFileName = documentName.toLowerCase().endsWith(".sgf") ? documentName : `${documentName}.sgf`;
  const nativeSgfDialogDataPath = useMemo(
    () => nativeSgfDialogWorkflow.path ? fileNameFromPath(nativeSgfDialogWorkflow.path) : "",
    [nativeSgfDialogWorkflow.path]
  );
  const selectedSgfNode = useMemo(
    () => selectedSgfNodeId ? sgfTree?.nodes.find((node) => node.id === selectedSgfNodeId) ?? null : null,
    [selectedSgfNodeId, sgfTree]
  );
  const isBusy = isKataGoRunning || isCommentSaving || isPropertySaving || isAnnotationSaving || isMoveAppending || isNodeDeleting || isNodeReordering;
  const canDeleteSgfNode = Boolean(selectedSgfNode && selectedSgfNode.id !== sgfTree?.root_id && selectedSgfNode.parent_id !== null && !isBusy);
  const canEditSelectedMove = Boolean(selectedSgfNode && selectedSgfNode.id !== sgfTree?.root_id && selectedSgfNode.color && selectedSgfNode.vertex !== null && selectedSgfNode.vertex !== undefined && !isBusy);

  useEffect(() => {
    setEditColor(sgfMoveEditMode === "edit" && selectedSgfNode?.color ? selectedSgfNode.color : currentPosition.to_play);
  }, [currentPosition.to_play, selectedSgfNode?.color, sgfMoveEditMode]);

  useEffect(() => {
    setSelectedCandidateIndex(null);
  }, [currentMove]);

  useEffect(() => {
    if (!preferences.showCandidates || (selectedCandidateIndex !== null && selectedCandidateIndex >= preferences.candidateLimit)) {
      setSelectedCandidateIndex(null);
    }
  }, [preferences.showCandidates, preferences.candidateLimit, selectedCandidateIndex]);

  function handlePreferencesChange(nextPreferences: AppPreferences) {
    const normalized = normalizeAppPreferences(nextPreferences);
    userChangedPreferencesRef.current = true;
    pendingPreferencesSaveRef.current = {
      version: preferencesSaveVersionRef.current + 1,
      preferences: normalized
    };
    preferencesSaveVersionRef.current = pendingPreferencesSaveRef.current.version;
    setPreferences(normalized);
    setPreferencesStatus("Saving preferences...");
    void runPreferencesSaveLoop();
  }

  async function runPreferencesSaveLoop() {
    if (preferencesSaveInFlightRef.current) return;
    preferencesSaveInFlightRef.current = true;
    try {
      while (pendingPreferencesSaveRef.current) {
        const pending = pendingPreferencesSaveRef.current;
        try {
          await saveAppPreferences(pending.preferences);
        } catch (error) {
          if (pendingPreferencesSaveRef.current?.version === pending.version) {
            setPreferencesStatus(`Save failed: ${errorMessage(error)}`);
            return;
          }
          setPreferencesStatus("Saving preferences...");
          continue;
        }

        if (pendingPreferencesSaveRef.current?.version === pending.version) {
          pendingPreferencesSaveRef.current = null;
          setPreferencesStatus("Preferences saved.");
          return;
        }
        setPreferencesStatus("Saving preferences...");
      }
    } finally {
      preferencesSaveInFlightRef.current = false;
    }
  }

  function handleLegacyConfigPathChange(path: string) {
    setLegacyConfigPath(path);
    setLegacyConfigPreview(null);
    setLegacyConfigApplyResult(null);
    setLegacyConfigStatus(path.trim() ? "Ready to preview legacy config." : "No legacy config selected.");
  }

  async function handlePreviewLegacyConfigMigration() {
    const path = legacyConfigPath.trim();
    if (!path) {
      setLegacyConfigStatus("Enter a legacy Java/Swing config path before previewing.");
      return;
    }
    setIsLegacyConfigMigrating(true);
    setLegacyConfigStatus("Previewing legacy config migration...");
    setLegacyConfigApplyResult(null);
    try {
      const preview = await previewLegacyConfigMigration(path);
      setLegacyConfigPreview(preview);
      const fieldCount = preview.migratedFields.length;
      const warningCount = preview.warnings.length;
      setLegacyConfigStatus(`Preview ready: ${fieldCount} migrated fields, ${warningCount} warnings.`);
    } catch (error) {
      setLegacyConfigPreview(null);
      setLegacyConfigStatus(`Preview failed: ${errorMessage(error)}`);
    } finally {
      setIsLegacyConfigMigrating(false);
    }
  }

  async function handleApplyLegacyConfigMigration() {
    const path = legacyConfigPath.trim();
    if (!path) {
      setLegacyConfigStatus("Enter a legacy Java/Swing config path before applying.");
      return;
    }
    setIsLegacyConfigMigrating(true);
    setLegacyConfigStatus("Applying legacy config migration...");
    try {
      const result = await applyLegacyConfigMigration(path);
      setLegacyConfigApplyResult(result);
      if (result.status === "failed") {
        setLegacyConfigStatus(`Apply failed: ${legacyConfigApplyFailureSummary(result)}`);
        return;
      }
      setLegacyConfigPreview({
        sourcePath: result.sourcePath,
        preferences: null,
        engineProfiles: null,
        migratedFields: result.migratedFields,
        warnings: result.warnings
      });
      const loadedPreferences = await loadAppPreferences();
      setPreferences(loadedPreferences);
      await loadEngineProfilesSettings();
      setPreferencesStatus("Preferences loaded after legacy migration.");
      setLegacyConfigStatus(`Applied legacy config migration: ${result.migratedFields.length} migrated fields. ${legacyConfigApplySuccessSummary(result)}`);
    } catch (error) {
      setLegacyConfigStatus(`Apply failed: ${errorMessage(error)}`);
    } finally {
      setIsLegacyConfigMigrating(false);
    }
  }

  async function handleParseSgf() {
    const text = sgfText;
    const sgfTreeRequest = beginSgfTreeLoad();
    try {
      const [parsed, replayed, tree] = await Promise.all([parseSgfSummary(text), replaySgfPositions(text), parseSgfTree(text)]);
      const targetMove = replayed.at(-1)?.move_number ?? parsed.moves.length;
      const loadedMessage = `Loaded ${parsed.summary.black_name ?? "Black"} vs ${parsed.summary.white_name ?? "White"}: ${parsed.summary.move_count} moves.`;
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(targetMove);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      clearTreeNodePositionOverride();
      applySgfTree(tree, targetMove, sgfTreeRequest);
      setMessage(loadedMessage);
      await checkAnalysisCacheForGame(text, currentFilePath, parsed, replayed, loadedMessage, tree);
    } catch (error) {
      clearReviewData();
      resetAnalysisCacheState();
      setCurrentMove(0);
      failSgfTreeLoad(error, sgfTreeRequest);
      setMessage(`Parse failed: ${errorMessage(error)}`);
    } finally {
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleOpenSgfDocument() {
    if (dirty && !window.confirm("Discard unsaved SGF changes and open another file?")) return;
    let sgfTreeRequest: number | null = null;
    setNativeSgfDialogWorkflow({
      action: "open",
      status: "opening",
      source: tauriRuntimeObserved ? "native-dialog" : "browser-fallback",
      path: currentFilePath,
      message: "Opening SGF through native dialog...",
      readbackVerified: false,
      reparseVerified: false,
      dirtyAfter: dirty
    });
    try {
      const document = await openSgfDocument();
      if (!document) {
        setMessage("Native Open is unavailable here. Use Import SGF in browser preview.");
        setNativeSgfDialogWorkflow({
          action: "open",
          status: "cancelled",
          source: tauriRuntimeObserved ? "native-dialog" : "browser-fallback",
          path: currentFilePath,
          message: "Open cancelled or unavailable; current SGF was not replaced.",
          readbackVerified: false,
          reparseVerified: false,
          dirtyAfter: dirty
        });
        return;
      }
      setSgfText(document.sgfText);
      sgfTextEditVersionRef.current += 1;
      setCurrentFilePath(document.path);
      setFallbackFileName(null);
      setDirty(false);
      clearTreeNodePositionOverride();
      sgfTreeRequest = beginSgfTreeLoad();
      const [parsed, replayed, tree] = await Promise.all([parseSgfSummary(document.sgfText), replaySgfPositions(document.sgfText), parseSgfTree(document.sgfText)]);
      const targetMove = replayed.at(-1)?.move_number ?? parsed.moves.length;
      const openedMessage = `Opened ${fileNameFromPath(document.path ?? "SGF")}: ${parsed.summary.move_count} moves.`;
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(targetMove);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      clearTreeNodePositionOverride();
      applySgfTree(tree, targetMove, sgfTreeRequest);
      setMessage(openedMessage);
      setNativeSgfDialogWorkflow({
        action: "open",
        status: "opened",
        source: "native-dialog",
        path: document.path,
        message: openedMessage,
        readbackVerified: true,
        reparseVerified: true,
        dirtyAfter: false
      });
      await checkAnalysisCacheForGame(document.sgfText, document.path, parsed, replayed, openedMessage, tree);
    } catch (error) {
      failSgfTreeLoad(error, sgfTreeRequest);
      const message = `Open failed: ${errorMessage(error)}`;
      setMessage(message);
      setNativeSgfDialogWorkflow({
        action: "open",
        status: "error",
        source: tauriRuntimeObserved ? "native-dialog" : "browser-fallback",
        path: currentFilePath,
        message,
        readbackVerified: false,
        reparseVerified: false,
        dirtyAfter: dirty
      });
    } finally {
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleSaveSgfDocument(saveAs = false) {
    let sgfTreeRequest: number | null = null;
    let savedPath: string | null = null;
    const action: NativeSgfDialogAction = saveAs ? "save-as" : "save";
    const saveSource = nativeSaveWorkflowSource(saveAs, currentFilePath, tauriRuntimeObserved);
    setNativeSgfDialogWorkflow({
      action,
      status: "saving",
      source: saveSource,
      path: saveAs ? null : currentFilePath,
      message: saveAs ? "Saving SGF through native Save As dialog..." : "Saving SGF...",
      readbackVerified: false,
      reparseVerified: false,
      dirtyAfter: dirty
    });
    try {
      const saved = await saveSgfDocument(saveAs ? null : currentFilePath, sgfText, saveFileName);
      if (!saved) {
        setMessage("Save cancelled.");
        setNativeSgfDialogWorkflow({
          action,
          status: "cancelled",
          source: saveSource,
          path: currentFilePath,
          message: "Save cancelled; current SGF remains dirty state unchanged.",
          readbackVerified: false,
          reparseVerified: false,
          dirtyAfter: dirty
        });
        return;
      }
      savedPath = saved.path;

      if (!saved.path) {
        setCurrentFilePath(saved.path);
        setDirty(false);
        setMessage(`Saved ${saveFileName}.`);
        setNativeSgfDialogWorkflow({
          action,
          status: "saved",
          source: saveSource,
          path: saved.path,
          message: `Saved ${saveFileName}.`,
          readbackVerified: saved.sgfText === sgfText,
          reparseVerified: false,
          dirtyAfter: false
        });
        return;
      }

      setCurrentFilePath(saved.path);
      setFallbackFileName(null);
      setDirty(false);
      sgfTreeRequest = beginSgfTreeLoad();
      const [parsed, replayed, tree] = await Promise.all([parseSgfSummary(saved.sgfText), replaySgfPositions(saved.sgfText), parseSgfTree(saved.sgfText)]);
      const targetMove = replayed.at(-1)?.move_number ?? parsed.moves.length;
      const savedMessage = `Saved and reloaded ${fileNameFromPath(saved.path)}: ${parsed.summary.move_count} moves.`;
      setSgfText(saved.sgfText);
      sgfTextEditVersionRef.current += 1;
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(targetMove);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      clearTreeNodePositionOverride();
      applySgfTree(tree, targetMove, sgfTreeRequest);
      setMessage(savedMessage);
      setNativeSgfDialogWorkflow({
        action,
        status: "saved",
        source: saveSource,
        path: saved.path,
        message: savedMessage,
        readbackVerified: saved.sgfText === sgfText,
        reparseVerified: true,
        dirtyAfter: false
      });
      await checkAnalysisCacheForGame(saved.sgfText, saved.path, parsed, replayed, savedMessage, tree);
    } catch (error) {
      if (sgfTreeRequest !== null) {
        failSgfTreeLoad(error, sgfTreeRequest);
      }
      const message = savedPath ? `Saved ${fileNameFromPath(savedPath)}, but reload failed: ${errorMessage(error)}` : `Save failed: ${errorMessage(error)}`;
      setMessage(message);
      setNativeSgfDialogWorkflow({
        action,
        status: savedPath ? "readback-error" : "error",
        source: saveSource,
        path: savedPath,
        message,
        readbackVerified: false,
        reparseVerified: false,
        dirtyAfter: dirty
      });
    } finally {
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleFakeAnalyze() {
    const text = sgfText;
    const sgfTreeRequest = beginSgfTreeLoad();
    const sessionToken = nextAnalysisSessionToken();
    setReviewWorkflowStatus({
      ...initialReviewWorkflowStatus,
      phase: "running",
      source: "fake",
      message: "Running browser review fallback.",
      sessionToken
    });
    try {
      const [parsed, result, replayed, tree] = await Promise.all([parseSgfSummary(text), fakeAnalyze(text), replaySgfPositions(text), parseSgfTree(text)]);
      const classified = await classifyProblems(result);
      const targetMove = replayed.at(-1)?.move_number ?? parsed.moves.length;
      setGame(parsed);
      setPositions(replayed);
      setFrames(result);
      setProblems(classified);
      setCurrentMove(targetMove);
      setSelectedCandidateIndex(null);
      clearTreeNodePositionOverride();
      applySgfTree(tree, targetMove, sgfTreeRequest);
      const cacheMessage = await saveAnalysisCacheForGame(text, currentFilePath, parsed, result, classified, "fake");
      setReviewWorkflowStatus((status) => ({
        ...status,
        phase: "completed",
        source: "fake",
        message: `Browser review completed with ${result.length} frames.`,
        completed: result.length,
        expected: result.length,
        currentTurn: targetMove,
        progressVerified: true
      }));
      setMessage(`Generated ${result.length} review frames with candidate moves and winrate history.${cacheMessage}`);
    } catch (error) {
      failSgfTreeLoad(error, sgfTreeRequest);
      setReviewWorkflowStatus((status) => ({
        ...status,
        phase: "error",
        source: "fake",
        message: `Browser review failed: ${errorMessage(error)}`,
        engineFailureVerified: true
      }));
      setMessage(errorMessage(error));
    } finally {
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleRunKataGo(profile: EngineProfileDto, maxVisits: number) {
    const targetTurn = currentMove;
    const visits = resolveAnalysisMaxVisits(maxVisits, preferences);
    const sessionToken = nextAnalysisSessionToken();
    setIsKataGoRunning(true);
    setReviewWorkflowStatus({
      ...initialReviewWorkflowStatus,
      phase: "running",
      source: "katago",
      message: `Running KataGo for move ${targetTurn}.`,
      sessionToken,
      currentTurn: targetTurn
    });
    setMessage(`Running KataGo analysis for move ${targetTurn}...`);
    const sgfTreeRequest = beginSgfTreeLoad();
    try {
      const [parsed, replayed, tree] = await Promise.all([parseSgfSummary(sgfText), replaySgfPositions(sgfText), parseSgfTree(sgfText)]);
      const turn = clampMoveNumberToPositions(replayed, Math.min(targetTurn, replayed.at(-1)?.move_number ?? parsed.moves.length));
      const frame = await analyzeKataGoOnce(profile, sgfText, turn, visits);
      const mergedFrames = mergeAnalysisFrame(frames, frame);
      setGame(parsed);
      setPositions(replayed);
      setFrames(mergedFrames);
      setProblems(await classifyProblems(mergedFrames));
      setCurrentMove(frame.turn);
      setSelectedCandidateIndex(null);
      clearTreeNodePositionOverride();
      applySgfTree(tree, frame.turn, sgfTreeRequest);
      setReviewWorkflowStatus((status) => ({
        ...status,
        phase: "completed",
        source: "katago",
        message: `KataGo completed move ${frame.turn}.`,
        completed: 1,
        expected: 1,
        currentTurn: frame.turn,
        progressVerified: true
      }));
      setMessage(`KataGo analysis completed for move ${frame.turn} with ${frame.visits} visits.`);
    } catch (error) {
      failSgfTreeLoad(error, sgfTreeRequest);
      const message = engineFailureMessage(error);
      setReviewWorkflowStatus((status) => ({
        ...status,
        phase: "error",
        source: "katago",
        message,
        engineFailureVerified: true
      }));
      setMessage(message);
    } finally {
      setIsKataGoRunning(false);
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleAnalyzeKataGoGame(profile: EngineProfileDto, maxVisits: number) {
    if (activeJobIdRef.current || startingAnalysisRef.current) return;
    const visits = resolveAnalysisMaxVisits(maxVisits, preferences);
    const previousWasCancelled = reviewWorkflowStatus.phase === "cancelled";
    const sessionToken = nextAnalysisSessionToken();
    startingAnalysisRef.current = true;
    pendingAnalysisProgressRef.current.clear();
    pendingAnalysisTerminalEventsRef.current.clear();
    setIsKataGoRunning(true);
    setAnalysisProgress(null);
    setReviewWorkflowStatus({
      ...initialReviewWorkflowStatus,
      phase: "starting",
      source: "katago",
      message: "Starting full-game KataGo review.",
      sessionToken,
      restartAfterCancelVerified: previousWasCancelled
    });
    setMessage("Starting full-game KataGo analysis...");
    let cleanup: (() => void) | null = null;
    const sgfTreeRequest = beginSgfTreeLoad();
    try {
      const [parsed, replayed, tree] = await Promise.all([parseSgfSummary(sgfText), replaySgfPositions(sgfText), parseSgfTree(sgfText)]);
      clearTreeNodePositionOverride();
      applySgfTree(tree, replayed.at(-1)?.move_number ?? parsed.moves.length, sgfTreeRequest);
      cleanup = await listenToKataGoAnalysisEvents({
        onProgress: (payload) => {
          if (startingAnalysisRef.current && activeJobIdRef.current === null) {
            pendingAnalysisProgressRef.current.set(payload.job_id, {
              jobId: payload.job_id,
              completed: payload.completed,
              expected: payload.expected,
              turn: payload.turn,
              responseJsonl: payload.response_jsonl
            });
            return;
          }
          if (!isCurrentAnalysisJob(payload.job_id)) {
            markStaleAnalysisPrevented(payload.job_id);
            return;
          }
          const progress = {
            jobId: payload.job_id,
            completed: payload.completed,
            expected: payload.expected,
            turn: payload.turn,
            responseJsonl: payload.response_jsonl
          };
          setAnalysisProgress(progress);
          setReviewWorkflowProgress(progress);
          setMessage(`Analyzing move ${payload.turn}: ${payload.completed}/${payload.expected} positions complete.`);
        },
        onComplete: (payload) => {
          if (startingAnalysisRef.current && activeJobIdRef.current === null) {
            pendingAnalysisTerminalEventsRef.current.set(payload.job_id, { kind: "complete", frames: payload.frames });
            return;
          }
          if (!isCurrentAnalysisJob(payload.job_id)) {
            markStaleAnalysisPrevented(payload.job_id);
            return;
          }
          void finishCompletedAnalysis(payload.job_id, payload.frames, parsed, replayed);
        },
        onError: (payload) => {
          if (startingAnalysisRef.current && activeJobIdRef.current === null) {
            pendingAnalysisTerminalEventsRef.current.set(payload.job_id, { kind: "error", message: payload.message });
            return;
          }
          if (!isCurrentAnalysisJob(payload.job_id)) {
            markStaleAnalysisPrevented(payload.job_id);
            return;
          }
          finishStoppedAnalysis(payload.job_id);
          const message = engineFailureMessage(payload.message);
          setReviewWorkflowStatus((status) => ({
            ...status,
            phase: "error",
            source: "katago",
            activeJobId: null,
            message,
            engineFailureVerified: true
          }));
          setMessage(message);
        },
        onCancelled: (payload) => {
          if (startingAnalysisRef.current && activeJobIdRef.current === null) {
            pendingAnalysisTerminalEventsRef.current.set(payload.job_id, { kind: "cancelled", message: payload.message });
            return;
          }
          if (!isCurrentAnalysisJob(payload.job_id)) {
            markStaleAnalysisPrevented(payload.job_id);
            return;
          }
          finishStoppedAnalysis(payload.job_id);
          setAnalysisProgress(null);
          setReviewWorkflowStatus((status) => ({
            ...status,
            phase: "cancelled",
            source: "katago",
            activeJobId: null,
            message: payload.message || "Full-game KataGo analysis cancelled. You can restart review when ready.",
            cancelVerified: true
          }));
          setMessage(payload.message || "Full-game KataGo analysis cancelled. You can restart review when ready.");
        }
      });
      cleanupAnalysisListeners();
      analysisCleanupRef.current = cleanup;
      const jobId = await startKataGoGameAnalysis(profile, sgfText, visits);
      const pendingTerminalEvent = pendingAnalysisTerminalEventsRef.current.get(jobId);
      const pendingProgress = pendingAnalysisProgressRef.current.get(jobId);
      const hasStalePendingEvent = [...pendingAnalysisProgressRef.current.keys(), ...pendingAnalysisTerminalEventsRef.current.keys()].some((pendingJobId) => pendingJobId !== jobId);
      startingAnalysisRef.current = false;
      pendingAnalysisProgressRef.current.clear();
      pendingAnalysisTerminalEventsRef.current.clear();
      if (hasStalePendingEvent) markStaleAnalysisPrevented("pending-startup-event");
      if (pendingTerminalEvent) {
        await finishPendingAnalysisTerminalEvent(jobId, pendingTerminalEvent, parsed, replayed);
        return;
      }
      activeJobIdRef.current = jobId;
      setActiveJobId(jobId);
      setReviewWorkflowStatus((status) => ({
        ...status,
        phase: pendingProgress ? "running" : "starting",
        source: "katago",
        activeJobId: jobId,
        message: `Full-game KataGo analysis started (${jobId}).`
      }));
      if (pendingProgress) {
        setAnalysisProgress(pendingProgress);
        setReviewWorkflowProgress(pendingProgress);
      }
      setMessage(`Full-game KataGo analysis started (${jobId}).`);
    } catch (error) {
      failSgfTreeLoad(error, sgfTreeRequest);
      cleanup?.();
      if (analysisCleanupRef.current === cleanup) analysisCleanupRef.current = null;
      startingAnalysisRef.current = false;
      pendingAnalysisProgressRef.current.clear();
      pendingAnalysisTerminalEventsRef.current.clear();
      activeJobIdRef.current = null;
      setActiveJobId(null);
      setAnalysisProgress(null);
      setIsKataGoRunning(false);
      const message = engineFailureMessage(error);
      setReviewWorkflowStatus((status) => ({
        ...status,
        phase: "error",
        source: "katago",
        activeJobId: null,
        message,
        engineFailureVerified: true
      }));
      setMessage(message);
    } finally {
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleCancelKataGoAnalysis() {
    const jobId = activeJobIdRef.current;
    if (!jobId) return;
    setReviewWorkflowStatus((status) => ({
      ...status,
      phase: "cancelling",
      source: "katago",
      activeJobId: jobId,
      message: `Cancelling full-game KataGo analysis (${jobId})...`
    }));
    try {
      setMessage("Cancelling full-game KataGo analysis...");
      await cancelKataGoAnalysis(jobId);
      finishStoppedAnalysis(jobId);
      setAnalysisProgress(null);
      setReviewWorkflowStatus((status) => ({
        ...status,
        phase: "cancelled",
        source: "katago",
        activeJobId: null,
        message: "Full-game KataGo analysis cancelled. You can restart review when ready.",
        cancelVerified: true
      }));
      setMessage("Full-game KataGo analysis cancelled. You can restart review when ready.");
    } catch (error) {
      finishStoppedAnalysis(jobId);
      setAnalysisProgress(null);
      const message = `Cancel failed and the UI was released so you can restart safely: ${errorMessage(error)}`;
      setReviewWorkflowStatus((status) => ({
        ...status,
        phase: "error",
        source: "katago",
        activeJobId: null,
        message,
        cancelVerified: true,
        engineFailureVerified: true
      }));
      setMessage(message);
    }
  }

  async function handleImportFile(file: File | null) {
    if (!file) return;
    const sgfTreeRequest = beginSgfTreeLoad();
    try {
      const text = await file.text();
      const [parsed, replayed, tree] = await Promise.all([parseSgfSummary(text), replaySgfPositions(text), parseSgfTree(text)]);
      const targetMove = replayed.at(-1)?.move_number ?? parsed.moves.length;
      const importedMessage = `Imported ${file.name}: ${parsed.summary.move_count} moves.`;
      setSgfText(text);
      sgfTextEditVersionRef.current += 1;
      setCurrentFilePath(null);
      setFallbackFileName(file.name);
      setDirty(false);
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(targetMove);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      clearTreeNodePositionOverride();
      applySgfTree(tree, targetMove, sgfTreeRequest);
      setMessage(importedMessage);
      await checkAnalysisCacheForGame(text, null, parsed, replayed, importedMessage, tree);
    } catch (error) {
      failSgfTreeLoad(error, sgfTreeRequest);
      setMessage(`Import failed: ${errorMessage(error)}`);
    } finally {
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleProviderImport(result: ProviderImportResult) {
    const sgfTreeRequest = beginSgfTreeLoad();
    try {
      const [parsed, replayed, tree] = await Promise.all([parseSgfSummary(result.sgf_text), replaySgfPositions(result.sgf_text), parseSgfTree(result.sgf_text)]);
      const source = providerSourceLabel(result);
      const warningText = result.warnings.length > 0 ? ` ${result.warnings.length} provider warning(s).` : "";
      const importedMessage = `Imported ${providerLabel(result.provider)} provider payload from ${source}: ${parsed.summary.move_count} moves.${warningText}`;
      const targetMove = replayed.at(-1)?.move_number ?? parsed.moves.length;
      setSgfText(result.sgf_text);
      sgfTextEditVersionRef.current += 1;
      setCurrentFilePath(null);
      setFallbackFileName(providerDocumentName(result));
      setDirty(false);
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(targetMove);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      clearTreeNodePositionOverride();
      applySgfTree(tree, targetMove, sgfTreeRequest);
      setMessage(importedMessage);
      await checkAnalysisCacheForGame(result.sgf_text, null, parsed, replayed, importedMessage, tree);
    } catch (error) {
      failSgfTreeLoad(error, sgfTreeRequest);
      setMessage(`Provider import failed: ${errorMessage(error)}`);
      throw error;
    } finally {
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function loadSample() {
    const sgfTreeRequest = beginSgfTreeLoad();
    try {
      const [parsed, replayed, tree] = await Promise.all([parseSgfSummary(demoSgf), replaySgfPositions(demoSgf), parseSgfTree(demoSgf)]);
      const targetMove = replayed.at(-1)?.move_number ?? parsed.moves.length;
      const sampleMessage = `Sample SGF restored: ${parsed.summary.move_count} moves.`;
      setSgfText(demoSgf);
      sgfTextEditVersionRef.current += 1;
      setCurrentFilePath(null);
      setFallbackFileName("sample.sgf");
      setDirty(false);
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(targetMove);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      clearTreeNodePositionOverride();
      applySgfTree(tree, targetMove, sgfTreeRequest);
      setMessage(sampleMessage);
      await checkAnalysisCacheForGame(demoSgf, null, parsed, replayed, sampleMessage, tree);
    } catch (error) {
      failSgfTreeLoad(error, sgfTreeRequest);
      setMessage(`Sample load failed: ${errorMessage(error)}`);
    } finally {
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  function handleMoveSelect(moveNumber: number) {
    clearTreeNodePositionOverride();
    const selectedMove = clampMoveNumberToPositions(positions, moveNumber);
    setCurrentMove(selectedMove);
    setSelectedCandidateIndex(null);
    syncSelectedSgfNodeToMove(selectedMove);
  }

  async function handleSgfTreeNodeSelect(nodeId: string) {
    const node = sgfTree?.nodes.find((item) => item.id === nodeId);
    setSelectedSgfNodeId(nodeId);
    setCommentDraft(node?.comment ?? "");
    if (node?.move_number !== null && node?.move_number !== undefined) {
      setCurrentMove(clampMoveNumberToPositions(positions, node.move_number));
      setSelectedCandidateIndex(null);
    }
    if (!node) return;

    const requestVersion = beginTreeNodeReplay();
    const text = sgfText;
    setMessage(`Loading ${node.is_mainline ? "mainline" : "branch"} node position...`);
    try {
      const position = await replaySgfPositionAtNode(text, nodeId);
      if (treeNodeReplayRequestVersionRef.current !== requestVersion) return;
      setTreeNodePositionOverride(position);
      if (node.is_mainline) {
        setMessage(`Mainline node position displayed for move ${position.move_number}. Analysis remains mainline/current cache.`);
      } else {
        setMessage(`Branch position displayed for ${formatSgfNodeLabel(node)}. Analysis remains mainline/current cache unless re-run.`);
      }
    } catch (error) {
      if (treeNodeReplayRequestVersionRef.current !== requestVersion) return;
      setTreeNodePositionOverride(null);
      setMessage(`Branch position replay failed: ${errorMessage(error)}`);
    }
  }

  async function handleSaveComment(nodeId: string, comment: string) {
    const existingNode = sgfTree?.nodes.find((node) => node.id === nodeId) ?? null;
    const sgfTreeRequest = beginSgfTreeLoad();
    const sourceVersion = sgfTextEditVersionRef.current;
    const sourceText = sgfText;
    setIsCommentSaving(true);
    try {
      const updatedSgfText = await updateSgfNodeComment(sourceText, nodeId, comment.length > 0 ? comment : null);
      if (sgfTextEditVersionRef.current !== sourceVersion) {
        setMessage("Save comment cancelled because the SGF source changed while the save was running.");
        return;
      }
      sgfTextEditVersionRef.current += 1;
      setSgfText(updatedSgfText);
      setDirty(true);
      clearReviewData();
      resetAnalysisCacheState();
      const updatedTree = await parseSgfTree(updatedSgfText);
      const selectedNode = applySgfTreeSelectedNode(updatedTree, nodeId, sgfTreeRequest)
        ?? selectSgfTreeNodeForMove(updatedTree, currentMove);
      setSgfTreeError(null);
      setCommentDraft(selectedNode?.comment ?? "");
      let replayWarning = "";
      if (selectedNode) {
        try {
          const replayRequest = beginTreeNodeReplay();
          const position = await replaySgfPositionAtNode(updatedSgfText, selectedNode.id);
          if (treeNodeReplayRequestVersionRef.current === replayRequest) setTreeNodePositionOverride(position);
        } catch (error) {
          setTreeNodePositionOverride(null);
          replayWarning = ` Position replay failed: ${errorMessage(error)}`;
        }
      }
      setMessage(`comment saved to SGF text for ${selectedNode ? formatSgfNodeLabel(selectedNode) : existingNode ? formatSgfNodeLabel(existingNode) : "selected node"}.${replayWarning}`);
    } catch (error) {
      setMessage(`Save comment failed: ${errorMessage(error)}`);
    } finally {
      setIsCommentSaving(false);
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleSaveProperties(nodeId: string, updates: SgfPropertyUpdate[]) {
    if (updates.length === 0) return;
    const existingNode = sgfTree?.nodes.find((node) => node.id === nodeId) ?? null;
    const sgfTreeRequest = beginSgfTreeLoad();
    const sourceVersion = sgfTextEditVersionRef.current;
    const sourceText = sgfText;
    setIsPropertySaving(true);
    try {
      const result = await updateSgfNodeProperties(sourceText, nodeId, updates);
      if (sgfTextEditVersionRef.current !== sourceVersion) {
        setMessage("Save properties cancelled because the SGF source changed while the save was running.");
        return;
      }

      sgfTextEditVersionRef.current += 1;
      setSgfText(result.sgf_text);
      setDirty(true);
      clearReviewData();
      resetAnalysisCacheState();

      const [parsed, replayed, updatedTree] = await Promise.all([
        parseSgfSummary(result.sgf_text),
        replaySgfPositions(result.sgf_text),
        parseSgfTree(result.sgf_text)
      ]);
      const selectedNode = applySgfTreeSelectedNode(updatedTree, result.node_id, sgfTreeRequest)
        ?? selectSgfTreeNodeForMove(updatedTree, currentMove);
      setGame(parsed);
      setPositions(replayed);
      setSgfTreeError(null);
      setCommentDraft(selectedNode?.comment ?? "");

      let replayWarning = "";
      if (selectedNode) {
        try {
          const replayRequest = beginTreeNodeReplay();
          const position = await replaySgfPositionAtNode(result.sgf_text, selectedNode.id);
          if (treeNodeReplayRequestVersionRef.current === replayRequest) {
            setTreeNodePositionOverride(position);
            setCurrentMove(clampMoveNumberToPositions(replayed, position.move_number));
          }
        } catch (error) {
          setTreeNodePositionOverride(null);
          setCurrentMove(clampMoveNumberToPositions(replayed, selectedNode.move_number ?? replayed.at(-1)?.move_number ?? parsed.moves.length));
          replayWarning = ` Position replay failed: ${errorMessage(error)}`;
        }
      } else {
        clearTreeNodePositionOverride();
        setCurrentMove(clampMoveNumberToPositions(replayed, replayed.at(-1)?.move_number ?? parsed.moves.length));
      }

      setMessage(`SGF properties saved for ${selectedNode ? formatSgfNodeLabel(selectedNode) : existingNode ? formatSgfNodeLabel(existingNode) : "selected node"}.${replayWarning}`);
    } catch (error) {
      setMessage(`Save properties failed: ${errorMessage(error)}`);
    } finally {
      setIsPropertySaving(false);
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleSaveAnnotations(nodeId: string, updates: SgfPropertyUpdate[]) {
    if (updates.length === 0) return;
    const existingNode = sgfTree?.nodes.find((node) => node.id === nodeId) ?? null;
    const sgfTreeRequest = beginSgfTreeLoad();
    const sourceVersion = sgfTextEditVersionRef.current;
    const sourceText = sgfText;
    setIsAnnotationSaving(true);
    setAnnotationError(null);
    try {
      const result = await updateSgfNodeProperties(sourceText, nodeId, updates);
      if (sgfTextEditVersionRef.current !== sourceVersion) {
        const cancelled = "Save annotations cancelled because the SGF source changed while the save was running.";
        setAnnotationError(cancelled);
        setMessage(cancelled);
        return;
      }

      sgfTextEditVersionRef.current += 1;
      setSgfText(result.sgf_text);
      setDirty(true);
      clearReviewData();
      resetAnalysisCacheState();

      const [parsed, replayed, updatedTree] = await Promise.all([
        parseSgfSummary(result.sgf_text),
        replaySgfPositions(result.sgf_text),
        parseSgfTree(result.sgf_text)
      ]);
      const selectedNode = applySgfTreeSelectedNode(updatedTree, result.node_id, sgfTreeRequest)
        ?? selectSgfTreeNodeForMove(updatedTree, currentMove);
      setGame(parsed);
      setPositions(replayed);
      setSgfTreeError(null);
      setCommentDraft(selectedNode?.comment ?? "");

      let replayWarning = "";
      if (selectedNode) {
        try {
          const replayRequest = beginTreeNodeReplay();
          const position = await replaySgfPositionAtNode(result.sgf_text, selectedNode.id);
          if (treeNodeReplayRequestVersionRef.current === replayRequest) {
            setTreeNodePositionOverride(position);
            setCurrentMove(clampMoveNumberToPositions(replayed, position.move_number));
          }
        } catch (error) {
          setTreeNodePositionOverride(null);
          setCurrentMove(clampMoveNumberToPositions(replayed, selectedNode.move_number ?? replayed.at(-1)?.move_number ?? parsed.moves.length));
          replayWarning = ` Position replay failed: ${errorMessage(error)}`;
        }
      } else {
        clearTreeNodePositionOverride();
        setCurrentMove(clampMoveNumberToPositions(replayed, replayed.at(-1)?.move_number ?? parsed.moves.length));
      }

      setMessage(`SGF annotations saved for ${selectedNode ? formatSgfNodeLabel(selectedNode) : existingNode ? formatSgfNodeLabel(existingNode) : "selected node"}.${replayWarning}`);
    } catch (error) {
      const message = `Save annotations failed: ${errorMessage(error)}`;
      setAnnotationError(message);
      setMessage(message);
    } finally {
      setIsAnnotationSaving(false);
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleAppendMove(vertex: MoveVertex) {
    const parentNodeId = selectedSgfNodeId;
    if (!parentNodeId) {
      setMessage("Select an SGF tree node before appending a move.");
      return;
    }
    if (isBusy) return;

    const sgfTreeRequest = beginSgfTreeLoad();
    const sourceVersion = sgfTextEditVersionRef.current;
    const sourceText = sgfText;
    setIsMoveAppending(true);
    setMessage("Appending move to SGF...");
    try {
      const result = normalizeAppendSgfMoveResult(await callAppendSgfMove(sourceText, parentNodeId, editColor, vertex));
      if (sgfTextEditVersionRef.current !== sourceVersion) {
        setMessage("Append move cancelled because the SGF source changed while the edit was running.");
        return;
      }

      sgfTextEditVersionRef.current += 1;
      setSgfText(result.sgfText);
      setDirty(true);
      clearReviewData();
      resetAnalysisCacheState();

      const [parsed, replayed, updatedTree] = await Promise.all([
        parseSgfSummary(result.sgfText),
        replaySgfPositions(result.sgfText),
        parseSgfTree(result.sgfText)
      ]);
      const selectedNode = applySgfTreeSelectedNode(updatedTree, result.newNodeId, sgfTreeRequest);
      setGame(parsed);
      setPositions(replayed);
      setSgfTreeError(null);
      setCommentDraft(selectedNode?.comment ?? "");

      let replayWarning = "";
      if (selectedNode) {
        try {
          const replayRequest = beginTreeNodeReplay();
          const position = await replaySgfPositionAtNode(result.sgfText, selectedNode.id);
          if (treeNodeReplayRequestVersionRef.current === replayRequest) {
            setTreeNodePositionOverride(position);
            setCurrentMove(clampMoveNumberToPositions(replayed, position.move_number));
          }
        } catch (error) {
          setTreeNodePositionOverride(null);
          setCurrentMove(clampMoveNumberToPositions(replayed, selectedNode.move_number ?? replayed.at(-1)?.move_number ?? parsed.moves.length));
          replayWarning = ` Position replay failed: ${errorMessage(error)}`;
        }
      } else {
        clearTreeNodePositionOverride();
        setCurrentMove(clampMoveNumberToPositions(replayed, replayed.at(-1)?.move_number ?? parsed.moves.length));
      }

      setMessage(`Move appended to SGF.${replayWarning}`);
    } catch (error) {
      setMessage(`Append move failed: ${errorMessage(error)}`);
    } finally {
      setIsMoveAppending(false);
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleEditExistingMove(vertex: MoveVertex) {
    if (!selectedSgfNodeId) {
      setMessage("Select an existing SGF move node before editing a move.");
      return;
    }
    const node = sgfTree?.nodes.find((item) => item.id === selectedSgfNodeId) ?? null;
    if (!node) {
      setMessage("Edit move failed: selected SGF node was not found in the current tree.");
      return;
    }
    if (node.id === sgfTree?.root_id || node.parent_id === null || node.parent_id === undefined) {
      setMessage("Root SGF node cannot be edited as a move. Select an existing move node first.");
      return;
    }
    if (!node.color || node.vertex === null || node.vertex === undefined) {
      setMessage("Selected SGF node is not a move node. Select an existing black or white move before editing.");
      return;
    }
    if (isBusy) return;

    const sgfTreeRequest = beginSgfTreeLoad();
    const sourceVersion = sgfTextEditVersionRef.current;
    const sourceText = sgfText;
    setIsMoveAppending(true);
    setMessage(`Editing ${formatSgfNodeLabel(node)}...`);
    try {
      const result = normalizeEditSgfMoveResult(await callEditSgfMove(sourceText, node.id, editColor, vertex));
      if (sgfTextEditVersionRef.current !== sourceVersion) {
        setMessage("Edit move cancelled because the SGF source changed while the edit was running.");
        return;
      }

      sgfTextEditVersionRef.current += 1;
      const appliedVersion = sgfTextEditVersionRef.current;
      setSgfText(result.sgfText);
      setDirty(true);
      clearReviewData();
      resetAnalysisCacheState();

      const [parsed, replayed, updatedTree] = await Promise.all([
        parseSgfSummary(result.sgfText),
        replaySgfPositions(result.sgfText),
        parseSgfTree(result.sgfText)
      ]);
      if (sgfTextEditVersionRef.current !== appliedVersion) return;

      const selectedNode = applySgfTreeSelectedNode(updatedTree, result.nodeId, sgfTreeRequest)
        ?? selectSgfTreeNodeForMove(updatedTree, currentMove);
      setGame(parsed);
      setPositions(replayed);
      setSgfTreeError(null);
      setCommentDraft(selectedNode?.comment ?? "");

      let replayWarning = "";
      if (selectedNode) {
        try {
          const replayRequest = beginTreeNodeReplay();
          const position = await replaySgfPositionAtNode(result.sgfText, selectedNode.id);
          if (sgfTextEditVersionRef.current !== appliedVersion) return;
          if (treeNodeReplayRequestVersionRef.current === replayRequest) {
            setTreeNodePositionOverride(position);
            setCurrentMove(clampMoveNumberToPositions(replayed, position.move_number));
          }
        } catch (error) {
          if (sgfTextEditVersionRef.current !== appliedVersion) return;
          setTreeNodePositionOverride(null);
          setCurrentMove(clampMoveNumberToPositions(replayed, selectedNode.move_number ?? replayed.at(-1)?.move_number ?? parsed.moves.length));
          replayWarning = ` Position replay failed: ${errorMessage(error)}`;
        }
      } else {
        clearTreeNodePositionOverride();
        setCurrentMove(clampMoveNumberToPositions(replayed, replayed.at(-1)?.move_number ?? parsed.moves.length));
      }

      setMessage(`Edited existing SGF move.${replayWarning}`);
    } catch (error) {
      setMessage(`Edit move failed: ${errorMessage(error)}`);
    } finally {
      setIsMoveAppending(false);
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  function handleMoveEditInput(vertex: MoveVertex) {
    if (sgfMoveEditMode === "edit") {
      void handleEditExistingMove(vertex);
      return;
    }
    void handleAppendMove(vertex);
  }

  async function handleDeleteSgfNode(nodeId: string) {
    if (!selectedSgfNodeId) {
      setMessage("Select an SGF tree node before deleting.");
      return;
    }
    if (nodeId !== selectedSgfNodeId) {
      setMessage("Delete cancelled because the selected SGF node changed.");
      return;
    }
    const node = sgfTree?.nodes.find((item) => item.id === nodeId) ?? null;
    if (!node) {
      setMessage("Delete failed: selected SGF node was not found in the current tree.");
      return;
    }
    if (node.id === sgfTree?.root_id || node.parent_id === null) {
      setMessage("Root SGF node cannot be deleted.");
      return;
    }
    if (isBusy) return;

    const sgfTreeRequest = beginSgfTreeLoad();
    const sourceVersion = sgfTextEditVersionRef.current;
    const sourceText = sgfText;
    setIsNodeDeleting(true);
    setMessage(`Deleting ${formatSgfNodeLabel(node)} from SGF...`);
    try {
      const result = normalizeDeleteSgfNodeResult(await callDeleteSgfNode(sourceText, nodeId));
      if (sgfTextEditVersionRef.current !== sourceVersion) {
        setMessage("Delete node cancelled because the SGF source changed while the edit was running.");
        return;
      }

      sgfTextEditVersionRef.current += 1;
      const appliedVersion = sgfTextEditVersionRef.current;
      setSgfText(result.sgfText);
      setDirty(true);
      clearReviewData();
      resetAnalysisCacheState();

      const [parsed, replayed, updatedTree] = await Promise.all([
        parseSgfSummary(result.sgfText),
        replaySgfPositions(result.sgfText),
        parseSgfTree(result.sgfText)
      ]);
      if (sgfTextEditVersionRef.current !== appliedVersion) return;

      const parentNode = applySgfTreeSelectedNode(updatedTree, result.parentNodeId, sgfTreeRequest)
        ?? selectSgfTreeNodeForMove(updatedTree, 0);
      setGame(parsed);
      setPositions(replayed);
      setSgfTreeError(null);
      setCommentDraft(parentNode?.comment ?? "");

      let replayWarning = "";
      if (parentNode) {
        try {
          const replayRequest = beginTreeNodeReplay();
          const position = await replaySgfPositionAtNode(result.sgfText, parentNode.id);
          if (sgfTextEditVersionRef.current !== appliedVersion) return;
          if (treeNodeReplayRequestVersionRef.current === replayRequest) {
            setTreeNodePositionOverride(position);
            setCurrentMove(clampMoveNumberToPositions(replayed, position.move_number));
          }
        } catch (error) {
          if (sgfTextEditVersionRef.current !== appliedVersion) return;
          setTreeNodePositionOverride(null);
          setCurrentMove(clampMoveNumberToPositions(replayed, parentNode.move_number ?? 0));
          replayWarning = ` Parent position replay failed: ${errorMessage(error)}`;
        }
      } else {
        clearTreeNodePositionOverride();
        setCurrentMove(0);
      }

      setMessage(`Deleted ${formatSgfNodeLabel(node)} and its subtree from SGF.${replayWarning}`);
    } catch (error) {
      setMessage(`Delete node failed: ${errorMessage(error)}`);
    } finally {
      setIsNodeDeleting(false);
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function handleReorderSgfVariation(nodeId: string, targetIndex: number) {
    if (!selectedSgfNodeId) {
      setMessage("Select an SGF tree node before reordering variations.");
      return;
    }
    if (nodeId !== selectedSgfNodeId) {
      setMessage("Reorder cancelled because the selected SGF node changed.");
      return;
    }
    const node = sgfTree?.nodes.find((item) => item.id === nodeId) ?? null;
    if (!node) {
      setMessage("Reorder failed: selected SGF node was not found in the current tree.");
      return;
    }
    if (node.id === sgfTree?.root_id || node.parent_id === null || node.parent_id === undefined) {
      setMessage("Root SGF node cannot be reordered.");
      return;
    }
    const parentNode = sgfTree?.nodes.find((item) => item.id === node.parent_id) ?? null;
    const siblingIds = parentNode?.child_ids ?? [];
    const currentIndex = siblingIds.indexOf(node.id);
    if (!parentNode || currentIndex < 0 || siblingIds.length < 2 || targetIndex < 0 || targetIndex >= siblingIds.length || targetIndex === currentIndex) {
      setMessage("Reorder skipped: selected node has no valid sibling target.");
      return;
    }
    if (isBusy) return;

    const sgfTreeRequest = beginSgfTreeLoad();
    const sourceVersion = sgfTextEditVersionRef.current;
    const sourceText = sgfText;
    setIsNodeReordering(true);
    setMessage(`Moving ${formatSgfNodeLabel(node)} to variation ${targetIndex + 1}...`);
    try {
      const result = normalizeReorderSgfVariationResult(await callReorderSgfVariation(sourceText, nodeId, targetIndex));
      if (sgfTextEditVersionRef.current !== sourceVersion) {
        setMessage("Reorder variation cancelled because the SGF source changed while the edit was running.");
        return;
      }

      sgfTextEditVersionRef.current += 1;
      const appliedVersion = sgfTextEditVersionRef.current;
      setSgfText(result.sgfText);
      setDirty(true);
      clearReviewData();
      resetAnalysisCacheState();

      const [parsed, replayed, updatedTree] = await Promise.all([
        parseSgfSummary(result.sgfText),
        replaySgfPositions(result.sgfText),
        parseSgfTree(result.sgfText)
      ]);
      if (sgfTextEditVersionRef.current !== appliedVersion) return;

      const selectedNode = applySgfTreeSelectedNode(updatedTree, result.nodeId, sgfTreeRequest)
        ?? selectSgfTreeNodeForMove(updatedTree, currentMove);
      setGame(parsed);
      setPositions(replayed);
      setSgfTreeError(null);
      setCommentDraft(selectedNode?.comment ?? "");

      let replayWarning = "";
      if (selectedNode) {
        try {
          const replayRequest = beginTreeNodeReplay();
          const position = await replaySgfPositionAtNode(result.sgfText, selectedNode.id);
          if (sgfTextEditVersionRef.current !== appliedVersion) return;
          if (treeNodeReplayRequestVersionRef.current === replayRequest) {
            setTreeNodePositionOverride(position);
            setCurrentMove(clampMoveNumberToPositions(replayed, position.move_number));
          }
        } catch (error) {
          if (sgfTextEditVersionRef.current !== appliedVersion) return;
          setTreeNodePositionOverride(null);
          setCurrentMove(clampMoveNumberToPositions(replayed, selectedNode.move_number ?? replayed.at(-1)?.move_number ?? parsed.moves.length));
          replayWarning = ` Position replay failed: ${errorMessage(error)}`;
        }
      } else {
        clearTreeNodePositionOverride();
        setCurrentMove(clampMoveNumberToPositions(replayed, replayed.at(-1)?.move_number ?? parsed.moves.length));
      }

      setMessage(`Moved ${selectedNode ? formatSgfNodeLabel(selectedNode) : formatSgfNodeLabel(node)} to sibling position ${targetIndex + 1}. Variation 1 is the mainline.${replayWarning}`);
    } catch (error) {
      setMessage(`Reorder variation failed: ${errorMessage(error)}`);
    } finally {
      setIsNodeReordering(false);
      finishSgfTreeLoad(sgfTreeRequest);
    }
  }

  async function refreshSgfTree(text: string, targetMove: number, showLoading = true) {
    const requestVersion = beginSgfTreeLoad(showLoading);
    try {
      applySgfTree(await parseSgfTree(text), targetMove, requestVersion);
    } catch (error) {
      failSgfTreeLoad(error, requestVersion);
    } finally {
      finishSgfTreeLoad(requestVersion, showLoading);
    }
  }

  function beginSgfTreeLoad(showLoading = true): number {
    const requestVersion = sgfTreeRequestVersionRef.current + 1;
    sgfTreeRequestVersionRef.current = requestVersion;
    if (showLoading) setIsSgfTreeLoading(true);
    return requestVersion;
  }

  function finishSgfTreeLoad(requestVersion: number | null, showLoading = true) {
    if (!showLoading || requestVersion === null) return;
    if (sgfTreeRequestVersionRef.current === requestVersion) setIsSgfTreeLoading(false);
  }

  function failSgfTreeLoad(error: unknown, requestVersion: number | null) {
    if (requestVersion !== null && sgfTreeRequestVersionRef.current !== requestVersion) return;
    setSgfTree(null);
    setSelectedSgfNodeId(null);
    setCommentDraft("");
    setSgfTreeError(errorMessage(error));
  }

  function applySgfTree(tree: SgfTreeDto | null, targetMove: number, requestVersion?: number | null) {
    if (requestVersion !== undefined && requestVersion !== null && sgfTreeRequestVersionRef.current !== requestVersion) return;
    setSgfTree(tree);
    setSgfTreeError(null);
    const selectedNode = selectSgfTreeNodeForMove(tree, targetMove);
    setSelectedSgfNodeId(selectedNode?.id ?? tree?.root_id ?? null);
    setCommentDraft(selectedNode?.comment ?? "");
    setAnnotationError(null);
  }

  function applySgfTreeSelectedNode(tree: SgfTreeDto | null, nodeId: string, requestVersion?: number | null): SgfTreeNodeDto | null {
    if (requestVersion !== undefined && requestVersion !== null && sgfTreeRequestVersionRef.current !== requestVersion) return null;
    setSgfTree(tree);
    setSgfTreeError(null);
    const selectedNode = tree?.nodes.find((node) => node.id === nodeId) ?? null;
    setSelectedSgfNodeId(selectedNode?.id ?? tree?.root_id ?? null);
    setCommentDraft(selectedNode?.comment ?? "");
    setAnnotationError(null);
    return selectedNode;
  }

  function syncSelectedSgfNodeToMove(moveNumber: number, sourceTree = sgfTree) {
    const selectedNode = selectSgfTreeNodeForMove(sourceTree, moveNumber);
    if (!selectedNode) return;
    setSelectedSgfNodeId(selectedNode.id);
    setCommentDraft(selectedNode.comment ?? "");
    setAnnotationError(null);
  }

  function beginTreeNodeReplay(): number {
    const requestVersion = treeNodeReplayRequestVersionRef.current + 1;
    treeNodeReplayRequestVersionRef.current = requestVersion;
    return requestVersion;
  }

  function clearTreeNodePositionOverride() {
    treeNodeReplayRequestVersionRef.current += 1;
    setTreeNodePositionOverride(null);
  }

  function nextAnalysisSessionToken(): string {
    analysisSessionCounterRef.current += 1;
    return `review-session-${analysisSessionCounterRef.current}`;
  }

  function setReviewWorkflowProgress(progress: AnalysisProgress) {
    setReviewWorkflowStatus((status) => ({
      ...status,
      phase: "running",
      source: "katago",
      activeJobId: progress.jobId,
      message: `Analyzing move ${progress.turn}: ${progress.completed}/${progress.expected || "?"} positions complete.`,
      completed: progress.completed,
      expected: progress.expected,
      currentTurn: progress.turn,
      progressVerified: true
    }));
  }

  function markStaleAnalysisPrevented(jobId: string) {
    setReviewWorkflowStatus((status) => ({
      ...status,
      staleAnalysisPrevented: true,
      message: status.phase === "running" || status.phase === "starting"
        ? `${status.message} Ignored stale event from ${jobId}.`
        : `Ignored stale analysis event from ${jobId}.`
    }));
  }

  function cleanupAnalysisListeners() {
    analysisCleanupRef.current?.();
    analysisCleanupRef.current = null;
  }

  function isCurrentAnalysisJob(jobId: string): boolean {
    return activeJobIdRef.current === jobId;
  }

  async function finishPendingAnalysisTerminalEvent(jobId: string, event: PendingAnalysisTerminalEvent, parsed: GameDto, replayed: PositionDto[]) {
    if (event.kind === "complete") {
      await finishCompletedAnalysis(jobId, event.frames, parsed, replayed);
      return;
    }
    finishStoppedAnalysis(jobId);
    setAnalysisProgress(null);
    if (event.kind === "error") {
      const message = engineFailureMessage(event.message);
      setReviewWorkflowStatus((status) => ({
        ...status,
        phase: "error",
        source: "katago",
        activeJobId: null,
        message,
        engineFailureVerified: true
      }));
      setMessage(message);
      return;
    }
    const message = event.message || "Full-game KataGo analysis cancelled. You can restart review when ready.";
    setReviewWorkflowStatus((status) => ({
      ...status,
      phase: "cancelled",
      source: "katago",
      activeJobId: null,
      message,
      cancelVerified: true
    }));
    setMessage(message);
  }

  async function finishCompletedAnalysis(jobId: string, result: AnalysisFrameDto[], parsed: GameDto, replayed: PositionDto[]) {
    const lastAnalyzedMove = result.at(-1)?.turn ?? replayed.at(-1)?.move_number ?? parsed.moves.length;
    const shownMove = clampMoveNumberToPositions(replayed, lastAnalyzedMove);
    const classified = await classifyProblems(result);
    setGame(parsed);
    setPositions(replayed);
    setFrames(result);
    setProblems(classified);
    setCurrentMove(shownMove);
    setSelectedCandidateIndex(null);
    clearTreeNodePositionOverride();
    setAnalysisProgress((progress) => progress ? { ...progress, completed: progress.expected || result.length, expected: progress.expected || result.length } : progress);
    finishStoppedAnalysis(jobId);
    const cacheMessage = await saveAnalysisCacheForGame(sgfText, currentFilePath, parsed, result, classified, "katago");
    setReviewWorkflowStatus((status) => ({
      ...status,
      phase: "completed",
      source: "katago",
      activeJobId: null,
      message: `Full-game KataGo analysis completed with ${result.length} frames.`,
      completed: result.length,
      expected: Math.max(status.expected, result.length),
      currentTurn: shownMove,
      progressVerified: true
    }));
    setMessage(`Full-game KataGo analysis completed with ${result.length} frames. Showing move ${shownMove}.${cacheMessage}`);
  }

  function finishStoppedAnalysis(jobId: string) {
    if (activeJobIdRef.current !== null && activeJobIdRef.current !== jobId) return;
    activeJobIdRef.current = null;
    setActiveJobId(null);
    setIsKataGoRunning(false);
    cleanupAnalysisListeners();
  }

  async function checkAnalysisCacheForGame(
    text: string,
    filePath: string | null,
    parsed: GameDto,
    replayed: PositionDto[],
    baseMessage: string,
    treeForSelection: SgfTreeDto | null = sgfTree
  ) {
    if (!preferences.autoLoadCache) {
      resetAnalysisCacheState();
      setMessage(`${baseMessage} Cache auto-load is off.`);
      return;
    }
    setCacheStatus("checking");
    setCacheRecord(null);
    setCacheError(null);
    try {
      const key = await computeGameCacheKey(text, filePath);
      setCurrentCacheKey(key);
      const lookup = await loadPreferredAnalysisCache(key.gameKey);
      if (lookup.status === "hit") {
        const payload = cachedAnalysisPayload(lookup.record.payload);
        if (!payload) {
          setCacheStatus("error");
          setCacheRecord(lookup.record);
          setCacheError("Cached payload is not compatible with this app version.");
          setMessage(`${baseMessage} ${cacheEngineLabel(lookup.engineKind)} cache hit, but the payload could not be restored.`);
          return;
        }
        setFrames(payload.frames);
        setProblems(payload.problems);
        const cachedMove = clampMoveNumberToPositions(replayed, payload.frames.at(-1)?.turn ?? parsed.moves.length);
        setCurrentMove(cachedMove);
        setSelectedCandidateIndex(null);
        setAnalysisProgress(null);
        setIsKataGoRunning(false);
        syncSelectedSgfNodeToMove(cachedMove, treeForSelection);
        setCacheStatus("hit");
        setCacheRecord(lookup.record);
        setReviewWorkflowStatus((status) => ({
          ...status,
          phase: "cache-restored",
          source: "cache",
          activeJobId: null,
          message: `Restored ${payload.frames.length} cached ${cacheEngineLabel(lookup.engineKind)} review frames.`,
          completed: payload.frames.length,
          expected: payload.frames.length,
          currentTurn: cachedMove,
          cacheRestoreVerified: true
        }));
        setMessage(`${baseMessage} Restored ${payload.frames.length} cached ${cacheEngineLabel(lookup.engineKind)} review frames.`);
        return;
      }
      if (lookup.status === "error") {
        setCacheStatus("error");
        setCacheRecord(null);
        setCacheError(lookup.message);
        setMessage(`${baseMessage} Cache unavailable: ${lookup.message}`);
        return;
      }
      setCacheStatus("miss");
      setCacheRecord(null);
      setMessage(`${baseMessage} No cached review yet.`);
    } catch (error) {
      const message = errorMessage(error);
      setCacheStatus("error");
      setCacheRecord(null);
      setCacheError(message);
      setCurrentCacheKey(null);
      setMessage(`${baseMessage} Cache unavailable: ${message}`);
    }
  }

  async function loadPreferredAnalysisCache(gameKey: string): Promise<AnalysisCacheLoadResult> {
    const katagoLookup = await loadAnalysisCache(gameKey, null, "katago");
    if (katagoLookup.status === "hit" && katagoLookup.record) return { status: "hit", record: katagoLookup.record, engineKind: "katago" };
    if (katagoLookup.status === "error") return { status: "error", message: katagoLookup.error ?? "KataGo cache lookup failed." };

    const fakeLookup = await loadAnalysisCache(gameKey, null, "fake");
    if (fakeLookup.status === "hit" && fakeLookup.record) return { status: "hit", record: fakeLookup.record, engineKind: "fake" };
    if (fakeLookup.status === "error") return { status: "error", message: fakeLookup.error ?? "Fake review cache lookup failed." };

    return { status: "miss" };
  }

  async function saveAnalysisCacheForGame(
    text: string,
    filePath: string | null,
    parsed: GameDto,
    analysisFrames: AnalysisFrameDto[],
    analysisProblems: ProblemMarkerDto[],
    engineKind: CacheEngineKind
  ): Promise<string> {
    if (!preferences.autoSaveAnalysis) {
      setCacheStatus("idle");
      return " Cache auto-save is off.";
    }
    setCacheStatus("saving");
    setCacheError(null);
    try {
      const key = currentCacheKey ?? await computeGameCacheKey(text, filePath);
      setCurrentCacheKey(key);
      const payload = { frames: analysisFrames, problems: analysisProblems } as unknown as JsonValue;
      const saved = await saveAnalysisCache({
        gameKey: key.gameKey,
        sgfHash: key.sgfHash,
        profileId: null,
        engineKind,
        source: engineKind,
        moveCount: parsed.summary.move_count,
        analyzedMoveCount: countAnalyzedMoves(analysisFrames, parsed.summary.move_count),
        payload
      });
      const record: AnalysisCacheRecord = {
        id: saved.id,
        gameKey: saved.gameKey,
        sgfHash: key.sgfHash,
        profileId: null,
        engineKind,
        source: engineKind,
        moveCount: parsed.summary.move_count,
        analyzedMoveCount: countAnalyzedMoves(analysisFrames, parsed.summary.move_count),
        payload,
        createdAt: saved.updatedAt,
        updatedAt: saved.updatedAt
      };
      setCacheStatus("saved");
      setCacheRecord(record);
      return " Cache saved.";
    } catch (error) {
      const message = errorMessage(error);
      setCacheStatus("error");
      setCacheError(message);
      return ` Cache save failed: ${message}`;
    }
  }

  function resetAnalysisCacheState() {
    setCacheStatus("idle");
    setCacheRecord(null);
    setCacheError(null);
    setCurrentCacheKey(null);
  }

  function clearReviewData() {
    setFrames([]);
    setProblems([]);
    setSelectedCandidateIndex(null);
    setAnalysisProgress(null);
    setCacheRecord(null);
  }

  async function callAppendSgfMove(sgfText: string, parentNodeId: string, color: PlayerColor, vertex: MoveVertex): Promise<unknown> {
    const appendSgfMove = (backendApi as unknown as { appendSgfMove?: AppendSgfMove }).appendSgfMove;
    if (!appendSgfMove) {
      throw new Error("appendSgfMove is not available yet. Bridge/Core needs to expose the SGF append API.");
    }
    return await appendSgfMove(sgfText, parentNodeId, color, vertex);
  }

  async function callEditSgfMove(sgfText: string, nodeId: string, color: PlayerColor, vertex: MoveVertex): Promise<unknown> {
    const editSgfMove = (backendApi as unknown as { editSgfMove?: EditSgfMove }).editSgfMove;
    if (!editSgfMove) {
      throw new Error("editSgfMove is not available yet. Bridge/Core needs to expose the SGF edit API.");
    }
    return await editSgfMove(sgfText, nodeId, color, vertex);
  }

  async function callDeleteSgfNode(sgfText: string, nodeId: string): Promise<unknown> {
    const deleteSgfNode = (backendApi as unknown as { deleteSgfNode?: DeleteSgfNode }).deleteSgfNode;
    if (!deleteSgfNode) {
      throw new Error("deleteSgfNode is not available yet. Bridge/Core needs to expose the SGF delete API.");
    }
    return await deleteSgfNode(sgfText, nodeId);
  }

  async function callReorderSgfVariation(sgfText: string, nodeId: string, targetIndex: number): Promise<unknown> {
    const reorderSgfVariation = (backendApi as unknown as { reorderSgfVariation?: ReorderSgfVariation }).reorderSgfVariation;
    if (!reorderSgfVariation) {
      throw new Error("reorderSgfVariation is not available yet. Bridge/Core needs to expose the SGF reorder API.");
    }
    return await reorderSgfVariation(sgfText, nodeId, targetIndex);
  }

  const sgfTreeDeleteProps = {
    onDeleteNode: (nodeId: string) => void handleDeleteSgfNode(nodeId),
    isNodeDeleting,
    canDelete: canDeleteSgfNode
  };

  const sgfTreeReorderProps = {
    onReorderNode: (nodeId: string, targetIndex: number) => void handleReorderSgfVariation(nodeId, targetIndex),
    isNodeReordering,
    canReorder: !isBusy
  };
  const runtimeSource = backendApi.frontendRuntimeSource();
  const tauriRuntimeObserved = runtimeSource === "tauri";
  const backendAvailability = health === null
    ? "checking"
    : tauriRuntimeObserved && health.rust_backend_ready
      ? "available"
      : tauriRuntimeObserved
        ? "tauri-backend-unavailable"
        : "browser-fallback";
  const backendAvailable = backendAvailability === "available";
  const sgfWorkflowState = sgfTreeError
    ? "parse-error"
    : isSgfTreeLoading
      ? "loading-tree"
      : dirty
        ? "dirty"
        : currentFilePath
          ? "opened-saved"
          : fallbackFileName
            ? "imported"
            : sgfTree
              ? "sample-ready"
              : "source-editing";
  const sgfWorkflowLabel = sgfTreeError
    ? `SGF error: ${sgfTreeError}`
    : `${documentName}: ${game.summary.move_count} moves, move ${currentMove}, ${dirty ? "unsaved" : "saved"}.`;

  return (
    <LegacyShell
      themeClassName={preferences.boardTheme === "high-contrast" ? "theme-high-contrast" : ""}
      architectureLabel={health?.architecture ?? "Tauri 2 + React review workspace"}
      backendStatusLabel={health?.rust_backend_ready ? "Rust backend ready" : "Browser fallback"}
      cacheBadge={
        <CacheStatusBadge
          status={cacheStatus}
          record={cacheRecord}
          error={cacheError}
          cacheRestoreVerified={reviewWorkflowStatus.cacheRestoreVerified}
        />
      }
      board={
        <BoardCanvas
          position={currentPosition}
          analysis={visibleCurrentFrame}
          selectedCandidateIndex={selectedCandidateIndex}
          canEdit={!isBusy && selectedSgfNodeId !== null}
          editColor={editColor}
          onPlayPoint={(point) => handleMoveEditInput({ point })}
        />
      }
      chart={
        <WinrateChart
          frames={frames}
          currentMove={currentMove}
          reviewSource={reviewWorkflowStatus.source}
          reviewPhase={reviewWorkflowStatus.phase}
          cacheRestoreVerified={reviewWorkflowStatus.cacheRestoreVerified}
        />
      }
      analysisPanel={
        <div className="legacy-review-stack">
          <AnalysisPanel
            frame={visibleCurrentFrame}
            problems={problems}
            boardSize={game.summary.board_size}
            currentMove={currentMove}
            selectedCandidateIndex={selectedCandidateIndex}
            onSelectCandidate={setSelectedCandidateIndex}
            onSelectProblem={handleMoveSelect}
            reviewSource={reviewWorkflowStatus.source}
            reviewPhase={reviewWorkflowStatus.phase}
            cacheRestoreVerified={reviewWorkflowStatus.cacheRestoreVerified}
          />
          <SgfTreePanelWithMoveEdit
            tree={sgfTree}
            selectedNodeId={selectedSgfNodeId}
            currentMove={currentMove}
            boardSize={game.summary.board_size}
            isLoading={isSgfTreeLoading}
            parseError={sgfTreeError}
            commentDraft={commentDraft}
            onCommentDraftChange={setCommentDraft}
            onSelectNode={(nodeId) => void handleSgfTreeNodeSelect(nodeId)}
            onSaveComment={(nodeId, comment) => void handleSaveComment(nodeId, comment)}
            onSaveProperties={(nodeId, updates) => void handleSaveProperties(nodeId, updates)}
            onSaveAnnotations={(nodeId, updates) => void handleSaveAnnotations(nodeId, updates)}
            isCommentSaving={isCommentSaving}
            isPropertySaving={isPropertySaving}
            isAnnotationSaving={isAnnotationSaving}
            annotationError={annotationError}
            commentActionLabel="Save Comment"
            commentNote="Saving writes the selected node comment into the SGF source text. Branch positions can be displayed; analysis remains mainline/current cache unless re-run."
            moveEditMode={sgfMoveEditMode}
            canEditSelectedMove={canEditSelectedMove}
            onMoveEditModeChange={setSgfMoveEditMode}
            onEditSelectedMovePass={() => void handleEditExistingMove("pass")}
            {...sgfTreeDeleteProps}
            {...sgfTreeReorderProps}
          />
        </div>
      }
      providerPanel={
        <div className="sgf-edit-provider-stack">
          <section className="sgf-edit-panel" aria-label="SGF move editing" data-testid="sgf-move-edit-panel">
            <div className="sgf-edit-header">
              <strong>{sgfMoveEditMode === "append" ? "Append move" : "Edit move"}</strong>
              <span>{colorLabel(editColor)} {sgfMoveEditMode === "append" ? "to play" : "move"}</span>
            </div>
            <div className="sgf-edit-controls" aria-label="Move edit mode">
              <button type="button" data-testid="sgf-move-mode-append" aria-pressed={sgfMoveEditMode === "append"} disabled={isBusy} onClick={() => setSgfMoveEditMode("append")}>Append</button>
              <button type="button" data-testid="sgf-move-mode-edit" aria-pressed={sgfMoveEditMode === "edit"} disabled={isBusy} onClick={() => setSgfMoveEditMode("edit")}>Edit</button>
            </div>
            <div className="sgf-edit-controls" aria-label="Move color">
              <button type="button" data-testid="sgf-move-color-black" aria-pressed={editColor === "black"} disabled={isBusy} onClick={() => setEditColor("black")}>B</button>
              <button type="button" data-testid="sgf-move-color-white" aria-pressed={editColor === "white"} disabled={isBusy} onClick={() => setEditColor("white")}>W</button>
              <button type="button" data-testid="sgf-move-pass" disabled={isBusy || selectedSgfNodeId === null} onClick={() => handleMoveEditInput("pass")}>Pass</button>
            </div>
          </section>
          <ProviderPanel disabled={isBusy} onImport={handleProviderImport} />
        </div>
      }
      enginePanel={
        <>
          <section
            className="analysis-progress"
            aria-label="Installed app runtime proof"
            data-testid="installed-app-runtime-proof"
            data-runtime-source={runtimeSource}
            data-tauri-runtime-observed={String(tauriRuntimeObserved)}
            data-browser-fallback-used={String(!tauriRuntimeObserved)}
            data-backend-availability={backendAvailability}
            data-backend-available={String(backendAvailable)}
            data-sgf-workflow-state={sgfWorkflowState}
            data-sgf-tree-loaded={String(Boolean(sgfTree))}
            data-sgf-tree-loading={String(isSgfTreeLoading)}
            data-sgf-tree-error={sgfTreeError ?? ""}
            data-sgf-current-move={currentMove}
            data-sgf-max-move={maxMove}
            data-sgf-dirty={String(dirty)}
            data-native-dialog-action={nativeSgfDialogWorkflow.action}
            data-native-dialog-status={nativeSgfDialogWorkflow.status}
            data-native-dialog-source={nativeSgfDialogWorkflow.source}
            data-native-dialog-path={nativeSgfDialogDataPath}
            data-native-dialog-readback-verified={String(nativeSgfDialogWorkflow.readbackVerified)}
            data-native-dialog-reparse-verified={String(nativeSgfDialogWorkflow.reparseVerified)}
            data-native-dialog-dirty-after={String(nativeSgfDialogWorkflow.dirtyAfter)}
          >
            <strong data-testid="runtime-source" data-runtime-source={runtimeSource}>
              {tauriRuntimeObserved ? "Tauri runtime" : "Browser preview"}
            </strong>
            <span data-testid="backend-availability" data-backend-availability={backendAvailability}>
              {backendAvailable ? "Backend available" : tauriRuntimeObserved ? "Backend unavailable" : "Browser fallback, no Tauri backend"}
            </span>
            <span data-testid="sgf-workflow-state" data-sgf-workflow-state={sgfWorkflowState}>
              {sgfWorkflowLabel}
            </span>
            <span
              data-testid="native-dialog-sgf-workflow-state"
              data-native-dialog-action={nativeSgfDialogWorkflow.action}
              data-native-dialog-status={nativeSgfDialogWorkflow.status}
              data-native-dialog-source={nativeSgfDialogWorkflow.source}
              data-native-dialog-path={nativeSgfDialogDataPath}
              data-native-dialog-readback-verified={String(nativeSgfDialogWorkflow.readbackVerified)}
              data-native-dialog-reparse-verified={String(nativeSgfDialogWorkflow.reparseVerified)}
              data-native-dialog-dirty-after={String(nativeSgfDialogWorkflow.dirtyAfter)}
            >
              {nativeSgfDialogWorkflow.message}
            </span>
          </section>
          <EngineSetupPanel
            disabled={isBusy}
            onRun={handleRunKataGo}
            onAnalyzeGame={handleAnalyzeKataGoGame}
            onCancelAnalysis={handleCancelKataGoAnalysis}
            analysisProgress={analysisProgress}
            activeJobId={activeJobId}
            reviewWorkflow={reviewWorkflowStatus}
          />
        </>
      }
      preferencesPanel={
        <PreferencesPanel
          preferences={preferences}
          status={preferencesStatus}
          disabled={isBusy}
          onChange={(nextPreferences) => void handlePreferencesChange(nextPreferences)}
          legacyConfigPath={legacyConfigPath}
          legacyConfigStatus={legacyConfigStatus}
          legacyConfigPreview={legacyConfigPreview}
          legacyConfigApplyResult={legacyConfigApplyResult}
          isLegacyConfigMigrating={isLegacyConfigMigrating}
          onLegacyConfigPathChange={handleLegacyConfigPathChange}
          onPreviewLegacyConfigMigration={() => void handlePreviewLegacyConfigMigration()}
          onApplyLegacyConfigMigration={() => void handleApplyLegacyConfigMigration()}
        />
      }
      documentName={documentName}
      documentTitle={currentFilePath ?? documentName}
      dirty={dirty}
      sgfText={sgfText}
      currentMove={currentMove}
      maxMove={maxMove}
      message={message}
      isBusy={isBusy}
      canSave={dirty}
      onOpen={handleOpenSgfDocument}
      onSave={() => handleSaveSgfDocument(false)}
      onSaveAs={() => handleSaveSgfDocument(true)}
      onImportFile={handleImportFile}
      onLoadSample={loadSample}
      onParseSgf={handleParseSgf}
      onRunReview={handleFakeAnalyze}
      onSgfTextChange={(value) => {
        sgfTextEditVersionRef.current += 1;
        sgfTreeRequestVersionRef.current += 1;
        setSgfText(value);
        setDirty(true);
        clearTreeNodePositionOverride();
        clearReviewData();
        resetAnalysisCacheState();
        setIsSgfTreeLoading(false);
        setSgfTree(null);
        setSelectedSgfNodeId(null);
        setCommentDraft("");
        setSgfTreeError(null);
        setCurrentMove(0);
        setMessage("SGF edited. Parse SGF or run review to refresh.");
      }}
      onMoveChange={handleMoveSelect}
    />
  );
}

function applyPreferencesToFrame(frame: AnalysisFrameDto | undefined, preferences: AppPreferences): AnalysisFrameDto | undefined {
  if (!frame) return undefined;
  return {
    ...frame,
    candidates: preferences.showCandidates ? frame.candidates.slice(0, preferences.candidateLimit) : [],
    ownership: preferences.showOwnership ? frame.ownership : null,
    policy: preferences.showPolicy ? frame.policy : null
  };
}

function resolveAnalysisMaxVisits(requestedMaxVisits: number | null | undefined, preferences: AppPreferences): number {
  if (typeof requestedMaxVisits === "number" && Number.isFinite(requestedMaxVisits) && requestedMaxVisits > 0) {
    return Math.floor(requestedMaxVisits);
  }
  return preferences.reviewMode === "deep" ? preferences.defaultMaxVisits * 2 : preferences.defaultMaxVisits;
}

function cachedAnalysisPayload(payload: JsonValue): CachedAnalysisPayload | null {
  if (!isJsonObject(payload)) return null;
  if (!Array.isArray(payload.frames) || !Array.isArray(payload.problems)) return null;
  return {
    frames: payload.frames as unknown as AnalysisFrameDto[],
    problems: payload.problems as unknown as ProblemMarkerDto[]
  };
}

function isJsonObject(value: JsonValue): value is { [key: string]: JsonValue } {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function mergeAnalysisFrame(frames: AnalysisFrameDto[], frame: AnalysisFrameDto): AnalysisFrameDto[] {
  return [...frames.filter((item) => item.turn !== frame.turn), frame].sort((a, b) => a.turn - b.turn);
}

function countAnalyzedMoves(frames: AnalysisFrameDto[], moveCount: number): number {
  const turns = new Set(frames.map((frame) => frame.turn).filter((turn) => turn > 0 && turn <= moveCount));
  return turns.size;
}

function selectSgfTreeNodeForMove(tree: SgfTreeDto | null, moveNumber: number): SgfTreeNodeDto | null {
  if (!tree) return null;
  if (moveNumber <= 0) return tree.nodes.find((node) => node.id === tree.root_id) ?? null;
  const candidates = tree.nodes.filter((node) => node.move_number === moveNumber);
  return candidates.find((node) => node.is_mainline) ?? candidates[0] ?? null;
}

function formatSgfNodeLabel(node: SgfTreeNodeDto): string {
  if (node.move_number === null || node.move_number === undefined) return "root";
  const line = node.is_mainline ? "mainline" : `variation ${node.variation_index + 1}`;
  return `${line} move ${node.move_number}`;
}

function normalizeAppendSgfMoveResult(result: unknown): { sgfText: string; newNodeId: string } {
  if (!isUnknownRecord(result)) throw new Error("appendSgfMove returned an invalid response.");
  const sgfText = typeof result.sgfText === "string" ? result.sgfText : typeof result.sgf_text === "string" ? result.sgf_text : null;
  const newNodeId = typeof result.newNodeId === "string" ? result.newNodeId : typeof result.new_node_id === "string" ? result.new_node_id : null;
  if (!sgfText || !newNodeId) throw new Error("appendSgfMove response must include sgfText and newNodeId.");
  return { sgfText, newNodeId };
}

function normalizeEditSgfMoveResult(result: unknown): { sgfText: string; nodeId: string } {
  if (!isUnknownRecord(result)) throw new Error("editSgfMove returned an invalid response.");
  const sgfText = typeof result.sgfText === "string" ? result.sgfText : typeof result.sgf_text === "string" ? result.sgf_text : null;
  const nodeId = typeof result.nodeId === "string" ? result.nodeId : typeof result.node_id === "string" ? result.node_id : null;
  if (!sgfText || !nodeId) throw new Error("editSgfMove response must include sgfText and nodeId.");
  return { sgfText, nodeId };
}

function normalizeDeleteSgfNodeResult(result: unknown): { sgfText: string; parentNodeId: string } {
  if (!isUnknownRecord(result)) throw new Error("deleteSgfNode returned an invalid response.");
  const sgfText = typeof result.sgfText === "string" ? result.sgfText : typeof result.sgf_text === "string" ? result.sgf_text : null;
  const parentNodeId = typeof result.parentNodeId === "string"
    ? result.parentNodeId
    : typeof result.parent_node_id === "string"
      ? result.parent_node_id
      : null;
  if (!sgfText || !parentNodeId) throw new Error("deleteSgfNode response must include sgfText and parentNodeId.");
  return { sgfText, parentNodeId };
}

function normalizeReorderSgfVariationResult(result: unknown): { sgfText: string; nodeId: string; parentNodeId: string } {
  if (!isUnknownRecord(result)) throw new Error("reorderSgfVariation returned an invalid response.");
  const sgfText = typeof result.sgfText === "string" ? result.sgfText : typeof result.sgf_text === "string" ? result.sgf_text : null;
  const nodeId = typeof result.nodeId === "string" ? result.nodeId : typeof result.node_id === "string" ? result.node_id : null;
  const parentNodeId = typeof result.parentNodeId === "string"
    ? result.parentNodeId
    : typeof result.parent_node_id === "string"
      ? result.parent_node_id
      : null;
  if (!sgfText || !nodeId || !parentNodeId) throw new Error("reorderSgfVariation response must include sgfText, nodeId, and parentNodeId.");
  return { sgfText, nodeId, parentNodeId };
}

function isUnknownRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function colorLabel(color: PlayerColor): string {
  return color === "black" ? "Black" : "White";
}

function nativeSaveWorkflowSource(
  saveAs: boolean,
  currentFilePath: string | null,
  tauriRuntimeObserved: boolean
): NativeSgfDialogWorkflow["source"] {
  if (!tauriRuntimeObserved) return "browser-fallback";
  return saveAs || !currentFilePath ? "native-dialog" : "native-backend";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function engineFailureMessage(error: unknown): string {
  return `KataGo analysis failed: ${errorMessage(error)}. Check the engine, model, config paths, run Check assets, then start again.`;
}

function legacyConfigApplyFailureSummary(result: backendApi.LegacyConfigMigrationApplyDto): string {
  const reason = result.errorMessage?.trim() || "legacy config migration failed";
  const noWrite = result.noWriteOnError ? "no writes performed on error" : "write state may require inspection";
  const rollback = result.rollbackPerformed
    ? result.rollbackSucceeded
      ? "rollback succeeded"
      : "rollback failed"
    : "rollback not needed";
  return `${reason}; ${noWrite}; ${rollback}.`;
}

function legacyConfigApplySuccessSummary(result: backendApi.LegacyConfigMigrationApplyDto): string {
  const transactional = result.transactional ? "transactional apply" : "non-transactional apply";
  const writtenCount = result.writtenPathLabels.length;
  const written = writtenCount === 1 ? "1 target written" : `${writtenCount} targets written`;
  return `${transactional}; ${written}.`;
}

function cacheEngineLabel(engineKind: CacheEngineKind): string {
  return engineKind === "katago" ? "KataGo" : "fake";
}

function fileNameFromPath(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}
