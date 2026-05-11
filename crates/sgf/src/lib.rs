use app_model::{
    GameDto, GameSummaryDto, MoveDto, MoveVertex, NodeId, PlayerColor, PointDto, PositionDto, SgfPropertyDto,
    SgfTreeDto, SgfTreeNodeDto, StoneDto,
};
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppendSgfMoveResult {
    pub sgf_text: String,
    pub new_node_id: NodeId,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeleteSgfNodeResult {
    pub sgf_text: String,
    pub parent_node_id: NodeId,
}

#[derive(Debug, Error)]
pub enum SgfError {
    #[error("SGF is empty")]
    Empty,
    #[error("unsupported or malformed SGF")]
    Malformed,
    #[error("SGF node was not found")]
    NodeNotFound,
    #[error("cannot delete the SGF root node")]
    CannotDeleteRoot,
    #[error("illegal SGF move: {0}")]
    IllegalMove(String),
    #[error("unsupported board size: {0}")]
    UnsupportedBoardSize(u8),
}

const FOX_ROOT_PROPERTY_ORDER: &[&str] = &[
    "GM", "FF", "CA", "AP", "ST", "RU", "SZ", "KM", "HA", "TM", "TC", "TT", "OT", "EV", "RO", "PC", "DT",
    "GN", "GC", "PB", "BR", "PW", "WR", "RE", "US", "SO", "CP", "AN", "ON", "BT", "WT", "PL", "C", "AB",
    "AW", "AE", "RN", "RL",
];

const FOX_ROOT_MULTI_VALUE_PROPERTIES: &[&str] = &["AB", "AW", "AE"];

/// Keep the first child variation as the mainline and drop sibling variations.
///
/// This is intentionally text-based so parentheses and escaped brackets inside
/// property values do not affect tree selection.
pub fn normalize_yike_sgf_mainline(input: &str) -> String {
    if input.is_empty() {
        return input.to_string();
    }
    let Some(start) = input.chars().position(|c| c == '(') else {
        return input.to_string();
    };
    let chars: Vec<char> = input.chars().collect();
    match parse_yike_game_tree(&chars, start) {
        Some((text, _)) => text,
        None => input.to_string(),
    }
}

/// Remove Fox payload backslashes that occur outside SGF property values.
///
/// Backslash escapes inside property values are preserved, including escaped
/// closing brackets.
pub fn sanitize_fox_sgf(input: &str) -> String {
    if input.trim().is_empty() {
        return input.to_string();
    }

    let text = input.replace('\u{FEFF}', "").trim().to_string();
    let chars: Vec<char> = text.chars().collect();
    let mut output = String::with_capacity(text.len());
    let mut inside_value = false;
    let mut index = 0;
    while index < chars.len() {
        let current = chars[index];
        if inside_value {
            output.push(current);
            if current == '\\' && index + 1 < chars.len() {
                index += 1;
                output.push(chars[index]);
            } else if current == ']' {
                inside_value = false;
            }
            index += 1;
            continue;
        }

        if current == '\\' {
            index += 1;
            continue;
        }
        output.push(current);
        if current == '[' {
            inside_value = true;
        }
        index += 1;
    }
    output
}

/// Normalize Fox SGF into a single-mainline, provider-friendly SGF string.
///
/// The normalizer sanitizes Fox payload escapes, promotes leading setup nodes
/// into the root, keeps common game/player metadata, and drops sibling
/// variations in favor of the first playable mainline.
pub fn normalize_fox_sgf(input: &str) -> String {
    let sanitized = sanitize_fox_sgf(input);
    if sanitized.trim().is_empty() {
        return sanitized;
    }

    let Ok(document) = parse_sgf(&sanitized) else {
        return sanitized;
    };
    let Some(root) = document.root else {
        return sanitized;
    };
    let normalized = SgfDocument {
        root: Some(build_fox_normalized_root(&root)),
        ..document
    };
    serialize_sgf_document(&normalized).unwrap_or(sanitized)
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

pub fn to_sgf_tree_dto(document: &SgfDocument) -> Result<Option<SgfTreeDto>, SgfError> {
    document
        .root
        .as_ref()
        .map(|root| build_sgf_tree_dto(root, document.board_size))
        .transpose()
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

pub fn update_sgf_node_comment(
    input: &str,
    node_id: NodeId,
    comment: Option<&str>,
) -> Result<String, SgfError> {
    let mut document = parse_sgf(input)?;
    let root = document.root.as_mut().ok_or(SgfError::Malformed)?;
    let node = find_sgf_node_mut(root, node_id).ok_or(SgfError::NodeNotFound)?;
    set_node_comment(node, comment);
    serialize_sgf_document(&document)
}

pub fn delete_sgf_node(input: &str, node_id: NodeId) -> Result<DeleteSgfNodeResult, SgfError> {
    let mut document = parse_sgf(input)?;
    let root = document.root.as_ref().ok_or(SgfError::Malformed)?;
    let mut target_path = find_sgf_node_path(root, node_id).ok_or(SgfError::NodeNotFound)?;
    let child_index = target_path.pop().ok_or(SgfError::CannotDeleteRoot)?;
    let parent_node_id = stable_sgf_node_id(&target_path);

    let root = document.root.as_mut().ok_or(SgfError::Malformed)?;
    let parent = find_sgf_node_mut_at_path(root, &target_path).ok_or(SgfError::NodeNotFound)?;
    if child_index >= parent.children.len() {
        return Err(SgfError::NodeNotFound);
    }
    parent.children.remove(child_index);

    Ok(DeleteSgfNodeResult {
        sgf_text: serialize_sgf_document(&document)?,
        parent_node_id,
    })
}

pub fn append_sgf_move(
    input: &str,
    parent_node_id: NodeId,
    color: PlayerColor,
    vertex: MoveVertex,
) -> Result<AppendSgfMoveResult, SgfError> {
    let mut document = parse_sgf(input)?;
    let root = document.root.as_ref().ok_or(SgfError::Malformed)?;
    let parent_path = find_sgf_node_path(root, parent_node_id).ok_or(SgfError::NodeNotFound)?;
    let parent_child_count = find_sgf_node_at_path(root, &parent_path)
        .ok_or(SgfError::NodeNotFound)?
        .children
        .len();

    let mut replay = replay_sgf_state_at_path(&document, &parent_path)?;
    if !replay.errors.is_empty() {
        return Err(SgfError::IllegalMove(replay.errors.join("; ")));
    }
    let sgf_move = MoveDto {
        color,
        vertex: vertex.clone(),
        move_number: replay.move_number + 1,
    };
    replay
        .board
        .play(to_core_color(color), to_core_vertex(&vertex))
        .map_err(|error| SgfError::IllegalMove(format_rule_error(&sgf_move, error)))?;

    let new_node = SgfNode {
        properties: vec![SgfProperty {
            key: match color {
                PlayerColor::Black => "B".to_string(),
                PlayerColor::White => "W".to_string(),
            },
            values: vec![serialize_vertex(&vertex, document.board_size)?],
        }],
        children: Vec::new(),
    };
    let root = document.root.as_mut().ok_or(SgfError::Malformed)?;
    let parent = find_sgf_node_mut_at_path(root, &parent_path).ok_or(SgfError::NodeNotFound)?;
    parent.children.push(new_node);

    let mut new_path = parent_path;
    new_path.push(parent_child_count);
    let new_node_id = stable_sgf_node_id(&new_path);
    Ok(AppendSgfMoveResult {
        sgf_text: serialize_sgf_document(&document)?,
        new_node_id,
    })
}

pub fn replay_sgf_position_at_node(input: &str, node_id: NodeId) -> Result<PositionDto, SgfError> {
    let document = parse_sgf(input)?;
    let root = document.root.as_ref().ok_or(SgfError::Malformed)?;
    let path = find_sgf_node_path(root, node_id).ok_or(SgfError::NodeNotFound)?;
    replay_sgf_position_at_path(&document, &path)
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

fn parse_yike_game_tree(chars: &[char], start: usize) -> Option<(String, usize)> {
    if chars.get(start) != Some(&'(') {
        return None;
    }

    let mut output = String::from("(");
    let mut in_value = false;
    let mut escaping = false;
    let mut copied_first_child_tree = false;
    let mut index = start + 1;

    while index < chars.len() {
        let ch = chars[index];
        if in_value {
            output.push(ch);
            if escaping {
                escaping = false;
            } else if ch == '\\' {
                escaping = true;
            } else if ch == ']' {
                in_value = false;
            }
            index += 1;
            continue;
        }

        match ch {
            '[' => {
                in_value = true;
                output.push(ch);
                index += 1;
            }
            '(' => {
                let (child, next_index) = parse_yike_game_tree(chars, index)?;
                if !copied_first_child_tree {
                    if child.len() >= 2 {
                        output.push_str(&child[1..child.len() - 1]);
                    }
                    copied_first_child_tree = true;
                }
                index = next_index;
            }
            ')' => {
                output.push(ch);
                return Some((output, index + 1));
            }
            _ => {
                output.push(ch);
                index += 1;
            }
        }
    }

    None
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FoxMove {
    color: String,
    coordinate: String,
}

#[derive(Debug, Clone)]
struct FoxWindow {
    index: usize,
    context: Vec<FoxMove>,
    sequence: Vec<FoxMove>,
    skip_sequence: Vec<FoxMove>,
    augmented: Vec<FoxMove>,
}

#[derive(Debug, Clone)]
struct FoxCandidate {
    index: usize,
    target: Vec<FoxMove>,
    overlap: usize,
    uses_context: bool,
    append_size: usize,
    variant_rank: i32,
}

impl FoxWindow {
    fn new(index: usize, context: Vec<FoxMove>, sequence: Vec<FoxMove>) -> Self {
        let skip_sequence = if sequence.len() > 1 {
            sequence[1..].to_vec()
        } else {
            Vec::new()
        };
        let mut augmented = Vec::with_capacity(context.len() + sequence.len());
        augmented.extend(context.iter().cloned());
        augmented.extend(sequence.iter().cloned());
        Self {
            index,
            context,
            sequence,
            skip_sequence,
            augmented,
        }
    }
}

fn build_fox_normalized_root(root: &SgfNode) -> SgfNode {
    let mainline = mainline_nodes(root);
    let root_properties = build_fox_root_properties(&mainline);
    let root_moves = extract_fox_moves(&root.properties);
    let default_mainline_moves = mainline
        .iter()
        .skip(1)
        .flat_map(|node| extract_fox_moves(&node.properties))
        .collect::<Vec<_>>();
    let mainline_moves = recover_preferred_fox_moves(root, &default_mainline_moves, &root_moves);
    let next_color = mainline_moves.first().map(|sgf_move| sgf_move.color.as_str());
    let root_prefix = choose_compatible_fox_root_prefix(&root_moves, next_color);
    let moves = normalize_fox_moves(&root_prefix, &mainline_moves);
    build_fox_root_tree(root_properties, &moves)
}

fn build_fox_root_properties(mainline: &[&SgfNode]) -> Vec<SgfProperty> {
    let mut collected = Vec::new();
    for (index, node) in mainline.iter().enumerate() {
        if index > 0 && has_move_property(node) {
            break;
        }
        collected.extend(node.properties.iter().cloned());
    }
    build_clean_fox_root_properties(&collected)
}

fn build_clean_fox_root_properties(properties: &[SgfProperty]) -> Vec<SgfProperty> {
    let mut single_value_properties = std::collections::HashMap::<String, SgfProperty>::new();
    let mut multi_value_properties = std::collections::HashMap::<String, Vec<String>>::new();

    for property in properties {
        if !is_fox_root_property(&property.key) || property.values.is_empty() {
            continue;
        }

        if FOX_ROOT_MULTI_VALUE_PROPERTIES.contains(&property.key.as_str()) {
            multi_value_properties
                .entry(property.key.clone())
                .or_default()
                .extend(property.values.iter().cloned());
        } else {
            let existing = single_value_properties.get(&property.key);
            if existing.is_none() || property_has_content(property) {
                single_value_properties.insert(property.key.clone(), property.clone());
            }
        }
    }

    ensure_default_fox_root_property(&mut single_value_properties, "GM", "1");
    ensure_default_fox_root_property(&mut single_value_properties, "FF", "4");
    ensure_default_fox_root_property(&mut single_value_properties, "CA", "UTF-8");
    ensure_default_fox_root_property(&mut single_value_properties, "SZ", "19");

    let mut ordered = Vec::new();
    for key in FOX_ROOT_PROPERTY_ORDER {
        if FOX_ROOT_MULTI_VALUE_PROPERTIES.contains(key) {
            if let Some(values) = multi_value_properties.remove(*key) {
                if !values.is_empty() {
                    ordered.push(SgfProperty {
                        key: (*key).to_string(),
                        values,
                    });
                }
            }
            continue;
        }
        if let Some(property) = single_value_properties.remove(*key) {
            ordered.push(property);
        }
    }
    ordered
}

fn is_fox_root_property(key: &str) -> bool {
    FOX_ROOT_PROPERTY_ORDER.contains(&key)
}

fn ensure_default_fox_root_property(
    properties: &mut std::collections::HashMap<String, SgfProperty>,
    key: &str,
    value: &str,
) {
    properties.entry(key.to_string()).or_insert_with(|| SgfProperty {
        key: key.to_string(),
        values: vec![value.to_string()],
    });
}

fn property_has_content(property: &SgfProperty) -> bool {
    property.values.iter().any(|value| !value.trim().is_empty())
}

fn extract_fox_moves(properties: &[SgfProperty]) -> Vec<FoxMove> {
    properties
        .iter()
        .filter(|property| property.key == "B" || property.key == "W")
        .flat_map(|property| {
            property.values.iter().map(|value| FoxMove {
                color: property.key.clone(),
                coordinate: value.clone(),
            })
        })
        .collect()
}

fn recover_preferred_fox_moves(
    root: &SgfNode,
    default_moves: &[FoxMove],
    root_moves: &[FoxMove],
) -> Vec<FoxMove> {
    if !looks_like_windowed_fox(root) {
        return default_moves.to_vec();
    }

    let windows = extract_fox_windows(&root.children);
    if windows.len() < 5 {
        return default_moves.to_vec();
    }
    let recovered = recover_windowed_fox_moves(&windows, root_moves);
    if recovered.len() >= 15.max(default_moves.len() + 4) {
        recovered
    } else {
        default_moves.to_vec()
    }
}

fn looks_like_windowed_fox(root: &SgfNode) -> bool {
    if root.children.len() < 20 {
        return false;
    }
    let candidate_children = root
        .children
        .iter()
        .filter(|child| {
            let move_nodes = count_mainline_nodes_with_moves(child);
            !has_sibling_variations(child) && (7..=10).contains(&move_nodes)
        })
        .count();
    candidate_children >= 10.max(root.children.len() / 3)
}

fn count_mainline_nodes_with_moves(node: &SgfNode) -> usize {
    mainline_nodes(node)
        .iter()
        .filter(|node| !extract_fox_moves(&node.properties).is_empty())
        .count()
}

fn has_sibling_variations(node: &SgfNode) -> bool {
    node.children.len() > 1 || node.children.iter().any(has_sibling_variations)
}

fn extract_fox_windows(children: &[SgfNode]) -> Vec<FoxWindow> {
    children
        .iter()
        .enumerate()
        .filter_map(|(index, child)| {
            let mut context = Vec::new();
            let mut sequence = Vec::new();
            let mut first_node = true;
            for node in mainline_nodes(child) {
                let moves = extract_fox_moves(&node.properties);
                if moves.is_empty() {
                    continue;
                }
                if first_node && moves.len() >= 2 {
                    sequence.push(moves[0].clone());
                    context.push(moves[1].clone());
                } else {
                    sequence.push(moves[0].clone());
                }
                first_node = false;
            }
            if sequence.is_empty() {
                None
            } else {
                Some(FoxWindow::new(index, context, sequence))
            }
        })
        .collect()
}

fn recover_windowed_fox_moves(windows: &[FoxWindow], root_moves: &[FoxMove]) -> Vec<FoxMove> {
    let seeds = pick_seed_fox_windows(windows, root_moves);
    if seeds.is_empty() {
        return Vec::new();
    }
    let root_prefixes = build_fox_root_prefix_candidates(root_moves);
    let mut best_moves = Vec::new();
    let mut best_score = i32::MIN;
    let mut best_priority = i32::MIN;
    for root_prefix in root_prefixes {
        for seed in &seeds {
            let priority = fox_seed_priority(seed, root_moves);
            let attempt = build_windowed_fox_sequence(seed, windows, &root_prefix);
            if attempt.is_empty() {
                continue;
            }
            let score = score_recovered_fox_moves(&attempt, &root_prefix, root_moves);
            if score > best_score
                || (score == best_score && priority > best_priority)
                || (score == best_score && priority == best_priority && attempt.len() > best_moves.len())
            {
                best_moves = attempt;
                best_score = score;
                best_priority = priority;
            }
        }
    }
    best_moves
}

fn build_fox_root_prefix_candidates(root_moves: &[FoxMove]) -> Vec<Vec<FoxMove>> {
    let mut candidates = Vec::new();
    add_fox_root_prefix_candidate(&mut candidates, root_moves.to_vec());
    if let Some(last) = root_moves.last() {
        add_fox_root_prefix_candidate(&mut candidates, vec![last.clone()]);
    }
    if root_moves.len() > 1 {
        let mut reversed = root_moves.to_vec();
        reversed.reverse();
        add_fox_root_prefix_candidate(&mut candidates, reversed);
    }
    add_fox_root_prefix_candidate(&mut candidates, Vec::new());
    if candidates.is_empty() {
        candidates.push(Vec::new());
    }
    candidates
}

fn add_fox_root_prefix_candidate(candidates: &mut Vec<Vec<FoxMove>>, prefix: Vec<FoxMove>) {
    if !prefix.is_empty() && !fox_moves_are_alternating(&prefix) {
        return;
    }
    if !candidates.iter().any(|candidate| candidate == &prefix) {
        candidates.push(prefix);
    }
}

fn pick_seed_fox_windows(windows: &[FoxWindow], root_moves: &[FoxMove]) -> Vec<FoxWindow> {
    let mut ordered = windows.to_vec();
    ordered.sort_by(|left, right| {
        fox_seed_priority(right, root_moves)
            .cmp(&fox_seed_priority(left, root_moves))
            .then_with(|| left.index.cmp(&right.index))
    });
    ordered.truncate(16);
    ordered
}

fn fox_seed_priority(window: &FoxWindow, root_moves: &[FoxMove]) -> i32 {
    let last_root_color = root_moves.last().map(|sgf_move| sgf_move.color.as_str());
    let last_root_move = root_moves.last();
    if !window.context.is_empty() && last_root_move == window.context.first() {
        return 4;
    }
    if window.context.is_empty()
        && !window.sequence.is_empty()
        && last_root_color.is_some_and(|color| color != window.sequence[0].color)
    {
        return 3;
    }
    if !window.sequence.is_empty() && last_root_color.is_some_and(|color| color != window.sequence[0].color) {
        return 2;
    }
    if window.context.is_empty() {
        return 1;
    }
    0
}

fn build_windowed_fox_sequence(
    seed: &FoxWindow,
    windows: &[FoxWindow],
    root_prefix: &[FoxMove],
) -> Vec<FoxMove> {
    let mut current = root_prefix.to_vec();
    let seed_overlap = if root_prefix.is_empty() {
        0
    } else {
        compute_fox_overlap(root_prefix, &seed.sequence)
    };
    if !root_prefix.is_empty() && !can_append_fox_moves(root_prefix, &seed.sequence, seed_overlap) {
        return Vec::new();
    }
    current.extend(seed.sequence[seed_overlap..].iter().cloned());
    if !fox_moves_are_alternating(&current) {
        return Vec::new();
    }

    let mut used = std::collections::HashSet::from([seed.index]);
    while current.len() < 600 {
        let mut best = None;
        for window in windows {
            if used.contains(&window.index) {
                continue;
            }
            best = select_better_fox_candidate(
                best,
                build_fox_candidate(&current, &window.sequence, window.index, false, 3),
            );
            if !window.skip_sequence.is_empty() {
                best = select_better_fox_candidate(
                    best,
                    build_fox_candidate(&current, &window.skip_sequence, window.index, false, 2),
                );
            }
            if !window.context.is_empty() {
                best = select_better_fox_candidate(
                    best,
                    build_fox_candidate(&current, &window.augmented, window.index, true, 1),
                );
            }
        }
        let Some(best) = best else {
            break;
        };
        if best.overlap < 2 {
            break;
        }
        current.extend(best.target[best.overlap..].iter().cloned());
        used.insert(best.index);
    }

    if current.len() <= root_prefix.len() {
        Vec::new()
    } else {
        current[root_prefix.len()..].to_vec()
    }
}

fn score_recovered_fox_moves(
    recovered_moves: &[FoxMove],
    root_prefix: &[FoxMove],
    root_moves: &[FoxMove],
) -> i32 {
    let mut score = recovered_moves.len() as i32 * 100;
    score += root_prefix.len() as i32 * 8;
    if !root_prefix.is_empty()
        && recovered_moves.len() > root_prefix.len()
        && recovered_moves[0].color != root_prefix[root_prefix.len() - 1].color
    {
        score += 24;
    }
    score -= repeat_fox_penalty(recovered_moves);
    if !root_moves.is_empty()
        && recovered_moves.len() >= root_moves.len()
        && &recovered_moves[..root_moves.len()] == root_moves
    {
        score += 20;
    }
    score
}

fn repeat_fox_penalty(moves: &[FoxMove]) -> i32 {
    let mut penalty = 0;
    for index in 0..moves.len() {
        for previous in index.saturating_sub(12)..index {
            if moves[index] == moves[previous] {
                penalty += 12.max(120 - (index - previous) as i32 * 6);
            }
        }
    }
    for block_size in 2..=4 {
        penalty += repeated_fox_block_penalty(moves, block_size);
    }
    penalty
}

fn repeated_fox_block_penalty(moves: &[FoxMove], block_size: usize) -> i32 {
    if moves.len() < block_size * 2 {
        return 0;
    }
    let mut penalty = 0;
    let mut first_seen = std::collections::HashMap::<String, usize>::new();
    for index in 0..=moves.len() - block_size {
        let key = fox_moves_block_key(moves, index, block_size);
        if let Some(previous_index) = first_seen.insert(key, index) {
            if index - previous_index <= 16 {
                penalty += block_size as i32 * 180;
            }
        }
    }
    penalty
}

fn fox_moves_block_key(moves: &[FoxMove], start: usize, block_size: usize) -> String {
    let mut key = String::with_capacity(block_size * 8);
    for sgf_move in &moves[start..start + block_size] {
        key.push_str(&sgf_move.color);
        key.push(':');
        key.push_str(&sgf_move.coordinate);
        key.push('|');
    }
    key
}

fn build_fox_candidate(
    current: &[FoxMove],
    target: &[FoxMove],
    index: usize,
    uses_context: bool,
    variant_rank: i32,
) -> Option<FoxCandidate> {
    if target.is_empty() {
        return None;
    }
    let overlap = compute_fox_overlap(current, target);
    if overlap == 0 || !can_append_fox_moves(current, target, overlap) {
        return None;
    }
    Some(FoxCandidate {
        index,
        target: target.to_vec(),
        overlap,
        uses_context,
        append_size: target.len() - overlap,
        variant_rank,
    })
}

fn select_better_fox_candidate(
    current: Option<FoxCandidate>,
    next: Option<FoxCandidate>,
) -> Option<FoxCandidate> {
    let Some(next) = next else {
        return current;
    };
    let Some(current) = current else {
        return Some(next);
    };
    if next.overlap != current.overlap {
        return Some(if next.overlap > current.overlap {
            next
        } else {
            current
        });
    }
    if next.append_size != current.append_size {
        return Some(if next.append_size > current.append_size {
            next
        } else {
            current
        });
    }
    if next.variant_rank != current.variant_rank {
        return Some(if next.variant_rank > current.variant_rank {
            next
        } else {
            current
        });
    }
    if next.uses_context != current.uses_context {
        return Some(if current.uses_context { current } else { next });
    }
    Some(if next.index < current.index { next } else { current })
}

fn compute_fox_overlap(current: &[FoxMove], target: &[FoxMove]) -> usize {
    let mut best = 0;
    let max = current.len().min(target.len());
    for size in 1..=max {
        if current[current.len() - size..] == target[..size] {
            best = size;
        }
    }
    best
}

fn can_append_fox_moves(current: &[FoxMove], target: &[FoxMove], overlap: usize) -> bool {
    if overlap >= target.len() {
        return false;
    }
    let appended = &target[overlap..];
    if appended.is_empty() {
        return false;
    }
    if !current.is_empty() && current[current.len() - 1].color == appended[0].color {
        return false;
    }
    fox_moves_are_alternating(appended)
}

fn choose_compatible_fox_root_prefix(root_moves: &[FoxMove], next_color: Option<&str>) -> Vec<FoxMove> {
    let mut best = Vec::new();
    for index in 1..=root_moves.len() {
        let prefix = &root_moves[..index];
        if !fox_moves_are_alternating(prefix) {
            continue;
        }
        if next_color.is_some_and(|color| color == prefix[prefix.len() - 1].color) {
            continue;
        }
        if prefix.len() > best.len() {
            best = prefix.to_vec();
        }
    }
    if !best.is_empty() {
        return best;
    }
    for index in 1..=root_moves.len() {
        let prefix = &root_moves[..index];
        if fox_moves_are_alternating(prefix) && prefix.len() > best.len() {
            best = prefix.to_vec();
        }
    }
    best
}

fn fox_moves_are_alternating(moves: &[FoxMove]) -> bool {
    moves.windows(2).all(|window| window[0].color != window[1].color)
}

fn normalize_fox_moves(root_moves: &[FoxMove], mainline_moves: &[FoxMove]) -> Vec<FoxMove> {
    let mut normalized = Vec::new();
    let mut last_color = append_normalized_fox_moves(&mut normalized, root_moves, None);
    append_normalized_fox_moves(&mut normalized, mainline_moves, last_color.take());
    normalized
}

fn append_normalized_fox_moves(
    target: &mut Vec<FoxMove>,
    source: &[FoxMove],
    last_color: Option<String>,
) -> Option<String> {
    let mut current_last_color = last_color;
    for sgf_move in source {
        if current_last_color.as_ref() != Some(&sgf_move.color) {
            target.push(sgf_move.clone());
            current_last_color = Some(sgf_move.color.clone());
        }
    }
    current_last_color
}

fn build_fox_root_tree(root_properties: Vec<SgfProperty>, moves: &[FoxMove]) -> SgfNode {
    let mut next = None;
    for sgf_move in moves.iter().rev() {
        let children = next.into_iter().collect();
        next = Some(SgfNode {
            properties: vec![SgfProperty {
                key: sgf_move.color.clone(),
                values: vec![sgf_move.coordinate.clone()],
            }],
            children,
        });
    }

    SgfNode {
        properties: root_properties,
        children: next.into_iter().collect(),
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

fn build_sgf_tree_dto(root: &SgfNode, board_size: u8) -> Result<SgfTreeDto, SgfError> {
    let mut nodes = Vec::new();
    let root_id = push_sgf_tree_node(root, SgfTreeNodeContext::root(), board_size, &mut nodes)?;
    Ok(SgfTreeDto { root_id, nodes })
}

#[derive(Debug, Clone)]
struct SgfTreeNodeContext {
    parent_id: Option<NodeId>,
    path: Vec<usize>,
    variation_index: usize,
    depth: u32,
    previous_move_number: u32,
    is_mainline: bool,
}

impl SgfTreeNodeContext {
    fn root() -> Self {
        Self {
            parent_id: None,
            path: Vec::new(),
            variation_index: 0,
            depth: 0,
            previous_move_number: 0,
            is_mainline: true,
        }
    }

    fn child(&self, parent_id: NodeId, variation_index: usize, previous_move_number: u32) -> Self {
        let mut path = self.path.clone();
        path.push(variation_index);
        Self {
            parent_id: Some(parent_id),
            path,
            variation_index,
            depth: self.depth + 1,
            previous_move_number,
            is_mainline: self.is_mainline && variation_index == 0,
        }
    }
}

fn push_sgf_tree_node(
    node: &SgfNode,
    context: SgfTreeNodeContext,
    board_size: u8,
    nodes: &mut Vec<SgfTreeNodeDto>,
) -> Result<NodeId, SgfError> {
    let id = stable_sgf_node_id(&context.path);
    let (color, vertex) = node_move_metadata(node, board_size)?;
    let move_number = color.map(|_| context.previous_move_number + 1);
    let child_previous_move_number = move_number.unwrap_or(context.previous_move_number);
    let node_index = nodes.len();

    nodes.push(SgfTreeNodeDto {
        id,
        parent_id: context.parent_id,
        child_ids: Vec::new(),
        variation_index: context.variation_index,
        depth: context.depth,
        move_number,
        color,
        vertex,
        name: first_property_value(node, "N").cloned(),
        comment: first_property_value(node, "C").cloned(),
        properties: node_property_dtos(node),
        is_mainline: context.is_mainline,
    });

    let mut child_ids = Vec::with_capacity(node.children.len());
    for (variation_index, child) in node.children.iter().enumerate() {
        let child_context = context.child(id, variation_index, child_previous_move_number);
        child_ids.push(push_sgf_tree_node(child, child_context, board_size, nodes)?);
    }
    nodes[node_index].child_ids = child_ids;

    Ok(id)
}

fn stable_sgf_node_id(path: &[usize]) -> NodeId {
    let mut high = 0x7367_662d_7472_6565_2d6e_6f64_652d_7631u128;
    let mut low = 0x9e37_79b9_7f4a_7c15_d1b5_4a32_d192_ed03u128;
    for (depth, index) in path.iter().enumerate() {
        let part = ((*index as u128) << 32) ^ depth as u128 ^ 0xa076_1d64_78bd_642f;
        high ^= part;
        high = high.rotate_left(17).wrapping_mul(0xe703_7ed1_a0b4_28db);
        low ^= high.wrapping_add(part.rotate_left(31));
        low = low.rotate_left(29).wrapping_mul(0x8ebc_6af0_9c88_c6e3);
    }
    Uuid::from_u128(high ^ low ^ path.len() as u128)
}

fn find_sgf_node_path(root: &SgfNode, node_id: NodeId) -> Option<Vec<usize>> {
    let mut path = Vec::new();
    find_sgf_node_path_inner(root, node_id, &mut path)
}

fn find_sgf_node_path_inner(node: &SgfNode, node_id: NodeId, path: &mut Vec<usize>) -> Option<Vec<usize>> {
    if stable_sgf_node_id(path) == node_id {
        return Some(path.clone());
    }
    for (index, child) in node.children.iter().enumerate() {
        path.push(index);
        if let Some(found) = find_sgf_node_path_inner(child, node_id, path) {
            return Some(found);
        }
        path.pop();
    }
    None
}

fn find_sgf_node_mut(root: &mut SgfNode, node_id: NodeId) -> Option<&mut SgfNode> {
    let path = find_sgf_node_path(root, node_id)?;
    find_sgf_node_mut_at_path(root, &path)
}

fn find_sgf_node_at_path<'a>(root: &'a SgfNode, path: &[usize]) -> Option<&'a SgfNode> {
    let mut current = root;
    for index in path {
        current = current.children.get(*index)?;
    }
    Some(current)
}

fn find_sgf_node_mut_at_path<'a>(root: &'a mut SgfNode, path: &[usize]) -> Option<&'a mut SgfNode> {
    let mut current = root;
    for index in path {
        current = current.children.get_mut(*index)?;
    }
    Some(current)
}

fn set_node_comment(node: &mut SgfNode, comment: Option<&str>) {
    let Some(comment) = comment.filter(|value| !value.is_empty()) else {
        node.properties.retain(|property| property.key != "C");
        return;
    };

    if let Some(property) = node.properties.iter_mut().find(|property| property.key == "C") {
        if property.values.is_empty() {
            property.values.push(comment.to_string());
        } else {
            property.values[0] = comment.to_string();
        }
        return;
    }

    node.properties.push(SgfProperty {
        key: "C".to_string(),
        values: vec![comment.to_string()],
    });
}

fn replay_sgf_position_at_path(document: &SgfDocument, path: &[usize]) -> Result<PositionDto, SgfError> {
    let replay = replay_sgf_state_at_path(document, path)?;
    Ok(PositionDto {
        board_size: document.board_size,
        move_number: replay.move_number,
        to_play: replay.to_play,
        stones: stones_from_board(&replay.board),
        captures_black: replay.captures_black,
        captures_white: replay.captures_white,
        last_move: replay.last_move,
        errors: replay.errors,
    })
}

fn replay_sgf_state_at_path(document: &SgfDocument, path: &[usize]) -> Result<SgfReplayState, SgfError> {
    let mut replay = SgfReplayState::new(document.board_size)?;
    let mut node = document.root.as_ref().ok_or(SgfError::Malformed)?;

    replay_sgf_node(node, &mut replay)?;

    for index in path {
        node = node.children.get(*index).ok_or(SgfError::NodeNotFound)?;
        replay_sgf_node(node, &mut replay)?;
    }

    Ok(replay)
}

struct SgfReplayState {
    board_size: u8,
    board: Board,
    captures_black: u32,
    captures_white: u32,
    to_play: PlayerColor,
    move_number: u32,
    last_move: Option<MoveDto>,
    errors: Vec<String>,
}

impl SgfReplayState {
    fn new(board_size: u8) -> Result<Self, SgfError> {
        Ok(Self {
            board_size,
            board: Board::new(board_size).map_err(|_| SgfError::UnsupportedBoardSize(board_size))?,
            captures_black: 0,
            captures_white: 0,
            to_play: PlayerColor::Black,
            move_number: 0,
            last_move: None,
            errors: Vec::new(),
        })
    }
}

fn replay_sgf_node(node: &SgfNode, replay: &mut SgfReplayState) -> Result<(), SgfError> {
    apply_setup_properties(&mut replay.board, node, replay.board_size)?;
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
        replay.move_number += 1;
        let sgf_move = MoveDto {
            color,
            vertex: parse_vertex(raw, replay.board_size)?,
            move_number: replay.move_number,
        };
        match replay
            .board
            .play(to_core_color(sgf_move.color), to_core_vertex(&sgf_move.vertex))
        {
            Ok(outcome) => match sgf_move.color {
                PlayerColor::Black => replay.captures_black += outcome.captured.len() as u32,
                PlayerColor::White => replay.captures_white += outcome.captured.len() as u32,
            },
            Err(error) => replay.errors.push(format_rule_error(&sgf_move, error)),
        }
        replay.to_play = sgf_move.color.opponent();
        replay.last_move = Some(sgf_move);
    }
    if let Some(color) = player_to_play(node)? {
        replay.to_play = color;
    }
    Ok(())
}

fn node_move_metadata(
    node: &SgfNode,
    board_size: u8,
) -> Result<(Option<PlayerColor>, Option<MoveVertex>), SgfError> {
    for property in &node.properties {
        let color = match property.key.as_str() {
            "B" => PlayerColor::Black,
            "W" => PlayerColor::White,
            _ => continue,
        };
        let Some(raw) = property.values.first() else {
            return Err(SgfError::Malformed);
        };
        return Ok((Some(color), Some(parse_vertex(raw, board_size)?)));
    }

    Ok((None, None))
}

fn first_property_value<'a>(node: &'a SgfNode, key: &str) -> Option<&'a String> {
    property_values(node, key).and_then(|values| values.first())
}

