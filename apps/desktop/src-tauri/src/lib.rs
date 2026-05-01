use app_model::{
    AnalysisFrameDto, AppHealthDto, CandidateMoveDto, EngineBackend, EngineProfileDto, MoveVertex, PointDto,
    PositionDto,
};
use engine_manager::{
    build_command_spec, check_assets, AnalysisBatchRunOptions, AnalysisCancelToken, AssetCheck, CommandSpec,
    EngineManagerError,
};
use katago_protocol::{AnalysisBatchQueryOptions, AnalysisQueryOptions};
use rusqlite::{Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::ErrorKind;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager, State};
use uuid::Uuid;

const ENGINE_PROFILE_FILE: &str = "lizzieyzy-next-engine-profile.json";
const APP_PREFERENCES_FILE: &str = "lizzieyzy-next-app-preferences.json";
const ANALYSIS_CACHE_DB_FILE: &str = "analysis-cache.sqlite3";
const DEFAULT_ENGINE_PROFILE_ID: &str = "default";

#[derive(Default)]
struct AnalysisJobRegistry {
    jobs: Mutex<HashMap<String, AnalysisCancelToken>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EngineProfileSettingsDto {
    profile: EngineProfileDto,
    max_visits: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EngineProfileRecordDto {
    id: String,
    profile: EngineProfileDto,
    max_visits: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EngineProfilesSettingsDto {
    selected_profile_id: String,
    profiles: Vec<EngineProfileRecordDto>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct AppPreferencesDto {
    #[serde(default = "default_show_ownership")]
    show_ownership: bool,
    #[serde(default = "default_show_policy")]
    show_policy: bool,
    #[serde(default = "default_show_candidates")]
    show_candidates: bool,
    #[serde(default = "default_candidate_limit")]
    candidate_limit: u32,
    #[serde(default = "default_auto_load_cache")]
    auto_load_cache: bool,
    #[serde(default = "default_auto_save_analysis")]
    auto_save_analysis: bool,
    #[serde(default = "default_max_visits")]
    default_max_visits: u32,
    #[serde(default = "default_review_mode")]
    review_mode: String,
    #[serde(default = "default_board_theme")]
    board_theme: String,
}

struct PreparedBatchAnalysis {
    query_jsonl: String,
    turns: Vec<u32>,
    board_size: u8,
    expected: usize,
    timeout: Duration,
}

#[derive(Debug, Clone, Serialize)]
struct AnalysisProgressPayload {
    job_id: String,
    completed: usize,
    expected: usize,
    turn: Option<u32>,
    response_jsonl: String,
}

#[derive(Debug, Clone, Serialize)]
struct AnalysisCompletePayload {
    job_id: String,
    frames: Vec<AnalysisFrameDto>,
}

#[derive(Debug, Clone, Serialize)]
struct AnalysisMessagePayload {
    job_id: String,
    message: String,
}

#[derive(Debug, Clone, Serialize)]
struct ComputeGameCacheKeyDto {
    game_key: String,
    sgf_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AnalysisCacheRecordDto {
    id: String,
    game_key: String,
    sgf_hash: String,
    profile_id: Option<String>,
    engine_kind: Option<String>,
    source: String,
    move_count: u32,
    analyzed_move_count: u32,
    payload: Value,
    created_at: Option<String>,
    updated_at: String,
}

#[derive(Debug, Clone, Serialize)]
struct GetAnalysisCacheDto {
    status: String,
    record: Option<AnalysisCacheRecordDto>,
    error: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct SaveAnalysisCacheDto {
    id: String,
    game_key: String,
    updated_at: String,
}

#[derive(Debug, Clone, Serialize)]
struct DeleteAnalysisCacheDto {
    deleted: usize,
}

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
fn replay_sgf_positions(sgf_text: String) -> Result<Vec<PositionDto>, String> {
    sgf::replay_sgf_positions(&sgf_text).map_err(|err| err.to_string())
}

#[tauri::command]
fn read_sgf_file(path: String) -> Result<String, String> {
    let path = non_empty_path(path)?;
    fs::read_to_string(&path).map_err(|err| format!("failed to read SGF file {}: {err}", path.display()))
}

#[tauri::command]
fn write_sgf_file(path: String, sgf_text: String) -> Result<(), String> {
    let path = non_empty_path(path)?;
    sgf::parse_sgf(&sgf_text).map_err(|err| format!("failed to parse SGF text: {err}"))?;
    fs::write(&path, sgf_text).map_err(|err| format!("failed to write SGF file {}: {err}", path.display()))
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
    let mut checks = check_assets(&profile);
    if matches!(profile.backend, EngineBackend::KataGoAnalysis) {
        ensure_asset_check(&mut checks, &profile.model_path, "model");
        ensure_asset_check(&mut checks, &profile.config_path, "config");
    }
    checks
}

#[tauri::command]
fn load_app_preferences(app_handle: AppHandle) -> Result<AppPreferencesDto, String> {
    let path = app_preferences_path(&app_handle)?;
    match fs::read_to_string(&path) {
        Ok(contents) => serde_json::from_str::<AppPreferencesDto>(&contents)
            .map_err(|err| format!("failed to parse {}: {err}", path.display()))
            .map(normalize_app_preferences),
        Err(err) if err.kind() == ErrorKind::NotFound => Ok(default_app_preferences()),
        Err(err) => Err(format!("failed to read {}: {err}", path.display())),
    }
}

#[tauri::command]
fn save_app_preferences(
    app_handle: AppHandle,
    preferences: AppPreferencesDto,
) -> Result<AppPreferencesDto, String> {
    let preferences = normalize_app_preferences(preferences);
    let path = app_preferences_path(&app_handle)?;
    let json = serde_json::to_string_pretty(&preferences)
        .map_err(|err| format!("failed to serialize app preferences: {err}"))?;
    fs::write(&path, json).map_err(|err| format!("failed to write {}: {err}", path.display()))?;
    Ok(preferences)
}

#[tauri::command]
fn load_engine_profile_settings(app_handle: AppHandle) -> Result<Option<EngineProfileSettingsDto>, String> {
    let settings = load_engine_profiles_settings(app_handle)?;
    let selected = selected_engine_profile_record(&settings)
        .or_else(|| settings.profiles.first())
        .cloned();
    Ok(selected.map(|record| EngineProfileSettingsDto {
        profile: record.profile,
        max_visits: record.max_visits,
    }))
}

#[tauri::command]
fn save_engine_profile_settings(
    app_handle: AppHandle,
    settings: EngineProfileSettingsDto,
) -> Result<EngineProfileSettingsDto, String> {
    validate_engine_profile_settings(&settings)?;
    let collection = EngineProfilesSettingsDto {
        selected_profile_id: DEFAULT_ENGINE_PROFILE_ID.to_string(),
        profiles: vec![EngineProfileRecordDto {
            id: DEFAULT_ENGINE_PROFILE_ID.to_string(),
            profile: settings.profile.clone(),
            max_visits: settings.max_visits,
        }],
    };
    let saved = save_engine_profiles_settings(app_handle, collection)?;
    let selected = selected_engine_profile_record(&saved)
        .ok_or_else(|| "saved engine profile collection did not include the selected profile".to_string())?;
    Ok(EngineProfileSettingsDto {
        profile: selected.profile.clone(),
        max_visits: selected.max_visits,
    })
}

#[tauri::command]
fn load_engine_profiles_settings(app_handle: AppHandle) -> Result<EngineProfilesSettingsDto, String> {
    let path = engine_profile_path(&app_handle)?;
    match fs::read_to_string(&path) {
        Ok(contents) => parse_engine_profiles_settings(&contents, &path),
        Err(err) if err.kind() == ErrorKind::NotFound => load_legacy_engine_profile_settings(&app_handle),
        Err(err) => Err(format!("failed to read {}: {err}", path.display())),
    }
}

#[tauri::command]
fn save_engine_profiles_settings(
    app_handle: AppHandle,
    settings: EngineProfilesSettingsDto,
) -> Result<EngineProfilesSettingsDto, String> {
    let settings = normalize_engine_profiles_settings(settings)?;
    let path = engine_profile_path(&app_handle)?;
    let json = serde_json::to_string_pretty(&settings)
        .map_err(|err| format!("failed to serialize engine profiles: {err}"))?;
    fs::write(&path, json).map_err(|err| format!("failed to write {}: {err}", path.display()))?;
    Ok(settings)
}

#[tauri::command]
fn compute_game_cache_key(
    sgf_text: String,
    file_path: Option<String>,
) -> Result<ComputeGameCacheKeyDto, String> {
    let _ = file_path;
    let document = sgf::parse_sgf(&sgf_text).map_err(|err| err.to_string())?;
    let sgf_hash = stable_hash_hex(&sgf_text);
    let canonical = serde_json::json!({
        "document": document,
        "raw_sgf_hash": sgf_hash,
    });
    let canonical_text = serde_json::to_string(&canonical)
        .map_err(|err| format!("failed to serialize canonical SGF cache key: {err}"))?;
    let game_key = format!("sgf:{}", stable_hash_hex(&canonical_text));
    Ok(ComputeGameCacheKeyDto { game_key, sgf_hash })
}

#[tauri::command]
fn get_analysis_cache(
    app_handle: AppHandle,
    game_key: String,
    profile_id: Option<String>,
    engine_kind: Option<String>,
) -> Result<GetAnalysisCacheDto, String> {
    let path = analysis_cache_db_path(&app_handle)?;
    get_analysis_cache_at_path(&path, game_key, profile_id, engine_kind)
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn save_analysis_cache(
    app_handle: AppHandle,
    game_key: String,
    sgf_hash: String,
    profile_id: Option<String>,
    engine_kind: String,
    source: String,
    move_count: u32,
    analyzed_move_count: u32,
    payload: Value,
) -> Result<SaveAnalysisCacheDto, String> {
    let path = analysis_cache_db_path(&app_handle)?;
    save_analysis_cache_at_path(
        &path,
        game_key,
        sgf_hash,
        profile_id,
        engine_kind,
        source,
        move_count,
        analyzed_move_count,
        payload,
    )
}

#[tauri::command]
fn delete_analysis_cache(
    app_handle: AppHandle,
    game_key: String,
    profile_id: Option<String>,
    engine_kind: Option<String>,
) -> Result<DeleteAnalysisCacheDto, String> {
    let path = analysis_cache_db_path(&app_handle)?;
    delete_analysis_cache_at_path(&path, game_key, profile_id, engine_kind)
}

#[tauri::command]
fn katago_analyze_once(
    profile: EngineProfileDto,
    sgf_text: String,
    turn: u32,
    max_visits: u32,
) -> Result<AnalysisFrameDto, String> {
    let document = sgf::parse_sgf(&sgf_text).map_err(|err| err.to_string())?;
    let game = sgf::to_game_dto(document);
    let job_id = Uuid::new_v4();
    let query = katago_protocol::analysis_query_from_game(
        &game,
        AnalysisQueryOptions {
            id: job_id.to_string(),
            rules: "chinese".to_string(),
            turn,
            max_visits: Some(max_visits),
            include_ownership: Some(true),
            include_policy: Some(true),
        },
    )
    .map_err(|err| err.to_string())?;
    let query_jsonl = query.to_jsonl().map_err(|err| err.to_string())?;
    let spec = engine_manager::build_command_spec(&profile).map_err(|err| err.to_string())?;
    let result = engine_manager::run_katago_analysis_once(&spec, &query_jsonl, Duration::from_secs(60))
        .map_err(|err| err.to_string())?;
    let response =
        katago_protocol::parse_response_line(&result.response_jsonl).map_err(|err| err.to_string())?;
    Ok(katago_protocol::normalize_response(
        job_id,
        response,
        game.summary.board_size,
    ))
}

#[tauri::command]
fn katago_analyze_game(
    profile: EngineProfileDto,
    sgf_text: String,
    max_visits: u32,
) -> Result<Vec<AnalysisFrameDto>, String> {
    let job_id = Uuid::new_v4();
    let prepared = prepare_katago_batch_analysis(&sgf_text, job_id, max_visits)?;
    let spec = build_command_spec(&profile).map_err(|err| err.to_string())?;
    let result = engine_manager::run_katago_analysis_batch(
        &spec,
        &prepared.query_jsonl,
        prepared.expected,
        prepared.timeout,
    )
    .map_err(|err| err.to_string())?;
    let responses = result
        .response_jsonl_lines
        .iter()
        .map(|line| katago_protocol::parse_response_line(line).map_err(|err| err.to_string()))
        .collect::<Result<Vec<_>, _>>()?;
    validate_batch_response_turns(&prepared.turns, &responses)?;

    Ok(katago_protocol::normalize_responses_for_turns(
        job_id,
        responses,
        prepared.board_size,
        &prepared.turns,
    ))
}

#[tauri::command]
fn katago_start_analyze_game(
    app_handle: AppHandle,
    registry: State<'_, AnalysisJobRegistry>,
    profile: EngineProfileDto,
    sgf_text: String,
    max_visits: u32,
) -> Result<String, String> {
    let job_id = Uuid::new_v4();
    let job_id_string = job_id.to_string();
    let prepared = prepare_katago_batch_analysis(&sgf_text, job_id, max_visits)?;
    let spec = build_command_spec(&profile).map_err(|err| err.to_string())?;
    let cancel_token = AnalysisCancelToken::new();

    {
        let mut jobs = registry
            .jobs
            .lock()
            .map_err(|_| "analysis job registry is unavailable".to_string())?;
        jobs.insert(job_id_string.clone(), cancel_token.clone());
    }

    std::thread::spawn({
        let job_id_string = job_id_string.clone();
        move || {
            run_katago_analysis_job(app_handle, job_id, job_id_string, spec, prepared, cancel_token);
        }
    });

    Ok(job_id_string)
}

#[tauri::command]
fn katago_cancel_analysis(registry: State<'_, AnalysisJobRegistry>, job_id: String) -> Result<(), String> {
    let cancel_token = {
        let jobs = registry
            .jobs
            .lock()
            .map_err(|_| "analysis job registry is unavailable".to_string())?;
        jobs.get(&job_id).cloned()
    };

    match cancel_token {
        Some(cancel_token) => {
            cancel_token.cancel();
            Ok(())
        }
        None => Err(format!("analysis job not found: {job_id}")),
    }
}

fn prepare_katago_batch_analysis(
    sgf_text: &str,
    job_id: Uuid,
    max_visits: u32,
) -> Result<PreparedBatchAnalysis, String> {
    let document = sgf::parse_sgf(sgf_text).map_err(|err| err.to_string())?;
    let game = sgf::to_game_dto(document);
    let query = katago_protocol::analysis_batch_query_from_game(
        &game,
        AnalysisBatchQueryOptions {
            id: job_id.to_string(),
            rules: "chinese".to_string(),
            analyze_turns: None,
            max_visits: Some(max_visits),
            include_ownership: Some(true),
            include_policy: Some(true),
        },
    )
    .map_err(|err| err.to_string())?;
    let turns = query.analyze_turns.clone().unwrap_or_default();
    if turns.is_empty() {
        return Err("analysis batch query did not include any turns".to_string());
    }

    let query_jsonl = query.to_jsonl().map_err(|err| err.to_string())?;
    let expected = turns.len();
    let timeout_secs = 60u64.max((expected as u64).saturating_mul(15)).min(600);
    Ok(PreparedBatchAnalysis {
        query_jsonl,
        turns,
        board_size: game.summary.board_size,
        expected,
        timeout: Duration::from_secs(timeout_secs),
    })
}

fn run_katago_analysis_job(
    app_handle: AppHandle,
    job_id: Uuid,
    job_id_string: String,
    spec: CommandSpec,
    prepared: PreparedBatchAnalysis,
    cancel_token: AnalysisCancelToken,
) {
    let mut on_progress = {
        let app_handle = app_handle.clone();
        let job_id_string = job_id_string.clone();
        move |progress: engine_manager::AnalysisBatchProgress| {
            let turn = katago_protocol::parse_response_line(&progress.response_jsonl_line)
                .map(|response| response.turn_number)
                .ok();
            let payload = AnalysisProgressPayload {
                job_id: job_id_string.clone(),
                completed: progress.response_index,
                expected: progress.expected_responses,
                turn,
                response_jsonl: progress.response_jsonl_line,
            };
            let _ = app_handle.emit("katago://analysis-progress", payload);
        }
    };

    let result = engine_manager::run_katago_analysis_batch_with_options(
        &spec,
        &prepared.query_jsonl,
        AnalysisBatchRunOptions {
            expected_responses: prepared.expected,
            timeout: prepared.timeout,
            cancel_token: Some(&cancel_token),
            on_progress: Some(&mut on_progress),
        },
    );

    match result {
        Ok(result) => emit_katago_analysis_complete(&app_handle, job_id, &job_id_string, prepared, result),
        Err(EngineManagerError::Cancelled { .. }) => {
            let _ = app_handle.emit(
                "katago://analysis-cancelled",
                AnalysisMessagePayload {
                    job_id: job_id_string.clone(),
                    message: "analysis job was cancelled".to_string(),
                },
            );
        }
        Err(err) => {
            let _ = app_handle.emit(
                "katago://analysis-error",
                AnalysisMessagePayload {
                    job_id: job_id_string.clone(),
                    message: err.to_string(),
                },
            );
        }
    }

    remove_analysis_job(&app_handle, &job_id_string);
}

fn emit_katago_analysis_complete(
    app_handle: &AppHandle,
    job_id: Uuid,
    job_id_string: &str,
    prepared: PreparedBatchAnalysis,
    result: engine_manager::AnalysisBatchRunResult,
) {
    let responses = result
        .response_jsonl_lines
        .iter()
        .map(|line| katago_protocol::parse_response_line(line).map_err(|err| err.to_string()))
        .collect::<Result<Vec<_>, _>>();

    let frames = responses.and_then(|responses| {
        validate_batch_response_turns(&prepared.turns, &responses)?;
        Ok(katago_protocol::normalize_responses_for_turns(
            job_id,
            responses,
            prepared.board_size,
            &prepared.turns,
        ))
    });

    match frames {
        Ok(frames) => {
            let _ = app_handle.emit(
                "katago://analysis-complete",
                AnalysisCompletePayload {
                    job_id: job_id_string.to_string(),
                    frames,
                },
            );
        }
        Err(message) => {
            let _ = app_handle.emit(
                "katago://analysis-error",
                AnalysisMessagePayload {
                    job_id: job_id_string.to_string(),
                    message,
                },
            );
        }
    }
}

fn remove_analysis_job(app_handle: &AppHandle, job_id: &str) {
    let Some(registry) = app_handle.try_state::<AnalysisJobRegistry>() else {
        return;
    };
    if let Ok(mut jobs) = registry.jobs.lock() {
        jobs.remove(job_id);
    };
}

fn validate_batch_response_turns(
    expected_turns: &[u32],
    responses: &[katago_protocol::AnalysisResponse],
) -> Result<(), String> {
    let expected = sorted_unique_turns(expected_turns);
    let received_raw = responses
        .iter()
        .map(|response| response.turn_number)
        .collect::<Vec<_>>();
    let received = sorted_unique_turns(&received_raw);
    let duplicates = duplicate_turns(&received_raw);

    if expected == received && duplicates.is_empty() {
        return Ok(());
    }

    let missing = expected
        .iter()
        .copied()
        .filter(|turn| received.binary_search(turn).is_err())
        .collect::<Vec<_>>();
    let unexpected = received
        .iter()
        .copied()
        .filter(|turn| expected.binary_search(turn).is_err())
        .collect::<Vec<_>>();

    Err(format!(
        "KataGo batch response turns did not match request; expected={expected:?}; received={received:?}; missing={missing:?}; unexpected={unexpected:?}; duplicates={duplicates:?}"
    ))
}

fn sorted_unique_turns(turns: &[u32]) -> Vec<u32> {
    let mut values = turns.to_vec();
    values.sort_unstable();
    values.dedup();
    values
}

fn duplicate_turns(turns: &[u32]) -> Vec<u32> {
    let mut values = turns.to_vec();
    values.sort_unstable();
    let mut duplicates = Vec::new();
    for pair in values.windows(2) {
        if pair[0] == pair[1] && duplicates.last().copied() != Some(pair[0]) {
            duplicates.push(pair[0]);
        }
    }
    duplicates
}

fn ensure_asset_check(checks: &mut Vec<AssetCheck>, path: &Option<String>, label: &str) {
    if checks.iter().any(|check| check.label == label) {
        return;
    }
    checks.push(AssetCheck {
        path: path.clone().unwrap_or_default(),
        exists: false,
        required: true,
        label: label.to_string(),
    });
}

fn normalize_app_preferences(mut preferences: AppPreferencesDto) -> AppPreferencesDto {
    preferences.candidate_limit = preferences.candidate_limit.clamp(1, 20);
    preferences.default_max_visits = preferences.default_max_visits.clamp(1, 1_000_000);
    if preferences.review_mode != "deep" {
        preferences.review_mode = default_review_mode();
    }
    if preferences.board_theme != "high-contrast" {
        preferences.board_theme = default_board_theme();
    }
    preferences
}

fn default_app_preferences() -> AppPreferencesDto {
    AppPreferencesDto {
        show_ownership: default_show_ownership(),
        show_policy: default_show_policy(),
        show_candidates: default_show_candidates(),
        candidate_limit: default_candidate_limit(),
        auto_load_cache: default_auto_load_cache(),
        auto_save_analysis: default_auto_save_analysis(),
        default_max_visits: default_max_visits(),
        review_mode: default_review_mode(),
        board_theme: default_board_theme(),
    }
}

fn default_show_ownership() -> bool {
    true
}

fn default_show_policy() -> bool {
    true
}

fn default_show_candidates() -> bool {
    true
}

fn default_candidate_limit() -> u32 {
    8
}

fn default_auto_load_cache() -> bool {
    true
}

fn default_auto_save_analysis() -> bool {
    true
}

fn default_max_visits() -> u32 {
    800
}

fn default_review_mode() -> String {
    "quick".to_string()
}

fn default_board_theme() -> String {
    "classic".to_string()
}

fn selected_engine_profile_record(settings: &EngineProfilesSettingsDto) -> Option<&EngineProfileRecordDto> {
    settings
        .profiles
        .iter()
        .find(|profile| profile.id == settings.selected_profile_id)
}

fn parse_engine_profiles_settings(contents: &str, path: &Path) -> Result<EngineProfilesSettingsDto, String> {
    serde_json::from_str::<EngineProfilesSettingsDto>(contents)
        .or_else(|_| {
            serde_json::from_str::<EngineProfileSettingsDto>(contents).map(|settings| {
                EngineProfilesSettingsDto {
                    selected_profile_id: DEFAULT_ENGINE_PROFILE_ID.to_string(),
                    profiles: vec![EngineProfileRecordDto {
                        id: DEFAULT_ENGINE_PROFILE_ID.to_string(),
                        profile: settings.profile,
                        max_visits: settings.max_visits,
                    }],
                }
            })
        })
        .map_err(|err| format!("failed to parse {}: {err}", path.display()))
        .and_then(normalize_engine_profiles_settings)
}

fn load_legacy_engine_profile_settings(app_handle: &AppHandle) -> Result<EngineProfilesSettingsDto, String> {
    let legacy_path = legacy_engine_profile_path()?;
    match fs::read_to_string(&legacy_path) {
        Ok(contents) => {
            let settings = parse_engine_profiles_settings(&contents, &legacy_path)?;
            let path = engine_profile_path(app_handle)?;
            let json = serde_json::to_string_pretty(&settings)
                .map_err(|err| format!("failed to serialize migrated engine profiles: {err}"))?;
            fs::write(&path, json).map_err(|err| {
                format!(
                    "failed to migrate engine profiles from {} to {}: {err}",
                    legacy_path.display(),
                    path.display()
                )
            })?;
            Ok(settings)
        }
        Err(err) if err.kind() == ErrorKind::NotFound => {
            normalize_engine_profiles_settings(default_engine_profiles_settings())
        }
        Err(err) => Err(format!("failed to read {}: {err}", legacy_path.display())),
    }
}

fn normalize_engine_profiles_settings(
    mut settings: EngineProfilesSettingsDto,
) -> Result<EngineProfilesSettingsDto, String> {
    if settings.profiles.is_empty() {
        settings.profiles.push(default_engine_profile_record());
    }

    let mut seen_ids = HashSet::new();
    let mut normalized_profiles = Vec::new();
    for mut record in settings.profiles {
        record.id = record.id.trim().to_string();
        if record.id.is_empty() {
            return Err("engine profile id is required".to_string());
        }
        if !seen_ids.insert(record.id.clone()) {
            return Err(format!("duplicate engine profile id: {}", record.id));
        }
        validate_engine_profile_settings(&EngineProfileSettingsDto {
            profile: record.profile.clone(),
            max_visits: record.max_visits,
        })?;
        normalized_profiles.push(record);
    }

    if !seen_ids.contains(DEFAULT_ENGINE_PROFILE_ID) {
        normalized_profiles.insert(0, default_engine_profile_record());
        seen_ids.insert(DEFAULT_ENGINE_PROFILE_ID.to_string());
    }

    settings.selected_profile_id = settings.selected_profile_id.trim().to_string();
    if !seen_ids.contains(&settings.selected_profile_id) {
        settings.selected_profile_id = DEFAULT_ENGINE_PROFILE_ID.to_string();
    }
    settings.profiles = normalized_profiles;
    Ok(settings)
}

fn validate_engine_profile_settings(settings: &EngineProfileSettingsDto) -> Result<(), String> {
    if settings.max_visits == 0 {
        return Err("max_visits must be greater than 0".to_string());
    }
    if settings.profile.name.trim().is_empty() {
        return Err("engine profile name is required".to_string());
    }
    Ok(())
}

fn default_engine_profiles_settings() -> EngineProfilesSettingsDto {
    EngineProfilesSettingsDto {
        selected_profile_id: DEFAULT_ENGINE_PROFILE_ID.to_string(),
        profiles: vec![default_engine_profile_record()],
    }
}

fn default_engine_profile_record() -> EngineProfileRecordDto {
    EngineProfileRecordDto {
        id: DEFAULT_ENGINE_PROFILE_ID.to_string(),
        profile: EngineProfileDto {
            name: "Local KataGo".to_string(),
            engine_path: String::new(),
            model_path: None,
            config_path: None,
            working_dir: None,
            backend: EngineBackend::KataGoAnalysis,
        },
        max_visits: 800,
    }
}

fn engine_profile_path(app_handle: &AppHandle) -> Result<PathBuf, String> {
    let dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|err| format!("failed to resolve app data directory for engine profiles: {err}"))?;
    fs::create_dir_all(&dir).map_err(|err| {
        format!(
            "failed to create engine profile directory {}: {err}",
            dir.display()
        )
    })?;
    Ok(dir.join(ENGINE_PROFILE_FILE))
}

fn legacy_engine_profile_path() -> Result<PathBuf, String> {
    std::env::current_dir()
        .map(|dir| dir.join(ENGINE_PROFILE_FILE))
        .map_err(|err| format!("failed to resolve current directory for legacy engine profile: {err}"))
}

fn app_preferences_path(app_handle: &AppHandle) -> Result<PathBuf, String> {
    let dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|err| format!("failed to resolve app data directory for app preferences: {err}"))?;
    fs::create_dir_all(&dir).map_err(|err| {
        format!(
            "failed to create app preferences directory {}: {err}",
            dir.display()
        )
    })?;
    Ok(dir.join(APP_PREFERENCES_FILE))
}

fn analysis_cache_db_path(app_handle: &AppHandle) -> Result<PathBuf, String> {
    let dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|err| format!("failed to resolve app data directory for analysis cache: {err}"))?;
    fs::create_dir_all(&dir).map_err(|err| {
        format!(
            "failed to create analysis cache directory {}: {err}",
            dir.display()
        )
    })?;
    Ok(dir.join(ANALYSIS_CACHE_DB_FILE))
}

fn open_analysis_cache_connection(path: &Path) -> Result<Connection, String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            format!(
                "failed to create analysis cache directory {}: {err}",
                parent.display()
            )
        })?;
    }
    let mut conn = Connection::open(path)
        .map_err(|err| format!("failed to open analysis cache database {}: {err}", path.display()))?;
    storage::apply_migrations(&mut conn).map_err(|err| {
        format!(
            "failed to migrate analysis cache database {}: {err}",
            path.display()
        )
    })?;
    Ok(conn)
}

