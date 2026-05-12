import { invoke } from "@tauri-apps/api/core";
import type {
  ProviderGameMetadata,
  ProviderFetchRequest,
  ProviderFetchResult,
  ProviderImportRequest,
  ProviderImportResult,
  LegacyImportCaptureHelperRequest,
  LegacyImportCaptureHelperResult,
  ReadboardSidecarProbeRequest,
  ReadboardSidecarProbeResult,
  ReadboardSidecarSyncSnapshotRequest,
  ReadboardSidecarSyncSnapshotResult,
  YikeRoomKind,
  YikeUrlDescriptor
} from "../domain/providers";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

const isTauriRuntime = () => typeof window !== "undefined" && window.__TAURI_INTERNALS__ !== undefined;

export async function parseYikeUrl(rawUrl: string): Promise<YikeUrlDescriptor> {
  if (!isTauriRuntime()) return parseYikeUrlLocally(rawUrl);
  return await invoke<YikeUrlDescriptor>("provider_parse_yike_url", { rawUrl });
}

export async function importProviderPayload(request: ProviderImportRequest): Promise<ProviderImportResult> {
  if (!isTauriRuntime()) return importProviderPayloadLocally(request);
  return await invoke<ProviderImportResult>("provider_import_from_payload", { request });
}

export async function fetchYikeProvider(request: ProviderFetchRequest): Promise<ProviderFetchResult> {
  if (!isTauriRuntime()) throw new Error("Yike fetch requires the desktop Tauri runtime; browser preview can only import pasted payloads.");
  return await invoke<ProviderFetchResult>("provider_fetch_yike", { request });
}

export async function fetchFoxProvider(request: ProviderFetchRequest): Promise<ProviderFetchResult> {
  if (!isTauriRuntime()) throw new Error("Fox fetch requires the desktop Tauri runtime; browser preview can only import pasted payloads.");
  return await invoke<ProviderFetchResult>("provider_fetch_fox", { request });
}

export async function probeReadboardSidecar(request: ReadboardSidecarProbeRequest): Promise<ReadboardSidecarProbeResult> {
  if (!isTauriRuntime()) {
    return {
      available: false,
      endpoint: request.endpoint?.trim() || null,
      version: null,
      warnings: ["Readboard sidecar probing requires the desktop Tauri runtime; browser preview cannot reach the local sidecar."]
    };
  }
  return await invoke<ReadboardSidecarProbeResult>("readboard_sidecar_probe", { request });
}

export async function syncReadboardSidecarSnapshot(
  request: ReadboardSidecarSyncSnapshotRequest
): Promise<ReadboardSidecarSyncSnapshotResult> {
  if (!isTauriRuntime()) {
    const source = request.image_path || request.image_base64 ? "controlled board image import" : "readboard protocol preview";
    throw new Error(`${source} requires the desktop Tauri runtime; browser preview cannot reach the local readboard sidecar.`);
  }
  return await invoke<ReadboardSidecarSyncSnapshotResult>("readboard_sidecar_sync_snapshot", { request });
}

export async function previewLegacyImportCaptureHelper(
  request: LegacyImportCaptureHelperRequest
): Promise<LegacyImportCaptureHelperResult> {
  if (!isTauriRuntime()) return legacyImportCaptureHelperFallback(request);
  try {
    return await invoke<LegacyImportCaptureHelperResult>("legacy_import_capture_helper", { request });
  } catch (error) {
    return legacyImportCaptureHelperFallback(request, errorMessage(error));
  }
}

function importProviderPayloadLocally(request: ProviderImportRequest): ProviderImportResult {
  const sgfText = extractSgfFromPayload(request.payload);
  const metadata = normalizeMetadata({
    ...request.metadata,
    source_url: request.metadata.source_url ?? request.source_url ?? null,
    source_id: request.metadata.source_id ?? request.source_id ?? null,
    extra: request.metadata.extra ?? {}
  });
  return {
    provider: request.provider,
    sgf_text: sgfText,
    summary: {
      provider: request.provider,
      source_id: metadata.source_id,
      board_size: numberProperty(sgfText, "SZ"),
      komi: numberProperty(sgfText, "KM"),
      black_name: textProperty(sgfText, "PB"),
      white_name: textProperty(sgfText, "PW"),
      result: textProperty(sgfText, "RE"),
      move_count: countMoves(sgfText)
    },
    metadata,
    warnings: ["Browser preview imported local payload only; provider network retrieval is handled by the desktop backend contract."]
  };
}

