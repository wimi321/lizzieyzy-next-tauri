import { useEffect, useMemo, useRef, useState } from "react";
import { BoardCanvas } from "./components/BoardCanvas";
import { WinrateChart } from "./components/WinrateChart";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { EngineSetupPanel } from "./components/EngineSetupPanel";
import { CacheStatusBadge } from "./components/CacheStatusBadge";
import { PreferencesPanel } from "./components/PreferencesPanel";
import { ProviderPanel } from "./components/ProviderPanel";
import {
  analyzeKataGoOnce,
  cancelKataGoAnalysis,
  classifyProblems,
  fakeAnalyze,
  getHealth,
  listenToKataGoAnalysisEvents,
  openSgfDocument,
  parseSgfSummary,
  replaySgfPositions,
  saveSgfDocument,
  startKataGoGameAnalysis
} from "./api/backend";
import { computeGameCacheKey, loadAnalysisCache, saveAnalysisCache } from "./api/analysisCache";
import { loadAppPreferences, saveAppPreferences } from "./api/preferences";
import { clampMoveNumberToPositions, createDemoGame, replayGamePositions, selectExactPosition } from "./domain/board";
import type { AnalysisCacheRecord, CacheStatus, GameCacheKey, JsonValue } from "./domain/cache";
import { defaultAppPreferences, normalizeAppPreferences, type AppPreferences } from "./domain/preferences";
import { providerDocumentName, providerLabel, providerSourceLabel, type ProviderImportResult } from "./domain/providers";
import type { AnalysisFrameDto, AppHealthDto, EngineProfileDto, GameDto, PositionDto, ProblemMarkerDto } from "./domain/types";

const demoSgf = "(;GM[1]FF[4]SZ[19]KM[7.5]PB[Lee Changho]PW[Rui Naiwei]RE[B+R];B[pd];W[dd];B[pp];W[dp];B[jq];W[qj];B[nc];W[fc];B[qf];W[cn];B[cp];W[do];B[co];W[dn];B[fq];W[eq];B[fp];W[gp];B[gq];W[hp])";
const demoGame = createDemoGame();
type AnalysisProgress = { jobId: string; completed: number; expected: number; turn: number; responseJsonl: string };
type PendingAnalysisTerminalEvent =
  | { kind: "complete"; frames: AnalysisFrameDto[] }
  | { kind: "error" | "cancelled"; message: string };
