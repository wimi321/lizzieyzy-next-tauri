import { useState } from "react";
import {
  fetchFoxProvider,
  fetchYikeProvider,
  importProviderPayload,
  parseYikeUrl,
  probeReadboardSidecar,
  syncReadboardSidecarSnapshot
} from "../api/providers";
import {
  emptyProviderMetadata,
  providerLabel,
  yikeRoomKindLabel,
  type ProviderFetchRequest,
  type ProviderFetchResult,
  type ProviderGameMetadata,
  type ProviderImportRequest,
  type ProviderImportResult,
  type ProviderKind,
  type ReadboardSidecarProbeResult,
  type ReadboardSidecarSyncSnapshotResult,
  type YikeUrlDescriptor
} from "../domain/providers";
import type { PlayerColor, PositionDto, StoneDto } from "../domain/types";

type Props = {
  disabled?: boolean;
  onImport: (result: ProviderImportResult) => void | Promise<void>;
};

type OperationStatus = {
  preview: string;
  fetch: string;
  import: string;
  readboardProbe: string;
  readboardSync: string;
};

type FoxFetchInput = {
  url: string;
  sourceUrl: string | null;
  sourceId: string | null;
};

const providerFetchTimeoutMs = 15_000;
const readboardTimeoutMs = 5_000;

const initialStatuses: OperationStatus = {
  preview: "Yike URL preview ready.",
  fetch: "Provider fetch ready.",
  import: "Payload import ready.",
  readboardProbe: "Readboard probe ready.",
  readboardSync: "Protocol snapshot preview ready."
};

