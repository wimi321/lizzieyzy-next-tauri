import { invoke } from "@tauri-apps/api/core";
import type { AnalysisFrameDto, AppHealthDto, GameDto, ProblemMarkerDto } from "../domain/types";

const isTauriRuntime = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export async function getHealth(): Promise<AppHealthDto> {
  if (!isTauriRuntime()) {
    return { app: "LizzieYzy Next", architecture: "browser-preview", rust_backend_ready: false, notes: ["Vite 浏览器预览；Tauri 运行时启动后会调用 Rust 后端。"] };
  }
  return invoke<AppHealthDto>("health");
}

export async function parseSgfSummary(sgfText: string): Promise<GameDto> {
  if (!isTauriRuntime()) throw new Error("SGF 解析需要 Tauri Rust 后端；当前可先使用演示棋局。");
  return invoke<GameDto>("parse_sgf_summary", { sgfText });
}

export async function fakeAnalyze(sgfText: string): Promise<AnalysisFrameDto[]> {
  if (!isTauriRuntime()) return [];
  return invoke<AnalysisFrameDto[]>("fake_analyze", { sgfText });
}

export async function classifyProblems(frames: AnalysisFrameDto[]): Promise<ProblemMarkerDto[]> {
  if (!isTauriRuntime()) return [];
  return invoke<ProblemMarkerDto[]>("classify_problems", { frames });
}
