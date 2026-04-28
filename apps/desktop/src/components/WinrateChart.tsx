import { useEffect, useRef } from "react";
import type { AnalysisFrameDto } from "../domain/types";

type Props = { frames: AnalysisFrameDto[]; currentMove: number };
export function WinrateChart({ frames, currentMove }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const canvas = canvasRef.current; const ctx = canvas?.getContext("2d"); if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1; const width = canvas.clientWidth || 600; const height = canvas.clientHeight || 160;
    canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(255,255,255,.04)"; ctx.fillRect(0, 0, width, height); ctx.strokeStyle = "rgba(255,255,255,.15)";
    for (let i = 0; i <= 4; i += 1) { const y = (height / 4) * i; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
    if (frames.length > 1) { ctx.strokeStyle = "#7db7ff"; ctx.lineWidth = 2; ctx.beginPath(); frames.forEach((frame, index) => { const x = (index / Math.max(frames.length - 1, 1)) * width; const y = height - frame.winrate_black * height; if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }); ctx.stroke(); }
    const markerX = (currentMove / Math.max(frames.length - 1, 1)) * width; ctx.strokeStyle = "rgba(255,255,255,.8)"; ctx.beginPath(); ctx.moveTo(markerX, 0); ctx.lineTo(markerX, height); ctx.stroke();
  }, [frames, currentMove]);
  return <canvas ref={canvasRef} className="winrate-chart" aria-label="Winrate chart" />;
}
