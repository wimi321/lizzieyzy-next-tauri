import { useState } from "react";
import {
  captureReadboardExternal,
  fetchFoxProvider,
  fetchYikeProvider,
  importProviderPayload,
  parseYikeUrl,
  previewLegacyImportCaptureHelper,
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
  type ReadboardControlledTargetMetadata,
  type ReadboardExternalCaptureResult,
  type ReadboardExternalCaptureSource,
  type LegacyImportCaptureHelperKind,
  type LegacyImportCaptureHelperResult,
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
  legacyHelper: string;
};

type FoxFetchInput = {
  url: string;
  sourceUrl: string | null;
  sourceId: string | null;
};

type ReadboardPreviewKind = "none" | "protocol" | "image_path" | "image_base64" | "capture_screen" | "capture_window" | "controlled_target";

const providerFetchTimeoutMs = 15_000;
const readboardTimeoutMs = 5_000;

const initialStatuses: OperationStatus = {
  preview: "Yike URL preview ready.",
  fetch: "Provider fetch ready.",
  import: "Payload import ready.",
  readboardProbe: "Readboard probe ready.",
  readboardSync: "Protocol snapshot preview ready.",
  legacyHelper: "Legacy helper status ready."
};

export function ProviderPanel({ disabled = false, onImport }: Props) {
  const [provider, setProvider] = useState<ProviderKind>("yike");
  const [sourceUrl, setSourceUrl] = useState("");
  const [payload, setPayload] = useState("");
  const [descriptor, setDescriptor] = useState<YikeUrlDescriptor | null>(null);
  const [statuses, setStatuses] = useState<OperationStatus>(initialStatuses);
  const [readboardEndpoint, setReadboardEndpoint] = useState("");
  const [readboardProtocolLine, setReadboardProtocolLine] = useState("");
  const [readboardImagePath, setReadboardImagePath] = useState("");
  const [readboardImageBase64, setReadboardImageBase64] = useState("");
  const [readboardImageName, setReadboardImageName] = useState("");
  const [readboardCaptureWindowTitle, setReadboardCaptureWindowTitle] = useState("");
  const [readboardControlledFixtureId, setReadboardControlledFixtureId] = useState("");
  const [readboardControlledProcessId, setReadboardControlledProcessId] = useState("");
  const [readboardControlledWidth, setReadboardControlledWidth] = useState("");
  const [readboardControlledHeight, setReadboardControlledHeight] = useState("");
  const [readboardCaptureResult, setReadboardCaptureResult] = useState<ReadboardExternalCaptureResult | null>(null);
  const [readboardProbeResult, setReadboardProbeResult] = useState<ReadboardSidecarProbeResult | null>(null);
  const [readboardSyncResult, setReadboardSyncResult] = useState<ReadboardSidecarSyncSnapshotResult | null>(null);
  const [readboardPreviewKind, setReadboardPreviewKind] = useState<ReadboardPreviewKind>("none");
  const [readboardPreviewError, setReadboardPreviewError] = useState("");
  const [readboardImportConfirmed, setReadboardImportConfirmed] = useState(false);
  const [readboardReplacementObserved, setReadboardReplacementObserved] = useState(false);
  const [readboardReplacementConfirmedByUser, setReadboardReplacementConfirmedByUser] = useState(false);
  const [legacyHelperResult, setLegacyHelperResult] = useState<LegacyImportCaptureHelperResult | null>(null);
  const [providerWarnings, setProviderWarnings] = useState<string[]>([]);
  const canPreviewYike = !disabled && provider === "yike" && sourceUrl.trim().length > 0;
  const canFetchYike = !disabled && provider === "yike" && descriptor !== null;
  const canFetchFox = !disabled && provider === "fox" && sourceUrl.trim().length > 0;
  const canImport = !disabled && payload.trim().length > 0;
  const canProbeReadboard = !disabled;
  const canSyncReadboard = !disabled && readboardProtocolLine.trim().length > 0;
  const canPreviewReadboardImage = !disabled && (readboardImagePath.trim().length > 0 || readboardImageBase64.trim().length > 0);
  const canCaptureReadboardExternal = !disabled;
  const canPreviewControlledTarget = !disabled && readboardImagePath.trim().length > 0;
  const canConfirmReadboardImport = !disabled && readboardSyncResult?.position != null;
  const canImportReadboardSnapshot = canConfirmReadboardImport && readboardImportConfirmed;
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
    resetReadboardPreviewState();
    try {
      const result = await syncReadboardSidecarSnapshot({
        endpoint: optionalTrimmed(readboardEndpoint),
        sgf_text: readboardProtocolLine.trim(),
        metadata: { source: "provider_panel", input: "protocol_line" },
        timeout_ms: readboardTimeoutMs
      });
      setReadboardSyncResult(result);
      setReadboardPreviewKind("protocol");
      setReadboardPreviewError("");
      setOperationStatus("readboardSync", readboardSyncStatus(result));
    } catch (error) {
      setReadboardSyncResult(null);
      setReadboardPreviewKind("protocol");
      setReadboardPreviewError(errorMessage(error));
      setOperationStatus("readboardSync", `Readboard preview failed recoverably: ${errorMessage(error)} No SGF was imported and the board was not replaced.`);
    }
  }

  async function handleReadboardImagePreview() {
    if (!canPreviewReadboardImage) return;
    setOperationStatus("readboardSync", "Previewing controlled board image import...");
    resetReadboardPreviewState();
    try {
      const hasPath = readboardImagePath.trim().length > 0;
      const result = await syncReadboardSidecarSnapshot({
        endpoint: optionalTrimmed(readboardEndpoint),
        image_path: hasPath ? readboardImagePath.trim() : null,
        image_base64: hasPath ? null : cleanImageBase64(readboardImageBase64),
        metadata: {
          source: "provider_panel",
          input: hasPath ? "controlled_image_path" : "controlled_image_base64",
          scope: "controlled_board_image_import_mvp",
          file_name: readboardImageName
        },
        timeout_ms: readboardTimeoutMs
      });
      setReadboardSyncResult(result);
      setReadboardPreviewKind(hasPath ? "image_path" : "image_base64");
      setReadboardPreviewError("");
      setOperationStatus("readboardSync", readboardImagePreviewStatus(result));
    } catch (error) {
      setReadboardSyncResult(null);
      setReadboardPreviewKind(readboardImagePath.trim().length > 0 ? "image_path" : "image_base64");
      setReadboardPreviewError(errorMessage(error));
      setOperationStatus("readboardSync", `Controlled board image preview failed recoverably: ${errorMessage(error)} No SGF was imported and the board was not replaced.`);
    }
  }

  async function handleReadboardImageFile(file: File | null) {
    if (!file) return;
    setReadboardImageName(file.name);
    setReadboardImagePath("");
    resetReadboardPreviewState();
    setOperationStatus("readboardSync", `Loaded ${file.name} for controlled board image preview. Use Preview image before importing.`);
    try {
      const dataUrl = await readFileAsDataUrl(file);
      setReadboardImageBase64(cleanImageBase64(dataUrl));
    } catch (error) {
      setReadboardImageBase64("");
      setOperationStatus("readboardSync", `Image selection failed: ${errorMessage(error)}`);
    }
  }

  async function handleReadboardExternalCapture(source: ReadboardExternalCaptureSource) {
    if (!canCaptureReadboardExternal) return;
    setOperationStatus("readboardSync", `Starting operator-selected ${source} capture preview...`);
    resetReadboardPreviewState();
    setReadboardCaptureResult(null);
    try {
      const capture = await captureReadboardExternal({
        source,
        endpoint: optionalTrimmed(readboardEndpoint),
        window_title: source === "window" ? optionalTrimmed(readboardCaptureWindowTitle) : null,
        timeout_ms: readboardTimeoutMs,
        metadata: {
          source: "provider_panel",
          input: source === "screen" ? "operator_selected_screen_capture" : "operator_selected_window_capture",
          scope: "operator_selected_capture_mvp_not_full_ocr_or_external_client_capture"
        }
      });
      setReadboardCaptureResult(capture);
      const status = normalizeCaptureStatus(capture.status);
      if (status !== "captured") {
        setReadboardPreviewKind(source === "screen" ? "capture_screen" : "capture_window");
        setReadboardPreviewError(capture.message ?? capture.errorMessage ?? `Capture ${status}; no image preview was imported.`);
        setOperationStatus("readboardSync", readboardCaptureStatus(capture));
        return;
      }

      const directSnapshot = readboardSnapshotFromCapture(capture);
      if (directSnapshot) {
        setReadboardSyncResult(directSnapshot);
        setReadboardPreviewKind(source === "screen" ? "capture_screen" : "capture_window");
        setReadboardPreviewError("");
        setOperationStatus("readboardSync", readboardCapturePreviewStatus(capture, directSnapshot));
        return;
      }

      const imagePath = capture.image_path ?? capture.imagePath ?? null;
      const imageBase64 = capture.image_base64 ?? capture.imageBase64 ?? null;
      if (!imagePath && !imageBase64) {
        setReadboardPreviewKind(source === "screen" ? "capture_screen" : "capture_window");
        setReadboardPreviewError("Capture succeeded but did not return image data for readboard preview.");
        setOperationStatus("readboardSync", "Capture returned no image data; no import performed and the board was not replaced.");
        return;
      }

      const preview = await syncReadboardSidecarSnapshot({
        endpoint: optionalTrimmed(readboardEndpoint),
        image_path: imagePath,
        image_base64: imagePath ? null : cleanImageBase64(imageBase64 ?? ""),
        metadata: {
          source: "provider_panel",
          input: source === "screen" ? "operator_selected_screen_capture" : "operator_selected_window_capture",
          capture_status: capture.status,
          snapshot_id: capture.snapshot_id ?? capture.snapshotId ?? "",
          snapshot_hash: capture.snapshot_hash ?? capture.snapshotHash ?? capture.hash ?? "",
          scope: "operator_selected_capture_mvp_not_full_ocr_or_external_client_capture"
        },
        timeout_ms: readboardTimeoutMs
      });
      setReadboardSyncResult(preview);
      setReadboardPreviewKind(source === "screen" ? "capture_screen" : "capture_window");
      setReadboardPreviewError("");
      setOperationStatus("readboardSync", readboardCapturePreviewStatus(capture, preview));
    } catch (error) {
      setReadboardCaptureResult({
        status: normalizeCaptureStatus(errorMessage(error)),
        source,
        warnings: ["Capture preview failed recoverably. No SGF was imported and the board was not replaced."],
        message: errorMessage(error),
        recoverable: true,
        imported: false
      });
      setReadboardPreviewKind(source === "screen" ? "capture_screen" : "capture_window");
      setReadboardPreviewError(errorMessage(error));
      setOperationStatus("readboardSync", `Capture preview failed recoverably: ${errorMessage(error)} No SGF was imported and the board was not replaced.`);
    }
  }

  async function handleReadboardControlledTargetPreview() {
    if (!canPreviewControlledTarget) return;
    setOperationStatus("readboardSync", "Previewing controlled local target window/screenshot proof...");
    resetReadboardPreviewState();
    try {
      const imagePath = readboardImagePath.trim();
      const targetMetadata = readboardControlledTargetMetadata(
        readboardCaptureWindowTitle,
        readboardControlledProcessId,
        readboardControlledFixtureId,
        readboardControlledWidth,
        readboardControlledHeight,
        imagePath
      );
      const capture = await captureReadboardExternal({
        source: "controlled_local_target_window",
        endpoint: optionalTrimmed(readboardEndpoint),
        image_path: imagePath,
        imagePath,
        window_title: targetMetadata.window_title ?? null,
        windowTitle: targetMetadata.windowTitle ?? null,
        process_id: targetMetadata.process_id ?? null,
        processId: targetMetadata.processId ?? null,
        fixture_id: targetMetadata.fixture_id ?? null,
        fixtureId: targetMetadata.fixtureId ?? null,
        width: targetMetadata.width ?? null,
        height: targetMetadata.height ?? null,
        controlledLocalTargetWindow: true,
        controlled_local_target_window: true,
        controlledTarget: targetMetadata,
        controlled_target: targetMetadata,
        timeout_ms: readboardTimeoutMs,
        metadata: {
          source: "provider_panel",
          input: "controlled_local_target_window",
          scope: "controlled_target_screenshot_proof_not_full_ocr_or_external_client_parity",
          fixture_id: targetMetadata.fixture_id ?? "",
          window_title: targetMetadata.window_title ?? "",
          process_id: targetMetadata.process_id === null || targetMetadata.process_id === undefined ? "" : String(targetMetadata.process_id),
          width: targetMetadata.width === null || targetMetadata.width === undefined ? "" : String(targetMetadata.width),
          height: targetMetadata.height === null || targetMetadata.height === undefined ? "" : String(targetMetadata.height)
        }
      });
      setReadboardCaptureResult(capture);
      const status = normalizeCaptureStatus(capture.status);
      if (status !== "captured") {
        setReadboardPreviewKind("controlled_target");
        setReadboardPreviewError(capture.message ?? capture.errorMessage ?? `Controlled target proof ${status}; no image preview was imported.`);
        setOperationStatus("readboardSync", readboardCaptureStatus(capture));
        return;
      }

      const directSnapshot = readboardSnapshotFromCapture(capture);
      if (directSnapshot) {
        setReadboardSyncResult(directSnapshot);
        setReadboardPreviewKind("controlled_target");
        setReadboardPreviewError("");
        setOperationStatus("readboardSync", readboardCapturePreviewStatus(capture, directSnapshot));
        return;
      }

      const imageBase64 = capture.image_base64 ?? capture.imageBase64 ?? null;
      const preview = await syncReadboardSidecarSnapshot({
        endpoint: optionalTrimmed(readboardEndpoint),
        image_path: capture.image_path ?? capture.imagePath ?? imagePath,
        image_base64: capture.image_path || capture.imagePath || imagePath ? null : cleanImageBase64(imageBase64 ?? ""),
        metadata: {
          source: "provider_panel",
          input: "controlled_local_target_window",
          capture_status: capture.status,
          snapshot_id: capture.snapshot_id ?? capture.snapshotId ?? "",
          snapshot_hash: capture.snapshot_hash ?? capture.snapshotHash ?? capture.hash ?? "",
          scope: "controlled_target_screenshot_proof_not_full_ocr_or_external_client_parity",
          ...stringifyMetadata(readboardControlledTargetMetadataFromResult(capture, targetMetadata))
        },
        timeout_ms: readboardTimeoutMs
      });
      setReadboardSyncResult(preview);
      setReadboardPreviewKind("controlled_target");
      setReadboardPreviewError("");
      setOperationStatus("readboardSync", readboardCapturePreviewStatus(capture, preview));
    } catch (error) {
      setReadboardCaptureResult({
        status: normalizeCaptureStatus(errorMessage(error)),
        source: "controlled_local_target_window",
        warnings: ["Controlled target proof failed recoverably. No SGF was imported and the board was not replaced."],
        message: errorMessage(error),
        recoverable: true,
        imported: false,
        controlledLocalTargetWindow: true
      });
      setReadboardPreviewKind("controlled_target");
      setReadboardPreviewError(errorMessage(error));
      setOperationStatus("readboardSync", `Controlled target preview failed recoverably: ${errorMessage(error)} No SGF was imported and the board was not replaced.`);
    }
  }

  async function handleImportReadboardSnapshot() {
    if (!readboardSyncResult?.position || !readboardImportConfirmed) return;
    setOperationStatus("readboardSync", "Importing readboard snapshot...");
    try {
      const result = buildReadboardSnapshotImportResult(readboardSyncResult, optionalTrimmed(readboardEndpoint));
      await onImport(result);
      setReadboardReplacementConfirmedByUser(readboardImportConfirmed);
      setReadboardReplacementObserved(true);
      setReadboardImportConfirmed(false);
      setOperationStatus("readboardSync", readboardSnapshotImportStatus(result));
    } catch (error) {
      setOperationStatus("readboardSync", `Readboard snapshot import failed: ${errorMessage(error)}`);
    }
  }

  async function handleLegacyHelperStatus(kind: LegacyImportCaptureHelperKind) {
    setOperationStatus("legacyHelper", legacyHelperPendingStatus(kind));
    try {
      const result = await previewLegacyImportCaptureHelper({
        kind,
        payload: kind === "sgf_payload" ? payload : kind === "protocol_snapshot" ? readboardProtocolLine : null,
        metadata: { source: "provider_panel_legacy_helper_surface" }
      });
      setLegacyHelperResult(result);
      setOperationStatus("legacyHelper", legacyHelperStatus(result));
    } catch (error) {
      setLegacyHelperResult({
        kind,
        status: "recoverable_unsupported",
        title: "Legacy helper unavailable",
        message: `Helper status failed: ${errorMessage(error)}. No SGF was imported and the board was not replaced.`,
        recoverable: true,
        imported: false,
        boardReplacement: "none",
        warnings: ["No stale, guessed, or partial board replacement was applied."],
        details: { no_stale_board_replacement: "true" }
      });
      setOperationStatus("legacyHelper", "Legacy helper status unavailable; no import performed.");
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

  function resetReadboardPreviewState() {
    setReadboardSyncResult(null);
    setReadboardPreviewError("");
    setReadboardPreviewKind("none");
    setReadboardImportConfirmed(false);
    setReadboardReplacementObserved(false);
    setReadboardReplacementConfirmedByUser(false);
    setReadboardCaptureResult(null);
  }

  return (
    <section
      className="provider-panel"
      aria-label="Provider import"
      data-testid="provider-panel"
      data-legacy-target="providers"
      data-provider-kind={provider}
      data-provider-preview-status={statuses.preview}
      data-provider-fetch-status={statuses.fetch}
      data-provider-import-status={statuses.import}
      data-readboard-preview-kind={readboardPreviewKind}
      data-readboard-preview-has-position={String(readboardSyncResult?.position != null)}
      data-external-capture-supported="false"
    >
      <div className="provider-header" data-testid="provider-header" data-legacy-target="providers-status">
        <h2>Provider</h2>
        <span data-testid="provider-header-status" title={headerStatus}>{headerStatus}</span>
      </div>
      <div className="provider-grid" data-testid="provider-source-target" data-legacy-target="providers-source">
        <label>
          <span>Source</span>
          <select data-testid="provider-source-select" value={provider} disabled={disabled} onChange={(event) => handleProviderChange(event.target.value as ProviderKind)}>
            <option value="yike">Yike</option>
            <option value="fox">Fox</option>
          </select>
        </label>
        <button data-testid="provider-preview" onClick={() => void handlePreviewYikeUrl()} disabled={!canPreviewYike}>Preview</button>
      </div>
      <label>
        <span>{provider === "yike" ? "URL" : "Command / chessid"}</span>
          <input
            data-testid="provider-source-input"
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
      <p className="provider-status" data-testid="provider-preview-status" title={statuses.preview}>{statuses.preview}</p>
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
      <button data-testid="provider-fetch-import" data-legacy-target="providers-fetch" onClick={() => void (provider === "yike" ? handleFetchYikeAndImport() : handleFetchFoxAndImport())} disabled={provider === "yike" ? !canFetchYike : !canFetchFox}>
        Fetch &amp; import
      </button>
      <p className="provider-status" data-testid="provider-fetch-status" title={statuses.fetch}>{statuses.fetch}</p>
      <label className="provider-payload-label">
        <span>Payload / SGF</span>
          <textarea
            data-testid="provider-payload-textarea"
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
      <button data-testid="provider-import-payload" data-legacy-target="providers-import" onClick={() => void handleImport()} disabled={!canImport}>Import pasted payload</button>
      <p className="provider-status" data-testid="provider-import-status" title={statuses.import}>{statuses.import}</p>
      <WarningList label="Provider warnings" warnings={providerWarnings} />

      <div
        className="provider-readboard"
        data-testid="controlled-board-image-import-mvp"
        data-legacy-target="provider-readboard"
        data-preview-kind={readboardPreviewKind}
        data-preview-has-position={String(readboardSyncResult?.position != null)}
        data-preview-confirmed={String(readboardImportConfirmed)}
        data-user-confirmed={String(readboardImportConfirmed || readboardReplacementConfirmedByUser)}
        data-can-import-preview={String(canImportReadboardSnapshot)}
        data-controlled-local-target-window={String(readboardPreviewKind === "controlled_target" || readboardCaptureControlledTarget(readboardCaptureResult))}
        data-preview-before-confirmation={String(readboardSyncResult?.position != null && !readboardImportConfirmed && !readboardReplacementObserved)}
        data-preview-only-before-confirmation={String(readboardSyncResult?.position != null && !readboardImportConfirmed && !readboardReplacementObserved)}
        data-board-replaced-before-confirmation="false"
        data-board-replacement-observed={String(readboardReplacementObserved)}
        data-board-replaced-only-after-confirmation={String(readboardReplacementObserved && readboardReplacementConfirmedByUser)}
        data-arbitrary-ocr-parity="false"
        data-target-client-parity="false"
        data-full-readboard-parity="false"
        data-release-parity="false"
        data-no-full-ocr-parity="true"
        data-no-target-client-parity="true"
        data-no-release-parity="true"
      >
        <div className="provider-subheader" data-testid="readboard-preview-header" data-legacy-target="provider-readboard-status">
          <h3>Readboard preview and controlled image import</h3>
          <span title={statuses.readboardProbe}>{statuses.readboardProbe}</span>
        </div>
        <p className="provider-status">
          Controlled board image import MVP accepts a selected board image, an explicit image path, or pasted image base64 and previews the extracted current position before import. It is not full OCR parity, arbitrary screenshot capture, or external client/window capture.
        </p>
        <div
          className="provider-subheader"
          data-testid="readboard-external-capture-target"
          data-legacy-target="provider-external-capture"
          data-external-capture-supported="false"
          data-readboard-capture-status={readboardCaptureResult ? normalizeCaptureStatus(readboardCaptureResult.status) : "ready"}
        >
          <h4>Capture from screen/window</h4>
          <span data-testid="readboard-external-capture-status" title={readboardCaptureResult?.message ?? statuses.readboardSync}>
            {readboardCaptureResult ? normalizeCaptureStatus(readboardCaptureResult.status) : "ready"}
          </span>
        </div>
        <p className="provider-status" data-testid="readboard-external-capture-boundary">
          Operator-selected capture MVP can preview a chosen screen or window image through readboard. It is not full OCR, external client automation, or automatic board replacement.
        </p>
        <div className="provider-grid">
          <label>
            <span>Window title</span>
            <input
              data-testid="readboard-capture-window-title-input"
              value={readboardCaptureWindowTitle}
              disabled={disabled}
              placeholder="Optional window title hint"
              onChange={(event) => setReadboardCaptureWindowTitle(event.target.value)}
            />
          </label>
          <button data-testid="readboard-capture-window" onClick={() => void handleReadboardExternalCapture("window")} disabled={!canCaptureReadboardExternal}>Capture window</button>
        </div>
        <div className="provider-grid provider-capture-actions">
          <button data-testid="readboard-capture-screen" onClick={() => void handleReadboardExternalCapture("screen")} disabled={!canCaptureReadboardExternal}>Capture screen</button>
          <button data-testid="readboard-import-captured-snapshot" onClick={() => void handleImportReadboardSnapshot()} disabled={!canImportReadboardSnapshot}>Import confirmed capture</button>
        </div>
        {readboardCaptureResult ? (
          <dl className="provider-preview" data-testid="readboard-external-capture-summary">
            <div>
              <dt>Status</dt>
              <dd>{normalizeCaptureStatus(readboardCaptureResult.status)}</dd>
            </div>
            <div>
              <dt>Capture source</dt>
              <dd>{readboardCaptureSourceLabel(readboardCaptureResult)}</dd>
            </div>
            <div>
              <dt>Snapshot hash</dt>
              <dd title={readboardCaptureHash(readboardCaptureResult) ?? ""}>{readboardCaptureHash(readboardCaptureResult) ?? "not reported"}</dd>
            </div>
            <div>
              <dt>Sanitized path</dt>
              <dd title={readboardCaptureResult.sanitizedPath ?? ""}>{readboardCaptureResult.sanitizedPath ?? "not reported"}</dd>
            </div>
            <div>
              <dt>Bytes</dt>
              <dd>{readboardCaptureSize(readboardCaptureResult) ?? "not reported"}</dd>
            </div>
            <div>
              <dt>Target</dt>
              <dd title={readboardControlledTargetSummary(readboardCaptureResult)}>{readboardControlledTargetSummary(readboardCaptureResult)}</dd>
            </div>
            <div>
              <dt>Fixture</dt>
              <dd>{readboardControlledTargetValue(readboardCaptureResult, "fixture") ?? "not reported"}</dd>
            </div>
            <div>
              <dt>Board size</dt>
              <dd>{readboardCapturePosition(readboardCaptureResult) ? `${readboardCapturePosition(readboardCaptureResult)?.board_size}x${readboardCapturePosition(readboardCaptureResult)?.board_size}` : readboardSyncResult?.position ? `${readboardSyncResult.position.board_size}x${readboardSyncResult.position.board_size}` : "not previewed"}</dd>
            </div>
            <div>
              <dt>Stones</dt>
              <dd>{readboardCapturePosition(readboardCaptureResult)?.stones.length ?? readboardSyncResult?.position?.stones.length ?? 0}</dd>
            </div>
            <div>
              <dt>Warnings</dt>
              <dd title={readboardCaptureResult.warnings.join("; ")}>{warningCount(readboardCaptureResult.warnings)}</dd>
            </div>
          </dl>
        ) : null}
        <WarningList label="Readboard capture warnings" warnings={readboardCaptureResult?.warnings ?? []} />
        <div className="provider-grid">
          <label>
            <span>Endpoint</span>
              <input
                data-testid="readboard-endpoint-input"
                value={readboardEndpoint}
              disabled={disabled}
              placeholder="Optional sidecar endpoint"
              onChange={(event) => setReadboardEndpoint(event.target.value)}
            />
          </label>
            <button data-testid="readboard-probe" onClick={() => void handleReadboardProbe()} disabled={!canProbeReadboard}>Probe</button>
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
        <div
          className="provider-subheader"
          data-testid="readboard-image-import-target"
          data-legacy-target="provider-readboard-image"
          data-readboard-image-status={statuses.readboardSync}
        >
          <h4>Choose image / image path route</h4>
          <span data-testid="readboard-image-import-status" title={statuses.readboardSync}>{statuses.readboardSync}</span>
        </div>
        <div className="provider-grid">
          <label>
            <span>Image path</span>
            <input
              data-testid="readboard-image-path-input"
              value={readboardImagePath}
              disabled={disabled}
              placeholder="Controlled board image path in desktop runtime"
              onChange={(event) => {
                setReadboardImagePath(event.target.value);
                if (event.target.value.trim()) setReadboardImageBase64("");
                resetReadboardPreviewState();
              }}
            />
          </label>
          <label className="file-button">
            Choose image
            <input
              data-testid="readboard-image-file-input"
              type="file"
              accept="image/*"
              disabled={disabled}
              onChange={(event) => {
                void handleReadboardImageFile(event.target.files?.[0] ?? null);
                event.currentTarget.value = "";
              }}
            />
          </label>
        </div>
        <label className="provider-payload-label">
          <span>Image base64</span>
          <textarea
            data-testid="readboard-image-base64-textarea"
            className="provider-payload provider-readboard-line"
            value={readboardImageBase64}
            disabled={disabled}
            spellCheck={false}
            aria-label="Controlled board image base64"
            placeholder="Paste a controlled board image data URL or base64. Preview is required before import."
            onChange={(event) => {
              setReadboardImageBase64(event.target.value);
              if (event.target.value.trim()) setReadboardImagePath("");
              resetReadboardPreviewState();
            }}
          />
        </label>
        <section
          className="provider-controlled-target"
          data-testid="readboard-controlled-target-proof"
          data-controlled-local-target-window={String(readboardPreviewKind === "controlled_target" || readboardCaptureControlledTarget(readboardCaptureResult))}
          data-preview-before-confirmation={String(readboardSyncResult?.position != null && !readboardImportConfirmed && !readboardReplacementObserved)}
          data-no-full-ocr-parity="true"
          data-no-target-client-parity="true"
          data-no-release-parity="true"
        >
          <div className="provider-subheader">
            <h4>Controlled target window/screenshot proof</h4>
            <span>scoped proof</span>
          </div>
          <p className="provider-status">
            Uses an explicit image path plus target metadata to prove a controlled local target window/screenshot route. It does not claim arbitrary OCR, external client automation, or release parity.
          </p>
          <div className="provider-grid provider-target-metadata-grid">
            <label>
              <span>Fixture id</span>
              <input
                data-testid="readboard-controlled-target-fixture-id-input"
                value={readboardControlledFixtureId}
                disabled={disabled}
                placeholder="controlled-board-fixture"
                onChange={(event) => setReadboardControlledFixtureId(event.target.value)}
              />
            </label>
            <label>
              <span>Process id</span>
              <input
                data-testid="readboard-controlled-target-process-id-input"
                value={readboardControlledProcessId}
                disabled={disabled}
                inputMode="numeric"
                placeholder="optional pid"
                onChange={(event) => setReadboardControlledProcessId(event.target.value)}
              />
            </label>
          </div>
          <div className="provider-grid provider-target-metadata-grid">
            <label>
              <span>Width</span>
              <input
                data-testid="readboard-controlled-target-width-input"
                value={readboardControlledWidth}
                disabled={disabled}
                inputMode="numeric"
                placeholder="optional"
                onChange={(event) => setReadboardControlledWidth(event.target.value)}
              />
            </label>
            <label>
              <span>Height</span>
              <input
                data-testid="readboard-controlled-target-height-input"
                value={readboardControlledHeight}
                disabled={disabled}
                inputMode="numeric"
                placeholder="optional"
                onChange={(event) => setReadboardControlledHeight(event.target.value)}
              />
            </label>
          </div>
          <button
            type="button"
            data-testid="readboard-preview-controlled-target"
            onClick={() => void handleReadboardControlledTargetPreview()}
            disabled={!canPreviewControlledTarget}
          >
            Preview controlled target
          </button>
        </section>
        <div className="provider-grid">
          <button data-testid="readboard-preview-image" onClick={() => void handleReadboardImagePreview()} disabled={!canPreviewReadboardImage}>Preview image</button>
          <button data-testid="readboard-import-image-snapshot" onClick={() => void handleImportReadboardSnapshot()} disabled={!canImportReadboardSnapshot}>Import confirmed preview</button>
        </div>
        <p className="provider-status" data-testid="readboard-image-boundary">
          Image import is scoped to controlled board images and imports only the previewed current position. Failed preview is recoverable and does not import or replace the board.
        </p>
        <label className="provider-payload-label">
          <span>Protocol preview line</span>
            <textarea
              data-testid="readboard-protocol-textarea"
              className="provider-payload provider-readboard-line"
            value={readboardProtocolLine}
            disabled={disabled}
            spellCheck={false}
            aria-label="Readboard protocol preview line"
            placeholder="Paste readboard snapshot protocol line for position preview"
            onChange={(event) => {
              setReadboardProtocolLine(event.target.value);
              resetReadboardPreviewState();
            }}
          />
        </label>
        <div className="provider-grid">
            <button data-testid="readboard-preview-snapshot" onClick={() => void handleReadboardSync()} disabled={!canSyncReadboard}>Preview snapshot</button>
            <button data-testid="readboard-import-snapshot" onClick={() => void handleImportReadboardSnapshot()} disabled={!canImportReadboardSnapshot}>Import confirmed snapshot</button>
        </div>
        <p className="provider-status" title={statuses.readboardSync}>{statuses.readboardSync}</p>
        {readboardPreviewError ? (
          <div className="warning-list" role="alert" data-testid="readboard-preview-error">
            <strong>Preview failed recoverably</strong>
            <p>{readboardPreviewError}</p>
            <small>No SGF was imported and the current board was not replaced.</small>
          </div>
        ) : null}
        {readboardSyncResult ? (
          <dl
            className="provider-preview"
            data-testid="readboard-snapshot-preview-summary"
            data-legacy-target="provider-readboard-preview"
            data-preview-kind={readboardPreviewKind}
            data-preview-has-position={String(readboardSyncResult.position != null)}
            data-preview-stone-count={readboardSyncResult.position?.stones.length ?? 0}
            data-controlled-local-target-window={String(readboardPreviewKind === "controlled_target")}
          >
            <div>
              <dt>Snapshot</dt>
              <dd title={readboardSnapshotId(readboardSyncResult)}>{readboardSnapshotId(readboardSyncResult)}</dd>
            </div>
            <div>
              <dt>Hash</dt>
              <dd title={readboardSnapshotHash(readboardSyncResult) ?? ""}>{readboardSnapshotHash(readboardSyncResult) ?? "not reported"}</dd>
            </div>
            <div>
              <dt>Board size</dt>
              <dd>{readboardSyncResult.position ? `${readboardSyncResult.position.board_size}x${readboardSyncResult.position.board_size}` : "none"}</dd>
            </div>
            <div>
              <dt>Move</dt>
              <dd>{readboardSyncResult.position?.move_number ?? "unknown"}</dd>
            </div>
            <div>
              <dt>Stones</dt>
              <dd>{readboardSyncResult.position?.stones.length ?? 0}</dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{readboardConfidence(readboardSyncResult)}</dd>
            </div>
            <div>
              <dt>To play</dt>
              <dd>{readboardSyncResult.position ? colorLabel(readboardSyncResult.position.to_play) : "unknown"}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd title={readboardSourceMetadata(readboardSyncResult, readboardPreviewKind).join("; ")}>{readboardPreviewSourceLabel(readboardPreviewKind)}</dd>
            </div>
            <div>
              <dt>Metadata</dt>
              <dd title={readboardSourceMetadata(readboardSyncResult, readboardPreviewKind).join("; ")}>{readboardSourceMetadata(readboardSyncResult, readboardPreviewKind).slice(0, 3).join("; ")}</dd>
            </div>
            <div>
              <dt>Warnings</dt>
              <dd title={readboardSyncResult.warnings.join("; ")}>{warningCount(readboardSyncResult.warnings)}</dd>
            </div>
          </dl>
        ) : null}
        {readboardSyncResult ? (
          <div
            className="migration-result"
            data-testid="readboard-import-confirmation"
            data-legacy-target="provider-readboard-confirmation"
            data-user-confirmed={String(readboardImportConfirmed)}
            data-can-import-preview={String(canImportReadboardSnapshot)}
          >
            <label className="toggle-row">
              <span>Confirm current-position import</span>
              <input
                type="checkbox"
                data-testid="readboard-confirm-import"
                checked={readboardImportConfirmed}
                disabled={!canConfirmReadboardImport}
                onChange={(event) => setReadboardImportConfirmed(event.target.checked)}
              />
            </label>
            <small>
              Import replaces the current board with the previewed snapshot SGF only after this confirmation. It does not reconstruct full game history or external capture/OCR parity.
            </small>
          </div>
        ) : null}
        <WarningList label="Readboard snapshot warnings" warnings={readboardSyncResult?.warnings ?? []} />
      </div>

      <section
        className="legacy-import-helper"
        aria-label="Legacy import and capture helpers"
        data-testid="legacy-import-capture-helper-surface"
        data-legacy-target="legacy-import-capture"
        data-external-window-capture-supported="false"
        data-external-client-capture-supported="false"
        data-full-ocr-parity="false"
      >
        <div className="provider-subheader">
          <h3>Legacy import/capture helpers</h3>
          <span title={statuses.legacyHelper}>{statuses.legacyHelper}</span>
        </div>
        <div className="legacy-helper-grid">
          <HelperCard
            testId="legacy-helper-sgf-payload"
            title="SGF/payload helper"
            status="available"
            detail="Paste SGF or provider JSON above, then use Import pasted payload."
            actionLabel="Show payload path"
            disabled={disabled}
            onAction={() => void handleLegacyHelperStatus("sgf_payload")}
          />
          <HelperCard
            testId="legacy-helper-protocol-snapshot"
            title="Protocol snapshot helper"
            status="available"
            detail="Paste a readboard protocol line, preview it, then import only after a position is shown."
            actionLabel="Show snapshot path"
            disabled={disabled}
            onAction={() => void handleLegacyHelperStatus("protocol_snapshot")}
          />
          <HelperCard
            testId="legacy-helper-ocr-unsupported"
            title="Controlled board image import"
            status="scoped MVP"
            detail="Use the controlled board image import fields above. Arbitrary screenshots and full OCR parity remain out of scope."
            actionLabel="Show image import scope"
            disabled={disabled}
            onAction={() => void handleLegacyHelperStatus("image_ocr")}
          />
          <HelperCard
            testId="legacy-helper-external-capture-unsupported"
            title="External window/client capture"
            status="recoverable unsupported"
            detail="External client/window capture is not implemented here; it will not import SGF or replace the board."
            actionLabel="Check capture status"
            disabled={disabled}
            onAction={() => void handleLegacyHelperStatus("external_window_capture")}
          />
          <HelperCard
            testId="legacy-helper-external-client-unsupported"
            title="External client protocol capture"
            status="recoverable unsupported"
            detail="External client capture remains a visible unsupported boundary; use controlled import paths instead."
            actionLabel="Check client status"
            disabled={disabled}
            onAction={() => void handleLegacyHelperStatus("external_client_capture")}
          />
        </div>
        <p className="provider-status" data-testid="legacy-helper-no-board-replacement">
          External capture helpers remain recoverable unsupported boundaries: no SGF import is performed and the board was not replaced with guessed, stale, or partial data.
        </p>
        {legacyHelperResult ? (
          <dl className="provider-preview legacy-helper-result" data-testid="legacy-helper-status">
            <div>
              <dt>Helper</dt>
              <dd>{legacyHelperResult.title}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{legacyHelperResult.status}</dd>
            </div>
            <div>
              <dt>Import</dt>
              <dd>{legacyHelperResult.imported ? "imported" : "not imported"}</dd>
            </div>
            <div>
              <dt>Board</dt>
              <dd>{legacyHelperResult.boardReplacement === "none" ? "not replaced" : legacyHelperResult.boardReplacement}</dd>
            </div>
            <div>
              <dt>Message</dt>
              <dd title={legacyHelperResult.message}>{legacyHelperResult.message}</dd>
            </div>
          </dl>
        ) : null}
        <WarningList label="Legacy helper warnings" warnings={legacyHelperResult?.warnings ?? []} />
      </section>
    </section>
  );
}

function HelperCard({
  testId,
  title,
  status,
  detail,
  actionLabel,
  disabled,
  onAction
}: {
  testId: string;
  title: string;
  status: string;
  detail: string;
  actionLabel: string;
  disabled: boolean;
  onAction: () => void;
}) {
  return (
    <section className="legacy-helper-card" data-testid={testId}>
      <div>
        <strong>{title}</strong>
        <span>{status}</span>
      </div>
      <p>{detail}</p>
      <button type="button" disabled={disabled} onClick={onAction}>{actionLabel}</button>
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
  const snapshotId = readboardSnapshotId(result);
  const snapshotHash = readboardSnapshotHash(result);
  const sourceMetadata = readboardResultMetadata(result);
  const metadata = normalizeMetadata({
    source_url: endpoint,
    source_id: snapshotId,
    title: `Readboard snapshot ${snapshotId}`,
    provider_status: "snapshot_only",
    extra: {
      import_kind: "readboard_snapshot",
      history_scope: "current_position_only_not_complete_game_history",
      snapshot_id: snapshotId,
      snapshot_hash: snapshotHash ?? "",
      confidence: String(result.confidence ?? ""),
      board_size: String(result.position.board_size),
      move_number: String(result.position.move_number),
      to_play: result.position.to_play,
      ...sourceMetadata
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
      source_id: snapshotId,
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
  return `Snapshot preview ${readboardSnapshotId(result)}: ${position}${warnings}.`;
}

function readboardImagePreviewStatus(result: ReadboardSidecarSyncSnapshotResult): string {
  const snapshotId = readboardSnapshotId(result);
  if (!result.position) return `Controlled board image preview ${snapshotId}: no position extracted; no import performed.`;
  return `Controlled board image preview ${snapshotId}: ${result.position.board_size}x${result.position.board_size}, ${result.position.stones.length} stones, ${colorLabel(result.position.to_play)} to play. Confirm before import.`;
}

function readboardCaptureStatus(result: ReadboardExternalCaptureResult): string {
  const status = normalizeCaptureStatus(result.status);
  if (status === "captured" && readboardCaptureControlledTarget(result)) return "Controlled local target captured; preview is required before import.";
  if (status === "captured") return `Operator-selected ${readboardCaptureSourceLabel(result)} captured; preview is required before import.`;
  return `Capture ${status}: ${result.message ?? result.errorMessage ?? "recoverable; no SGF imported and board not replaced."}`;
}

function readboardCapturePreviewStatus(result: ReadboardExternalCaptureResult, preview: ReadboardSidecarSyncSnapshotResult): string {
  const source = readboardCaptureSourceLabel(result);
  const prefix = readboardCaptureControlledTarget(result) ? "Controlled local target" : `Operator-selected ${source} capture`;
  if (!preview.position) return `${prefix} preview ${readboardSnapshotId(preview)}: no board position extracted; no import performed.`;
  return `${prefix} preview ${readboardSnapshotId(preview)}: ${preview.position.board_size}x${preview.position.board_size}, ${preview.position.stones.length} stones, ${colorLabel(preview.position.to_play)} to play. Confirm before import.`;
}

function readboardSnapshotImportStatus(result: ProviderImportResult): string {
  return `Imported readboard snapshot ${result.metadata.source_id ?? "current"} with ${result.summary.board_size ?? "unknown"}x${result.summary.board_size ?? "unknown"} position and ${result.warnings.length} warning(s).`;
}

function legacyHelperPendingStatus(kind: LegacyImportCaptureHelperKind): string {
  if (kind === "image_ocr") return "Checking controlled image import / external OCR helper boundary...";
  if (kind === "external_window_capture" || kind === "external_client_capture") return "Checking external capture helper boundary...";
  return "Checking legacy import helper path...";
}

function legacyHelperStatus(result: LegacyImportCaptureHelperResult): string {
  if (result.status === "available") return `${result.title} available; no import performed yet.`;
  return `${result.title}: recoverable unsupported; no import performed and board not replaced.`;
}

function positionStatus(result: ReadboardSidecarSyncSnapshotResult): string {
  if (!result.position) return "none";
  return `${result.position.board_size}x${result.position.board_size}, move ${result.position.move_number}, ${result.position.stones.length} stones`;
}

function readboardSnapshotId(result: ReadboardSidecarSyncSnapshotResult): string {
  return result.snapshot_id || result.snapshotId || "unreported snapshot";
}

function readboardSnapshotHash(result: ReadboardSidecarSyncSnapshotResult): string | null {
  return result.snapshot_hash ?? result.snapshotHash ?? result.hash ?? null;
}

function readboardConfidence(result: ReadboardSidecarSyncSnapshotResult): string {
  const confidence = result.confidence;
  if (confidence === null || confidence === undefined || confidence === "") return "not reported";
  if (typeof confidence === "number") {
    const value = confidence <= 1 ? confidence * 100 : confidence;
    return `${value.toFixed(value >= 10 ? 1 : 2)}%`;
  }
  return confidence;
}

function readboardPreviewSourceLabel(kind: ReadboardPreviewKind): string {
  if (kind === "image_path") return "controlled image path";
  if (kind === "image_base64") return "controlled image base64";
  if (kind === "capture_screen") return "operator-selected screen capture";
  if (kind === "capture_window") return "operator-selected window capture";
  if (kind === "controlled_target") return "controlled target window/screenshot proof";
  if (kind === "protocol") return "protocol snapshot line";
  return "not reported";
}

function readboardSnapshotFromCapture(result: ReadboardExternalCaptureResult): ReadboardSidecarSyncSnapshotResult | null {
  if (!result.position) return null;
  return {
    snapshot_id: result.snapshot_id ?? result.snapshotId ?? "captured-preview",
    snapshot_hash: readboardCaptureHash(result),
    hash: readboardCaptureHash(result),
    confidence: result.confidence ?? null,
    source: readboardCaptureSourceLabel(result),
    source_metadata: {
      capture_status: normalizeCaptureStatus(result.status),
      capture_source: readboardCaptureSourceLabel(result),
      sanitized_path: result.sanitizedPath ?? "",
      sha256: result.sha256 ?? "",
      size: readboardCaptureSize(result) === null ? "" : String(readboardCaptureSize(result)),
      decode: typeof result.decode === "string" ? result.decode : result.decode ? JSON.stringify(result.decode) : "",
      scope: "operator_selected_capture_mvp_not_full_ocr_or_external_client_capture",
      ...stringifyMetadata(readboardControlledTargetMetadataFromResult(result, null))
    },
    position: result.position,
    warnings: result.warnings
  };
}

function normalizeCaptureStatus(value: unknown): string {
  const status = typeof value === "string" ? value.toLowerCase() : "";
  if (status.includes("captured") || status === "ok" || status === "success") return "captured";
  if (status.includes("cancel")) return "cancelled";
  if (status.includes("permission") || status.includes("denied")) return "permission";
  if (status.includes("decode") || status.includes("image")) return "decode_error";
  if (status.includes("unsupported") || status.includes("browser preview") || status.includes("unknown command")) return "unsupported";
  return status || "error";
}

function readboardCaptureSourceLabel(result: ReadboardExternalCaptureResult): string {
  if (result.source === "window") return "window";
  if (result.source === "screen") return "screen";
  if (result.source === "controlled_local_target_window" || readboardCaptureControlledTarget(result)) return "controlled target";
  return String(result.source || "capture");
}

function readboardCaptureHash(result: ReadboardExternalCaptureResult): string | null {
  return result.snapshot_hash ?? result.snapshotHash ?? result.hash ?? result.sha256 ?? null;
}

function readboardCaptureSize(result: ReadboardExternalCaptureResult): number | null {
  return result.size ?? result.sizeBytes ?? numberFromUnknown(result.artifact?.sizeBytes) ?? numberFromUnknown(result.artifact?.size) ?? null;
}

function readboardCapturePosition(result: ReadboardExternalCaptureResult): PositionDto | null {
  return result.position ?? null;
}

function readboardCaptureControlledTarget(result: ReadboardExternalCaptureResult | null): boolean {
  if (!result) return false;
  return Boolean(
      result.controlledLocalTargetWindow ||
      result.controlled_local_target_window ||
      result.source === "controlled_local_target_window" ||
      readboardControlledTargetValue(result, "fixture") ||
      readboardControlledTargetValue(result, "window")
  );
}

function readboardControlledTargetSummary(result: ReadboardExternalCaptureResult): string {
  const metadata = readboardControlledTargetMetadataFromResult(result, null);
  const parts = [
    metadata.window_title ? `window ${metadata.window_title}` : "",
    metadata.process_id !== null && metadata.process_id !== undefined ? `pid ${metadata.process_id}` : "",
    metadata.fixture_id ? `fixture ${metadata.fixture_id}` : "",
    metadata.width && metadata.height ? `${metadata.width}x${metadata.height}` : ""
  ].filter(Boolean);
  return parts.length > 0 ? parts.join("; ") : readboardCaptureControlledTarget(result) ? "controlled target" : "not reported";
}

function readboardControlledTargetValue(result: ReadboardExternalCaptureResult, key: "fixture" | "window"): string | null {
  const metadata = readboardControlledTargetMetadataFromResult(result, null);
  if (key === "fixture") return metadata.fixture_id ?? null;
  return metadata.window_title ?? null;
}

function readboardResultMetadata(result: ReadboardSidecarSyncSnapshotResult): Record<string, string> {
  return stringifyMetadata(result.source_metadata ?? result.sourceMetadata ?? result.metadata ?? {});
}

function readboardSourceMetadata(result: ReadboardSidecarSyncSnapshotResult, kind: ReadboardPreviewKind): string[] {
  const entries = Object.entries(readboardResultMetadata(result)).map(([key, value]) => `${key}: ${value}`);
  if (result.source) entries.unshift(`source: ${result.source}`);
  entries.unshift(`input: ${readboardPreviewSourceLabel(kind)}`);
  return entries;
}

function readboardControlledTargetMetadata(
  windowTitle: string,
  processId: string,
  fixtureId: string,
  width: string,
  height: string,
  imagePath: string
): ReadboardControlledTargetMetadata {
  const normalizedWindowTitle = optionalTrimmed(windowTitle);
  const normalizedFixtureId = optionalTrimmed(fixtureId);
  const normalizedProcessId = positiveIntegerOrNull(processId);
  const normalizedWidth = positiveIntegerOrNull(width);
  const normalizedHeight = positiveIntegerOrNull(height);
  return {
    controlledLocalTargetWindow: true,
    controlled_local_target_window: true,
    windowTitle: normalizedWindowTitle,
    window_title: normalizedWindowTitle,
    processId: normalizedProcessId,
    process_id: normalizedProcessId,
    fixtureId: normalizedFixtureId,
    fixture_id: normalizedFixtureId,
    width: normalizedWidth,
    height: normalizedHeight,
    imagePath,
    image_path: imagePath
  };
}

function readboardControlledTargetMetadataFromResult(
  result: ReadboardExternalCaptureResult,
  fallback: ReadboardControlledTargetMetadata | null
): ReadboardControlledTargetMetadata {
  const rawTarget = result.controlledTarget ?? result.controlled_target ?? result.targetMetadata ?? result.target_metadata ?? {};
  const target = isUnknownRecord(rawTarget) ? rawTarget : {};
  const sourceMetadata = stringifyMetadata(result.source_metadata ?? result.sourceMetadata ?? result.metadata ?? {});
  const windowTitle = stringFromUnknown(result.windowTitle)
    ?? stringFromUnknown(result.window_title)
    ?? stringFromUnknown(target.windowTitle)
    ?? stringFromUnknown(target.window_title)
    ?? sourceMetadata.window_title
    ?? fallback?.window_title
    ?? null;
  const fixtureId = stringFromUnknown(result.fixtureId)
    ?? stringFromUnknown(result.fixture_id)
    ?? stringFromUnknown(target.fixtureId)
    ?? stringFromUnknown(target.fixture_id)
    ?? sourceMetadata.fixture_id
    ?? fallback?.fixture_id
    ?? null;
  const processId = numberFromUnknown(result.processId)
    ?? numberFromUnknown(result.process_id)
    ?? numberFromUnknown(target.processId)
    ?? numberFromUnknown(target.process_id)
    ?? numberFromString(sourceMetadata.process_id)
    ?? fallback?.process_id
    ?? null;
  const width = numberFromUnknown(result.width)
    ?? numberFromUnknown(target.width)
    ?? numberFromString(sourceMetadata.width)
    ?? fallback?.width
    ?? null;
  const height = numberFromUnknown(result.height)
    ?? numberFromUnknown(target.height)
    ?? numberFromString(sourceMetadata.height)
    ?? fallback?.height
    ?? null;
  const imagePath = stringFromUnknown(result.imagePath)
    ?? stringFromUnknown(result.image_path)
    ?? stringFromUnknown(target.imagePath)
    ?? stringFromUnknown(target.image_path)
    ?? fallback?.image_path
    ?? null;
  return {
    controlledLocalTargetWindow: Boolean(result.controlledLocalTargetWindow ?? result.controlled_local_target_window ?? target.controlledLocalTargetWindow ?? target.controlled_local_target_window ?? fallback?.controlledLocalTargetWindow ?? false),
    controlled_local_target_window: Boolean(result.controlled_local_target_window ?? result.controlledLocalTargetWindow ?? target.controlled_local_target_window ?? target.controlledLocalTargetWindow ?? fallback?.controlled_local_target_window ?? false),
    windowTitle,
    window_title: windowTitle,
    processId,
    process_id: processId,
    fixtureId,
    fixture_id: fixtureId,
    width,
    height,
    imagePath,
    image_path: imagePath
  };
}

function stringifyMetadata(metadata: Record<string, unknown> | null | undefined): Record<string, string> {
  if (!metadata) return {};
  const normalized: Record<string, string> = {};
  for (const [key, value] of Object.entries(metadata)) {
    if (value === undefined || value === null) continue;
    normalized[key] = String(value);
  }
  return normalized;
}

function warningCount(warnings: string[]): string {
  return warnings.length === 0 ? "none" : `${warnings.length} warning(s)`;
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(new Error("Image file did not produce a base64 data URL."));
      }
    });
    reader.addEventListener("error", () => reject(reader.error ?? new Error("Image file read failed.")));
    reader.readAsDataURL(file);
  });
}

function cleanImageBase64(value: string): string {
  const trimmed = value.trim();
  const comma = trimmed.indexOf(",");
  if (/^data:image\//i.test(trimmed) && comma >= 0) return trimmed.slice(comma + 1).trim();
  return trimmed;
}

function positiveIntegerOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function stringFromUnknown(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberFromUnknown(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numberFromString(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function colorLabel(color: PlayerColor): string {
  return color === "black" ? "Black" : "White";
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

function isUnknownRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
