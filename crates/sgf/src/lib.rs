use app_model::{GameDto, GameSummaryDto, MoveDto, MoveVertex, PlayerColor, PointDto};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SgfDocument {
    pub board_size: u8,
    pub komi: f32,
    pub handicap: Option<u8>,
    pub black_name: Option<String>,
    pub white_name: Option<String>,
    pub result: Option<String>,
    pub moves: Vec<MoveDto>,
}

#[derive(Debug, Error)]
pub enum SgfError {
    #[error("SGF is empty")]
    Empty,
    #[error("unsupported or malformed SGF")]
    Malformed,
    #[error("unsupported board size: {0}")]
    UnsupportedBoardSize(u8),
}

pub fn parse_sgf(input: &str) -> Result<SgfDocument, SgfError> {
    if input.trim().is_empty() {
        return Err(SgfError::Empty);
    }
    let props = scan_properties(input)?;
    let board_size = props
        .get("SZ")
        .and_then(|v| v.first())
        .and_then(|v| v.parse::<u8>().ok())
        .unwrap_or(19);
    if !(2..=25).contains(&board_size) {
        return Err(SgfError::UnsupportedBoardSize(board_size));
    }
    let komi = props
        .get("KM")
        .and_then(|v| v.first())
        .and_then(|v| v.parse::<f32>().ok())
        .unwrap_or(7.5);
    let mut move_number = 1;
    let mut moves = Vec::new();
    for node in scan_nodes(input) {
        for (key, values) in node {
            let color = match key.as_str() {
                "B" => Some(PlayerColor::Black),
                "W" => Some(PlayerColor::White),
                _ => None,
            };
            if let (Some(color), Some(raw)) = (color, values.first()) {
                moves.push(MoveDto {
                    color,
                    vertex: parse_vertex(raw, board_size)?,
                    move_number,
                });
                move_number += 1;
            }
        }
    }
    Ok(SgfDocument {
        board_size,
        komi,
        handicap: props
            .get("HA")
            .and_then(|v| v.first())
            .and_then(|v| v.parse::<u8>().ok()),
        black_name: props.get("PB").and_then(|v| v.first()).cloned(),
        white_name: props.get("PW").and_then(|v| v.first()).cloned(),
        result: props.get("RE").and_then(|v| v.first()).cloned(),
        moves,
    })
}

pub fn to_game_dto(doc: SgfDocument) -> GameDto {
    GameDto {
        summary: GameSummaryDto {
            id: Uuid::new_v4(),
            board_size: doc.board_size,
            komi: doc.komi,
            black_name: doc.black_name,
            white_name: doc.white_name,
            result: doc.result,
            move_count: doc.moves.len(),
        },
        moves: doc.moves,
    }
}

fn scan_properties(input: &str) -> Result<HashMap<String, Vec<String>>, SgfError> {
    let mut props = HashMap::new();
    for node in scan_nodes(input) {
        for (k, v) in node {
            props.entry(k).or_insert_with(Vec::new).extend(v);
        }
    }
    if props.is_empty() {
        Err(SgfError::Malformed)
    } else {
        Ok(props)
    }
}

fn scan_nodes(input: &str) -> Vec<HashMap<String, Vec<String>>> {
    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;
    let mut nodes = Vec::new();
    while i < chars.len() {
        if chars[i] != ';' {
            i += 1;
            continue;
        }
        i += 1;
        let mut node = HashMap::new();
        while i < chars.len() {
            while i < chars.len() && chars[i].is_whitespace() {
                i += 1;
            }
            if i >= chars.len() || !chars[i].is_ascii_uppercase() {
                break;
            }
            let start = i;
            while i < chars.len() && chars[i].is_ascii_uppercase() {
                i += 1;
            }
            let key: String = chars[start..i].iter().collect();
            let mut values = Vec::new();
            while i < chars.len() && chars[i] == '[' {
                i += 1;
                let mut value = String::new();
                while i < chars.len() {
                    match chars[i] {
                        '\\' if i + 1 < chars.len() => {
                            i += 1;
                            value.push(chars[i]);
                        }
                        ']' => break,
                        c => value.push(c),
                    }
                    i += 1;
                }
                if i < chars.len() && chars[i] == ']' {
                    i += 1;
                }
                values.push(value);
            }
            node.insert(key, values);
        }
        nodes.push(node);
    }
    nodes
}

fn parse_vertex(raw: &str, board_size: u8) -> Result<MoveVertex, SgfError> {
    if raw.is_empty() || (raw.eq_ignore_ascii_case("tt") && board_size <= 19) {
        return Ok(MoveVertex::Pass);
    }
    let bytes = raw.as_bytes();
    if bytes.len() < 2 {
        return Err(SgfError::Malformed);
    }
    let x = bytes[0].saturating_sub(b'a');
    let y = bytes[1].saturating_sub(b'a');
    if x >= board_size || y >= board_size {
        return Err(SgfError::Malformed);
    }
    Ok(MoveVertex::Point(PointDto { x, y }))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parses_basic_sgf() {
        let doc = parse_sgf("(;GM[1]FF[4]SZ[19]KM[7.5]PB[Black]PW[White];B[pd];W[dd];B[])").unwrap();
        assert_eq!(doc.board_size, 19);
        assert_eq!(doc.moves.len(), 3);
        assert!(matches!(doc.moves[2].vertex, MoveVertex::Pass));
    }
}
