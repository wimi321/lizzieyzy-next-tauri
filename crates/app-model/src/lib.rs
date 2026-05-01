use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use uuid::Uuid;

pub type GameId = Uuid;
pub type NodeId = Uuid;
pub type AnalysisJobId = Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PlayerColor {
    Black,
    White,
}

impl PlayerColor {
    pub fn opponent(self) -> Self {
        match self {
            PlayerColor::Black => PlayerColor::White,
            PlayerColor::White => PlayerColor::Black,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PointDto {
    pub x: u8,
    pub y: u8,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MoveVertex {
    Point(PointDto),
    Pass,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MoveDto {
    pub color: PlayerColor,
    pub vertex: MoveVertex,
    pub move_number: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StoneDto {
    pub x: u8,
    pub y: u8,
    pub color: PlayerColor,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PositionDto {
    pub board_size: u8,
    pub move_number: u32,
    pub to_play: PlayerColor,
    pub stones: Vec<StoneDto>,
    pub captures_black: u32,
    pub captures_white: u32,
    pub last_move: Option<MoveDto>,
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameSummaryDto {
    pub id: GameId,
    pub board_size: u8,
    pub komi: f32,
    pub black_name: Option<String>,
    pub white_name: Option<String>,
    pub result: Option<String>,
    pub move_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameDto {
    pub summary: GameSummaryDto,
    pub moves: Vec<MoveDto>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CandidateMoveDto {
    pub vertex: MoveVertex,
    pub visits: u32,
    pub winrate_black: f32,
    pub score_mean_black: f32,
    pub policy_prior: Option<f32>,
    pub pv: Vec<MoveVertex>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisFrameDto {
    pub job_id: AnalysisJobId,
    pub game_id: Option<GameId>,
    pub node_id: Option<NodeId>,
    pub turn: u32,
    pub visits: u32,
    pub winrate_black: f32,
    pub score_mean_black: f32,
    pub score_stdev: Option<f32>,
    pub candidates: Vec<CandidateMoveDto>,
    pub ownership: Option<Vec<f32>>,
    pub policy: Option<Vec<f32>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProblemMarkerDto {
    pub turn: u32,
    pub severity: ProblemSeverity,
    pub winrate_loss: f32,
    pub score_loss: f32,
    pub label: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProblemSeverity {
    Info,
    Inaccuracy,
    Mistake,
    Blunder,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineProfileDto {
    pub name: String,
    pub engine_path: String,
    pub model_path: Option<String>,
    pub config_path: Option<String>,
    pub working_dir: Option<String>,
    pub backend: EngineBackend,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EngineBackend {
    KataGoAnalysis,
    KataGoGtp,
    GenericGtp,
    ReadboardSidecar,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppHealthDto {
    pub app: String,
    pub architecture: String,
    pub rust_backend_ready: bool,
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderKind {
    Yike,
    Fox,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ProviderImportRequest {
    pub provider: ProviderKind,
    pub payload: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_id: Option<String>,
    #[serde(default)]
    pub metadata: ProviderGameMetadata,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ProviderImportResult {
    pub provider: ProviderKind,
    pub sgf_text: String,
    pub summary: ProviderGameSummary,
    pub metadata: ProviderGameMetadata,
    #[serde(default)]
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ProviderGameSummary {
    pub provider: ProviderKind,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub board_size: Option<u8>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub komi: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub handicap: Option<u8>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub black_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub white_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub result: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub date: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub move_count: Option<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub struct ProviderGameMetadata {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub request_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub room_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_status: Option<String>,
    #[serde(default)]
    pub extra: BTreeMap<String, String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ProviderError {
    pub kind: ProviderErrorKind,
    pub message: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderErrorKind {
    InvalidRequest,
    UnsupportedProvider,
    InvalidUrl,
    InvalidPayload,
    ParseFailed,
}

impl ProviderGameSummary {
    pub fn empty(provider: ProviderKind) -> Self {
        Self {
            provider,
            source_id: None,
            board_size: None,
            komi: None,
            handicap: None,
            black_name: None,
            white_name: None,
            result: None,
            date: None,
            move_count: None,
        }
    }
}

#[cfg(test)]
mod provider_tests {
    use super::*;

    #[test]
    fn provider_dtos_serialize_with_snake_case_contract() {
        let request = ProviderImportRequest {
            provider: ProviderKind::Yike,
            payload: "(;GM[1])".to_string(),
            source_url: Some("https://example.test/game".to_string()),
            source_id: Some("123".to_string()),
            metadata: ProviderGameMetadata::default(),
        };

        let json = serde_json::to_value(request).unwrap();

        assert_eq!(json["provider"], "yike");
        assert_eq!(json["source_url"], "https://example.test/game");
        assert_eq!(json["source_id"], "123");
    }

    #[test]
    fn provider_errors_serialize_kind_for_tauri_commands() {
        let error = ProviderError {
            kind: ProviderErrorKind::InvalidPayload,
            message: "missing SGF".to_string(),
        };

        let json = serde_json::to_value(error).unwrap();

        assert_eq!(json["kind"], "invalid_payload");
        assert_eq!(json["message"], "missing SGF");
    }
}
