import { useEffect, useMemo, useState } from "react";
import { BoardCanvas } from "./components/BoardCanvas";
import { WinrateChart } from "./components/WinrateChart";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { classifyProblems, fakeAnalyze, getHealth, parseSgfSummary } from "./api/backend";
import { createDemoGame } from "./domain/board";
import type { AnalysisFrameDto, AppHealthDto, GameDto, ProblemMarkerDto } from "./domain/types";

const demoSgf = "(;GM[1]FF[4]SZ[19]KM[7.5]PB[Black]PW[White];B[pd];W[dd];B[pp];W[dp];B[jq];W[qj])";

export function App() {
  const [health, setHealth] = useState<AppHealthDto | null>(null);
  const [game, setGame] = useState<GameDto>(() => createDemoGame());
  const [currentMove, setCurrentMove] = useState(6);
  const [frames, setFrames] = useState<AnalysisFrameDto[]>([]);
  const [problems, setProblems] = useState<ProblemMarkerDto[]>([]);
  const [sgfText, setSgfText] = useState(demoSgf);
  const [message, setMessage] = useState("新架构基线已加载。连接 Tauri 后端后可解析 SGF 和调用 fake analysis。");

  useEffect(() => { getHealth().then(setHealth).catch((error) => setMessage(String(error))); }, []);
  const currentFrame = useMemo(() => frames.find((f) => f.turn === currentMove) ?? frames.at(-1), [frames, currentMove]);

  async function handleParseSgf() { try { const parsed = await parseSgfSummary(sgfText); setGame(parsed); setCurrentMove(parsed.moves.length); setMessage(`已解析 SGF：${parsed.summary.move_count} 手。`); } catch (error) { setMessage(String(error)); } }
  async function handleFakeAnalyze() { try { const result = await fakeAnalyze(sgfText); setFrames(result); setProblems(await classifyProblems(result)); setMessage(`已生成 ${result.length} 个演示分析帧。`); } catch (error) { setMessage(String(error)); } }

  return <main className="app-shell">
    <header className="topbar"><div><h1>LizzieYzy Next</h1><p>{health?.architecture ?? "Tauri 2 + Rust + TypeScript"}</p></div><div className="status-pill">{health?.rust_backend_ready ? "Rust backend ready" : "Preview mode"}</div></header>
    <section className="workspace"><div className="left-pane"><BoardCanvas game={game} currentMove={currentMove} analysis={currentFrame} /><WinrateChart frames={frames} currentMove={currentMove} /><input className="move-slider" type="range" min={0} max={Math.max(game.moves.length, frames.length - 1, 1)} value={currentMove} onChange={(e) => setCurrentMove(Number(e.target.value))} /></div><AnalysisPanel frame={currentFrame} problems={problems} boardSize={game.summary.board_size} /></section>
    <section className="bottom-dock"><div className="sgf-tools"><textarea value={sgfText} onChange={(e) => setSgfText(e.target.value)} spellCheck={false} /><div className="button-row"><button onClick={handleParseSgf}>解析 SGF</button><button onClick={handleFakeAnalyze}>演示全盘分析</button></div></div><p className="message">{message}</p></section>
  </main>;
}
