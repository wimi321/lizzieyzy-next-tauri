import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { open, save } from "@tauri-apps/plugin-dialog";
import type {
  AnalysisFrameDto,
  AppHealthDto,
  AssetCheckDto,
  CandidateMoveDto,
  EngineProfileRecordDto,
  EngineProfileDto,
  EngineProfilesSettingsDto,
  EngineProfileSettingsDto,
  GameDto,
  MoveDto,
  MoveVertex,
  PlayerColor,
  PositionDto,
  ProblemMarkerDto,
  SgfTreeDto
} from "../domain/types";
import { ensureInitialPosition, replayGamePositions } from "../domain/board";

const letters = "abcdefghijklmnopqrstuvwxyz";
const sampleGameId = "browser-sgf";
const sgfDialogFilters = [{ name: "SGF files", extensions: ["sgf", "txt"] }];

export type SgfDocument = {
  path: string | null;
  sgfText: string;
};

export type AppendSgfMoveResult = {
  sgf_text: string;
  new_node_id: string;
};

export type DeleteSgfNodeResult = {
  sgf_text: string;
  parent_node_id: string;
};

export type ReorderSgfVariationResult = {
  sgf_text: string;
  node_id: string;
  parent_node_id: string;
};

export type SgfPropertyUpdate = {
  key: string;
  values: string[];
};

export type UpdateSgfNodePropertiesResult = {
  sgf_text: string;
  node_id: string;
};

export type AnalysisProgressPayload = {
  job_id: string;
  completed: number;
  expected: number;
  turn: number;
  response_jsonl: string;
};

export type AnalysisCompletePayload = {
  job_id: string;
  frames: AnalysisFrameDto[];
};

export type AnalysisErrorPayload = {
  job_id: string;
  message: string;
};

export type KataGoAnalysisEventHandlers = {
  onProgress?: (payload: AnalysisProgressPayload) => void;
  onComplete?: (payload: AnalysisCompletePayload) => void;
  onError?: (payload: AnalysisErrorPayload) => void;
  onCancelled?: (payload: AnalysisErrorPayload) => void;
};

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

const isTauriRuntime = () => typeof window !== "undefined" && window.__TAURI_INTERNALS__ !== undefined;

export async function getHealth(): Promise<AppHealthDto> {
  if (!isTauriRuntime()) {
    return browserHealth("Tauri APIs are unavailable, so SGF parsing and analysis are running in browser preview mode.");
  }
  try {
    return await invoke<AppHealthDto>("health");
  } catch {
    return browserHealth("Tauri is running, but backend commands are not ready; using local review fallback.");
  }
}

export async function parseSgfSummary(sgfText: string): Promise<GameDto> {
  if (!isTauriRuntime()) return parseSgfLocally(sgfText);
  try {
    return await invoke<GameDto>("parse_sgf_summary", { sgfText });
  } catch {
    return parseSgfLocally(sgfText);
  }
}

export async function parseSgfTree(sgfText: string): Promise<SgfTreeDto | null> {
  if (isTauriRuntime()) return await invoke<SgfTreeDto | null>("parse_sgf_tree", { sgfText });
  return buildBrowserSgfTree(await parseSgfSummary(sgfText));
}

export async function fakeAnalyze(sgfText: string): Promise<AnalysisFrameDto[]> {
  if (!isTauriRuntime()) return buildBrowserAnalysis(parseSgfLocally(sgfText));
  try {
    return await invoke<AnalysisFrameDto[]>("fake_analyze", { sgfText });
  } catch {
    return buildBrowserAnalysis(parseSgfLocally(sgfText));
  }
}

export async function openSgfDocument(): Promise<SgfDocument | null> {
  if (!isTauriRuntime()) return null;
  const selected = await open({
    multiple: false,
    directory: false,
    filters: sgfDialogFilters
  });
  if (typeof selected !== "string") return null;
  const sgfText = await invoke<string>("read_sgf_file", { path: selected });
  return { path: selected, sgfText };
}

export async function readSgfDocument(path: string): Promise<SgfDocument> {
  if (!isTauriRuntime()) {
    throw new Error("Reading an SGF document by path requires the Tauri desktop backend. Browser preview can still open files through Import SGF.");
  }
  const sgfText = await invoke<string>("read_sgf_file", { path });
  return { path, sgfText };
}

