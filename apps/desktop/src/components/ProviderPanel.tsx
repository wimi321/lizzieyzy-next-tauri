import { useState } from "react";
import { importProviderPayload, parseYikeUrl } from "../api/providers";
import {
  emptyProviderMetadata,
  providerLabel,
  yikeRoomKindLabel,
  type ProviderImportRequest,
  type ProviderImportResult,
  type ProviderKind,
  type YikeUrlDescriptor
} from "../domain/providers";

type Props = {
  disabled?: boolean;
  onImport: (result: ProviderImportResult) => void | Promise<void>;
};

export function ProviderPanel({ disabled = false, onImport }: Props) {
  const [provider, setProvider] = useState<ProviderKind>("yike");
  const [sourceUrl, setSourceUrl] = useState("");
  const [payload, setPayload] = useState("");
  const [descriptor, setDescriptor] = useState<YikeUrlDescriptor | null>(null);
  const [status, setStatus] = useState("Payload import ready.");
  const canPreviewYike = !disabled && provider === "yike" && sourceUrl.trim().length > 0;
  const canImport = !disabled && payload.trim().length > 0;

  function handleProviderChange(nextProvider: ProviderKind) {
    setProvider(nextProvider);
    setDescriptor(null);
    setStatus(nextProvider === "yike" ? "Yike payload import ready." : "Fox payload import ready.");
  }

  async function handlePreviewYikeUrl() {
    if (!canPreviewYike) return;
    try {
      const nextDescriptor = await parseYikeUrl(sourceUrl);
      setDescriptor(nextDescriptor);
      setStatus(`${yikeRoomKindLabel(nextDescriptor.room_kind)} descriptor ready.`);
    } catch (error) {
      setDescriptor(null);
      setStatus(`URL preview failed: ${errorMessage(error)}`);
    }
  }

  async function handleImport() {
    if (!canImport) return;
    setStatus("Importing provider payload...");
    try {
      const result = await importProviderPayload(buildRequest(provider, payload, sourceUrl, descriptor));
      await onImport(result);
      setStatus(result.warnings.length > 0 ? `Imported with ${result.warnings.length} warning(s).` : `Imported ${providerLabel(result.provider)} payload.`);
    } catch (error) {
      setStatus(`Import failed: ${errorMessage(error)}`);
    }
  }

  return (
    <section className="provider-panel" aria-label="Provider import">
      <div className="provider-header">
        <h2>Provider</h2>
        <span title={status}>{status}</span>
      </div>
      <div className="provider-grid">
        <label>
          <span>Source</span>
          <select value={provider} disabled={disabled} onChange={(event) => handleProviderChange(event.target.value as ProviderKind)}>
            <option value="yike">Yike</option>
            <option value="fox">Fox</option>
          </select>
        </label>
        <button onClick={() => void handlePreviewYikeUrl()} disabled={!canPreviewYike}>Preview URL</button>
      </div>
      <label>
        <span>URL</span>
        <input
          value={sourceUrl}
          disabled={disabled}
          placeholder={provider === "yike" ? "Yike room or live URL" : "Optional source URL"}
          onChange={(event) => {
            setSourceUrl(event.target.value);
            setDescriptor(null);
          }}
        />
      </label>
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
      <label className="provider-payload-label">
        <span>Payload / SGF</span>
        <textarea
          className="provider-payload"
          value={payload}
          disabled={disabled}
          spellCheck={false}
          aria-label="Provider payload or SGF"
          placeholder='Paste raw SGF or JSON with "sgf", "clean_sgf", or "chess".'
          onChange={(event) => setPayload(event.target.value)}
        />
      </label>
      <button onClick={() => void handleImport()} disabled={!canImport}>Import from provider</button>
    </section>
  );
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

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
