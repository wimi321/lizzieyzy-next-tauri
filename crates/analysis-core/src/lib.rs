use app_model::{AnalysisFrameDto, ProblemMarkerDto, ProblemSeverity};
use std::cmp::Reverse;

pub fn sort_candidates_by_visits(frame: &mut AnalysisFrameDto) {
    frame
        .candidates
        .sort_by_key(|candidate| Reverse(candidate.visits));
}

pub fn classify_problem_markers(frames: &[AnalysisFrameDto]) -> Vec<ProblemMarkerDto> {
    let mut markers = Vec::new();
    for pair in frames.windows(2) {
        let previous = &pair[0];
        let current = &pair[1];
        let winrate_loss = (previous.winrate_black - current.winrate_black).abs();
        let score_loss = (previous.score_mean_black - current.score_mean_black).abs();
        let severity = severity_for(winrate_loss, score_loss);
        if severity != ProblemSeverity::Info {
            markers.push(ProblemMarkerDto {
                turn: current.turn,
                severity,
                winrate_loss,
                score_loss,
                label: label_for(severity).to_string(),
            });
        }
    }
    markers
}

pub fn severity_for(winrate_loss: f32, score_loss: f32) -> ProblemSeverity {
    if winrate_loss >= 0.18 || score_loss >= 12.0 {
        ProblemSeverity::Blunder
    } else if winrate_loss >= 0.10 || score_loss >= 7.0 {
        ProblemSeverity::Mistake
    } else if winrate_loss >= 0.05 || score_loss >= 3.0 {
        ProblemSeverity::Inaccuracy
    } else {
        ProblemSeverity::Info
    }
}
fn label_for(severity: ProblemSeverity) -> &'static str {
    match severity {
        ProblemSeverity::Info => "正常波动",
        ProblemSeverity::Inaccuracy => "疑似缓手",
        ProblemSeverity::Mistake => "明显问题手",
        ProblemSeverity::Blunder => "重大失误",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use app_model::AnalysisFrameDto;
    use uuid::Uuid;
    fn f(t: u32, w: f32, s: f32) -> AnalysisFrameDto {
        AnalysisFrameDto {
            job_id: Uuid::new_v4(),
            game_id: None,
            node_id: None,
            turn: t,
            visits: 100,
            winrate_black: w,
            score_mean_black: s,
            score_stdev: None,
            candidates: vec![],
            ownership: None,
            policy: None,
        }
    }
    #[test]
    fn classifies() {
        assert_eq!(
            classify_problem_markers(&[f(1, 0.62, 3.0), f(2, 0.48, -5.0)]).len(),
            1
        )
    }
}