export function ProviderPanel({ disabled = false, onImport }: Props) {
  const [provider, setProvider] = useState<ProviderKind>("yike");
  const [sourceUrl, setSourceUrl] = useState("");
  const [payload, setPayload] = useState("");
  const [descriptor, setDescriptor] = useState<YikeUrlDescriptor | null>(null);
  const [statuses, setStatuses] = useState<OperationStatus>(initialStatuses);
  const [readboardEndpoint, setReadboardEndpoint] = useState("");
  const [readboardProtocolLine, setReadboardProtocolLine] = useState("");
  const [readboardProbeResult, setReadboardProbeResult] = useState<ReadboardSidecarProbeResult | null>(null);
  const [readboardSyncResult, setReadboardSyncResult] = useState<ReadboardSidecarSyncSnapshotResult | null>(null);
  const [providerWarnings, setProviderWarnings] = useState<string[]>([]);
  const canPreviewYike = !disabled && provider === "yike" && sourceUrl.trim().length > 0;
  const canFetchYike = !disabled && provider === "yike" && descriptor !== null;
  const canFetchFox = !disabled && provider === "fox" && sourceUrl.trim().length > 0;
  const canImport = !disabled && payload.trim().length > 0;
  const canProbeReadboard = !disabled;
  const canSyncReadboard = !disabled && readboardProtocolLine.trim().length > 0;
  const canImportReadboardSnapshot = !disabled && readboardSyncResult?.position != null;
  const headerStatus = statuses.fetch !== initialStatuses.fetch
    ? statuses.fetch
    : statuses.import !== initialStatuses.import
      ? statuses.import
      : provider === "yike"
        ? statuses.preview
        : "Fox fetch ready.";

  function handleProviderChange(nextProvider: ProviderKind) {
    setProvider(nextProvider);
    setDescriptor(null);
    setProviderWarnings([]);
    setOperationStatus("preview", nextProvider === "yike" ? "Yike URL preview ready." : "Fox accepts chessid or provider command input.");
    setOperationStatus("fetch", `${providerLabel(nextProvider)} fetch ready.`);
    setOperationStatus("import", `${providerLabel(nextProvider)} payload import ready.`);
  }

  async function handlePreviewYikeUrl() {
    if (!canPreviewYike) return;
    setOperationStatus("preview", "Previewing Yike URL...");
    try {
      const nextDescriptor = await parseYikeUrl(sourceUrl);
      setDescriptor(nextDescriptor);
      setProviderWarnings([]);
      setOperationStatus("preview", `${yikeRoomKindLabel(nextDescriptor.room_kind)} descriptor ready.`);
    } catch (error) {
      setDescriptor(null);
      setProviderWarnings([]);
      setOperationStatus("preview", `URL preview failed: ${errorMessage(error)}`);
    }
  }

  async function handleFetchYikeAndImport() {
    if (!canFetchYike || descriptor === null) return;
    setOperationStatus("fetch", "Fetching Yike payload...");
    try {
      const result = await fetchYikeProvider(buildYikeFetchRequest(descriptor, sourceUrl));
      await importFetchedPayload(result, sourceUrl.trim() || descriptor.request_url, descriptor.id);
      setOperationStatus("fetch", providerFetchStatus(result, "Yike"));
    } catch (error) {
      setProviderWarnings([]);
      setOperationStatus("fetch", `Yike fetch failed: ${errorMessage(error)}`);
    }
  }

  async function handleFetchFoxAndImport() {
    if (!canFetchFox) return;
    try {
      const foxInput = normalizeFoxFetchInput(sourceUrl);
      setOperationStatus("fetch", "Fetching Fox payload...");
      const result = await fetchFoxProvider(buildFoxFetchRequest(foxInput));
      await importFetchedPayload(result, foxInput.sourceUrl, foxInput.sourceId);
      setOperationStatus("fetch", providerFetchStatus(result, "Fox"));
    } catch (error) {
      setProviderWarnings([]);
      setOperationStatus("fetch", `Fox fetch failed: ${errorMessage(error)}`);
    }
  }

  async function handleImport() {
    if (!canImport) return;
    setOperationStatus("import", "Importing provider payload...");
    try {
      const result = await importProviderPayload(buildRequest(provider, payload, sourceUrl, descriptor));
      await onImport(result);
      setProviderWarnings(result.warnings);
      setOperationStatus("import", importStatus(result));
    } catch (error) {
      setProviderWarnings([]);
      setOperationStatus("import", `Import failed: ${errorMessage(error)}`);
    }
  }

  async function handleReadboardProbe() {
    if (!canProbeReadboard) return;
    setOperationStatus("readboardProbe", "Probing readboard sidecar...");
    try {
      const result = await probeReadboardSidecar({
        endpoint: optionalTrimmed(readboardEndpoint),
        timeout_ms: readboardTimeoutMs
      });
      setReadboardProbeResult(result);
      setOperationStatus("readboardProbe", result.available ? "Readboard sidecar available." : "Readboard sidecar unavailable.");
    } catch (error) {
      setReadboardProbeResult(null);
      setOperationStatus("readboardProbe", `Readboard probe failed: ${errorMessage(error)}`);
    }
  }

  async function handleReadboardSync() {
    if (!canSyncReadboard) return;
    setOperationStatus("readboardSync", "Previewing protocol snapshot...");
    try {
      const result = await syncReadboardSidecarSnapshot({
        endpoint: optionalTrimmed(readboardEndpoint),
        sgf_text: readboardProtocolLine.trim(),
        metadata: { source: "provider_panel", input: "protocol_line" },
        timeout_ms: readboardTimeoutMs
      });
      setReadboardSyncResult(result);
      setOperationStatus("readboardSync", readboardSyncStatus(result));
    } catch (error) {
      setReadboardSyncResult(null);
      setOperationStatus("readboardSync", `Readboard preview failed: ${errorMessage(error)}`);
    }
  }

  async function handleImportReadboardSnapshot() {
    if (!readboardSyncResult?.position) return;
    setOperationStatus("readboardSync", "Importing readboard snapshot...");
    try {
      const result = buildReadboardSnapshotImportResult(readboardSyncResult, optionalTrimmed(readboardEndpoint));
      await onImport(result);
      setOperationStatus("readboardSync", readboardSnapshotImportStatus(result));
    } catch (error) {
      setOperationStatus("readboardSync", `Readboard snapshot import failed: ${errorMessage(error)}`);
    }
  }

  async function importFetchedPayload(result: ProviderFetchResult, fallbackSourceUrl: string | null, fallbackSourceId: string | null) {
    setPayload(result.payload);
    setOperationStatus("import", `Importing fetched ${providerLabel(result.provider)} payload...`);
    const imported = await importProviderPayload(buildFetchImportRequest(result, fallbackSourceUrl, fallbackSourceId));
    await onImport(imported);
    setProviderWarnings([...result.warnings, ...imported.warnings]);
    setOperationStatus("import", importStatus(imported));
  }

  function setOperationStatus(operation: keyof OperationStatus, status: string) {
    setStatuses((current) => ({ ...current, [operation]: status }));
  }

  return (
    <section className="provider-panel" aria-label="Provider import">
      <div className="provider-header">
        <h2>Provider</h2>
        <span title={headerStatus}>{headerStatus}</span>
      </div>
      <div className="provider-grid">
        <label>
          <span>Source</span>
          <select value={provider} disabled={disabled} onChange={(event) => handleProviderChange(event.target.value as ProviderKind)}>
            <option value="yike">Yike</option>
            <option value="fox">Fox</option>
          </select>
        </label>
        <button onClick={() => void handlePreviewYikeUrl()} disabled={!canPreviewYike}>Preview</button>
      </div>
      <label>
        <span>{provider === "yike" ? "URL" : "Command / chessid"}</span>
        <input
          value={sourceUrl}
          disabled={disabled}
          placeholder={provider === "yike" ? "Yike room or live URL" : "123456, chessid 123456, uid 123 [last_code], or user_name name"}
          onChange={(event) => {
            setSourceUrl(event.target.value);
            setDescriptor(null);
            setProviderWarnings([]);
          }}
        />
      </label>
      <p className="provider-status" title={statuses.preview}>{statuses.preview}</p>
      {descriptor ? (
        <dl className="provider-preview">
          <div>
            <dt>Kind</dt>
            <dd>{yikeRoomKindLabel(descriptor.room_kind)}</dd>
          </div>
          <div>
            <dt>ID</dt>
            <dd>{descriptor.id}</dd>
          </div>
          <div>
            <dt>Request</dt>
            <dd title={descriptor.request_url}>{descriptor.request_url}</dd>
          </div>
        </dl>
      ) : null}
      <button onClick={() => void (provider === "yike" ? handleFetchYikeAndImport() : handleFetchFoxAndImport())} disabled={provider === "yike" ? !canFetchYike : !canFetchFox}>
        Fetch &amp; import
      </button>
      <p className="provider-status" title={statuses.fetch}>{statuses.fetch}</p>
      <label className="provider-payload-label">
        <span>Payload / SGF</span>
        <textarea
          className="provider-payload"
          value={payload}
          disabled={disabled}
          spellCheck={false}
          aria-label="Provider payload or SGF"
          placeholder='Paste raw SGF or JSON with "sgf", "clean_sgf", or "chess".'
          onChange={(event) => {
            setPayload(event.target.value);
            setProviderWarnings([]);
          }}
        />
      </label>
      <button onClick={() => void handleImport()} disabled={!canImport}>Import pasted payload</button>
      <p className="provider-status" title={statuses.import}>{statuses.import}</p>
      <WarningList label="Provider warnings" warnings={providerWarnings} />

      <div className="provider-readboard">
        <div className="provider-subheader">
          <h3>Readboard protocol preview</h3>
          <span title={statuses.readboardProbe}>{statuses.readboardProbe}</span>
        </div>
        <div className="provider-grid">
          <label>
            <span>Endpoint</span>
            <input
              value={readboardEndpoint}
              disabled={disabled}
              placeholder="Optional sidecar endpoint"
              onChange={(event) => setReadboardEndpoint(event.target.value)}
            />
          </label>
          <button onClick={() => void handleReadboardProbe()} disabled={!canProbeReadboard}>Probe</button>
        </div>
        {readboardProbeResult ? (
          <dl className="provider-preview">
            <div>
              <dt>Status</dt>
              <dd>{readboardProbeResult.available ? "available" : "unavailable"}</dd>
            </div>
            <div>
              <dt>Endpoint</dt>
              <dd title={readboardProbeResult.endpoint ?? ""}>{readboardProbeResult.endpoint ?? "default"}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{readboardProbeResult.version ?? "unknown"}</dd>
            </div>
            <div>
              <dt>Warnings</dt>
              <dd title={readboardProbeResult.warnings.join("; ")}>{warningCount(readboardProbeResult.warnings)}</dd>
            </div>
          </dl>
        ) : null}
        <WarningList label="Readboard probe warnings" warnings={readboardProbeResult?.warnings ?? []} />
        <label className="provider-payload-label">
          <span>Protocol preview line</span>
          <textarea
            className="provider-payload provider-readboard-line"
            value={readboardProtocolLine}
            disabled={disabled}
            spellCheck={false}
            aria-label="Readboard protocol preview line"
            placeholder="Paste readboard snapshot protocol line for position preview"
            onChange={(event) => setReadboardProtocolLine(event.target.value)}
          />
        </label>
        <div className="provider-grid">
          <button onClick={() => void handleReadboardSync()} disabled={!canSyncReadboard}>Preview snapshot</button>
          <button onClick={() => void handleImportReadboardSnapshot()} disabled={!canImportReadboardSnapshot}>Import snapshot</button>
        </div>
        <p className="provider-status" title={statuses.readboardSync}>{statuses.readboardSync}</p>
        {readboardSyncResult ? (
          <dl className="provider-preview">
            <div>
              <dt>Snapshot</dt>
              <dd title={readboardSyncResult.snapshot_id}>{readboardSyncResult.snapshot_id}</dd>
            </div>
            <div>
              <dt>Position</dt>
              <dd>{positionStatus(readboardSyncResult)}</dd>
            </div>
            <div>
              <dt>Warnings</dt>
              <dd title={readboardSyncResult.warnings.join("; ")}>{warningCount(readboardSyncResult.warnings)}</dd>
            </div>
          </dl>
        ) : null}
        <WarningList label="Readboard snapshot warnings" warnings={readboardSyncResult?.warnings ?? []} />
      </div>
    </section>
  );
}

