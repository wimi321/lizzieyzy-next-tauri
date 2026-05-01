use app_model::{
    AnalysisFrameDto, AnalysisJobId, CandidateMoveDto, GameDto, MoveDto, MoveVertex, PlayerColor, PointDto,
};
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

#[derive(Debug, Clone)]
pub struct AnalysisQueryOptions {
    pub id: String,
    pub rules: String,
    pub turn: u32,
    pub max_visits: Option<u32>,
    pub include_ownership: Option<bool>,
    pub include_policy: Option<bool>,
}

#[derive(Debug, Clone)]
pub struct AnalysisBatchQueryOptions {
    pub id: String,
    pub rules: String,
    pub analyze_turns: Option<Vec<u32>>,
    pub max_visits: Option<u32>,
    pub include_ownership: Option<bool>,
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
    #[error("move vertex ({x}, {y}) is outside board size {board_size}")]
    InvalidVertex { x: u8, y: u8, board_size: u8 },
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

pub fn analysis_query_from_game(
    game: &GameDto,
    options: AnalysisQueryOptions,
) -> Result<AnalysisQuery, ProtocolError> {
    let board_size = game.summary.board_size;
    let turn = options.turn.min(game.moves.len() as u32);
    let moves = game
        .moves
        .iter()
        .take(turn as usize)
        .map(|move_| move_dto_to_kata_move(move_, board_size))
        .collect::<Result<Vec<_>, _>>()?;

    Ok(AnalysisQuery {
        id: options.id,
        moves,
        initial_stones: Vec::new(),
        rules: options.rules,
        komi: game.summary.komi,
        board_x_size: board_size,
        board_y_size: board_size,
        analyze_turns: Some(vec![turn]),
        max_visits: options.max_visits,
        include_ownership: options.include_ownership,
        include_policy: options.include_policy,
    })
}

pub fn analysis_batch_query_from_game(
    game: &GameDto,
    options: AnalysisBatchQueryOptions,
) -> Result<AnalysisQuery, ProtocolError> {
    let board_size = game.summary.board_size;
    let move_count = game.moves.len() as u32;
    let moves = game
        .moves
        .iter()
        .map(|move_| move_dto_to_kata_move(move_, board_size))
        .collect::<Result<Vec<_>, _>>()?;

    Ok(AnalysisQuery {
        id: options.id,
        moves,
        initial_stones: Vec::new(),
        rules: options.rules,
        komi: game.summary.komi,
        board_x_size: board_size,
        board_y_size: board_size,
        analyze_turns: Some(normalize_analysis_turns(options.analyze_turns, move_count)),
        max_visits: options.max_visits,
        include_ownership: options.include_ownership,
        include_policy: options.include_policy,
    })
}

fn normalize_analysis_turns(turns: Option<Vec<u32>>, move_count: u32) -> Vec<u32> {
    let mut turns = turns.unwrap_or_else(|| (0..=move_count).collect());
    for turn in &mut turns {
        *turn = (*turn).min(move_count);
    }
    turns.sort_unstable();
    turns.dedup();
    turns
}

pub fn move_dto_to_kata_move(move_: &MoveDto, board_size: u8) -> Result<KataMove, ProtocolError> {
    Ok((
        player_color_to_kata(move_.color).to_string(),
        move_vertex_to_kata_coordinate(&move_.vertex, board_size)?,
    ))
}

pub fn player_color_to_kata(color: PlayerColor) -> &'static str {
    match color {
        PlayerColor::Black => "B",
        PlayerColor::White => "W",
    }
}

pub fn move_vertex_to_kata_coordinate(vertex: &MoveVertex, board_size: u8) -> Result<String, ProtocolError> {
    match vertex {
        MoveVertex::Pass => Ok("pass".to_string()),
        MoveVertex::Point(point) => point_to_kata_coordinate(point, board_size),
    }
}

pub fn point_to_kata_coordinate(point: &PointDto, board_size: u8) -> Result<String, ProtocolError> {
    if point.x >= board_size || point.y >= board_size {
        return Err(ProtocolError::InvalidVertex {
            x: point.x,
            y: point.y,
            board_size,
        });
    }
    let col = if point.x >= 8 {
        (b'A' + point.x + 1) as char
    } else {
        (b'A' + point.x) as char
    };
    let row = board_size - point.y;
    Ok(format!("{col}{row}"))
}