#[allow(clippy::too_many_arguments)]
fn save_analysis_cache_at_path(
    path: &Path,
    game_key: String,
    sgf_hash: String,
    profile_id: Option<String>,
    engine_kind: String,
    source: String,
    move_count: u32,
    analyzed_move_count: u32,
    payload: Value,
) -> Result<SaveAnalysisCacheDto, String> {
    let conn = open_analysis_cache_connection(path)?;
    let input = AnalysisCacheSaveInput {
        game_key,
        sgf_hash,
        profile_id,
        engine_kind,
        source,
        move_count,
        analyzed_move_count,
        payload,
    };
    save_analysis_cache_in_connection(&conn, input)
}

fn get_analysis_cache_at_path(
    path: &Path,
    game_key: String,
    profile_id: Option<String>,
    engine_kind: Option<String>,
) -> Result<GetAnalysisCacheDto, String> {
    let conn = open_analysis_cache_connection(path)?;
    let record =
        latest_analysis_cache_record(&conn, &game_key, profile_id.as_deref(), engine_kind.as_deref())?;
    Ok(GetAnalysisCacheDto {
        status: if record.is_some() { "hit" } else { "miss" }.to_string(),
        record,
        error: None,
    })
}

fn delete_analysis_cache_at_path(
    path: &Path,
    game_key: String,
    profile_id: Option<String>,
    engine_kind: Option<String>,
) -> Result<DeleteAnalysisCacheDto, String> {
    let conn = open_analysis_cache_connection(path)?;
    let deleted = if profile_id.is_none() && engine_kind.is_none() {
        storage::delete_analysis_for_game(&conn, &game_key, None)
            .map_err(|err| format!("failed to delete analysis cache for {game_key}: {err}"))?
    } else {
        matching_cache_scope_ids(&conn, &game_key, profile_id.as_deref(), engine_kind.as_deref())?
            .into_iter()
            .map(|scope_id| {
                storage::delete_analysis_for_game(&conn, &game_key, Some(&scope_id))
                    .map_err(|err| format!("failed to delete analysis cache for {game_key}: {err}"))
            })
            .try_fold(0usize, |total, deleted| deleted.map(|deleted| total + deleted))?
    };
    Ok(DeleteAnalysisCacheDto { deleted })
}

