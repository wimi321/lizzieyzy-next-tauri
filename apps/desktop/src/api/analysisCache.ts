import { invoke } from "@tauri-apps/api/core";
import type {
  AnalysisCacheLookup,
  AnalysisCacheRecord,
  AnalysisCacheRecordDto,
  ClearAnalysisCacheResult,
  ComputeGameCacheKeyDto,
  DeleteAnalysisCacheDto,
  GameCacheKey,
  GetAnalysisCacheDto,
  SaveAnalysisCacheDto,
  SaveAnalysisCacheInput,
  SaveAnalysisCacheResult
} from "../domain/cache";
import { cacheRecordFromDto, cacheRecordToDto } from "../domain/cache";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

const storagePrefix = "lizzieyzy-next-analysis-cache";
const memoryCache = new Map<string, AnalysisCacheRecord[]>();

const isTauriRuntime = () => typeof window !== "undefined" && window.__TAURI_INTERNALS__ !== undefined;

export async function computeGameCacheKey(sgfText: string, filePath?: string | null): Promise<GameCacheKey> {
  if (!isTauriRuntime()) {
    return computeBrowserGameCacheKey(sgfText, filePath);
  }

  const result = await invokeCacheCommand<ComputeGameCacheKeyDto>("compute_game_cache_key", { sgfText, filePath: filePath ?? null });
  return { gameKey: result.game_key, sgfHash: result.sgf_hash };
}

export async function loadAnalysisCache(gameKey: string, profileId?: string | null, engineKind?: string | null): Promise<AnalysisCacheLookup> {
  if (!isTauriRuntime()) {
    return loadBrowserAnalysisCache(gameKey, profileId, engineKind);
  }

  const result = await invokeCacheCommand<GetAnalysisCacheDto>("get_analysis_cache", {
    gameKey,
    profileId: profileId ?? null,
    engineKind: engineKind ?? null
  });
  return {
    status: result.status,
    record: result.record ? convertCacheRecordFromDto(result.record, "get_analysis_cache") : null,
    error: result.error
  };
}

export async function saveAnalysisCache(input: SaveAnalysisCacheInput): Promise<SaveAnalysisCacheResult> {
  if (!isTauriRuntime()) {
    return saveBrowserAnalysisCache(input);
  }

  const result = await invokeCacheCommand<SaveAnalysisCacheDto>("save_analysis_cache", {
    gameKey: input.gameKey,
    sgfHash: input.sgfHash,
    profileId: input.profileId ?? null,
    engineKind: input.engineKind,
    source: input.source,
    moveCount: input.moveCount,
    analyzedMoveCount: input.analyzedMoveCount,
    payload: input.payload
  });
  return { id: result.id, gameKey: result.game_key, updatedAt: result.updated_at };
}

export async function clearAnalysisCache(gameKey: string, profileId?: string | null, engineKind?: string | null): Promise<ClearAnalysisCacheResult> {
  if (!isTauriRuntime()) {
    return clearBrowserAnalysisCache(gameKey, profileId, engineKind);
  }

  const result = await invokeCacheCommand<DeleteAnalysisCacheDto>("delete_analysis_cache", {
    gameKey,
    profileId: profileId ?? null,
    engineKind: engineKind ?? null
  });
  return { deleted: result.deleted };
}

async function invokeCacheCommand<T>(command: string, args: Record<string, unknown>): Promise<T> {
  try {
    return await invoke<T>(command, args);
  } catch (error) {
    throw new Error(`Analysis cache backend command "${command}" failed: ${formatCacheError(error)}`);
  }
}

function convertCacheRecordFromDto(record: AnalysisCacheRecordDto, command: string): AnalysisCacheRecord {
  try {
    return cacheRecordFromDto(record);
  } catch (error) {
    throw new Error(`Analysis cache backend command "${command}" returned an invalid cache record: ${formatCacheError(error)}`);
  }
}

