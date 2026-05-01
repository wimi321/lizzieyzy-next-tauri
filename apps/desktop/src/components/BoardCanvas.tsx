import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisFrameDto, PositionDto } from "../domain/types";
import { isPoint, vertexLabel } from "../domain/board";

type Props = { position: PositionDto; analysis?: AnalysisFrameDto; selectedCandidateIndex?: number | null };
type OverlayMode = "candidates" | "ownership" | "policy";
type PolicyPoint = { x: number; y: number; value: number };

export function BoardCanvas({ position, analysis, selectedCandidateIndex }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [overlayMode, setOverlayMode] = useState<OverlayMode>("candidates");
  const boardPointCount = position.board_size * position.board_size;
  const hasOwnership = (analysis?.ownership?.length ?? 0) >= boardPointCount;
  const policyPoints = useMemo(() => getTopPolicyPoints(analysis?.policy, position.board_size, 12), [analysis?.policy, position.board_size]);
  const hasPolicy = policyPoints.length > 0;
  const effectiveOverlayMode = overlayMode === "ownership" && !hasOwnership ? "candidates" : overlayMode === "policy" && !hasPolicy ? "candidates" : overlayMode;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const cssSize = Math.min(canvas.clientWidth || 720, canvas.clientHeight || 720);
    canvas.width = Math.floor(cssSize * dpr);
    canvas.height = Math.floor(cssSize * dpr);
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, cssSize, cssSize);

    const boardSize = position.board_size;
    const padding = cssSize * 0.07;
    const grid = (cssSize - padding * 2) / (boardSize - 1);
    const coord = (n: number) => padding + n * grid;

    ctx.lineWidth = 1;
    ctx.fillStyle = "#d8aa68";
    ctx.fillRect(0, 0, cssSize, cssSize);
    ctx.strokeStyle = "rgba(35,20,8,.82)";
    for (let i = 0; i < boardSize; i += 1) {
      ctx.beginPath(); ctx.moveTo(coord(0), coord(i)); ctx.lineTo(coord(boardSize - 1), coord(i)); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(coord(i), coord(0)); ctx.lineTo(coord(i), coord(boardSize - 1)); ctx.stroke();
    }

    const stars = boardSize === 19 ? [3, 9, 15] : boardSize === 13 ? [3, 6, 9] : [2, boardSize - 3];
    ctx.fillStyle = "rgba(35,20,8,.85)";
    for (const x of stars) for (const y of stars) { ctx.beginPath(); ctx.arc(coord(x), coord(y), 3, 0, Math.PI * 2); ctx.fill(); }

    if (effectiveOverlayMode === "ownership" && hasOwnership && analysis?.ownership) {
      const cellSize = Math.max(2, grid * 0.94);
      for (let y = 0; y < boardSize; y += 1) {
        for (let x = 0; x < boardSize; x += 1) {
          const value = normalizeOwnershipValue(analysis.ownership[y * boardSize + x]);
          const magnitude = Math.abs(value);
          if (magnitude < 0.015) continue;
          const alpha = 0.12 + magnitude * 0.42;
          ctx.fillStyle = value >= 0 ? `rgba(37,99,235,${alpha})` : `rgba(244,63,94,${alpha})`;
          ctx.fillRect(coord(x) - cellSize / 2, coord(y) - cellSize / 2, cellSize, cellSize);
        }
      }
    }

    for (const stone of position.stones) {
      const cx = coord(stone.x); const cy = coord(stone.y); const radius = grid * 0.45;
      ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fillStyle = stone.color === "black" ? "#101010" : "#f5f5f2"; ctx.fill();
      ctx.strokeStyle = stone.color === "black" ? "#000" : "#b8b8b8"; ctx.stroke();
    }

    if (position.last_move && isPoint(position.last_move.vertex)) {
      const { x, y } = position.last_move.vertex.point;
      const cx = coord(x); const cy = coord(y);
      ctx.strokeStyle = position.last_move.color === "black" ? "#f3f3f3" : "#222";
      ctx.lineWidth = Math.max(2, grid * 0.07);
      ctx.beginPath(); ctx.arc(cx, cy, grid * 0.18, 0, Math.PI * 2); ctx.stroke();
    }

    if (effectiveOverlayMode === "policy" && hasPolicy) {
      drawPolicyOverlay(ctx, policyPoints, boardSize, coord, grid);
    } else {
      const topCandidates = analysis?.candidates.slice(0, 8) ?? [];
      for (const [index, candidate] of topCandidates.entries()) {
        if (!isPoint(candidate.vertex)) continue;
        const cx = coord(candidate.vertex.point.x); const cy = coord(candidate.vertex.point.y);
        const radius = grid * (0.18 + Math.min(candidate.visits / Math.max(analysis?.visits ?? 1, 1), 1) * 0.24);
        const isSelected = selectedCandidateIndex === index;
        ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2); ctx.fillStyle = isSelected ? "rgba(249,115,22,.86)" : "rgba(74,144,226,.75)"; ctx.fill();
        if (isSelected) {
          ctx.strokeStyle = "rgba(15,23,42,.86)";
          ctx.lineWidth = Math.max(2, grid * 0.08);
          ctx.beginPath(); ctx.arc(cx, cy, radius + grid * 0.1, 0, Math.PI * 2); ctx.stroke();
        }
        ctx.fillStyle = "white"; ctx.font = `${Math.max(10, grid * 0.3)}px system-ui`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(String(index + 1), cx, cy);
        ctx.fillStyle = "rgba(0,0,0,.72)"; ctx.font = `${Math.max(9, grid * 0.22)}px system-ui`; ctx.fillText(vertexLabel(candidate.vertex, boardSize), cx, cy + radius + 11);
      }
    }
  }, [position, analysis, selectedCandidateIndex, effectiveOverlayMode, hasOwnership, hasPolicy, policyPoints]);

  return <div className="board-canvas" style={{ position: "relative", overflow: "hidden" }}>
    <canvas ref={canvasRef} style={{ display: "block", width: "100%", height: "100%" }} aria-label="Go board" />
    <div style={{ position: "absolute", left: 10, top: 10, display: "flex", gap: 6, padding: 4, borderRadius: 6, background: "rgba(255,255,255,.82)", boxShadow: "0 4px 14px rgba(15,23,42,.14)" }} aria-label="Board overlay mode">
      <OverlayButton label="Candidates" active={effectiveOverlayMode === "candidates"} onClick={() => setOverlayMode("candidates")} />
      <OverlayButton label="Ownership" active={effectiveOverlayMode === "ownership"} disabled={!hasOwnership} onClick={() => setOverlayMode("ownership")} />
      <OverlayButton label="Policy" active={effectiveOverlayMode === "policy"} disabled={!hasPolicy} onClick={() => setOverlayMode("policy")} />
    </div>
  </div>;
}

