export type CacheStatus = "idle" | "checking" | "hit" | "miss" | "saving" | "saved" | "error";
export type BackendCacheStatus = "hit" | "miss" | "error";

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type CacheSource = "katago" | "browser" | "imported" | (string & {});

export type ComputeGameCacheKeyDto = {
  game_key: string;
  sgf_hash: string;
};

export type AnalysisCacheRecordDto = {
  id: string;
  game_key: string;
  sgf_hash: string;
  profile_id?: string | null;
  engine_kind?: string | null;
  source: CacheSource;
  move_count: number;
  analyzed_move_count: number;
  payload: JsonValue;
  created_at?: string | null;
  updated_at: string;
};

export type GetAnalysisCacheDto = {
  status: BackendCacheStatus;
  record?: AnalysisCacheRecordDto | null;
  error?: string | null;
};

export type SaveAnalysisCacheDto = {
  id: string;
  game_key: string;
  updated_at: string;
};

export type DeleteAnalysisCacheDto = {
  deleted: number;
};

export type GameCacheKey = {
  gameKey: string;
  sgfHash: string;
};

export type AnalysisCacheRecord = {
  id: string;
  gameKey: string;
  sgfHash: string;
  profileId?: string | null;
  engineKind?: string | null;
  source: CacheSource;
  moveCount: number;
  analyzedMoveCount: number;
  payload: JsonValue;
  createdAt?: string | null;
  updatedAt: string;
};

export type AnalysisCacheLookup = {
  status: BackendCacheStatus;
  record?: AnalysisCacheRecord | null;
  error?: string | null;
};

export type SaveAnalysisCacheInput = {
  gameKey: string;
  sgfHash: string;
  profileId?: string | null;
  engineKind: string;
  source: CacheSource;
  moveCount: number;
  analyzedMoveCount: number;
  payload: JsonValue;
};

export type SaveAnalysisCacheResult = {
  id: string;
  gameKey: string;
  updatedAt: string;
};

export type ClearAnalysisCacheResult = {
  deleted: number;
};

export function cacheRecordFromDto(record: AnalysisCacheRecordDto): AnalysisCacheRecord {
  return {
    id: record.id,
    gameKey: record.game_key,
    sgfHash: record.sgf_hash,
    profileId: record.profile_id,
    engineKind: record.engine_kind,
    source: record.source,
    moveCount: record.move_count,
    analyzedMoveCount: record.analyzed_move_count,
    payload: record.payload,
    createdAt: record.created_at,
    updatedAt: record.updated_at
  };
}

export function cacheRecordToDto(record: AnalysisCacheRecord): AnalysisCacheRecordDto {
  return {
    id: record.id,
    game_key: record.gameKey,
    sgf_hash: record.sgfHash,
    profile_id: record.profileId,
    engine_kind: record.engineKind,
    source: record.source,
    move_count: record.moveCount,
    analyzed_move_count: record.analyzedMoveCount,
    payload: record.payload,
    created_at: record.createdAt,
    updated_at: record.updatedAt
  };
}
