use serde::{Deserialize, Serialize};
use std::collections::{HashSet, VecDeque};
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
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

#[cfg(test)]
mod tests {
    use super::*;
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
}
