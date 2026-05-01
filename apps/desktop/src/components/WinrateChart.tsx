import { useEffect, useRef } from "react";
import type { AnalysisFrameDto } from "../domain/types";

type Props = { frames: AnalysisFrameDto[]; currentMove: number };
export function WinrateChart({ frames, currentMove }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const canvas = canvasRef.current; const ctx = canvas?.getContext("2d"); if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1; const width = canvas.clientWidth || 600; const height = canvas.clientHeight || 160;
    canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(248,250,252,.72)"; ctx.fillRect(0, 0, width, height); ctx.strokeStyle = "rgba(51,65,85,.14)";
    for (let i = 0; i <= 4; i += 1) { const y = (height / 4) * i; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
    const sortedFrames = [...frames].sort((a, b) => a.turn - b.turn);
    const maxTurn = Math.max(currentMove, ...sortedFrames.map((frame) => frame.turn), 1);
    const turnToX = (turn: number) => (Math.min(Math.max(turn, 0), maxTurn) / maxTurn) * width;
    if (sortedFrames.length > 1) { ctx.strokeStyle = "#2563eb"; ctx.lineWidth = 2; ctx.beginPath(); sortedFrames.forEach((frame, index) => { const x = turnToX(frame.turn); const y = height - frame.winrate_black * height; if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }); ctx.stroke(); }
    const markerX = turnToX(currentMove); ctx.strokeStyle = "rgba(15,23,42,.72)"; ctx.beginPath(); ctx.moveTo(markerX, 0); ctx.lineTo(markerX, height); ctx.stroke();
  }, [frames, currentMove]);
  return <canvas ref={canvasRef} className="winrate-chart" aria-label="Winrate chart" />;
}