function parseYikeUrlLocally(rawUrl: string): YikeUrlDescriptor {
  const trimmed = rawUrl.trim();
  if (!trimmed) throw new Error("Enter a Yike URL to preview.");

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error(unsupportedYikePreviewMessage());
  }

  if (!isYikeHost(parsed.hostname)) throw new Error(unsupportedYikePreviewMessage());

  const descriptor = parseYikeRoute(parsed);
  if (!descriptor) throw new Error(unsupportedYikePreviewMessage());
  return descriptor;
}

function legacyImportCaptureHelperFallback(
  request: LegacyImportCaptureHelperRequest,
  backendMessage?: string
): LegacyImportCaptureHelperResult {
  if (request.kind === "sgf_payload") {
    return {
      kind: request.kind,
      status: "available",
      title: "SGF/payload helper",
      message: "Paste SGF or provider JSON into Payload / SGF, then use Import pasted payload.",
      recoverable: true,
      imported: false,
      boardReplacement: "none",
      warnings: ["This helper only describes the visible import path; it does not import until the user presses Import pasted payload."],
      details: { surface: "provider-payload-textarea", action: "provider-import-payload" }
    };
  }
  if (request.kind === "protocol_snapshot") {
    return {
      kind: request.kind,
      status: "available",
      title: "Protocol snapshot helper",
      message: "Paste a readboard protocol line, preview the snapshot, then import only after a valid position is shown.",
      recoverable: true,
      imported: false,
      boardReplacement: "none",
      warnings: ["Protocol snapshot import is current-position only and does not reconstruct full game history."],
      details: { surface: "readboard-protocol-textarea", action: "readboard-preview-snapshot" }
    };
  }

  const isOcr = request.kind === "image_ocr";
  return {
    kind: request.kind,
    status: isOcr ? "available" : "recoverable_unsupported",
    title: isOcr ? "Controlled board image import MVP" : "External window/client capture unsupported",
    message: isOcr
      ? "Use the controlled board image import fields in ProviderPanel to preview via the readboard sidecar, then import only after a position preview is shown."
      : "External window/client capture is not implemented in this build. No SGF was imported and the board was not replaced.",
    recoverable: true,
    imported: false,
    boardReplacement: "none",
    warnings: [
      isOcr ? "Controlled board image import is scoped to selected/pasted board images; arbitrary screenshots and external capture remain unsupported." : "External window/client capture helper is a recoverable unsupported path.",
      "No stale, guessed, or partial board replacement was applied.",
      ...(backendMessage ? [`Backend helper contract unavailable: ${backendMessage}`] : [])
    ],
    details: {
      boundary: isOcr ? "real_ocr_external_gate" : "real_external_capture_external_gate",
      no_stale_board_replacement: "true"
    }
  };
}

function parseYikeRoute(parsed: URL): YikeUrlDescriptor | null {
  for (const route of yikeRouteCandidates(parsed)) {
    const liveDescriptor = parseYikeLiveRoute(route);
    if (liveDescriptor) return liveDescriptor;

    const gameDescriptor = parseYikeGameRoute(route);
    if (gameDescriptor) return gameDescriptor;
  }

  const hallRoomId = yikeHallRoomId(parsed);
  if (hallRoomId) return yikeGameRoomDescriptor(hallRoomId);
  return null;
}

function parseYikeLiveRoute(route: string): YikeUrlDescriptor | null {
  const match = /^\/?live\/(new-room|room)\/(\d+)(?:\/(\d+)\/(\d+))?\/?$/.exec(route);
  if (!match) return null;

  const [, roomType, id, suffixKind, suffixRoom] = match;
  if (suffixKind !== undefined && suffixRoom !== undefined && !isZeroSuffix(suffixKind, suffixRoom) && Number(suffixRoom) <= 0) {
    return null;
  }

  if (roomType === "new-room") {
    return {
      provider: "yike",
      room_kind: "new_live_room",
      id,
      room_id: isZeroSuffix(suffixKind, suffixRoom) ? Number(id) : numberOrFallback(suffixRoom, Number(id)),
      request_url: `https://api-new.yikeweiqi.com/v1/golives/${id}`
    };
  }

  const suffixRoomId = numberOrFallback(suffixRoom, Number(id));
  const roomKind: YikeRoomKind = suffixKind === undefined || suffixRoomId <= 0 ? "old_live_board" : "old_live_room";
  return {
    provider: "yike",
    room_kind: roomKind,
    id,
    room_id: roomKind === "old_live_room" ? suffixRoomId : Number(id),
    request_url: roomKind === "old_live_room"
      ? `https://api.yikeweiqi.com/golive/dtl?id=${id}&flag=1`
      : `https://api.yikeweiqi.com/golive/dtl?id=${id}`
  };
}