fn node_property_dtos(node: &SgfNode) -> Vec<SgfPropertyDto> {
    node.properties
        .iter()
        .map(|property| SgfPropertyDto {
            key: property.key.clone(),
            values: property.values.clone(),
        })
        .collect()
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
    fn exposes_sgf_tree_dto_with_variations_and_comments() {
        let doc = parse_sgf("(;SZ[5]C[root];B[aa]N[one]C[first](;W[bb]C[main])(;W[cc]N[var]C[branch];B[]))")
            .unwrap();
        let tree = to_sgf_tree_dto(&doc).unwrap().unwrap();

        assert_eq!(tree.nodes.len(), 5);

        let root = tree.nodes.iter().find(|node| node.id == tree.root_id).unwrap();
        assert_eq!(root.parent_id, None);
        assert_eq!(root.depth, 0);
        assert_eq!(root.move_number, None);
        assert_eq!(root.comment.as_deref(), Some("root"));
        assert_eq!(root.child_ids.len(), 1);
        assert!(root.is_mainline);

        let first_move = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap();
        assert_eq!(first_move.parent_id, Some(root.id));
        assert_eq!(first_move.name.as_deref(), Some("one"));
        assert_eq!(first_move.comment.as_deref(), Some("first"));
        assert_eq!(first_move.color, Some(PlayerColor::Black));
        assert_eq!(
            first_move.vertex,
            Some(MoveVertex::Point(PointDto { x: 0, y: 0 }))
        );
        assert_eq!(first_move.child_ids.len(), 2);

        let mainline_reply = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("main"))
            .unwrap();
        assert_eq!(mainline_reply.parent_id, Some(first_move.id));
        assert_eq!(mainline_reply.variation_index, 0);
        assert_eq!(mainline_reply.move_number, Some(2));
        assert!(mainline_reply.is_mainline);

        let branch_reply = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch"))
            .unwrap();
        assert_eq!(branch_reply.parent_id, Some(first_move.id));
        assert_eq!(branch_reply.variation_index, 1);
        assert_eq!(branch_reply.move_number, Some(2));
        assert_eq!(branch_reply.name.as_deref(), Some("var"));
        assert!(!branch_reply.is_mainline);

        let branch_pass = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(3))
            .unwrap();
        assert_eq!(branch_pass.parent_id, Some(branch_reply.id));
        assert_eq!(branch_pass.vertex, Some(MoveVertex::Pass));
        assert!(!branch_pass.is_mainline);
    }

    #[test]
    fn sgf_tree_node_ids_are_stable_for_same_parse_result_shape() {
        let input = "(;SZ[5]C[root];B[aa](;W[bb]C[main])(;W[cc]C[branch]))";
        let first = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();
        let second = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();

        let first_ids: Vec<NodeId> = first.nodes.iter().map(|node| node.id).collect();
        let second_ids: Vec<NodeId> = second.nodes.iter().map(|node| node.id).collect();
        assert_eq!(first_ids, second_ids);
    }

    #[test]
    fn updates_mainline_comment_roundtrip() {
        let input = "(;SZ[5]C[root];B[aa]C[old];W[bb])";
        let doc = parse_sgf(input).unwrap();
        let tree = to_sgf_tree_dto(&doc).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;

        let updated = update_sgf_node_comment(input, node_id, Some("new mainline")).unwrap();
        let reparsed = parse_sgf(&updated).unwrap();
        let reparsed_tree = to_sgf_tree_dto(&reparsed).unwrap().unwrap();
        let node = reparsed_tree
            .nodes
            .iter()
            .find(|node| node.id == node_id)
            .unwrap();

        assert_eq!(node.comment.as_deref(), Some("new mainline"));
        assert_eq!(serialize_sgf_document(&reparsed).unwrap(), updated);
    }

    #[test]
    fn updates_branch_comment_roundtrip_without_touching_mainline_sibling() {
        let input = "(;SZ[5];B[aa](;W[bb]C[main])(;W[cc]C[branch]))";
        let doc = parse_sgf(input).unwrap();
        let tree = to_sgf_tree_dto(&doc).unwrap().unwrap();
        let branch_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch"))
            .unwrap()
            .id;
        let mainline_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("main"))
            .unwrap()
            .id;

        let updated = update_sgf_node_comment(input, branch_id, Some("branch updated")).unwrap();
        let reparsed_tree = to_sgf_tree_dto(&parse_sgf(&updated).unwrap()).unwrap().unwrap();
        let branch = reparsed_tree
            .nodes
            .iter()
            .find(|node| node.id == branch_id)
            .unwrap();
        let mainline = reparsed_tree
            .nodes
            .iter()
            .find(|node| node.id == mainline_id)
            .unwrap();

        assert_eq!(branch.comment.as_deref(), Some("branch updated"));
        assert_eq!(mainline.comment.as_deref(), Some("main"));
        assert!(updated.contains("(;W[bb]C[main])"));
        assert!(updated.contains("(;W[cc]C[branch updated])"));
    }

    #[test]
    fn appends_move_to_leaf_mainline_roundtrip_and_exposes_new_node_id() {
        let input = "(;SZ[5]XY[keep];B[aa]C[first])";
        let tree = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;

        let result = append_sgf_move(
            input,
            parent_id,
            PlayerColor::White,
            MoveVertex::Point(PointDto { x: 1, y: 1 }),
        )
        .unwrap();

        assert_eq!(result.sgf_text, "(;SZ[5]XY[keep];B[aa]C[first];W[bb])");
        let reparsed = parse_sgf(&result.sgf_text).unwrap();
        let reparsed_tree = to_sgf_tree_dto(&reparsed).unwrap().unwrap();
        let new_node = reparsed_tree
            .nodes
            .iter()
            .find(|node| node.id == result.new_node_id)
            .unwrap();
        assert_eq!(new_node.parent_id, Some(parent_id));
        assert_eq!(new_node.move_number, Some(2));
        assert_eq!(new_node.color, Some(PlayerColor::White));
        assert_eq!(new_node.vertex, Some(MoveVertex::Point(PointDto { x: 1, y: 1 })));
        assert_eq!(reparsed.moves.len(), 2);
    }

    #[test]
    fn appending_under_parent_with_existing_child_creates_sibling_variation() {
        let input = "(;SZ[5];B[aa](;W[bb]C[main])(;W[cc]C[branch]))";
        let tree = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();
        let parent = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap();

        let result = append_sgf_move(
            input,
            parent.id,
            PlayerColor::White,
            MoveVertex::Point(PointDto { x: 3, y: 3 }),
        )
        .unwrap();

        assert_eq!(
            result.sgf_text,
            "(;SZ[5];B[aa](;W[bb]C[main])(;W[cc]C[branch])(;W[dd]))"
        );
        let reparsed_tree = to_sgf_tree_dto(&parse_sgf(&result.sgf_text).unwrap())
            .unwrap()
            .unwrap();
        let updated_parent = reparsed_tree
            .nodes
            .iter()
            .find(|node| node.id == parent.id)
            .unwrap();
        assert_eq!(updated_parent.child_ids.len(), 3);
        assert!(result.sgf_text.contains("(;W[bb]C[main])"));
        assert!(result.sgf_text.contains("(;W[cc]C[branch])"));

        let new_node = reparsed_tree
            .nodes
            .iter()
            .find(|node| node.id == result.new_node_id)
            .unwrap();
        assert_eq!(new_node.variation_index, 2);
        assert!(!new_node.is_mainline);
    }

    #[test]
    fn appends_pass_move_and_replays_at_new_node() {
        let input = "(;SZ[5];B[aa])";
        let tree = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;

        let result = append_sgf_move(input, parent_id, PlayerColor::White, MoveVertex::Pass).unwrap();

        assert_eq!(result.sgf_text, "(;SZ[5];B[aa];W[])");
        let position = replay_sgf_position_at_node(&result.sgf_text, result.new_node_id).unwrap();
        assert_eq!(position.move_number, 2);
        assert!(matches!(
            position.last_move.as_ref().unwrap().vertex,
            MoveVertex::Pass
        ));
        assert!(position.errors.is_empty());
    }

    #[test]
    fn append_rejects_occupied_point_and_leaves_input_replayable() {
        let input = "(;SZ[5];B[aa])";
        let tree = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;

        let error = append_sgf_move(
            input,
            parent_id,
            PlayerColor::White,
            MoveVertex::Point(PointDto { x: 0, y: 0 }),
        )
        .unwrap_err();

        assert!(matches!(error, SgfError::IllegalMove(_)));
        assert_eq!(serialize_sgf_document(&parse_sgf(input).unwrap()).unwrap(), input);
    }

    #[test]
    fn append_rejects_suicide_against_parent_branch_position() {
        let input = "(;SZ[5];W[ab];W[ba];W[cb];W[bc])";
        let tree = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(4))
            .unwrap()
            .id;

        let error = append_sgf_move(
            input,
            parent_id,
            PlayerColor::Black,
            MoveVertex::Point(PointDto { x: 1, y: 1 }),
        )
        .unwrap_err();

        assert!(matches!(error, SgfError::IllegalMove(message) if message.contains("suicide")));
        assert_eq!(serialize_sgf_document(&parse_sgf(input).unwrap()).unwrap(), input);
    }

    #[test]
    fn updates_comment_with_bracket_backslash_and_newline_roundtrip() {
        let input = "(;SZ[5];B[aa])";
        let doc = parse_sgf(input).unwrap();
        let tree = to_sgf_tree_dto(&doc).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;
        let comment = "close ] slash \\ line\nnext";

        let updated = update_sgf_node_comment(input, node_id, Some(comment)).unwrap();
        assert!(updated.contains("C[close \\] slash \\\\ line\nnext]"));

        let reparsed_tree = to_sgf_tree_dto(&parse_sgf(&updated).unwrap()).unwrap().unwrap();
        let node = reparsed_tree
            .nodes
            .iter()
            .find(|node| node.id == node_id)
            .unwrap();
        assert_eq!(node.comment.as_deref(), Some(comment));
    }

    #[test]
    fn clearing_comment_removes_c_property() {
        let input = "(;SZ[5];B[aa]C[old];W[bb]C[keep])";
        let doc = parse_sgf(input).unwrap();
        let tree = to_sgf_tree_dto(&doc).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;

        let updated = update_sgf_node_comment(input, node_id, Some("")).unwrap();
        assert_eq!(updated, "(;SZ[5];B[aa];W[bb]C[keep])");

        let cleared_again = update_sgf_node_comment(input, node_id, None).unwrap();
        assert_eq!(cleared_again, updated);
    }

    #[test]
    fn deletes_leaf_mainline_node_roundtrip() {
        let input = "(;SZ[5]C[root]XY[keep];B[aa]C[first];W[bb]C[leaf]ZZ[unknown])";
        let tree = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();
        let leaf_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("leaf"))
            .unwrap()
            .id;
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("first"))
            .unwrap()
            .id;

        let result = delete_sgf_node(input, leaf_id).unwrap();

        assert_eq!(result.parent_node_id, parent_id);
        assert_eq!(result.sgf_text, "(;SZ[5]C[root]XY[keep];B[aa]C[first])");
        let reparsed = parse_sgf(&result.sgf_text).unwrap();
        assert_eq!(serialize_sgf_document(&reparsed).unwrap(), result.sgf_text);
        assert_eq!(replay_sgf_positions(&result.sgf_text).unwrap().len(), 2);
        let reparsed_tree = to_sgf_tree_dto(&reparsed).unwrap().unwrap();
        assert!(reparsed_tree.nodes.iter().any(|node| node.id == parent_id));
        assert!(!reparsed_tree
            .nodes
            .iter()
            .any(|node| node.comment.as_deref() == Some("leaf")));
    }

    #[test]
    fn deleting_node_with_subtree_removes_descendants() {
        let input = "(;SZ[5];B[aa]C[parent];W[bb]C[target];B[cc]C[descendant])";
        let tree = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();
        let target_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("target"))
            .unwrap()
            .id;
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("parent"))
            .unwrap()
            .id;

        let result = delete_sgf_node(input, target_id).unwrap();

        assert_eq!(result.parent_node_id, parent_id);
        assert_eq!(result.sgf_text, "(;SZ[5];B[aa]C[parent])");
        let reparsed = parse_sgf(&result.sgf_text).unwrap();
        let reparsed_tree = to_sgf_tree_dto(&reparsed).unwrap().unwrap();
        let parent = reparsed_tree
            .nodes
            .iter()
            .find(|node| node.id == parent_id)
            .unwrap();
        assert!(parent.child_ids.is_empty());
        assert!(!reparsed_tree
            .nodes
            .iter()
            .any(|node| node.comment.as_deref() == Some("target")));
        assert!(!reparsed_tree
            .nodes
            .iter()
            .any(|node| node.comment.as_deref() == Some("descendant")));
        assert!(replay_sgf_position_at_node(&result.sgf_text, parent_id)
            .unwrap()
            .errors
            .is_empty());
    }

    #[test]
    fn deleting_variation_sibling_keeps_other_siblings_and_parent() {
        let input = concat!(
            "(;SZ[5]C[root];B[aa]C[parent]",
            "(;W[bb]C[main]XY[one])",
            "(;W[cc]C[target];B[dd]C[target child])",
            "(;W[dc]C[keep]ZZ[unknown]))"
        );
        let tree = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();
        let target_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("target"))
            .unwrap()
            .id;
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("parent"))
            .unwrap()
            .id;

        let result = delete_sgf_node(input, target_id).unwrap();

        assert_eq!(result.parent_node_id, parent_id);
        assert_eq!(
            result.sgf_text,
            "(;SZ[5]C[root];B[aa]C[parent](;W[bb]C[main]XY[one])(;W[dc]C[keep]ZZ[unknown]))"
        );
        let reparsed = parse_sgf(&result.sgf_text).unwrap();
        let reparsed_tree = to_sgf_tree_dto(&reparsed).unwrap().unwrap();
        let parent = reparsed_tree
            .nodes
            .iter()
            .find(|node| node.id == parent_id)
            .unwrap();
        assert_eq!(parent.child_ids.len(), 2);
        assert!(reparsed_tree
            .nodes
            .iter()
            .any(|node| node.comment.as_deref() == Some("main")));
        assert!(reparsed_tree
            .nodes
            .iter()
            .any(|node| node.comment.as_deref() == Some("keep")
                && node.properties.iter().any(|property| property.key == "ZZ")));
        assert!(!reparsed_tree
            .nodes
            .iter()
            .any(|node| node.comment.as_deref() == Some("target")));
        assert!(!reparsed_tree
            .nodes
            .iter()
            .any(|node| node.comment.as_deref() == Some("target child")));
        assert!(replay_sgf_positions(&result.sgf_text)
            .unwrap()
            .iter()
            .all(|position| position.errors.is_empty()));
    }

    #[test]
    fn deleting_root_fails() {
        let input = "(;SZ[5]C[root];B[aa])";
        let tree = to_sgf_tree_dto(&parse_sgf(input).unwrap()).unwrap().unwrap();

        let error = delete_sgf_node(input, tree.root_id).unwrap_err();

        assert!(matches!(error, SgfError::CannotDeleteRoot));
        assert_eq!(serialize_sgf_document(&parse_sgf(input).unwrap()).unwrap(), input);
    }

    #[test]
    fn replay_sgf_position_at_node_uses_branch_path_not_mainline_move_number() {
        let input = "(;SZ[5]AB[aa]PL[W];B[bb](;W[bc]C[main])(;W[cb]C[branch]))";
        let doc = parse_sgf(input).unwrap();
        let tree = to_sgf_tree_dto(&doc).unwrap().unwrap();
        let mainline_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("main"))
            .unwrap()
            .id;
        let branch_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch"))
            .unwrap()
            .id;

        let mainline = replay_sgf_position_at_node(input, mainline_id).unwrap();
        let branch = replay_sgf_position_at_node(input, branch_id).unwrap();

        assert_eq!(mainline.move_number, 2);
        assert_eq!(branch.move_number, 2);
        assert!(has_stone(&mainline, 1, 2, PlayerColor::White));
        assert!(!has_stone(&mainline, 2, 1, PlayerColor::White));
        assert!(has_stone(&branch, 2, 1, PlayerColor::White));
        assert!(!has_stone(&branch, 1, 2, PlayerColor::White));
        assert!(has_stone(&branch, 0, 0, PlayerColor::Black));
        assert!(branch.errors.is_empty());
    }

    #[test]
    fn yike_normalizer_keeps_first_variation_and_ignores_property_text() {
        let sgf = "(;GM[1]SZ[19]C[text (not a tree) \\] ok];B[aa](;W[bb];B[cc])(;W[dd];B[ee]);W[ff])";

        assert_eq!(
            normalize_yike_sgf_mainline(sgf),
            "(;GM[1]SZ[19]C[text (not a tree) \\] ok];B[aa];W[bb];B[cc];W[ff])"
        );
    }

    #[test]
    fn fox_sanitizer_removes_backslashes_only_outside_values() {
        let sgf = r#"\(;C[keep \\ and \] bracket] \;B[aa]\)"#;

        assert_eq!(sanitize_fox_sgf(sgf), r#"(;C[keep \\ and \] bracket] ;B[aa])"#);
    }

    #[test]
    fn fox_normalizer_promotes_setup_and_keeps_single_replayable_mainline() {
        let input = r#"\(;SZ[5]PB[Black]PW[White]RE[B+R]C[root (ok) \] text];AB[aa][bb]AW[cc]AE[bb]PL[W];W[dd](;B[]C[first])(;B[ee]C[sibling])\)"#;

        let normalized = normalize_fox_sgf(input);

        assert_eq!(
            normalized,
            "(;GM[1]FF[4]CA[UTF-8]SZ[5]PB[Black]PW[White]RE[B+R]PL[W]C[root (ok) \\] text]AB[aa][bb]AW[cc]AE[bb];W[dd];B[])"
        );
        assert!(!normalized.contains("sibling"));

        let doc = parse_sgf(&normalized).unwrap();
        assert_eq!(doc.board_size, 5);
        assert_eq!(doc.black_name.as_deref(), Some("Black"));
        assert_eq!(doc.white_name.as_deref(), Some("White"));
        assert_eq!(doc.result.as_deref(), Some("B+R"));
        assert_eq!(
            property_values(doc.root.as_ref().unwrap(), "C").unwrap(),
            &vec!["root (ok) ] text".to_string()]
        );
        assert_eq!(doc.moves.len(), 2);
        assert_eq!(doc.moves[0].color, PlayerColor::White);
        assert!(matches!(doc.moves[1].vertex, MoveVertex::Pass));

        let serialized = serialize_sgf_document(&doc).unwrap();
        let reparsed = parse_sgf(&serialized).unwrap();
        assert_eq!(reparsed.root, doc.root);
        assert_eq!(reparsed.moves, doc.moves);

        let positions = replay_sgf_positions(&normalized).unwrap();
        assert_eq!(positions.len(), 3);
        assert_eq!(positions[0].to_play, PlayerColor::White);
        assert!(has_stone(&positions[0], 0, 0, PlayerColor::Black));
        assert!(has_stone(&positions[0], 2, 2, PlayerColor::White));
        assert!(!positions[0]
            .stones
            .iter()
            .any(|stone| stone.x == 1 && stone.y == 1));
        assert!(matches!(
            positions[2].last_move.as_ref().unwrap().vertex,
            MoveVertex::Pass
        ));
        assert!(positions.iter().all(|position| position.errors.is_empty()));
    }

    #[test]
    fn fox_normalizer_recovers_windowed_mainline_chunks() {
        let mut input = String::from("(;SZ[19]");
        for start in (0..80).step_by(4).take(20) {
            input.push('(');
            for index in start..start + 8 {
                let color = if index % 2 == 0 { "B" } else { "W" };
                input.push(';');
                input.push_str(color);
                input.push('[');
                input.push_str(&test_sgf_coord(index));
                input.push(']');
            }
            input.push(')');
        }
        input.push(')');

        let normalized = normalize_fox_sgf(&input);
        let doc = parse_sgf(&normalized).unwrap();

        assert_eq!(normalized.matches('(').count(), 1);
        assert_eq!(doc.moves.len(), 84);
        assert_eq!(doc.moves[0].vertex, MoveVertex::Point(PointDto { x: 0, y: 0 }));
        assert_eq!(doc.moves[83].vertex, MoveVertex::Point(PointDto { x: 7, y: 4 }));
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
    fn roundtrips_ff4_common_properties_unknowns_markup_timing_and_branches() {
        let input = include_str!("../../../tests/golden/sgf_ff4_compat.sgf").trim();
        let doc = parse_sgf(input).unwrap();

        assert_eq!(doc.board_size, 9);
        assert_eq!(doc.komi, 6.5);
        assert_eq!(doc.handicap, Some(2));
        assert_eq!(doc.black_name.as_deref(), Some("A]lice"));
        assert_eq!(doc.white_name.as_deref(), Some("Bob\\Lee"));
        assert_eq!(doc.result.as_deref(), Some("W+2.5"));
        assert_eq!(doc.moves.len(), 2);
        assert_eq!(doc.moves[0].color, PlayerColor::White);
        assert_eq!(doc.moves[0].vertex, MoveVertex::Point(PointDto { x: 3, y: 3 }));
        assert_eq!(doc.moves[1].color, PlayerColor::Black);
        assert_eq!(doc.moves[1].vertex, MoveVertex::Point(PointDto { x: 4, y: 4 }));

        let root = doc.root.as_ref().unwrap();
        let root_keys: Vec<&str> = root
            .properties
            .iter()
            .map(|property| property.key.as_str())
            .collect();
        assert_eq!(
            root_keys,
            vec![
                "FF", "GM", "SZ", "KM", "HA", "PB", "PW", "BR", "WR", "RE", "DT", "EV", "RO", "PC", "RU",
                "OT", "TM", "C", "XY", "AB", "AW", "AE", "PL", "TR", "SQ", "CR", "MA", "LB", "AR", "LN",
                "SL",
            ]
        );
        assert_eq!(property_values(root, "BR").unwrap(), &vec!["1d".to_string()]);
        assert_eq!(property_values(root, "WR").unwrap(), &vec!["2k".to_string()]);
        assert_eq!(
            property_values(root, "DT").unwrap(),
            &vec!["2026-04-30".to_string()]
        );
        assert_eq!(
            property_values(root, "EV").unwrap(),
            &vec!["Test Cup".to_string()]
        );
        assert_eq!(property_values(root, "RO").unwrap(), &vec!["R1".to_string()]);
        assert_eq!(
            property_values(root, "PC").unwrap(),
            &vec!["Shanghai".to_string()]
        );
        assert_eq!(property_values(root, "RU").unwrap(), &vec!["Chinese".to_string()]);
        assert_eq!(
            property_values(root, "OT").unwrap(),
            &vec!["byo-yomi".to_string()]
        );
        assert_eq!(property_values(root, "TM").unwrap(), &vec!["3600".to_string()]);
        assert_eq!(
            property_values(root, "C").unwrap(),
            &vec!["root ] comment\\done".to_string()]
        );
        assert_eq!(
            property_values(root, "XY").unwrap(),
            &vec![
                "alpha".to_string(),
                "beta]two".to_string(),
                "slash\\end".to_string(),
            ]
        );
        assert_eq!(
            property_values(root, "TR").unwrap(),
            &vec!["aa".to_string(), "bb".to_string()]
        );
        assert_eq!(
            property_values(root, "LB").unwrap(),
            &vec!["aa:A".to_string(), "bb:B]2".to_string()]
        );
        assert_eq!(property_values(root, "AR").unwrap(), &vec!["aa:bb".to_string()]);
        assert_eq!(property_values(root, "LN").unwrap(), &vec!["cc:dd".to_string()]);
        assert_eq!(property_values(root, "SL").unwrap(), &vec!["ee".to_string()]);

        let move_node = &root.children[0];
        assert_eq!(
            property_values(move_node, "N").unwrap(),
            &vec!["move 1".to_string()]
        );
        assert_eq!(
            property_values(move_node, "C").unwrap(),
            &vec!["hello]world".to_string()]
        );
        assert_eq!(property_values(move_node, "GB").unwrap(), &vec!["1".to_string()]);
        assert_eq!(property_values(move_node, "GW").unwrap(), &vec!["2".to_string()]);
        assert_eq!(property_values(move_node, "DM").unwrap(), &vec!["1".to_string()]);
        assert_eq!(property_values(move_node, "HO").unwrap(), &vec!["1".to_string()]);
        assert_eq!(property_values(move_node, "BM").unwrap(), &vec!["2".to_string()]);
        assert_eq!(property_values(move_node, "TE").unwrap(), &vec!["1".to_string()]);
        assert_eq!(property_values(move_node, "IT").unwrap(), &vec!["1".to_string()]);
        assert_eq!(property_values(move_node, "DO").unwrap(), &vec!["1".to_string()]);
        assert_eq!(
            property_values(move_node, "BL").unwrap(),
            &vec!["3550.5".to_string()]
        );
        assert_eq!(
            property_values(move_node, "WL").unwrap(),
            &vec!["3600".to_string()]
        );
        assert_eq!(property_values(move_node, "OB").unwrap(), &vec!["5".to_string()]);
        assert_eq!(property_values(move_node, "OW").unwrap(), &vec!["4".to_string()]);
        assert_eq!(move_node.children.len(), 2);
        assert_eq!(
            property_values(&move_node.children[1], "ZZ").unwrap(),
            &vec!["unknown".to_string(), "multi".to_string()]
        );

        let serialized = serialize_sgf_document(&doc).unwrap();
        assert_eq!(serialized, input);
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

    #[test]
    fn replay_ignores_ff4_annotations_markup_timing_and_unknown_properties() {
        let input = include_str!("../../../tests/golden/sgf_ff4_compat.sgf");
        let positions = replay_sgf_positions(input).unwrap();

        assert_eq!(positions.len(), 3);
        let initial = &positions[0];
        assert_eq!(initial.to_play, PlayerColor::White);
        assert!(has_stone(initial, 0, 0, PlayerColor::Black));
        assert!(has_stone(initial, 2, 2, PlayerColor::White));
        assert!(!initial.stones.iter().any(|stone| stone.x == 1 && stone.y == 1));

        let first_move = &positions[1];
        assert_eq!(first_move.last_move.as_ref().unwrap().color, PlayerColor::White);
        assert!(has_stone(first_move, 3, 3, PlayerColor::White));

        let branch_move = &positions[2];
        assert_eq!(branch_move.last_move.as_ref().unwrap().color, PlayerColor::Black);
        assert!(has_stone(branch_move, 4, 4, PlayerColor::Black));
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

    fn test_sgf_coord(index: usize) -> String {
        let x = (index % 19) as u8;
        let y = (index / 19) as u8;
        format!("{}{}", char::from(b'a' + x), char::from(b'a' + y))
    }
}