struct AnalysisCacheSaveInput {
    game_key: String,
    sgf_hash: String,
    profile_id: Option<String>,
    engine_kind: String,
    source: String,
    move_count: u32,
    analyzed_move_count: u32,
    payload: Value,
}

#[derive(Debug, Clone)]
struct StoredAnalysisJob {
    id: String,
    engine_profile_id: Option<String>,
    model_hash: Option<String>,
    created_at: Option<String>,
    finished_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AnalysisPositionRawJson {
    record: Option<AnalysisCacheRecordDto>,
    frame: Option<AnalysisFrameDto>,
}

fn save_analysis_cache_in_connection(
    conn: &Connection,
    input: AnalysisCacheSaveInput,
) -> Result<SaveAnalysisCacheDto, String> {
    let frames = parse_cached_frames(&input.payload)?;
    let id = cache_record_id(
        &input.game_key,
        input.profile_id.as_deref(),
        Some(input.engine_kind.as_str()),
    );
    let now = cache_timestamp();
    let created_at = existing_analysis_job_created_at(conn, &id)?.unwrap_or_else(|| now.clone());
    let scope_id = cache_scope_id(input.profile_id.as_deref(), Some(input.engine_kind.as_str()));
    let record = AnalysisCacheRecordDto {
        id: id.clone(),
        game_key: input.game_key.clone(),
        sgf_hash: input.sgf_hash.clone(),
        profile_id: input.profile_id.clone(),
        engine_kind: Some(input.engine_kind.clone()),
        source: input.source.clone(),
        move_count: input.move_count,
        analyzed_move_count: input.analyzed_move_count,
        payload: input.payload,
        created_at: Some(created_at.clone()),
        updated_at: now.clone(),
    };
    let game = storage::GameMetadata {
        id: input.game_key.clone(),
        source: input.source,
        source_id: Some(input.sgf_hash.clone()),
        board_size: i64::from(infer_board_size(&frames)),
        komi: 7.5,
        black_name: None,
        white_name: None,
        result: None,
        sgf_hash: Some(input.sgf_hash),
    };
    let job = storage::AnalysisJob {
        id: id.clone(),
        game_id: Some(input.game_key.clone()),
        engine_profile_id: scope_id,
        model_hash: Some(input.engine_kind),
        visits: frames
            .iter()
            .map(|frame| i64::from(frame.visits))
            .max()
            .unwrap_or(0),
        status: "finished".to_string(),
        created_at: Some(created_at),
        finished_at: Some(now.clone()),
    };

    conn.execute_batch("SAVEPOINT save_analysis_cache")
        .map_err(|err| format!("failed to start analysis cache save: {err}"))?;
    let result = (|| -> Result<(), String> {
        storage::upsert_game_metadata(conn, &game)
            .map_err(|err| format!("failed to upsert cached game metadata: {err}"))?;
        if analysis_job_exists(conn, &id)? {
            storage::update_analysis_job(conn, &job)
                .map_err(|err| format!("failed to update analysis cache job: {err}"))?;
        } else {
            storage::create_analysis_job(conn, &job)
                .map_err(|err| format!("failed to create analysis cache job: {err}"))?;
        }
        conn.execute("DELETE FROM analysis_positions WHERE job_id = ?1", [&id])
            .map_err(|err| format!("failed to replace cached analysis positions: {err}"))?;
        save_cached_positions(conn, &record, &frames)?;
        Ok(())
    })();

    match result {
        Ok(()) => {
            if let Err(err) = conn.execute_batch("RELEASE SAVEPOINT save_analysis_cache") {
                let _ = conn.execute_batch(
                    "ROLLBACK TO SAVEPOINT save_analysis_cache;
                    RELEASE SAVEPOINT save_analysis_cache;",
                );
                return Err(format!("failed to commit analysis cache save: {err}"));
            }
        }
        Err(err) => {
            let _ = conn.execute_batch(
                "ROLLBACK TO SAVEPOINT save_analysis_cache;
                RELEASE SAVEPOINT save_analysis_cache;",
            );
            return Err(err);
        }
    }

    Ok(SaveAnalysisCacheDto {
        id,
        game_key: input.game_key,
        updated_at: now,
    })
}

fn parse_cached_frames(payload: &Value) -> Result<Vec<AnalysisFrameDto>, String> {
    let frames = payload
        .get("frames")
        .ok_or_else(|| "analysis cache payload must include frames".to_string())?;
    if !payload.get("problems").is_some_and(Value::is_array) {
        return Err("analysis cache payload must include problems".to_string());
    }
    serde_json::from_value(frames.clone())
        .map_err(|err| format!("failed to parse analysis cache payload frames: {err}"))
}

fn save_cached_positions(
    conn: &Connection,
    record: &AnalysisCacheRecordDto,
    frames: &[AnalysisFrameDto],
) -> Result<(), String> {
    let mut saved_turn_zero_record = false;
    for frame in frames {
        let raw = AnalysisPositionRawJson {
            record: if frame.turn == 0 {
                saved_turn_zero_record = true;
                Some(record.clone())
            } else {
                None
            },
            frame: Some(frame.clone()),
        };
        let position = analysis_position_from_frame(&record.id, frame, raw)?;
        storage::upsert_analysis_position(conn, &position)
            .map_err(|err| format!("failed to save cached analysis position {}: {err}", frame.turn))?;
    }

    if !saved_turn_zero_record {
        let raw = AnalysisPositionRawJson {
            record: Some(record.clone()),
            frame: None,
        };
        let position = storage::AnalysisPosition {
            id: format!("{}:turn:0", record.id),
            job_id: record.id.clone(),
            node_id: None,
            turn: 0,
            visits: 0,
            winrate_black: 0.0,
            score_mean_black: 0.0,
            score_stdev: None,
            policy_json: None,
            ownership_json: None,
            candidates_json: "[]".to_string(),
            raw_json: Some(serialize_raw_position(&raw)?),
        };
        storage::upsert_analysis_position(conn, &position)
            .map_err(|err| format!("failed to save cached analysis payload: {err}"))?;
    }
    Ok(())
}

fn analysis_position_from_frame(
    job_id: &str,
    frame: &AnalysisFrameDto,
    raw: AnalysisPositionRawJson,
) -> Result<storage::AnalysisPosition, String> {
    Ok(storage::AnalysisPosition {
        id: format!("{job_id}:turn:{}", frame.turn),
        job_id: job_id.to_string(),
        node_id: frame.node_id.map(|id| id.to_string()),
        turn: i64::from(frame.turn),
        visits: i64::from(frame.visits),
        winrate_black: f64::from(frame.winrate_black),
        score_mean_black: f64::from(frame.score_mean_black),
        score_stdev: frame.score_stdev.map(f64::from),
        policy_json: optional_json_string(&frame.policy)?,
        ownership_json: optional_json_string(&frame.ownership)?,
        candidates_json: serde_json::to_string(&frame.candidates)
            .map_err(|err| format!("failed to serialize cached candidate moves: {err}"))?,
        raw_json: Some(serialize_raw_position(&raw)?),
    })
}

fn optional_json_string<T: Serialize>(value: &Option<T>) -> Result<Option<String>, String> {
    value
        .as_ref()
        .map(serde_json::to_string)
        .transpose()
        .map_err(|err| format!("failed to serialize analysis cache JSON field: {err}"))
}

fn serialize_raw_position(raw: &AnalysisPositionRawJson) -> Result<String, String> {
    serde_json::to_string(raw)
        .map_err(|err| format!("failed to serialize cached raw analysis payload: {err}"))
}

fn latest_analysis_cache_record(
    conn: &Connection,
    game_key: &str,
    profile_id: Option<&str>,
    engine_kind: Option<&str>,
) -> Result<Option<AnalysisCacheRecordDto>, String> {
    for job in load_finished_analysis_jobs(conn, game_key)? {
        let record = analysis_cache_record_from_job(conn, game_key, &job)?;
        if cache_record_matches(&record, game_key, profile_id, engine_kind) {
            return Ok(Some(record));
        }
    }
    Ok(None)
}

fn matching_cache_scope_ids(
    conn: &Connection,
    game_key: &str,
    profile_id: Option<&str>,
    engine_kind: Option<&str>,
) -> Result<Vec<String>, String> {
    let mut scopes = HashSet::new();
    for job in load_finished_analysis_jobs(conn, game_key)? {
        let Some(scope_id) = job.engine_profile_id.clone() else {
            continue;
        };
        let record = analysis_cache_record_from_job(conn, game_key, &job)?;
        if cache_record_matches(&record, game_key, profile_id, engine_kind) {
            scopes.insert(scope_id);
        }
    }
    Ok(scopes.into_iter().collect())
}

fn load_finished_analysis_jobs(conn: &Connection, game_key: &str) -> Result<Vec<StoredAnalysisJob>, String> {
    let mut stmt = conn
        .prepare(
            "SELECT id, engine_profile_id, model_hash, created_at, finished_at
            FROM analysis_jobs
            WHERE game_id = ?1 AND status = 'finished'
            ORDER BY COALESCE(finished_at, created_at) DESC, created_at DESC, id DESC",
        )
        .map_err(|err| format!("failed to prepare analysis cache lookup: {err}"))?;
    let rows = stmt
        .query_map([game_key], |row| {
            Ok(StoredAnalysisJob {
                id: row.get(0)?,
                engine_profile_id: row.get(1)?,
                model_hash: row.get(2)?,
                created_at: row.get(3)?,
                finished_at: row.get(4)?,
            })
        })
        .map_err(|err| format!("failed to query analysis cache jobs: {err}"))?;
    rows.collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("failed to read analysis cache jobs: {err}"))
}