function parseYikeGameRoute(route: string): YikeUrlDescriptor | null {
  const match = /^\/?game\/[a-zA-Z]+\/\d+\/(\d+)\/?$/.exec(route);
  return match ? yikeGameRoomDescriptor(match[1]) : null;
}

function yikeGameRoomDescriptor(roomId: string): YikeUrlDescriptor {
  return {
    provider: "yike",
    room_kind: "game_room",
    id: roomId,
    room_id: Number(roomId),
    request_url: `https://api.yikeweiqi.com/golive/dtl?id=${roomId}`
  };
}

function yikeRouteCandidates(parsed: URL): string[] {
  const routes = [parsed.pathname];
  if (parsed.hash.startsWith("#")) {
    const hash = parsed.hash.slice(1);
    const hashPath = hash.split("?")[0];
    if (hashPath) routes.push(hashPath);
  }
  return routes.map((route) => safeDecodeURIComponent(route).replace(/^\/+/, ""));
}

function yikeHallRoomId(parsed: URL): string | null {
  const roomId = hallRoomIdFromSearch(parsed.searchParams);
  if (roomId) return roomId;

  const hashQuery = parsed.hash.split("?")[1];
  if (!hashQuery) return null;
  return hallRoomIdFromSearch(new URLSearchParams(hashQuery));
}

function hallRoomIdFromSearch(searchParams: URLSearchParams): string | null {
  const roomId = searchParams.get("room");
  if (!roomId || !/^\d+$/.test(roomId) || !searchParams.has("hall")) return null;
  return roomId;
}

function isYikeHost(hostname: string): boolean {
  const lowerHostname = hostname.toLowerCase();
  return lowerHostname === "yikeweiqi.com" || lowerHostname.endsWith(".yikeweiqi.com");
}

function numberOrFallback(value: string | undefined, fallback: number): number {
  if (value === undefined) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function isZeroSuffix(suffixKind: string | undefined, suffixRoom: string | undefined): boolean {
  return suffixKind === "0" && suffixRoom === "0";
}

function safeDecodeURIComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function unsupportedYikePreviewMessage(): string {
  return "Browser preview only recognizes supported yikeweiqi.com live, game, or hall URLs. The desktop backend may support exact parsing for this URL, and payload or SGF import still works offline.";
}

function extractSgfFromPayload(payload: string): string {
  const trimmed = payload.trim();
  if (!trimmed) throw new Error("Paste provider payload or SGF before importing.");
  if (trimmed.startsWith("(")) return trimmed;

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (error) {
    throw new Error(`Provider payload is not SGF or JSON: ${errorMessage(error)}`);
  }

  const sgf = firstJsonString(parsed, ["sgf", "clean_sgf", "chess"]);
  if (!sgf) throw new Error("Provider payload JSON does not contain sgf, clean_sgf, or chess.");
  if (!sgf.trimStart().startsWith("(")) throw new Error("The provider payload field does not contain SGF text.");
  return sgf.trim();
}

function firstJsonString(value: unknown, keys: string[]): string | null {
  if (Array.isArray(value)) {
    for (const item of value) {
      const result = firstJsonString(item, keys);
      if (result) return result;
    }
    return null;
  }
  if (!isRecord(value)) return null;
  for (const key of keys) {
    const rawValue = value[key];
    if (typeof rawValue === "string" && rawValue.trim()) return rawValue.trim();
  }
  for (const rawValue of Object.values(value)) {
    const result = firstJsonString(rawValue, keys);
    if (result) return result;
  }
  return null;
}

function normalizeMetadata(metadata: ProviderGameMetadata): ProviderGameMetadata {
  return { ...metadata, extra: metadata.extra ?? {} };
}

function countMoves(sgfText: string): number {
  return sgfText.match(/;[BW]\[[^\]]*\]/gi)?.length ?? 0;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