type CacheEngineKind = "fake" | "katago";
type CachedAnalysisPayload = { frames: AnalysisFrameDto[]; problems: ProblemMarkerDto[] };
type PendingPreferencesSave = { version: number; preferences: AppPreferences };
type AnalysisCacheLoadResult =
  | { status: "hit"; record: AnalysisCacheRecord; engineKind: CacheEngineKind }
  | { status: "miss" }
  | { status: "error"; message: string };

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
  const [preferences, setPreferences] = useState<AppPreferences>(() => defaultAppPreferences);
  const [preferencesStatus, setPreferencesStatus] = useState("Loading preferences...");
  const activeJobIdRef = useRef<string | null>(null);
  const startingAnalysisRef = useRef(false);
  const userChangedPreferencesRef = useRef(false);
  const preferencesSaveInFlightRef = useRef(false);
  const preferencesSaveVersionRef = useRef(0);
  const pendingPreferencesSaveRef = useRef<PendingPreferencesSave | null>(null);
  const pendingAnalysisProgressRef = useRef<Map<string, AnalysisProgress>>(new Map());
  const pendingAnalysisTerminalEventsRef = useRef<Map<string, PendingAnalysisTerminalEvent>>(new Map());
  const analysisCleanupRef = useRef<(() => void) | null>(null);

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

  const currentFrame = useMemo(() => frames.find((f) => f.turn === currentMove) ?? frames.at(-1), [frames, currentMove]);
  const visibleCurrentFrame = useMemo(() => applyPreferencesToFrame(currentFrame, preferences), [currentFrame, preferences]);
  const currentPosition = useMemo(() => selectExactPosition(positions, currentMove, game.summary.board_size), [positions, currentMove, game.summary.board_size]);
  const maxMove = Math.max(positions.at(-1)?.move_number ?? 0, 1);
  const documentName = useMemo(() => currentFilePath ? fileNameFromPath(currentFilePath) : fallbackFileName ?? "Untitled SGF", [currentFilePath, fallbackFileName]);
  const saveFileName = documentName.toLowerCase().endsWith(".sgf") ? documentName : `${documentName}.sgf`;

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

  async function handleParseSgf() {
    try {
      const [parsed, replayed] = await Promise.all([parseSgfSummary(sgfText), replaySgfPositions(sgfText)]);
      const loadedMessage = `Loaded ${parsed.summary.black_name ?? "Black"} vs ${parsed.summary.white_name ?? "White"}: ${parsed.summary.move_count} moves.`;
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(replayed.at(-1)?.move_number ?? parsed.moves.length);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      setMessage(loadedMessage);
      await checkAnalysisCacheForGame(sgfText, currentFilePath, parsed, replayed, loadedMessage);
    } catch (error) {
      clearReviewData();
      resetAnalysisCacheState();
      setCurrentMove(0);
      setMessage(`Parse failed: ${errorMessage(error)}`);
    }
  }

  async function handleOpenSgfDocument() {
    if (dirty && !window.confirm("Discard unsaved SGF changes and open another file?")) return;
    try {
      const document = await openSgfDocument();
      if (!document) {
        setMessage("Native Open is unavailable here. Use Import SGF in browser preview.");
        return;
      }
      setSgfText(document.sgfText);
      setCurrentFilePath(document.path);
      setFallbackFileName(null);
      setDirty(false);
      const [parsed, replayed] = await Promise.all([parseSgfSummary(document.sgfText), replaySgfPositions(document.sgfText)]);
      const openedMessage = `Opened ${fileNameFromPath(document.path ?? "SGF")}: ${parsed.summary.move_count} moves.`;
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(replayed.at(-1)?.move_number ?? parsed.moves.length);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      setMessage(openedMessage);
      await checkAnalysisCacheForGame(document.sgfText, document.path, parsed, replayed, openedMessage);
    } catch (error) {
      setMessage(`Open failed: ${errorMessage(error)}`);
    }
  }

  async function handleSaveSgfDocument(saveAs = false) {
    try {
      const saved = await saveSgfDocument(saveAs ? null : currentFilePath, sgfText, saveFileName);
      if (!saved) {
        setMessage("Save cancelled.");
        return;
      }
      setCurrentFilePath(saved.path);
      setDirty(false);
      setMessage(`Saved ${saved.path ? fileNameFromPath(saved.path) : saveFileName}.`);
    } catch (error) {
      setMessage(`Save failed: ${errorMessage(error)}`);
    }
  }

  async function handleFakeAnalyze() {
    try {
      const [parsed, result, replayed] = await Promise.all([parseSgfSummary(sgfText), fakeAnalyze(sgfText), replaySgfPositions(sgfText)]);
      const classified = await classifyProblems(result);
      setGame(parsed);
      setPositions(replayed);
      setFrames(result);
      setProblems(classified);
      setCurrentMove(replayed.at(-1)?.move_number ?? parsed.moves.length);
      setSelectedCandidateIndex(null);
      const cacheMessage = await saveAnalysisCacheForGame(sgfText, currentFilePath, parsed, result, classified, "fake");
      setMessage(`Generated ${result.length} review frames with candidate moves and winrate history.${cacheMessage}`);
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }

  async function handleRunKataGo(profile: EngineProfileDto, maxVisits: number) {
    const targetTurn = currentMove;
    const visits = resolveAnalysisMaxVisits(maxVisits, preferences);
    setIsKataGoRunning(true);
    setMessage(`Running KataGo analysis for move ${targetTurn}...`);
    try {
      const [parsed, replayed] = await Promise.all([parseSgfSummary(sgfText), replaySgfPositions(sgfText)]);
      const turn = clampMoveNumberToPositions(replayed, Math.min(targetTurn, replayed.at(-1)?.move_number ?? parsed.moves.length));
      const frame = await analyzeKataGoOnce(profile, sgfText, turn, visits);
      const mergedFrames = mergeAnalysisFrame(frames, frame);
      setGame(parsed);
      setPositions(replayed);
      setFrames(mergedFrames);
      setProblems(await classifyProblems(mergedFrames));
      setCurrentMove(frame.turn);
      setSelectedCandidateIndex(null);
      setMessage(`KataGo analysis completed for move ${frame.turn} with ${frame.visits} visits.`);
    } catch (error) {
      setMessage(`KataGo analysis failed: ${errorMessage(error)}`);
    } finally {
      setIsKataGoRunning(false);
    }
  }

  async function handleAnalyzeKataGoGame(profile: EngineProfileDto, maxVisits: number) {
    if (activeJobIdRef.current || startingAnalysisRef.current) return;
    const visits = resolveAnalysisMaxVisits(maxVisits, preferences);
    startingAnalysisRef.current = true;
    pendingAnalysisProgressRef.current.clear();
    pendingAnalysisTerminalEventsRef.current.clear();
    setIsKataGoRunning(true);
    setAnalysisProgress(null);
    setMessage("Starting full-game KataGo analysis...");
    let cleanup: (() => void) | null = null;
    try {
      const [parsed, replayed] = await Promise.all([parseSgfSummary(sgfText), replaySgfPositions(sgfText)]);
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
          if (!isCurrentAnalysisJob(payload.job_id)) return;
          setAnalysisProgress({
            jobId: payload.job_id,
            completed: payload.completed,
            expected: payload.expected,
            turn: payload.turn,
            responseJsonl: payload.response_jsonl
          });
          setMessage(`Analyzing move ${payload.turn}: ${payload.completed}/${payload.expected} positions complete.`);
        },
        onComplete: (payload) => {
          if (startingAnalysisRef.current && activeJobIdRef.current === null) {
            pendingAnalysisTerminalEventsRef.current.set(payload.job_id, { kind: "complete", frames: payload.frames });
            return;
          }
          if (!isCurrentAnalysisJob(payload.job_id)) return;
          void finishCompletedAnalysis(payload.job_id, payload.frames, parsed, replayed);
        },
        onError: (payload) => {
          if (startingAnalysisRef.current && activeJobIdRef.current === null) {
            pendingAnalysisTerminalEventsRef.current.set(payload.job_id, { kind: "error", message: payload.message });
            return;
          }
          if (!isCurrentAnalysisJob(payload.job_id)) return;
          finishStoppedAnalysis(payload.job_id);
          setMessage(`Full-game KataGo analysis failed: ${payload.message}`);
        },
        onCancelled: (payload) => {
          if (startingAnalysisRef.current && activeJobIdRef.current === null) {
            pendingAnalysisTerminalEventsRef.current.set(payload.job_id, { kind: "cancelled", message: payload.message });
            return;
          }
          if (!isCurrentAnalysisJob(payload.job_id)) return;
          finishStoppedAnalysis(payload.job_id);
          setAnalysisProgress(null);
          setMessage(payload.message || "Full-game KataGo analysis cancelled.");
        }
      });
      cleanupAnalysisListeners();
      analysisCleanupRef.current = cleanup;
      const jobId = await startKataGoGameAnalysis(profile, sgfText, visits);
      const pendingTerminalEvent = pendingAnalysisTerminalEventsRef.current.get(jobId);
      const pendingProgress = pendingAnalysisProgressRef.current.get(jobId);
      startingAnalysisRef.current = false;
      pendingAnalysisProgressRef.current.clear();
      pendingAnalysisTerminalEventsRef.current.clear();
      if (pendingTerminalEvent) {
        await finishPendingAnalysisTerminalEvent(jobId, pendingTerminalEvent, parsed, replayed);
        return;
      }
      activeJobIdRef.current = jobId;
      setActiveJobId(jobId);
      if (pendingProgress) setAnalysisProgress(pendingProgress);
      setMessage(`Full-game KataGo analysis started (${jobId}).`);
    } catch (error) {
      cleanup?.();
      if (analysisCleanupRef.current === cleanup) analysisCleanupRef.current = null;
      startingAnalysisRef.current = false;
      pendingAnalysisProgressRef.current.clear();
      pendingAnalysisTerminalEventsRef.current.clear();
      activeJobIdRef.current = null;
      setActiveJobId(null);
      setAnalysisProgress(null);
      setIsKataGoRunning(false);
      setMessage(`Full-game KataGo analysis failed: ${errorMessage(error)}`);
    }
  }

  async function handleCancelKataGoAnalysis() {
    const jobId = activeJobIdRef.current;
    if (!jobId) return;
    try {
      setMessage("Cancelling full-game KataGo analysis...");
      await cancelKataGoAnalysis(jobId);
    } catch (error) {
      setMessage(`Cancel failed: ${errorMessage(error)}`);
    }
  }

  async function handleImportFile(file: File | null) {
    if (!file) return;
    try {
      const text = await file.text();
      const [parsed, replayed] = await Promise.all([parseSgfSummary(text), replaySgfPositions(text)]);
      const importedMessage = `Imported ${file.name}: ${parsed.summary.move_count} moves.`;
      setSgfText(text);
      setCurrentFilePath(null);
      setFallbackFileName(file.name);
      setDirty(false);
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(replayed.at(-1)?.move_number ?? parsed.moves.length);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      setMessage(importedMessage);
      await checkAnalysisCacheForGame(text, null, parsed, replayed, importedMessage);
    } catch (error) {
      setMessage(`Import failed: ${errorMessage(error)}`);
    }
  }

  async function handleProviderImport(result: ProviderImportResult) {
    try {
      const [parsed, replayed] = await Promise.all([parseSgfSummary(result.sgf_text), replaySgfPositions(result.sgf_text)]);
      const source = providerSourceLabel(result);
      const warningText = result.warnings.length > 0 ? ` ${result.warnings.length} provider warning(s).` : "";
      const importedMessage = `Imported ${providerLabel(result.provider)} provider payload from ${source}: ${parsed.summary.move_count} moves.${warningText}`;
      setSgfText(result.sgf_text);
      setCurrentFilePath(null);
      setFallbackFileName(providerDocumentName(result));
      setDirty(false);
      setGame(parsed);
      setPositions(replayed);
      setCurrentMove(replayed.at(-1)?.move_number ?? parsed.moves.length);
      setFrames([]);
      setProblems([]);
      setSelectedCandidateIndex(null);
      setMessage(importedMessage);
      await checkAnalysisCacheForGame(result.sgf_text, null, parsed, replayed, importedMessage);
    } catch (error) {
      setMessage(`Provider import failed: ${errorMessage(error)}`);
      throw error;
    }
  }

  async function loadSample() {
    const [parsed, replayed] = await Promise.all([parseSgfSummary(demoSgf), replaySgfPositions(demoSgf)]);
    const sampleMessage = `Sample SGF restored: ${parsed.summary.move_count} moves.`;
    setSgfText(demoSgf);
    setCurrentFilePath(null);
    setFallbackFileName("sample.sgf");
    setDirty(false);
    setGame(parsed);
    setPositions(replayed);
    setCurrentMove(replayed.at(-1)?.move_number ?? parsed.moves.length);
    setFrames([]);
    setProblems([]);
    setSelectedCandidateIndex(null);
    setMessage(sampleMessage);
    await checkAnalysisCacheForGame(demoSgf, null, parsed, replayed, sampleMessage);
  }

  function handleMoveSelect(moveNumber: number) {
    setCurrentMove(clampMoveNumberToPositions(positions, moveNumber));
    setSelectedCandidateIndex(null);
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
    setMessage(event.kind === "error"
      ? `Full-game KataGo analysis failed: ${event.message}`
      : event.message || "Full-game KataGo analysis cancelled.");
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
    setAnalysisProgress((progress) => progress ? { ...progress, completed: progress.expected || result.length, expected: progress.expected || result.length } : progress);
    finishStoppedAnalysis(jobId);
    const cacheMessage = await saveAnalysisCacheForGame(sgfText, currentFilePath, parsed, result, classified, "katago");
    setMessage(`Full-game KataGo analysis completed with ${result.length} frames. Showing move ${shownMove}.${cacheMessage}`);
  }

  function finishStoppedAnalysis(jobId: string) {
    if (activeJobIdRef.current !== null && activeJobIdRef.current !== jobId) return;
    activeJobIdRef.current = null;
    setActiveJobId(null);
    setIsKataGoRunning(false);
    cleanupAnalysisListeners();
  }

  async function checkAnalysisCacheForGame(text: string, filePath: string | null, parsed: GameDto, replayed: PositionDto[], baseMessage: string) {
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
        setCurrentMove(clampMoveNumberToPositions(replayed, payload.frames.at(-1)?.turn ?? parsed.moves.length));
        setSelectedCandidateIndex(null);
        setCacheStatus("hit");
        setCacheRecord(lookup.record);
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

  return <main className={`app-shell${preferences.boardTheme === "high-contrast" ? " theme-high-contrast" : ""}`}>
    <header className="topbar">
      <div>
        <h1>LizzieYzy Next</h1>
        <p>{health?.architecture ?? "Tauri 2 + React review workspace"}</p>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
        <CacheStatusBadge status={cacheStatus} record={cacheRecord} error={cacheError} />
        <div className="status-pill">{health?.rust_backend_ready ? "Rust backend ready" : "Browser fallback"}</div>
      </div>
    </header>
    <section className="workspace">
      <div className="left-pane">
        <BoardCanvas position={currentPosition} analysis={visibleCurrentFrame} selectedCandidateIndex={selectedCandidateIndex} />
        <WinrateChart frames={frames} currentMove={currentMove} />
        <div className="timeline-row">
          <span>Move {currentMove}</span>
          <input className="move-slider" type="range" min={0} max={maxMove} value={Math.min(currentMove, maxMove)} onChange={(e) => setCurrentMove(clampMoveNumberToPositions(positions, Number(e.target.value)))} />
          <span>{maxMove}</span>
        </div>
      </div>
      <AnalysisPanel
        frame={visibleCurrentFrame}
        problems={problems}
        boardSize={game.summary.board_size}
        currentMove={currentMove}
        selectedCandidateIndex={selectedCandidateIndex}
        onSelectCandidate={setSelectedCandidateIndex}
        onSelectProblem={handleMoveSelect}
      />
    </section>
    <section className="bottom-dock">
      <div className="sgf-tools">
        <div className="document-row">
          <strong title={currentFilePath ?? documentName}>{documentName}{dirty ? " *" : ""}</strong>
          <span>{dirty ? "Unsaved changes" : "Saved"}</span>
        </div>
        <textarea value={sgfText} onChange={(e) => {
          setSgfText(e.target.value);
          setDirty(true);
          clearReviewData();
          resetAnalysisCacheState();
          setCurrentMove(0);
          setMessage("SGF edited. Parse SGF or run review to refresh.");
        }} spellCheck={false} aria-label="SGF source" />
        <div className="button-row">
          <button onClick={() => void handleOpenSgfDocument()} disabled={isKataGoRunning}>Open</button>
          <button onClick={() => void handleSaveSgfDocument(false)} disabled={isKataGoRunning || !dirty}>Save</button>
          <button onClick={() => void handleSaveSgfDocument(true)} disabled={isKataGoRunning}>Save As</button>
          <label className={`file-button${isKataGoRunning ? " file-button-disabled" : ""}`}>
            Import SGF
            <input type="file" accept=".sgf,.txt,application/x-go-sgf,text/plain" disabled={isKataGoRunning} onChange={(event) => void handleImportFile(event.target.files?.[0] ?? null)} />
          </label>
          <button onClick={() => void loadSample()} disabled={isKataGoRunning}>Load sample</button>
          <button onClick={handleParseSgf} disabled={isKataGoRunning}>Parse SGF</button>
          <button onClick={handleFakeAnalyze} disabled={isKataGoRunning}>Run review</button>
        </div>
      </div>
      <ProviderPanel disabled={isKataGoRunning} onImport={handleProviderImport} />
      <EngineSetupPanel
        disabled={isKataGoRunning}
        onRun={handleRunKataGo}
        onAnalyzeGame={handleAnalyzeKataGoGame}
        onCancelAnalysis={handleCancelKataGoAnalysis}
        analysisProgress={analysisProgress}
        activeJobId={activeJobId}
      />
      <PreferencesPanel
        preferences={preferences}
        status={preferencesStatus}
        disabled={isKataGoRunning}
        onChange={(nextPreferences) => void handlePreferencesChange(nextPreferences)}
      />
      <p className="message">{message}</p>
    </section>
  </main>;
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

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function cacheEngineLabel(engineKind: CacheEngineKind): string {
  return engineKind === "katago" ? "KataGo" : "fake";
}

function fileNameFromPath(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}