function formatCacheError(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

async function computeBrowserGameCacheKey(sgfText: string, filePath?: string | null): Promise<GameCacheKey> {
  const sgfHash = await sha256Hex(sgfText);
  const pathHint = filePath?.trim() ? `:${filePath.trim()}` : "";
  const gameHash = await sha256Hex(`${sgfHash}${pathHint}`);
  return { gameKey: `browser:${gameHash.slice(0, 32)}`, sgfHash };
}

async function sha256Hex(value: string): Promise<string> {
  if (typeof crypto !== "undefined" && crypto.subtle) {
    try {
      const bytes = new TextEncoder().encode(value);
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    } catch {
      return fnv1aHex(value);
    }
  }
  return fnv1aHex(value);
}

function fnv1aHex(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0").repeat(8).slice(0, 64);
}

function loadBrowserAnalysisCache(gameKey: string, profileId?: string | null, engineKind?: string | null): AnalysisCacheLookup {
  const records = readBrowserRecords(gameKey);
  const record = findMatchingRecord(records, profileId, engineKind);
  return record ? { status: "hit", record } : { status: "miss", record: null };
}

function saveBrowserAnalysisCache(input: SaveAnalysisCacheInput): SaveAnalysisCacheResult {
  const now = new Date().toISOString();
  const records = readBrowserRecords(input.gameKey);
  const existingIndex = records.findIndex((record) => cacheRecordMatches(record, input.profileId, input.engineKind));
  const existing = existingIndex >= 0 ? records[existingIndex] : null;
  const record: AnalysisCacheRecord = {
    id: existing?.id ?? browserRecordId(input.gameKey, input.profileId, input.engineKind),
    gameKey: input.gameKey,
    sgfHash: input.sgfHash,
    profileId: input.profileId ?? null,
    engineKind: input.engineKind,
    source: input.source,
    moveCount: input.moveCount,
    analyzedMoveCount: input.analyzedMoveCount,
    payload: input.payload,
    createdAt: existing?.createdAt ?? now,
    updatedAt: now
  };
  if (existingIndex >= 0) records[existingIndex] = record;
  else records.push(record);
  writeBrowserRecords(input.gameKey, records);
  return { id: record.id, gameKey: record.gameKey, updatedAt: record.updatedAt };
}

function clearBrowserAnalysisCache(gameKey: string, profileId?: string | null, engineKind?: string | null): ClearAnalysisCacheResult {
  const records = readBrowserRecords(gameKey);
  if (profileId === undefined && engineKind === undefined) {
    deleteBrowserRecords(gameKey);
    return { deleted: records.length };
  }
  const kept = records.filter((record) => !cacheRecordMatches(record, profileId, engineKind));
  writeBrowserRecords(gameKey, kept);
  return { deleted: records.length - kept.length };
}

function readBrowserRecords(gameKey: string): AnalysisCacheRecord[] {
  const memoryRecords = memoryCache.get(gameKey) ?? [];
  if (typeof window === "undefined") return memoryRecords;
  try {
    const raw = window.localStorage.getItem(storageKey(gameKey));
    if (!raw) return memoryRecords;
    const records = JSON.parse(raw) as AnalysisCacheRecordDto[];
    return records.map(cacheRecordFromDto);
  } catch {
    return memoryRecords;
  }
}

function writeBrowserRecords(gameKey: string, records: AnalysisCacheRecord[]) {
  memoryCache.set(gameKey, records);
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(gameKey), JSON.stringify(records.map(cacheRecordToDto)));
  } catch {
    memoryCache.set(gameKey, records);
  }
}

function deleteBrowserRecords(gameKey: string) {
  memoryCache.delete(gameKey);
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(storageKey(gameKey));
  } catch {
    memoryCache.delete(gameKey);
  }
}

function findMatchingRecord(records: AnalysisCacheRecord[], profileId?: string | null, engineKind?: string | null): AnalysisCacheRecord | null {
  return records.find((record) => cacheRecordMatches(record, profileId, engineKind)) ?? null;
}

function cacheRecordMatches(record: AnalysisCacheRecord, profileId?: string | null, engineKind?: string | null): boolean {
  if (profileId !== undefined && (record.profileId ?? null) !== (profileId ?? null)) return false;
  if (engineKind !== undefined && (record.engineKind ?? null) !== (engineKind ?? null)) return false;
  return true;
}

function browserRecordId(gameKey: string, profileId?: string | null, engineKind?: string | null): string {
  const identity = [gameKey, profileId ?? "default", engineKind ?? "default"].join(":");
  return `browser-cache:${fnv1aHex(identity).slice(0, 16)}`;
}

function storageKey(gameKey: string): string {
  return `${storagePrefix}:${encodeURIComponent(gameKey)}`;
}