export async function saveSgfDocument(path: string | null, sgfText: string, defaultFileName = "review.sgf"): Promise<SgfDocument | null> {
  if (!isTauriRuntime()) {
    downloadSgf(sgfText, path ? fileNameFromPath(path) : defaultFileName);
    return { path, sgfText };
  }

  const targetPath = path ?? await save({
    filters: sgfDialogFilters,
    defaultPath: defaultFileName
  });
  if (!targetPath) return null;
  await invoke<void>("write_sgf_file", { path: targetPath, sgfText });
  const savedSgfText = await invoke<string>("read_sgf_file", { path: targetPath });
  return { path: targetPath, sgfText: savedSgfText };
}

export async function analyzeKataGoOnce(profile: EngineProfileDto, sgfText: string, turn: number, maxVisits: number): Promise<AnalysisFrameDto> {
  if (!isTauriRuntime()) {
    throw new Error("Real KataGo analysis requires the Tauri desktop backend. Browser preview can still use Run review for fake analysis.");
  }
  return await invoke<AnalysisFrameDto>("katago_analyze_once", { profile, sgfText, turn, maxVisits });
}

export async function analyzeKataGoGame(profile: EngineProfileDto, sgfText: string, maxVisits: number): Promise<AnalysisFrameDto[]> {
  if (!isTauriRuntime()) {
    throw new Error("Full-game KataGo analysis requires the Tauri desktop backend. Browser preview cannot run real KataGo; use Run review for fake analysis.");
  }
  return await invoke<AnalysisFrameDto[]>("katago_analyze_game", { profile, sgfText, maxVisits });
}

export async function startKataGoGameAnalysis(profile: EngineProfileDto, sgfText: string, maxVisits: number): Promise<string> {
  if (!isTauriRuntime()) {
    throw new Error("Full-game KataGo analysis requires the Tauri desktop backend. Browser preview cannot run real KataGo; use Run review for fake analysis.");
  }
  return await invoke<string>("katago_start_analyze_game", { profile, sgfText, maxVisits });
}

export async function cancelKataGoAnalysis(jobId: string): Promise<void> {
  if (!isTauriRuntime()) return;
  await invoke<void>("katago_cancel_analysis", { jobId });
}

export async function listenToKataGoAnalysisEvents(handlers: KataGoAnalysisEventHandlers): Promise<() => void> {
  if (!isTauriRuntime()) return () => undefined;
  const unlisteners = await Promise.all([
    listen<AnalysisProgressPayload>("katago://analysis-progress", (event) => handlers.onProgress?.(event.payload)),
    listen<AnalysisCompletePayload>("katago://analysis-complete", (event) => handlers.onComplete?.(event.payload)),
    listen<AnalysisErrorPayload>("katago://analysis-error", (event) => handlers.onError?.(event.payload)),
    listen<AnalysisErrorPayload>("katago://analysis-cancelled", (event) => handlers.onCancelled?.(event.payload))
  ]);
  return () => {
    for (const unlisten of unlisteners) unlisten();
  };
}

export async function loadEngineProfileSettings(): Promise<EngineProfileSettingsDto | null> {
  if (!isTauriRuntime()) return loadBrowserEngineProfileSettings();
  return await invoke<EngineProfileSettingsDto | null>("load_engine_profile_settings");
}

export async function saveEngineProfileSettings(settings: EngineProfileSettingsDto): Promise<EngineProfileSettingsDto> {
  if (!isTauriRuntime()) {
    saveBrowserEngineProfileSettings(settings);
    return settings;
  }
  return await invoke<EngineProfileSettingsDto>("save_engine_profile_settings", { settings });
}

export async function loadEngineProfilesSettings(): Promise<EngineProfilesSettingsDto> {
  if (!isTauriRuntime()) return loadBrowserEngineProfilesSettings();
  return await invoke<EngineProfilesSettingsDto>("load_engine_profiles_settings");
}

export async function saveEngineProfilesSettings(settings: EngineProfilesSettingsDto): Promise<EngineProfilesSettingsDto> {
  if (!isTauriRuntime()) {
    const normalized = normalizeBrowserEngineProfilesSettings(settings);
    saveBrowserEngineProfilesSettings(normalized);
    return normalized;
  }
  return await invoke<EngineProfilesSettingsDto>("save_engine_profiles_settings", { settings });
}

