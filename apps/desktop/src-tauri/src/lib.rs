use app_model::{AnalysisFrameDto, AppHealthDto, CandidateMoveDto, EngineProfileDto, MoveVertex, PointDto};
use engine_manager::{build_command_spec, check_assets, AssetCheck, CommandSpec};
use uuid::Uuid;

#[tauri::command]
fn health() -> AppHealthDto {
    AppHealthDto {
        app: "LizzieYzy Next".to_string(),
        architecture: "Tauri 2 + Rust workspace + TypeScript UI".to_string(),
        rust_backend_ready: true,
        notes: vec![
            "SGF parser command is wired".to_string(),
            "Fake analysis command is wired for UI development before KataGo process streaming".to_string(),
            "KataGo launch plan command is wired".to_string(),
        ],
    }
}

#[tauri::command]
fn parse_sgf_summary(sgf_text: String) -> Result<app_model::GameDto, String> {
    let document = sgf::parse_sgf(&sgf_text).map_err(|err| err.to_string())?;
    Ok(sgf::to_game_dto(document))
}

#[tauri::command]
fn fake_analyze(sgf_text: String) -> Result<Vec<AnalysisFrameDto>, String> {
    let document = sgf::parse_sgf(&sgf_text).map_err(|err| err.to_string())?;
    let job_id = Uuid::new_v4();
    let mut frames = Vec::new();
    for turn in 0..=document.moves.len() as u32 {
        let drift = ((turn as f32 * 0.73).sin()) * 0.13;
        let winrate = (0.52 + drift).clamp(0.05, 0.95);
        let score = (turn as f32 * 0.31).cos() * 6.0;
        frames.push(AnalysisFrameDto {
            job_id,
            game_id: None,
            node_id: None,
            turn,
            visits: 256,
            winrate_black: winrate,
            score_mean_black: score,
            score_stdev: Some(4.2),
            candidates: demo_candidates(turn, document.board_size),
            ownership: None,
            policy: None,
        });
    }
    Ok(frames)
}

#[tauri::command]
fn classify_problems(frames: Vec<AnalysisFrameDto>) -> Vec<app_model::ProblemMarkerDto> {
    analysis_core::classify_problem_markers(&frames)
}

#[tauri::command]
fn katago_launch_plan(profile: EngineProfileDto) -> Result<CommandSpec, String> {
    build_command_spec(&profile).map_err(|err| err.to_string())
}

#[tauri::command]
fn engine_asset_checks(profile: EngineProfileDto) -> Vec<AssetCheck> {
    check_assets(&profile)
}

fn demo_candidates(turn: u32, board_size: u8) -> Vec<CandidateMoveDto> {
    let anchors = [(15usize, 3usize), (3, 15), (15, 15), (3, 3), (9, 9), (10, 15)];
    anchors
        .iter()
        .enumerate()
        .map(|(index, (x, y))| CandidateMoveDto {
            vertex: MoveVertex::Point(PointDto {
                x: ((*x + turn as usize + index) % board_size as usize) as u8,
                y: ((*y + index * 2) % board_size as usize) as u8,
            }),
            visits: 128u32.saturating_sub(index as u32 * 13),
            winrate_black: (0.58 - index as f32 * 0.025).clamp(0.0, 1.0),
            score_mean_black: 4.5 - index as f32,
            policy_prior: Some(0.18 - index as f32 * 0.015),
            pv: Vec::new(),
        })
        .collect()
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            health,
            parse_sgf_summary,
            fake_analyze,
            classify_problems,
            katago_launch_plan,
            engine_asset_checks
        ])
        .run(tauri::generate_context!())
        .expect("failed to run LizzieYzy Next");
}
