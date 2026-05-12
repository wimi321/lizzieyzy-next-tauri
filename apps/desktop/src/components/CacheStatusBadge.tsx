import type { AnalysisCacheRecord, CacheStatus } from "../domain/cache";

type Props = {
  status: CacheStatus;
  record?: AnalysisCacheRecord | null;
  error?: string | null;
  cacheRestoreVerified?: boolean;
};

const statusLabels: Record<CacheStatus, string> = {
  idle: "Cache idle",
  checking: "Checking cache",
  hit: "Cache hit",
  miss: "Cache miss",
  saving: "Saving cache",
  saved: "Cache saved",
  error: "Cache error"
};

const statusColors: Record<CacheStatus, { background: string; border: string; color: string }> = {
  idle: { background: "#f8fafc", border: "#cbd5e1", color: "#475569" },
  checking: { background: "#eff6ff", border: "#bfdbfe", color: "#1d4ed8" },
  hit: { background: "#ecfdf5", border: "#a7f3d0", color: "#047857" },
  miss: { background: "#fff7ed", border: "#fed7aa", color: "#c2410c" },
  saving: { background: "#f5f3ff", border: "#ddd6fe", color: "#6d28d9" },
  saved: { background: "#f0fdf4", border: "#bbf7d0", color: "#15803d" },
  error: { background: "#fef2f2", border: "#fecaca", color: "#b91c1c" }
};

export function CacheStatusBadge({ status, record = null, error = null, cacheRestoreVerified = false }: Props) {
  const colors = statusColors[status];
  const metadata = record ? cacheRecordMetadata(record) : null;
  const detail = status === "error" ? error : metadata;

  return (
    <div
      className="status-pill"
      data-testid="cache-status-badge"
      data-cache-status={status}
      data-cache-restore-verified={String(cacheRestoreVerified)}
      title={detail ?? statusLabels[status]}
      aria-live="polite"
      style={{
        display: "inline-flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: 2,
        maxWidth: "100%",
        background: colors.background,
        borderColor: colors.border,
        color: colors.color
      }}
    >
      <span style={{ color: "inherit", fontSize: 13, fontWeight: 800, lineHeight: 1.2 }}>{statusLabels[status]}</span>
      {detail ? <small style={{ color: "inherit", fontSize: 11, fontWeight: 700, lineHeight: 1.25 }}>{detail}</small> : null}
    </div>
  );
}

function cacheRecordMetadata(record: AnalysisCacheRecord): string {
  const analyzedMoves = Math.min(record.analyzedMoveCount, record.moveCount);
  const frameDetail = record.analyzedMoveCount > record.moveCount ? ` (${record.analyzedMoveCount} frames)` : "";
  const parts = [
    record.engineKind,
    `${analyzedMoves}/${record.moveCount} moves${frameDetail}`,
    formatUpdatedAt(record.updatedAt)
  ].filter(Boolean);
  return parts.join(" | ");
}

function formatUpdatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}