export async function checkEngineAssets(profile: EngineProfileDto): Promise<AssetCheckDto[]> {
  if (!isTauriRuntime()) {
    throw new Error("Asset checks require the Tauri desktop backend so local files can be inspected.");
  }
  return await invoke<AssetCheckDto[]>("engine_asset_checks", { profile });
}

export async function replaySgfPositions(sgfText: string): Promise<PositionDto[]> {
  if (!isTauriRuntime()) return replayGamePositions(parseSgfLocally(sgfText));
  try {
    const parsed = await parseSgfSummary(sgfText);
    const positions = await invoke<PositionDto[]>("replay_sgf_positions", { sgfText });
    return ensureInitialPosition(parsed.summary.board_size, positions);
  } catch {
    return replayGamePositions(parseSgfLocally(sgfText));
  }
}

export async function updateSgfNodeComment(sgfText: string, nodeId: string, comment: string | null): Promise<string> {
  if (!isTauriRuntime()) {
    throw new Error("Editing SGF node comments requires the Tauri desktop backend. Browser preview cannot persist branch-safe SGF edits.");
  }
  return await invoke<string>("update_sgf_node_comment", { sgfText, nodeId, comment });
}

export async function updateSgfNodeProperties(
  sgfText: string,
  nodeId: string,
  updates: SgfPropertyUpdate[]
): Promise<UpdateSgfNodePropertiesResult> {
  if (!isTauriRuntime()) {
    throw new Error("Editing SGF node properties requires the Tauri desktop backend. Browser preview cannot persist branch-safe SGF edits.");
  }
  return await invoke<UpdateSgfNodePropertiesResult>("update_sgf_node_properties", { sgfText, nodeId, updates });
}

export async function appendSgfMove(
  sgfText: string,
  parentNodeId: string,
  color: PlayerColor,
  vertex: MoveVertex
): Promise<AppendSgfMoveResult> {
  if (!isTauriRuntime()) {
    throw new Error("真实 SGF move editing requires Tauri backend. Browser preview cannot append SGF moves or variations.");
  }
  return await invoke<AppendSgfMoveResult>("append_sgf_move", { sgfText, parentNodeId, color, vertex });
}

export async function deleteSgfNode(sgfText: string, nodeId: string): Promise<DeleteSgfNodeResult> {
  if (!isTauriRuntime()) {
    throw new Error("真实 SGF node deletion requires Tauri backend. Browser preview cannot delete SGF nodes or variations.");
  }
  return await invoke<DeleteSgfNodeResult>("delete_sgf_node", { sgfText, nodeId });
}

export async function reorderSgfVariation(sgfText: string, nodeId: string, targetIndex: number): Promise<ReorderSgfVariationResult> {
  if (!isTauriRuntime()) {
    throw new Error("真实 SGF variation reordering requires Tauri backend. Browser preview cannot reorder SGF variations.");
  }
  return await invoke<ReorderSgfVariationResult>("reorder_sgf_variation", { sgfText, nodeId, targetIndex });
}

export async function replaySgfPositionAtNode(sgfText: string, nodeId: string): Promise<PositionDto> {
  if (!isTauriRuntime()) return replayBrowserSgfPositionAtNode(sgfText, nodeId);
  return await invoke<PositionDto>("replay_sgf_position_at_node", { sgfText, nodeId });
}

export async function classifyProblems(frames: AnalysisFrameDto[]): Promise<ProblemMarkerDto[]> {
  if (!isTauriRuntime()) return classifyProblemFrames(frames);
  try {
    return await invoke<ProblemMarkerDto[]>("classify_problems", { frames });
  } catch {
    return classifyProblemFrames(frames);
  }
}

function browserHealth(note: string): AppHealthDto {
  return { app: "LizzieYzy Next", architecture: "React review workspace fallback", rust_backend_ready: false, notes: [note] };
}

const browserEngineProfileKey = "lizzieyzy-next-engine-profile";
const defaultEngineProfileId = "default";

