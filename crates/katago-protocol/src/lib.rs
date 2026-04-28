use app_model::{AnalysisFrameDto, AnalysisJobId, CandidateMoveDto, MoveVertex, PointDto};
use serde::{Deserialize, Serialize};
use thiserror::Error;

pub type KataMove = (String, String);

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnalysisQuery {
    pub id: String,
    pub moves: Vec<KataMove>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub initial_stones: Vec<KataMove>,
    pub rules: String,
    pub komi: f32,
    pub board_x_size: u8,
    pub board_y_size: u8,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub analyze_turns: Option<Vec<u32>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_visits: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub include_ownership: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub include_policy: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnalysisResponse {
    pub id: String,
    #[serde(default)]
    pub turn_number: u32,
    #[serde(default)]
    pub root_info: Option<RootInfo>,
    #[serde(default)]
    pub move_infos: Vec<MoveInfo>,
    #[serde(default)]
    pub ownership: Option<Vec<f32>>,
    #[serde(default)]
    pub policy: Option<Vec<f32>>,
    #[serde(default)]
    pub error: Option<String>,
    #[serde(default)]
    pub warning: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RootInfo {
    #[serde(default)]
    pub visits: u32,
    #[serde(default)]
    pub winrate: f32,
    #[serde(default)]
    pub score_mean: f32,
    #[serde(default)]
    pub score_stdev: Option<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MoveInfo {
    #[serde(rename = "move")]
    pub move_: Option<String>,
    #[serde(default)]
    pub visits: u32,
    #[serde(default)]
    pub winrate: f32,
    #[serde(default)]
    pub score_mean: f32,
    #[serde(default)]
    pub prior: Option<f32>,
    #[serde(default)]
    pub pv: Vec<String>,
}

#[derive(Debug, Error)]
pub enum ProtocolError {
    #[error("json parse error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("KataGo returned error: {0}")]
    Engine(String),
}

impl AnalysisQuery {
    pub fn to_jsonl(&self) -> Result<String, ProtocolError> {
        Ok(format!("{}\n", serde_json::to_string(self)?))
    }
}

pub fn parse_response_line(line: &str) -> Result<AnalysisResponse, ProtocolError> {
    let response: AnalysisResponse = serde_json::from_str(line)?;
    if let Some(error) = &response.error {
        return Err(ProtocolError::Engine(error.clone()));
    }
    Ok(response)
}

pub fn normalize_response(
    job_id: AnalysisJobId,
    response: AnalysisResponse,
    board_size: u8,
) -> AnalysisFrameDto {
    let root = response.root_info.unwrap_or(RootInfo {
        visits: 0,
        winrate: 0.5,
        score_mean: 0.0,
        score_stdev: None,
    });
    AnalysisFrameDto {
        job_id,
        game_id: None,
        node_id: None,
        turn: response.turn_number,
        visits: root.visits,
        winrate_black: root.winrate,
        score_mean_black: root.score_mean,
        score_stdev: root.score_stdev,
        candidates: response
            .move_infos
            .into_iter()
            .map(|info| CandidateMoveDto {
                vertex: info
                    .move_
                    .as_deref()
                    .map(|m| gtp_vertex_to_dto(m, board_size))
                    .unwrap_or(MoveVertex::Pass),
                visits: info.visits,
                winrate_black: info.winrate,
                score_mean_black: info.score_mean,
                policy_prior: info.prior,
                pv: info.pv.iter().map(|m| gtp_vertex_to_dto(m, board_size)).collect(),
            })
            .collect(),
        ownership: response.ownership,
        policy: response.policy,
    }
}

pub fn gtp_vertex_to_dto(vertex: &str, board_size: u8) -> MoveVertex {
    if vertex.eq_ignore_ascii_case("pass") || vertex.is_empty() {
        return MoveVertex::Pass;
    }
    let mut chars = vertex.chars();
    let Some(col) = chars.next() else {
        return MoveVertex::Pass;
    };
    let row: String = chars.collect();
    let Ok(row_num) = row.parse::<u8>() else {
        return MoveVertex::Pass;
    };
    let col_upper = col.to_ascii_uppercase();
    let skipped_i = if col_upper > 'I' { 1 } else { 0 };
    let x = (col_upper as u8).saturating_sub(b'A').saturating_sub(skipped_i);
    let y = board_size.saturating_sub(row_num);
    if x >= board_size || y >= board_size {
        MoveVertex::Pass
    } else {
        MoveVertex::Point(PointDto { x, y })
    }
}