pub fn normalize_responses_for_turns(
    job_id: AnalysisJobId,
    responses: Vec<AnalysisResponse>,
    board_size: u8,
    turns: &[u32],
) -> Vec<AnalysisFrameDto> {
    let mut turns = turns.to_vec();
    turns.sort_unstable();
    turns.dedup();

    let mut frames = responses
        .into_iter()
        .filter(|response| turns.binary_search(&response.turn_number).is_ok())
        .map(|response| normalize_response(job_id, response, board_size))
        .collect::<Vec<_>>();
    frames.sort_by_key(|frame| frame.turn);
    frames
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

#[cfg(test)]
mod tests {
    use super::*;
    use app_model::{GameId, GameSummaryDto};

    fn move_at(color: PlayerColor, x: u8, y: u8, move_number: u32) -> MoveDto {
        MoveDto {
            color,
            vertex: MoveVertex::Point(PointDto { x, y }),
            move_number,
        }
    }

    fn pass(color: PlayerColor, move_number: u32) -> MoveDto {
        MoveDto {
            color,
            vertex: MoveVertex::Pass,
            move_number,
        }
    }

    fn game(moves: Vec<MoveDto>) -> GameDto {
        GameDto {
            summary: GameSummaryDto {
                id: GameId::nil(),
                board_size: 19,
                komi: 7.5,
                black_name: None,
                white_name: None,
                result: None,
                move_count: moves.len(),
            },
            moves,
        }
    }

    fn options(turn: u32) -> AnalysisQueryOptions {
        AnalysisQueryOptions {
            id: "query-1".to_string(),
            rules: "chinese".to_string(),
            turn,
            max_visits: Some(128),
            include_ownership: Some(true),
            include_policy: Some(false),
        }
    }

    fn batch_options(analyze_turns: Option<Vec<u32>>) -> AnalysisBatchQueryOptions {
        AnalysisBatchQueryOptions {
            id: "batch-1".to_string(),
            rules: "chinese".to_string(),
            analyze_turns,
            max_visits: Some(256),
            include_ownership: Some(false),
            include_policy: Some(true),
        }
    }

    fn response(turn_number: u32, visits: u32) -> AnalysisResponse {
        AnalysisResponse {
            id: "batch-1".to_string(),
            turn_number,
            root_info: Some(RootInfo {
                visits,
                winrate: 0.5,
                score_mean: 0.0,
                score_stdev: None,
            }),
            move_infos: Vec::new(),
            ownership: None,
            policy: None,
            error: None,
            warning: None,
        }
    }

    #[test]
    fn parse_response_line_returns_engine_error_field() {
        let error = parse_response_line(r#"{"id":"query-1","error":"bad query"}"#).unwrap_err();

        match error {
            ProtocolError::Engine(message) => assert_eq!(message, "bad query"),
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn parse_response_line_accepts_success_response_without_error_field() {
        let response = parse_response_line(
            r#"{"id":"query-1","turnNumber":2,"rootInfo":{"visits":64,"winrate":0.52,"scoreMean":1.5}}"#,
        )
        .unwrap();

        assert_eq!(response.id, "query-1");
        assert_eq!(response.turn_number, 2);
        assert_eq!(response.root_info.unwrap().visits, 64);
    }

    #[test]
    fn converts_pass_to_katago_pass() {
        let move_ = pass(PlayerColor::Black, 1);
        let kata_move = move_dto_to_kata_move(&move_, 19).unwrap();

        assert_eq!(kata_move, ("B".to_string(), "pass".to_string()));
    }

    #[test]
    fn skips_i_column_in_katago_coordinates() {
        let coordinate = point_to_kata_coordinate(&PointDto { x: 8, y: 9 }, 19).unwrap();

        assert_eq!(coordinate, "J10");
    }

    #[test]
    fn converts_19_line_board_edges() {
        let top_left = point_to_kata_coordinate(&PointDto { x: 0, y: 0 }, 19).unwrap();
        let bottom_right = point_to_kata_coordinate(&PointDto { x: 18, y: 18 }, 19).unwrap();

        assert_eq!(top_left, "A19");
        assert_eq!(bottom_right, "T1");
    }

    #[test]
    fn query_for_turn_truncates_moves_and_sets_analyze_turn() {
        let game = game(vec![
            move_at(PlayerColor::Black, 3, 15, 1),
            move_at(PlayerColor::White, 15, 3, 2),
            pass(PlayerColor::Black, 3),
        ]);

        let query = analysis_query_from_game(&game, options(2)).unwrap();

        assert_eq!(
            query.moves,
            vec![
                ("B".to_string(), "D4".to_string()),
                ("W".to_string(), "Q16".to_string())
            ]
        );
        assert_eq!(query.analyze_turns, Some(vec![2]));
        assert_eq!(query.max_visits, Some(128));
        assert_eq!(query.include_ownership, Some(true));
        assert_eq!(query.include_policy, Some(false));
    }

    #[test]
    fn batch_query_defaults_to_every_turn_and_full_main_line() {
        let game = game(vec![
            move_at(PlayerColor::Black, 3, 15, 1),
            move_at(PlayerColor::White, 15, 3, 2),
            pass(PlayerColor::Black, 3),
        ]);

        let query = analysis_batch_query_from_game(&game, batch_options(None)).unwrap();

        assert_eq!(
            query.moves,
            vec![
                ("B".to_string(), "D4".to_string()),
                ("W".to_string(), "Q16".to_string()),
                ("B".to_string(), "pass".to_string())
            ]
        );
        assert_eq!(query.analyze_turns, Some(vec![0, 1, 2, 3]));
        assert_eq!(query.max_visits, Some(256));
        assert_eq!(query.include_ownership, Some(false));
        assert_eq!(query.include_policy, Some(true));
    }

    #[test]
    fn batch_query_normalizes_custom_turns() {
        let game = game(vec![
            move_at(PlayerColor::Black, 3, 15, 1),
            move_at(PlayerColor::White, 15, 3, 2),
            pass(PlayerColor::Black, 3),
        ]);

        let query = analysis_batch_query_from_game(&game, batch_options(Some(vec![3, 1, 99, 1, 0]))).unwrap();

        assert_eq!(query.analyze_turns, Some(vec![0, 1, 3]));
    }

    #[test]
    fn normalizes_responses_for_requested_turns_sorted_by_turn() {
        let job_id = AnalysisJobId::nil();
        let frames = normalize_responses_for_turns(
            job_id,
            vec![response(3, 30), response(1, 10), response(2, 20)],
            19,
            &[3, 1, 3],
        );

        assert_eq!(
            frames.iter().map(|frame| frame.turn).collect::<Vec<_>>(),
            vec![1, 3]
        );
        assert_eq!(
            frames.iter().map(|frame| frame.visits).collect::<Vec<_>>(),
            vec![10, 30]
        );
    }

    #[test]
    fn normalizes_responses_filters_unrequested_turns_without_collapsing_duplicate_responses() {
        let job_id = AnalysisJobId::nil();
        let frames = normalize_responses_for_turns(
            job_id,
            vec![response(1, 10), response(2, 20), response(1, 11)],
            19,
            &[1, 1],
        );

        assert_eq!(
            frames.iter().map(|frame| frame.turn).collect::<Vec<_>>(),
            vec![1, 1]
        );
        assert_eq!(
            frames.iter().map(|frame| frame.visits).collect::<Vec<_>>(),
            vec![10, 11]
        );
    }

    #[test]
    fn normalizes_response_ownership_and_policy_arrays() {
        let job_id = AnalysisJobId::nil();
        let response = parse_response_line(
            r#"{"id":"query-1","turnNumber":2,"rootInfo":{"visits":64,"winrate":0.52,"scoreMean":1.5},"ownership":[0.1,-0.2,0.3],"policy":[0.01,0.02,0.03]}"#,
        )
        .unwrap();

        let frame = normalize_response(job_id, response, 19);

        assert_eq!(frame.ownership, Some(vec![0.1, -0.2, 0.3]));
        assert_eq!(frame.policy, Some(vec![0.01, 0.02, 0.03]));
    }
}