function loadBrowserEngineProfileSettings(): EngineProfileSettingsDto | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(browserEngineProfileKey);
  if (!raw) return null;
  try {
    const settings = normalizeBrowserEngineProfilesSettings(JSON.parse(raw) as EngineProfilesSettingsDto | EngineProfileSettingsDto);
    const selected = settings.profiles.find((profile) => profile.id === settings.selected_profile_id) ?? settings.profiles[0];
    return selected ? { profile: selected.profile, max_visits: selected.max_visits } : null;
  } catch {
    return null;
  }
}

function saveBrowserEngineProfileSettings(settings: EngineProfileSettingsDto) {
  if (typeof window === "undefined") return;
  saveBrowserEngineProfilesSettings({
    selected_profile_id: defaultEngineProfileId,
    profiles: [{ id: defaultEngineProfileId, profile: settings.profile, max_visits: settings.max_visits }]
  });
}

function loadBrowserEngineProfilesSettings(): EngineProfilesSettingsDto {
  if (typeof window === "undefined") return defaultBrowserEngineProfilesSettings();
  const raw = window.localStorage.getItem(browserEngineProfileKey);
  if (!raw) return defaultBrowserEngineProfilesSettings();
  try {
    return normalizeBrowserEngineProfilesSettings(JSON.parse(raw) as EngineProfilesSettingsDto | EngineProfileSettingsDto);
  } catch {
    return defaultBrowserEngineProfilesSettings();
  }
}

function saveBrowserEngineProfilesSettings(settings: EngineProfilesSettingsDto) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(browserEngineProfileKey, JSON.stringify(settings));
}

function normalizeBrowserEngineProfilesSettings(settings: EngineProfilesSettingsDto | EngineProfileSettingsDto): EngineProfilesSettingsDto {
  if (isEngineProfilesSettings(settings)) {
    const profiles = settings.profiles.length > 0 ? settings.profiles : [defaultBrowserEngineProfileRecord()];
    const hasDefault = profiles.some((profile) => profile.id === defaultEngineProfileId);
    const normalizedProfiles = hasDefault ? profiles : [defaultBrowserEngineProfileRecord(), ...profiles];
    const selected = normalizedProfiles.some((profile) => profile.id === settings.selected_profile_id)
      ? settings.selected_profile_id
      : defaultEngineProfileId;
    return { selected_profile_id: selected, profiles: normalizedProfiles };
  }
  return {
    selected_profile_id: defaultEngineProfileId,
    profiles: [{ id: defaultEngineProfileId, profile: settings.profile, max_visits: settings.max_visits }]
  };
}

function isEngineProfilesSettings(settings: EngineProfilesSettingsDto | EngineProfileSettingsDto): settings is EngineProfilesSettingsDto {
  return "profiles" in settings && Array.isArray(settings.profiles);
}

function defaultBrowserEngineProfilesSettings(): EngineProfilesSettingsDto {
  return { selected_profile_id: defaultEngineProfileId, profiles: [defaultBrowserEngineProfileRecord()] };
}

function defaultBrowserEngineProfileRecord(): EngineProfileRecordDto {
  return {
    id: defaultEngineProfileId,
    profile: {
      name: "Local KataGo",
      engine_path: "",
      model_path: null,
      config_path: null,
      working_dir: null,
      backend: "kata_go_analysis"
    },
    max_visits: 800
  };
}

