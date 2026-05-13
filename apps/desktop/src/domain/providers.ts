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
  snapshotId?: string | null;
  snapshot_hash?: string | null;
  snapshotHash?: string | null;
  hash?: string | null;
  confidence?: number | string | null;
  source?: string | null;
  source_metadata?: Record<string, string> | null;
  sourceMetadata?: Record<string, string> | null;
  metadata?: Record<string, string> | null;
  position?: PositionDto | null;
  warnings: string[];
};

export type ReadboardControlledTargetMetadata = {
  controlledLocalTargetWindow?: boolean;
  controlled_local_target_window?: boolean;
  windowTitle?: string | null;
  window_title?: string | null;
  processId?: number | null;
  process_id?: number | null;
  fixtureId?: string | null;
  fixture_id?: string | null;
  width?: number | null;
  height?: number | null;
  imagePath?: string | null;
  image_path?: string | null;
};

export type ReadboardBoardRegionMetadata = {
  detected?: boolean | null;
  x?: number | null;
  y?: number | null;
  width?: number | null;
  height?: number | null;
  confidence?: number | string | null;
  source?: string | null;
};

export type ReadboardExternalCaptureSource =
  | "screen"
  | "window"
  | "local_image"
  | "operator_selected_file"
  | "controlled_local_target_window"
  | "arbitrary_screenshot_board_region";

export type ReadboardExternalCaptureStatus = "captured" | "cancelled" | "permission" | "unsupported" | "decode_error" | "error" | string;

export type ReadboardExternalCaptureRequest = {
  source: ReadboardExternalCaptureSource;
  endpoint?: string | null;
  image_path?: string | null;
  imagePath?: string | null;
  image_base64?: string | null;
  imageBase64?: string | null;
  window_title?: string | null;
  windowTitle?: string | null;
  process_id?: number | null;
  processId?: number | null;
  fixture_id?: string | null;
  fixtureId?: string | null;
  width?: number | null;
  height?: number | null;
  controlledLocalTargetWindow?: boolean;
  controlled_local_target_window?: boolean;
  arbitraryScreenshot?: boolean;
  arbitrary_screenshot?: boolean;
  boardRegionDetection?: boolean;
  board_region_detection?: boolean;
  boardRegion?: ReadboardBoardRegionMetadata | null;
  board_region?: ReadboardBoardRegionMetadata | null;
  controlledTarget?: ReadboardControlledTargetMetadata | null;
  controlled_target?: ReadboardControlledTargetMetadata | null;
  timeout_ms?: number | null;
  timeoutMs?: number | null;
  metadata: Record<string, string>;
};

export type ReadboardExternalCaptureResult = {
  status: ReadboardExternalCaptureStatus;
  source: ReadboardExternalCaptureSource | string;
  image_path?: string | null;
  imagePath?: string | null;
  image_base64?: string | null;
  imageBase64?: string | null;
  snapshot_id?: string | null;
  snapshotId?: string | null;
  snapshot_hash?: string | null;
  snapshotHash?: string | null;
  hash?: string | null;
  sanitizedPath?: string | null;
  sha256?: string | null;
  size?: number | null;
  sizeBytes?: number | null;
  width?: number | null;
  height?: number | null;
  window_title?: string | null;
  windowTitle?: string | null;
  process_id?: number | null;
  processId?: number | null;
  fixture_id?: string | null;
  fixtureId?: string | null;
  controlledLocalTargetWindow?: boolean;
  controlled_local_target_window?: boolean;
  arbitraryScreenshot?: boolean;
  arbitrary_screenshot?: boolean;
  boardRegionDetection?: boolean;
  board_region_detection?: boolean;
  boardRegion?: ReadboardBoardRegionMetadata | Record<string, unknown> | null;
  board_region?: ReadboardBoardRegionMetadata | Record<string, unknown> | null;
  detectedBoardRegion?: ReadboardBoardRegionMetadata | Record<string, unknown> | null;
  detected_board_region?: ReadboardBoardRegionMetadata | Record<string, unknown> | null;
  controlledTarget?: ReadboardControlledTargetMetadata | null;
  controlled_target?: ReadboardControlledTargetMetadata | null;
  targetMetadata?: ReadboardControlledTargetMetadata | Record<string, unknown> | null;
  target_metadata?: ReadboardControlledTargetMetadata | Record<string, unknown> | null;
  artifact?: Record<string, unknown> | null;
  decode?: Record<string, unknown> | string | null;
  confidence?: number | string | null;
  position?: PositionDto | null;
  warnings: string[];
  message?: string | null;
  errorMessage?: string | null;
  recoverable?: boolean;
  imported?: boolean;
  metadata?: Record<string, string> | null;
  source_metadata?: Record<string, string> | null;
  sourceMetadata?: Record<string, string> | null;
  [key: string]: unknown;
};

export type LegacyImportCaptureHelperKind =
  | "sgf_payload"
  | "protocol_snapshot"
  | "image_ocr"
  | "external_window_capture"
  | "external_client_capture";

export type LegacyImportCaptureHelperStatus = "available" | "recoverable_unsupported" | "error";

export type LegacyImportCaptureHelperRequest = {
  kind: LegacyImportCaptureHelperKind;
  payload?: string | null;
  image_path?: string | null;
  image_base64?: string | null;
  window_title?: string | null;
  client_name?: string | null;
  process_id?: number | null;
  timeout_ms?: number | null;
  metadata: Record<string, string>;
};

export type LegacyImportCaptureHelperResult = {
  kind: LegacyImportCaptureHelperKind;
  status: LegacyImportCaptureHelperStatus;
  title: string;
  message: string;
  recoverable: boolean;
  imported: boolean;
  boardReplacement: "none" | "imported" | "preview_only";
  warnings: string[];
  details: Record<string, string>;
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