function WarningList({ label, warnings }: { label: string; warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="warning-list" role="status" aria-label={label}>
      <strong>{label}</strong>
      <ul>
        {warnings.slice(0, 5).map((warning, index) => (
          <li key={`${index}:${warning}`} title={warning}>{warning}</li>
        ))}
      </ul>
      {warnings.length > 5 ? <small>{warnings.length - 5} more warning(s)</small> : null}
    </div>
  );
}

function buildYikeFetchRequest(descriptor: YikeUrlDescriptor, sourceUrl: string): ProviderFetchRequest {
  return {
    provider: "yike",
    url: descriptor.request_url,
    method: "get",
    headers: {},
    source_url: optionalTrimmed(sourceUrl),
    source_id: descriptor.id,
    timeout_ms: providerFetchTimeoutMs
  };
}

function buildFoxFetchRequest(input: FoxFetchInput): ProviderFetchRequest {
  return {
    provider: "fox",
    url: input.url,
    method: "get",
    headers: {},
    source_url: input.sourceUrl,
    source_id: input.sourceId,
    timeout_ms: providerFetchTimeoutMs
  };
}

function buildRequest(provider: ProviderKind, payload: string, sourceUrl: string, descriptor: YikeUrlDescriptor | null): ProviderImportRequest {
  const trimmedSourceUrl = sourceUrl.trim();
  const metadata = emptyProviderMetadata();
  if (trimmedSourceUrl) metadata.source_url = trimmedSourceUrl;
  if (descriptor) {
    metadata.request_url = descriptor.request_url;
    metadata.source_id = descriptor.id;
    metadata.room_id = String(descriptor.room_id);
    metadata.extra.room_kind = descriptor.room_kind;
  }
  return {
    provider,
    payload,
    source_url: trimmedSourceUrl || null,
    source_id: descriptor?.id ?? null,
    metadata
  };
}

