use serde::{Deserialize, Serialize};
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoveDto {
    pub color: PlayerColor,
    pub vertex: MoveVertex,
    pub move_number: u32,
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
