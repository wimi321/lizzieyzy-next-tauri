import type { AnalysisFrameDto, ProblemMarkerDto } from "../domain/types";
import { vertexLabel } from "../domain/board";

type Props = { frame?: AnalysisFrameDto; problems: ProblemMarkerDto[]; boardSize: number };
export function AnalysisPanel({ frame, problems, boardSize }: Props) {
  return <aside className="analysis-panel">
    <section><h2>当前分析</h2>{frame ? <div className="metric-grid"><span>访问数</span><strong>{frame.visits}</strong><span>黑胜率</span><strong>{(frame.winrate_black * 100).toFixed(1)}%</strong><span>黑目差</span><strong>{frame.score_mean_black.toFixed(1)}</strong></div> : <p className="muted">尚未连接 KataGo；当前显示架构演示数据。</p>}</section>
    <section><h2>候选点</h2><ol className="candidate-list">{(frame?.candidates ?? []).slice(0, 8).map((candidate, index) => <li key={index}><span className="candidate-move">{vertexLabel(candidate.vertex, boardSize)}</span><span>{candidate.visits} visits</span><span>{(candidate.winrate_black * 100).toFixed(1)}%</span></li>)}</ol></section>
    <section><h2>问题手概览</h2>{problems.length === 0 ? <p className="muted">暂无明显问题手。</p> : <ol className="problem-list">{problems.slice(0, 12).map((p) => <li key={p.turn} className={`severity-${p.severity}`}><span>第 {p.turn} 手</span><strong>{p.label}</strong><small>胜率波动 {(p.winrate_loss * 100).toFixed(1)}%</small></li>)}</ol>}</section>
  </aside>;
}
