import type { GameDto, MoveDto, MoveVertex, PlayerColor, PointDto } from "./types";

export type Stone = PointDto & { color: PlayerColor; moveNumber: number };

export function isPoint(vertex: MoveVertex): vertex is { point: PointDto } {
  return typeof vertex === "object" && vertex !== null && "point" in vertex;
}

export function replayMainLine(game: GameDto, untilMove = game.moves.length): Stone[] {
  const stones = new Map<string, Stone>();
  for (const move of game.moves.slice(0, untilMove)) {
    if (!isPoint(move.vertex)) continue;
    const { x, y } = move.vertex.point;
    stones.set(`${x}:${y}`, { x, y, color: move.color, moveNumber: move.move_number });
  }
  return [...stones.values()];
}

export function vertexLabel(vertex: MoveVertex, boardSize: number): string {
  if (!isPoint(vertex)) return "pass";
  const letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ";
  const col = letters[vertex.point.x] ?? "?";
  return `${col}${boardSize - vertex.point.y}`;
}

export function createDemoGame(): GameDto {
  const moves: MoveDto[] = [
    { color: "black", vertex: { point: { x: 15, y: 3 } }, move_number: 1 },
    { color: "white", vertex: { point: { x: 3, y: 15 } }, move_number: 2 },
    { color: "black", vertex: { point: { x: 15, y: 15 } }, move_number: 3 },
    { color: "white", vertex: { point: { x: 3, y: 3 } }, move_number: 4 },
    { color: "black", vertex: { point: { x: 10, y: 16 } }, move_number: 5 },
    { color: "white", vertex: { point: { x: 16, y: 10 } }, move_number: 6 }
  ];
  return { summary: { id: "demo", board_size: 19, komi: 7.5, black_name: "Black", white_name: "White", result: null, move_count: moves.length }, moves };
}