function downloadSgf(sgfText: string, fileName: string) {
  if (typeof document === "undefined") return;
  const blob = new Blob([sgfText], { type: "application/x-go-sgf;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName || "review.sgf";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function fileNameFromPath(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? "review.sgf";
}

function parseSgfLocally(sgfText: string): GameDto {
  const text = sgfText.trim();
  if (!text.startsWith("(") || !text.includes(";")) {
    throw new Error("The SGF text does not look like a game tree.");
  }

  const boardSize = numberProperty(text, "SZ") ?? 19;
  const komi = numberProperty(text, "KM") ?? 7.5;
  const moves = extractMainVariationNodes(text)
    .flatMap((node) => {
      const match = /(?:^|[^A-Za-z])([BW])\[([a-z]{0,2})\]/i.exec(node);
      const color: PlayerColor = match?.[1].toUpperCase() === "B" ? "black" : "white";
      return match ? [{ color, rawVertex: match[2] }] : [];
    })
    .map<MoveDto>((move, index) => ({
      color: move.color,
      vertex: parseVertex(move.rawVertex, boardSize),
      move_number: index + 1
    }));

  if (moves.length === 0) {
    throw new Error("No main-line moves were found in the SGF text.");
  }

  return {
    summary: {
      id: sampleGameId,
      board_size: boardSize,
      komi,
      black_name: textProperty(text, "PB") ?? "Black",
      white_name: textProperty(text, "PW") ?? "White",
      result: textProperty(text, "RE"),
      move_count: moves.length
    },
    moves
  };
}

export function extractMainVariationNodes(sgfText: string): string[] {
  const nodes: string[] = [];
  const text = sgfText.trim();
  const start = text.indexOf("(");
  if (start < 0) return nodes;

  function parseSequence(index: number): number {
    let cursor = index;
    while (cursor < text.length) {
      cursor = skipWhitespace(cursor);
      const char = text[cursor];
      if (char === ";") {
        const node = readNode(cursor + 1);
        nodes.push(node.value);
        cursor = node.nextIndex;
      } else if (char === "(") {
        return skipSiblingVariations(parseSequence(cursor + 1));
      } else if (char === ")") {
        return cursor + 1;
      } else {
        cursor += 1;
      }
    }
    return cursor;
  }

  parseSequence(start + 1);
  return nodes;

  function readNode(index: number): { value: string; nextIndex: number } {
    let cursor = index;
    let inValue = false;
    let escaped = false;
    while (cursor < text.length) {
      const char = text[cursor];
      if (inValue) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === "]") inValue = false;
      } else if (char === "[") {
        inValue = true;
      } else if (char === ";" || char === "(" || char === ")") {
        break;
      }
      cursor += 1;
    }
    return { value: text.slice(index, cursor), nextIndex: cursor };
  }

  function skipSiblingVariations(index: number): number {
    let cursor = skipWhitespace(index);
    while (text[cursor] === "(") {
      cursor = skipGameTree(cursor);
      cursor = skipWhitespace(cursor);
    }
    return cursor;
  }

  function skipGameTree(index: number): number {
    let cursor = index;
    let depth = 0;
    let inValue = false;
    let escaped = false;
    while (cursor < text.length) {
      const char = text[cursor];
      if (inValue) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === "]") inValue = false;
      } else if (char === "[") {
        inValue = true;
      } else if (char === "(") {
        depth += 1;
      } else if (char === ")") {
        depth -= 1;
        if (depth === 0) return cursor + 1;
      }
      cursor += 1;
    }
    return cursor;
  }

  function skipWhitespace(index: number): number {
    let cursor = index;
    while (/\s/.test(text[cursor] ?? "")) cursor += 1;
    return cursor;
  }
}

function parseVertex(raw: string, boardSize: number): MoveVertex {
  if (raw.length !== 2) return "pass";
  const x = letters.indexOf(raw[0].toLowerCase());
  const y = letters.indexOf(raw[1].toLowerCase());
  if (x < 0 || y < 0 || x >= boardSize || y >= boardSize) return "pass";
  return { point: { x, y } };
}