function buildFetchImportRequest(result: ProviderFetchResult, fallbackSourceUrl: string | null, fallbackSourceId: string | null): ProviderImportRequest {
  const metadata = normalizeMetadata({
    ...result.metadata,
    request_url: result.metadata.request_url ?? result.url,
    source_url: result.metadata.source_url ?? fallbackSourceUrl,
    source_id: result.metadata.source_id ?? fallbackSourceId,
    extra: {
      ...(result.metadata.extra ?? {}),
      status_code: String(result.status_code),
      content_type: result.content_type ?? ""
    }
  });
  return {
    provider: result.provider,
    payload: result.payload,
    source_url: metadata.source_url,
    source_id: metadata.source_id,
    metadata
  };
}

function buildReadboardSnapshotImportResult(result: ReadboardSidecarSyncSnapshotResult, endpoint: string | null): ProviderImportResult {
  if (!result.position) throw new Error("Preview a readboard snapshot with a position before importing.");
  const sgfBuild = buildReadboardSnapshotSgf(result.position);
  const metadata = normalizeMetadata({
    source_url: endpoint,
    source_id: result.snapshot_id,
    title: `Readboard snapshot ${result.snapshot_id}`,
    provider_status: "snapshot_only",
    extra: {
      import_kind: "readboard_snapshot",
      history_scope: "current_position_only_not_complete_game_history",
      snapshot_id: result.snapshot_id,
      board_size: String(result.position.board_size),
      move_number: String(result.position.move_number),
      to_play: result.position.to_play
    }
  });
  const warnings = [
    "Readboard snapshot import contains only the current board position; it is not a complete game history.",
    "Move order, captures, comments, clock data, and earlier variations are not reconstructed from this snapshot.",
    ...result.warnings,
    ...result.position.errors,
    ...sgfBuild.warnings
  ];
  return {
    provider: "readboard_snapshot",
    sgf_text: sgfBuild.sgfText,
    summary: {
      provider: "readboard_snapshot",
      source_id: result.snapshot_id,
      board_size: result.position.board_size,
      move_count: 0
    },
    metadata,
    warnings
  };
}