function OverlayButton({ label, active, disabled, onClick }: { label: string; active: boolean; disabled?: boolean; onClick: () => void }) {
  return <button
    type="button"
    disabled={disabled}
    aria-pressed={active}
    onClick={onClick}
    style={{
      border: "1px solid rgba(15,23,42,.18)",
      borderRadius: 5,
      background: active ? "#0f172a" : "rgba(255,255,255,.88)",
      color: active ? "#fff" : disabled ? "rgba(15,23,42,.38)" : "#0f172a",
      cursor: disabled ? "not-allowed" : "pointer",
      font: "700 12px system-ui",
      lineHeight: 1,
      padding: "7px 8px"
    }}
  >{label}</button>;
}

function normalizeOwnershipValue(value: number | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  const normalized = Math.abs(value) > 1 ? value / 100 : value;
  return Math.max(-1, Math.min(1, normalized));
}

function getTopPolicyPoints(policy: number[] | null | undefined, boardSize: number, limit: number): PolicyPoint[] {
  if (!policy || policy.length < boardSize * boardSize) return [];
  const points: PolicyPoint[] = [];
  for (let index = 0; index < boardSize * boardSize; index += 1) {
    const value = policy[index];
    if (!Number.isFinite(value) || value <= 0) continue;
    points.push({ x: index % boardSize, y: Math.floor(index / boardSize), value });
  }
  return points.sort((a, b) => b.value - a.value).slice(0, limit);
}

function drawPolicyOverlay(ctx: CanvasRenderingContext2D, points: PolicyPoint[], boardSize: number, coord: (n: number) => number, grid: number) {
  const maxPolicy = Math.max(points[0]?.value ?? 1, 1e-6);
  for (const [rank, point] of points.entries()) {
    const weight = Math.sqrt(point.value / maxPolicy);
    const cx = coord(point.x);
    const cy = coord(point.y);
    const radius = grid * (0.12 + weight * 0.32);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(20,184,166,${0.28 + weight * 0.58})`;
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,.85)";
    ctx.lineWidth = Math.max(1.5, grid * 0.04);
    ctx.stroke();
    if (rank < 8) {
      ctx.fillStyle = "white";
      ctx.font = `${Math.max(10, grid * 0.26)}px system-ui`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(rank + 1), cx, cy);
      ctx.fillStyle = "rgba(0,0,0,.72)";
      ctx.font = `${Math.max(9, grid * 0.2)}px system-ui`;
      ctx.fillText(vertexLabel({ point: { x: point.x, y: point.y } }, boardSize), cx, cy + radius + 10);
    }
  }
}