fn analysis_cache_record_from_job(
    conn: &Connection,
    game_key: &str,
    job: &StoredAnalysisJob,
) -> Result<AnalysisCacheRecordDto, String> {
    let positions = storage::load_analysis_positions(conn, &job.id)
        .map_err(|err| format!("failed to load cached analysis positions: {err}"))?;
    if let Some(record) = positions.iter().find_map(raw_record_from_position) {
        return Ok(record);
    }

    let sgf_hash = conn
        .query_row("SELECT sgf_hash FROM games WHERE id = ?1", [game_key], |row| {
            row.get::<_, Option<String>>(0)
        })
        .optional()
        .map_err(|err| format!("failed to load cached game metadata: {err}"))?
        .flatten()
        .unwrap_or_default();
    let frames = positions
        .iter()
        .filter_map(raw_frame_from_position)
        .collect::<Vec<_>>();
    let payload = serde_json::json!({
        "frames": frames,
        "problems": [],
    });
    Ok(AnalysisCacheRecordDto {
        id: job.id.clone(),
        game_key: game_key.to_string(),
        sgf_hash,
        profile_id: None,
        engine_kind: job.model_hash.clone(),
        source: job.model_hash.clone().unwrap_or_else(|| "katago".to_string()),
        move_count: positions
            .iter()
            .map(|position| position.turn as u32)
            .max()
            .unwrap_or(0),
        analyzed_move_count: positions.len() as u32,
        payload,
        created_at: job.created_at.clone(),
        updated_at: job
            .finished_at
            .clone()
            .or_else(|| job.created_at.clone())
            .unwrap_or_else(cache_timestamp),
    })
}