function buildReadboardSnapshotSgf(position: PositionDto): { sgfText: string; warnings: string[] } {
  const boardSize = normalizeBoardSize(position.board_size);
  const warnings: string[] = [];
  if (boardSize !== position.board_size) {
    warnings.push(`Readboard board size ${position.board_size} was normalized to ${boardSize} for SGF SZ.`);
  }

  const blackStones = uniqueSortedSgfPoints(position.stones, "black", boardSize, warnings);
  const whiteStones = uniqueSortedSgfPoints(position.stones, "white", boardSize, warnings);
  const properties = [`FF[4]`, `GM[1]`, `SZ[${boardSize}]`];
  if (blackStones.length > 0) properties.push(`AB${blackStones.map((point) => `[${point}]`).join("")}`);
  if (whiteStones.length > 0) properties.push(`AW${whiteStones.map((point) => `[${point}]`).join("")}`);
  properties.push(`PL[${playerColorSgfValue(position.to_play)}]`);
  return { sgfText: `(;${properties.join("")})`, warnings };
}

function normalizeBoardSize(boardSize: number): number {
  if (Number.isInteger(boardSize) && boardSize >= 1 && boardSize <= 52) return boardSize;
  return 19;
}

function uniqueSortedSgfPoints(stones: StoneDto[], color: PlayerColor, boardSize: number, warnings: string[]): string[] {
  const points = new Set<string>();
  for (const stone of stones) {
    if (stone.color !== color) continue;
    if (!isBoardCoordinate(stone.x, boardSize) || !isBoardCoordinate(stone.y, boardSize)) {
      warnings.push(`Skipped ${stone.color} stone outside ${boardSize}x${boardSize} board at (${stone.x}, ${stone.y}).`);
      continue;
    }
    points.add(`${sgfCoordinate(stone.x)}${sgfCoordinate(stone.y)}`);
  }
  return [...points].sort();
}

