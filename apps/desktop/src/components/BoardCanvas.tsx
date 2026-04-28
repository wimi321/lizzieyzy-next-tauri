import { useEffect, useRef } from "react";
import type { AnalysisFrameDto, GameDto } from "../domain/types";
import { isPoint, replayMainLine, vertexLabel } from "../domain/board";

type Props = { game: GameDto; currentMove: number; analysis?: AnalysisFrameDto };

export function BoardCanvas({ game, currentMove, analysis }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

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

    const boardSize = game.summary.board_size;
    const padding = cssSize * 0.07;
    const grid = (cssSize - padding * 2) / (boardSize - 1);
    const coord = (n: number) => padding + n * grid;

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

    for (const stone of replayMainLine(game, currentMove)) {
      const cx = coord(stone.x); const cy = coord(stone.y); const radius = grid * 0.45;
      ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fillStyle = stone.color === "black" ? "#101010" : "#f5f5f2"; ctx.fill();
      ctx.strokeStyle = stone.color === "black" ? "#000" : "#b8b8b8"; ctx.stroke();
      if (currentMove <= 120) { ctx.fillStyle = stone.color === "black" ? "#f3f3f3" : "#222"; ctx.font = `${Math.max(10, grid * 0.32)}px system-ui`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(String(stone.moveNumber), cx, cy + 0.5); }
    }

    const topCandidates = analysis?.candidates.slice(0, 5) ?? [];
    for (const [index, candidate] of topCandidates.entries()) {
      if (!isPoint(candidate.vertex)) continue;
      const cx = coord(candidate.vertex.point.x); const cy = coord(candidate.vertex.point.y);
      const radius = grid * (0.22 + Math.min(candidate.visits / Math.max(analysis?.visits ?? 1, 1), 1) * 0.28);
      ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2); ctx.fillStyle = "rgba(74,144,226,.75)"; ctx.fill();
      ctx.fillStyle = "white"; ctx.font = `${Math.max(11, grid * 0.34)}px system-ui`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(String(index + 1), cx, cy);
      ctx.fillStyle = "rgba(0,0,0,.72)"; ctx.font = `${Math.max(10, grid * 0.24)}px system-ui`; ctx.fillText(vertexLabel(candidate.vertex, boardSize), cx, cy + radius + 12);
    }
  }, [game, currentMove, analysis]);

  return <canvas ref={canvasRef} className="board-canvas" aria-label="Go board" />;
}