function numberProperty(text: string, property: string): number | null {
  const value = textProperty(text, property);
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function textProperty(text: string, property: string): string | null {
  const match = new RegExp(`${property}\\[([^\\]]*)\\]`, "i").exec(text);
  return match?.[1] ?? null;
}

function buildBrowserSgfTree(game: GameDto): SgfTreeDto {
  const rootId = `${game.summary.id}:root`;
  const nodes: SgfTreeDto["nodes"] = [
    {
      id: rootId,
      parent_id: null,
      child_ids: game.moves.length > 0 ? [`${game.summary.id}:move-1`] : [],
      variation_index: 0,
      depth: 0,
      move_number: null,
      color: null,
      vertex: null,
      name: null,
      comment: null,
      properties: [
        { key: "SZ", values: [String(game.summary.board_size)] },
        { key: "KM", values: [String(game.summary.komi)] }
      ],
      is_mainline: true
    }
  ];

  game.moves.forEach((move, index) => {
    const id = `${game.summary.id}:move-${index + 1}`;
    const nextId = index + 1 < game.moves.length ? `${game.summary.id}:move-${index + 2}` : null;
    nodes.push({
      id,
      parent_id: index === 0 ? rootId : `${game.summary.id}:move-${index}`,
      child_ids: nextId ? [nextId] : [],
      variation_index: 0,
      depth: index + 1,
      move_number: move.move_number,
      color: move.color,
      vertex: move.vertex,
      name: null,
      comment: null,
      properties: [],
      is_mainline: true
    });
  });

  return { root_id: rootId, nodes };
}

function replayBrowserSgfPositionAtNode(sgfText: string, nodeId: string): PositionDto {
  const game = parseSgfLocally(sgfText);
  const tree = buildBrowserSgfTree(game);
  const node = tree.nodes.find((candidate) => candidate.id === nodeId);
  const positions = replayGamePositions(game);
  if (!node) return positions.at(-1) ?? initialBrowserPosition(game.summary.board_size);
  return positions[node.move_number ?? 0] ?? positions.at(-1) ?? initialBrowserPosition(game.summary.board_size);
}

function initialBrowserPosition(boardSize: number): PositionDto {
  return {
    board_size: boardSize,
    move_number: 0,
    to_play: "black",
    stones: [],
    captures_black: 0,
    captures_white: 0,
    last_move: null,
    errors: []
  };
}

function buildBrowserAnalysis(game: GameDto): AnalysisFrameDto[] {
  const frames: AnalysisFrameDto[] = [];
  for (let turn = 0; turn <= game.moves.length; turn += 1) {
    const trend = Math.sin(turn * 0.62) * 0.08 + Math.cos(turn * 0.21) * 0.045;
    const movePressure = turn > 0 && turn % 7 === 0 ? -0.08 : 0;
    const winrate = clamp(0.51 + trend + movePressure, 0.18, 0.82);
    frames.push({
      job_id: "browser-preview",
      game_id: game.summary.id,
      node_id: `turn-${turn}`,
      turn,
      visits: 800 + turn * 137,
      winrate_black: winrate,
      score_mean_black: (winrate - 0.5) * 28,
      score_stdev: 8.5,
      candidates: buildCandidates(game, turn, winrate)
    });
  }
  return frames;
}

function buildCandidates(game: GameDto, turn: number, winrate: number): CandidateMoveDto[] {
  const occupied = new Set(
    game.moves
      .slice(0, turn)
      .map((move) => (typeof move.vertex === "object" ? `${move.vertex.point.x}:${move.vertex.point.y}` : "pass"))
  );
  const candidates: CandidateMoveDto[] = [];
  let cursor = turn * 5 + 3;
  while (candidates.length < 8 && cursor < game.summary.board_size * game.summary.board_size * 3) {
    const x = (cursor * 7 + 3) % game.summary.board_size;
    const y = (cursor * 11 + 5) % game.summary.board_size;
    cursor += 1;
    if (occupied.has(`${x}:${y}`)) continue;
    const rank = candidates.length;
    const rankPenalty = rank * 0.018;
    const candidateWinrate = clamp(winrate - rankPenalty + Math.sin((turn + rank) * 0.9) * 0.012, 0.04, 0.96);
    candidates.push({
      vertex: { point: { x, y } },
      visits: Math.max(32, Math.round((1100 + turn * 92) / (rank + 1.35))),
      winrate_black: candidateWinrate,
      score_mean_black: (candidateWinrate - 0.5) * 28,
      policy_prior: clamp(0.34 - rank * 0.035, 0.03, 0.34),
      pv: [{ point: { x, y } }]
    });
  }
  return candidates;
}

function classifyProblemFrames(frames: AnalysisFrameDto[]): ProblemMarkerDto[] {
  return frames
    .slice(1)
    .map((frame, index) => {
      const previous = frames[index];
      const loss = Math.max(0, previous.winrate_black - frame.winrate_black);
      return { frame, loss };
    })
    .filter(({ loss }) => loss >= 0.045)
    .map(({ frame, loss }) => ({
      turn: frame.turn,
      severity: loss >= 0.12 ? "blunder" : loss >= 0.085 ? "mistake" : "inaccuracy",
      winrate_loss: loss,
      score_loss: loss * 28,
      label: loss >= 0.12 ? "Major drop" : loss >= 0.085 ? "Mistake" : "Inaccuracy"
    }));
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
