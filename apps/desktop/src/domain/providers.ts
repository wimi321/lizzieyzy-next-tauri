export type ProviderKind = "yike" | "fox";
export type YikeRoomKind = "old_live_room" | "old_live_board" | "game_room" | "new_live_room";

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

export type YikeUrlDescriptor = {
  provider: "yike";
  room_kind: YikeRoomKind;
  id: string;
  room_id: number;
  request_url: string;
};

export function providerLabel(provider: ProviderKind): string {
  return provider === "yike" ? "Yike" : "Fox";
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
  return source?.trim() ? source : "pasted payload";
}

export function providerDocumentName(result: ProviderImportResult): string {
  const rawSource = providerSourceLabel(result);
  const safeSource = rawSource.replace(/^https?:\/\//i, "").replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "");
  return `${result.provider}-${safeSource || "payload"}.sgf`;
}

export function emptyProviderMetadata(): ProviderGameMetadata {
  return { extra: {} };
}