fn raw_record_from_position(position: &storage::AnalysisPosition) -> Option<AnalysisCacheRecordDto> {
    position
        .raw_json
        .as_deref()
        .and_then(|raw| serde_json::from_str::<AnalysisPositionRawJson>(raw).ok())
        .and_then(|raw| raw.record)
}

fn raw_frame_from_position(position: &storage::AnalysisPosition) -> Option<AnalysisFrameDto> {
    if let Some(frame) = position
        .raw_json
        .as_deref()
        .and_then(|raw| serde_json::from_str::<AnalysisPositionRawJson>(raw).ok())
        .and_then(|raw| raw.frame)
    {
        return Some(frame);
    }
    let candidates = serde_json::from_str::<Vec<CandidateMoveDto>>(&position.candidates_json).ok()?;
    let ownership = position
        .ownership_json
        .as_deref()
        .map(serde_json::from_str::<Vec<f32>>)
        .transpose()
        .ok()?;
    let policy = position
        .policy_json
        .as_deref()
        .map(serde_json::from_str::<Vec<f32>>)
        .transpose()
        .ok()?;
    Some(AnalysisFrameDto {
        job_id: Uuid::nil(),
        game_id: None,
        node_id: position
            .node_id
            .as_deref()
            .and_then(|id| Uuid::parse_str(id).ok()),
        turn: position.turn as u32,
        visits: position.visits as u32,
        winrate_black: position.winrate_black as f32,
        score_mean_black: position.score_mean_black as f32,
        score_stdev: position.score_stdev.map(|value| value as f32),
        candidates,
        ownership,
        policy,
    })
}

