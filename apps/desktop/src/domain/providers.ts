import type { PositionDto } from "./types";

export type ProviderKind = "yike" | "fox" | "readboard_snapshot";
export type YikeRoomKind = "old_live_room" | "old_live_board" | "game_room" | "new_live_room";
export type ProviderFetchMethod = "get" | "post";

export type ProviderGameMetadata = {
  source_url?: string | null;
  request_url?: string | null;
  source_id?: string | null;
  room_id?: string | null;
  title?: string | null;
  provider_status?: string | null;
  extra: Record<string, string>;
};

export type ProviderGameSummary = {
  provider: ProviderKind;
  source_id?: string | null;
  board_size?: number | null;
  komi?: number | null;
  handicap?: number | null;
  black_name?: string | null;
  white_name?: string | null;
  result?: string | null;
  date?: string | null;
  move_count?: number | null;
};

export type ProviderImportRequest = {
  provider: ProviderKind;
  payload: string;
  source_url?: string | null;
  source_id?: string | null;
  metadata: ProviderGameMetadata;
};

export type ProviderImportResult = {
  provider: ProviderKind;
  sgf_text: string;
  summary: ProviderGameSummary;
  metadata: ProviderGameMetadata;
  warnings: string[];
};

export type ProviderFetchRequest = {
  provider: ProviderKind;
  url: string;
  method: ProviderFetchMethod;
  headers: Record<string, string>;
  body?: string | null;
  source_url?: string | null;
  source_id?: string | null;
  timeout_ms?: number | null;
};

export type ProviderFetchResult = {
  provider: ProviderKind;
  url: string;
  status_code: number;
  payload: string;
  headers: Record<string, string>;
  content_type?: string | null;
  metadata: ProviderGameMetadata;
  warnings: string[];
};

export type ReadboardSidecarProbeRequest = {
  endpoint?: string | null;
  timeout_ms?: number | null;
};

export type ReadboardSidecarProbeResult = {
  available: boolean;
  endpoint?: string | null;
  version?: string | null;
  warnings: string[];
};

export type ReadboardSidecarSyncSnapshotRequest = {
  endpoint?: string | null;
  snapshot_id?: string | null;
  image_path?: string | null;
  image_base64?: string | null;
  sgf_text?: string | null;
  metadata: Record<string, string>;
  timeout_ms?: number | null;
};

export type ReadboardSidecarSyncSnapshotResult = {
  snapshot_id: string;
  position?: PositionDto | null;
  warnings: string[];
};

export type YikeUrlDescriptor = {
  provider: "yike";
  room_kind: YikeRoomKind;
  id: string;
  room_id: number;
  request_url: string;
};

export function providerLabel(provider: ProviderKind): string {
  switch (provider) {
    case "yike":
      return "Yike";
    case "fox":
      return "Fox";
    case "readboard_snapshot":
      return "Readboard snapshot";
  }
}

export function yikeRoomKindLabel(kind: YikeRoomKind): string {
  switch (kind) {
    case "new_live_room":
      return "New live room";
    case "old_live_room":
      return "Old live room";
    case "old_live_board":
      return "Old live board";
    case "game_room":
      return "Game room";
  }
}

export function providerSourceLabel(result: ProviderImportResult): string {
  const source =
    result.summary.source_id ??
    result.metadata.source_id ??
    result.metadata.room_id ??
    result.metadata.source_url ??
    result.metadata.request_url;
  if (source?.trim()) return source;
  return result.provider === "readboard_snapshot" ? "current snapshot" : "pasted payload";
}

export function providerDocumentName(result: ProviderImportResult): string {
  const rawSource = providerSourceLabel(result);
  const safeSource = rawSource.replace(/^https?:\/\//i, "").replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "");
  return `${result.provider}-${safeSource || "payload"}.sgf`;
}

export function emptyProviderMetadata(): ProviderGameMetadata {
  return { extra: {} };
}