function isBoardCoordinate(value: number, boardSize: number): boolean {
  return Number.isInteger(value) && value >= 0 && value < boardSize;
}

function sgfCoordinate(value: number): string {
  const code = value < 26 ? 97 + value : 65 + value - 26;
  return String.fromCharCode(code);
}

function playerColorSgfValue(color: PlayerColor): string {
  return color === "black" ? "B" : "W";
}

function normalizeFoxFetchInput(rawInput: string): FoxFetchInput {
  const trimmed = rawInput.trim();
  if (!trimmed) throw new Error("Enter a Fox numeric chessid or command.");
  if (/^https?:\/\//i.test(trimmed)) {
    throw new Error("Fox direct http(s) URLs are not supported here. Enter a numeric chessid, chessid <id>, uid <id> [last_code], or user_name <name>.");
  }
  if (/^\d+$/.test(trimmed)) {
    return { url: `chessid ${trimmed}`, sourceUrl: null, sourceId: trimmed };
  }
  const chessidMatch = /^chessid\s+(\d+)\s*$/i.exec(trimmed);
  if (chessidMatch) {
    return { url: `chessid ${chessidMatch[1]}`, sourceUrl: null, sourceId: chessidMatch[1] };
  }
  const uidMatch = /^uid\s+(\d+)(?:\s+(\S+))?\s*$/i.exec(trimmed);
  if (uidMatch) {
    return { url: `uid ${uidMatch[1]}${uidMatch[2] ? ` ${uidMatch[2]}` : ""}`, sourceUrl: null, sourceId: uidMatch[1] };
  }
  const userNameMatch = /^user_name\s+(\S+)\s*$/i.exec(trimmed);
  if (userNameMatch) {
    return { url: `user_name ${userNameMatch[1]}`, sourceUrl: null, sourceId: userNameMatch[1] };
  }
  throw new Error("Enter a Fox numeric chessid or command: chessid <id>, uid <id> [last_code], or user_name <name>.");
}

function normalizeMetadata(metadata: ProviderGameMetadata): ProviderGameMetadata {
  return { ...metadata, extra: metadata.extra ?? {} };
}

function optionalTrimmed(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function importStatus(result: ProviderImportResult): string {
  return result.warnings.length > 0
    ? `Imported with ${result.warnings.length} warning(s).`
    : `Imported ${providerLabel(result.provider)} payload.`;
}

function providerFetchStatus(result: ProviderFetchResult, label: string): string {
  const warnings = result.warnings.length > 0 ? `, ${result.warnings.length} warning(s)` : "";
  return `${label} fetch ${result.status_code}; imported payload${warnings}.`;
}

function readboardSyncStatus(result: ReadboardSidecarSyncSnapshotResult): string {
  const position = result.position ? `position ${result.position.board_size}x${result.position.board_size} move ${result.position.move_number}` : "no position";
  const warnings = result.warnings.length > 0 ? `, ${result.warnings.length} warning(s)` : "";
  return `Snapshot preview ${result.snapshot_id}: ${position}${warnings}.`;
}

function readboardSnapshotImportStatus(result: ProviderImportResult): string {
  return `Imported readboard snapshot ${result.metadata.source_id ?? "current"} with ${result.summary.board_size ?? "unknown"}x${result.summary.board_size ?? "unknown"} position and ${result.warnings.length} warning(s).`;
}

function positionStatus(result: ReadboardSidecarSyncSnapshotResult): string {
  if (!result.position) return "none";
  return `${result.position.board_size}x${result.position.board_size}, move ${result.position.move_number}, ${result.position.stones.length} stones`;
}

function warningCount(warnings: string[]): string {
  return warnings.length === 0 ? "none" : `${warnings.length} warning(s)`;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (isErrorRecord(error) && typeof error.message === "string") return error.message;
  if (isErrorRecord(error) && typeof error.kind === "string") return error.kind;
  return String(error);
}

function isErrorRecord(value: unknown): value is { kind?: unknown; message?: unknown } {
  return typeof value === "object" && value !== null;
}