fn existing_analysis_job_created_at(conn: &Connection, job_id: &str) -> Result<Option<String>, String> {
    conn.query_row(
        "SELECT created_at FROM analysis_jobs WHERE id = ?1",
        [job_id],
        |row| row.get(0),
    )
    .optional()
    .map_err(|err| format!("failed to read existing analysis cache job: {err}"))
}

fn analysis_job_exists(conn: &Connection, job_id: &str) -> Result<bool, String> {
    let count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM analysis_jobs WHERE id = ?1",
            [job_id],
            |row| row.get(0),
        )
        .map_err(|err| format!("failed to inspect analysis cache job: {err}"))?;
    Ok(count > 0)
}

fn cache_scope_id(profile_id: Option<&str>, engine_kind: Option<&str>) -> Option<String> {
    if profile_id.is_none() && engine_kind.is_none() {
        return None;
    }
    let scope = serde_json::json!({
        "profile_id": profile_id,
        "engine_kind": engine_kind,
    });
    Some(format!(
        "cache-scope:{}",
        stable_hash_hex(&scope.to_string())
            .chars()
            .take(24)
            .collect::<String>()
    ))
}

fn infer_board_size(frames: &[AnalysisFrameDto]) -> u8 {
    frames
        .iter()
        .flat_map(|frame| [frame.ownership.as_ref(), frame.policy.as_ref()])
        .flatten()
        .find_map(|values| perfect_square_board_size(values.len()))
        .unwrap_or(19)
}

