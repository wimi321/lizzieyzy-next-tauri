import type { AnalysisFrameDto, ProblemMarkerDto } from "../domain/types";
import { vertexLabel } from "../domain/board";

type PolicyPoint = { x: number; y: number; value: number };

type Props = {
  frame?: AnalysisFrameDto;
  problems: ProblemMarkerDto[];
  boardSize: number;
  currentMove: number;
  selectedCandidateIndex: number | null;
  onSelectCandidate: (index: number) => void;
  onSelectProblem: (moveNumber: number) => void;
  reviewSource?: string;
  reviewPhase?: string;
  cacheRestoreVerified?: boolean;
  staleAnalysisPrevented?: boolean;
  analysisInvalidated?: boolean;
  invalidationReason?: string;
  activeJobId?: string | null;
};

export function AnalysisPanel({
  frame,
  problems,
  boardSize,
  currentMove,
  selectedCandidateIndex,
  onSelectCandidate,
  onSelectProblem,
  reviewSource = "none",
  reviewPhase = "idle",
  cacheRestoreVerified = false,
  staleAnalysisPrevented = false,
  analysisInvalidated = false,
  invalidationReason = "",
  activeJobId = null
}: Props) {
  const hasOwnership = (frame?.ownership?.length ?? 0) >= boardSize * boardSize;
  const topPolicy = getTopPolicyPoints(frame?.policy, boardSize, 5);
  const hasPolicy = topPolicy.length > 0;

  return <aside
    className="analysis-panel"
    data-testid="analysis-panel"
    data-legacy-target="analysis-review"
    data-review-source={reviewSource}
    data-review-phase={reviewPhase}
    data-cache-restore-verified={String(cacheRestoreVerified)}
    data-stale-analysis-prevented={String(staleAnalysisPrevented)}
    data-analysis-invalidated={String(analysisInvalidated)}
    data-active-job-id={activeJobId ?? ""}
    data-current-move={currentMove}
    data-candidate-count={frame?.candidates.length ?? 0}
    data-winrate-black={frame?.winrate_black ?? ""}
    data-ownership-observed={String(hasOwnership)}
    data-policy-observed={String(hasPolicy)}
    data-visits={frame?.visits ?? 0}
    data-candidates-visible={String((frame?.candidates.length ?? 0) > 0)}
    data-ownership-visible={String(hasOwnership)}
    data-policy-visible={String(hasPolicy)}
  >
    <section data-testid="analysis-position-target" data-legacy-target="analysis-position">
      <h2>Position</h2>
      <p className="muted" data-testid="analysis-source-status">
        {reviewSource === "cache"
          ? "Showing restored cache review data; no live engine is running."
          : reviewPhase === "running" || reviewPhase === "starting"
            ? "Review analysis is updating this position."
            : "Review data is shown from the current workspace state."}
      </p>
      <p
        className={`analysis-stale-guard${staleAnalysisPrevented || analysisInvalidated ? " is-active" : ""}`}
        data-testid="analysis-stale-guard-status"
        data-stale-analysis-prevented={String(staleAnalysisPrevented)}
        data-analysis-invalidated={String(analysisInvalidated)}
        data-active-job-id={activeJobId ?? ""}
        data-invalidation-reason={invalidationReason}
      >
        {staleAnalysisPrevented
          ? "Stale KataGo result blocked after SGF changed."
          : analysisInvalidated
            ? "Analysis cleared after SGF changed; run review again for this workspace."
            : "Stale guard ready for current SGF."}
      </p>
      {frame ? <div
        className="metric-grid"
        data-testid="analysis-ownership-policy-status"
        data-legacy-target="ownership-policy"
        data-ownership-observed={String(hasOwnership)}
        data-policy-observed={String(hasPolicy)}
      >
        <span>Visits</span><strong>{frame.visits.toLocaleString()}</strong>
        <span>Black winrate</span><strong>{(frame.winrate_black * 100).toFixed(1)}%</strong>
        <span>Score lead</span><strong>{frame.score_mean_black.toFixed(1)}</strong>
        <span>Ownership</span><strong>{hasOwnership ? "available" : "none"}</strong>
        <span>Policy</span><strong>{hasPolicy ? "available" : "none"}</strong>
      </div> : <p className="muted">Run review to show candidate moves and winrate data.</p>}
    </section>
    <section
      data-testid="analysis-candidates-target"
      data-legacy-target="candidates"
      data-candidate-count={frame?.candidates.length ?? 0}
      data-selected-candidate-index={selectedCandidateIndex ?? ""}
    >
      <h2>Candidates</h2>
      <ol className="candidate-list" data-testid="analysis-candidates-list">{(frame?.candidates ?? []).slice(0, 8).map((candidate, index) => {
        const pv = candidate.pv.slice(0, 6).map((vertex) => vertexLabel(vertex, boardSize));
        const isSelected = selectedCandidateIndex === index;
        return <li key={index}>
          <button
            type="button"
            className={`candidate-button${isSelected ? " is-selected" : ""}`}
            data-testid="analysis-candidate-button"
            data-candidate-index={index}
            data-candidate-selected={String(isSelected)}
            data-candidate-move={vertexLabel(candidate.vertex, boardSize)}
            aria-pressed={isSelected}
            onClick={() => onSelectCandidate(index)}
            onFocus={() => onSelectCandidate(index)}
            onMouseEnter={() => onSelectCandidate(index)}
          >
            <span className="candidate-move">{vertexLabel(candidate.vertex, boardSize)}</span>
            <span>{candidate.visits.toLocaleString()} visits</span>
            <span>{(candidate.winrate_black * 100).toFixed(1)}%</span>
            {pv.length > 0 ? <span className="candidate-pv"><strong>PV</strong> {pv.join(" ")}</span> : null}
          </button>
        </li>;
      })}</ol>
    </section>
    <section data-testid="analysis-policy-target" data-legacy-target="policy" data-policy-count={topPolicy.length}>
      <h2>Policy</h2>
      {hasPolicy ? <ol className="candidate-list">{topPolicy.map((point, index) => {
        const vertex = { point: { x: point.x, y: point.y } };
        return <li key={`${point.x}:${point.y}`}>
          <div
            className="candidate-button"
            style={{ cursor: "default" }}
            data-testid="analysis-policy-point"
            data-policy-rank={index + 1}
            data-policy-move={vertexLabel(vertex, boardSize)}
          >
            <span className="candidate-move">{vertexLabel(vertex, boardSize)}</span>
            <span>#{index + 1}</span>
            <span>{formatPolicyValue(point.value)}</span>
          </div>
        </li>;
      })}</ol> : <p className="muted">No policy data for this move.</p>}
    </section>
    <section data-testid="analysis-problems-target" data-legacy-target="review-marks" data-problem-count={problems.length}>
      <h2>Review Marks</h2>
      {problems.length === 0 ? <p className="muted">No notable drops yet.</p> : <ol className="problem-list">{problems.slice(0, 12).map((p) => {
        const isCurrent = currentMove === p.turn;
        return <li key={p.turn} className={`severity-${p.severity}${isCurrent ? " is-current" : ""}`}>
          <button
            type="button"
            className="problem-button"
            data-testid="analysis-problem-button"
            data-problem-move={p.turn}
            data-problem-current={String(isCurrent)}
            aria-current={isCurrent ? "step" : undefined}
            onClick={() => onSelectProblem(p.turn)}
          >
            <span>Move {p.turn}</span>
            <strong>{p.label}</strong>
            <small>Winrate change {(p.winrate_loss * 100).toFixed(1)}%</small>
          </button>
        </li>;
      })}</ol>}
    </section>
  </aside>;
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

function formatPolicyValue(value: number): string {
  if (value <= 1) return `${(value * 100).toFixed(value >= 0.01 ? 1 : 2)}%`;
  return value.toFixed(2);
}
