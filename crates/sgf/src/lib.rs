use app_model::{GameDto, GameSummaryDto, MoveDto, MoveVertex, PlayerColor, PointDto, PositionDto, StoneDto};
use go_core::{Board, Color, Point, RuleError, Vertex};
use serde::{Deserialize, Serialize};
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub root: Option<SgfNode>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SgfNode {
    pub properties: Vec<SgfProperty>,
    pub children: Vec<SgfNode>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SgfProperty {
    pub key: String,
    pub values: Vec<String>,
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
    let root = SgfParser::new(input).parse()?;
    let board_size = property_values(&root, "SZ")
        .and_then(|v| v.first())
        .and_then(|v| v.parse::<u8>().ok())
        .unwrap_or(19);
    if !(2..=25).contains(&board_size) {
        return Err(SgfError::UnsupportedBoardSize(board_size));
    }
    let komi = property_values(&root, "KM")
        .and_then(|v| v.first())
        .and_then(|v| v.parse::<f32>().ok())
        .unwrap_or(7.5);
    let mut move_number = 1;
    let mut moves = Vec::new();
    for node in mainline_nodes(&root) {
        for property in &node.properties {
            let color = match property.key.as_str() {
                "B" => Some(PlayerColor::Black),
                "W" => Some(PlayerColor::White),
                _ => None,
            };
            if let (Some(color), Some(raw)) = (color, property.values.first()) {
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
        handicap: property_values(&root, "HA")
            .and_then(|v| v.first())
            .and_then(|v| v.parse::<u8>().ok()),
        black_name: property_values(&root, "PB").and_then(|v| v.first()).cloned(),
        white_name: property_values(&root, "PW").and_then(|v| v.first()).cloned(),
        result: property_values(&root, "RE").and_then(|v| v.first()).cloned(),
        moves,
        root: Some(root),
    })
}

pub fn serialize_sgf_document(document: &SgfDocument) -> Result<String, SgfError> {
    if !(2..=25).contains(&document.board_size) {
        return Err(SgfError::UnsupportedBoardSize(document.board_size));
    }
    if let Some(root) = &document.root {
        return serialize_sgf_tree(root);
    }

    let mut output = String::from("(;FF[4]GM[1]");
    push_property(&mut output, "SZ", &document.board_size.to_string());
    push_property(&mut output, "KM", &document.komi.to_string());
    if let Some(black_name) = &document.black_name {
        push_property(&mut output, "PB", black_name);
    }
    if let Some(white_name) = &document.white_name {
        push_property(&mut output, "PW", white_name);
    }
    if let Some(result) = &document.result {
        push_property(&mut output, "RE", result);
    }
    if let Some(handicap) = document.handicap {
        push_property(&mut output, "HA", &handicap.to_string());
    }

    for sgf_move in &document.moves {
        output.push(';');
        output.push_str(match sgf_move.color {
            PlayerColor::Black => "B",
            PlayerColor::White => "W",
        });
        output.push('[');
        output.push_str(&serialize_vertex(&sgf_move.vertex, document.board_size)?);
        output.push(']');
    }
    output.push(')');
    Ok(output)
}

pub fn to_sgf(document: &SgfDocument) -> Result<String, SgfError> {
    serialize_sgf_document(document)
}

pub fn replay_sgf_positions(input: &str) -> Result<Vec<PositionDto>, SgfError> {
    let document = parse_sgf(input)?;
    let mut board =
        Board::new(document.board_size).map_err(|_| SgfError::UnsupportedBoardSize(document.board_size))?;
    let mut captures_black = 0u32;
    let mut captures_white = 0u32;
    let mut to_play = PlayerColor::Black;
    let mainline = document.root.as_ref().map(mainline_nodes).unwrap_or_default();

    for node in &mainline {
        if has_move_property(node) {
            break;
        }
        apply_setup_properties(&mut board, node, document.board_size)?;
        if let Some(color) = player_to_play(node)? {
            to_play = color;
        }
    }

    let mut positions = Vec::with_capacity(document.moves.len() + 1);
    positions.push(PositionDto {
        board_size: document.board_size,
        move_number: 0,
        to_play,
        stones: stones_from_board(&board),
        captures_black,
        captures_white,
        last_move: None,
        errors: Vec::new(),
    });

    if document.root.is_some() {
        let mut move_number = 1;
        for node in mainline {
            apply_setup_properties(&mut board, node, document.board_size)?;
            for property in &node.properties {
                let color = match property.key.as_str() {
                    "B" => Some(PlayerColor::Black),
                    "W" => Some(PlayerColor::White),
                    _ => None,
                };
                let Some(color) = color else {
                    continue;
                };
                let Some(raw) = property.values.first() else {
                    return Err(SgfError::Malformed);
                };
                let sgf_move = MoveDto {
                    color,
                    vertex: parse_vertex(raw, document.board_size)?,
                    move_number,
                };
                move_number += 1;
                let mut errors = Vec::new();
                let vertex = to_core_vertex(&sgf_move.vertex);
                match board.play(to_core_color(sgf_move.color), vertex) {
                    Ok(outcome) => match sgf_move.color {
                        PlayerColor::Black => captures_black += outcome.captured.len() as u32,
                        PlayerColor::White => captures_white += outcome.captured.len() as u32,
                    },
                    Err(error) => errors.push(format_rule_error(&sgf_move, error)),
                }

                let to_play = player_to_play(node)?.unwrap_or_else(|| sgf_move.color.opponent());
                positions.push(PositionDto {
                    board_size: document.board_size,
                    move_number: sgf_move.move_number,
                    to_play,
                    stones: stones_from_board(&board),
                    captures_black,
                    captures_white,
                    last_move: Some(sgf_move),
                    errors,
                });
            }
        }

        return Ok(positions);
    }

    for sgf_move in document.moves {
        let mut errors = Vec::new();
        let vertex = to_core_vertex(&sgf_move.vertex);
        match board.play(to_core_color(sgf_move.color), vertex) {
            Ok(outcome) => match sgf_move.color {
                PlayerColor::Black => captures_black += outcome.captured.len() as u32,
                PlayerColor::White => captures_white += outcome.captured.len() as u32,
            },
            Err(error) => errors.push(format_rule_error(&sgf_move, error)),
        }

        positions.push(PositionDto {
            board_size: document.board_size,
            move_number: sgf_move.move_number,
            to_play: sgf_move.color.opponent(),
            stones: stones_from_board(&board),
            captures_black,
            captures_white,
            last_move: Some(sgf_move),
            errors,
        });
    }

    Ok(positions)
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

fn to_core_color(color: PlayerColor) -> Color {
    match color {
        PlayerColor::Black => Color::Black,
        PlayerColor::White => Color::White,
    }
}

fn from_core_color(color: Color) -> PlayerColor {
    match color {
        Color::Black => PlayerColor::Black,
        Color::White => PlayerColor::White,
    }
}

fn to_core_vertex(vertex: &MoveVertex) -> Vertex {
    match vertex {
        MoveVertex::Point(point) => Vertex::Point(Point {
            x: point.x,
            y: point.y,
        }),
        MoveVertex::Pass => Vertex::Pass,
    }
}

fn stones_from_board(board: &Board) -> Vec<StoneDto> {
    let size = board.size();
    board
        .stones_snapshot()
        .into_iter()
        .enumerate()
        .filter_map(|(index, color)| {
            color.map(|color| StoneDto {
                x: (index % size as usize) as u8,
                y: (index / size as usize) as u8,
                color: from_core_color(color),
            })
        })
        .collect()
}

fn format_rule_error(sgf_move: &MoveDto, error: RuleError) -> String {
    format!(
        "move {} by {:?} at {} is illegal: {}",
        sgf_move.move_number,
        sgf_move.color,
        vertex_label(&sgf_move.vertex),
        error
    )
}

fn vertex_label(vertex: &MoveVertex) -> String {
    match vertex {
        MoveVertex::Point(point) => format!("({}, {})", point.x, point.y),
        MoveVertex::Pass => "pass".to_string(),
    }
}

fn push_property(output: &mut String, key: &str, value: &str) {
    output.push_str(key);
    output.push('[');
    output.push_str(&escape_sgf_value(value));
    output.push(']');
}

fn escape_sgf_value(value: &str) -> String {
    let normalized = value.replace("\r\n", "\n").replace('\r', "\n");
    let mut escaped = String::with_capacity(normalized.len());
    for c in normalized.chars() {
        match c {
            '\\' => escaped.push_str("\\\\"),
            ']' => escaped.push_str("\\]"),
            _ => escaped.push(c),
        }
    }
    escaped
}

fn serialize_vertex(vertex: &MoveVertex, board_size: u8) -> Result<String, SgfError> {
    match vertex {
        MoveVertex::Pass => Ok(String::new()),
        MoveVertex::Point(point) if point.x < board_size && point.y < board_size => Ok(format!(
            "{}{}",
            char::from(b'a' + point.x),
            char::from(b'a' + point.y)
        )),
        MoveVertex::Point(_) => Err(SgfError::Malformed),
    }
}

fn serialize_sgf_tree(root: &SgfNode) -> Result<String, SgfError> {
    let mut output = String::new();
    serialize_tree_into(root, &mut output);
    Ok(output)
}

fn serialize_tree_into(root: &SgfNode, output: &mut String) {
    output.push('(');
    serialize_node_sequence_into(root, output);
    output.push(')');
}

fn serialize_node_sequence_into(node: &SgfNode, output: &mut String) {
    output.push(';');
    for property in &node.properties {
        output.push_str(&property.key);
        for value in &property.values {
            output.push('[');
            output.push_str(&escape_sgf_value(value));
            output.push(']');
        }
    }
    match node.children.as_slice() {
        [] => {}
        [child] => serialize_node_sequence_into(child, output),
        children => {
            for child in children {
                serialize_tree_into(child, output);
            }
        }
    }
}

fn property_values<'a>(node: &'a SgfNode, key: &str) -> Option<&'a Vec<String>> {
    node.properties
        .iter()
        .find(|property| property.key == key)
        .map(|property| &property.values)
}

fn mainline_nodes(root: &SgfNode) -> Vec<&SgfNode> {
    let mut nodes = Vec::new();
    let mut current = Some(root);
    while let Some(node) = current {
        nodes.push(node);
        current = node.children.first();
    }
    nodes
}

fn player_to_play(node: &SgfNode) -> Result<Option<PlayerColor>, SgfError> {
    let Some(value) = property_values(node, "PL").and_then(|values| values.first()) else {
        return Ok(None);
    };
    match value.as_str() {
        "B" | "b" => Ok(Some(PlayerColor::Black)),
        "W" | "w" => Ok(Some(PlayerColor::White)),
        _ => Err(SgfError::Malformed),
    }
}

fn has_move_property(node: &SgfNode) -> bool {
    node.properties
        .iter()
        .any(|property| property.key == "B" || property.key == "W")
}

fn apply_setup_properties(board: &mut Board, node: &SgfNode, board_size: u8) -> Result<(), SgfError> {
    for property in &node.properties {
        let color = match property.key.as_str() {
            "AB" => Some(Some(Color::Black)),
            "AW" => Some(Some(Color::White)),
            "AE" => Some(None),
            _ => None,
        };
        let Some(color) = color else {
            continue;
        };
        for value in &property.values {
            for point in parse_setup_points(value, board_size)? {
                board.set_stone(point, color).map_err(|_| SgfError::Malformed)?;
            }
        }
    }
    Ok(())
}

fn parse_setup_points(raw: &str, board_size: u8) -> Result<Vec<Point>, SgfError> {
    if raw.len() == 5 && raw.as_bytes()[2] == b':' {
        let start = parse_point(&raw[..2], board_size)?;
        let end = parse_point(&raw[3..], board_size)?;
        let min_x = start.x.min(end.x);
        let max_x = start.x.max(end.x);
        let min_y = start.y.min(end.y);
        let max_y = start.y.max(end.y);
        let mut points = Vec::new();
        for y in min_y..=max_y {
            for x in min_x..=max_x {
                points.push(Point { x, y });
            }
        }
        return Ok(points);
    }
    Ok(vec![parse_point(raw, board_size)?])
}

fn parse_point(raw: &str, board_size: u8) -> Result<Point, SgfError> {
    let bytes = raw.as_bytes();
    if bytes.len() != 2 || !bytes[0].is_ascii_lowercase() || !bytes[1].is_ascii_lowercase() {
        return Err(SgfError::Malformed);
    }
    let x = bytes[0] - b'a';
    let y = bytes[1] - b'a';
    if x >= board_size || y >= board_size {
        return Err(SgfError::Malformed);
    }
    Ok(Point { x, y })
}

struct SgfParser {
    chars: Vec<char>,
    index: usize,
}

impl SgfParser {
    fn new(input: &str) -> Self {
        Self {
            chars: input.chars().collect(),
            index: 0,
        }
    }

    fn parse(mut self) -> Result<SgfNode, SgfError> {
        self.skip_ws();
        let root = self.parse_game_tree()?;
        self.skip_ws();
        if self.index != self.chars.len() {
            return Err(SgfError::Malformed);
        }
        Ok(root)
    }

    fn parse_game_tree(&mut self) -> Result<SgfNode, SgfError> {
        self.expect('(')?;
        self.skip_ws();
        let mut sequence = Vec::new();
        while self.peek() == Some(';') {
            sequence.push(self.parse_node()?);
            self.skip_ws();
        }
        if sequence.is_empty() {
            return Err(SgfError::Malformed);
        }
        while self.peek() == Some('(') {
            let child = self.parse_game_tree()?;
            sequence
                .last_mut()
                .ok_or(SgfError::Malformed)?
                .children
                .push(child);
            self.skip_ws();
        }
        self.expect(')')?;
        Ok(chain_sequence(sequence))
    }

    fn parse_node(&mut self) -> Result<SgfNode, SgfError> {
        self.expect(';')?;
        self.skip_ws();
        let mut properties = Vec::new();
        while self.peek().is_some_and(|c| c.is_ascii_uppercase()) {
            let key = self.parse_property_key();
            self.skip_ws();
            let mut values = Vec::new();
            while self.peek() == Some('[') {
                values.push(self.parse_property_value()?);
                self.skip_ws();
            }
            if values.is_empty() {
                return Err(SgfError::Malformed);
            }
            properties.push(SgfProperty { key, values });
            self.skip_ws();
        }
        Ok(SgfNode {
            properties,
            children: Vec::new(),
        })
    }

    fn parse_property_key(&mut self) -> String {
        let start = self.index;
        while self.peek().is_some_and(|c| c.is_ascii_uppercase()) {
            self.index += 1;
        }
        self.chars[start..self.index].iter().collect()
    }

    fn parse_property_value(&mut self) -> Result<String, SgfError> {
        self.expect('[')?;
        let mut value = String::new();
        while let Some(c) = self.peek() {
            match c {
                ']' => {
                    self.index += 1;
                    return Ok(value);
                }
                '\\' => {
                    self.index += 1;
                    self.push_escaped_char(&mut value)?;
                }
                '\r' => {
                    self.index += 1;
                    if self.peek() == Some('\n') {
                        self.index += 1;
                    }
                    value.push('\n');
                }
                c => {
                    self.index += 1;
                    value.push(c);
                }
            }
        }
        Err(SgfError::Malformed)
    }

    fn push_escaped_char(&mut self, value: &mut String) -> Result<(), SgfError> {
        let Some(c) = self.peek() else {
            return Err(SgfError::Malformed);
        };
        self.index += 1;
        match c {
            '\r' => {
                if self.peek() == Some('\n') {
                    self.index += 1;
                }
            }
            '\n' => {}
            c => value.push(c),
        }
        Ok(())
    }

    fn skip_ws(&mut self) {
        while self.peek().is_some_and(char::is_whitespace) {
            self.index += 1;
        }
    }

    fn expect(&mut self, expected: char) -> Result<(), SgfError> {
        if self.peek() != Some(expected) {
            return Err(SgfError::Malformed);
        }
        self.index += 1;
        Ok(())
    }

    fn peek(&self) -> Option<char> {
        self.chars.get(self.index).copied()
    }
}

fn chain_sequence(mut sequence: Vec<SgfNode>) -> SgfNode {
    let mut node = sequence.pop().expect("sequence is validated as non-empty");
    while let Some(mut previous) = sequence.pop() {
        previous.children.insert(0, node);
        node = previous;
    }
    node
}

fn parse_vertex(raw: &str, board_size: u8) -> Result<MoveVertex, SgfError> {
    if raw.is_empty() || (raw.eq_ignore_ascii_case("tt") && board_size <= 19) {
        return Ok(MoveVertex::Pass);
    }
    let point = parse_point(raw, board_size)?;
    Ok(MoveVertex::Point(PointDto {
        x: point.x,
        y: point.y,
    }))
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

    #[test]
    fn serializes_root_metadata() {
        let doc = SgfDocument {
            board_size: 13,
            komi: 6.5,
            handicap: Some(2),
            black_name: Some("Black".to_string()),
            white_name: Some("White".to_string()),
            result: Some("B+R".to_string()),
            moves: Vec::new(),
            root: None,
        };

        let serialized = serialize_sgf_document(&doc).unwrap();

        assert_eq!(
            serialized,
            "(;FF[4]GM[1]SZ[13]KM[6.5]PB[Black]PW[White]RE[B+R]HA[2])"
        );
        let parsed = parse_sgf(&serialized).unwrap();
        assert_eq!(parsed.board_size, 13);
        assert_eq!(parsed.komi, 6.5);
        assert_eq!(parsed.handicap, Some(2));
        assert_eq!(parsed.black_name.as_deref(), Some("Black"));
        assert_eq!(parsed.white_name.as_deref(), Some("White"));
        assert_eq!(parsed.result.as_deref(), Some("B+R"));
    }

    #[test]
    fn serializes_pass_and_point_moves() {
        let doc = SgfDocument {
            board_size: 9,
            komi: 0.5,
            handicap: None,
            black_name: None,
            white_name: None,
            result: None,
            moves: vec![
                MoveDto {
                    color: PlayerColor::Black,
                    vertex: MoveVertex::Pass,
                    move_number: 1,
                },
                MoveDto {
                    color: PlayerColor::White,
                    vertex: MoveVertex::Point(PointDto { x: 3, y: 4 }),
                    move_number: 2,
                },
            ],
            root: None,
        };

        let serialized = serialize_sgf_document(&doc).unwrap();

        assert_eq!(serialized, "(;FF[4]GM[1]SZ[9]KM[0.5];B[];W[de])");
        assert_eq!(parse_sgf(&serialized).unwrap().moves, doc.moves);
    }

    #[test]
    fn serializes_escaped_property_values() {
        let doc = SgfDocument {
            board_size: 19,
            komi: 7.5,
            handicap: None,
            black_name: Some("A]B\\C\r\nD\rE".to_string()),
            white_name: Some("White".to_string()),
            result: Some("W+R]".to_string()),
            moves: Vec::new(),
            root: None,
        };

        let serialized = serialize_sgf_document(&doc).unwrap();

        assert!(serialized.contains("PB[A\\]B\\\\C\nD\nE]"));
        assert!(serialized.contains("RE[W+R\\]]"));
        let parsed = parse_sgf(&serialized).unwrap();
        assert_eq!(parsed.black_name.as_deref(), Some("A]B\\C\nD\nE"));
        assert_eq!(parsed.result.as_deref(), Some("W+R]"));
    }

    #[test]
    fn parse_serialize_parse_preserves_core_document_fields() {
        let original =
            parse_sgf("(;GM[1]FF[4]SZ[9]KM[6.5]HA[3]PB[A\\]lice]PW[Bob\\\\Lee]RE[W+2.5];B[aa];W[];B[ii])")
                .unwrap();

        let serialized = serialize_sgf_document(&original).unwrap();
        let reparsed = parse_sgf(&serialized).unwrap();

        assert_eq!(reparsed.board_size, original.board_size);
        assert_eq!(reparsed.komi, original.komi);
        assert_eq!(reparsed.handicap, original.handicap);
        assert_eq!(reparsed.black_name, original.black_name);
        assert_eq!(reparsed.white_name, original.white_name);
        assert_eq!(reparsed.result, original.result);
        assert_eq!(reparsed.moves, original.moves);
    }

    #[test]
    fn replays_captures_and_passes() {
        let positions = replay_sgf_positions("(;SZ[5];B[bb];W[ab];W[ba];W[cb];W[bc];B[])").unwrap();
        assert_initial_position(&positions);
        assert_eq!(positions.len(), 7);

        let capture = &positions[5];
        assert_eq!(capture.captures_white, 1);
        assert_eq!(capture.captures_black, 0);
        assert!(!capture.stones.iter().any(|stone| stone.x == 1 && stone.y == 1));
        assert!(matches!(
            positions[6].last_move.as_ref().unwrap().vertex,
            MoveVertex::Pass
        ));
        assert!(positions.iter().all(|position| position.errors.is_empty()));
    }

    #[test]
    fn reports_illegal_suicide_without_changing_board() {
        let positions = replay_sgf_positions("(;SZ[5];W[ab];W[ba];W[cb];W[bc];B[bb])").unwrap();
        assert_initial_position(&positions);
        assert_eq!(positions.len(), 6);

        let before_suicide = &positions[4];
        let final_position = positions.last().unwrap();
        assert_eq!(before_suicide.stones, final_position.stones);
        assert!(before_suicide.errors.is_empty());
        assert_eq!(final_position.move_number, 5);
        assert_eq!(final_position.stones.len(), 4);
        assert_eq!(final_position.errors.len(), 1);
        assert!(final_position.errors[0].contains("suicide"));
    }

    #[test]
    fn parses_first_variation_as_mainline() {
        let doc = parse_sgf("(;SZ[5];B[aa](;W[bb];B[cc])(;W[dd]))").unwrap();
        assert_eq!(doc.moves.len(), 3);
        assert_eq!(doc.moves[1].vertex, MoveVertex::Point(PointDto { x: 1, y: 1 }));
    }

    #[test]
    fn roundtrips_variations_comments_setup_and_pl() {
        let input = include_str!("../../../tests/golden/sgf_compat_variations.sgf");
        let doc = parse_sgf(input).unwrap();

        assert_eq!(doc.board_size, 5);
        assert_eq!(doc.komi, 0.5);
        assert_eq!(doc.black_name.as_deref(), Some("A]lice"));
        assert_eq!(doc.white_name.as_deref(), Some("Bob\\Lee"));
        assert_eq!(doc.moves.len(), 3);
        assert_eq!(doc.moves[0].color, PlayerColor::White);
        assert_eq!(doc.moves[1].vertex, MoveVertex::Point(PointDto { x: 4, y: 4 }));
        assert!(matches!(doc.moves[2].vertex, MoveVertex::Pass));

        let root = doc.root.as_ref().unwrap();
        assert_eq!(
            property_values(root, "C").unwrap(),
            &vec!["root ] comment\\done".to_string()]
        );
        assert_eq!(property_values(root, "PL").unwrap(), &vec!["W".to_string()]);
        assert_eq!(root.children[0].children.len(), 2);
        assert_eq!(
            property_values(&root.children[0].children[1], "C").unwrap(),
            &vec!["second branch ] keep".to_string()]
        );

        let serialized = serialize_sgf_document(&doc).unwrap();
        assert!(serialized.contains("(;B[ee]C[first branch];W[])"));
        assert!(serialized.contains("(;B[ad]C[second branch \\] keep])"));

        let reparsed = parse_sgf(&serialized).unwrap();
        assert_eq!(reparsed.root, doc.root);
        assert_eq!(reparsed.moves, doc.moves);
    }

    #[test]
    fn replay_applies_setup_stones_and_player_to_play() {
        let input = include_str!("../../../tests/golden/sgf_compat_variations.sgf");
        let positions = replay_sgf_positions(input).unwrap();

        assert_eq!(positions.len(), 4);
        let initial = &positions[0];
        assert_eq!(initial.to_play, PlayerColor::White);
        assert!(has_stone(initial, 0, 0, PlayerColor::Black));
        assert!(has_stone(initial, 2, 2, PlayerColor::White));
        assert!(!initial.stones.iter().any(|stone| stone.x == 1 && stone.y == 1));

        let first_move = &positions[1];
        assert!(has_stone(first_move, 3, 3, PlayerColor::White));
        assert_eq!(first_move.last_move.as_ref().unwrap().color, PlayerColor::White);

        let branch_move = &positions[2];
        assert!(has_stone(branch_move, 4, 4, PlayerColor::Black));
        assert!(matches!(
            positions[3].last_move.as_ref().unwrap().vertex,
            MoveVertex::Pass
        ));
        assert!(positions.iter().all(|position| position.errors.is_empty()));
    }

    fn assert_initial_position(positions: &[PositionDto]) {
        let initial = positions.first().unwrap();
        assert_eq!(initial.move_number, 0);
        assert_eq!(initial.to_play, PlayerColor::Black);
        assert!(initial.stones.is_empty());
        assert_eq!(initial.captures_black, 0);
        assert_eq!(initial.captures_white, 0);
        assert!(initial.last_move.is_none());
        assert!(initial.errors.is_empty());
    }

    fn has_stone(position: &PositionDto, x: u8, y: u8, color: PlayerColor) -> bool {
        position
            .stones
            .iter()
            .any(|stone| stone.x == x && stone.y == y && stone.color == color)
    }
}