fn perfect_square_board_size(value_count: usize) -> Option<u8> {
    let size = (value_count as f64).sqrt() as usize;
    if (2..=25).contains(&size) && size * size == value_count {
        Some(size as u8)
    } else {
        None
    }
}

fn cache_record_matches(
    record: &AnalysisCacheRecordDto,
    game_key: &str,
    profile_id: Option<&str>,
    engine_kind: Option<&str>,
) -> bool {
    if record.game_key != game_key {
        return false;
    }
    if profile_id.is_some() && record.profile_id.as_deref() != profile_id {
        return false;
    }
    if engine_kind.is_some() && record.engine_kind.as_deref() != engine_kind {
        return false;
    }
    true
}

fn cache_record_id(game_key: &str, profile_id: Option<&str>, engine_kind: Option<&str>) -> String {
    format!(
        "cache:{}",
        stable_hash_hex(&format!(
            "{}\n{}\n{}",
            game_key,
            profile_id.unwrap_or(""),
            engine_kind.unwrap_or("")
        ))
        .chars()
        .take(24)
        .collect::<String>()
    )
}

fn cache_timestamp() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or_default();
    format_unix_seconds_utc(seconds)
}

fn stable_hash_hex(value: &str) -> String {
    const SEEDS: [u64; 4] = [
        0xcbf2_9ce4_8422_2325,
        0x8422_2325_cbf2_9ce4,
        0x9e37_79b9_7f4a_7c15,
        0x94d0_49bb_1331_11eb,
    ];
    SEEDS
        .iter()
        .map(|seed| format!("{:016x}", fnv1a64(value.as_bytes(), *seed)))
        .collect::<String>()
}

