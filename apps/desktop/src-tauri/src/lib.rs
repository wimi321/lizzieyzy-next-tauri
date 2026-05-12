use app_model::{
    AnalysisFrameDto, AppHealthDto, CandidateMoveDto, EngineBackend, EngineProfileDto, MoveVertex, NodeId,
    PointDto, PositionDto, ProviderError, ProviderErrorKind, ProviderFetchMethod, ProviderFetchRequest,
    ProviderFetchResult, ProviderGameMetadata, ProviderImportRequest, ProviderImportResult, ProviderKind,
    ReadboardSidecarProbeRequest, ReadboardSidecarProbeResult, ReadboardSidecarSyncSnapshotRequest,
    ReadboardSidecarSyncSnapshotResult, SgfTreeDto,
};
use engine_manager::{
    build_command_spec, check_assets, AnalysisBatchRunOptions, AnalysisCancelToken, AssetCheck, CommandSpec,
    EngineManagerError,
};
use go_core::ReadBoardLocalContext;
use katago_protocol::{AnalysisBatchQueryOptions, AnalysisQueryOptions};
use provider_core::{
    invalid_payload, invalid_request, invalid_url, timeout, transport_failed, ProviderResult,
    ProviderTransport,
};
use rusqlite::{Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, HashMap, HashSet};
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
const DEFAULT_PROVIDER_HTTP_TIMEOUT_MS: u64 = 30_000;
const RUNTIME_SMOKE_ENABLED_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE";
const RUNTIME_SMOKE_SGF_PATH_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH";
const RUNTIME_SMOKE_REPORT_PATH_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH";
const RUNTIME_SMOKE_EXPECTED_REPORT_PATH_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_EXPECTED_REPORT_PATH";
const RUNTIME_SMOKE_PHASE_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_PHASE";
const RUNTIME_SMOKE_KATAGO_PROFILE_NAME_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_PROFILE_NAME";
const RUNTIME_SMOKE_KATAGO_ENGINE_PATH_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ENGINE_PATH";
const RUNTIME_SMOKE_KATAGO_MODEL_PATH_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MODEL_PATH";
const RUNTIME_SMOKE_KATAGO_CONFIG_PATH_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CONFIG_PATH";
const RUNTIME_SMOKE_KATAGO_WORKING_DIR_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_WORKING_DIR";
const RUNTIME_SMOKE_KATAGO_MAX_VISITS_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_MAX_VISITS";
const RUNTIME_SMOKE_KATAGO_ONCE_TURN_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_ONCE_TURN";
const RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS";
const RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS";
const RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS";
const RUNTIME_SMOKE_KATAGO_RUN_GAME_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_GAME";
const RUNTIME_SMOKE_KATAGO_RUN_CANCEL_ENV: &str = "LIZZIEYZY_RUNTIME_SMOKE_KATAGO_RUN_CANCEL";

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AppendSgfMoveResultDto {
    sgf_text: String,
    new_node_id: NodeId,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EditSgfMoveResultDto {
    sgf_text: String,
    node_id: NodeId,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DeleteSgfNodeResultDto {
    sgf_text: String,
    parent_node_id: NodeId,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ReorderSgfVariationResultDto {
    sgf_text: String,
    node_id: NodeId,
    parent_node_id: NodeId,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SgfPropertyUpdateDto {
    key: String,
    values: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct UpdateSgfNodePropertiesResultDto {
    sgf_text: String,
    node_id: NodeId,
}

#[derive(Debug, Default)]
struct ReqwestProviderTransport;

impl ProviderTransport for ReqwestProviderTransport {
    fn fetch(&self, request: &ProviderFetchRequest) -> ProviderResult<ProviderFetchResult> {
        if !is_http_url(&request.url) {
            return Err(invalid_url(format!(
                "provider transport only supports http(s) URLs: {}",
                request.url
            )));
        }
        let client = reqwest::blocking::Client::builder()
            .redirect(reqwest::redirect::Policy::limited(10))
            .build()
            .map_err(map_reqwest_error)?;
        let method = match request.method {
            ProviderFetchMethod::Get => reqwest::Method::GET,
            ProviderFetchMethod::Post => reqwest::Method::POST,
        };
        let mut builder = client
            .request(method, &request.url)
            .timeout(Duration::from_millis(
                request.timeout_ms.unwrap_or(DEFAULT_PROVIDER_HTTP_TIMEOUT_MS),
            ));
        for (name, value) in &request.headers {
            builder = builder.header(
                reqwest::header::HeaderName::from_bytes(name.as_bytes()).map_err(|err| {
                    invalid_request(format!("invalid provider request header `{name}`: {err}"))
                })?,
                reqwest::header::HeaderValue::from_str(value).map_err(|err| {
                    invalid_request(format!(
                        "invalid provider request header value for `{name}`: {err}"
                    ))
                })?,
            );
        }
        if let Some(body) = &request.body {
            builder = builder.body(body.clone());
        }

        let response = builder.send().map_err(map_reqwest_error)?;
        let url = response.url().to_string();
        let status_code = response.status().as_u16();
        let headers = response_headers(response.headers());
        let content_type = headers
            .iter()
            .find(|(name, _)| name.eq_ignore_ascii_case("content-type"))
            .map(|(_, value)| value.clone());
        let payload = response.text().map_err(map_reqwest_error)?;

        Ok(ProviderFetchResult {
            provider: request.provider,
            url,
            status_code,
            payload,
            headers,
            content_type,
            metadata: ProviderGameMetadata {
                source_url: request.source_url.clone(),
                request_url: Some(request.url.clone()),
                source_id: request.source_id.clone(),
                ..ProviderGameMetadata::default()
            },
            warnings: Vec::new(),
        })
    }
}

fn map_reqwest_error(error: reqwest::Error) -> ProviderError {
    if error.is_timeout() {
        return timeout(format!("provider request timed out: {error}"));
    }
    if error.is_builder() || error.is_request() {
        return invalid_request(format!("provider request could not be built: {error}"));
    }
    transport_failed(format!("provider request failed: {error}"))
}

fn response_headers(headers: &reqwest::header::HeaderMap) -> BTreeMap<String, String> {
    headers
        .iter()
        .filter_map(|(name, value)| {
            value
                .to_str()
                .ok()
                .map(|value| (name.as_str().to_string(), value.to_string()))
        })
        .collect()
}

fn prepare_yike_fetch_request(mut request: ProviderFetchRequest) -> ProviderFetchRequest {
    let signature = provider_yike::YikeRequestSignature::now();
    let signed_headers = provider_yike::signed_headers(signature.current_time_millis, signature.nonce);
    for (name, value) in signed_headers {
        insert_header_if_missing(&mut request.headers, &name, value);
    }
    request
}

fn fetch_yike_with_transport<T: ProviderTransport + ?Sized>(
    request: ProviderFetchRequest,
    transport: &T,
) -> ProviderResult<ProviderFetchResult> {
    let result = transport.fetch(&prepare_yike_fetch_request(request))?;
    ensure_provider_http_success(&result, "Yike provider fetch failed")?;
    validate_yike_fetch_payload(&result)?;
    Ok(result)
}

fn validate_yike_fetch_payload(result: &ProviderFetchResult) -> ProviderResult<()> {
    let url = result.url.to_ascii_lowercase();
    let request_url = result
        .metadata
        .request_url
        .as_deref()
        .unwrap_or_default()
        .to_ascii_lowercase();
    if url.contains("/golive/list") || request_url.contains("/golive/list") {
        provider_yike::parse_live_list_json(&result.payload).map(|_| ())
    } else if url.contains("/golives/")
        || url.contains("/golive/dtl")
        || request_url.contains("/golives/")
        || request_url.contains("/golive/dtl")
    {
        provider_yike::parse_live_detail_json(&result.payload).map(|_| ())
    } else {
        Err(invalid_payload(format!(
            "unsupported Yike fetch response URL for runtime validation: {}",
            result.url
        )))
    }
}

fn prepare_fox_http_fetch_request(mut request: ProviderFetchRequest) -> ProviderFetchRequest {
    insert_header_if_missing(
        &mut request.headers,
        "User-Agent",
        provider_fox::FOX_MOBILE_USER_AGENT.to_string(),
    );
    request
}

fn fetch_fox_with_transport<T: ProviderTransport + ?Sized>(
    request: ProviderFetchRequest,
    transport: &T,
) -> ProviderResult<ProviderFetchResult> {
    if is_http_url(&request.url) {
        let mut result = transport.fetch(&prepare_fox_http_fetch_request(request))?;
        ensure_provider_http_success(&result, "Fox provider fetch failed")?;
        result.warnings.push(
            "Fox HTTP URL fetched directly; provider command normalization was not applied.".to_string(),
        );
        return Ok(result);
    }
    provider_fox::fetch_command(&request.url, transport)
}

fn ensure_provider_http_success(result: &ProviderFetchResult, context: &str) -> ProviderResult<()> {
    if !(200..400).contains(&result.status_code) {
        return Err(transport_failed(format!(
            "{context}: HTTP {} for {}",
            result.status_code, result.url
        )));
    }
    Ok(())
}

fn insert_header_if_missing(headers: &mut BTreeMap<String, String>, name: &str, value: String) {
    if !headers.keys().any(|key| key.eq_ignore_ascii_case(name)) {
        headers.insert(name.to_string(), value);
    }
}

fn is_http_url(url: &str) -> bool {
    reqwest::Url::parse(url)
        .map(|url| matches!(url.scheme(), "http" | "https"))
        .unwrap_or(false)
}

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

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct LegacyConfigMigrationPreviewDto {
    source_path: String,
    preferences: Option<AppPreferencesDto>,
    engine_profiles: Option<EngineProfilesSettingsDto>,
    migrated_fields: Vec<String>,
    warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct LegacyConfigMigrationApplyDto {
    source_path: String,
    preferences_written: bool,
    engine_profiles_written: bool,
    written_paths: Vec<String>,
    migrated_fields: Vec<String>,
    warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeAssetPathDto {
    label: String,
    kind: String,
    source: String,
    path: String,
    required: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeAssetLayoutDto {
    resource_dir: Option<String>,
    dev_roots: Vec<String>,
    release_roots: Vec<String>,
    candidates: Vec<RuntimeAssetPathDto>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeAssetMissingWarningDto {
    label: String,
    kind: String,
    source: String,
    path: String,
    message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeAssetValidationDto {
    layout: RuntimeAssetLayoutDto,
    missing: Vec<RuntimeAssetMissingWarningDto>,
    warnings: Vec<String>,
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

#[derive(Debug, Clone, Serialize)]
struct RuntimeSmokeConfigDto {
    enabled: bool,
    sgf_path: Option<String>,
    report_path: Option<String>,
    expected_report_path: Option<String>,
    phase: Option<String>,
    katago: Option<RuntimeSmokeKatagoConfigDto>,
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeSmokeKatagoConfigDto {
    profile: EngineProfileDto,
    max_visits: Option<u32>,
    once_turn: Option<u32>,
    game_max_visits: Option<u32>,
    cancel_max_visits: Option<u32>,
    cancel_delay_ms: Option<u32>,
    run_game: Option<bool>,
    run_cancel: Option<bool>,
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
fn runtime_smoke_report(report_path: String, report_json: String) -> Result<(), String> {
    if !env_truthy(RUNTIME_SMOKE_ENABLED_ENV) {
        return Err(format!("{RUNTIME_SMOKE_ENABLED_ENV} is not enabled"));
    }

    let expected_path = std::env::var(RUNTIME_SMOKE_REPORT_PATH_ENV)
        .map_err(|_| format!("{RUNTIME_SMOKE_REPORT_PATH_ENV} is not set"))?;
    if expected_path != report_path {
        return Err(format!(
            "{RUNTIME_SMOKE_REPORT_PATH_ENV} does not match report_path"
        ));
    }

    let path = PathBuf::from(&report_path);
    if let Some(parent) = path.parent().filter(|parent| !parent.as_os_str().is_empty()) {
        fs::create_dir_all(parent).map_err(|err| format!("failed to create {}: {err}", parent.display()))?;
    }
    fs::write(&path, report_json).map_err(|err| format!("failed to write {}: {err}", path.display()))
}

#[tauri::command]
fn runtime_smoke_config() -> RuntimeSmokeConfigDto {
    RuntimeSmokeConfigDto {
        enabled: env_truthy(RUNTIME_SMOKE_ENABLED_ENV),
        sgf_path: non_empty_env(RUNTIME_SMOKE_SGF_PATH_ENV),
        report_path: non_empty_env(RUNTIME_SMOKE_REPORT_PATH_ENV),
        expected_report_path: non_empty_env(RUNTIME_SMOKE_EXPECTED_REPORT_PATH_ENV),
        phase: non_empty_env(RUNTIME_SMOKE_PHASE_ENV),
        katago: runtime_smoke_katago_config(),
    }
}

fn runtime_smoke_katago_config() -> Option<RuntimeSmokeKatagoConfigDto> {
    let engine_path = non_empty_env(RUNTIME_SMOKE_KATAGO_ENGINE_PATH_ENV)?;
    Some(RuntimeSmokeKatagoConfigDto {
        profile: EngineProfileDto {
            name: non_empty_env(RUNTIME_SMOKE_KATAGO_PROFILE_NAME_ENV)
                .unwrap_or_else(|| "Runtime Smoke KataGo".to_string()),
            engine_path,
            model_path: non_empty_env(RUNTIME_SMOKE_KATAGO_MODEL_PATH_ENV),
            config_path: non_empty_env(RUNTIME_SMOKE_KATAGO_CONFIG_PATH_ENV),
            working_dir: non_empty_env(RUNTIME_SMOKE_KATAGO_WORKING_DIR_ENV),
            backend: EngineBackend::KataGoAnalysis,
        },
        max_visits: env_u32(RUNTIME_SMOKE_KATAGO_MAX_VISITS_ENV),
        once_turn: env_u32(RUNTIME_SMOKE_KATAGO_ONCE_TURN_ENV),
        game_max_visits: env_u32(RUNTIME_SMOKE_KATAGO_GAME_MAX_VISITS_ENV),
        cancel_max_visits: env_u32(RUNTIME_SMOKE_KATAGO_CANCEL_MAX_VISITS_ENV),
        cancel_delay_ms: env_u32(RUNTIME_SMOKE_KATAGO_CANCEL_DELAY_MS_ENV),
        run_game: env_bool(RUNTIME_SMOKE_KATAGO_RUN_GAME_ENV),
        run_cancel: env_bool(RUNTIME_SMOKE_KATAGO_RUN_CANCEL_ENV),
    })
}

fn env_truthy(name: &str) -> bool {
    std::env::var(name)
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(false)
}

fn non_empty_env(name: &str) -> Option<String> {
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn env_u32(name: &str) -> Option<u32> {
    non_empty_env(name).and_then(|value| value.parse::<u32>().ok())
}

fn env_bool(name: &str) -> Option<bool> {
    let value = non_empty_env(name)?;
    match value.trim().to_ascii_lowercase().as_str() {
        "1" | "true" | "yes" | "on" => Some(true),
        "0" | "false" | "no" | "off" => Some(false),
        _ => None,
    }
}

#[tauri::command]
fn parse_sgf_summary(sgf_text: String) -> Result<app_model::GameDto, String> {
    let document = sgf::parse_sgf(&sgf_text).map_err(|err| err.to_string())?;
    Ok(sgf::to_game_dto(document))
}

#[tauri::command]
fn parse_sgf_tree(sgf_text: String) -> Result<Option<SgfTreeDto>, String> {
    let document = sgf::parse_sgf(&sgf_text).map_err(|err| err.to_string())?;
    sgf::to_sgf_tree_dto(&document).map_err(|err| err.to_string())
}

#[tauri::command]
fn provider_parse_yike_url(raw_url: String) -> Result<provider_yike::YikeUrlDescriptor, ProviderError> {
    provider_yike::parse_yike_url(&raw_url)
}

#[tauri::command]
fn provider_import_from_payload(
    request: ProviderImportRequest,
) -> Result<ProviderImportResult, ProviderError> {
    let result = match request.provider {
        ProviderKind::Yike => provider_yike::import_payload(request),
        ProviderKind::Fox => provider_fox::import_payload(request),
    }?;
    enrich_provider_import_result(result)
}

#[tauri::command]
fn provider_fetch_yike(request: ProviderFetchRequest) -> Result<ProviderFetchResult, ProviderError> {
    validate_provider_fetch_request(&request, ProviderKind::Yike, "provider_fetch_yike")?;
    let transport = ReqwestProviderTransport;
    fetch_yike_with_transport(request, &transport)
}

#[tauri::command]
fn provider_fetch_fox(request: ProviderFetchRequest) -> Result<ProviderFetchResult, ProviderError> {
    validate_provider_fetch_request(&request, ProviderKind::Fox, "provider_fetch_fox")?;
    let transport = ReqwestProviderTransport;
    fetch_fox_with_transport(request, &transport)
}

#[tauri::command]
fn readboard_sidecar_probe(
    request: ReadboardSidecarProbeRequest,
) -> Result<ReadboardSidecarProbeResult, ProviderError> {
    validate_timeout_ms(request.timeout_ms, "readboard_sidecar_probe")?;
    Ok(readboard_sidecar::probe_readboard_sidecar(
        &request,
        &readboard_sidecar::ReadboardSidecarOptions::default(),
    )
    .into_dto())
}

#[tauri::command]
fn readboard_sidecar_sync_snapshot(
    request: ReadboardSidecarSyncSnapshotRequest,
) -> Result<ReadboardSidecarSyncSnapshotResult, ProviderError> {
    validate_timeout_ms(request.timeout_ms, "readboard_sidecar_sync_snapshot")?;
    if request
        .image_path
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
        && request
            .image_base64
            .as_deref()
            .is_none_or(|value| value.trim().is_empty())
        && request
            .sgf_text
            .as_deref()
            .is_none_or(|value| value.trim().is_empty())
    {
        return Err(ProviderError {
            kind: ProviderErrorKind::InvalidRequest,
            message: "readboard_sidecar_sync_snapshot requires image_path, image_base64, or sgf_text"
                .to_string(),
        });
    }
    if let Some(protocol_line) = request
        .sgf_text
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        let parsed = readboard_sidecar::parse_snapshot_line(protocol_line).map_err(readboard_error)?;
        let local = ReadBoardLocalContext {
            board_size: parsed.snapshot.board_size,
            positions: Vec::new(),
            current_index: 0,
            main_end_index: 0,
        };
        let first_sync = request
            .metadata
            .get("first_sync")
            .map(|value| value != "false" && value != "0")
            .unwrap_or(true);
        return readboard_sidecar::sync_snapshot_line(&request, protocol_line, first_sync, local)
            .map(|outcome| outcome.into_dto())
            .map_err(readboard_error);
    }
    Err(ProviderError {
        kind: ProviderErrorKind::RuntimeUnavailable,
        message: "readboard image OCR runtime is unavailable; provide sgf_text as an offline snapshot protocol line"
            .to_string(),
    })
}

#[tauri::command]
fn replay_sgf_positions(sgf_text: String) -> Result<Vec<PositionDto>, String> {
    sgf::replay_sgf_positions(&sgf_text).map_err(|err| err.to_string())
}

#[tauri::command]
fn update_sgf_node_comment(
    sgf_text: String,
    node_id: NodeId,
    comment: Option<String>,
) -> Result<String, String> {
    sgf::update_sgf_node_comment(&sgf_text, node_id, comment.as_deref()).map_err(|err| err.to_string())
}

#[tauri::command]
fn update_sgf_node_properties(
    sgf_text: String,
    node_id: NodeId,
    updates: Vec<SgfPropertyUpdateDto>,
) -> Result<UpdateSgfNodePropertiesResultDto, String> {
    let updates = updates
        .into_iter()
        .map(|update| sgf::SgfPropertyUpdate {
            key: update.key,
            values: update.values,
        })
        .collect();
    let result =
        sgf::update_sgf_node_properties(&sgf_text, node_id, updates).map_err(|err| err.to_string())?;
    Ok(UpdateSgfNodePropertiesResultDto {
        sgf_text: result.sgf_text,
        node_id: result.node_id,
    })
}

#[tauri::command]
fn append_sgf_move(
    sgf_text: String,
    parent_node_id: NodeId,
    color: app_model::PlayerColor,
    vertex: MoveVertex,
) -> Result<AppendSgfMoveResultDto, String> {
    let result =
        sgf::append_sgf_move(&sgf_text, parent_node_id, color, vertex).map_err(|err| err.to_string())?;
    Ok(AppendSgfMoveResultDto {
        sgf_text: result.sgf_text,
        new_node_id: result.new_node_id,
    })
}

#[tauri::command]
fn edit_sgf_move(
    sgf_text: String,
    node_id: NodeId,
    color: app_model::PlayerColor,
    vertex: MoveVertex,
) -> Result<EditSgfMoveResultDto, String> {
    let result = sgf::edit_sgf_move(&sgf_text, node_id, color, vertex).map_err(|err| err.to_string())?;
    Ok(EditSgfMoveResultDto {
        sgf_text: result.sgf_text,
        node_id: result.node_id,
    })
}

#[tauri::command]
fn delete_sgf_node(sgf_text: String, node_id: NodeId) -> Result<DeleteSgfNodeResultDto, String> {
    let result = sgf::delete_sgf_node(&sgf_text, node_id).map_err(|err| err.to_string())?;
    Ok(DeleteSgfNodeResultDto {
        sgf_text: result.sgf_text,
        parent_node_id: result.parent_node_id,
    })
}

#[tauri::command]
fn reorder_sgf_variation(
    sgf_text: String,
    node_id: NodeId,
    target_index: usize,
) -> Result<ReorderSgfVariationResultDto, String> {
    let result =
        sgf::reorder_sgf_variation(&sgf_text, node_id, target_index).map_err(|err| err.to_string())?;
    Ok(ReorderSgfVariationResultDto {
        sgf_text: result.sgf_text,
        node_id: result.node_id,
        parent_node_id: result.parent_node_id,
    })
}

#[tauri::command]
fn replay_sgf_position_at_node(sgf_text: String, node_id: NodeId) -> Result<PositionDto, String> {
    sgf::replay_sgf_position_at_node(&sgf_text, node_id).map_err(|err| err.to_string())
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
fn preview_legacy_config_migration(path: String) -> Result<LegacyConfigMigrationPreviewDto, String> {
    preview_legacy_config_migration_from_path(&non_empty_path(path)?)
}

#[tauri::command]
fn apply_legacy_config_migration(
    app_handle: AppHandle,
    path: String,
) -> Result<LegacyConfigMigrationApplyDto, String> {
    let source_path = non_empty_path(path)?;
    let preview = preview_legacy_config_migration_from_path(&source_path)?;
    let mut written_paths = Vec::new();
    let preferences_written = if let Some(preferences) = preview.preferences.clone() {
        let preferences_path = app_preferences_path(&app_handle)?;
        let existing = load_app_preferences_at_path(&preferences_path)?;
        let merged = merge_migrated_preferences(existing, preferences, &preview.migrated_fields);
        save_app_preferences_at_path(&preferences_path, merged)?;
        written_paths.push(preferences_path.display().to_string());
        true
    } else {
        false
    };
    let engine_profiles_written = if let Some(engine_profiles) = preview.engine_profiles.clone() {
        let engine_profiles_path = engine_profile_path(&app_handle)?;
        let existing = load_engine_profiles_settings_at_path(&engine_profiles_path)?;
        let merged = merge_migrated_engine_profiles(existing, engine_profiles, &preview.migrated_fields);
        save_engine_profiles_settings_at_path(&engine_profiles_path, merged)?;
        written_paths.push(engine_profiles_path.display().to_string());
        true
    } else {
        false
    };

    Ok(LegacyConfigMigrationApplyDto {
        source_path: preview.source_path,
        preferences_written,
        engine_profiles_written,
        written_paths,
        migrated_fields: preview.migrated_fields,
        warnings: preview.warnings,
    })
}

#[tauri::command]
fn resolve_runtime_asset_layout(app_handle: AppHandle) -> RuntimeAssetLayoutDto {
    resolve_runtime_asset_layout_for_paths(
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
        app_handle.path().resource_dir().ok(),
    )
}

#[tauri::command]
fn validate_runtime_asset_layout(app_handle: AppHandle) -> RuntimeAssetValidationDto {
    validate_runtime_asset_layout_from_layout(resolve_runtime_asset_layout(app_handle))
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
    let path = app_preferences_path(&app_handle)?;
    save_app_preferences_at_path(&path, preferences)
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
    let path = engine_profile_path(&app_handle)?;
    save_engine_profiles_settings_at_path(&path, settings)
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

fn save_app_preferences_at_path(
    path: &Path,
    preferences: AppPreferencesDto,
) -> Result<AppPreferencesDto, String> {
    let preferences = normalize_app_preferences(preferences);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            format!(
                "failed to create app preferences directory {}: {err}",
                parent.display()
            )
        })?;
    }
    let json = serde_json::to_string_pretty(&preferences)
        .map_err(|err| format!("failed to serialize app preferences: {err}"))?;
    fs::write(path, json).map_err(|err| format!("failed to write {}: {err}", path.display()))?;
    Ok(preferences)
}

fn load_app_preferences_at_path(path: &Path) -> Result<AppPreferencesDto, String> {
    match fs::read_to_string(path) {
        Ok(contents) => serde_json::from_str::<AppPreferencesDto>(&contents)
            .map_err(|err| format!("failed to parse {}: {err}", path.display()))
            .map(normalize_app_preferences),
        Err(err) if err.kind() == ErrorKind::NotFound => Ok(default_app_preferences()),
        Err(err) => Err(format!("failed to read {}: {err}", path.display())),
    }
}

#[cfg(test)]
fn apply_legacy_config_migration_to_paths(
    source_path: &Path,
    preferences_path: &Path,
    engine_profiles_path: &Path,
) -> Result<LegacyConfigMigrationApplyDto, String> {
    let preview = preview_legacy_config_migration_from_path(source_path)?;
    let mut written_paths = Vec::new();
    let preferences_written = if let Some(preferences) = preview.preferences.clone() {
        let existing = load_app_preferences_at_path(preferences_path)?;
        let merged = merge_migrated_preferences(existing, preferences, &preview.migrated_fields);
        save_app_preferences_at_path(preferences_path, merged)?;
        written_paths.push(preferences_path.display().to_string());
        true
    } else {
        false
    };
    let engine_profiles_written = if let Some(engine_profiles) = preview.engine_profiles.clone() {
        let existing = load_engine_profiles_settings_at_path(engine_profiles_path)?;
        let merged = merge_migrated_engine_profiles(existing, engine_profiles, &preview.migrated_fields);
        save_engine_profiles_settings_at_path(engine_profiles_path, merged)?;
        written_paths.push(engine_profiles_path.display().to_string());
        true
    } else {
        false
    };

    Ok(LegacyConfigMigrationApplyDto {
        source_path: preview.source_path,
        preferences_written,
        engine_profiles_written,
        written_paths,
        migrated_fields: preview.migrated_fields,
        warnings: preview.warnings,
    })
}

fn merge_migrated_preferences(
    mut existing: AppPreferencesDto,
    migrated: AppPreferencesDto,
    migrated_fields: &[String],
) -> AppPreferencesDto {
    if has_migrated_field(migrated_fields, "showCandidates") {
        existing.show_candidates = migrated.show_candidates;
    }
    if has_migrated_field(migrated_fields, "candidateLimit") {
        existing.candidate_limit = migrated.candidate_limit;
    }
    if has_migrated_field(migrated_fields, "defaultMaxVisits") {
        existing.default_max_visits = migrated.default_max_visits;
    }
    if has_migrated_field(migrated_fields, "showOwnership") {
        existing.show_ownership = migrated.show_ownership;
    }
    if has_migrated_field(migrated_fields, "showPolicy") {
        existing.show_policy = migrated.show_policy;
    }
    if has_migrated_field(migrated_fields, "boardTheme") {
        existing.board_theme = migrated.board_theme;
    }
    normalize_app_preferences(existing)
}

fn merge_migrated_engine_profiles(
    mut existing: EngineProfilesSettingsDto,
    migrated: EngineProfilesSettingsDto,
    migrated_fields: &[String],
) -> EngineProfilesSettingsDto {
    let Some(migrated_default) = migrated
        .profiles
        .into_iter()
        .find(|record| record.id == DEFAULT_ENGINE_PROFILE_ID)
    else {
        return existing;
    };

    let existing_default = existing
        .profiles
        .iter_mut()
        .find(|record| record.id == DEFAULT_ENGINE_PROFILE_ID);
    if let Some(record) = existing_default {
        record.profile.name = migrated_default.profile.name;
        record.profile.backend = migrated_default.profile.backend;
        if !migrated_default.profile.engine_path.trim().is_empty() {
            record.profile.engine_path = migrated_default.profile.engine_path;
        }
        if migrated_default.profile.model_path.is_some() {
            record.profile.model_path = migrated_default.profile.model_path;
        }
        if migrated_default.profile.config_path.is_some() {
            record.profile.config_path = migrated_default.profile.config_path;
        }
        if has_migrated_field(migrated_fields, "defaultMaxVisits") {
            record.max_visits = migrated_default.max_visits;
        }
    } else {
        existing.profiles.insert(0, migrated_default);
    }
    existing.selected_profile_id = migrated.selected_profile_id;
    existing
}

fn has_migrated_field(migrated_fields: &[String], field: &str) -> bool {
    migrated_fields.iter().any(|value| value == field)
}

fn preview_legacy_config_migration_from_path(path: &Path) -> Result<LegacyConfigMigrationPreviewDto, String> {
    let contents = fs::read_to_string(path)
        .map_err(|err| format!("failed to read legacy config {}: {err}", path.display()))?;
    let root = parse_legacy_config_value(&contents, path)?;
    let mut warnings = Vec::new();
    let mut migrated_fields = Vec::new();
    let mut preferences = default_app_preferences();
    let mut touched_preferences = false;

    if let Some(value) =
        find_legacy_preference_value(&root, &["showCandidates", "show-candidates", "show-candidate"])
    {
        if let Some(parsed) = legacy_bool(value) {
            preferences.show_candidates = parsed;
            touched_preferences = true;
            migrated_fields.push("showCandidates".to_string());
        } else {
            warnings.push("legacy showCandidates value was not a boolean".to_string());
        }
    }
    if let Some(value) = find_legacy_preference_value(&root, &["candidateLimit", "maxAnalyzeTurns"]) {
        if let Some(parsed) = legacy_u32(value) {
            preferences.candidate_limit = parsed;
            touched_preferences = true;
            migrated_fields.push("candidateLimit".to_string());
        } else {
            warnings.push("legacy candidate limit value was not a positive integer".to_string());
        }
    }
    if let Some(value) = find_legacy_preference_value(&root, &["defaultMaxVisits", "maxVisits"]) {
        if let Some(parsed) = legacy_u32(value) {
            preferences.default_max_visits = parsed;
            touched_preferences = true;
            migrated_fields.push("defaultMaxVisits".to_string());
        } else {
            warnings.push("legacy max visits value was not a positive integer".to_string());
        }
    }
    if let Some(value) = find_legacy_preference_value(&root, &["showOwnership"]) {
        if let Some(parsed) = legacy_bool(value) {
            preferences.show_ownership = parsed;
            touched_preferences = true;
            migrated_fields.push("showOwnership".to_string());
        } else {
            warnings.push("legacy showOwnership value was not a boolean".to_string());
        }
    }
    if let Some(value) = find_legacy_preference_value(&root, &["showPolicy"]) {
        if let Some(parsed) = legacy_bool(value) {
            preferences.show_policy = parsed;
            touched_preferences = true;
            migrated_fields.push("showPolicy".to_string());
        } else {
            warnings.push("legacy showPolicy value was not a boolean".to_string());
        }
    }
    if let Some(value) = find_legacy_preference_value(&root, &["boardTheme", "theme"]) {
        if let Some(parsed) = legacy_string(value) {
            preferences.board_theme = parsed;
            touched_preferences = true;
            migrated_fields.push("boardTheme".to_string());
        } else {
            warnings.push("legacy board theme value was not a string".to_string());
        }
    }

    let engine_path = find_legacy_engine_value(
        &root,
        &[
            "engineCommand",
            "engine-command",
            "enginePath",
            "engine-path",
            "katagoCommand",
            "katago-command",
            "katagoPath",
            "katago-path",
            "leelazCommand",
            "leelaz-command",
            "leelazPath",
            "leelaz-path",
        ],
        &[
            "engineCommand",
            "engine-command",
            "enginePath",
            "engine-path",
            "katagoCommand",
            "katago-command",
            "katagoPath",
            "katago-path",
            "leelazCommand",
            "leelaz-command",
            "leelazPath",
            "leelaz-path",
            "command",
            "path",
        ],
    )
    .and_then(legacy_string);
    let model_path = find_legacy_engine_value(
        &root,
        &[
            "modelPath",
            "model-path",
            "katagoModelPath",
            "katago-model-path",
            "leelazModelPath",
            "leelaz-model-path",
        ],
        &[
            "modelPath",
            "model-path",
            "katagoModelPath",
            "katago-model-path",
            "leelazModelPath",
            "leelaz-model-path",
            "model",
        ],
    )
    .and_then(legacy_string);
    let config_path = find_legacy_engine_value(
        &root,
        &[
            "configPath",
            "config-path",
            "gtpConfig",
            "gtp-config",
            "katagoConfigPath",
            "katago-config-path",
        ],
        &[
            "configPath",
            "config-path",
            "gtpConfig",
            "gtp-config",
            "katagoConfigPath",
            "katago-config-path",
            "config",
        ],
    )
    .and_then(legacy_string);
    let mut profile_max_visits = preferences.default_max_visits;
    if let Some(value) = find_legacy_engine_value(
        &root,
        &["defaultMaxVisits", "maxVisits"],
        &["maxVisits", "defaultMaxVisits"],
    )
    .or_else(|| find_legacy_preference_value(&root, &["defaultMaxVisits", "maxVisits"]))
    .and_then(legacy_u32)
    {
        profile_max_visits = value;
    }
    let engine_profiles = if engine_path
        .as_deref()
        .is_some_and(|value| !value.trim().is_empty())
        || model_path
            .as_deref()
            .is_some_and(|value| !value.trim().is_empty())
        || config_path
            .as_deref()
            .is_some_and(|value| !value.trim().is_empty())
    {
        migrated_fields.push("engineProfile".to_string());
        Some(EngineProfilesSettingsDto {
            selected_profile_id: DEFAULT_ENGINE_PROFILE_ID.to_string(),
            profiles: vec![EngineProfileRecordDto {
                id: DEFAULT_ENGINE_PROFILE_ID.to_string(),
                profile: EngineProfileDto {
                    name: "Migrated KataGo".to_string(),
                    engine_path: engine_path.unwrap_or_default(),
                    model_path: non_empty_legacy_string(model_path),
                    config_path: non_empty_legacy_string(config_path),
                    working_dir: None,
                    backend: EngineBackend::KataGoAnalysis,
                },
                max_visits: profile_max_visits,
            }],
        })
    } else {
        None
    };

    let preferences = if touched_preferences {
        Some(normalize_app_preferences(preferences))
    } else {
        None
    };
    append_unsupported_legacy_warnings(&root, &mut warnings);
    if preferences.is_none() && engine_profiles.is_none() {
        warnings.push("no supported legacy config fields were found".to_string());
    }
    let engine_profiles = engine_profiles
        .map(normalize_engine_profiles_settings)
        .transpose()?;

    Ok(LegacyConfigMigrationPreviewDto {
        source_path: path.display().to_string(),
        preferences,
        engine_profiles,
        migrated_fields,
        warnings,
    })
}

fn parse_legacy_config_value(contents: &str, path: &Path) -> Result<Value, String> {
    match serde_json::from_str(contents).or_else(|_| serde_json::from_str(&sanitize_jsonish_config(contents))) {
        Ok(value) => Ok(value),
        Err(json_err) if looks_like_json_config(contents) => Err(format!(
            "failed to parse legacy config {} as JSON-ish config: {json_err}",
            path.display()
        )),
        Err(json_err) => parse_legacy_properties_config(contents).map_err(|properties_err| {
            format!(
                "failed to parse legacy config {} as JSON-ish config or Java properties: {json_err}; {properties_err}",
                path.display()
            )
        }),
    }
}

fn looks_like_json_config(contents: &str) -> bool {
    contents
        .trim_start_matches('\u{feff}')
        .trim_start()
        .starts_with(['{', '['])
}

fn parse_legacy_properties_config(contents: &str) -> Result<Value, String> {
    let mut map = serde_json::Map::new();
    let mut parsed_entries = 0usize;

    for (index, raw_line) in contents.lines().enumerate() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with('!') {
            continue;
        }
        let Some(separator) = find_legacy_property_separator(line) else {
            return Err(format!(
                "line {} is not a supported key=value Java properties entry",
                index + 1
            ));
        };
        let key = unescape_legacy_property(line[..separator].trim());
        if key.is_empty() {
            return Err(format!("line {} has an empty Java properties key", index + 1));
        }
        let value_start = separator + line[separator..].chars().next().map(char::len_utf8).unwrap_or(1);
        let value = unescape_legacy_property(line[value_start..].trim());
        insert_legacy_property_value(&mut map, &key, Value::String(value));
        parsed_entries += 1;
    }

    if parsed_entries == 0 {
        return Err("no Java properties entries were found".to_string());
    }

    Ok(Value::Object(map))
}

fn find_legacy_property_separator(line: &str) -> Option<usize> {
    let mut escaped = false;
    for (index, ch) in line.char_indices() {
        if escaped {
            escaped = false;
            continue;
        }
        if ch == '\\' {
            escaped = true;
            continue;
        }
        if ch == '=' || ch == ':' {
            return Some(index);
        }
    }
    None
}

fn unescape_legacy_property(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut chars = value.chars();
    while let Some(ch) = chars.next() {
        if ch != '\\' {
            output.push(ch);
            continue;
        }
        match chars.next() {
            Some('n') => output.push('\n'),
            Some('r') => output.push('\r'),
            Some('t') => output.push('\t'),
            Some(next @ ('\\' | ':' | '=' | '#' | '!' | ' ')) => output.push(next),
            Some(next) => {
                output.push('\\');
                output.push(next);
            }
            None => output.push('\\'),
        }
    }
    output
}

fn insert_legacy_property_value(map: &mut serde_json::Map<String, Value>, key: &str, value: Value) {
    let parts = key
        .split('.')
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>();
    if parts.is_empty() {
        return;
    }
    insert_legacy_property_parts(map, &parts, value);
}

fn insert_legacy_property_parts(map: &mut serde_json::Map<String, Value>, parts: &[&str], value: Value) {
    if parts.len() == 1 {
        map.insert(parts[0].to_string(), value);
        return;
    }

    let entry = map
        .entry(parts[0].to_string())
        .or_insert_with(|| Value::Object(serde_json::Map::new()));
    if !entry.is_object() {
        *entry = Value::Object(serde_json::Map::new());
    }
    if let Value::Object(nested) = entry {
        insert_legacy_property_parts(nested, &parts[1..], value);
    }
}

fn append_unsupported_legacy_warnings(root: &Value, warnings: &mut Vec<String>) {
    let Some(map) = root.as_object() else {
        return;
    };
    let top_level_keys = legacy_supported_top_level_keys();
    let nested_keys = legacy_supported_nested_keys();
    let known_containers = legacy_known_container_keys();

    for (key, value) in map {
        if !top_level_keys.contains(key.as_str()) {
            warnings.push(format!("unsupported legacy config key was ignored: {key}"));
            continue;
        }
        if !known_containers.contains(key.as_str()) {
            continue;
        }
        match value {
            Value::Object(nested) => {
                for nested_key in nested.keys() {
                    if !nested_keys.contains(nested_key.as_str()) {
                        warnings.push(format!(
                            "unsupported legacy config key was ignored: {key}.{nested_key}"
                        ));
                    }
                }
            }
            Value::Array(values) => {
                for (index, nested_value) in values.iter().enumerate() {
                    if let Some(nested) = nested_value.as_object() {
                        for nested_key in nested.keys() {
                            if !nested_keys.contains(nested_key.as_str()) {
                                warnings.push(format!(
                                    "unsupported legacy config key was ignored: {key}[{index}].{nested_key}"
                                ));
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }
}

fn legacy_supported_top_level_keys() -> HashSet<&'static str> {
    [
        "showCandidates",
        "show-candidates",
        "show-candidate",
        "candidateLimit",
        "maxAnalyzeTurns",
        "defaultMaxVisits",
        "maxVisits",
        "showOwnership",
        "showPolicy",
        "boardTheme",
        "theme",
        "engineCommand",
        "engine-command",
        "enginePath",
        "engine-path",
        "katagoCommand",
        "katago-command",
        "katagoPath",
        "katago-path",
        "leelazCommand",
        "leelaz-command",
        "leelazPath",
        "leelaz-path",
        "modelPath",
        "model-path",
        "katagoModelPath",
        "katago-model-path",
        "leelazModelPath",
        "leelaz-model-path",
        "configPath",
        "config-path",
        "gtpConfig",
        "gtp-config",
        "katagoConfigPath",
        "katago-config-path",
    ]
    .into_iter()
    .chain(legacy_known_container_keys())
    .collect()
}

fn legacy_supported_nested_keys() -> HashSet<&'static str> {
    [
        "showCandidates",
        "show-candidates",
        "show-candidate",
        "candidateLimit",
        "maxAnalyzeTurns",
        "defaultMaxVisits",
        "maxVisits",
        "showOwnership",
        "showPolicy",
        "boardTheme",
        "theme",
        "engineCommand",
        "engine-command",
        "enginePath",
        "engine-path",
        "katagoCommand",
        "katago-command",
        "katagoPath",
        "katago-path",
        "leelazCommand",
        "leelaz-command",
        "leelazPath",
        "leelaz-path",
        "modelPath",
        "model-path",
        "katagoModelPath",
        "katago-model-path",
        "leelazModelPath",
        "leelaz-model-path",
        "configPath",
        "config-path",
        "gtpConfig",
        "gtp-config",
        "katagoConfigPath",
        "katago-config-path",
        "command",
        "path",
        "model",
        "config",
    ]
    .into_iter()
    .collect()
}

fn legacy_known_container_keys() -> HashSet<&'static str> {
    [
        "ui",
        "preferences",
        "preference",
        "appPreferences",
        "app-preferences",
        "engine",
        "engines",
        "engineProfile",
        "engine-profile",
        "engineProfiles",
        "engine-profiles",
        "defaultEngine",
        "default-engine",
        "analysisEngine",
        "analysis-engine",
        "katago",
        "kataGo",
        "leelaz",
        "leelaZero",
    ]
    .into_iter()
    .collect()
}

fn sanitize_jsonish_config(contents: &str) -> String {
    let trimmed = contents.trim_start_matches('\u{feff}').trim();
    let object_slice = match (trimmed.find('{'), trimmed.rfind('}')) {
        (Some(start), Some(end)) if start < end => &trimmed[start..=end],
        _ => trimmed,
    };
    remove_trailing_json_commas(&strip_json_comments(object_slice))
}

fn strip_json_comments(input: &str) -> String {
    let mut output = String::with_capacity(input.len());
    let mut chars = input.chars().peekable();
    let mut in_string = false;
    let mut escaped = false;
    while let Some(ch) = chars.next() {
        if in_string {
            output.push(ch);
            if escaped {
                escaped = false;
                continue;
            }
            if ch == '\\' {
                escaped = true;
                continue;
            }
            if ch == '"' {
                in_string = false;
            }
            continue;
        }
        if ch == '"' {
            in_string = true;
            output.push(ch);
            continue;
        }
        if ch == '/' && chars.peek() == Some(&'/') {
            let _ = chars.next();
            for next in chars.by_ref() {
                if next == '\n' {
                    output.push('\n');
                    break;
                }
            }
            continue;
        }
        if ch == '/' && chars.peek() == Some(&'*') {
            let _ = chars.next();
            let mut previous = '\0';
            for next in chars.by_ref() {
                if previous == '*' && next == '/' {
                    break;
                }
                previous = next;
            }
            continue;
        }
        output.push(ch);
    }
    output
}

fn remove_trailing_json_commas(input: &str) -> String {
    let mut output = String::with_capacity(input.len());
    let mut chars = input.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch == ',' {
            let mut lookahead = chars.clone();
            while matches!(lookahead.peek(), Some(next) if next.is_whitespace()) {
                let _ = lookahead.next();
            }
            if matches!(lookahead.peek(), Some('}' | ']')) {
                continue;
            }
        }
        output.push(ch);
    }
    output
}

fn find_legacy_preference_value<'a>(root: &'a Value, aliases: &[&str]) -> Option<&'a Value> {
    let map = root.as_object()?;
    find_value_in_map(map, aliases).or_else(|| {
        [
            "ui",
            "preferences",
            "preference",
            "appPreferences",
            "app-preferences",
        ]
        .iter()
        .filter_map(|key| map.get(*key).and_then(Value::as_object))
        .find_map(|nested| find_value_in_map(nested, aliases))
    })
}

fn find_legacy_engine_value<'a>(
    root: &'a Value,
    top_level_aliases: &[&str],
    object_aliases: &[&str],
) -> Option<&'a Value> {
    let map = root.as_object()?;
    find_value_in_map(map, top_level_aliases).or_else(|| {
        find_known_engine_objects(root, false).find_map(|object| find_value_in_map(object, object_aliases))
    })
}

fn find_value_in_map<'a>(map: &'a serde_json::Map<String, Value>, aliases: &[&str]) -> Option<&'a Value> {
    aliases.iter().find_map(|alias| map.get(*alias))
}

fn find_known_engine_objects<'a>(
    value: &'a Value,
    include_self: bool,
) -> Box<dyn Iterator<Item = &'a serde_json::Map<String, Value>> + 'a> {
    let Some(map) = value.as_object() else {
        return Box::new(std::iter::empty());
    };

    let direct = if include_self && is_legacy_engine_object(map) {
        Some(map)
    } else {
        None
    }
    .into_iter();
    let nested = [
        "engine",
        "engines",
        "engineProfile",
        "engine-profile",
        "engineProfiles",
        "engine-profiles",
        "defaultEngine",
        "default-engine",
        "analysisEngine",
        "analysis-engine",
        "katago",
        "kataGo",
        "leelaz",
        "leelaZero",
    ]
    .into_iter()
    .filter_map(|key| map.get(key))
    .flat_map(|nested| match nested {
        Value::Object(_) => find_known_engine_objects(nested, true),
        Value::Array(values) => Box::new(
            values
                .iter()
                .flat_map(|value| find_known_engine_objects(value, true)),
        ) as Box<dyn Iterator<Item = &'a serde_json::Map<String, Value>>>,
        _ => Box::new(std::iter::empty()),
    });

    Box::new(direct.chain(nested))
}

fn is_legacy_engine_object(map: &serde_json::Map<String, Value>) -> bool {
    [
        "engineCommand",
        "engine-command",
        "enginePath",
        "engine-path",
        "katagoCommand",
        "katago-command",
        "katagoPath",
        "katago-path",
        "leelazCommand",
        "leelaz-command",
        "leelazPath",
        "leelaz-path",
        "modelPath",
        "model-path",
        "configPath",
        "config-path",
        "gtpConfig",
        "gtp-config",
        "command",
        "path",
        "model",
        "config",
    ]
    .iter()
    .any(|key| map.contains_key(*key))
}

fn legacy_bool(value: &Value) -> Option<bool> {
    match value {
        Value::Bool(value) => Some(*value),
        Value::String(value) => match value.trim().to_ascii_lowercase().as_str() {
            "true" | "yes" | "1" => Some(true),
            "false" | "no" | "0" => Some(false),
            _ => None,
        },
        Value::Number(value) => value.as_u64().and_then(|value| match value {
            0 => Some(false),
            1 => Some(true),
            _ => None,
        }),
        _ => None,
    }
}

fn legacy_u32(value: &Value) -> Option<u32> {
    match value {
        Value::Number(value) => value.as_u64().and_then(|value| u32::try_from(value).ok()),
        Value::String(value) => value.trim().parse::<u32>().ok(),
        _ => None,
    }
    .filter(|value| *value > 0)
}

fn legacy_string(value: &Value) -> Option<String> {
    match value {
        Value::String(value) => Some(value.trim().to_string()),
        _ => None,
    }
}

fn non_empty_legacy_string(value: Option<String>) -> Option<String> {
    value.and_then(|value| {
        let trimmed = value.trim();
        (!trimmed.is_empty()).then(|| trimmed.to_string())
    })
}

fn resolve_runtime_asset_layout_for_paths(
    current_dir: PathBuf,
    resource_dir: Option<PathBuf>,
) -> RuntimeAssetLayoutDto {
    let mut dev_roots = vec![current_dir.clone()];
    let nested_src_tauri = current_dir.join("apps").join("desktop").join("src-tauri");
    if nested_src_tauri != current_dir {
        dev_roots.push(nested_src_tauri);
    }
    let release_roots = resource_dir.iter().cloned().collect::<Vec<_>>();
    let mut candidates = Vec::new();
    for root in &dev_roots {
        push_runtime_asset_candidates(&mut candidates, root, "dev");
    }
    for root in &release_roots {
        push_runtime_asset_candidates(&mut candidates, root, "release");
    }

    RuntimeAssetLayoutDto {
        resource_dir: resource_dir.map(|path| path.display().to_string()),
        dev_roots: dev_roots
            .into_iter()
            .map(|path| path.display().to_string())
            .collect(),
        release_roots: release_roots
            .into_iter()
            .map(|path| path.display().to_string())
            .collect(),
        candidates,
    }
}

fn push_runtime_asset_candidates(candidates: &mut Vec<RuntimeAssetPathDto>, root: &Path, source: &str) {
    for (label, kind, relative, required) in [
        ("resource dir", "directory", PathBuf::new(), false),
        (
            "KataGo bin",
            "directory",
            PathBuf::from("runtime").join("katago").join("bin"),
            false,
        ),
        (
            "KataGo models",
            "directory",
            PathBuf::from("runtime").join("katago").join("models"),
            false,
        ),
        (
            "KataGo configs",
            "directory",
            PathBuf::from("runtime").join("katago").join("configs"),
            false,
        ),
        (
            "readboard runtime",
            "directory",
            PathBuf::from("runtime").join("readboard"),
            false,
        ),
    ] {
        candidates.push(RuntimeAssetPathDto {
            label: label.to_string(),
            kind: kind.to_string(),
            source: source.to_string(),
            path: root.join(relative).display().to_string(),
            required,
        });
    }
}

fn validate_runtime_asset_layout_from_layout(layout: RuntimeAssetLayoutDto) -> RuntimeAssetValidationDto {
    let missing = layout
        .candidates
        .iter()
        .filter(|candidate| !Path::new(&candidate.path).exists())
        .map(|candidate| RuntimeAssetMissingWarningDto {
            label: candidate.label.clone(),
            kind: candidate.kind.clone(),
            source: candidate.source.clone(),
            path: candidate.path.clone(),
            message: format!("{} candidate is missing at {}", candidate.label, candidate.path),
        })
        .collect::<Vec<_>>();
    let warnings = missing
        .iter()
        .map(|missing| missing.message.clone())
        .collect::<Vec<_>>();

    RuntimeAssetValidationDto {
        layout,
        missing,
        warnings,
    }
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

fn load_engine_profiles_settings_at_path(path: &Path) -> Result<EngineProfilesSettingsDto, String> {
    match fs::read_to_string(path) {
        Ok(contents) => parse_engine_profiles_settings(&contents, path),
        Err(err) if err.kind() == ErrorKind::NotFound => {
            normalize_engine_profiles_settings(default_engine_profiles_settings())
        }
        Err(err) => Err(format!("failed to read {}: {err}", path.display())),
    }
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

fn save_engine_profiles_settings_at_path(
    path: &Path,
    settings: EngineProfilesSettingsDto,
) -> Result<EngineProfilesSettingsDto, String> {
    let settings = normalize_engine_profiles_settings(settings)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            format!(
                "failed to create engine profile directory {}: {err}",
                parent.display()
            )
        })?;
    }
    let json = serde_json::to_string_pretty(&settings)
        .map_err(|err| format!("failed to serialize engine profiles: {err}"))?;
    fs::write(path, json).map_err(|err| format!("failed to write {}: {err}", path.display()))?;
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

fn enrich_provider_import_result(
    mut result: ProviderImportResult,
) -> Result<ProviderImportResult, ProviderError> {
    let document = sgf::parse_sgf(&result.sgf_text).map_err(|err| ProviderError {
        kind: ProviderErrorKind::ParseFailed,
        message: format!("failed to parse imported provider SGF: {err}"),
    })?;
    result.summary.provider = result.provider;
    result.summary.board_size = Some(document.board_size);
    result.summary.komi = Some(document.komi);
    result.summary.handicap = document.handicap;
    result.summary.black_name = document.black_name;
    result.summary.white_name = document.white_name;
    result.summary.result = document.result;
    result.summary.move_count = Some(document.moves.len());
    Ok(result)
}

fn validate_provider_fetch_request(
    request: &ProviderFetchRequest,
    expected_provider: ProviderKind,
    command_name: &str,
) -> Result<(), ProviderError> {
    if request.provider != expected_provider {
        return Err(ProviderError {
            kind: ProviderErrorKind::InvalidRequest,
            message: format!("{command_name} received provider {:?}", request.provider),
        });
    }
    if request.url.trim().is_empty() {
        return Err(ProviderError {
            kind: ProviderErrorKind::InvalidRequest,
            message: format!("{command_name} requires a non-empty url"),
        });
    }
    validate_timeout_ms(request.timeout_ms, command_name)
}

fn validate_timeout_ms(timeout_ms: Option<u64>, command_name: &str) -> Result<(), ProviderError> {
    if timeout_ms == Some(0) {
        return Err(ProviderError {
            kind: ProviderErrorKind::InvalidRequest,
            message: format!("{command_name} timeout_ms must be greater than zero"),
        });
    }
    Ok(())
}

fn readboard_error(error: readboard_sidecar::ReadboardSidecarError) -> ProviderError {
    let kind = match &error {
        readboard_sidecar::ReadboardSidecarError::MissingLaunchTarget => {
            ProviderErrorKind::RuntimeUnavailable
        }
        readboard_sidecar::ReadboardSidecarError::EmptyProtocolLine
        | readboard_sidecar::ReadboardSidecarError::MissingField(_)
        | readboard_sidecar::ReadboardSidecarError::InvalidField { .. }
        | readboard_sidecar::ReadboardSidecarError::DuplicateField { .. } => {
            ProviderErrorKind::InvalidPayload
        }
        readboard_sidecar::ReadboardSidecarError::Sync(_) => ProviderErrorKind::ParseFailed,
    };
    ProviderError {
        kind,
        message: error.to_string(),
    }
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
            runtime_smoke_config,
            runtime_smoke_report,
            parse_sgf_summary,
            parse_sgf_tree,
            provider_parse_yike_url,
            provider_import_from_payload,
            provider_fetch_yike,
            provider_fetch_fox,
            readboard_sidecar_probe,
            readboard_sidecar_sync_snapshot,
            replay_sgf_positions,
            update_sgf_node_comment,
            update_sgf_node_properties,
            append_sgf_move,
            edit_sgf_move,
            delete_sgf_node,
            reorder_sgf_variation,
            replay_sgf_position_at_node,
            read_sgf_file,
            write_sgf_file,
            fake_analyze,
            classify_problems,
            katago_launch_plan,
            engine_asset_checks,
            preview_legacy_config_migration,
            apply_legacy_config_migration,
            resolve_runtime_asset_layout,
            validate_runtime_asset_layout,
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

    static RUNTIME_SMOKE_REPORT_ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    fn native_sgf_temp_path(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!("lizzieyzy-native-sgf-{name}-{}.sgf", Uuid::new_v4()))
    }

    fn remove_native_sgf_temp_file(path: &Path) {
        let _ = fs::remove_file(path);
    }

    fn native_config_temp_dir(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!("lizzieyzy-{name}-{}", Uuid::new_v4()))
    }

    fn runtime_smoke_report_temp_path(name: &str) -> PathBuf {
        std::env::temp_dir()
            .join(format!("lizzieyzy-runtime-smoke-{name}-{}", Uuid::new_v4()))
            .join("nested")
            .join("report.json")
    }

    #[test]
    fn runtime_smoke_report_env_missing_does_not_write_file() {
        let _guard = RUNTIME_SMOKE_REPORT_ENV_LOCK.lock().unwrap();
        std::env::set_var(RUNTIME_SMOKE_ENABLED_ENV, "1");
        std::env::remove_var(RUNTIME_SMOKE_REPORT_PATH_ENV);
        let path = runtime_smoke_report_temp_path("missing");

        let error =
            runtime_smoke_report(path.display().to_string(), r#"{"ok":true}"#.to_string()).unwrap_err();

        std::env::remove_var(RUNTIME_SMOKE_ENABLED_ENV);
        let _ = fs::remove_dir_all(path.parent().unwrap().parent().unwrap());
        assert!(error.contains("is not set"));
        assert!(!path.exists());
    }

    #[test]
    fn runtime_smoke_report_env_mismatch_does_not_write_file() {
        let _guard = RUNTIME_SMOKE_REPORT_ENV_LOCK.lock().unwrap();
        let path = runtime_smoke_report_temp_path("mismatch");
        let allowed_path = runtime_smoke_report_temp_path("allowed");
        std::env::set_var(RUNTIME_SMOKE_ENABLED_ENV, "1");
        std::env::set_var(RUNTIME_SMOKE_REPORT_PATH_ENV, allowed_path.display().to_string());

        let error =
            runtime_smoke_report(path.display().to_string(), r#"{"ok":true}"#.to_string()).unwrap_err();

        std::env::remove_var(RUNTIME_SMOKE_ENABLED_ENV);
        std::env::remove_var(RUNTIME_SMOKE_REPORT_PATH_ENV);
        let _ = fs::remove_dir_all(path.parent().unwrap().parent().unwrap());
        let _ = fs::remove_dir_all(allowed_path.parent().unwrap().parent().unwrap());
        assert!(error.contains("does not match"));
        assert!(!path.exists());
    }

    #[test]
    fn runtime_smoke_report_disabled_does_not_write_file() {
        let _guard = RUNTIME_SMOKE_REPORT_ENV_LOCK.lock().unwrap();
        let path = runtime_smoke_report_temp_path("disabled");
        std::env::remove_var(RUNTIME_SMOKE_ENABLED_ENV);
        std::env::set_var(RUNTIME_SMOKE_REPORT_PATH_ENV, path.display().to_string());

        let error =
            runtime_smoke_report(path.display().to_string(), r#"{"ok":true}"#.to_string()).unwrap_err();

        std::env::remove_var(RUNTIME_SMOKE_REPORT_PATH_ENV);
        let _ = fs::remove_dir_all(path.parent().unwrap().parent().unwrap());
        assert!(error.contains("is not enabled"));
        assert!(!path.exists());
    }

    #[test]
    fn runtime_smoke_report_enabled_success_writes_file() {
        let _guard = RUNTIME_SMOKE_REPORT_ENV_LOCK.lock().unwrap();
        let path = runtime_smoke_report_temp_path("success");
        let report_json = r#"{"status":"ok","checks":["runtime"]}"#;
        std::env::set_var(RUNTIME_SMOKE_ENABLED_ENV, "true");
        std::env::set_var(RUNTIME_SMOKE_REPORT_PATH_ENV, path.display().to_string());

        runtime_smoke_report(path.display().to_string(), report_json.to_string()).unwrap();

        std::env::remove_var(RUNTIME_SMOKE_ENABLED_ENV);
        std::env::remove_var(RUNTIME_SMOKE_REPORT_PATH_ENV);
        let written = fs::read_to_string(&path).unwrap();
        let _ = fs::remove_dir_all(path.parent().unwrap().parent().unwrap());
        assert_eq!(written, report_json);
    }

    #[test]
    fn runtime_smoke_config_includes_phase() {
        let _guard = RUNTIME_SMOKE_REPORT_ENV_LOCK.lock().unwrap();
        let sgf_path = runtime_smoke_report_temp_path("config-sgf").with_extension("sgf");
        let report_path = runtime_smoke_report_temp_path("config-report");
        std::env::set_var(RUNTIME_SMOKE_ENABLED_ENV, "yes");
        std::env::set_var(RUNTIME_SMOKE_SGF_PATH_ENV, sgf_path.display().to_string());
        std::env::set_var(RUNTIME_SMOKE_REPORT_PATH_ENV, report_path.display().to_string());
        std::env::set_var(
            RUNTIME_SMOKE_EXPECTED_REPORT_PATH_ENV,
            report_path.display().to_string(),
        );
        std::env::set_var(RUNTIME_SMOKE_PHASE_ENV, "reopen-verify");

        let config = runtime_smoke_config();

        std::env::remove_var(RUNTIME_SMOKE_ENABLED_ENV);
        std::env::remove_var(RUNTIME_SMOKE_SGF_PATH_ENV);
        std::env::remove_var(RUNTIME_SMOKE_REPORT_PATH_ENV);
        std::env::remove_var(RUNTIME_SMOKE_EXPECTED_REPORT_PATH_ENV);
        std::env::remove_var(RUNTIME_SMOKE_PHASE_ENV);
        assert!(config.enabled);
        assert_eq!(config.sgf_path, Some(sgf_path.display().to_string()));
        assert_eq!(config.report_path, Some(report_path.display().to_string()));
        assert_eq!(
            config.expected_report_path,
            Some(report_path.display().to_string())
        );
        assert_eq!(config.phase, Some("reopen-verify".to_string()));
    }

    #[test]
    fn legacy_config_preview_does_not_write_files() {
        let dir = native_config_temp_dir("legacy-preview");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("lizzie.properties");
        let legacy_text = r#"
            // Lizzie-style JSON-ish config
            {
                "show-candidates": false,
                "candidateLimit": 42,
                "showOwnership": true,
                "theme": "high-contrast",
                "engine": {
                    "engineCommand": "/opt/katago/katago",
                    "modelPath": "/opt/katago/model.bin.gz",
                    "configPath": "/opt/katago/analysis.cfg",
                },
            }
        "#;
        fs::write(&legacy_path, legacy_text).unwrap();

        let preview = preview_legacy_config_migration_from_path(&legacy_path).unwrap();

        let after = fs::read_to_string(&legacy_path).unwrap();
        let _ = fs::remove_dir_all(&dir);
        assert_eq!(after, legacy_text);
        let preferences = preview.preferences.unwrap();
        assert!(!preferences.show_candidates);
        assert_eq!(preferences.candidate_limit, 20);
        assert_eq!(preferences.board_theme, "high-contrast");
        let profiles = preview.engine_profiles.unwrap();
        assert_eq!(profiles.profiles[0].profile.engine_path, "/opt/katago/katago");
        assert_eq!(
            profiles.profiles[0].profile.model_path.as_deref(),
            Some("/opt/katago/model.bin.gz")
        );
    }

    #[test]
    fn legacy_config_apply_writes_normalized_preferences_and_profile() {
        let dir = native_config_temp_dir("legacy-apply");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("config.json");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);
        fs::write(
            &legacy_path,
            r#"{
                "showCandidates": true,
                "candidateLimit": 999,
                "maxVisits": 1200,
                "showPolicy": false,
                "boardTheme": "unknown-theme",
                "enginePath": "/bin/katago",
                "modelPath": "/models/default.bin.gz",
                "configPath": "/configs/analysis.cfg"
            }"#,
        )
        .unwrap();

        let applied =
            apply_legacy_config_migration_to_paths(&legacy_path, &preferences_path, &profiles_path).unwrap();
        let preferences =
            serde_json::from_str::<AppPreferencesDto>(&fs::read_to_string(&preferences_path).unwrap())
                .unwrap();
        let profiles =
            serde_json::from_str::<EngineProfilesSettingsDto>(&fs::read_to_string(&profiles_path).unwrap())
                .unwrap();

        let _ = fs::remove_dir_all(&dir);
        assert!(applied.preferences_written);
        assert!(applied.engine_profiles_written);
        assert_eq!(preferences.candidate_limit, 20);
        assert_eq!(preferences.default_max_visits, 1200);
        assert_eq!(preferences.board_theme, "classic");
        assert_eq!(profiles.selected_profile_id, DEFAULT_ENGINE_PROFILE_ID);
        assert_eq!(profiles.profiles[0].profile.engine_path, "/bin/katago");
        assert_eq!(profiles.profiles[0].max_visits, 1200);
    }

    #[test]
    fn legacy_config_preview_reads_java_properties_and_warns_unsupported_keys() {
        let dir = native_config_temp_dir("legacy-properties");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("lizzie.properties");
        fs::write(
            &legacy_path,
            r#"
                # Representative legacy Java properties config
                preferences.showCandidates=false
                preferences.candidateLimit=12
                preferences.showOwnership=true
                preferences.showPolicy=false
                preferences.theme=high-contrast
                preferences.maxVisits=1600
                katago.command=/java/katago
                katago.model=/java/model.bin.gz
                katago.config=/java/analysis.cfg
                katago.maxVisits=1600
                unsupportedLegacyKey=ignored
            "#,
        )
        .unwrap();

        let preview = preview_legacy_config_migration_from_path(&legacy_path).unwrap();

        let _ = fs::remove_dir_all(&dir);
        let preferences = preview.preferences.unwrap();
        let profiles = preview.engine_profiles.unwrap();
        let profile = &profiles.profiles[0];
        assert!(!preferences.show_candidates);
        assert_eq!(preferences.candidate_limit, 12);
        assert!(preferences.show_ownership);
        assert!(!preferences.show_policy);
        assert_eq!(preferences.board_theme, "high-contrast");
        assert_eq!(preferences.default_max_visits, 1600);
        assert_eq!(profile.profile.engine_path, "/java/katago");
        assert_eq!(profile.profile.model_path.as_deref(), Some("/java/model.bin.gz"));
        assert_eq!(profile.profile.config_path.as_deref(), Some("/java/analysis.cfg"));
        assert_eq!(profile.max_visits, 1600);
        assert!(preview
            .warnings
            .iter()
            .any(|warning| warning.contains("unsupportedLegacyKey")));
    }

    #[test]
    fn legacy_config_ignores_unrelated_nested_generic_fields() {
        let dir = native_config_temp_dir("legacy-whitelist");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("config.json");
        fs::write(
            &legacy_path,
            r#"{
                "recentFile": {
                    "path": "/tmp/game.sgf",
                    "theme": "high-contrast",
                    "config": "/tmp/not-engine.cfg"
                }
            }"#,
        )
        .unwrap();

        let preview = preview_legacy_config_migration_from_path(&legacy_path).unwrap();

        let _ = fs::remove_dir_all(&dir);
        assert!(preview.preferences.is_none());
        assert!(preview.engine_profiles.is_none());
        assert!(preview
            .warnings
            .iter()
            .any(|warning| warning.contains("no supported legacy config fields")));
    }

    #[test]
    fn legacy_config_apply_merges_with_existing_preferences_and_profiles() {
        let dir = native_config_temp_dir("legacy-merge");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("config.json");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);
        save_app_preferences_at_path(
            &preferences_path,
            AppPreferencesDto {
                auto_load_cache: false,
                review_mode: "deep".to_string(),
                candidate_limit: 4,
                ..default_app_preferences()
            },
        )
        .unwrap();
        save_engine_profiles_settings_at_path(
            &profiles_path,
            EngineProfilesSettingsDto {
                selected_profile_id: "custom".to_string(),
                profiles: vec![
                    EngineProfileRecordDto {
                        id: DEFAULT_ENGINE_PROFILE_ID.to_string(),
                        profile: EngineProfileDto {
                            name: "Existing Default".to_string(),
                            engine_path: "/old/katago".to_string(),
                            model_path: Some("/old/model.bin.gz".to_string()),
                            config_path: Some("/old/analysis.cfg".to_string()),
                            working_dir: Some("/old".to_string()),
                            backend: EngineBackend::KataGoAnalysis,
                        },
                        max_visits: 4321,
                    },
                    EngineProfileRecordDto {
                        id: "custom".to_string(),
                        profile: EngineProfileDto {
                            name: "Custom Engine".to_string(),
                            engine_path: "/custom/engine".to_string(),
                            model_path: None,
                            config_path: None,
                            working_dir: None,
                            backend: EngineBackend::GenericGtp,
                        },
                        max_visits: 99,
                    },
                ],
            },
        )
        .unwrap();
        fs::write(
            &legacy_path,
            r#"{
                "candidateLimit": 6,
                "engine": {
                    "path": "/new/katago"
                }
            }"#,
        )
        .unwrap();

        let applied =
            apply_legacy_config_migration_to_paths(&legacy_path, &preferences_path, &profiles_path).unwrap();
        let preferences =
            serde_json::from_str::<AppPreferencesDto>(&fs::read_to_string(&preferences_path).unwrap())
                .unwrap();
        let profiles =
            serde_json::from_str::<EngineProfilesSettingsDto>(&fs::read_to_string(&profiles_path).unwrap())
                .unwrap();
        let default_profile = profiles
            .profiles
            .iter()
            .find(|record| record.id == DEFAULT_ENGINE_PROFILE_ID)
            .unwrap();
        let custom_profile = profiles
            .profiles
            .iter()
            .find(|record| record.id == "custom")
            .unwrap();

        let _ = fs::remove_dir_all(&dir);
        assert!(applied.preferences_written);
        assert!(applied.engine_profiles_written);
        assert_eq!(preferences.candidate_limit, 6);
        assert!(!preferences.auto_load_cache);
        assert_eq!(preferences.review_mode, "deep");
        assert_eq!(default_profile.profile.engine_path, "/new/katago");
        assert_eq!(
            default_profile.profile.model_path.as_deref(),
            Some("/old/model.bin.gz")
        );
        assert_eq!(default_profile.max_visits, 4321);
        assert_eq!(custom_profile.profile.engine_path, "/custom/engine");
        assert_eq!(custom_profile.max_visits, 99);
    }

    #[test]
    fn legacy_config_apply_malformed_config_returns_error_without_writing() {
        let dir = native_config_temp_dir("legacy-malformed");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("broken-config.json");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);
        let existing_preferences = AppPreferencesDto {
            show_candidates: false,
            candidate_limit: 3,
            ..default_app_preferences()
        };
        let existing_profiles = EngineProfilesSettingsDto {
            selected_profile_id: "custom".to_string(),
            profiles: vec![EngineProfileRecordDto {
                id: "custom".to_string(),
                profile: EngineProfileDto {
                    name: "Custom Engine".to_string(),
                    engine_path: "/custom/engine".to_string(),
                    model_path: None,
                    config_path: None,
                    working_dir: None,
                    backend: EngineBackend::GenericGtp,
                },
                max_visits: 99,
            }],
        };
        save_app_preferences_at_path(&preferences_path, existing_preferences.clone()).unwrap();
        save_engine_profiles_settings_at_path(&profiles_path, existing_profiles.clone()).unwrap();
        let before_preferences = fs::read_to_string(&preferences_path).unwrap();
        let before_profiles = fs::read_to_string(&profiles_path).unwrap();
        fs::write(
            &legacy_path,
            r#"{
                "showCandidates": true,
                "enginePath": "/new/katago",
            "#,
        )
        .unwrap();

        let error = apply_legacy_config_migration_to_paths(&legacy_path, &preferences_path, &profiles_path)
            .unwrap_err();
        let after_preferences = fs::read_to_string(&preferences_path).unwrap();
        let after_profiles = fs::read_to_string(&profiles_path).unwrap();

        let _ = fs::remove_dir_all(&dir);
        assert!(error.contains("failed to parse legacy config"));
        assert_eq!(after_preferences, before_preferences);
        assert_eq!(after_profiles, before_profiles);
    }

    #[test]
    fn legacy_config_missing_or_invalid_path_returns_error() {
        let missing = std::env::temp_dir().join(format!("lizzieyzy-missing-{}.json", Uuid::new_v4()));
        let error = preview_legacy_config_migration_from_path(&missing).unwrap_err();
        assert!(error.contains("failed to read legacy config"));

        let empty_error = preview_legacy_config_migration("  ".to_string()).unwrap_err();
        assert!(empty_error.contains("path must not be empty"));
    }

    #[test]
    fn legacy_config_no_supported_fields_succeeds_with_warning() {
        let dir = native_config_temp_dir("legacy-empty");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("config.json");
        fs::write(&legacy_path, r#"{"unrelated": true}"#).unwrap();

        let preview = preview_legacy_config_migration_from_path(&legacy_path).unwrap();

        let _ = fs::remove_dir_all(&dir);
        assert!(preview.preferences.is_none());
        assert!(preview.engine_profiles.is_none());
        assert!(preview
            .warnings
            .iter()
            .any(|warning| warning.contains("no supported legacy config fields")));
    }

    #[test]
    fn runtime_asset_validation_missing_assets_returns_warnings_not_panic() {
        let dir = native_config_temp_dir("runtime-assets");
        fs::create_dir_all(&dir).unwrap();
        let layout =
            resolve_runtime_asset_layout_for_paths(dir.join("dev-root"), Some(dir.join("resources")));

        let validation = validate_runtime_asset_layout_from_layout(layout);

        let _ = fs::remove_dir_all(&dir);
        assert!(!validation.missing.is_empty());
        assert_eq!(validation.missing.len(), validation.warnings.len());
        assert!(validation
            .missing
            .iter()
            .any(|warning| warning.path.contains("runtime/katago/bin")));
    }

    #[test]
    fn parse_sgf_tree_returns_variations_and_comments() {
        let tree = parse_sgf_tree(
            "(;SZ[5]C[root];B[aa]N[one]C[first](;W[bb]C[main])(;W[cc]N[var]C[branch];B[]))".to_string(),
        )
        .unwrap()
        .unwrap();

        assert_eq!(tree.nodes.len(), 5);
        let root = tree.nodes.iter().find(|node| node.id == tree.root_id).unwrap();
        assert_eq!(root.comment.as_deref(), Some("root"));
        assert_eq!(root.child_ids.len(), 1);
        assert!(root.is_mainline);

        let first_move = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap();
        assert_eq!(first_move.comment.as_deref(), Some("first"));
        assert_eq!(first_move.name.as_deref(), Some("one"));
        assert_eq!(first_move.color, Some(app_model::PlayerColor::Black));
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
        assert_eq!(mainline_reply.variation_index, 0);
        assert_eq!(mainline_reply.move_number, Some(2));
        assert!(mainline_reply.is_mainline);

        let branch_reply = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch"))
            .unwrap();
        assert_eq!(branch_reply.variation_index, 1);
        assert_eq!(branch_reply.move_number, Some(2));
        assert_eq!(branch_reply.name.as_deref(), Some("var"));
        assert!(!branch_reply.is_mainline);
    }

    #[test]
    fn parse_sgf_tree_reports_bad_sgf() {
        let error = parse_sgf_tree("not sgf".to_string()).unwrap_err();

        assert!(!error.is_empty());
    }

    #[test]
    fn command_updates_branch_comment_visible_in_tree() {
        let input = "(;SZ[5];B[aa](;W[bb]C[main])(;W[cc]C[branch]))";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let branch_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch"))
            .unwrap()
            .id;

        let updated =
            update_sgf_node_comment(input.to_string(), branch_id, Some("branch updated".to_string()))
                .unwrap();
        let updated_tree = parse_sgf_tree(updated).unwrap().unwrap();
        let branch = updated_tree
            .nodes
            .iter()
            .find(|node| node.id == branch_id)
            .unwrap();

        assert_eq!(branch.comment.as_deref(), Some("branch updated"));
    }

    #[test]
    fn command_clears_comment_visible_as_none_in_tree() {
        let input = "(;SZ[5];B[aa]C[old];W[bb]C[keep])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("old"))
            .unwrap()
            .id;

        let updated = update_sgf_node_comment(input.to_string(), node_id, None).unwrap();
        let updated_tree = parse_sgf_tree(updated).unwrap().unwrap();
        let node = updated_tree.nodes.iter().find(|node| node.id == node_id).unwrap();

        assert_eq!(node.comment, None);
    }

    #[test]
    fn command_updates_sgf_node_properties() {
        let input = "(;SZ[5]PB[Old];B[aa]N[old]TR[bb]ZZ[keep])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.name.as_deref() == Some("old"))
            .unwrap()
            .id;

        let result = update_sgf_node_properties(
            input.to_string(),
            node_id,
            vec![
                SgfPropertyUpdateDto {
                    key: "N".to_string(),
                    values: vec!["new".to_string()],
                },
                SgfPropertyUpdateDto {
                    key: "TR".to_string(),
                    values: Vec::new(),
                },
                SgfPropertyUpdateDto {
                    key: "LB".to_string(),
                    values: vec!["aa:A".to_string()],
                },
            ],
        )
        .unwrap();

        assert_eq!(result.node_id, node_id);
        assert_eq!(result.sgf_text, "(;SZ[5]PB[Old];B[aa]N[new]ZZ[keep]LB[aa:A])");
    }

    #[test]
    fn command_rejects_invalid_sgf_property_key() {
        let input = "(;SZ[5];B[aa]C[old])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("old"))
            .unwrap()
            .id;

        let error = update_sgf_node_properties(
            input.to_string(),
            node_id,
            vec![SgfPropertyUpdateDto {
                key: "C1".to_string(),
                values: vec!["new".to_string()],
            }],
        )
        .unwrap_err();

        assert!(error.contains("invalid SGF property key"));
    }

    #[test]
    fn command_appends_sgf_move_to_leaf() {
        let input = "(;SZ[5];B[aa])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let leaf_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;

        let result = append_sgf_move(
            input.to_string(),
            leaf_id,
            app_model::PlayerColor::White,
            MoveVertex::Point(PointDto { x: 1, y: 1 }),
        )
        .unwrap();
        let updated_tree = parse_sgf_tree(result.sgf_text).unwrap().unwrap();
        let appended = updated_tree
            .nodes
            .iter()
            .find(|node| node.id == result.new_node_id)
            .unwrap();

        assert_eq!(appended.parent_id, Some(leaf_id));
        assert_eq!(appended.color, Some(app_model::PlayerColor::White));
        assert_eq!(appended.vertex, Some(MoveVertex::Point(PointDto { x: 1, y: 1 })));
        assert_eq!(appended.move_number, Some(2));
    }

    #[test]
    fn command_appends_sgf_move_as_variation() {
        let input = "(;SZ[5];B[aa];W[bb])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;

        let result = append_sgf_move(
            input.to_string(),
            parent_id,
            app_model::PlayerColor::White,
            MoveVertex::Point(PointDto { x: 2, y: 2 }),
        )
        .unwrap();
        let updated_tree = parse_sgf_tree(result.sgf_text).unwrap().unwrap();
        let parent = updated_tree
            .nodes
            .iter()
            .find(|node| node.id == parent_id)
            .unwrap();
        let appended = updated_tree
            .nodes
            .iter()
            .find(|node| node.id == result.new_node_id)
            .unwrap();

        assert_eq!(parent.child_ids.len(), 2);
        assert_eq!(appended.parent_id, Some(parent_id));
        assert_eq!(appended.variation_index, 1);
        assert_eq!(appended.color, Some(app_model::PlayerColor::White));
        assert_eq!(appended.vertex, Some(MoveVertex::Point(PointDto { x: 2, y: 2 })));
    }

    #[test]
    fn command_append_sgf_move_reports_illegal_occupied_point() {
        let input = "(;SZ[5];B[aa])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let leaf_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;

        let error = append_sgf_move(
            input.to_string(),
            leaf_id,
            app_model::PlayerColor::White,
            MoveVertex::Point(PointDto { x: 0, y: 0 }),
        )
        .unwrap_err();

        assert!(error.to_ascii_lowercase().contains("occupied"));
    }

    #[test]
    fn command_edits_sgf_move_and_keeps_node_id_stable() {
        let input = "(;SZ[5];B[aa]C[first];W[bb])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("first"))
            .unwrap()
            .id;

        let result = edit_sgf_move(
            input.to_string(),
            node_id,
            app_model::PlayerColor::Black,
            MoveVertex::Point(PointDto { x: 2, y: 2 }),
        )
        .unwrap();
        let updated_tree = parse_sgf_tree(result.sgf_text).unwrap().unwrap();
        let edited = updated_tree.nodes.iter().find(|node| node.id == node_id).unwrap();

        assert_eq!(result.node_id, node_id);
        assert_eq!(edited.color, Some(app_model::PlayerColor::Black));
        assert_eq!(edited.vertex, Some(MoveVertex::Point(PointDto { x: 2, y: 2 })));
        assert_eq!(edited.comment.as_deref(), Some("first"));
    }

    #[test]
    fn command_edit_sgf_move_rejects_root_node() {
        let input = "(;SZ[5];B[aa])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();

        let error = edit_sgf_move(
            input.to_string(),
            tree.root_id,
            app_model::PlayerColor::Black,
            MoveVertex::Point(PointDto { x: 1, y: 1 }),
        )
        .unwrap_err();

        assert!(error.to_ascii_lowercase().contains("root"));
    }

    #[test]
    fn command_edit_sgf_move_rejects_non_move_node() {
        let input = "(;SZ[5];C[setup];B[aa])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("setup"))
            .unwrap()
            .id;

        let error = edit_sgf_move(
            input.to_string(),
            node_id,
            app_model::PlayerColor::Black,
            MoveVertex::Point(PointDto { x: 1, y: 1 }),
        )
        .unwrap_err();

        assert!(error.to_ascii_lowercase().contains("move"));
    }

    #[test]
    fn command_edit_sgf_move_rejects_occupied_point() {
        let input = "(;SZ[5];B[aa];W[bb]C[target])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("target"))
            .unwrap()
            .id;

        let error = edit_sgf_move(
            input.to_string(),
            node_id,
            app_model::PlayerColor::White,
            MoveVertex::Point(PointDto { x: 0, y: 0 }),
        )
        .unwrap_err();

        assert!(error.to_ascii_lowercase().contains("occupied"));
    }

    #[test]
    fn command_edit_sgf_move_preserves_comment_property_and_child() {
        let input = "(;SZ[5];B[aa]C[keep]N[name]ZZ[unknown];W[bb]C[child])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let node_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("keep"))
            .unwrap()
            .id;

        let result = edit_sgf_move(
            input.to_string(),
            node_id,
            app_model::PlayerColor::Black,
            MoveVertex::Point(PointDto { x: 2, y: 2 }),
        )
        .unwrap();
        let updated_tree = parse_sgf_tree(result.sgf_text.clone()).unwrap().unwrap();
        let edited = updated_tree.nodes.iter().find(|node| node.id == node_id).unwrap();

        assert_eq!(edited.comment.as_deref(), Some("keep"));
        assert_eq!(edited.name.as_deref(), Some("name"));
        assert!(result.sgf_text.contains("ZZ[unknown]"));
        assert!(updated_tree
            .nodes
            .iter()
            .any(|node| node.comment.as_deref() == Some("child") && node.parent_id == Some(node_id)));
    }

    #[test]
    fn command_deletes_sgf_leaf_node() {
        let input = "(;SZ[5];B[aa];W[bb]C[leaf])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;
        let leaf_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("leaf"))
            .unwrap()
            .id;

        let result = delete_sgf_node(input.to_string(), leaf_id).unwrap();
        let updated_tree = parse_sgf_tree(result.sgf_text).unwrap().unwrap();
        let parent = updated_tree
            .nodes
            .iter()
            .find(|node| node.id == parent_id)
            .unwrap();

        assert_eq!(result.parent_node_id, parent_id);
        assert!(updated_tree.nodes.iter().all(|node| node.id != leaf_id));
        assert!(parent.child_ids.is_empty());
    }

    #[test]
    fn command_deletes_sgf_variation_node() {
        let input = "(;SZ[5];B[aa](;W[bb]C[main])(;W[cc]C[branch]))";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;
        let branch_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch"))
            .unwrap()
            .id;

        let result = delete_sgf_node(input.to_string(), branch_id).unwrap();
        let updated_tree = parse_sgf_tree(result.sgf_text).unwrap().unwrap();
        let parent = updated_tree
            .nodes
            .iter()
            .find(|node| node.id == parent_id)
            .unwrap();

        assert_eq!(result.parent_node_id, parent_id);
        assert_eq!(parent.child_ids.len(), 1);
        assert!(updated_tree
            .nodes
            .iter()
            .all(|node| node.comment.as_deref() != Some("branch")));
    }

    #[test]
    fn command_delete_sgf_node_reports_root_error() {
        let input = "(;SZ[5];B[aa])";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();

        let error = delete_sgf_node(input.to_string(), tree.root_id).unwrap_err();

        assert!(error.to_ascii_lowercase().contains("root"));
    }

    #[test]
    fn command_reorders_sgf_variation_and_returns_new_node_id() {
        let input = "(;SZ[5];B[aa](;W[bb]C[main])(;W[cc]C[branch];B[dd]C[child]))";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let branch_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch"))
            .unwrap()
            .id;
        let parent_id = tree
            .nodes
            .iter()
            .find(|node| node.move_number == Some(1))
            .unwrap()
            .id;

        let result = reorder_sgf_variation(input.to_string(), branch_id, 0).unwrap();
        let updated_tree = parse_sgf_tree(result.sgf_text).unwrap().unwrap();
        let moved = updated_tree
            .nodes
            .iter()
            .find(|node| node.id == result.node_id)
            .unwrap();

        assert_eq!(result.parent_node_id, parent_id);
        assert_eq!(moved.comment.as_deref(), Some("branch"));
        assert_eq!(moved.variation_index, 0);
        assert!(moved.is_mainline);
        assert!(updated_tree
            .nodes
            .iter()
            .any(|node| node.comment.as_deref() == Some("child") && node.parent_id == Some(result.node_id)));
    }

    #[test]
    fn command_reorder_sgf_variation_reports_out_of_range() {
        let input = "(;SZ[5];B[aa](;W[bb])(;W[cc]C[branch]))";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let branch_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch"))
            .unwrap()
            .id;

        let error = reorder_sgf_variation(input.to_string(), branch_id, 2).unwrap_err();

        assert!(error.contains("out of range"));
    }

    #[test]
    fn command_replays_branch_node_not_mainline_sibling() {
        let input = "(;SZ[5]AB[aa]PL[W];B[bb](;W[bc]C[main])(;W[cb]C[branch]))";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let branch_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch"))
            .unwrap()
            .id;

        let position = replay_sgf_position_at_node(input.to_string(), branch_id).unwrap();

        assert!(position
            .stones
            .iter()
            .any(|stone| stone.x == 2 && stone.y == 1 && stone.color == app_model::PlayerColor::White));
        assert!(!position
            .stones
            .iter()
            .any(|stone| stone.x == 1 && stone.y == 2 && stone.color == app_model::PlayerColor::White));
    }

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
    fn native_sgf_read_sgf_file_reads_real_temp_sgf() {
        let path = native_sgf_temp_path("read");
        let sgf_text = "(;GM[1]FF[4]SZ[19]C[real temp file];B[dd];W[qq])";
        fs::write(&path, sgf_text).unwrap();

        let read = read_sgf_file(path.display().to_string()).unwrap();

        remove_native_sgf_temp_file(&path);
        assert_eq!(read, sgf_text);
    }

    #[test]
    fn native_sgf_write_sgf_file_rejects_invalid_sgf_without_polluting_existing_file() {
        let path = native_sgf_temp_path("invalid-write");
        let original = "(;GM[1]FF[4]SZ[19]C[original];B[dd])";
        fs::write(&path, original).unwrap();

        let error = write_sgf_file(path.display().to_string(), "not sgf".to_string()).unwrap_err();
        let after = fs::read_to_string(&path).unwrap();

        remove_native_sgf_temp_file(&path);
        assert!(error.contains("failed to parse SGF text"));
        assert_eq!(after, original);
    }

    #[test]
    fn native_sgf_roundtrip_preserves_parseable_tokens_after_updates_and_reorder() {
        let path = native_sgf_temp_path("roundtrip");
        let input = "(;GM[1]FF[4]SZ[19]KM[7.5]PB[Black]PW[White]C[root comment]\
            ;B[dd]N[first move]TR[dd]C[first comment]\
            (;W[qq]LB[qq:A]C[main variation])\
            (;W[pq]CR[pq]C[branch variation];B[dp]MA[dp]C[branch child]))";
        let tree = parse_sgf_tree(input.to_string()).unwrap().unwrap();
        let branch_id = tree
            .nodes
            .iter()
            .find(|node| node.comment.as_deref() == Some("branch variation"))
            .unwrap()
            .id;

        let with_comment =
            update_sgf_node_comment(input.to_string(), branch_id, Some("branch updated".to_string()))
                .unwrap();
        let with_properties = update_sgf_node_properties(
            with_comment,
            branch_id,
            vec![
                SgfPropertyUpdateDto {
                    key: "N".to_string(),
                    values: vec!["forcing line".to_string()],
                },
                SgfPropertyUpdateDto {
                    key: "LB".to_string(),
                    values: vec!["pq:X".to_string(), "dp:Y".to_string()],
                },
            ],
        )
        .unwrap()
        .sgf_text;
        let reordered = reorder_sgf_variation(with_properties, branch_id, 0)
            .unwrap()
            .sgf_text;

        write_sgf_file(path.display().to_string(), reordered).unwrap();
        let read = read_sgf_file(path.display().to_string()).unwrap();
        let roundtrip_tree = parse_sgf_tree(read.clone()).unwrap().unwrap();

        remove_native_sgf_temp_file(&path);
        let updated_branch = roundtrip_tree
            .nodes
            .iter()
            .find(|node| {
                node.comment.as_deref() == Some("branch updated")
                    && node.name.as_deref() == Some("forcing line")
                    && node.variation_index == 0
                    && node.is_mainline
            })
            .unwrap();
        let original_sibling = roundtrip_tree
            .nodes
            .iter()
            .find(|node| {
                node.comment.as_deref() == Some("main variation")
                    && node.color == Some(app_model::PlayerColor::White)
                    && node.vertex == Some(MoveVertex::Point(PointDto { x: 16, y: 16 }))
            })
            .unwrap();

        assert_eq!(updated_branch.parent_id, original_sibling.parent_id);
        assert_eq!(original_sibling.variation_index, 1);
        assert!(!original_sibling.is_mainline);
        for token in [
            "GM[1]",
            "FF[4]",
            "SZ[19]",
            "KM[7.5]",
            "PB[Black]",
            "PW[White]",
            "C[root comment]",
            "TR[dd]",
            "W[qq]",
            "LB[qq:A]",
            "C[main variation]",
            "CR[pq]",
            "MA[dp]",
            "LB[pq:X]",
            "LB[pq:X][dp:Y]",
            "C[branch child]",
        ] {
            assert!(read.contains(token), "missing token {token} in {read}");
        }
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
    fn provider_fetch_yike_adds_missing_signature_headers_without_network() {
        let mut request = provider_fetch_request(ProviderKind::Yike);
        request
            .headers
            .insert("AppKey".to_string(), "caller-app-key".to_string());

        let prepared = prepare_yike_fetch_request(request);

        assert_eq!(
            prepared.headers.get("AppKey").map(String::as_str),
            Some("caller-app-key")
        );
        assert!(prepared.headers.contains_key("CurTime"));
        assert!(prepared.headers.contains_key("CheckSum"));
        assert!(prepared.headers.contains_key("Nonce"));
        assert!(prepared.headers.contains_key("accesstoken"));
    }

    #[test]
    fn provider_fetch_fox_http_adds_default_user_agent_without_network() {
        let request = provider_fetch_request(ProviderKind::Fox);

        let prepared = prepare_fox_http_fetch_request(request);

        assert_eq!(
            prepared.headers.get("User-Agent").map(String::as_str),
            Some(provider_fox::FOX_MOBILE_USER_AGENT)
        );
    }

    #[test]
    fn provider_fetch_yike_validates_detail_payload_and_preserves_signature_headers_without_network() {
        let mut request = provider_fetch_request(ProviderKind::Yike);
        request.url = "https://api-new.yikeweiqi.com/v1/golives/186031".to_string();
        request
            .headers
            .insert("AppKey".to_string(), "caller-app-key".to_string());
        let transport = provider_core::RecordingProviderTransport::with_result(Ok(provider_fetch_result(
            ProviderKind::Yike,
            "https://api-new.yikeweiqi.com/v1/golives/186031",
            200,
            r#"{"status":0,"result":{"sgf":"(;GM[1]SZ[19];B[aa])","status":2}}"#,
        )));

        let result = fetch_yike_with_transport(request, &transport).unwrap();

        assert_eq!(result.status_code, 200);
        let requests = transport.requests().unwrap();
        assert_eq!(requests.len(), 1);
        assert_eq!(
            requests[0].headers.get("AppKey").map(String::as_str),
            Some("caller-app-key")
        );
        assert!(requests[0].headers.contains_key("CurTime"));
        assert!(requests[0].headers.contains_key("CheckSum"));
        assert!(requests[0].headers.contains_key("Nonce"));
        assert!(requests[0].headers.contains_key("accesstoken"));
    }

    #[test]
    fn provider_fetch_yike_maps_http_and_bad_json_without_network() {
        let mut request = provider_fetch_request(ProviderKind::Yike);
        request.url = "https://api-new.yikeweiqi.com/v1/golives/186031".to_string();
        let transport = provider_core::StaticProviderTransport::ok(provider_fetch_result(
            ProviderKind::Yike,
            "https://api-new.yikeweiqi.com/v1/golives/186031",
            503,
            "service unavailable",
        ));

        let error = fetch_yike_with_transport(request.clone(), &transport).unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::TransportFailed);
        assert!(error.message.contains("HTTP 503"));

        let transport = provider_core::StaticProviderTransport::ok(provider_fetch_result(
            ProviderKind::Yike,
            "https://api-new.yikeweiqi.com/v1/golives/186031",
            200,
            "{",
        ));

        let error = fetch_yike_with_transport(request, &transport).unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::InvalidPayload);
    }

    #[test]
    fn provider_fetch_yike_validates_list_payload_without_network() {
        let mut request = provider_fetch_request(ProviderKind::Yike);
        request.url = "https://api.yikeweiqi.com/v2/golive/list?p=1&since=0&official=&version=2".to_string();
        let transport = provider_core::StaticProviderTransport::ok(provider_fetch_result(
            ProviderKind::Yike,
            &request.url,
            200,
            r#"{"Status":1200,"Result":{"since":12,"list":[]}}"#,
        ));

        let result = fetch_yike_with_transport(request, &transport).unwrap();

        assert_eq!(result.status_code, 200);
    }

    #[test]
    fn provider_fetch_fox_http_checks_status_and_warns_without_network() {
        let mut request = provider_fetch_request(ProviderKind::Fox);
        request.url = "https://example.test/fox".to_string();
        let transport = provider_core::StaticProviderTransport::ok(provider_fetch_result(
            ProviderKind::Fox,
            "https://example.test/fox",
            500,
            "server error",
        ));

        let error = fetch_fox_with_transport(request.clone(), &transport).unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::TransportFailed);
        assert!(error.message.contains("HTTP 500"));

        let transport = provider_core::StaticProviderTransport::ok(provider_fetch_result(
            ProviderKind::Fox,
            "https://example.test/fox",
            200,
            "{}",
        ));
        let result = fetch_fox_with_transport(request, &transport).unwrap();

        assert!(result.warnings.iter().any(|warning| warning.contains("directly")));
    }

    #[test]
    fn provider_fetch_commands_validate_provider_before_runtime() {
        let error = provider_fetch_yike(provider_fetch_request(ProviderKind::Fox)).unwrap_err();

        assert_eq!(error.kind, ProviderErrorKind::InvalidRequest);
        assert!(error.message.contains("provider_fetch_yike"));
    }

    #[test]
    fn provider_fetch_fox_non_http_uses_command_parser_without_network() {
        let mut request = provider_fetch_request(ProviderKind::Fox);
        request.url = "not-a-fox-command".to_string();

        let error = provider_fetch_fox(request).unwrap_err();

        assert_eq!(error.kind, ProviderErrorKind::InvalidRequest);
        assert!(error.message.contains("Fox command"));
    }

    #[test]
    fn readboard_sidecar_probe_returns_structured_runtime_status() {
        let result = readboard_sidecar_probe(ReadboardSidecarProbeRequest {
            endpoint: Some("local-test-endpoint".to_string()),
            timeout_ms: Some(100),
        })
        .unwrap();

        assert!(!result.available);
        assert_eq!(result.endpoint.as_deref(), Some("local-test-endpoint"));
        assert!(result
            .warnings
            .iter()
            .any(|warning| warning.contains("UnsupportedEndpoint")));
    }

    #[test]
    fn readboard_sidecar_sync_snapshot_supports_offline_protocol_line() {
        let result = readboard_sidecar_sync_snapshot(ReadboardSidecarSyncSnapshotRequest {
            endpoint: None,
            snapshot_id: Some("snapshot-1".to_string()),
            image_path: None,
            image_base64: None,
            sgf_text: Some("snapshot board_size=2 move_number=1 codes=3000".to_string()),
            metadata: std::collections::BTreeMap::new(),
            timeout_ms: Some(100),
        })
        .unwrap();

        assert_eq!(result.snapshot_id, "snapshot-1");
        let position = result.position.unwrap();
        assert_eq!(position.board_size, 2);
        assert_eq!(position.move_number, 1);
        assert_eq!(position.stones.len(), 1);
    }

    #[test]
    fn readboard_sidecar_sync_snapshot_reports_image_runtime_unavailable() {
        let sync_error = readboard_sidecar_sync_snapshot(ReadboardSidecarSyncSnapshotRequest {
            endpoint: Some("http://127.0.0.1:39081".to_string()),
            snapshot_id: Some("snapshot-1".to_string()),
            image_path: Some("/tmp/board.png".to_string()),
            image_base64: None,
            sgf_text: None,
            metadata: std::collections::BTreeMap::new(),
            timeout_ms: Some(100),
        })
        .unwrap_err();

        assert_eq!(sync_error.kind, ProviderErrorKind::RuntimeUnavailable);
        assert!(sync_error
            .message
            .contains("readboard image OCR runtime is unavailable"));
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

    fn provider_fetch_request(provider: ProviderKind) -> ProviderFetchRequest {
        ProviderFetchRequest {
            provider,
            url: "https://example.test/provider".to_string(),
            method: app_model::ProviderFetchMethod::Get,
            headers: std::collections::BTreeMap::new(),
            body: None,
            source_url: None,
            source_id: None,
            timeout_ms: Some(100),
        }
    }

    fn provider_fetch_result(
        provider: ProviderKind,
        url: &str,
        status_code: u16,
        payload: &str,
    ) -> ProviderFetchResult {
        ProviderFetchResult {
            provider,
            url: url.to_string(),
            status_code,
            payload: payload.to_string(),
            headers: std::collections::BTreeMap::new(),
            content_type: Some("application/json".to_string()),
            metadata: ProviderGameMetadata {
                request_url: Some(url.to_string()),
                ..ProviderGameMetadata::default()
            },
            warnings: Vec::new(),
        }
    }
}
