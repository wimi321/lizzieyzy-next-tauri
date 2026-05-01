use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashSet, VecDeque};
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Color {
    Black,
    White,
}
impl Color {
    pub fn opponent(self) -> Self {
        match self {
            Color::Black => Color::White,
            Color::White => Color::Black,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Point {
    pub x: u8,
    pub y: u8,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Vertex {
    Point(Point),
    Pass,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoveOutcome {
    pub played: Vertex,
    pub captured: Vec<Point>,
    pub ko: Option<Point>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Board {
    size: u8,
    stones: Vec<Option<Color>>,
    ko: Option<Point>,
    consecutive_passes: u8,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum RuleError {
    #[error("board size must be between 2 and 25")]
    InvalidBoardSize,
    #[error("point is outside board")]
    OutOfBounds,
    #[error("point is already occupied")]
    Occupied,
    #[error("move violates simple ko")]
    Ko,
    #[error("suicide move is not allowed")]
    Suicide,
}

impl Board {
    pub fn new(size: u8) -> Result<Self, RuleError> {
        if !(2..=25).contains(&size) {
            return Err(RuleError::InvalidBoardSize);
        }
        Ok(Self {
            size,
            stones: vec![None; size as usize * size as usize],
            ko: None,
            consecutive_passes: 0,
        })
    }
    pub fn size(&self) -> u8 {
        self.size
    }
    pub fn ko(&self) -> Option<Point> {
        self.ko
    }
    pub fn get(&self, point: Point) -> Result<Option<Color>, RuleError> {
        Ok(self.stones[self.index(point)?])
    }
    pub fn stones_snapshot(&self) -> Vec<Option<Color>> {
        self.stones.clone()
    }

    pub fn set_stone(&mut self, point: Point, color: Option<Color>) -> Result<(), RuleError> {
        let idx = self.index(point)?;
        self.stones[idx] = color;
        self.ko = None;
        self.consecutive_passes = 0;
        Ok(())
    }

    pub fn play(&mut self, color: Color, vertex: Vertex) -> Result<MoveOutcome, RuleError> {
        match vertex {
            Vertex::Pass => {
                self.ko = None;
                self.consecutive_passes = self.consecutive_passes.saturating_add(1);
                Ok(MoveOutcome {
                    played: vertex,
                    captured: vec![],
                    ko: None,
                })
            }
            Vertex::Point(point) => self.play_point(color, point),
        }
    }

    fn play_point(&mut self, color: Color, point: Point) -> Result<MoveOutcome, RuleError> {
        let idx = self.index(point)?;
        if self.stones[idx].is_some() {
            return Err(RuleError::Occupied);
        }
        if self.ko == Some(point) {
            return Err(RuleError::Ko);
        }
        let previous = self.clone();
        self.stones[idx] = Some(color);
        self.consecutive_passes = 0;
        let mut captured = Vec::new();
        for neighbor in self.neighbors(point) {
            if self.get(neighbor)? == Some(color.opponent()) {
                let group = self.group_at(neighbor)?;
                if self.liberty_count(&group) == 0 {
                    for stone in &group {
                        let stone_idx = self.index(*stone)?;
                        self.stones[stone_idx] = None;
                    }
                    captured.extend(group);
                }
            }
        }
        let own_group = self.group_at(point)?;
        if self.liberty_count(&own_group) == 0 {
            *self = previous;
            return Err(RuleError::Suicide);
        }
        self.ko = if captured.len() == 1 && own_group.len() == 1 {
            captured.first().copied()
        } else {
            None
        };
        Ok(MoveOutcome {
            played: Vertex::Point(point),
            captured,
            ko: self.ko,
        })
    }

    fn index(&self, point: Point) -> Result<usize, RuleError> {
        if point.x >= self.size || point.y >= self.size {
            return Err(RuleError::OutOfBounds);
        }
        Ok(point.y as usize * self.size as usize + point.x as usize)
    }
    fn neighbors(&self, point: Point) -> Vec<Point> {
        let mut result = Vec::with_capacity(4);
        if point.x > 0 {
            result.push(Point {
                x: point.x - 1,
                y: point.y,
            });
        }
        if point.y > 0 {
            result.push(Point {
                x: point.x,
                y: point.y - 1,
            });
        }
        if point.x + 1 < self.size {
            result.push(Point {
                x: point.x + 1,
                y: point.y,
            });
        }
        if point.y + 1 < self.size {
            result.push(Point {
                x: point.x,
                y: point.y + 1,
            });
        }
        result
    }
    fn group_at(&self, start: Point) -> Result<Vec<Point>, RuleError> {
        let color = self.get(start)?.ok_or(RuleError::OutOfBounds)?;
        let mut seen = HashSet::new();
        let mut queue = VecDeque::new();
        seen.insert(start);
        queue.push_back(start);
        while let Some(point) = queue.pop_front() {
            for n in self.neighbors(point) {
                if !seen.contains(&n) && self.get(n)? == Some(color) {
                    seen.insert(n);
                    queue.push_back(n);
                }
            }
        }
        Ok(seen.into_iter().collect())
    }
    fn liberty_count(&self, group: &[Point]) -> usize {
        let mut liberties = HashSet::new();
        for point in group {
            for n in self.neighbors(*point) {
                if self.get(n).ok().flatten().is_none() {
                    liberties.insert(n);
                }
            }
        }
        liberties.len()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadBoardMarker {
    pub point: Point,
    pub color: Color,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReadBoardProviderKind {
    Generic,
    FoxLive,
    FoxRecord,
}

impl ReadBoardProviderKind {
    pub fn is_fox(self) -> bool {
        matches!(self, Self::FoxLive | Self::FoxRecord)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadBoardProvider {
    pub kind: ReadBoardProviderKind,
    pub source: Option<String>,
}

impl Default for ReadBoardProvider {
    fn default() -> Self {
        Self {
            kind: ReadBoardProviderKind::Generic,
            source: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadBoardSnapshot {
    pub board_size: u8,
    pub stones: Vec<Option<Color>>,
    pub last_move: Option<ReadBoardMarker>,
    pub remote_move_number: Option<u32>,
    pub provider: ReadBoardProvider,
}

impl ReadBoardSnapshot {
    pub fn from_legacy_codes(
        board_size: u8,
        codes: impl IntoIterator<Item = u8>,
        remote_move_number: Option<u32>,
        provider: ReadBoardProvider,
    ) -> Result<Self, ReadBoardSyncError> {
        let mut stones = Vec::new();
        let mut last_move = None;
        for (index, code) in codes.into_iter().enumerate() {
            let x = index % board_size as usize;
            let y = index / board_size as usize;
            let point = Point {
                x: x as u8,
                y: y as u8,
            };
            let stone = match code {
                0 => None,
                1 => Some(Color::Black),
                2 => Some(Color::White),
                3 => {
                    last_move = Some(ReadBoardMarker {
                        point,
                        color: Color::Black,
                    });
                    Some(Color::Black)
                }
                4 => {
                    last_move = Some(ReadBoardMarker {
                        point,
                        color: Color::White,
                    });
                    Some(Color::White)
                }
                _ => return Err(ReadBoardSyncError::InvalidSnapshotCode(code)),
            };
            stones.push(stone);
        }
        let snapshot = Self {
            board_size,
            stones,
            last_move,
            remote_move_number,
            provider,
        };
        snapshot.validate()?;
        Ok(snapshot)
    }

    pub fn occupied_count(&self) -> u32 {
        self.stones.iter().filter(|stone| stone.is_some()).count() as u32
    }

    pub fn validate(&self) -> Result<(), ReadBoardSyncError> {
        validate_board_shape(self.board_size, self.stones.len())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct ReadBoardSnapshotMetadata {
    pub properties: BTreeMap<String, Vec<String>>,
    pub comment: Option<String>,
    pub extra_stones: Vec<ReadBoardExtraStone>,
    pub has_removed_stone: bool,
}

impl ReadBoardSnapshotMetadata {
    pub fn is_empty(&self) -> bool {
        self.properties.is_empty()
            && self.comment.is_none()
            && self.extra_stones.is_empty()
            && !self.has_removed_stone
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadBoardExtraStone {
    pub point: Point,
    pub color: Color,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadBoardLocalPosition {
    pub stones: Vec<Option<Color>>,
    pub last_move: Option<ReadBoardMarker>,
    pub move_number: u32,
    pub black_to_play: bool,
    pub metadata: ReadBoardSnapshotMetadata,
}

impl ReadBoardLocalPosition {
    pub fn new(
        stones: Vec<Option<Color>>,
        last_move: Option<ReadBoardMarker>,
        move_number: u32,
        black_to_play: bool,
    ) -> Self {
        Self {
            stones,
            last_move,
            move_number,
            black_to_play,
            metadata: ReadBoardSnapshotMetadata::default(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadBoardLocalContext {
    pub board_size: u8,
    pub positions: Vec<ReadBoardLocalPosition>,
    pub current_index: usize,
    pub main_end_index: usize,
}

impl ReadBoardLocalContext {
    pub fn current(&self) -> Option<&ReadBoardLocalPosition> {
        self.positions.get(self.current_index)
    }

    pub fn validate(&self) -> Result<(), ReadBoardSyncError> {
        validate_board_shape(
            self.board_size,
            self.board_size as usize * self.board_size as usize,
        )?;
        if self.positions.is_empty() {
            return Ok(());
        }
        if self.current_index >= self.positions.len() {
            return Err(ReadBoardSyncError::InvalidLocalIndex {
                index: self.current_index,
                len: self.positions.len(),
            });
        }
        if self.main_end_index >= self.positions.len() {
            return Err(ReadBoardSyncError::InvalidLocalIndex {
                index: self.main_end_index,
                len: self.positions.len(),
            });
        }
        for position in &self.positions {
            validate_board_shape(self.board_size, position.stones.len())?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadBoardSyncInput {
    pub first_sync: bool,
    pub snapshot: ReadBoardSnapshot,
    pub local: ReadBoardLocalContext,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReadBoardRebuildReason {
    FirstSync,
    EmptyRollback,
    NoReusableHistory,
    MoveNumberJump,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ReadBoardSyncDecision {
    RebuildSnapshot {
        reason: ReadBoardRebuildReason,
        move_number: u32,
        black_to_play: bool,
        preserved_metadata: ReadBoardSnapshotMetadata,
    },
    ReuseAncestor {
        target_index: usize,
        main_end_index: usize,
    },
    NavigateExisting {
        target_index: usize,
    },
    AppendMove {
        point: Point,
        color: Color,
        move_number: u32,
        black_to_play: bool,
    },
    SteadyState {
        target_index: usize,
    },
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ReadBoardSyncError {
    #[error("board size must be between 2 and 25")]
    InvalidBoardSize,
    #[error("snapshot length {actual} does not match board area {expected}")]
    InvalidSnapshotLength { expected: usize, actual: usize },
    #[error("legacy readboard snapshot code {0} is invalid")]
    InvalidSnapshotCode(u8),
    #[error("local position index {index} is outside {len} positions")]
    InvalidLocalIndex { index: usize, len: usize },
    #[error("snapshot board size does not match local board size")]
    BoardSizeMismatch,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadBoardRemoteContext {
    pub provider: ReadBoardProvider,
    pub remote_move_number: Option<u32>,
    pub record_current_move: Option<u32>,
    pub record_total_move: Option<u32>,
    pub record_at_end: bool,
}

impl ReadBoardRemoteContext {
    pub fn fox_live(
        room_token: impl Into<String>,
        live_title_move: Option<u32>,
        fox_move_number: Option<u32>,
    ) -> Self {
        Self {
            provider: ReadBoardProvider {
                kind: ReadBoardProviderKind::FoxLive,
                source: Some(room_token.into()),
            },
            remote_move_number: fox_move_number.or(live_title_move),
            record_current_move: live_title_move,
            record_total_move: None,
            record_at_end: false,
        }
    }

    pub fn fox_record(
        fingerprint: impl Into<String>,
        current_move: Option<u32>,
        total_move: Option<u32>,
        at_end: bool,
    ) -> Self {
        Self {
            provider: ReadBoardProvider {
                kind: ReadBoardProviderKind::FoxRecord,
                source: Some(fingerprint.into()),
            },
            remote_move_number: current_move.or_else(|| at_end.then_some(total_move).flatten()),
            record_current_move: current_move,
            record_total_move: total_move,
            record_at_end: at_end,
        }
    }

    pub fn recovery_move_number(&self) -> Option<u32> {
        self.remote_move_number
            .or_else(|| self.record_at_end.then_some(self.record_total_move).flatten())
    }

    pub fn apply_fox_move_number_text(&mut self, raw: &str) -> Result<(), ReadBoardMetadataError> {
        let move_number = parse_remote_move_number(raw)?;
        self.remote_move_number = Some(move_number);
        Ok(())
    }
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ReadBoardMetadataError {
    #[error("remote move number `{0}` is invalid")]
    InvalidMoveNumber(String),
}

pub fn decide_readboard_sync(
    input: &ReadBoardSyncInput,
) -> Result<ReadBoardSyncDecision, ReadBoardSyncError> {
    input.snapshot.validate()?;
    input.local.validate()?;
    if input.snapshot.board_size != input.local.board_size {
        return Err(ReadBoardSyncError::BoardSizeMismatch);
    }

    let snapshot_move_number = infer_snapshot_move_number(&input.snapshot);
    let snapshot_black_to_play = infer_snapshot_black_to_play(&input.snapshot);

    if input.first_sync || input.local.positions.is_empty() {
        return Ok(rebuild_decision(
            input,
            ReadBoardRebuildReason::FirstSync,
            snapshot_move_number,
            snapshot_black_to_play,
        ));
    }

    if let Some(target_index) = find_existing_position(input) {
        return Ok(navigation_decision(input, target_index));
    }

    if let Some(current) = input.local.current() {
        if input.snapshot.stones.iter().all(Option::is_none) && current.stones.iter().any(Option::is_some) {
            return Ok(rebuild_decision(
                input,
                ReadBoardRebuildReason::EmptyRollback,
                snapshot_move_number,
                true,
            ));
        }

        if let Some((point, color)) =
            single_added_stone(input.snapshot.board_size, &current.stones, &input.snapshot.stones)
        {
            let next_move_number = current.move_number.saturating_add(1);
            if input
                .snapshot
                .remote_move_number
                .is_none_or(|remote| remote == next_move_number)
            {
                return Ok(ReadBoardSyncDecision::AppendMove {
                    point,
                    color,
                    move_number: input.snapshot.remote_move_number.unwrap_or(next_move_number),
                    black_to_play: color == Color::White,
                });
            }
        }
    }

    let reason = if input.snapshot.remote_move_number.is_some() {
        ReadBoardRebuildReason::MoveNumberJump
    } else {
        ReadBoardRebuildReason::NoReusableHistory
    };
    Ok(rebuild_decision(
        input,
        reason,
        snapshot_move_number,
        snapshot_black_to_play,
    ))
}

fn validate_board_shape(board_size: u8, stones_len: usize) -> Result<(), ReadBoardSyncError> {
    if !(2..=25).contains(&board_size) {
        return Err(ReadBoardSyncError::InvalidBoardSize);
    }
    let expected = board_size as usize * board_size as usize;
    if stones_len != expected {
        return Err(ReadBoardSyncError::InvalidSnapshotLength {
            expected,
            actual: stones_len,
        });
    }
    Ok(())
}

fn infer_snapshot_move_number(snapshot: &ReadBoardSnapshot) -> u32 {
    snapshot
        .remote_move_number
        .unwrap_or_else(|| snapshot.occupied_count())
}

fn infer_snapshot_black_to_play(snapshot: &ReadBoardSnapshot) -> bool {
    if let Some(marker) = snapshot.last_move {
        return marker.color == Color::White;
    }
    if snapshot.provider.kind.is_fox() {
        if let Some(move_number) = snapshot.remote_move_number {
            return move_number & 1 == 0;
        }
    }
    snapshot.occupied_count() & 1 == 0
}

fn find_existing_position(input: &ReadBoardSyncInput) -> Option<usize> {
    let remote_move_number = input.snapshot.remote_move_number;
    let marker = input.snapshot.last_move;
    let is_fox = input.snapshot.provider.kind.is_fox();

    if let Some(move_number) = remote_move_number {
        if let Some((index, _)) = input.local.positions.iter().enumerate().find(|(_, position)| {
            position.move_number == move_number
                && position.stones == input.snapshot.stones
                && (is_fox || marker.is_none() || position.last_move == marker)
        }) {
            return Some(index);
        }
        if is_fox {
            return None;
        }
    }

    input
        .local
        .positions
        .iter()
        .enumerate()
        .find(|(_, position)| {
            position.stones == input.snapshot.stones
                && (marker.is_none() || position.last_move == marker || is_fox)
        })
        .map(|(index, _)| index)
}

fn navigation_decision(input: &ReadBoardSyncInput, target_index: usize) -> ReadBoardSyncDecision {
    if target_index == input.local.current_index {
        ReadBoardSyncDecision::SteadyState { target_index }
    } else if target_index < input.local.current_index {
        ReadBoardSyncDecision::ReuseAncestor {
            target_index,
            main_end_index: input.local.main_end_index,
        }
    } else {
        ReadBoardSyncDecision::NavigateExisting { target_index }
    }
}

fn single_added_stone(
    board_size: u8,
    current: &[Option<Color>],
    snapshot: &[Option<Color>],
) -> Option<(Point, Color)> {
    if current.len() != snapshot.len() {
        return None;
    }
    let mut added = None;
    for (index, (before, after)) in current.iter().zip(snapshot).enumerate() {
        match (before, after) {
            (None, Some(color)) if added.is_none() => {
                added = Some((
                    Point {
                        x: (index % board_size as usize) as u8,
                        y: (index / board_size as usize) as u8,
                    },
                    *color,
                ));
            }
            (None, Some(_)) => return None,
            (before, after) if before == after => {}
            _ => return None,
        }
    }
    added
}

fn rebuild_decision(
    input: &ReadBoardSyncInput,
    reason: ReadBoardRebuildReason,
    move_number: u32,
    black_to_play: bool,
) -> ReadBoardSyncDecision {
    ReadBoardSyncDecision::RebuildSnapshot {
        reason,
        move_number,
        black_to_play,
        preserved_metadata: metadata_to_preserve(&input.local),
    }
}

fn metadata_to_preserve(local: &ReadBoardLocalContext) -> ReadBoardSnapshotMetadata {
    if local.positions.is_empty() {
        return ReadBoardSnapshotMetadata::default();
    }
    let start = local.current_index.min(local.positions.len() - 1);
    local.positions[..=start]
        .iter()
        .rev()
        .find_map(|position| (!position.metadata.is_empty()).then(|| position.metadata.clone()))
        .unwrap_or_default()
}

fn parse_remote_move_number(raw: &str) -> Result<u32, ReadBoardMetadataError> {
    raw.trim()
        .parse()
        .map_err(|_| ReadBoardMetadataError::InvalidMoveNumber(raw.trim().to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn p(x: u8, y: u8) -> Vertex {
        Vertex::Point(Point { x, y })
    }
    #[test]
    fn captures_single_stone() {
        let mut b = Board::new(5).unwrap();
        b.play(Color::Black, p(1, 1)).unwrap();
        b.play(Color::White, p(0, 1)).unwrap();
        b.play(Color::White, p(1, 0)).unwrap();
        b.play(Color::White, p(2, 1)).unwrap();
        let out = b.play(Color::White, p(1, 2)).unwrap();
        assert_eq!(out.captured, vec![Point { x: 1, y: 1 }]);
    }
    #[test]
    fn rejects_suicide() {
        let mut b = Board::new(5).unwrap();
        b.play(Color::White, p(0, 1)).unwrap();
        b.play(Color::White, p(1, 0)).unwrap();
        b.play(Color::White, p(2, 1)).unwrap();
        b.play(Color::White, p(1, 2)).unwrap();
        assert_eq!(b.play(Color::Black, p(1, 1)).unwrap_err(), RuleError::Suicide);
    }

    #[test]
    fn setup_can_add_replace_and_clear_stones() {
        let mut b = Board::new(5).unwrap();
        let point = Point { x: 2, y: 3 };

        b.set_stone(point, Some(Color::Black)).unwrap();
        assert_eq!(b.get(point).unwrap(), Some(Color::Black));

        b.set_stone(point, Some(Color::White)).unwrap();
        assert_eq!(b.get(point).unwrap(), Some(Color::White));

        b.set_stone(point, None).unwrap();
        assert_eq!(b.get(point).unwrap(), None);
        assert_eq!(
            b.set_stone(Point { x: 5, y: 0 }, Some(Color::Black)).unwrap_err(),
            RuleError::OutOfBounds
        );
    }

    fn rb_point(x: u8, y: u8) -> Point {
        Point { x, y }
    }

    fn rb_marker(x: u8, y: u8, color: Color) -> ReadBoardMarker {
        ReadBoardMarker {
            point: rb_point(x, y),
            color,
        }
    }

    fn rb_stones(placements: &[(u8, u8, Color)]) -> Vec<Option<Color>> {
        let mut stones = vec![None; 9];
        for (x, y, color) in placements {
            stones[*y as usize * 3 + *x as usize] = Some(*color);
        }
        stones
    }

    fn rb_provider(kind: ReadBoardProviderKind) -> ReadBoardProvider {
        ReadBoardProvider { kind, source: None }
    }

    fn rb_snapshot(
        stones: Vec<Option<Color>>,
        marker: Option<ReadBoardMarker>,
        remote_move_number: Option<u32>,
        kind: ReadBoardProviderKind,
    ) -> ReadBoardSnapshot {
        ReadBoardSnapshot {
            board_size: 3,
            stones,
            last_move: marker,
            remote_move_number,
            provider: rb_provider(kind),
        }
    }

    fn rb_position(
        stones: Vec<Option<Color>>,
        marker: Option<ReadBoardMarker>,
        move_number: u32,
        black_to_play: bool,
    ) -> ReadBoardLocalPosition {
        ReadBoardLocalPosition::new(stones, marker, move_number, black_to_play)
    }

    fn rb_context(
        positions: Vec<ReadBoardLocalPosition>,
        current_index: usize,
        main_end_index: usize,
    ) -> ReadBoardLocalContext {
        ReadBoardLocalContext {
            board_size: 3,
            positions,
            current_index,
            main_end_index,
        }
    }

    fn rb_decide(
        first_sync: bool,
        snapshot: ReadBoardSnapshot,
        local: ReadBoardLocalContext,
    ) -> ReadBoardSyncDecision {
        decide_readboard_sync(&ReadBoardSyncInput {
            first_sync,
            snapshot,
            local,
        })
        .unwrap()
    }

    #[test]
    fn readboard_first_sync_rebuilds_snapshot_without_history_replay() {
        let initial = rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White)]);
        let target = rb_stones(&[(0, 0, Color::Black)]);
        let local = rb_context(vec![rb_position(initial, None, 2, true)], 0, 0);
        let snapshot = rb_snapshot(
            target,
            Some(rb_marker(0, 0, Color::Black)),
            None,
            ReadBoardProviderKind::Generic,
        );

        assert_eq!(
            rb_decide(true, snapshot, local),
            ReadBoardSyncDecision::RebuildSnapshot {
                reason: ReadBoardRebuildReason::FirstSync,
                move_number: 1,
                black_to_play: false,
                preserved_metadata: ReadBoardSnapshotMetadata::default(),
            }
        );
    }

    #[test]
    fn readboard_first_sync_empty_rollback_restores_black_to_play() {
        let initial = rb_stones(&[(0, 0, Color::Black)]);
        let local = rb_context(
            vec![rb_position(
                initial,
                Some(rb_marker(0, 0, Color::Black)),
                1,
                false,
            )],
            0,
            0,
        );
        let snapshot = rb_snapshot(vec![None; 9], None, None, ReadBoardProviderKind::Generic);

        assert_eq!(
            rb_decide(true, snapshot, local),
            ReadBoardSyncDecision::RebuildSnapshot {
                reason: ReadBoardRebuildReason::FirstSync,
                move_number: 0,
                black_to_play: true,
                preserved_metadata: ReadBoardSnapshotMetadata::default(),
            }
        );
    }

    #[test]
    fn readboard_non_first_sync_empty_rollback_rebuilds_when_no_empty_ancestor_exists() {
        let initial = rb_stones(&[(0, 0, Color::Black)]);
        let local = rb_context(
            vec![rb_position(
                initial,
                Some(rb_marker(0, 0, Color::Black)),
                1,
                false,
            )],
            0,
            0,
        );
        let snapshot = rb_snapshot(vec![None; 9], None, None, ReadBoardProviderKind::Generic);

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::RebuildSnapshot {
                reason: ReadBoardRebuildReason::EmptyRollback,
                move_number: 0,
                black_to_play: true,
                preserved_metadata: ReadBoardSnapshotMetadata::default(),
            }
        );
    }

    #[test]
    fn readboard_fox_live_rollback_reuses_matching_ancestor_with_repeated_stones() {
        let move_one_stones = rb_stones(&[(1, 1, Color::Black)]);
        let move_three_stones = rb_stones(&[(1, 1, Color::Black), (0, 0, Color::Black)]);
        let local = rb_context(
            vec![
                rb_position(
                    move_one_stones.clone(),
                    Some(rb_marker(1, 1, Color::Black)),
                    1,
                    false,
                ),
                rb_position(move_one_stones.clone(), None, 2, true),
                rb_position(move_three_stones, Some(rb_marker(0, 0, Color::Black)), 3, false),
            ],
            2,
            2,
        );
        let snapshot = rb_snapshot(move_one_stones, None, Some(1), ReadBoardProviderKind::FoxLive);

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::ReuseAncestor {
                target_index: 0,
                main_end_index: 2,
            }
        );
    }

    #[test]
    fn readboard_fox_ancestor_match_ignores_marker_mismatch() {
        let ancestor = rb_stones(&[(1, 1, Color::Black)]);
        let end = rb_stones(&[(1, 1, Color::Black), (0, 0, Color::White), (2, 2, Color::Black)]);
        let local = rb_context(
            vec![
                rb_position(ancestor.clone(), Some(rb_marker(1, 1, Color::Black)), 1, false),
                rb_position(
                    rb_stones(&[(1, 1, Color::Black), (0, 0, Color::White)]),
                    Some(rb_marker(0, 0, Color::White)),
                    2,
                    true,
                ),
                rb_position(end, Some(rb_marker(2, 2, Color::Black)), 3, false),
            ],
            2,
            2,
        );
        let snapshot = rb_snapshot(
            ancestor,
            Some(rb_marker(1, 1, Color::White)),
            Some(1),
            ReadBoardProviderKind::FoxLive,
        );

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::ReuseAncestor {
                target_index: 0,
                main_end_index: 2,
            }
        );
    }

    #[test]
    fn readboard_forward_to_existing_node_navigates_inside_retained_window() {
        let move_one = rb_stones(&[(0, 0, Color::Black)]);
        let move_two = rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White)]);
        let move_three = rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White), (0, 1, Color::Black)]);
        let local = rb_context(
            vec![
                rb_position(move_one, Some(rb_marker(0, 0, Color::Black)), 1, false),
                rb_position(move_two.clone(), Some(rb_marker(1, 0, Color::White)), 2, true),
                rb_position(move_three, Some(rb_marker(0, 1, Color::Black)), 3, false),
            ],
            0,
            2,
        );
        let snapshot = rb_snapshot(
            move_two,
            Some(rb_marker(1, 0, Color::White)),
            Some(2),
            ReadBoardProviderKind::FoxLive,
        );

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::NavigateExisting { target_index: 1 }
        );
    }

    #[test]
    fn readboard_append_move_when_snapshot_is_one_forward_step() {
        let move_one = rb_stones(&[(0, 0, Color::Black)]);
        let move_two = rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White)]);
        let local = rb_context(
            vec![rb_position(
                move_one,
                Some(rb_marker(0, 0, Color::Black)),
                1,
                false,
            )],
            0,
            0,
        );
        let snapshot = rb_snapshot(
            move_two,
            Some(rb_marker(1, 0, Color::White)),
            Some(2),
            ReadBoardProviderKind::Generic,
        );

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::AppendMove {
                point: rb_point(1, 0),
                color: Color::White,
                move_number: 2,
                black_to_play: true,
            }
        );
    }

    #[test]
    fn readboard_provider_kind_serializes_as_snake_case_contract() {
        let context = ReadBoardRemoteContext::fox_live("room-43581", Some(18), Some(19));
        let value = serde_json::to_value(&context).unwrap();
        let encoded = serde_json::to_string(&context).unwrap();

        assert_eq!(value["provider"]["kind"], json!("fox_live"));
        assert_eq!(value["provider"]["source"], json!("room-43581"));
        assert!(!encoded.contains("FoxLive"));

        let decoded: ReadBoardRemoteContext = serde_json::from_value(json!({
            "provider": {
                "kind": "fox_record",
                "source": "record-fingerprint"
            },
            "remote_move_number": 256,
            "record_current_move": 120,
            "record_total_move": 256,
            "record_at_end": true
        }))
        .unwrap();
        assert_eq!(decoded.provider.kind, ReadBoardProviderKind::FoxRecord);
    }

    #[test]
    fn readboard_append_move_decision_uses_tagged_snake_case_contract() {
        let decision = ReadBoardSyncDecision::AppendMove {
            point: rb_point(1, 0),
            color: Color::White,
            move_number: 2,
            black_to_play: true,
        };
        let value = serde_json::to_value(&decision).unwrap();
        let encoded = serde_json::to_string(&decision).unwrap();

        assert_eq!(
            value,
            json!({
                "kind": "append_move",
                "point": { "x": 1, "y": 0 },
                "color": "white",
                "move_number": 2,
                "black_to_play": true
            })
        );
        assert!(!encoded.contains("AppendMove"));
        assert!(!encoded.contains("White"));

        let decoded: ReadBoardSyncDecision = serde_json::from_value(json!({
            "kind": "append_move",
            "point": { "x": 1, "y": 0 },
            "color": "white",
            "move_number": 2,
            "black_to_play": true
        }))
        .unwrap();
        assert_eq!(decoded, decision);
    }

    #[test]
    fn readboard_rebuild_snapshot_decision_uses_tagged_snake_case_contract() {
        let mut metadata = ReadBoardSnapshotMetadata::default();
        metadata
            .properties
            .insert("AB".to_string(), vec!["aa".to_string()]);
        metadata.comment = Some("setup snapshot comment".to_string());
        metadata.extra_stones.push(ReadBoardExtraStone {
            point: rb_point(2, 2),
            color: Color::Black,
        });
        metadata.has_removed_stone = true;

        let decision = ReadBoardSyncDecision::RebuildSnapshot {
            reason: ReadBoardRebuildReason::MoveNumberJump,
            move_number: 58,
            black_to_play: true,
            preserved_metadata: metadata,
        };
        let value = serde_json::to_value(&decision).unwrap();
        let encoded = serde_json::to_string(&decision).unwrap();

        assert_eq!(value["kind"], json!("rebuild_snapshot"));
        assert_eq!(value["reason"], json!("move_number_jump"));
        assert_eq!(
            value["preserved_metadata"],
            json!({
                "properties": { "AB": ["aa"] },
                "comment": "setup snapshot comment",
                "extra_stones": [
                    {
                        "point": { "x": 2, "y": 2 },
                        "color": "black"
                    }
                ],
                "has_removed_stone": true
            })
        );
        assert!(!encoded.contains("RebuildSnapshot"));
        assert!(!encoded.contains("MoveNumberJump"));
        assert!(!encoded.contains("Black"));

        let decoded: ReadBoardSyncDecision = serde_json::from_value(value).unwrap();
        assert_eq!(decoded, decision);
    }

    #[test]
    fn readboard_markerless_fox_odd_move_number_rebuilds_with_white_to_play() {
        let target = rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White)]);
        let local = rb_context(vec![rb_position(vec![None; 9], None, 0, true)], 0, 0);
        let snapshot = rb_snapshot(target, None, Some(57), ReadBoardProviderKind::FoxLive);

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::RebuildSnapshot {
                reason: ReadBoardRebuildReason::MoveNumberJump,
                move_number: 57,
                black_to_play: false,
                preserved_metadata: ReadBoardSnapshotMetadata::default(),
            }
        );
    }

    #[test]
    fn readboard_markerless_fox_even_move_number_rebuilds_with_black_to_play() {
        let target = rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White)]);
        let local = rb_context(vec![rb_position(vec![None; 9], None, 0, true)], 0, 0);
        let snapshot = rb_snapshot(target, None, Some(58), ReadBoardProviderKind::FoxLive);

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::RebuildSnapshot {
                reason: ReadBoardRebuildReason::MoveNumberJump,
                move_number: 58,
                black_to_play: true,
                preserved_metadata: ReadBoardSnapshotMetadata::default(),
            }
        );
    }

    #[test]
    fn readboard_fox_move_number_jump_from_midgame_rebuilds_instead_of_replaying() {
        let initial = rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White)]);
        let target = rb_stones(&[
            (0, 0, Color::Black),
            (1, 0, Color::White),
            (0, 1, Color::Black),
            (1, 1, Color::White),
            (2, 2, Color::Black),
        ]);
        let local = rb_context(
            vec![rb_position(initial, Some(rb_marker(1, 0, Color::White)), 2, true)],
            0,
            0,
        );
        let snapshot = rb_snapshot(target, None, Some(58), ReadBoardProviderKind::FoxLive);

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::RebuildSnapshot {
                reason: ReadBoardRebuildReason::MoveNumberJump,
                move_number: 58,
                black_to_play: true,
                preserved_metadata: ReadBoardSnapshotMetadata::default(),
            }
        );
    }

    #[test]
    fn readboard_invalid_fox_move_number_retains_pending_metadata_and_returns_error() {
        let mut context = ReadBoardRemoteContext::fox_live("43581号", Some(18), None);

        assert_eq!(
            context.apply_fox_move_number_text("nope"),
            Err(ReadBoardMetadataError::InvalidMoveNumber("nope".to_string()))
        );
        assert_eq!(context.remote_move_number, Some(18));

        context.apply_fox_move_number_text("42").unwrap();
        assert_eq!(context.remote_move_number, Some(42));
    }

    #[test]
    fn readboard_record_at_end_falls_back_to_total_move_for_recovery() {
        let context = ReadBoardRemoteContext::fox_record("record-fingerprint", None, Some(256), true);

        assert_eq!(context.recovery_move_number(), Some(256));
    }

    #[test]
    fn readboard_snapshot_rebuild_preserves_current_setup_metadata() {
        let mut metadata = ReadBoardSnapshotMetadata::default();
        metadata
            .properties
            .insert("AB".to_string(), vec!["aa".to_string()]);
        metadata
            .properties
            .insert("AW".to_string(), vec!["ba".to_string()]);
        metadata.comment = Some("setup snapshot comment".to_string());
        metadata.extra_stones.push(ReadBoardExtraStone {
            point: rb_point(2, 2),
            color: Color::Black,
        });
        metadata.has_removed_stone = true;

        let target = rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White), (2, 2, Color::Black)]);
        let mut position = rb_position(target.clone(), None, 2, true);
        position.metadata = metadata.clone();
        let local = rb_context(vec![position], 0, 0);
        let snapshot = rb_snapshot(target, None, Some(58), ReadBoardProviderKind::FoxLive);

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::RebuildSnapshot {
                reason: ReadBoardRebuildReason::MoveNumberJump,
                move_number: 58,
                black_to_play: true,
                preserved_metadata: metadata,
            }
        );
    }

    #[test]
    fn readboard_snapshot_rebuild_preserves_setup_metadata_from_anchor() {
        let mut metadata = ReadBoardSnapshotMetadata::default();
        metadata
            .properties
            .insert("AE".to_string(), vec!["cb".to_string()]);
        metadata.comment = Some("setup snapshot comment".to_string());

        let anchor_stones = rb_stones(&[(0, 0, Color::Black), (2, 2, Color::Black)]);
        let mut anchor = rb_position(anchor_stones, None, 7, false);
        anchor.metadata = metadata.clone();
        let current = rb_position(
            rb_stones(&[(0, 0, Color::Black), (1, 1, Color::White), (2, 2, Color::Black)]),
            Some(rb_marker(1, 1, Color::White)),
            8,
            true,
        );
        let local = rb_context(vec![anchor, current], 1, 1);
        let snapshot = rb_snapshot(
            rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White), (2, 2, Color::Black)]),
            Some(rb_marker(1, 0, Color::White)),
            None,
            ReadBoardProviderKind::Generic,
        );

        assert_eq!(
            rb_decide(false, snapshot, local),
            ReadBoardSyncDecision::RebuildSnapshot {
                reason: ReadBoardRebuildReason::NoReusableHistory,
                move_number: 3,
                black_to_play: true,
                preserved_metadata: metadata,
            }
        );
    }

    #[test]
    fn readboard_snapshot_can_be_built_from_legacy_codes_with_marker_metadata() {
        let snapshot = ReadBoardSnapshot::from_legacy_codes(
            3,
            [3, 2, 0, 0, 0, 0, 0, 0, 0],
            Some(57),
            rb_provider(ReadBoardProviderKind::FoxLive),
        )
        .unwrap();

        assert_eq!(
            snapshot.stones,
            rb_stones(&[(0, 0, Color::Black), (1, 0, Color::White)])
        );
        assert_eq!(snapshot.last_move, Some(rb_marker(0, 0, Color::Black)));
        assert_eq!(snapshot.remote_move_number, Some(57));
    }
}