fn fnv1a64(bytes: &[u8], seed: u64) -> u64 {
    const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;
    let mut hash = seed;
    for byte in bytes {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(FNV_PRIME);
    }
    hash ^= bytes.len() as u64;
    hash.wrapping_mul(FNV_PRIME)
}

fn format_unix_seconds_utc(seconds: u64) -> String {
    let days = (seconds / 86_400) as i64;
    let seconds_of_day = seconds % 86_400;
    let (year, month, day) = civil_from_days(days);
    let hour = seconds_of_day / 3_600;
    let minute = (seconds_of_day % 3_600) / 60;
    let second = seconds_of_day % 60;
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z")
}

fn civil_from_days(days_since_unix_epoch: i64) -> (i64, u32, u32) {
    let days = days_since_unix_epoch + 719_468;
    let era = if days >= 0 { days } else { days - 146_096 } / 146_097;
    let day_of_era = days - era * 146_097;
    let year_of_era = (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_prime = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_prime + 2) / 5 + 1;
    let month = month_prime + if month_prime < 10 { 3 } else { -9 };
    let year = year + if month <= 2 { 1 } else { 0 };
    (year, month as u32, day as u32)
}

fn non_empty_path(path: String) -> Result<PathBuf, String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("path must not be empty".to_string());
    }
    Ok(PathBuf::from(trimmed))
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
        .manage(AnalysisJobRegistry::default())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            health,
            parse_sgf_summary,
            replay_sgf_positions,
            read_sgf_file,
            write_sgf_file,
            fake_analyze,
            classify_problems,
            katago_launch_plan,
            engine_asset_checks,
            load_app_preferences,
            save_app_preferences,
            load_engine_profile_settings,
            save_engine_profile_settings,
            load_engine_profiles_settings,
            save_engine_profiles_settings,
            compute_game_cache_key,
            get_analysis_cache,
            save_analysis_cache,
            delete_analysis_cache,
            katago_analyze_once,
            katago_analyze_game,
            katago_start_analyze_game,
            katago_cancel_analysis
        ])
        .run(tauri::generate_context!())
        .expect("failed to run LizzieYzy Next");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn write_sgf_file_preserves_original_text_after_validation() {
        let path = std::env::temp_dir().join(format!("lizzieyzy-save-{}.sgf", Uuid::new_v4()));
        let sgf_text =
            "(;GM[1]FF[4]SZ[19]KM[7.5]DT[2026-05-01]PB[Black]BR[1d]PW[White]WR[2d]AB[pd][dp]C[root comment]\n\
            ;B[dd]C[kept comment](;W[qq]C[main variation])(;W[pp]C[side variation]))";

        write_sgf_file(path.display().to_string(), sgf_text.to_string()).unwrap();

        let written = fs::read_to_string(&path).unwrap();
        let _ = fs::remove_file(&path);
        assert_eq!(written, sgf_text);
    }

    #[test]
    fn batch_analysis_query_requests_ownership_and_policy() {
        let job_id = Uuid::nil();
        let sgf_text = "(;GM[1]FF[4]SZ[19]KM[7.5];B[dd];W[qq])";

        let prepared = prepare_katago_batch_analysis(sgf_text, job_id, 64).unwrap();
        let query: serde_json::Value = serde_json::from_str(prepared.query_jsonl.trim()).unwrap();

        assert_eq!(query["includeOwnership"], true);
        assert_eq!(query["includePolicy"], true);
        assert_eq!(query["analyzeTurns"], serde_json::json!([0, 1, 2]));
    }

    #[test]
    fn analysis_cache_saves_and_restores_payload_from_sqlite() {
        let path = std::env::temp_dir().join(format!("lizzieyzy-analysis-cache-{}.sqlite3", Uuid::new_v4()));
        let sgf_text = "(;GM[1]FF[4]SZ[19]KM[7.5]PB[Black]PW[White];B[dd];W[qq])";
        let cache_key = compute_game_cache_key(sgf_text.to_string(), None).unwrap();
        let frames = fake_analyze(sgf_text.to_string()).unwrap();
        let problems = classify_problems(frames.clone());
        let payload = serde_json::json!({
            "frames": frames,
            "problems": problems,
        });

        let saved = save_analysis_cache_at_path(
            &path,
            cache_key.game_key.clone(),
            cache_key.sgf_hash.clone(),
            None,
            "fake".to_string(),
            "fake".to_string(),
            2,
            payload["frames"].as_array().unwrap().len() as u32,
            payload.clone(),
        )
        .unwrap();
        let lookup =
            get_analysis_cache_at_path(&path, cache_key.game_key.clone(), None, Some("fake".to_string()))
                .unwrap();

        assert_eq!(lookup.status, "hit");
        let record = lookup.record.unwrap();
        assert_eq!(record.id, saved.id);
        assert_eq!(record.game_key, cache_key.game_key);
        assert_eq!(record.sgf_hash, cache_key.sgf_hash);
        assert_eq!(record.engine_kind.as_deref(), Some("fake"));
        assert_eq!(
            record.payload["frames"].as_array().unwrap().len(),
            payload["frames"].as_array().unwrap().len()
        );
        assert_eq!(
            record.payload["problems"].as_array().unwrap().len(),
            payload["problems"].as_array().unwrap().len()
        );
        assert_eq!(record.payload["frames"][0]["turn"], serde_json::json!(0));

        let conn = open_analysis_cache_connection(&path).unwrap();
        let game_count: i64 = conn
            .query_row("SELECT COUNT(1) FROM games", [], |row| row.get(0))
            .unwrap();
        let job_count: i64 = conn
            .query_row("SELECT COUNT(1) FROM analysis_jobs", [], |row| row.get(0))
            .unwrap();
        let position_count: i64 = conn
            .query_row("SELECT COUNT(1) FROM analysis_positions", [], |row| row.get(0))
            .unwrap();
        let full_payload_rows: i64 = conn
            .query_row(
                "SELECT COUNT(1) FROM analysis_positions WHERE turn = 0 AND raw_json LIKE '%\"record\"%'",
                [],
                |row| row.get(0),
            )
            .unwrap();

        let _ = fs::remove_file(&path);
        assert_eq!(game_count, 1);
        assert_eq!(job_count, 1);
        assert_eq!(position_count, payload["frames"].as_array().unwrap().len() as i64);
        assert_eq!(full_payload_rows, 1);
    }
}
