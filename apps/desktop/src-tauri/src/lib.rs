use app_model::{
    AnalysisFrameDto, AppHealthDto, CandidateMoveDto, EngineBackend, EngineProfileDto, MoveVertex, NodeId,
    PointDto, PositionDto, ProviderError, ProviderErrorKind, ProviderFetchMethod, ProviderFetchRequest,
    ProviderFetchResult, ProviderGameMetadata, ProviderImportRequest, ProviderImportResult, ProviderKind,
    ReadboardSidecarProbeRequest, ReadboardSidecarProbeResult, ReadboardSidecarSyncSnapshotRequest,
    ReadboardSidecarSyncSnapshotResult, SgfTreeDto, SgfTreeNodeDto,
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
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager, Runtime, State};
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
const NATIVE_MENU_EVENT_NAME: &str = "legacy://native-menu-action";

struct NativeMenuActionSpec {
    menu_id: &'static str,
    action_id: &'static str,
    target_id: &'static str,
    label: &'static str,
    menu_path: &'static [&'static str],
    accelerator: Option<&'static str>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct NativeMenuActionDto {
    menu_id: String,
    action_id: String,
    target_id: String,
    label: String,
    menu_path: Vec<String>,
    accelerator: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct NativeMenuContractDto {
    schema: String,
    event_name: String,
    actions: Vec<NativeMenuActionDto>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct NativeMenuActionEventDto {
    menu_id: String,
    action_id: String,
    target_id: String,
    label: String,
    menu_path: Vec<String>,
    accelerator: Option<String>,
    source: String,
}

const NATIVE_MENU_ACTIONS: &[NativeMenuActionSpec] = &[
    NativeMenuActionSpec {
        menu_id: "legacy-menu-file-open",
        action_id: "file.open",
        target_id: "open-sgf",
        label: "Open",
        menu_path: &["File", "Open"],
        accelerator: Some("CmdOrCtrl+O"),
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-file-save",
        action_id: "file.save",
        target_id: "save-sgf",
        label: "Save",
        menu_path: &["File", "Save"],
        accelerator: Some("CmdOrCtrl+S"),
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-file-save-as",
        action_id: "file.saveAs",
        target_id: "save-as-sgf",
        label: "Save As",
        menu_path: &["File", "Save As"],
        accelerator: Some("CmdOrCtrl+Shift+S"),
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-file-import-sgf",
        action_id: "file.importSgf",
        target_id: "import-sgf",
        label: "Import SGF",
        menu_path: &["File", "Import SGF"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-game-load-sample",
        action_id: "game.loadSample",
        target_id: "load-sample",
        label: "Load sample",
        menu_path: &["Game", "Load sample"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-game-parse-sgf",
        action_id: "game.parseSgf",
        target_id: "parse-sgf",
        label: "Parse SGF",
        menu_path: &["Game", "Parse SGF"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-analysis-run-review",
        action_id: "analysis.runReview",
        target_id: "run-review",
        label: "Run review",
        menu_path: &["Analysis", "Run review"],
        accelerator: Some("CmdOrCtrl+R"),
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-analysis-katago-panel",
        action_id: "analysis.katagoPanel",
        target_id: "profiles",
        label: "KataGo panel",
        menu_path: &["Analysis", "KataGo panel"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-view-candidates",
        action_id: "view.candidates",
        target_id: "candidates",
        label: "Candidates",
        menu_path: &["View", "Candidates"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-view-ownership",
        action_id: "view.ownership",
        target_id: "ownership",
        label: "Ownership",
        menu_path: &["View", "Ownership"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-view-policy",
        action_id: "view.policy",
        target_id: "policy",
        label: "Policy",
        menu_path: &["View", "Policy"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-engine-profiles",
        action_id: "engine.profiles",
        target_id: "profiles",
        label: "Profiles",
        menu_path: &["Engine", "Profiles"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-engine-assets",
        action_id: "engine.assets",
        target_id: "assets",
        label: "Assets",
        menu_path: &["Engine", "Assets"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-tools-providers",
        action_id: "tools.providers",
        target_id: "providers",
        label: "Providers",
        menu_path: &["Tools", "Providers"],
        accelerator: None,
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-tools-preferences",
        action_id: "tools.preferences",
        target_id: "preferences",
        label: "Preferences",
        menu_path: &["Tools", "Preferences"],
        accelerator: Some("CmdOrCtrl+,"),
    },
    NativeMenuActionSpec {
        menu_id: "legacy-menu-help-backend-status",
        action_id: "help.backendStatus",
        target_id: "backend-status",
        label: "Backend status",
        menu_path: &["Help", "Backend status"],
        accelerator: None,
    },
];

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

impl AnalysisJobRegistry {
    fn insert(&self, job_id: String, cancel_token: AnalysisCancelToken) -> Result<(), String> {
        let mut jobs = self
            .jobs
            .lock()
            .map_err(|_| "analysis job registry is unavailable".to_string())?;
        jobs.insert(job_id, cancel_token);
        Ok(())
    }

    fn cancel(&self, job_id: &str) -> Result<bool, String> {
        let cancel_token = {
            let mut jobs = self
                .jobs
                .lock()
                .map_err(|_| "analysis job registry is unavailable".to_string())?;
            jobs.remove(job_id)
        };
        if let Some(cancel_token) = cancel_token {
            cancel_token.cancel();
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn remove(&self, job_id: &str) {
        if let Ok(mut jobs) = self.jobs.lock() {
            jobs.remove(job_id);
        };
    }

    #[cfg(test)]
    fn contains(&self, job_id: &str) -> bool {
        self.jobs
            .lock()
            .map(|jobs| jobs.contains_key(job_id))
            .unwrap_or(false)
    }
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
    status: String,
    source_path: String,
    preferences_written: bool,
    engine_profiles_written: bool,
    written_paths: Vec<String>,
    written_path_labels: Vec<String>,
    transactional: bool,
    no_write_on_error: bool,
    rollback_performed: bool,
    rollback_succeeded: bool,
    rollback_paths: Vec<String>,
    rollback_errors: Vec<String>,
    error_message: Option<String>,
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
    resource_roots: Vec<String>,
    release_roots: Vec<String>,
    candidates: Vec<RuntimeAssetPathDto>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeAssetValidationEntryDto {
    label: String,
    kind: String,
    source: String,
    path: String,
    required: bool,
    status: String,
    message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeAssetValidationDto {
    layout: RuntimeAssetLayoutDto,
    checks: Vec<RuntimeAssetValidationEntryDto>,
    exists: Vec<RuntimeAssetValidationEntryDto>,
    missing: Vec<RuntimeAssetValidationEntryDto>,
    placeholders: Vec<RuntimeAssetValidationEntryDto>,
    warnings: Vec<String>,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "snake_case")]
struct LegacyExternalCaptureRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    client_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    window_title: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    process_id: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    timeout_ms: Option<u64>,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "snake_case")]
struct LegacyImportCaptureHelperRequest {
    #[serde(default)]
    kind: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    payload: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    image_path: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    window_title: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    client_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    process_id: Option<u32>,
    #[serde(default)]
    metadata: BTreeMap<String, String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    timeout_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct LegacyImportCaptureHelperResult {
    kind: String,
    status: String,
    title: String,
    message: String,
    recoverable: bool,
    imported: bool,
    board_replacement: String,
    warnings: Vec<String>,
    details: BTreeMap<String, String>,
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

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppRuntimeProofRequestDto {
    engine_profile: Option<EngineProfileDto>,
    attempt_engine_launch: Option<bool>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppRuntimeProofDto {
    schema: String,
    status: String,
    platform: String,
    runtime: InstalledAppRuntimeDto,
    bundle: InstalledAppBundleDto,
    assets: RuntimeAssetValidationDto,
    bundled_katago: InstalledAppBundledKataGoDto,
    profile_status: InstalledAppProfileStatusDto,
    engine_launch_attempt: InstalledAppEngineLaunchAttemptDto,
    boundaries: InstalledAppRuntimeBoundariesDto,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppRuntimeDto {
    app_name: String,
    version: String,
    identifier: String,
    source: String,
    tauri_runtime_observed: bool,
    dev_server_required: bool,
    debug_assertions: bool,
    current_exe: Option<String>,
    resource_dir: Option<String>,
    app_data_dir: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppBundleDto {
    product_name: String,
    main_binary_name: String,
    app_bundle_path: Option<String>,
    app_bundle_exists: bool,
    executable_exists: bool,
    resource_dir_exists: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppProfileStatusDto {
    status: String,
    path: Option<String>,
    loaded: bool,
    selected_profile_id: Option<String>,
    profile_count: usize,
    selected_profile_name: Option<String>,
    selected_profile: Option<EngineProfileDto>,
    max_visits: Option<u32>,
    error_message: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppBundledKataGoDto {
    status: String,
    source: String,
    root: Option<String>,
    profile: Option<EngineProfileDto>,
    engine: InstalledAppAssetProofDto,
    model: InstalledAppAssetProofDto,
    config: InstalledAppAssetProofDto,
    warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppAssetProofDto {
    label: String,
    kind: String,
    source: String,
    status: String,
    required: bool,
    sanitized_path: Option<String>,
    size: Option<u64>,
    sha256: Option<String>,
    message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppEngineLaunchAttemptDto {
    attempted: bool,
    status: String,
    recoverable: bool,
    profile_source: String,
    command_spec: Option<CommandSpec>,
    asset_checks: Vec<AssetCheck>,
    asset_proofs: Vec<InstalledAppAssetProofDto>,
    process_id: Option<u32>,
    exit_code: Option<i32>,
    stderr_preview: Option<String>,
    error_kind: Option<String>,
    error_message: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppRuntimeBoundariesDto {
    browser_fallback_used: bool,
    dev_server_started: bool,
    real_release_published: bool,
    production_signed: bool,
    notarized: bool,
    full_legacy_parity: bool,
    large_model_bundled: bool,
    full_katago_parity: bool,
    full_review_parity: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppSgfWorkflowProofRequestDto {
    path: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppSgfWorkflowProofDto {
    schema: String,
    status: String,
    saved_path: String,
    checks: Vec<InstalledAppSgfWorkflowCheckDto>,
    initial_node_count: usize,
    reopened_node_count: usize,
    reopened_move_count: usize,
    comment_persisted: bool,
    property_persisted: bool,
    annotation_persisted: bool,
    append_persisted: bool,
    edit_persisted: bool,
    reorder_persisted: bool,
    delete_persisted: bool,
    save_readback_persisted: bool,
    reopen_invariant: String,
    boundaries: InstalledAppSgfWorkflowBoundariesDto,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppSgfWorkflowCheckDto {
    name: String,
    status: String,
    message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledAppSgfWorkflowBoundariesDto {
    dev_server_required: bool,
    native_dialog_covered: bool,
    webview_dom_covered: bool,
    full_legacy_parity: bool,
}

#[derive(Debug, Clone, Deserialize)]
struct ReadboardExternalCaptureRequestDto {
    #[serde(alias = "source", alias = "captureSource")]
    capture_source: String,
    #[serde(default, alias = "imagePath", alias = "image_path")]
    image_path: Option<String>,
    #[serde(default, alias = "timeoutMs", alias = "timeout_ms")]
    timeout_ms: Option<u64>,
    #[serde(default, alias = "sourceMetadata", alias = "source_metadata")]
    metadata: Option<BTreeMap<String, String>>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ReadboardExternalCaptureResultDto {
    schema: String,
    status: String,
    recoverable: bool,
    operator_initiated: bool,
    user_selection_required: bool,
    source: String,
    capture_source: String,
    source_metadata: BTreeMap<String, String>,
    sanitized_path: Option<String>,
    sha256: Option<String>,
    hash: Option<String>,
    snapshot_id: Option<String>,
    snapshot_hash: Option<String>,
    size: Option<u64>,
    position: Option<PositionDto>,
    decode: ReadboardExternalCaptureDecodeDto,
    snapshot: Option<ReadboardExternalCaptureSnapshotDto>,
    board_replacement: String,
    warnings: Vec<String>,
    message: Option<String>,
    error_message: Option<String>,
    metadata: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ReadboardExternalCaptureDecodeDto {
    attempted: bool,
    status: String,
    board_size: Option<u8>,
    stone_count: Option<usize>,
    black_stones: Option<usize>,
    white_stones: Option<usize>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ReadboardExternalCaptureSnapshotDto {
    snapshot_id: String,
    position_move_number: u32,
    to_play: String,
    warnings: Vec<String>,
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
fn native_menu_contract() -> NativeMenuContractDto {
    native_menu_contract_dto()
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

#[tauri::command]
fn installed_app_runtime_proof(
    app_handle: AppHandle,
    request: Option<InstalledAppRuntimeProofRequestDto>,
) -> InstalledAppRuntimeProofDto {
    let current_exe = std::env::current_exe().ok();
    let resource_dir = app_handle.path().resource_dir().ok();
    let app_data_dir = app_handle.path().app_data_dir().ok();
    let app_bundle_path = current_exe.as_deref().and_then(derive_macos_app_bundle_path);
    let source = installed_app_runtime_source(current_exe.as_deref(), resource_dir.as_deref());
    let asset_layout = resolve_runtime_asset_layout_for_paths(
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
        resource_dir.clone(),
    );
    let assets = validate_runtime_asset_layout_from_layout(asset_layout);
    let bundled_katago = resolve_installed_app_bundled_katago(&assets);
    let profile_status = installed_app_profile_status(
        &app_handle,
        request.as_ref().and_then(|value| value.engine_profile.clone()),
    );
    let attempt_engine_launch = request
        .as_ref()
        .and_then(|value| value.attempt_engine_launch)
        .unwrap_or(true);
    let (launch_profile, profile_source) = installed_app_launch_profile(
        profile_status.selected_profile.clone(),
        &profile_status,
        &bundled_katago,
    );
    let engine_launch_attempt = installed_app_engine_launch_attempt(
        launch_profile,
        attempt_engine_launch,
        profile_source.as_str(),
        resource_dir.clone(),
    );

    InstalledAppRuntimeProofDto {
        schema: "lizzieyzy.installed-app-runtime-proof.v1".to_string(),
        status: "ok".to_string(),
        platform: std::env::consts::OS.to_string(),
        runtime: InstalledAppRuntimeDto {
            app_name: "LizzieYzy Next".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            identifier: "org.lizzieyzy.next".to_string(),
            source,
            tauri_runtime_observed: true,
            dev_server_required: false,
            debug_assertions: cfg!(debug_assertions),
            current_exe: current_exe.as_ref().map(|path| path_to_string(path)),
            resource_dir: resource_dir.as_ref().map(|path| path_to_string(path)),
            app_data_dir: app_data_dir.as_ref().map(|path| path_to_string(path)),
        },
        bundle: InstalledAppBundleDto {
            product_name: "LizzieYzy Next".to_string(),
            main_binary_name: "lizzieyzy-next-desktop".to_string(),
            app_bundle_path: app_bundle_path.as_ref().map(|path| path_to_string(path)),
            app_bundle_exists: app_bundle_path.as_deref().is_some_and(Path::exists),
            executable_exists: current_exe.as_deref().is_some_and(Path::exists),
            resource_dir_exists: resource_dir.as_deref().is_some_and(Path::exists),
        },
        assets,
        bundled_katago,
        profile_status,
        engine_launch_attempt,
        boundaries: InstalledAppRuntimeBoundariesDto {
            browser_fallback_used: false,
            dev_server_started: false,
            real_release_published: false,
            production_signed: false,
            notarized: false,
            full_legacy_parity: false,
            large_model_bundled: false,
            full_katago_parity: false,
            full_review_parity: false,
        },
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

fn installed_app_runtime_source(current_exe: Option<&Path>, resource_dir: Option<&Path>) -> String {
    if current_exe.and_then(derive_macos_app_bundle_path).is_some() {
        return "packaged-macos-app".to_string();
    }
    if cfg!(debug_assertions) {
        return "tauri-dev".to_string();
    }
    if resource_dir.is_some() {
        return "packaged-app".to_string();
    }
    "unknown".to_string()
}

fn derive_macos_app_bundle_path(executable_path: &Path) -> Option<PathBuf> {
    executable_path
        .ancestors()
        .find(|ancestor| ancestor.extension().is_some_and(|extension| extension == "app"))
        .map(Path::to_path_buf)
}

fn path_to_string(path: &Path) -> String {
    path.display().to_string()
}

fn installed_app_profile_status(
    app_handle: &AppHandle,
    requested_profile: Option<EngineProfileDto>,
) -> InstalledAppProfileStatusDto {
    if let Some(profile) = requested_profile {
        return InstalledAppProfileStatusDto {
            status: "requestProfile".to_string(),
            path: None,
            loaded: true,
            selected_profile_id: None,
            profile_count: 1,
            selected_profile_name: Some(profile.name.clone()),
            selected_profile: Some(profile),
            max_visits: None,
            error_message: None,
        };
    }

    let path = match engine_profile_path(app_handle) {
        Ok(path) => path,
        Err(err) => {
            return InstalledAppProfileStatusDto {
                status: "error".to_string(),
                path: None,
                loaded: false,
                selected_profile_id: None,
                profile_count: 0,
                selected_profile_name: None,
                selected_profile: None,
                max_visits: None,
                error_message: Some(err),
            };
        }
    };

    match fs::read_to_string(&path) {
        Ok(contents) => match parse_engine_profiles_settings(&contents, &path) {
            Ok(settings) => installed_app_profile_status_from_settings("loaded", Some(path), settings),
            Err(err) => InstalledAppProfileStatusDto {
                status: "error".to_string(),
                path: Some(path.display().to_string()),
                loaded: false,
                selected_profile_id: None,
                profile_count: 0,
                selected_profile_name: None,
                selected_profile: None,
                max_visits: None,
                error_message: Some(err),
            },
        },
        Err(err) if err.kind() == ErrorKind::NotFound => installed_app_profile_status_from_settings(
            "defaultMissingFile",
            Some(path),
            default_engine_profiles_settings(),
        ),
        Err(err) => InstalledAppProfileStatusDto {
            status: "error".to_string(),
            path: Some(path.display().to_string()),
            loaded: false,
            selected_profile_id: None,
            profile_count: 0,
            selected_profile_name: None,
            selected_profile: None,
            max_visits: None,
            error_message: Some(format!("failed to read engine profiles: {err}")),
        },
    }
}

fn installed_app_profile_status_from_settings(
    status: &str,
    path: Option<PathBuf>,
    settings: EngineProfilesSettingsDto,
) -> InstalledAppProfileStatusDto {
    let selected = selected_engine_profile_record(&settings)
        .or_else(|| settings.profiles.first())
        .cloned();
    InstalledAppProfileStatusDto {
        status: status.to_string(),
        path: path.as_ref().map(|path| path.display().to_string()),
        loaded: status == "loaded",
        selected_profile_id: Some(settings.selected_profile_id),
        profile_count: settings.profiles.len(),
        selected_profile_name: selected.as_ref().map(|record| record.profile.name.clone()),
        selected_profile: selected.as_ref().map(|record| record.profile.clone()),
        max_visits: selected.map(|record| record.max_visits),
        error_message: None,
    }
}

fn installed_app_launch_profile(
    selected_profile: Option<EngineProfileDto>,
    profile_status: &InstalledAppProfileStatusDto,
    bundled_katago: &InstalledAppBundledKataGoDto,
) -> (Option<EngineProfileDto>, String) {
    if let Some(profile) = selected_profile {
        let source = if profile_status.status == "requestProfile" {
            "requestProfile"
        } else {
            "userLocalProfile"
        };
        if profile_has_launch_assets(&profile) {
            return (Some(profile), source.to_string());
        }
        if let Some(bundled_profile) = bundled_katago.profile.clone() {
            return (Some(bundled_profile), "bundledAssetFallback".to_string());
        }
        return (Some(profile), source.to_string());
    }
    if let Some(bundled_profile) = bundled_katago.profile.clone() {
        return (Some(bundled_profile), "bundledAsset".to_string());
    }
    (None, "missing".to_string())
}

fn profile_has_launch_assets(profile: &EngineProfileDto) -> bool {
    if profile.engine_path.trim().is_empty() {
        return false;
    }
    if !matches!(profile.backend, EngineBackend::KataGoAnalysis) {
        return true;
    }
    profile
        .model_path
        .as_deref()
        .is_some_and(|value| !value.trim().is_empty())
        && profile
            .config_path
            .as_deref()
            .is_some_and(|value| !value.trim().is_empty())
}

fn installed_app_engine_launch_attempt(
    profile: Option<EngineProfileDto>,
    attempt_engine_launch: bool,
    profile_source: &str,
    bundled_root: Option<PathBuf>,
) -> InstalledAppEngineLaunchAttemptDto {
    let Some(profile) = profile else {
        return installed_app_engine_launch_skipped(
            "no selected engine profile or bundled KataGo asset is available",
        );
    };
    let raw_asset_checks = engine_asset_checks(profile.clone());
    let asset_proofs =
        installed_app_asset_proofs_from_profile(&profile, profile_source, bundled_root.as_deref());
    let asset_checks =
        sanitize_asset_checks_for_proof(raw_asset_checks, bundled_root.as_deref(), profile_source);
    if !attempt_engine_launch {
        return InstalledAppEngineLaunchAttemptDto {
            attempted: false,
            status: "skipped".to_string(),
            recoverable: true,
            profile_source: profile_source.to_string(),
            command_spec: None,
            asset_checks,
            asset_proofs,
            process_id: None,
            exit_code: None,
            stderr_preview: None,
            error_kind: None,
            error_message: Some("engine launch attempt disabled by request".to_string()),
        };
    }

    let spec = match build_command_spec(&profile) {
        Ok(spec) => spec,
        Err(err) => {
            return InstalledAppEngineLaunchAttemptDto {
                attempted: true,
                status: "unavailable".to_string(),
                recoverable: true,
                profile_source: profile_source.to_string(),
                command_spec: None,
                asset_checks,
                asset_proofs,
                process_id: None,
                exit_code: None,
                stderr_preview: None,
                error_kind: Some(engine_error_kind(&err).to_string()),
                error_message: Some(sanitize_runtime_proof_message(&err.to_string())),
            };
        }
    };
    let proof_spec = sanitize_command_spec_for_proof(&spec, bundled_root.as_deref(), profile_source);

    let mut command = Command::new(&spec.program);
    command
        .args(&spec.args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(working_dir) = spec.working_dir.as_ref().filter(|value| !value.trim().is_empty()) {
        command.current_dir(working_dir);
    }
    for (key, value) in &spec.env {
        command.env(key, value);
    }

    match command.spawn() {
        Ok(mut child) => {
            let process_id = child.id();
            let _ = child.kill();
            match child.wait_with_output() {
                Ok(output) => InstalledAppEngineLaunchAttemptDto {
                    attempted: true,
                    status: "launched".to_string(),
                    recoverable: false,
                    profile_source: profile_source.to_string(),
                    command_spec: Some(proof_spec),
                    asset_checks,
                    asset_proofs,
                    process_id: Some(process_id),
                    exit_code: output.status.code(),
                    stderr_preview: stderr_preview(&output.stderr)
                        .map(|value| sanitize_runtime_proof_message(&value)),
                    error_kind: None,
                    error_message: None,
                },
                Err(err) => InstalledAppEngineLaunchAttemptDto {
                    attempted: true,
                    status: "error".to_string(),
                    recoverable: true,
                    profile_source: profile_source.to_string(),
                    command_spec: Some(proof_spec),
                    asset_checks,
                    asset_proofs,
                    process_id: Some(process_id),
                    exit_code: None,
                    stderr_preview: None,
                    error_kind: Some("waitFailed".to_string()),
                    error_message: Some(sanitize_runtime_proof_message(&format!(
                        "engine spawned but wait failed: {err}"
                    ))),
                },
            }
        }
        Err(err) => InstalledAppEngineLaunchAttemptDto {
            attempted: true,
            status: "unavailable".to_string(),
            recoverable: true,
            profile_source: profile_source.to_string(),
            command_spec: Some(proof_spec),
            asset_checks,
            asset_proofs,
            process_id: None,
            exit_code: None,
            stderr_preview: None,
            error_kind: Some("spawnFailed".to_string()),
            error_message: Some(sanitize_runtime_proof_message(&format!(
                "failed to spawn engine: {err}"
            ))),
        },
    }
}

fn installed_app_engine_launch_skipped(message: &str) -> InstalledAppEngineLaunchAttemptDto {
    InstalledAppEngineLaunchAttemptDto {
        attempted: false,
        status: "skipped".to_string(),
        recoverable: true,
        profile_source: "missing".to_string(),
        command_spec: None,
        asset_checks: Vec::new(),
        asset_proofs: Vec::new(),
        process_id: None,
        exit_code: None,
        stderr_preview: None,
        error_kind: None,
        error_message: Some(message.to_string()),
    }
}

fn resolve_installed_app_bundled_katago(assets: &RuntimeAssetValidationDto) -> InstalledAppBundledKataGoDto {
    let root = assets
        .layout
        .resource_roots
        .first()
        .or_else(|| assets.layout.release_roots.first())
        .map(PathBuf::from);
    let root_ref = root.as_deref();
    let engine_dir = runtime_asset_candidate_path(assets, "KataGo bin", "resource_dir");
    let model_dir = runtime_asset_candidate_path(assets, "KataGo models", "resource_dir");
    let config_dir = runtime_asset_candidate_path(assets, "KataGo configs", "resource_dir");

    let (engine, engine_path) = installed_app_bundled_asset_proof(
        "engine binary",
        "file",
        engine_dir.as_deref(),
        root_ref,
        is_katago_engine_asset,
    );
    let (model, model_path) = installed_app_bundled_asset_proof(
        "model",
        "file",
        model_dir.as_deref(),
        root_ref,
        is_katago_model_asset,
    );
    let (config, config_path) = installed_app_bundled_asset_proof(
        "config",
        "file",
        config_dir.as_deref(),
        root_ref,
        is_katago_config_asset,
    );

    let complete = engine_path.is_some() && model_path.is_some() && config_path.is_some();
    let status = if complete {
        "available"
    } else if root.is_some() {
        "incomplete"
    } else {
        "unavailable"
    };
    let mut warnings = Vec::new();
    if !complete {
        warnings.push(
            "Bundled KataGo launch proof is unavailable unless runtime/katago/bin, models, and configs all contain real assets.".to_string(),
        );
    }
    warnings.push(
        "No large model, signed release, or full analysis parity is claimed by this backend proof."
            .to_string(),
    );

    let profile = match (engine_path, model_path, config_path) {
        (Some(engine_path), Some(model_path), Some(config_path)) => Some(EngineProfileDto {
            name: "Bundled KataGo".to_string(),
            engine_path: engine_path.display().to_string(),
            model_path: Some(model_path.display().to_string()),
            config_path: Some(config_path.display().to_string()),
            working_dir: root.as_ref().map(|path| path.display().to_string()),
            backend: EngineBackend::KataGoAnalysis,
        }),
        _ => None,
    };

    InstalledAppBundledKataGoDto {
        status: status.to_string(),
        source: "bundledAsset".to_string(),
        root: root
            .as_ref()
            .map(|path| sanitize_runtime_proof_path(path, root_ref, "bundledAsset")),
        profile,
        engine,
        model,
        config,
        warnings,
    }
}

fn runtime_asset_candidate_path(
    assets: &RuntimeAssetValidationDto,
    label: &str,
    source: &str,
) -> Option<PathBuf> {
    assets
        .layout
        .candidates
        .iter()
        .find(|candidate| candidate.label == label && candidate.source == source)
        .map(|candidate| PathBuf::from(&candidate.path))
}

fn installed_app_bundled_asset_proof(
    label: &str,
    kind: &str,
    directory: Option<&Path>,
    root: Option<&Path>,
    matches_asset: fn(&str) -> bool,
) -> (InstalledAppAssetProofDto, Option<PathBuf>) {
    let source = "bundledAsset";
    let Some(directory) = directory else {
        return (
            installed_app_asset_proof_missing(
                label,
                kind,
                source,
                "bundled runtime asset directory is not available",
            ),
            None,
        );
    };
    let Some(path) = find_runtime_asset_file(directory, 3, matches_asset) else {
        return (
            installed_app_asset_proof_missing(
                label,
                kind,
                source,
                &format!("bundled {label} asset is missing or only a placeholder"),
            ),
            None,
        );
    };
    (
        installed_app_asset_proof_for_path(label, kind, source, &path, root, true),
        Some(path),
    )
}

fn installed_app_asset_proofs_from_profile(
    profile: &EngineProfileDto,
    profile_source: &str,
    bundled_root: Option<&Path>,
) -> Vec<InstalledAppAssetProofDto> {
    engine_asset_checks(profile.clone())
        .into_iter()
        .map(|check| {
            let path = PathBuf::from(&check.path);
            let kind = if path.is_dir() { "directory" } else { "file" };
            if check.exists {
                installed_app_asset_proof_for_path(
                    &check.label,
                    kind,
                    profile_source,
                    &path,
                    bundled_root,
                    check.required,
                )
            } else {
                InstalledAppAssetProofDto {
                    label: check.label,
                    kind: kind.to_string(),
                    source: profile_source.to_string(),
                    status: "missing".to_string(),
                    required: check.required,
                    sanitized_path: Some(sanitize_runtime_proof_path(&path, bundled_root, profile_source)),
                    size: None,
                    sha256: None,
                    message: "required engine/profile asset is missing or unavailable".to_string(),
                }
            }
        })
        .collect()
}

fn sanitize_asset_checks_for_proof(
    checks: Vec<AssetCheck>,
    root: Option<&Path>,
    source: &str,
) -> Vec<AssetCheck> {
    checks
        .into_iter()
        .map(|mut check| {
            check.path = sanitize_runtime_proof_arg(&check.path, root, source);
            check
        })
        .collect()
}

fn sanitize_command_spec_for_proof(spec: &CommandSpec, root: Option<&Path>, source: &str) -> CommandSpec {
    CommandSpec {
        program: sanitize_runtime_proof_arg(&spec.program, root, source),
        args: spec
            .args
            .iter()
            .map(|arg| sanitize_runtime_proof_arg(arg, root, source))
            .collect(),
        working_dir: spec
            .working_dir
            .as_ref()
            .map(|path| sanitize_runtime_proof_arg(path, root, source)),
        env: spec
            .env
            .iter()
            .map(|(key, value)| (key.clone(), sanitize_runtime_proof_arg(value, root, source)))
            .collect(),
    }
}

fn installed_app_asset_proof_missing(
    label: &str,
    kind: &str,
    source: &str,
    message: &str,
) -> InstalledAppAssetProofDto {
    InstalledAppAssetProofDto {
        label: label.to_string(),
        kind: kind.to_string(),
        source: source.to_string(),
        status: "missing".to_string(),
        required: true,
        sanitized_path: None,
        size: None,
        sha256: None,
        message: message.to_string(),
    }
}

fn installed_app_asset_proof_for_path(
    label: &str,
    kind: &str,
    source: &str,
    path: &Path,
    root: Option<&Path>,
    required: bool,
) -> InstalledAppAssetProofDto {
    match fs::metadata(path) {
        Ok(metadata) if metadata.is_file() => {
            let (sha256, message) = match fs::read(path) {
                Ok(bytes) => (
                    Some(sha256_hex(&bytes)),
                    format!("{label} asset exists and was hashed for installed-app proof"),
                ),
                Err(err) => (
                    None,
                    sanitize_runtime_proof_message(&format!(
                        "{label} asset exists but could not be hashed: {err}"
                    )),
                ),
            };
            InstalledAppAssetProofDto {
                label: label.to_string(),
                kind: kind.to_string(),
                source: source.to_string(),
                status: "exists".to_string(),
                required,
                sanitized_path: Some(sanitize_runtime_proof_path(path, root, source)),
                size: Some(metadata.len()),
                sha256,
                message,
            }
        }
        Ok(metadata) if metadata.is_dir() => InstalledAppAssetProofDto {
            label: label.to_string(),
            kind: "directory".to_string(),
            source: source.to_string(),
            status: "exists".to_string(),
            required,
            sanitized_path: Some(sanitize_runtime_proof_path(path, root, source)),
            size: None,
            sha256: None,
            message: format!("{label} directory exists for installed-app proof"),
        },
        Ok(_) => InstalledAppAssetProofDto {
            label: label.to_string(),
            kind: kind.to_string(),
            source: source.to_string(),
            status: "placeholder".to_string(),
            required,
            sanitized_path: Some(sanitize_runtime_proof_path(path, root, source)),
            size: None,
            sha256: None,
            message: format!("{label} path exists but is not a usable file or directory"),
        },
        Err(_) => InstalledAppAssetProofDto {
            label: label.to_string(),
            kind: kind.to_string(),
            source: source.to_string(),
            status: "missing".to_string(),
            required,
            sanitized_path: Some(sanitize_runtime_proof_path(path, root, source)),
            size: None,
            sha256: None,
            message: format!("{label} asset is missing for installed-app proof"),
        },
    }
}

fn find_runtime_asset_file(
    path: &Path,
    max_depth: usize,
    matches_asset: fn(&str) -> bool,
) -> Option<PathBuf> {
    let mut matches = Vec::new();
    collect_runtime_asset_files(path, max_depth, matches_asset, &mut matches);
    matches.sort();
    matches.into_iter().next()
}

fn collect_runtime_asset_files(
    path: &Path,
    max_depth: usize,
    matches_asset: fn(&str) -> bool,
    matches: &mut Vec<PathBuf>,
) {
    let entries = match fs::read_dir(path) {
        Ok(entries) => entries,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let entry_path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if is_placeholder_asset_name(&name) {
            continue;
        }
        let metadata = match entry.metadata() {
            Ok(metadata) => metadata,
            Err(_) => continue,
        };
        if metadata.is_file() && matches_asset(&name) {
            matches.push(entry_path);
        } else if metadata.is_dir() && max_depth > 0 {
            collect_runtime_asset_files(&entry_path, max_depth - 1, matches_asset, matches);
        }
    }
}

fn is_katago_engine_asset(name: &str) -> bool {
    let name = name.to_ascii_lowercase();
    name == "katago" || name == "katago.exe" || name.starts_with("katago-")
}

fn sanitize_runtime_proof_path(path: &Path, root: Option<&Path>, source: &str) -> String {
    if let Some(root) = root {
        if let Ok(relative) = path.strip_prefix(root) {
            let relative = relative.display().to_string();
            return if relative.is_empty() {
                format!("{source}:<root>")
            } else {
                format!("{source}:{relative}")
            };
        }
    }
    if let Some(file_name) = path.file_name().and_then(|value| value.to_str()) {
        return format!("{source}:{file_name}");
    }
    format!("{source}:<path>")
}

fn sanitize_runtime_proof_arg(value: &str, root: Option<&Path>, source: &str) -> String {
    let trimmed = value.trim();
    if trimmed.starts_with('/')
        || trimmed.starts_with('~')
        || trimmed.starts_with("/private/")
        || trimmed.starts_with("/var/folders/")
        || trimmed.starts_with("/tmp/")
        || trimmed.contains(":\\")
        || trimmed.contains(":/")
    {
        if trimmed.contains(":\\") {
            return format!(
                "{source}:{}",
                trimmed.rsplit(['\\', '/']).next().unwrap_or("<path>")
            );
        }
        sanitize_runtime_proof_path(Path::new(trimmed), root, source)
    } else {
        value.to_string()
    }
}

fn sanitize_runtime_proof_message(message: &str) -> String {
    sanitize_capture_message(message)
}

fn engine_error_kind(err: &EngineManagerError) -> &'static str {
    match err {
        EngineManagerError::MissingEnginePath => "missingEnginePath",
        EngineManagerError::MissingModelPath => "missingModelPath",
        EngineManagerError::MissingConfigPath => "missingConfigPath",
        EngineManagerError::EnginePathNotFound { .. } => "enginePathNotFound",
        EngineManagerError::ModelPathNotFound { .. } => "modelPathNotFound",
        EngineManagerError::ConfigPathNotFound { .. } => "configPathNotFound",
        EngineManagerError::WorkingDirNotFound { .. } => "workingDirNotFound",
        EngineManagerError::Spawn { .. } => "spawnFailed",
        EngineManagerError::StdinWrite { .. } => "stdinWriteFailed",
        EngineManagerError::StdoutRead { .. } => "stdoutReadFailed",
        EngineManagerError::Wait { .. } => "waitFailed",
        EngineManagerError::MissingStdout { .. } => "missingStdout",
        EngineManagerError::InsufficientStdout { .. } => "insufficientStdout",
        EngineManagerError::NonZeroExit { .. } => "nonZeroExit",
        EngineManagerError::Timeout { .. } => "timeout",
        EngineManagerError::Cancelled { .. } => "cancelled",
    }
}

fn stderr_preview(stderr: &[u8]) -> Option<String> {
    let value = String::from_utf8_lossy(stderr).trim().to_string();
    if value.is_empty() {
        None
    } else {
        Some(value.chars().take(500).collect())
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
    readboard_sidecar::sync_snapshot_image(&request)
        .map(|outcome| outcome.into_dto())
        .map_err(readboard_error)
}

#[tauri::command]
fn readboard_external_capture(
    request: ReadboardExternalCaptureRequestDto,
) -> Result<ReadboardExternalCaptureResultDto, ProviderError> {
    readboard_external_capture_with_runner(request, run_macos_interactive_screencapture)
}

fn readboard_external_capture_with_runner(
    request: ReadboardExternalCaptureRequestDto,
    screencapture_runner: fn(Duration) -> ReadboardCaptureFileOutcome,
) -> Result<ReadboardExternalCaptureResultDto, ProviderError> {
    #[cfg(not(target_os = "macos"))]
    let _ = screencapture_runner;
    let capture_source = request.capture_source.trim().to_ascii_lowercase();
    if capture_source.is_empty() {
        return Err(invalid_request(
            "readboard_external_capture requires a non-empty source or captureSource",
        ));
    }
    validate_timeout_ms(request.timeout_ms, "readboard_external_capture")?;
    let metadata = request.metadata.unwrap_or_default();
    match capture_source.as_str() {
        "local_image" | "local_image_file" | "image_path" => {
            let path = request
                .image_path
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| {
                    invalid_request("readboard_external_capture local_image requires imagePath")
                })?;
            Ok(readboard_external_capture_decode_path(
                Path::new(path),
                "local_image",
                false,
                false,
                metadata,
            ))
        }
        "operator_selected_file" | "selected_file" | "file" => {
            let path = request
                .image_path
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| {
                    invalid_request("readboard_external_capture operator_selected_file requires imagePath")
                })?;
            Ok(readboard_external_capture_decode_path(
                Path::new(path),
                "operator_selected_file",
                true,
                true,
                metadata,
            ))
        }
        "screen"
        | "window"
        | "macos_interactive_capture"
        | "macos_interactive_screencapture"
        | "interactive_screencapture"
        | "external_window_capture" => {
            #[cfg(not(target_os = "macos"))]
            {
                Ok(readboard_external_capture_status(
                    "unsupported",
                    true,
                    true,
                    true,
                    "macos_interactive_capture",
                    metadata,
                    Some("interactive screencapture is only supported on macOS".to_string()),
                ))
            }
            #[cfg(target_os = "macos")]
            {
                let timeout =
                    Duration::from_millis(request.timeout_ms.unwrap_or(120_000).clamp(1_000, 300_000));
                let source = normalize_capture_source(&capture_source);
                match screencapture_runner(timeout) {
                    ReadboardCaptureFileOutcome::Captured { path } => Ok(
                        readboard_external_capture_decode_path(&path, source, true, true, metadata),
                    ),
                    ReadboardCaptureFileOutcome::Cancelled { message } => {
                        Ok(readboard_external_capture_status(
                            "cancelled",
                            true,
                            true,
                            true,
                            source,
                            metadata,
                            Some(sanitize_capture_message(&message)),
                        ))
                    }
                    ReadboardCaptureFileOutcome::PermissionDenied { message } => {
                        Ok(readboard_external_capture_status(
                            "permission_denied",
                            true,
                            true,
                            true,
                            source,
                            metadata,
                            Some(sanitize_capture_message(&message)),
                        ))
                    }
                    ReadboardCaptureFileOutcome::Timeout { message } => {
                        Ok(readboard_external_capture_status(
                            "timeout",
                            true,
                            true,
                            true,
                            source,
                            metadata,
                            Some(sanitize_capture_message(&message)),
                        ))
                    }
                    ReadboardCaptureFileOutcome::Unsupported { message } => {
                        Ok(readboard_external_capture_status(
                            "unsupported",
                            true,
                            true,
                            true,
                            source,
                            metadata,
                            Some(sanitize_capture_message(&message)),
                        ))
                    }
                }
            }
        }
        other => Err(invalid_request(format!(
            "readboard_external_capture unsupported captureSource `{other}`"
        ))),
    }
}

#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
enum ReadboardCaptureFileOutcome {
    Captured { path: PathBuf },
    Cancelled { message: String },
    PermissionDenied { message: String },
    Timeout { message: String },
    Unsupported { message: String },
}

#[cfg(target_os = "macos")]
fn run_macos_interactive_screencapture(timeout: Duration) -> ReadboardCaptureFileOutcome {
    let path = std::env::temp_dir().join(format!("readboard-external-capture-{}.png", Uuid::new_v4()));
    let mut child = match Command::new("screencapture")
        .arg("-i")
        .arg(&path)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(child) => child,
        Err(err) => {
            return ReadboardCaptureFileOutcome::Unsupported {
                message: format!("failed to start macOS screencapture: {err}"),
            };
        }
    };
    let deadline = std::time::Instant::now() + timeout;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => {
                let output = child.wait_with_output();
                let stderr = output
                    .as_ref()
                    .ok()
                    .map(|output| String::from_utf8_lossy(&output.stderr).to_string())
                    .unwrap_or_default();
                let success = output.as_ref().is_ok_and(|output| output.status.success())
                    && fs::metadata(&path)
                        .map(|metadata| metadata.len() > 0)
                        .unwrap_or(false);
                if success {
                    return ReadboardCaptureFileOutcome::Captured { path };
                }
                let _ = fs::remove_file(&path);
                if stderr.to_ascii_lowercase().contains("permission")
                    || stderr.to_ascii_lowercase().contains("not authorized")
                {
                    return ReadboardCaptureFileOutcome::PermissionDenied {
                        message: sanitize_capture_error(
                            &stderr,
                            "macOS screen recording permission was denied",
                        ),
                    };
                }
                return ReadboardCaptureFileOutcome::Cancelled {
                    message: sanitize_capture_error(&stderr, "operator cancelled interactive screencapture"),
                };
            }
            Ok(None) if std::time::Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(100));
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait_with_output();
                let _ = fs::remove_file(&path);
                return ReadboardCaptureFileOutcome::Timeout {
                    message: format!(
                        "interactive screencapture timed out after {}ms",
                        timeout.as_millis()
                    ),
                };
            }
            Err(err) => {
                let _ = child.kill();
                let _ = fs::remove_file(&path);
                return ReadboardCaptureFileOutcome::Cancelled {
                    message: format!("failed while waiting for screencapture: {err}"),
                };
            }
        }
    }
}

#[cfg(not(target_os = "macos"))]
fn run_macos_interactive_screencapture(_timeout: Duration) -> ReadboardCaptureFileOutcome {
    match std::env::var("LIZZIEYZY_READBOARD_CAPTURE_TEST_STATUS")
        .unwrap_or_default()
        .as_str()
    {
        "captured" => ReadboardCaptureFileOutcome::Captured {
            path: std::env::temp_dir().join("readboard-external-capture-test.png"),
        },
        "cancelled" => ReadboardCaptureFileOutcome::Cancelled {
            message: "operator cancelled interactive screencapture".to_string(),
        },
        "permission_denied" => ReadboardCaptureFileOutcome::PermissionDenied {
            message: "macOS screen recording permission was denied".to_string(),
        },
        "timeout" => ReadboardCaptureFileOutcome::Timeout {
            message: "interactive screencapture timed out".to_string(),
        },
        _ => ReadboardCaptureFileOutcome::Unsupported {
            message: "interactive screencapture is only supported on macOS".to_string(),
        },
    }
}

fn readboard_external_capture_decode_path(
    path: &Path,
    capture_source: &str,
    operator_initiated: bool,
    user_selection_required: bool,
    metadata: BTreeMap<String, String>,
) -> ReadboardExternalCaptureResultDto {
    let sanitized_path = sanitize_capture_path_for_source(path, capture_source);
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(err) => {
            return readboard_external_capture_status(
                "decode_error",
                true,
                operator_initiated,
                user_selection_required,
                capture_source,
                metadata,
                Some(sanitize_capture_message(&format!(
                    "failed to read selected image `{sanitized_path}`: {err}"
                ))),
            );
        }
    };
    let sha256 = sha256_hex(&bytes);
    let size = bytes.len() as u64;
    let request = ReadboardSidecarSyncSnapshotRequest {
        sgf_text: None,
        snapshot_id: Some("external-capture-preview".to_string()),
        image_path: Some(path.display().to_string()),
        image_base64: None,
        endpoint: None,
        timeout_ms: None,
        metadata: BTreeMap::new(),
    };
    match readboard_sidecar::sync_snapshot_image(&request) {
        Ok(outcome) => {
            let dto = outcome.into_dto();
            let position = dto.position.clone();
            let snapshot_id = Some(dto.snapshot_id.clone());
            let snapshot_hash = position.as_ref().and_then(snapshot_position_hash);
            let mut warnings = dto.warnings.clone();
            warnings.push(readboard_external_capture_scope_warning(capture_source));
            let decode = dto
                .position
                .as_ref()
                .map(readboard_external_capture_decode_summary)
                .unwrap_or(ReadboardExternalCaptureDecodeDto {
                    attempted: true,
                    status: "decode_error".to_string(),
                    board_size: None,
                    stone_count: None,
                    black_stones: None,
                    white_stones: None,
                });
            let snapshot = dto
                .position
                .as_ref()
                .map(|position| ReadboardExternalCaptureSnapshotDto {
                    snapshot_id: dto.snapshot_id,
                    position_move_number: position.move_number,
                    to_play: format!("{:?}", position.to_play),
                    warnings: dto.warnings.clone(),
                });
            ReadboardExternalCaptureResultDto {
                schema: "lizzieyzy.readboard-external-capture.v1".to_string(),
                status: "captured".to_string(),
                recoverable: false,
                operator_initiated,
                user_selection_required,
                source: capture_source.to_string(),
                capture_source: capture_source.to_string(),
                source_metadata: metadata.clone(),
                sanitized_path: Some(sanitized_path),
                sha256: Some(sha256.clone()),
                hash: Some(sha256),
                snapshot_id,
                snapshot_hash,
                size: Some(size),
                position,
                decode,
                snapshot,
                board_replacement: "none".to_string(),
                warnings,
                message: None,
                error_message: None,
                metadata,
            }
        }
        Err(err) => readboard_external_capture_status_with_file(
            "decode_error",
            true,
            operator_initiated,
            user_selection_required,
            capture_source,
            metadata,
            Some(sanitize_readboard_capture_error(&err)),
            Some(sanitized_path),
            Some(sha256),
            Some(size),
        ),
    }
}

fn readboard_external_capture_decode_summary(position: &PositionDto) -> ReadboardExternalCaptureDecodeDto {
    let black = position
        .stones
        .iter()
        .filter(|stone| stone.color == app_model::PlayerColor::Black)
        .count();
    let white = position
        .stones
        .iter()
        .filter(|stone| stone.color == app_model::PlayerColor::White)
        .count();
    ReadboardExternalCaptureDecodeDto {
        attempted: true,
        status: "success".to_string(),
        board_size: Some(position.board_size),
        stone_count: Some(position.stones.len()),
        black_stones: Some(black),
        white_stones: Some(white),
    }
}

fn readboard_external_capture_status(
    status: &str,
    recoverable: bool,
    operator_initiated: bool,
    user_selection_required: bool,
    capture_source: &str,
    metadata: BTreeMap<String, String>,
    error_message: Option<String>,
) -> ReadboardExternalCaptureResultDto {
    readboard_external_capture_status_with_file(
        status,
        recoverable,
        operator_initiated,
        user_selection_required,
        capture_source,
        metadata,
        error_message,
        None,
        None,
        None,
    )
}

#[allow(clippy::too_many_arguments)]
fn readboard_external_capture_status_with_file(
    status: &str,
    recoverable: bool,
    operator_initiated: bool,
    user_selection_required: bool,
    capture_source: &str,
    metadata: BTreeMap<String, String>,
    error_message: Option<String>,
    sanitized_path: Option<String>,
    sha256: Option<String>,
    size: Option<u64>,
) -> ReadboardExternalCaptureResultDto {
    let warnings = vec![readboard_external_capture_scope_warning(capture_source)];
    ReadboardExternalCaptureResultDto {
        schema: "lizzieyzy.readboard-external-capture.v1".to_string(),
        status: status.to_string(),
        recoverable,
        operator_initiated,
        user_selection_required,
        source: capture_source.to_string(),
        capture_source: capture_source.to_string(),
        source_metadata: metadata.clone(),
        sanitized_path,
        sha256: sha256.clone(),
        hash: sha256,
        snapshot_id: None,
        snapshot_hash: None,
        size,
        position: None,
        decode: ReadboardExternalCaptureDecodeDto {
            attempted: matches!(status, "decode_error"),
            status: status.to_string(),
            board_size: None,
            stone_count: None,
            black_stones: None,
            white_stones: None,
        },
        snapshot: None,
        board_replacement: "none".to_string(),
        warnings,
        message: error_message.clone(),
        error_message,
        metadata,
    }
}

fn sanitize_capture_path(path: &Path) -> String {
    sanitize_capture_path_for_source(path, "local_image")
}

fn sanitize_capture_path_for_source(path: &Path, source: &str) -> String {
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("image");
    let prefix = match source {
        "operator_selected_file" => "operator-selected-file",
        "macos_interactive_capture" | "macos_interactive_screencapture" => "macos-interactive-capture",
        _ => "local-image",
    };
    let parent = path.parent();
    if parent == Some(std::env::temp_dir().as_path()) {
        format!("{prefix}:<tmp>/{file_name}")
    } else {
        format!("{prefix}:{file_name}")
    }
}

#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn normalize_capture_source(source: &str) -> &'static str {
    match source {
        "screen"
        | "window"
        | "macos_interactive_capture"
        | "macos_interactive_screencapture"
        | "interactive_screencapture"
        | "external_window_capture" => "macos_interactive_capture",
        "operator_selected_file" | "selected_file" | "file" => "operator_selected_file",
        _ => "local_image",
    }
}

fn readboard_external_capture_scope_warning(source: &str) -> String {
    match source {
        "local_image" | "local_image_file" => "Readboard external capture decoded an explicit local image file only; this is not arbitrary OCR or target-client capture parity.".to_string(),
        "operator_selected_file" => "Readboard external capture decoded an operator-selected image file only; no target-client discovery or automatic board replacement was performed.".to_string(),
        "macos_interactive_capture" => "Readboard external capture used operator-selected macOS interactive capture only; this is not arbitrary OCR or external client parity.".to_string(),
        _ => "Readboard external capture is scoped preview-only proof; no arbitrary OCR, target-client parity, or automatic board replacement is claimed.".to_string(),
    }
}

fn sanitize_readboard_capture_error(error: &readboard_sidecar::ReadboardSidecarError) -> String {
    match error {
        readboard_sidecar::ReadboardSidecarError::ImageRead { path, message } => {
            let sanitized_path = sanitize_capture_path(Path::new(path));
            format!("failed to read controlled readboard image `{sanitized_path}`: {message}")
        }
        _ => sanitize_capture_message(&error.to_string()),
    }
}

fn sanitize_capture_message(message: &str) -> String {
    let sanitized = message
        .split_whitespace()
        .map(|part| {
            if part.starts_with("/Users/")
                || part.starts_with("/private/")
                || part.starts_with("/var/folders/")
                || part.starts_with("/tmp/")
                || part.starts_with('~')
            {
                "<path>"
            } else {
                part
            }
        })
        .collect::<Vec<_>>()
        .join(" ");
    if sanitized.is_empty() {
        "capture failed".to_string()
    } else {
        sanitized
    }
}

fn snapshot_position_hash(position: &PositionDto) -> Option<String> {
    serde_json::to_vec(position).ok().map(|bytes| sha256_hex(&bytes))
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = sha256_digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn sha256_digest(bytes: &[u8]) -> [u8; 32] {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ];
    let mut h = [
        0x6a09e667u32,
        0xbb67ae85,
        0x3c6ef372,
        0xa54ff53a,
        0x510e527f,
        0x9b05688c,
        0x1f83d9ab,
        0x5be0cd19,
    ];
    let bit_len = (bytes.len() as u64).wrapping_mul(8);
    let mut padded = bytes.to_vec();
    padded.push(0x80);
    while padded.len() % 64 != 56 {
        padded.push(0);
    }
    padded.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in padded.chunks_exact(64) {
        let mut w = [0u32; 64];
        for (index, word) in w.iter_mut().take(16).enumerate() {
            let start = index * 4;
            *word = u32::from_be_bytes([chunk[start], chunk[start + 1], chunk[start + 2], chunk[start + 3]]);
        }
        for index in 16..64 {
            let s0 = w[index - 15].rotate_right(7) ^ w[index - 15].rotate_right(18) ^ (w[index - 15] >> 3);
            let s1 = w[index - 2].rotate_right(17) ^ w[index - 2].rotate_right(19) ^ (w[index - 2] >> 10);
            w[index] = w[index - 16]
                .wrapping_add(s0)
                .wrapping_add(w[index - 7])
                .wrapping_add(s1);
        }

        let mut a = h[0];
        let mut b = h[1];
        let mut c = h[2];
        let mut d = h[3];
        let mut e = h[4];
        let mut f = h[5];
        let mut g = h[6];
        let mut hh = h[7];
        for index in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let temp1 = hh
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[index])
                .wrapping_add(w[index]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }
        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }

    let mut out = [0u8; 32];
    for (index, word) in h.iter().enumerate() {
        out[index * 4..index * 4 + 4].copy_from_slice(&word.to_be_bytes());
    }
    out
}

#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn sanitize_capture_error(raw: &str, fallback: &str) -> String {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        fallback.to_string()
    } else {
        sanitize_capture_message(trimmed)
    }
}

#[tauri::command]
fn legacy_capture_external_window(
    request: LegacyExternalCaptureRequest,
) -> Result<LegacyImportCaptureHelperResult, ProviderError> {
    validate_legacy_external_capture_request(&request)?;
    Ok(legacy_import_capture_unsupported_result(
        "external_window_capture",
        "External window/client capture unsupported",
        "External window/client capture is not implemented in this build. No SGF was imported and the board was not replaced.",
        "real_external_capture_external_gate",
        "External window/client capture helper is a recoverable unsupported path.",
        BTreeMap::new(),
        [
            ("notImplementedBoundary", true),
            ("externalCaptureUnavailable", true),
            ("externalCaptureCovered", false),
            ("nativeWindowCaptureCovered", false),
            ("clientCaptureCovered", false),
            (
                "clientNameProvided",
                request
                    .client_name
                    .as_deref()
                    .is_some_and(|value| !value.trim().is_empty()),
            ),
            (
                "windowTitleProvided",
                request
                    .window_title
                    .as_deref()
                    .is_some_and(|value| !value.trim().is_empty()),
            ),
            ("processIdProvided", request.process_id.is_some()),
        ],
    ))
}

#[tauri::command]
fn legacy_import_capture_helper(
    request: LegacyImportCaptureHelperRequest,
) -> Result<LegacyImportCaptureHelperResult, ProviderError> {
    validate_timeout_ms(request.timeout_ms, "legacy_import_capture_helper")?;
    if request.process_id == Some(0) {
        return Err(invalid_request(
            "legacy_import_capture_helper process_id must be greater than zero",
        ));
    }

    let kind = request.kind.trim().to_string();
    match kind.as_str() {
        "sgf_payload" => Ok(legacy_import_capture_available_result(
            "sgf_payload",
            "SGF/payload helper",
            "Paste SGF or provider JSON into Payload / SGF, then use Import pasted payload.",
            "provider-payload-textarea",
            "provider-import-payload",
            "This helper only describes the visible import path; it does not import until the user presses Import pasted payload.",
            request.metadata,
        )),
        "protocol_snapshot" => Ok(legacy_import_capture_available_result(
            "protocol_snapshot",
            "Protocol snapshot helper",
            "Paste a readboard protocol line, preview the snapshot, then import only after a valid position is shown.",
            "readboard-protocol-textarea",
            "readboard-preview-snapshot",
            "Protocol snapshot import is current-position only and does not reconstruct full game history.",
            request.metadata,
        )),
        "image_ocr" => Ok(legacy_import_capture_unsupported_result(
            "image_ocr",
            "OCR/image helper unsupported",
            "Image OCR import is not implemented in this build. No SGF was imported and the board was not replaced.",
            "real_ocr_external_gate",
            "OCR/image helper is a recoverable unsupported path.",
            request.metadata,
            [
                ("imagePathProvided", request.image_path.is_some_and(|value| !value.trim().is_empty())),
                ("payloadProvided", request.payload.is_some_and(|value| !value.trim().is_empty())),
            ],
        )),
        "external_window_capture" | "external_client_capture" => {
            Ok(legacy_import_capture_unsupported_result(
                &kind,
                "External window/client capture unsupported",
                "External window/client capture is not implemented in this build. No SGF was imported and the board was not replaced.",
                "real_external_capture_external_gate",
                "External window/client capture helper is a recoverable unsupported path.",
                request.metadata,
                [
                    ("notImplementedBoundary", true),
                    ("externalCaptureUnavailable", true),
                    ("externalCaptureCovered", false),
                    ("nativeWindowCaptureCovered", false),
                    ("clientCaptureCovered", false),
                    (
                        "clientNameProvided",
                        request
                            .client_name
                            .is_some_and(|value| !value.trim().is_empty()),
                    ),
                    (
                        "windowTitleProvided",
                        request
                            .window_title
                            .is_some_and(|value| !value.trim().is_empty()),
                    ),
                    ("processIdProvided", request.process_id.is_some()),
                ],
            ))
        }
        "" => Err(invalid_request(
            "legacy_import_capture_helper requires a non-empty kind",
        )),
        other => Err(invalid_request(format!(
            "legacy_import_capture_helper received unsupported kind `{other}`"
        ))),
    }
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
fn installed_app_sgf_workflow_proof(
    request: Option<InstalledAppSgfWorkflowProofRequestDto>,
) -> Result<InstalledAppSgfWorkflowProofDto, String> {
    installed_app_sgf_workflow_proof_for_path(
        request
            .and_then(|request| request.path)
            .map(non_empty_path)
            .transpose()?,
    )
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

fn installed_app_sgf_workflow_proof_for_path(
    requested_path: Option<PathBuf>,
) -> Result<InstalledAppSgfWorkflowProofDto, String> {
    let save_path = requested_path.unwrap_or_else(|| {
        std::env::temp_dir().join(format!("lizzieyzy-installed-sgf-workflow-{}.sgf", Uuid::new_v4()))
    });
    let save_path_string = save_path.display().to_string();
    let mut checks = Vec::new();
    let initial_sgf = installed_app_sgf_workflow_fixture();

    let initial_tree = parse_sgf_tree(initial_sgf.to_string())?
        .ok_or_else(|| "workflow fixture did not produce an SGF tree".to_string())?;
    let initial_node_count = initial_tree.nodes.len();
    sgf_workflow_check(
        &mut checks,
        "app_started_backend",
        true,
        "Tauri backend command executed without requiring a dev server",
    );

    write_sgf_file(save_path_string.clone(), initial_sgf.to_string())?;
    let mut sgf_text = read_sgf_file(save_path_string.clone())?;
    let readback_tree = parse_sgf_tree(sgf_text.clone())?
        .ok_or_else(|| "readback SGF did not produce an SGF tree".to_string())?;
    sgf_workflow_check(
        &mut checks,
        "save_readback_reparse",
        readback_tree.nodes.len() == initial_node_count,
        "initial SGF saved, read back, and reparsed with the same node count",
    );

    let first_move_id = find_sgf_node_by_move(&readback_tree, 1)?.id;
    let branch_id = find_sgf_node_by_comment(&readback_tree, "branch variation")?.id;
    let branch_position = replay_sgf_position_at_node(sgf_text.clone(), branch_id)?;
    let tree_navigation_ok = position_has_stone(&branch_position, 0, 0, app_model::PlayerColor::Black)
        && position_has_stone(&branch_position, 2, 2, app_model::PlayerColor::White);
    sgf_workflow_check(
        &mut checks,
        "tree_navigation_branch_replay",
        tree_navigation_ok,
        "branch replay uses the selected tree path, not path-derived node ids",
    );

    sgf_text = update_sgf_node_comment(
        sgf_text,
        first_move_id,
        Some("installed workflow comment".to_string()),
    )?;
    let properties = update_sgf_node_properties(
        sgf_text,
        first_move_id,
        vec![
            SgfPropertyUpdateDto {
                key: "N".to_string(),
                values: vec!["installed-node".to_string()],
            },
            SgfPropertyUpdateDto {
                key: "TR".to_string(),
                values: vec!["bb".to_string()],
            },
            SgfPropertyUpdateDto {
                key: "LB".to_string(),
                values: vec!["cc:A".to_string()],
            },
            SgfPropertyUpdateDto {
                key: "AR".to_string(),
                values: vec!["aa:bb".to_string()],
            },
        ],
    )?;
    sgf_text = properties.sgf_text;
    let annotated_tree = parse_sgf_tree(sgf_text.clone())?
        .ok_or_else(|| "annotated SGF did not produce an SGF tree".to_string())?;
    let annotated_node = find_sgf_node_by_comment(&annotated_tree, "installed workflow comment")?;
    let comment_persisted = annotated_node.comment.as_deref() == Some("installed workflow comment");
    let property_persisted = sgf_node_has_property(annotated_node, "N", "installed-node");
    let annotation_persisted = sgf_node_has_property(annotated_node, "TR", "bb")
        && sgf_node_has_property(annotated_node, "LB", "cc:A")
        && sgf_node_has_property(annotated_node, "AR", "aa:bb");
    sgf_workflow_check(
        &mut checks,
        "comment_property_annotation_persistence",
        comment_persisted && property_persisted && annotation_persisted,
        "comment, regular property, and FF4 annotation markup survive update/reparse",
    );

    let append = append_sgf_move(
        sgf_text,
        first_move_id,
        app_model::PlayerColor::White,
        MoveVertex::Point(PointDto { x: 3, y: 3 }),
    )?;
    sgf_text = append.sgf_text;
    let appended_id = append.new_node_id;
    let edit = edit_sgf_move(
        sgf_text,
        appended_id,
        app_model::PlayerColor::White,
        MoveVertex::Pass,
    )?;
    sgf_text = edit.sgf_text;
    let reorder = reorder_sgf_variation(sgf_text, edit.node_id, 0)?;
    sgf_text = reorder.sgf_text;
    let reordered_tree = parse_sgf_tree(sgf_text.clone())?
        .ok_or_else(|| "reordered SGF did not produce an SGF tree".to_string())?;
    let reordered_node = reordered_tree
        .nodes
        .iter()
        .find(|node| node.id == reorder.node_id)
        .ok_or_else(|| "reordered node was not found after reparse".to_string())?;
    let append_persisted = reordered_tree.nodes.iter().any(|node| node.id == reorder.node_id);
    let edit_persisted = reordered_node.vertex == Some(MoveVertex::Pass);
    let reorder_persisted = reordered_node.variation_index == 0 && reordered_node.is_mainline;
    sgf_workflow_check(
        &mut checks,
        "append_edit_reorder_persistence",
        append_persisted && edit_persisted && reorder_persisted,
        "append, edit-to-pass, and variation reorder survive immediate reparse",
    );

    let delete_id = find_sgf_node_by_comment(&reordered_tree, "delete me")?.id;
    let delete = delete_sgf_node(sgf_text, delete_id)?;
    sgf_text = delete.sgf_text;
    let deleted_tree = parse_sgf_tree(sgf_text.clone())?
        .ok_or_else(|| "deleted SGF did not produce an SGF tree".to_string())?;
    let delete_persisted = deleted_tree
        .nodes
        .iter()
        .all(|node| node.comment.as_deref() != Some("delete me"));
    sgf_workflow_check(
        &mut checks,
        "delete_persistence",
        delete_persisted,
        "target leaf node is absent after delete/reparse",
    );

    write_sgf_file(save_path_string.clone(), sgf_text.clone())?;
    let reopened_sgf = read_sgf_file(save_path_string.clone())?;
    let reopened_tree = parse_sgf_tree(reopened_sgf.clone())?
        .ok_or_else(|| "reopened SGF did not produce an SGF tree".to_string())?;
    let reopened_game = parse_sgf_summary(reopened_sgf.clone())?;
    let reopened_node = find_sgf_node_by_comment(&reopened_tree, "installed workflow comment")?;
    let reopened_pass = reopened_tree
        .nodes
        .iter()
        .find(|node| node.vertex == Some(MoveVertex::Pass) && node.variation_index == 0);
    let save_readback_persisted = reopened_sgf == sgf_text;
    let reopened_comment = reopened_node.comment.as_deref() == Some("installed workflow comment");
    let reopened_property = sgf_node_has_property(reopened_node, "N", "installed-node");
    let reopened_annotation = sgf_node_has_property(reopened_node, "TR", "bb")
        && sgf_node_has_property(reopened_node, "LB", "cc:A")
        && sgf_node_has_property(reopened_node, "AR", "aa:bb");
    let reopened_append_edit_reorder = reopened_pass.is_some();
    let reopened_delete = reopened_tree
        .nodes
        .iter()
        .all(|node| node.comment.as_deref() != Some("delete me"));
    sgf_workflow_check(
        &mut checks,
        "save_reopen_invariants",
        save_readback_persisted
            && reopened_comment
            && reopened_property
            && reopened_annotation
            && reopened_append_edit_reorder
            && reopened_delete,
        "final SGF was saved, read back, reparsed, and semantic edit invariants were retained",
    );

    let status = if checks.iter().all(|check| check.status == "pass") {
        "pass"
    } else {
        "fail"
    };

    Ok(InstalledAppSgfWorkflowProofDto {
        schema: "lizzieyzy.installed-app-sgf-workflow-proof.v1".to_string(),
        status: status.to_string(),
        saved_path: save_path_string,
        checks,
        initial_node_count,
        reopened_node_count: reopened_tree.nodes.len(),
        reopened_move_count: reopened_game.summary.move_count,
        comment_persisted: reopened_comment,
        property_persisted: reopened_property,
        annotation_persisted: reopened_annotation,
        append_persisted: append_persisted && reopened_append_edit_reorder,
        edit_persisted: edit_persisted && reopened_append_edit_reorder,
        reorder_persisted: reorder_persisted && reopened_append_edit_reorder,
        delete_persisted: delete_persisted && reopened_delete,
        save_readback_persisted,
        reopen_invariant: sgf_workflow_invariant(&reopened_tree),
        boundaries: InstalledAppSgfWorkflowBoundariesDto {
            dev_server_required: false,
            native_dialog_covered: false,
            webview_dom_covered: false,
            full_legacy_parity: false,
        },
    })
}

fn installed_app_sgf_workflow_fixture() -> &'static str {
    "(;GM[1]FF[4]SZ[5]KM[0]C[root];B[aa]C[first move](;W[bb]C[main variation];B[cc]C[delete me])(;W[cc]C[branch variation]))"
}

fn sgf_workflow_check(
    checks: &mut Vec<InstalledAppSgfWorkflowCheckDto>,
    name: &str,
    passed: bool,
    message: &str,
) {
    checks.push(InstalledAppSgfWorkflowCheckDto {
        name: name.to_string(),
        status: if passed { "pass" } else { "fail" }.to_string(),
        message: message.to_string(),
    });
}

fn find_sgf_node_by_move(tree: &SgfTreeDto, move_number: u32) -> Result<&SgfTreeNodeDto, String> {
    tree.nodes
        .iter()
        .find(|node| node.move_number == Some(move_number) && node.is_mainline)
        .ok_or_else(|| format!("SGF node for mainline move {move_number} was not found"))
}

fn find_sgf_node_by_comment<'a>(tree: &'a SgfTreeDto, comment: &str) -> Result<&'a SgfTreeNodeDto, String> {
    tree.nodes
        .iter()
        .find(|node| node.comment.as_deref() == Some(comment))
        .ok_or_else(|| format!("SGF node with comment `{comment}` was not found"))
}

fn sgf_node_has_property(node: &SgfTreeNodeDto, key: &str, value: &str) -> bool {
    node.properties
        .iter()
        .any(|property| property.key == key && property.values.iter().any(|candidate| candidate == value))
}

fn position_has_stone(position: &PositionDto, x: u8, y: u8, color: app_model::PlayerColor) -> bool {
    position
        .stones
        .iter()
        .any(|stone| stone.x == x && stone.y == y && stone.color == color)
}

fn sgf_workflow_invariant(tree: &SgfTreeDto) -> String {
    let comments = tree
        .nodes
        .iter()
        .filter_map(|node| node.comment.as_deref())
        .collect::<Vec<_>>()
        .join("|");
    let moves = tree
        .nodes
        .iter()
        .filter_map(|node| node.move_number.map(|move_number| move_number.to_string()))
        .collect::<Vec<_>>()
        .join(",");
    format!("nodes={};moves={};comments={comments}", tree.nodes.len(), moves)
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
    let source_path_display = source_path.display().to_string();
    let preview = match preview_legacy_config_migration_from_path(&source_path) {
        Ok(preview) => preview,
        Err(err) => return Ok(legacy_migration_parse_failure_dto(source_path_display, err)),
    };
    let preferences_path = match app_preferences_path(&app_handle) {
        Ok(path) => path,
        Err(err) => return Ok(legacy_migration_preflight_failure_dto(&preview, err)),
    };
    let engine_profiles_path = match engine_profile_path(&app_handle) {
        Ok(path) => path,
        Err(err) => return Ok(legacy_migration_preflight_failure_dto(&preview, err)),
    };
    apply_legacy_config_migration_preview_to_paths(preview, &preferences_path, &engine_profiles_path)
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

    registry.insert(job_id_string.clone(), cancel_token.clone())?;

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
    let _was_running = cancel_analysis_job_in_registry(&registry, &job_id)?;
    Ok(())
}

fn cancel_analysis_job_in_registry(registry: &AnalysisJobRegistry, job_id: &str) -> Result<bool, String> {
    let job_id = job_id.trim();
    if job_id.is_empty() {
        return Err("analysis job id must not be empty".to_string());
    }
    registry.cancel(job_id)
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
    registry.remove(job_id);
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

#[derive(Clone)]
struct LegacyMigrationTarget {
    path: PathBuf,
    kind: LegacyMigrationTargetKind,
    contents: String,
    previous_contents: Option<String>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum LegacyMigrationTargetKind {
    Preferences,
    EngineProfiles,
}

fn apply_legacy_config_migration_preview_to_paths(
    preview: LegacyConfigMigrationPreviewDto,
    preferences_path: &Path,
    engine_profiles_path: &Path,
) -> Result<LegacyConfigMigrationApplyDto, String> {
    apply_legacy_config_migration_preview_to_paths_with_writer(
        preview,
        preferences_path,
        engine_profiles_path,
        |path, contents| {
            fs::write(path, contents).map_err(|err| format!("failed to write {}: {err}", path.display()))
        },
    )
}

fn apply_legacy_config_migration_preview_to_paths_with_writer(
    preview: LegacyConfigMigrationPreviewDto,
    preferences_path: &Path,
    engine_profiles_path: &Path,
    mut writer: impl FnMut(&Path, &str) -> Result<(), String>,
) -> Result<LegacyConfigMigrationApplyDto, String> {
    let targets =
        match prepare_legacy_config_migration_targets(&preview, preferences_path, engine_profiles_path) {
            Ok(targets) => targets,
            Err(err) => return Ok(legacy_migration_preflight_failure_dto(&preview, err)),
        };
    let mut written_targets: Vec<LegacyMigrationTarget> = Vec::new();

    for target in &targets {
        if let Some(parent) = target.path.parent() {
            if let Err(err) = fs::create_dir_all(parent) {
                return Ok(legacy_migration_transaction_failure_dto(
                    &preview,
                    target.kind,
                    format!("failed to create target directory {}: {err}", parent.display()),
                    &written_targets,
                ));
            }
        }

        if let Err(err) = writer(&target.path, &target.contents) {
            return Ok(legacy_migration_transaction_failure_dto(
                &preview,
                target.kind,
                err,
                &written_targets,
            ));
        }
        written_targets.push(target.clone());
    }

    let written_paths = targets
        .iter()
        .map(|target| target.path.display().to_string())
        .collect::<Vec<_>>();
    Ok(LegacyConfigMigrationApplyDto {
        status: "applied".to_string(),
        source_path: preview.source_path,
        preferences_written: targets
            .iter()
            .any(|target| target.kind == LegacyMigrationTargetKind::Preferences),
        engine_profiles_written: targets
            .iter()
            .any(|target| target.kind == LegacyMigrationTargetKind::EngineProfiles),
        written_paths,
        written_path_labels: targets
            .iter()
            .map(|target| legacy_migration_target_label(target.kind).to_string())
            .collect(),
        transactional: true,
        no_write_on_error: true,
        rollback_performed: false,
        rollback_succeeded: true,
        rollback_paths: Vec::new(),
        rollback_errors: Vec::new(),
        error_message: None,
        migrated_fields: preview.migrated_fields,
        warnings: preview.warnings,
    })
}

fn prepare_legacy_config_migration_targets(
    preview: &LegacyConfigMigrationPreviewDto,
    preferences_path: &Path,
    engine_profiles_path: &Path,
) -> Result<Vec<LegacyMigrationTarget>, String> {
    let mut targets = Vec::new();
    if let Some(preferences) = preview.preferences.clone() {
        let existing = load_app_preferences_at_path(preferences_path)?;
        let merged = merge_migrated_preferences(existing, preferences, &preview.migrated_fields);
        targets.push(LegacyMigrationTarget {
            path: preferences_path.to_path_buf(),
            kind: LegacyMigrationTargetKind::Preferences,
            contents: serialize_app_preferences(merged)?,
            previous_contents: read_existing_migration_target(preferences_path)?,
        });
    }
    if let Some(engine_profiles) = preview.engine_profiles.clone() {
        let existing = load_engine_profiles_settings_at_path(engine_profiles_path)?;
        let merged = merge_migrated_engine_profiles(existing, engine_profiles, &preview.migrated_fields);
        targets.push(LegacyMigrationTarget {
            path: engine_profiles_path.to_path_buf(),
            kind: LegacyMigrationTargetKind::EngineProfiles,
            contents: serialize_engine_profiles_settings(merged)?,
            previous_contents: read_existing_migration_target(engine_profiles_path)?,
        });
    }
    Ok(targets)
}

fn read_existing_migration_target(path: &Path) -> Result<Option<String>, String> {
    match fs::read_to_string(path) {
        Ok(contents) => Ok(Some(contents)),
        Err(err) if err.kind() == ErrorKind::NotFound => Ok(None),
        Err(err) => Err(format!(
            "legacy config migration no-write-on-error: failed to snapshot existing target {} before writes: {err}",
            path.display()
        )),
    }
}

fn serialize_app_preferences(preferences: AppPreferencesDto) -> Result<String, String> {
    serde_json::to_string_pretty(&normalize_app_preferences(preferences))
        .map_err(|err| format!("failed to serialize app preferences: {err}"))
}

fn serialize_engine_profiles_settings(settings: EngineProfilesSettingsDto) -> Result<String, String> {
    let settings = normalize_engine_profiles_settings(settings)?;
    serde_json::to_string_pretty(&settings)
        .map_err(|err| format!("failed to serialize engine profiles: {err}"))
}

fn legacy_migration_parse_failure_dto(
    source_path: String,
    error_message: String,
) -> LegacyConfigMigrationApplyDto {
    legacy_migration_failed_apply_dto(LegacyMigrationFailedApply {
        source_path,
        migrated_fields: Vec::new(),
        warnings: Vec::new(),
        error_message: format!(
            "legacy config migration parse/preflight failed with no writes: {error_message}"
        ),
        no_write_on_error: true,
        rollback_performed: false,
        rollback_succeeded: true,
        rollback_paths: Vec::new(),
        rollback_errors: Vec::new(),
        written_targets: &[],
    })
}

fn legacy_migration_preflight_failure_dto(
    preview: &LegacyConfigMigrationPreviewDto,
    error_message: String,
) -> LegacyConfigMigrationApplyDto {
    legacy_migration_failed_apply_dto(LegacyMigrationFailedApply {
        source_path: preview.source_path.clone(),
        migrated_fields: preview.migrated_fields.clone(),
        warnings: preview.warnings.clone(),
        error_message: format!(
            "legacy config migration parse/preflight failed with no writes: {error_message}"
        ),
        no_write_on_error: true,
        rollback_performed: false,
        rollback_succeeded: true,
        rollback_paths: Vec::new(),
        rollback_errors: Vec::new(),
        written_targets: &[],
    })
}

fn legacy_migration_transaction_failure_dto(
    preview: &LegacyConfigMigrationPreviewDto,
    target_kind: LegacyMigrationTargetKind,
    cause: String,
    written_targets: &[LegacyMigrationTarget],
) -> LegacyConfigMigrationApplyDto {
    let (rollback_succeeded, rollback_paths, rollback_errors) =
        rollback_legacy_migration_targets(written_targets);
    let rollback_performed = !written_targets.is_empty();
    let no_write_on_error = !rollback_performed;
    let rollback_note = if rollback_performed {
        format!(
            "rollback performed for [{}]; rollback_succeeded={rollback_succeeded}",
            rollback_paths.join(", ")
        )
    } else {
        "rollback not required because no migration targets were written".to_string()
    };
    let rollback_error_note = if rollback_errors.is_empty() {
        String::new()
    } else {
        format!("; rollback errors: {}", rollback_errors.join("; "))
    };
    let error_message = format!(
        "legacy config migration transactional write failed for {}; no-write-on-error={no_write_on_error}; {rollback_note}{rollback_error_note}; cause: {cause}",
        legacy_migration_target_label(target_kind)
    );
    legacy_migration_failed_apply_dto(LegacyMigrationFailedApply {
        source_path: preview.source_path.clone(),
        migrated_fields: preview.migrated_fields.clone(),
        warnings: preview.warnings.clone(),
        error_message,
        no_write_on_error,
        rollback_performed,
        rollback_succeeded: if rollback_performed {
            rollback_succeeded
        } else {
            true
        },
        rollback_paths,
        rollback_errors,
        written_targets,
    })
}

fn rollback_legacy_migration_targets(targets: &[LegacyMigrationTarget]) -> (bool, Vec<String>, Vec<String>) {
    let mut rollback_paths = Vec::new();
    let mut rollback_errors = Vec::new();
    for target in targets.iter().rev() {
        let result = if let Some(contents) = &target.previous_contents {
            fs::write(&target.path, contents)
        } else {
            match fs::remove_file(&target.path) {
                Ok(()) => Ok(()),
                Err(err) if err.kind() == ErrorKind::NotFound => Ok(()),
                Err(err) => Err(err),
            }
        };
        let label = legacy_migration_target_label(target.kind).to_string();
        rollback_paths.push(label.clone());
        if let Err(err) = result {
            rollback_errors.push(format!("{label}: {err}"));
        }
    }
    (rollback_errors.is_empty(), rollback_paths, rollback_errors)
}

struct LegacyMigrationFailedApply<'a> {
    source_path: String,
    migrated_fields: Vec<String>,
    warnings: Vec<String>,
    error_message: String,
    no_write_on_error: bool,
    rollback_performed: bool,
    rollback_succeeded: bool,
    rollback_paths: Vec<String>,
    rollback_errors: Vec<String>,
    written_targets: &'a [LegacyMigrationTarget],
}

fn legacy_migration_failed_apply_dto(
    failure: LegacyMigrationFailedApply<'_>,
) -> LegacyConfigMigrationApplyDto {
    LegacyConfigMigrationApplyDto {
        status: "failed".to_string(),
        source_path: failure.source_path,
        preferences_written: failure
            .written_targets
            .iter()
            .any(|target| target.kind == LegacyMigrationTargetKind::Preferences),
        engine_profiles_written: failure
            .written_targets
            .iter()
            .any(|target| target.kind == LegacyMigrationTargetKind::EngineProfiles),
        written_paths: failure
            .written_targets
            .iter()
            .map(|target| target.path.display().to_string())
            .collect(),
        written_path_labels: failure
            .written_targets
            .iter()
            .map(|target| legacy_migration_target_label(target.kind).to_string())
            .collect(),
        transactional: true,
        no_write_on_error: failure.no_write_on_error,
        rollback_performed: failure.rollback_performed,
        rollback_succeeded: failure.rollback_succeeded,
        rollback_paths: failure.rollback_paths,
        rollback_errors: failure.rollback_errors,
        error_message: Some(failure.error_message),
        migrated_fields: failure.migrated_fields,
        warnings: failure.warnings,
    }
}

fn legacy_migration_target_label(kind: LegacyMigrationTargetKind) -> &'static str {
    match kind {
        LegacyMigrationTargetKind::Preferences => "preferences",
        LegacyMigrationTargetKind::EngineProfiles => "engineProfiles",
    }
}

#[cfg(test)]
fn apply_legacy_config_migration_to_paths(
    source_path: &Path,
    preferences_path: &Path,
    engine_profiles_path: &Path,
) -> Result<LegacyConfigMigrationApplyDto, String> {
    let preview = match preview_legacy_config_migration_from_path(source_path) {
        Ok(preview) => preview,
        Err(err) => {
            return Ok(legacy_migration_parse_failure_dto(
                source_path.display().to_string(),
                err,
            ))
        }
    };
    apply_legacy_config_migration_preview_to_paths(preview, preferences_path, engine_profiles_path)
}

#[cfg(test)]
fn apply_legacy_config_migration_to_paths_with_writer(
    source_path: &Path,
    preferences_path: &Path,
    engine_profiles_path: &Path,
    writer: impl FnMut(&Path, &str) -> Result<(), String>,
) -> Result<LegacyConfigMigrationApplyDto, String> {
    let preview = match preview_legacy_config_migration_from_path(source_path) {
        Ok(preview) => preview,
        Err(err) => {
            return Ok(legacy_migration_parse_failure_dto(
                source_path.display().to_string(),
                err,
            ))
        }
    };
    apply_legacy_config_migration_preview_to_paths_with_writer(
        preview,
        preferences_path,
        engine_profiles_path,
        writer,
    )
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
        push_runtime_asset_candidates(&mut candidates, root, "resource_dir");
    }

    RuntimeAssetLayoutDto {
        resource_dir: resource_dir.map(|path| path.display().to_string()),
        dev_roots: dev_roots
            .into_iter()
            .map(|path| path.display().to_string())
            .collect(),
        resource_roots: release_roots
            .iter()
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
        ("runtime root", "directory", PathBuf::new(), false),
        (
            "KataGo bin",
            "directory",
            PathBuf::from("runtime").join("katago").join("bin"),
            true,
        ),
        (
            "KataGo models",
            "directory",
            PathBuf::from("runtime").join("katago").join("models"),
            true,
        ),
        (
            "KataGo configs",
            "directory",
            PathBuf::from("runtime").join("katago").join("configs"),
            true,
        ),
        (
            "readboard runtime",
            "directory",
            PathBuf::from("runtime").join("readboard"),
            true,
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
    let checks = layout
        .candidates
        .iter()
        .map(validate_runtime_asset_candidate)
        .collect::<Vec<_>>();

    let exists = checks
        .iter()
        .filter(|check| check.status == "exists")
        .cloned()
        .collect::<Vec<_>>();
    let missing = checks
        .iter()
        .filter(|check| check.status == "missing")
        .cloned()
        .collect::<Vec<_>>();
    let placeholders = checks
        .iter()
        .filter(|check| check.status == "placeholder")
        .cloned()
        .collect::<Vec<_>>();
    let warnings = missing
        .iter()
        .chain(placeholders.iter())
        .map(|missing| missing.message.clone())
        .collect::<Vec<_>>();

    RuntimeAssetValidationDto {
        layout,
        checks,
        exists,
        missing,
        placeholders,
        warnings,
    }
}

fn validate_runtime_asset_candidate(candidate: &RuntimeAssetPathDto) -> RuntimeAssetValidationEntryDto {
    let path = Path::new(&candidate.path);
    let (status, message) = match fs::metadata(path) {
        Ok(metadata) => {
            if candidate.kind == "directory" && !metadata.is_dir() {
                (
                    "placeholder",
                    format!(
                        "{} candidate exists at {} but is not a directory",
                        candidate.label, candidate.path
                    ),
                )
            } else if is_runtime_asset_placeholder(candidate, path) {
                (
                    "placeholder",
                    format!(
                        "{} candidate exists at {} but does not contain a real bundled runtime asset",
                        candidate.label, candidate.path
                    ),
                )
            } else {
                (
                    "exists",
                    format!("{} candidate exists at {}", candidate.label, candidate.path),
                )
            }
        }
        Err(_) => (
            "missing",
            format!("{} candidate is missing at {}", candidate.label, candidate.path),
        ),
    };

    RuntimeAssetValidationEntryDto {
        label: candidate.label.clone(),
        kind: candidate.kind.clone(),
        source: candidate.source.clone(),
        path: candidate.path.clone(),
        required: candidate.required,
        status: status.to_string(),
        message,
    }
}

fn is_runtime_asset_placeholder(candidate: &RuntimeAssetPathDto, path: &Path) -> bool {
    if !candidate.required {
        return false;
    }

    match candidate.label.as_str() {
        "KataGo models" => !directory_contains_matching_asset(path, 2, is_katago_model_asset),
        "KataGo configs" => !directory_contains_matching_asset(path, 2, is_katago_config_asset),
        "KataGo bin" | "readboard runtime" => !directory_contains_matching_asset(path, 3, |_| true),
        _ => false,
    }
}

fn directory_contains_matching_asset(path: &Path, max_depth: usize, matches_asset: fn(&str) -> bool) -> bool {
    let entries = match fs::read_dir(path) {
        Ok(entries) => entries,
        Err(_) => return false,
    };

    for entry in entries.flatten() {
        let entry_path = entry.path();
        let file_name = entry.file_name();
        let name = file_name.to_string_lossy();
        if is_placeholder_asset_name(&name) {
            continue;
        }

        let metadata = match entry.metadata() {
            Ok(metadata) => metadata,
            Err(_) => continue,
        };
        if metadata.is_file() && matches_asset(&name) {
            return true;
        }
        if metadata.is_dir()
            && max_depth > 0
            && directory_contains_matching_asset(&entry_path, max_depth - 1, matches_asset)
        {
            return true;
        }
    }

    false
}

fn is_placeholder_asset_name(name: &str) -> bool {
    let name = name.trim().to_ascii_lowercase();
    name.is_empty()
        || name == ".gitkeep"
        || name == ".keep"
        || name == "readme"
        || name.starts_with("readme.")
        || name.contains("placeholder")
}

fn is_katago_model_asset(name: &str) -> bool {
    let name = name.to_ascii_lowercase();
    name.ends_with(".bin.gz")
        || name.ends_with(".txt.gz")
        || name.ends_with(".onnx")
        || name.ends_with(".pb.gz")
}

fn is_katago_config_asset(name: &str) -> bool {
    let name = name.to_ascii_lowercase();
    name.ends_with(".cfg") || name.ends_with(".conf")
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

fn validate_legacy_external_capture_request(
    request: &LegacyExternalCaptureRequest,
) -> Result<(), ProviderError> {
    validate_timeout_ms(request.timeout_ms, "legacy_capture_external_window")?;
    if request.process_id == Some(0) {
        return Err(invalid_request(
            "legacy_capture_external_window process_id must be greater than zero",
        ));
    }
    let has_target = request
        .client_name
        .as_deref()
        .is_some_and(|value| !value.trim().is_empty())
        || request
            .window_title
            .as_deref()
            .is_some_and(|value| !value.trim().is_empty())
        || request.process_id.is_some();
    if !has_target {
        return Err(invalid_request(
            "legacy_capture_external_window requires client_name, window_title, or process_id",
        ));
    }
    Ok(())
}

fn legacy_import_capture_available_result(
    kind: &str,
    title: &str,
    message: &str,
    surface: &str,
    action: &str,
    warning: &str,
    metadata: BTreeMap<String, String>,
) -> LegacyImportCaptureHelperResult {
    let mut details = metadata;
    details.insert("surface".to_string(), surface.to_string());
    details.insert("action".to_string(), action.to_string());
    details.insert("importsOnHelperCall".to_string(), "false".to_string());
    details.insert("boardReplacementApplied".to_string(), "false".to_string());
    LegacyImportCaptureHelperResult {
        kind: kind.to_string(),
        status: "available".to_string(),
        title: title.to_string(),
        message: message.to_string(),
        recoverable: true,
        imported: false,
        board_replacement: "none".to_string(),
        warnings: vec![warning.to_string()],
        details,
    }
}

fn legacy_import_capture_unsupported_result<const N: usize>(
    kind: &str,
    title: &str,
    message: &str,
    boundary: &str,
    warning: &str,
    metadata: BTreeMap<String, String>,
    flags: [(&str, bool); N],
) -> LegacyImportCaptureHelperResult {
    let mut details = metadata;
    details.insert("boundary".to_string(), boundary.to_string());
    details.insert("no_stale_board_replacement".to_string(), "true".to_string());
    details.insert("providerErrorKind".to_string(), "not_implemented".to_string());
    details.insert("boardReplacementApplied".to_string(), "false".to_string());
    for (key, value) in flags {
        details.insert(key.to_string(), value.to_string());
    }
    LegacyImportCaptureHelperResult {
        kind: kind.to_string(),
        status: "recoverable_unsupported".to_string(),
        title: title.to_string(),
        message: message.to_string(),
        recoverable: true,
        imported: false,
        board_replacement: "none".to_string(),
        warnings: vec![
            warning.to_string(),
            "No stale, guessed, or partial board replacement was applied.".to_string(),
        ],
        details,
    }
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
        readboard_sidecar::ReadboardSidecarError::ImageRead { .. } => ProviderErrorKind::InvalidRequest,
        readboard_sidecar::ReadboardSidecarError::ImageBase64(_)
        | readboard_sidecar::ReadboardSidecarError::ImageDecode(_)
        | readboard_sidecar::ReadboardSidecarError::ImageLowConfidence(_) => {
            ProviderErrorKind::InvalidPayload
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

fn native_menu_contract_dto() -> NativeMenuContractDto {
    NativeMenuContractDto {
        schema: "lizzieyzy.native-menu-contract.v1".to_string(),
        event_name: NATIVE_MENU_EVENT_NAME.to_string(),
        actions: NATIVE_MENU_ACTIONS.iter().map(native_menu_action_dto).collect(),
    }
}

fn native_menu_action_dto(spec: &NativeMenuActionSpec) -> NativeMenuActionDto {
    NativeMenuActionDto {
        menu_id: spec.menu_id.to_string(),
        action_id: spec.action_id.to_string(),
        target_id: spec.target_id.to_string(),
        label: spec.label.to_string(),
        menu_path: spec
            .menu_path
            .iter()
            .map(|segment| (*segment).to_string())
            .collect(),
        accelerator: spec.accelerator.map(str::to_string),
    }
}

fn native_menu_event_payload(menu_id: &str) -> Option<NativeMenuActionEventDto> {
    NATIVE_MENU_ACTIONS
        .iter()
        .find(|spec| spec.menu_id == menu_id)
        .map(|spec| {
            let action = native_menu_action_dto(spec);
            NativeMenuActionEventDto {
                menu_id: action.menu_id,
                action_id: action.action_id,
                target_id: action.target_id,
                label: action.label,
                menu_path: action.menu_path,
                accelerator: action.accelerator,
                source: "native_menu".to_string(),
            }
        })
}

fn build_native_legacy_menu<R: Runtime, M: Manager<R>>(manager: &M) -> tauri::Result<tauri::menu::Menu<R>> {
    use tauri::menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder};

    let mut root = MenuBuilder::new(manager);
    for group in native_menu_groups() {
        let mut submenu = SubmenuBuilder::with_id(
            manager,
            format!("legacy-menu-group-{}", menu_group_id(group)),
            group,
        );
        for spec in NATIVE_MENU_ACTIONS
            .iter()
            .filter(|spec| spec.menu_path.first() == Some(&group))
        {
            let mut item = MenuItemBuilder::with_id(spec.menu_id, spec.label);
            if let Some(accelerator) = spec.accelerator {
                item = item.accelerator(accelerator);
            }
            submenu = submenu.item(&item.build(manager)?);
        }
        root = root.item(&submenu.build()?);
    }
    root.build()
}

fn native_menu_groups() -> Vec<&'static str> {
    let mut groups = Vec::new();
    for spec in NATIVE_MENU_ACTIONS {
        if let Some(group) = spec.menu_path.first() {
            if !groups.contains(group) {
                groups.push(*group);
            }
        }
    }
    groups
}

fn menu_group_id(group: &str) -> String {
    group.to_ascii_lowercase().replace(' ', "-")
}

pub fn run() {
    tauri::Builder::default()
        .manage(AnalysisJobRegistry::default())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let menu = build_native_legacy_menu(app.handle())?;
            app.set_menu(menu)?;
            Ok(())
        })
        .on_menu_event(|app, event| {
            if let Some(payload) = native_menu_event_payload(event.id().as_ref()) {
                let _ = app.emit(NATIVE_MENU_EVENT_NAME, payload);
            }
        })
        .invoke_handler(tauri::generate_handler![
            health,
            native_menu_contract,
            runtime_smoke_config,
            runtime_smoke_report,
            installed_app_runtime_proof,
            parse_sgf_summary,
            parse_sgf_tree,
            provider_parse_yike_url,
            provider_import_from_payload,
            provider_fetch_yike,
            provider_fetch_fox,
            readboard_sidecar_probe,
            readboard_sidecar_sync_snapshot,
            readboard_external_capture,
            legacy_capture_external_window,
            legacy_import_capture_helper,
            replay_sgf_positions,
            update_sgf_node_comment,
            update_sgf_node_properties,
            append_sgf_move,
            edit_sgf_move,
            delete_sgf_node,
            reorder_sgf_variation,
            replay_sgf_position_at_node,
            installed_app_sgf_workflow_proof,
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

    fn legacy_config_fixture(name: &str) -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../..")
            .join("tests")
            .join("fixtures")
            .join("legacy-config")
            .join(name)
    }

    fn readboard_image_fixture(name: &str) -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../..")
            .join("tests")
            .join("fixtures")
            .join("readboard-images")
            .join(name)
    }

    fn runtime_smoke_report_temp_path(name: &str) -> PathBuf {
        std::env::temp_dir()
            .join(format!("lizzieyzy-runtime-smoke-{name}-{}", Uuid::new_v4()))
            .join("nested")
            .join("report.json")
    }

    #[test]
    fn native_menu_contract_has_unique_ids_and_actions() {
        let contract = native_menu_contract();
        let mut menu_ids = HashSet::new();
        let mut action_ids = HashSet::new();

        assert_eq!(contract.schema, "lizzieyzy.native-menu-contract.v1");
        assert_eq!(contract.event_name, NATIVE_MENU_EVENT_NAME);
        assert_eq!(contract.actions.len(), NATIVE_MENU_ACTIONS.len());
        for action in &contract.actions {
            assert!(
                menu_ids.insert(action.menu_id.clone()),
                "duplicate menu id {}",
                action.menu_id
            );
            assert!(
                action_ids.insert(action.action_id.clone()),
                "duplicate action id {}",
                action.action_id
            );
            assert!(!action.target_id.trim().is_empty());
            assert!(action.menu_path.len() >= 2);
        }
    }

    #[test]
    fn native_menu_contract_includes_expected_scoped_actions() {
        let actions = native_menu_contract()
            .actions
            .into_iter()
            .map(|action| action.action_id)
            .collect::<HashSet<_>>();
        let expected = [
            "file.open",
            "file.save",
            "file.saveAs",
            "file.importSgf",
            "game.loadSample",
            "game.parseSgf",
            "analysis.runReview",
            "analysis.katagoPanel",
            "view.candidates",
            "view.ownership",
            "view.policy",
            "engine.profiles",
            "engine.assets",
            "tools.providers",
            "tools.preferences",
            "help.backendStatus",
        ];

        for action_id in expected {
            assert!(
                actions.contains(action_id),
                "missing native menu action {action_id}"
            );
        }
    }

    #[test]
    fn native_menu_event_mapping_returns_frontend_payload() {
        let payload = native_menu_event_payload("legacy-menu-view-candidates").unwrap();

        assert_eq!(payload.source, "native_menu");
        assert_eq!(payload.menu_id, "legacy-menu-view-candidates");
        assert_eq!(payload.action_id, "view.candidates");
        assert_eq!(payload.target_id, "candidates");
        assert_eq!(
            payload.menu_path,
            vec!["View".to_string(), "Candidates".to_string()]
        );
        assert!(payload.accelerator.is_none());
        assert!(native_menu_event_payload("unknown-menu-id").is_none());
    }

    #[test]
    fn native_menu_contract_keeps_accelerators_nullable() {
        let contract = native_menu_contract();
        let open = contract
            .actions
            .iter()
            .find(|action| action.action_id == "file.open")
            .unwrap();
        let import = contract
            .actions
            .iter()
            .find(|action| action.action_id == "file.importSgf")
            .unwrap();

        assert_eq!(open.accelerator.as_deref(), Some("CmdOrCtrl+O"));
        assert!(import.accelerator.is_none());
    }

    #[test]
    fn katago_cancel_registry_is_idempotent_and_cleans_up_token() {
        let registry = AnalysisJobRegistry::default();
        let cancel_token = AnalysisCancelToken::new();
        registry
            .insert("job-1".to_string(), cancel_token.clone())
            .unwrap();

        let first_cancel = cancel_analysis_job_in_registry(&registry, "job-1").unwrap();
        let second_cancel = cancel_analysis_job_in_registry(&registry, "job-1").unwrap();

        assert!(first_cancel);
        assert!(!second_cancel);
        assert!(cancel_token.is_cancelled());
        assert!(!registry.contains("job-1"));
    }

    #[test]
    fn katago_cancel_registry_treats_missing_job_as_recoverable() {
        let registry = AnalysisJobRegistry::default();

        let cancelled = cancel_analysis_job_in_registry(&registry, "already-finished-job").unwrap();

        assert!(!cancelled);
        assert!(!registry.contains("already-finished-job"));
    }

    #[test]
    fn katago_cancel_registry_rejects_empty_job_id() {
        let registry = AnalysisJobRegistry::default();

        let error = cancel_analysis_job_in_registry(&registry, "  ").unwrap_err();

        assert!(error.contains("analysis job id must not be empty"));
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
        assert_eq!(applied.status, "applied");
        assert!(applied.preferences_written);
        assert!(applied.engine_profiles_written);
        assert!(applied.transactional);
        assert!(applied.no_write_on_error);
        assert!(!applied.rollback_performed);
        assert!(applied.rollback_succeeded);
        assert!(applied.rollback_paths.is_empty());
        assert!(applied.rollback_errors.is_empty());
        assert!(applied.error_message.is_none());
        assert_eq!(applied.written_path_labels, vec!["preferences", "engineProfiles"]);
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
    fn legacy_config_properties_duplicate_entries_use_later_value() {
        let dir = native_config_temp_dir("legacy-properties-duplicates");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("lizzie.properties");
        fs::write(
            &legacy_path,
            r#"
                preferences.candidateLimit=4
                preferences.candidateLimit=13
                katago.command=/first/katago
                katago.command=/second/katago
            "#,
        )
        .unwrap();

        let preview = preview_legacy_config_migration_from_path(&legacy_path).unwrap();

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(preview.preferences.unwrap().candidate_limit, 13);
        assert_eq!(
            preview.engine_profiles.unwrap().profiles[0].profile.engine_path,
            "/second/katago"
        );
    }

    #[test]
    fn legacy_config_properties_preserve_windows_unicode_and_space_paths() {
        let dir = native_config_temp_dir("legacy-properties-windows-unicode");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("lizzie.properties");
        fs::write(
            &legacy_path,
            r#"
                katago.command=C:\\Program Files\\KataGo Unicode\\katago.exe
                katago.model=D:\\模型 目录\\kata go model.bin.gz
                katago.config=D:\\配置 目录\\analysis config.cfg
            "#,
        )
        .unwrap();

        let preview = preview_legacy_config_migration_from_path(&legacy_path).unwrap();

        let _ = fs::remove_dir_all(&dir);
        let profile = &preview.engine_profiles.unwrap().profiles[0].profile;
        assert_eq!(
            profile.engine_path,
            "C:\\Program Files\\KataGo Unicode\\katago.exe"
        );
        assert_eq!(
            profile.model_path.as_deref(),
            Some("D:\\模型 目录\\kata go model.bin.gz")
        );
        assert_eq!(
            profile.config_path.as_deref(),
            Some("D:\\配置 目录\\analysis config.cfg")
        );
    }

    #[test]
    fn legacy_config_partial_invalid_values_warn_but_valid_fields_migrate() {
        let dir = native_config_temp_dir("legacy-partial-invalid");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("lizzie.properties");
        fs::write(
            &legacy_path,
            r#"
                preferences.showCandidates=maybe
                preferences.candidateLimit=9
                preferences.showPolicy=false
                katago.command=/valid/katago
            "#,
        )
        .unwrap();

        let preview = preview_legacy_config_migration_from_path(&legacy_path).unwrap();

        let _ = fs::remove_dir_all(&dir);
        let preferences = preview.preferences.unwrap();
        assert_eq!(preferences.candidate_limit, 9);
        assert!(!preferences.show_policy);
        assert_eq!(
            preview.engine_profiles.unwrap().profiles[0].profile.engine_path,
            "/valid/katago"
        );
        assert!(preview
            .warnings
            .iter()
            .any(|warning| warning.contains("showCandidates value was not a boolean")));
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
        assert_eq!(applied.status, "applied");
        assert!(applied.preferences_written);
        assert!(applied.engine_profiles_written);
        assert!(applied.transactional);
        assert!(applied.no_write_on_error);
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

        let applied =
            apply_legacy_config_migration_to_paths(&legacy_path, &preferences_path, &profiles_path).unwrap();
        let after_preferences = fs::read_to_string(&preferences_path).unwrap();
        let after_profiles = fs::read_to_string(&profiles_path).unwrap();

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(applied.status, "failed");
        assert!(applied
            .error_message
            .unwrap()
            .contains("failed to parse legacy config"));
        assert!(applied.no_write_on_error);
        assert!(!applied.rollback_performed);
        assert!(applied.rollback_succeeded);
        assert!(applied.rollback_paths.is_empty());
        assert!(applied.rollback_errors.is_empty());
        assert_eq!(after_preferences, before_preferences);
        assert_eq!(after_profiles, before_profiles);
    }

    #[test]
    fn legacy_config_profile_write_failure_rolls_back_new_preferences_file() {
        let dir = native_config_temp_dir("legacy-rollback-new-preferences");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("config.json");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);
        fs::write(
            &legacy_path,
            r#"{
                "candidateLimit": 7,
                "enginePath": "/rollback/katago"
            }"#,
        )
        .unwrap();

        let applied = apply_legacy_config_migration_to_paths_with_writer(
            &legacy_path,
            &preferences_path,
            &profiles_path,
            |path, contents| {
                if path == profiles_path {
                    Err("injected profile write failure".to_string())
                } else {
                    fs::write(path, contents)
                        .map_err(|err| format!("failed to write {}: {err}", path.display()))
                }
            },
        )
        .unwrap();
        let preferences_exists = preferences_path.exists();
        let profiles_exists = profiles_path.exists();

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(applied.status, "failed");
        assert_eq!(applied.written_path_labels, vec!["preferences"]);
        assert!(!applied.no_write_on_error);
        assert!(applied.rollback_performed);
        assert!(applied.rollback_succeeded);
        assert_eq!(applied.rollback_paths, vec!["preferences"]);
        assert!(applied.rollback_errors.is_empty());
        let error = applied.error_message.unwrap();
        assert!(error.contains("transactional write failed"));
        assert!(error.contains("no-write-on-error=false"));
        assert!(error.contains("rollback performed"));
        assert!(!preferences_exists);
        assert!(!profiles_exists);
    }

    #[test]
    fn legacy_config_profile_write_failure_restores_existing_preferences_file() {
        let dir = native_config_temp_dir("legacy-rollback-existing-preferences");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("config.json");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);
        save_app_preferences_at_path(
            &preferences_path,
            AppPreferencesDto {
                show_candidates: false,
                candidate_limit: 3,
                auto_load_cache: false,
                review_mode: "deep".to_string(),
                ..default_app_preferences()
            },
        )
        .unwrap();
        let before_preferences = fs::read_to_string(&preferences_path).unwrap();
        fs::write(
            &legacy_path,
            r#"{
                "candidateLimit": 11,
                "enginePath": "/rollback/katago"
            }"#,
        )
        .unwrap();

        let applied = apply_legacy_config_migration_to_paths_with_writer(
            &legacy_path,
            &preferences_path,
            &profiles_path,
            |path, contents| {
                if path == profiles_path {
                    Err("injected profile write failure".to_string())
                } else {
                    fs::write(path, contents)
                        .map_err(|err| format!("failed to write {}: {err}", path.display()))
                }
            },
        )
        .unwrap();
        let after_preferences = fs::read_to_string(&preferences_path).unwrap();
        let profiles_exists = profiles_path.exists();

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(applied.status, "failed");
        assert_eq!(applied.written_path_labels, vec!["preferences"]);
        assert!(!applied.no_write_on_error);
        assert!(applied.rollback_performed);
        assert!(applied.rollback_succeeded);
        assert_eq!(applied.rollback_paths, vec!["preferences"]);
        assert!(applied.rollback_errors.is_empty());
        assert!(applied.error_message.unwrap().contains("rollback_succeeded=true"));
        assert_eq!(after_preferences, before_preferences);
        assert!(!profiles_exists);
    }

    #[test]
    fn legacy_config_rollback_failure_is_visible() {
        let dir = native_config_temp_dir("legacy-rollback-visible-failure");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = dir.join("config.json");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);
        save_app_preferences_at_path(
            &preferences_path,
            AppPreferencesDto {
                candidate_limit: 3,
                ..default_app_preferences()
            },
        )
        .unwrap();
        fs::write(
            &legacy_path,
            r#"{
                "candidateLimit": 11,
                "enginePath": "/rollback/katago"
            }"#,
        )
        .unwrap();

        let applied = apply_legacy_config_migration_to_paths_with_writer(
            &legacy_path,
            &preferences_path,
            &profiles_path,
            |path, contents| {
                if path == preferences_path {
                    fs::write(path, contents).map_err(|err| format!("failed to write preferences: {err}"))?;
                    fs::remove_file(path)
                        .map_err(|err| format!("failed to remove preferences fixture: {err}"))?;
                    fs::create_dir(path)
                        .map_err(|err| format!("failed to create preferences directory fixture: {err}"))?;
                    Ok(())
                } else if path == profiles_path {
                    Err("injected profile write failure".to_string())
                } else {
                    fs::write(path, contents).map_err(|err| format!("failed to write target: {err}"))
                }
            },
        )
        .unwrap();
        let preferences_is_dir = preferences_path.is_dir();

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(applied.status, "failed");
        assert_eq!(applied.written_path_labels, vec!["preferences"]);
        assert!(!applied.no_write_on_error);
        assert!(applied.rollback_performed);
        assert!(!applied.rollback_succeeded);
        assert_eq!(applied.rollback_paths, vec!["preferences"]);
        assert_eq!(applied.rollback_errors.len(), 1);
        assert!(applied.rollback_errors[0].contains("preferences"));
        assert!(applied
            .error_message
            .unwrap()
            .contains("rollback_succeeded=false"));
        assert!(preferences_is_dir);
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
    fn legacy_config_corpus_preview_parses_valid_fixtures_and_writes_nothing() {
        let cases = [
            ("minimal.properties", true, false, false),
            ("full-katago.jsonish", true, true, true),
            ("multi-engine-conflict.properties", false, true, false),
            ("ui-review-preferences.json", true, false, true),
            ("windows-path.properties", false, true, false),
            ("macos-linux-unicode-space.json", false, true, false),
            ("partial-invalid.properties", true, true, true),
            ("unknown-deprecated.json", true, true, true),
        ];

        for (fixture, expect_preferences, expect_profiles, expect_warnings) in cases {
            let path = legacy_config_fixture(fixture);
            let before = fs::read_to_string(&path).unwrap();
            let preview = preview_legacy_config_migration_from_path(&path).unwrap();
            let after = fs::read_to_string(&path).unwrap();

            assert_eq!(after, before, "preview must not modify fixture {fixture}");
            assert_eq!(
                preview.preferences.is_some(),
                expect_preferences,
                "{fixture} preference migration mismatch"
            );
            assert_eq!(
                preview.engine_profiles.is_some(),
                expect_profiles,
                "{fixture} engine migration mismatch"
            );
            if expect_preferences || expect_profiles {
                assert!(
                    !preview.migrated_fields.is_empty(),
                    "{fixture} should report migrated fields"
                );
            }
            assert_eq!(
                !preview.warnings.is_empty(),
                expect_warnings,
                "{fixture} warning expectation mismatch: {:?}",
                preview.warnings
            );
        }
    }

    #[test]
    fn legacy_config_corpus_apply_preferences_only_preserves_next_settings() {
        let dir = native_config_temp_dir("legacy-corpus-apply-preferences-only");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = legacy_config_fixture("ui-review-preferences.json");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);
        save_app_preferences_at_path(
            &preferences_path,
            AppPreferencesDto {
                auto_load_cache: false,
                auto_save_analysis: false,
                review_mode: "deep".to_string(),
                board_theme: "high-contrast".to_string(),
                ..default_app_preferences()
            },
        )
        .unwrap();

        let applied =
            apply_legacy_config_migration_to_paths(&legacy_path, &preferences_path, &profiles_path).unwrap();
        let preferences =
            serde_json::from_str::<AppPreferencesDto>(&fs::read_to_string(&preferences_path).unwrap())
                .unwrap();
        let profiles_exists = profiles_path.exists();

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(applied.status, "applied");
        assert!(applied.preferences_written);
        assert!(!applied.engine_profiles_written);
        assert_eq!(applied.written_path_labels, vec!["preferences"]);
        assert!(applied.no_write_on_error);
        assert!(!applied.rollback_performed);
        assert_eq!(preferences.candidate_limit, 9);
        assert!(!preferences.show_candidates);
        assert!(!preferences.show_policy);
        assert_eq!(preferences.default_max_visits, 800);
        assert!(!preferences.auto_load_cache);
        assert!(!preferences.auto_save_analysis);
        assert_eq!(preferences.review_mode, "deep");
        assert_eq!(preferences.board_theme, "classic");
        assert!(!profiles_exists);
    }

    #[test]
    fn legacy_config_corpus_apply_engine_only_preserves_existing_preferences_and_merges_profiles() {
        let dir = native_config_temp_dir("legacy-corpus-apply-engine-only");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = legacy_config_fixture("macos-linux-unicode-space.json");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);
        save_app_preferences_at_path(
            &preferences_path,
            AppPreferencesDto {
                show_candidates: false,
                candidate_limit: 5,
                auto_load_cache: false,
                review_mode: "deep".to_string(),
                ..default_app_preferences()
            },
        )
        .unwrap();
        save_engine_profiles_settings_at_path(
            &profiles_path,
            EngineProfilesSettingsDto {
                selected_profile_id: "custom".to_string(),
                profiles: vec![EngineProfileRecordDto {
                    id: "custom".to_string(),
                    profile: EngineProfileDto {
                        name: "Custom GTP".to_string(),
                        engine_path: "/custom/gtp".to_string(),
                        model_path: None,
                        config_path: None,
                        working_dir: None,
                        backend: EngineBackend::GenericGtp,
                    },
                    max_visits: 77,
                }],
            },
        )
        .unwrap();
        let before_preferences = fs::read_to_string(&preferences_path).unwrap();

        let applied =
            apply_legacy_config_migration_to_paths(&legacy_path, &preferences_path, &profiles_path).unwrap();
        let after_preferences = fs::read_to_string(&preferences_path).unwrap();
        let profiles =
            serde_json::from_str::<EngineProfilesSettingsDto>(&fs::read_to_string(&profiles_path).unwrap())
                .unwrap();
        let migrated = profiles
            .profiles
            .iter()
            .find(|record| record.id == DEFAULT_ENGINE_PROFILE_ID)
            .unwrap();
        let custom = profiles
            .profiles
            .iter()
            .find(|record| record.id == "custom")
            .unwrap();

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(applied.status, "applied");
        assert!(!applied.preferences_written);
        assert!(applied.engine_profiles_written);
        assert_eq!(applied.written_path_labels, vec!["engineProfiles"]);
        assert_eq!(after_preferences, before_preferences);
        assert_eq!(migrated.profile.engine_path, "/Applications/KataGo Legacy/katago");
        assert_eq!(
            migrated.profile.model_path.as_deref(),
            Some("/Users/shared/囲碁 models/kata model.bin.gz")
        );
        assert_eq!(
            migrated.profile.config_path.as_deref(),
            Some("/home/lizzie yzy/.katago/configs/分析.cfg")
        );
        assert_eq!(custom.profile.engine_path, "/custom/gtp");
        assert_eq!(custom.max_visits, 77);
    }

    #[test]
    fn legacy_config_corpus_duplicate_conflict_strategy_is_deterministic() {
        let preview = preview_legacy_config_migration_from_path(&legacy_config_fixture(
            "multi-engine-conflict.properties",
        ))
        .unwrap();
        let profiles = preview.engine_profiles.unwrap();
        let profile = &profiles.profiles[0];

        assert_eq!(profile.profile.engine_path, "/legacy/generic-gtp");
        assert_eq!(
            profile.profile.model_path.as_deref(),
            Some("/legacy/generic-model.bin.gz")
        );
        assert_eq!(
            profile.profile.config_path.as_deref(),
            Some("/configs/analysis.cfg")
        );
        assert_eq!(profile.max_visits, 2400);
    }

    #[test]
    fn legacy_config_corpus_preserves_windows_paths_and_unicode_space_paths() {
        let windows =
            preview_legacy_config_migration_from_path(&legacy_config_fixture("windows-path.properties"))
                .unwrap();
        let windows_profile = &windows.engine_profiles.unwrap().profiles[0].profile;
        assert_eq!(
            windows_profile.engine_path,
            "C:\\Program Files\\KataGo\\katago.exe"
        );
        assert_eq!(
            windows_profile.model_path.as_deref(),
            Some("D:\\KataGo Models\\kata1 b28.bin.gz")
        );
        assert_eq!(
            windows_profile.config_path.as_deref(),
            Some("D:\\KataGo Configs\\analysis example.cfg")
        );

        let unicode = preview_legacy_config_migration_from_path(&legacy_config_fixture(
            "macos-linux-unicode-space.json",
        ))
        .unwrap();
        let unicode_profile = &unicode.engine_profiles.unwrap().profiles[0].profile;
        assert_eq!(
            unicode_profile.model_path.as_deref(),
            Some("/Users/shared/囲碁 models/kata model.bin.gz")
        );
        assert_eq!(
            unicode_profile.config_path.as_deref(),
            Some("/home/lizzie yzy/.katago/configs/分析.cfg")
        );
    }

    #[test]
    fn legacy_config_corpus_partial_invalid_warns_and_valid_fields_migrate() {
        let preview =
            preview_legacy_config_migration_from_path(&legacy_config_fixture("partial-invalid.properties"))
                .unwrap();
        let preferences = preview.preferences.unwrap();
        let profile = &preview.engine_profiles.unwrap().profiles[0].profile;

        assert_eq!(preferences.candidate_limit, 11);
        assert!(!preferences.show_policy);
        assert_eq!(profile.engine_path, "/valid/katago");
        assert_eq!(profile.model_path.as_deref(), Some("/valid/model.bin.gz"));
        assert!(preview
            .warnings
            .iter()
            .any(|warning| warning.contains("showCandidates value was not a boolean")));
    }

    #[test]
    fn legacy_config_corpus_invalid_fixture_causes_no_write_failed_apply() {
        let dir = native_config_temp_dir("legacy-corpus-invalid-no-write");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = legacy_config_fixture("malformed-json.json");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);
        save_app_preferences_at_path(
            &preferences_path,
            AppPreferencesDto {
                show_candidates: false,
                candidate_limit: 4,
                ..default_app_preferences()
            },
        )
        .unwrap();
        let before_preferences = fs::read_to_string(&preferences_path).unwrap();

        let applied =
            apply_legacy_config_migration_to_paths(&legacy_path, &preferences_path, &profiles_path).unwrap();
        let after_preferences = fs::read_to_string(&preferences_path).unwrap();
        let profiles_exists = profiles_path.exists();

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(applied.status, "failed");
        assert!(applied.no_write_on_error);
        assert!(!applied.rollback_performed);
        assert!(applied.rollback_succeeded);
        assert!(applied.rollback_paths.is_empty());
        assert!(applied.rollback_errors.is_empty());
        assert!(applied.written_path_labels.is_empty());
        assert!(applied
            .error_message
            .as_deref()
            .unwrap_or_default()
            .contains("no writes"));
        assert_eq!(after_preferences, before_preferences);
        assert!(!profiles_exists);
    }

    #[test]
    fn legacy_config_corpus_unsupported_and_deprecated_keys_warn() {
        let preview =
            preview_legacy_config_migration_from_path(&legacy_config_fixture("unknown-deprecated.json"))
                .unwrap();

        assert!(preview.preferences.is_some());
        assert!(preview.engine_profiles.is_some());
        for expected in [
            "deprecatedLeelaZeroTuning",
            "recentFiles",
            "katago.oldAnalysisThreads",
            "ui.removedStoneOpacity",
        ] {
            assert!(
                preview.warnings.iter().any(|warning| warning.contains(expected)),
                "missing warning for {expected}: {:?}",
                preview.warnings
            );
        }
    }

    #[test]
    fn legacy_config_corpus_profile_write_failure_rolls_back_preferences_metadata() {
        let dir = native_config_temp_dir("legacy-corpus-rollback");
        fs::create_dir_all(&dir).unwrap();
        let legacy_path = legacy_config_fixture("full-katago.jsonish");
        let preferences_path = dir.join("prefs").join(APP_PREFERENCES_FILE);
        let profiles_path = dir.join("profiles").join(ENGINE_PROFILE_FILE);

        let applied = apply_legacy_config_migration_to_paths_with_writer(
            &legacy_path,
            &preferences_path,
            &profiles_path,
            |path, contents| {
                if path == profiles_path {
                    Err("injected profile write failure from corpus test".to_string())
                } else {
                    fs::write(path, contents)
                        .map_err(|err| format!("failed to write {}: {err}", path.display()))
                }
            },
        )
        .unwrap();
        let preferences_exists = preferences_path.exists();
        let profiles_exists = profiles_path.exists();

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(applied.status, "failed");
        assert_eq!(applied.written_path_labels, vec!["preferences"]);
        assert!(!applied.no_write_on_error);
        assert!(applied.rollback_performed);
        assert!(applied.rollback_succeeded);
        assert_eq!(applied.rollback_paths, vec!["preferences"]);
        assert!(applied.rollback_errors.is_empty());
        assert!(applied
            .error_message
            .as_deref()
            .unwrap_or_default()
            .contains("rollback_succeeded=true"));
        assert!(!preferences_exists);
        assert!(!profiles_exists);
    }

    #[test]
    fn runtime_asset_layout_resolves_dev_roots_and_required_slots() {
        let dir = native_config_temp_dir("runtime-assets-dev");
        let dev_root = dir.join("repo");
        let nested_src_tauri = dev_root.join("apps").join("desktop").join("src-tauri");
        let layout = resolve_runtime_asset_layout_for_paths(dev_root.clone(), None);

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(layout.resource_dir, None);
        assert_eq!(
            layout.dev_roots,
            vec![
                dev_root.display().to_string(),
                nested_src_tauri.display().to_string()
            ]
        );
        for relative in [
            PathBuf::from("runtime").join("katago").join("bin"),
            PathBuf::from("runtime").join("katago").join("models"),
            PathBuf::from("runtime").join("katago").join("configs"),
            PathBuf::from("runtime").join("readboard"),
        ] {
            let expected_path = dev_root.join(relative).display().to_string();
            let candidate = layout
                .candidates
                .iter()
                .find(|candidate| candidate.source == "dev" && candidate.path == expected_path)
                .unwrap();
            assert_eq!(candidate.kind, "directory");
            assert!(candidate.required);
        }
    }

    #[test]
    fn runtime_asset_layout_resolves_resource_dir_root() {
        let dir = native_config_temp_dir("runtime-assets-resource");
        let resource_dir = dir.join("resources");
        let layout = resolve_runtime_asset_layout_for_paths(dir.join("repo"), Some(resource_dir.clone()));

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(
            layout.resource_dir.as_deref(),
            Some(resource_dir.to_str().unwrap())
        );
        assert_eq!(layout.resource_roots, vec![resource_dir.display().to_string()]);
        assert_eq!(layout.release_roots, vec![resource_dir.display().to_string()]);
        assert!(layout.candidates.iter().any(|candidate| {
            candidate.source == "resource_dir"
                && candidate.label == "KataGo models"
                && candidate.path == resource_dir.join("runtime/katago/models").display().to_string()
                && candidate.required
        }));
    }

    #[test]
    fn runtime_asset_validation_reports_missing_and_placeholder_warnings() {
        let dir = native_config_temp_dir("runtime-assets-validation");
        let dev_root = dir.join("dev-root");
        fs::create_dir_all(dev_root.join("runtime/katago/bin")).unwrap();
        fs::create_dir_all(dev_root.join("runtime/katago/models")).unwrap();
        fs::create_dir_all(dev_root.join("runtime/katago/configs")).unwrap();
        fs::write(dev_root.join("runtime/katago/bin/katago"), "fake binary").unwrap();
        fs::write(
            dev_root.join("runtime/katago/models/README.md"),
            "model placeholder",
        )
        .unwrap();
        fs::write(
            dev_root.join("runtime/katago/configs/analysis.cfg"),
            "maxVisits = 64",
        )
        .unwrap();
        let layout = resolve_runtime_asset_layout_for_paths(dev_root.clone(), None);

        let validation = validate_runtime_asset_layout_from_layout(layout);

        let _ = fs::remove_dir_all(&dir);
        assert!(validation.exists.iter().any(|check| {
            check.status == "exists"
                && check.path == dev_root.join("runtime/katago/bin").display().to_string()
        }));
        assert!(validation.placeholders.iter().any(|check| {
            check.status == "placeholder"
                && check.path == dev_root.join("runtime/katago/models").display().to_string()
        }));
        assert!(validation.missing.iter().any(|check| {
            check.status == "missing"
                && check.path == dev_root.join("runtime/readboard").display().to_string()
        }));
        assert_eq!(
            validation.warnings.len(),
            validation.missing.len() + validation.placeholders.len()
        );
        assert!(validation
            .warnings
            .iter()
            .any(|warning| warning.contains("does not contain a real bundled runtime asset")));
    }

    #[test]
    fn runtime_asset_validation_invalid_path_does_not_panic() {
        let layout = RuntimeAssetLayoutDto {
            resource_dir: None,
            dev_roots: vec!["\0invalid-root".to_string()],
            resource_roots: Vec::new(),
            release_roots: Vec::new(),
            candidates: vec![RuntimeAssetPathDto {
                label: "KataGo models".to_string(),
                kind: "directory".to_string(),
                source: "dev".to_string(),
                path: "\0invalid-root/runtime/katago/models".to_string(),
                required: true,
            }],
        };

        let validation = std::panic::catch_unwind(|| validate_runtime_asset_layout_from_layout(layout))
            .expect("invalid paths should be reported instead of panicking");

        assert_eq!(validation.checks.len(), 1);
        assert_eq!(validation.missing[0].status, "missing");
        assert_eq!(validation.warnings.len(), 1);
    }

    #[test]
    fn installed_app_bundled_katago_lookup_reports_available_with_hashes() {
        let dir = native_config_temp_dir("bundled-katago-available");
        let resource_dir = dir.join("resources");
        fs::create_dir_all(resource_dir.join("runtime/katago/bin")).unwrap();
        fs::create_dir_all(resource_dir.join("runtime/katago/models")).unwrap();
        fs::create_dir_all(resource_dir.join("runtime/katago/configs")).unwrap();
        fs::write(resource_dir.join("runtime/katago/bin/katago"), "#!/bin/sh\n").unwrap();
        fs::write(
            resource_dir.join("runtime/katago/models/tiny.bin.gz"),
            "tiny model",
        )
        .unwrap();
        fs::write(
            resource_dir.join("runtime/katago/configs/analysis.cfg"),
            "maxVisits = 1",
        )
        .unwrap();
        let validation = validate_runtime_asset_layout_from_layout(resolve_runtime_asset_layout_for_paths(
            dir.join("repo"),
            Some(resource_dir.clone()),
        ));

        let bundled = resolve_installed_app_bundled_katago(&validation);

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(bundled.status, "available");
        assert_eq!(bundled.source, "bundledAsset");
        assert!(bundled.profile.is_some());
        assert_eq!(
            bundled.engine.sanitized_path.as_deref(),
            Some("bundledAsset:runtime/katago/bin/katago")
        );
        assert_eq!(
            bundled.model.sanitized_path.as_deref(),
            Some("bundledAsset:runtime/katago/models/tiny.bin.gz")
        );
        assert_eq!(
            bundled.config.sanitized_path.as_deref(),
            Some("bundledAsset:runtime/katago/configs/analysis.cfg")
        );
        assert_eq!(bundled.engine.sha256.as_deref().unwrap().len(), 64);
        assert_eq!(bundled.model.sha256.as_deref().unwrap().len(), 64);
        assert_eq!(bundled.config.sha256.as_deref().unwrap().len(), 64);
        assert!(bundled.engine.size.unwrap() > 0);
        assert!(bundled
            .warnings
            .iter()
            .any(|warning| warning.contains("No large model")));
    }

    #[test]
    fn installed_app_bundled_katago_lookup_reports_unavailable_without_resource_assets() {
        let dir = native_config_temp_dir("bundled-katago-unavailable");
        let validation = validate_runtime_asset_layout_from_layout(resolve_runtime_asset_layout_for_paths(
            dir.join("repo"),
            None,
        ));

        let bundled = resolve_installed_app_bundled_katago(&validation);

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(bundled.status, "unavailable");
        assert!(bundled.profile.is_none());
        assert_eq!(bundled.engine.status, "missing");
        assert!(bundled.engine.sha256.is_none());
    }

    #[test]
    fn installed_app_launch_profile_falls_back_to_complete_bundled_assets() {
        let dir = native_config_temp_dir("bundled-katago-launch-profile");
        let resource_dir = dir.join("resources");
        fs::create_dir_all(resource_dir.join("runtime/katago/bin")).unwrap();
        fs::create_dir_all(resource_dir.join("runtime/katago/models")).unwrap();
        fs::create_dir_all(resource_dir.join("runtime/katago/configs")).unwrap();
        fs::write(resource_dir.join("runtime/katago/bin/katago"), "fake").unwrap();
        fs::write(
            resource_dir.join("runtime/katago/models/tiny.bin.gz"),
            "tiny model",
        )
        .unwrap();
        fs::write(
            resource_dir.join("runtime/katago/configs/analysis.cfg"),
            "maxVisits = 1",
        )
        .unwrap();
        let validation = validate_runtime_asset_layout_from_layout(resolve_runtime_asset_layout_for_paths(
            dir.join("repo"),
            Some(resource_dir.clone()),
        ));
        let bundled = resolve_installed_app_bundled_katago(&validation);
        let profile_status = InstalledAppProfileStatusDto {
            status: "defaultMissingFile".to_string(),
            path: None,
            loaded: false,
            selected_profile_id: Some(DEFAULT_ENGINE_PROFILE_ID.to_string()),
            profile_count: 1,
            selected_profile_name: Some("Local KataGo".to_string()),
            selected_profile: Some(default_engine_profile_record().profile),
            max_visits: Some(600),
            error_message: None,
        };

        let (profile, source) =
            installed_app_launch_profile(profile_status.selected_profile.clone(), &profile_status, &bundled);
        let attempt = installed_app_engine_launch_attempt(profile, false, &source, Some(resource_dir));

        let _ = fs::remove_dir_all(&dir);
        assert_eq!(source, "bundledAssetFallback");
        assert!(!attempt.attempted);
        assert_eq!(attempt.status, "skipped");
        assert_eq!(attempt.profile_source, "bundledAssetFallback");
        assert_eq!(attempt.asset_proofs.len(), 4);
        assert!(attempt.asset_proofs.iter().any(|proof| {
            proof.label == "model"
                && proof.status == "exists"
                && proof.sha256.as_deref().is_some_and(|value| value.len() == 64)
                && proof.sanitized_path.as_deref()
                    == Some("bundledAssetFallback:runtime/katago/models/tiny.bin.gz")
        }));
    }

    #[test]
    fn installed_app_runtime_source_detects_macos_app_bundle() {
        let exe = Path::new("/Applications/LizzieYzy Next.app/Contents/MacOS/lizzieyzy-next-desktop");
        assert_eq!(
            derive_macos_app_bundle_path(exe),
            Some(PathBuf::from("/Applications/LizzieYzy Next.app"))
        );
        assert_eq!(
            installed_app_runtime_source(
                Some(exe),
                Some(Path::new("/Applications/LizzieYzy Next.app/Contents/Resources"))
            ),
            "packaged-macos-app"
        );
    }

    #[test]
    fn installed_app_profile_status_from_settings_reports_selected_profile() {
        let settings = EngineProfilesSettingsDto {
            selected_profile_id: "selected".to_string(),
            profiles: vec![EngineProfileRecordDto {
                id: "selected".to_string(),
                profile: EngineProfileDto {
                    name: "Installed profile".to_string(),
                    engine_path: "/opt/katago/bin/katago".to_string(),
                    model_path: Some("/opt/katago/model.bin.gz".to_string()),
                    config_path: Some("/opt/katago/analysis.cfg".to_string()),
                    working_dir: None,
                    backend: EngineBackend::KataGoAnalysis,
                },
                max_visits: 321,
            }],
        };

        let status = installed_app_profile_status_from_settings("loaded", None, settings);

        assert_eq!(status.status, "loaded");
        assert!(status.loaded);
        assert_eq!(status.selected_profile_id.as_deref(), Some("selected"));
        assert_eq!(status.profile_count, 1);
        assert_eq!(status.selected_profile_name.as_deref(), Some("Installed profile"));
        assert_eq!(status.max_visits, Some(321));
        assert_eq!(
            status.selected_profile.as_ref().map(|profile| profile.backend),
            Some(EngineBackend::KataGoAnalysis)
        );
    }

    #[test]
    fn installed_app_engine_launch_missing_profile_is_skipped() {
        let attempt = installed_app_engine_launch_attempt(None, true, "missing", None);

        assert!(!attempt.attempted);
        assert_eq!(attempt.status, "skipped");
        assert!(attempt.recoverable);
        assert_eq!(attempt.profile_source, "missing");
        assert!(attempt.command_spec.is_none());
        assert!(attempt.asset_checks.is_empty());
        assert!(attempt
            .error_message
            .as_deref()
            .unwrap_or_default()
            .contains("no selected engine profile"));
    }

    #[test]
    fn installed_app_engine_launch_missing_engine_is_structured_unavailable() {
        let profile = EngineProfileDto {
            name: "Missing engine".to_string(),
            engine_path: String::new(),
            model_path: None,
            config_path: None,
            working_dir: None,
            backend: EngineBackend::GenericGtp,
        };

        let attempt = installed_app_engine_launch_attempt(Some(profile), true, "userLocalProfile", None);

        assert!(attempt.attempted);
        assert_eq!(attempt.status, "unavailable");
        assert!(attempt.recoverable);
        assert_eq!(attempt.profile_source, "userLocalProfile");
        assert_eq!(attempt.error_kind.as_deref(), Some("missingEnginePath"));
        assert!(attempt.command_spec.is_none());
        assert_eq!(attempt.asset_checks.len(), 1);
        assert_eq!(attempt.asset_checks[0].label, "engine binary");
        assert!(!attempt.asset_checks[0].exists);
        assert_eq!(attempt.asset_proofs.len(), 1);
        assert_eq!(attempt.asset_proofs[0].status, "missing");
    }

    #[test]
    fn installed_app_engine_launch_can_be_disabled_without_spawning() {
        let profile = EngineProfileDto {
            name: "Disabled launch".to_string(),
            engine_path: "/definitely/missing/katago".to_string(),
            model_path: None,
            config_path: None,
            working_dir: None,
            backend: EngineBackend::GenericGtp,
        };

        let attempt = installed_app_engine_launch_attempt(Some(profile), false, "userLocalProfile", None);

        assert!(!attempt.attempted);
        assert_eq!(attempt.status, "skipped");
        assert!(attempt.recoverable);
        assert_eq!(attempt.profile_source, "userLocalProfile");
        assert!(attempt.command_spec.is_none());
        assert_eq!(attempt.asset_checks.len(), 1);
        assert_eq!(
            attempt.error_message.as_deref(),
            Some("engine launch attempt disabled by request")
        );
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
    fn command_rejects_invalid_sgf_annotation_value() {
        let input = "(;SZ[9];B[aa]C[old]TR[bb])";
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
                key: "AR".to_string(),
                values: vec!["aa:bb:cc".to_string()],
            }],
        )
        .unwrap_err();

        assert!(error.contains("invalid SGF property value for AR"));
        assert_eq!(
            sgf::serialize_sgf_document(&sgf::parse_sgf(input).unwrap()).unwrap(),
            input
        );
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
    fn installed_app_sgf_workflow_proof_covers_save_reopen_and_edit_invariants() {
        let path = native_sgf_temp_path("installed-workflow");

        let proof = installed_app_sgf_workflow_proof_for_path(Some(path.clone())).unwrap();
        let saved = fs::read_to_string(&path).unwrap();

        remove_native_sgf_temp_file(&path);
        assert_eq!(proof.schema, "lizzieyzy.installed-app-sgf-workflow-proof.v1");
        assert_eq!(proof.status, "pass");
        assert!(proof.saved_path.ends_with(".sgf"));
        assert!(proof.initial_node_count >= 5);
        assert!(proof.reopened_node_count >= 5);
        assert!(proof.reopened_move_count >= 2);
        assert!(proof.comment_persisted);
        assert!(proof.property_persisted);
        assert!(proof.annotation_persisted);
        assert!(proof.append_persisted);
        assert!(proof.edit_persisted);
        assert!(proof.reorder_persisted);
        assert!(proof.delete_persisted);
        assert!(proof.save_readback_persisted);
        assert!(proof.checks.iter().all(|check| check.status == "pass"));
        assert!(saved.contains("C[installed workflow comment]"));
        assert!(saved.contains("N[installed-node]"));
        assert!(saved.contains("TR[bb]"));
        assert!(saved.contains("LB[cc:A]"));
        assert!(saved.contains("AR[aa:bb]"));
        assert!(saved.contains("W[]"));
        assert!(!saved.contains("delete me"));
        assert!(!proof.boundaries.dev_server_required);
        assert!(!proof.boundaries.native_dialog_covered);
        assert!(!proof.boundaries.webview_dom_covered);
        assert!(!proof.boundaries.full_legacy_parity);
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
    fn readboard_sidecar_sync_snapshot_reports_unreadable_image_path() {
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

        assert_eq!(sync_error.kind, ProviderErrorKind::InvalidRequest);
        assert!(sync_error
            .message
            .contains("failed to read controlled readboard image"));
    }

    #[test]
    fn readboard_sidecar_sync_snapshot_reports_invalid_image_base64_payload() {
        let sync_error = readboard_sidecar_sync_snapshot(ReadboardSidecarSyncSnapshotRequest {
            endpoint: None,
            snapshot_id: Some("snapshot-base64".to_string()),
            image_path: None,
            image_base64: Some("iVBORw0KGgo=".to_string()),
            sgf_text: None,
            metadata: std::collections::BTreeMap::new(),
            timeout_ms: Some(100),
        })
        .unwrap_err();

        assert_eq!(sync_error.kind, ProviderErrorKind::InvalidPayload);
        assert!(sync_error
            .message
            .contains("failed to decode controlled readboard image bytes"));
    }

    #[test]
    fn readboard_sidecar_failed_image_extraction_does_not_poison_next_sync() {
        let sync_error = readboard_sidecar_sync_snapshot(ReadboardSidecarSyncSnapshotRequest {
            endpoint: None,
            snapshot_id: Some("bad-image".to_string()),
            image_path: None,
            image_base64: Some("bm90LWEtcG5n".to_string()),
            sgf_text: None,
            metadata: std::collections::BTreeMap::new(),
            timeout_ms: Some(100),
        })
        .unwrap_err();
        assert_eq!(sync_error.kind, ProviderErrorKind::InvalidPayload);

        let result = readboard_sidecar_sync_snapshot(ReadboardSidecarSyncSnapshotRequest {
            endpoint: None,
            snapshot_id: Some("protocol-after-failed-image".to_string()),
            image_path: None,
            image_base64: None,
            sgf_text: Some("snapshot board_size=2 move_number=1 codes=3000".to_string()),
            metadata: std::collections::BTreeMap::new(),
            timeout_ms: Some(100),
        })
        .unwrap();

        assert_eq!(result.snapshot_id, "protocol-after-failed-image");
        let position = result.position.unwrap();
        assert_eq!(position.board_size, 2);
        assert_eq!(position.stones.len(), 1);
    }

    #[test]
    fn readboard_sidecar_sync_snapshot_rejects_empty_ocr_request() {
        let sync_error = readboard_sidecar_sync_snapshot(ReadboardSidecarSyncSnapshotRequest {
            endpoint: None,
            snapshot_id: None,
            image_path: Some("  ".to_string()),
            image_base64: None,
            sgf_text: None,
            metadata: std::collections::BTreeMap::new(),
            timeout_ms: Some(100),
        })
        .unwrap_err();

        assert_eq!(sync_error.kind, ProviderErrorKind::InvalidRequest);
        assert!(sync_error.message.contains("requires image_path"));
    }

    #[test]
    fn readboard_external_capture_local_image_returns_sanitized_decode_preview() {
        let path = readboard_image_fixture("controlled-19-three-stones.ppm");
        let result = readboard_external_capture(ReadboardExternalCaptureRequestDto {
            capture_source: "local_image".to_string(),
            image_path: Some(path.display().to_string()),
            timeout_ms: None,
            metadata: Some(BTreeMap::from([("case".to_string(), "fixture".to_string())])),
        })
        .unwrap();

        assert_eq!(result.schema, "lizzieyzy.readboard-external-capture.v1");
        assert_eq!(result.status, "captured");
        assert!(!result.recoverable);
        assert!(!result.operator_initiated);
        assert!(!result.user_selection_required);
        assert_eq!(result.source, "local_image");
        assert_eq!(result.capture_source, "local_image");
        assert_eq!(
            result.source_metadata.get("case").map(String::as_str),
            Some("fixture")
        );
        assert_eq!(
            result.sanitized_path.as_deref(),
            Some("local-image:controlled-19-three-stones.ppm")
        );
        assert_eq!(result.sha256.as_deref().unwrap().len(), 64);
        assert_eq!(result.hash, result.sha256);
        assert_eq!(result.snapshot_id.as_deref(), Some("external-capture-preview"));
        assert_eq!(result.snapshot_hash.as_deref().unwrap().len(), 64);
        assert!(result.size.unwrap() > 0);
        assert!(result.position.is_some());
        assert_eq!(result.position.as_ref().unwrap().board_size, 19);
        assert_eq!(result.decode.status, "success");
        assert_eq!(result.decode.board_size, Some(19));
        assert_eq!(result.decode.stone_count, Some(3));
        assert_eq!(result.decode.black_stones, Some(2));
        assert_eq!(result.decode.white_stones, Some(1));
        assert!(result.snapshot.is_some());
        assert_eq!(result.board_replacement, "none");
        assert!(result
            .warnings
            .iter()
            .any(|warning| warning.contains("not arbitrary OCR")));
        assert_eq!(result.metadata.get("case").map(String::as_str), Some("fixture"));
        let serialized = serde_json::to_string(&result).unwrap();
        assert!(!serialized.contains("/Users/"));
        assert!(!serialized.contains("/private/"));
        assert!(!serialized.contains("/var/folders/"));
    }

    #[test]
    fn readboard_external_capture_frontend_style_request_aliases_screen_to_operator_capture() {
        let value = serde_json::json!({
            "source": "screen",
            "timeoutMs": 1000,
            "sourceMetadata": {
                "ui": "frontend"
            }
        });
        let request: ReadboardExternalCaptureRequestDto = serde_json::from_value(value).unwrap();

        assert_eq!(request.capture_source, "screen");
        assert_eq!(request.timeout_ms, Some(1000));
        assert_eq!(
            request
                .metadata
                .as_ref()
                .and_then(|metadata| metadata.get("ui"))
                .map(String::as_str),
            Some("frontend")
        );
        assert_eq!(
            normalize_capture_source(&request.capture_source),
            "macos_interactive_capture"
        );
    }

    #[test]
    fn readboard_external_capture_operator_selected_file_is_preview_only() {
        let path = readboard_image_fixture("controlled-19-three-stones.ppm");
        let result = readboard_external_capture(ReadboardExternalCaptureRequestDto {
            capture_source: "operator_selected_file".to_string(),
            image_path: Some(path.display().to_string()),
            timeout_ms: Some(1_000),
            metadata: Some(BTreeMap::from([(
                "selection".to_string(),
                "operator".to_string(),
            )])),
        })
        .unwrap();

        assert_eq!(result.status, "captured");
        assert_eq!(result.source, "operator_selected_file");
        assert!(result.operator_initiated);
        assert!(result.user_selection_required);
        assert_eq!(
            result.sanitized_path.as_deref(),
            Some("operator-selected-file:controlled-19-three-stones.ppm")
        );
        assert_eq!(result.sha256.as_deref().unwrap().len(), 64);
        assert_eq!(result.snapshot_hash.as_deref().unwrap().len(), 64);
        assert!(result.position.is_some());
        assert_eq!(result.board_replacement, "none");
        assert!(result
            .warnings
            .iter()
            .any(|warning| warning.contains("no target-client discovery")));
    }

    #[test]
    fn readboard_external_capture_local_image_file_alias_returns_legacy_capture_source() {
        let path = readboard_image_fixture("controlled-19-three-stones.ppm");
        let result = readboard_external_capture(ReadboardExternalCaptureRequestDto {
            capture_source: "local_image_file".to_string(),
            image_path: Some(path.display().to_string()),
            timeout_ms: Some(1_000),
            metadata: None,
        })
        .unwrap();

        assert_eq!(result.status, "captured");
        assert_eq!(result.source, "local_image");
        assert_eq!(result.capture_source, "local_image");
        assert!(!result.operator_initiated);
        assert!(!result.user_selection_required);
        assert_eq!(
            result.sanitized_path.as_deref(),
            Some("local-image:controlled-19-three-stones.ppm")
        );
        assert!(result.position.is_some());
        assert_eq!(result.board_replacement, "none");
    }

    #[test]
    fn readboard_external_capture_snake_case_aliases_are_accepted() {
        let value = serde_json::json!({
            "captureSource": "local_image",
            "image_path": "board.png",
            "timeout_ms": 1000,
            "source_metadata": {
                "style": "snake"
            }
        });
        let request: ReadboardExternalCaptureRequestDto = serde_json::from_value(value).unwrap();

        assert_eq!(request.capture_source, "local_image");
        assert_eq!(request.image_path.as_deref(), Some("board.png"));
        assert_eq!(request.timeout_ms, Some(1000));
        assert_eq!(
            request
                .metadata
                .as_ref()
                .and_then(|metadata| metadata.get("style"))
                .map(String::as_str),
            Some("snake")
        );
    }

    #[test]
    fn readboard_external_capture_invalid_local_image_is_decode_error_without_private_path() {
        let path = readboard_image_fixture("invalid-image.bin");
        let result = readboard_external_capture(ReadboardExternalCaptureRequestDto {
            capture_source: "local_image".to_string(),
            image_path: Some(path.display().to_string()),
            timeout_ms: None,
            metadata: None,
        })
        .unwrap();

        assert_eq!(result.status, "decode_error");
        assert!(result.recoverable);
        assert_eq!(result.decode.status, "decode_error");
        assert_eq!(
            result.sanitized_path.as_deref(),
            Some("local-image:invalid-image.bin")
        );
        assert_eq!(result.sha256.as_deref().unwrap().len(), 64);
        assert!(result.size.unwrap() > 0);
        assert!(result.snapshot.is_none());
        assert!(result.position.is_none());
        assert_eq!(result.board_replacement, "none");
        let serialized = serde_json::to_string(&result).unwrap();
        assert!(!serialized.contains(path.parent().unwrap().to_str().unwrap()));
        assert!(!serialized.contains("/Users/"));
        assert!(!serialized.contains("/private/"));
        assert!(!serialized.contains("/var/folders/"));
    }

    #[test]
    fn readboard_external_capture_rejects_invalid_source_and_missing_local_path() {
        let invalid_source = readboard_external_capture(ReadboardExternalCaptureRequestDto {
            capture_source: "unknown".to_string(),
            image_path: None,
            timeout_ms: None,
            metadata: None,
        })
        .unwrap_err();
        assert_eq!(invalid_source.kind, ProviderErrorKind::InvalidRequest);

        let missing_path = readboard_external_capture(ReadboardExternalCaptureRequestDto {
            capture_source: "local_image".to_string(),
            image_path: None,
            timeout_ms: None,
            metadata: None,
        })
        .unwrap_err();
        assert_eq!(missing_path.kind, ProviderErrorKind::InvalidRequest);
    }

    #[test]
    fn readboard_external_capture_sha256_helper_matches_known_digest() {
        assert_eq!(
            sha256_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn readboard_external_capture_interactive_cancel_is_structured() {
        fn fake_cancel(_timeout: Duration) -> ReadboardCaptureFileOutcome {
            ReadboardCaptureFileOutcome::Cancelled {
                message: "operator cancelled test capture".to_string(),
            }
        }

        let result = readboard_external_capture_with_runner(
            ReadboardExternalCaptureRequestDto {
                capture_source: "window".to_string(),
                image_path: None,
                timeout_ms: Some(1_000),
                metadata: None,
            },
            fake_cancel,
        )
        .unwrap();

        assert_eq!(result.status, "cancelled");
        assert_eq!(result.source, "macos_interactive_capture");
        assert!(result.recoverable);
        assert!(result.operator_initiated);
        assert!(result.user_selection_required);
        assert_eq!(result.board_replacement, "none");
        assert!(result
            .warnings
            .iter()
            .any(|warning| warning.contains("operator-selected macOS interactive capture")));
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn readboard_external_capture_interactive_non_macos_is_unsupported() {
        let result = readboard_external_capture(ReadboardExternalCaptureRequestDto {
            capture_source: "screen".to_string(),
            image_path: None,
            timeout_ms: Some(1_000),
            metadata: None,
        })
        .unwrap();

        assert_eq!(result.status, "unsupported");
        assert_eq!(result.source, "macos_interactive_capture");
        assert!(result.recoverable);
        assert!(result.operator_initiated);
        assert!(result.user_selection_required);
        assert_eq!(result.board_replacement, "none");
    }

    #[test]
    fn legacy_capture_external_window_reports_unsupported_contract() {
        let result = legacy_capture_external_window(LegacyExternalCaptureRequest {
            client_name: Some("Fox".to_string()),
            window_title: Some("Live game".to_string()),
            process_id: None,
            timeout_ms: Some(100),
        })
        .unwrap();

        assert_eq!(result.kind, "external_window_capture");
        assert_eq!(result.status, "recoverable_unsupported");
        assert!(result.recoverable);
        assert!(!result.imported);
        assert_eq!(result.board_replacement, "none");
        assert_eq!(result.details.get("boardReplacementApplied").unwrap(), "false");
        assert_eq!(result.details.get("externalCaptureCovered").unwrap(), "false");
        assert_eq!(result.details.get("nativeWindowCaptureCovered").unwrap(), "false");
        assert_eq!(result.details.get("clientCaptureCovered").unwrap(), "false");
        assert_eq!(result.details.get("clientNameProvided").unwrap(), "true");
        assert_eq!(result.details.get("windowTitleProvided").unwrap(), "true");
    }

    #[test]
    fn legacy_capture_external_window_rejects_empty_or_invalid_request() {
        let empty_error = legacy_capture_external_window(LegacyExternalCaptureRequest {
            client_name: Some(" ".to_string()),
            window_title: None,
            process_id: None,
            timeout_ms: Some(100),
        })
        .unwrap_err();
        assert_eq!(empty_error.kind, ProviderErrorKind::InvalidRequest);
        assert!(empty_error.message.contains("requires client_name"));

        let invalid_pid_error = legacy_capture_external_window(LegacyExternalCaptureRequest {
            client_name: None,
            window_title: None,
            process_id: Some(0),
            timeout_ms: Some(100),
        })
        .unwrap_err();
        assert_eq!(invalid_pid_error.kind, ProviderErrorKind::InvalidRequest);
        assert!(invalid_pid_error
            .message
            .contains("process_id must be greater than zero"));
    }

    #[test]
    fn legacy_import_capture_helper_reports_sgf_payload_available_without_import() {
        let result = legacy_import_capture_helper(LegacyImportCaptureHelperRequest {
            kind: "sgf_payload".to_string(),
            payload: Some("(;GM[1]SZ[19])".to_string()),
            metadata: std::collections::BTreeMap::from([("source".to_string(), "rust-test".to_string())]),
            ..LegacyImportCaptureHelperRequest::default()
        })
        .unwrap();

        assert_eq!(result.kind, "sgf_payload");
        assert_eq!(result.status, "available");
        assert!(result.recoverable);
        assert!(!result.imported);
        assert_eq!(result.board_replacement, "none");
        assert_eq!(result.details.get("importsOnHelperCall").unwrap(), "false");
        assert_eq!(result.details.get("boardReplacementApplied").unwrap(), "false");
    }

    #[test]
    fn legacy_import_capture_helper_reports_protocol_snapshot_available_without_import() {
        let result = legacy_import_capture_helper(LegacyImportCaptureHelperRequest {
            kind: "protocol_snapshot".to_string(),
            payload: Some("snapshot board_size=2 move_number=1 codes=3000".to_string()),
            ..LegacyImportCaptureHelperRequest::default()
        })
        .unwrap();

        assert_eq!(result.kind, "protocol_snapshot");
        assert_eq!(result.status, "available");
        assert!(result.recoverable);
        assert!(!result.imported);
        assert_eq!(result.board_replacement, "none");
        assert!(result
            .warnings
            .iter()
            .any(|warning| warning.contains("current-position only")));
    }

    #[test]
    fn legacy_import_capture_helper_reports_image_ocr_recoverable_unsupported() {
        let result = legacy_import_capture_helper(LegacyImportCaptureHelperRequest {
            kind: "image_ocr".to_string(),
            image_path: Some("/tmp/board.png".to_string()),
            ..LegacyImportCaptureHelperRequest::default()
        })
        .unwrap();

        assert_eq!(result.kind, "image_ocr");
        assert_eq!(result.status, "recoverable_unsupported");
        assert!(result.recoverable);
        assert!(!result.imported);
        assert_eq!(result.board_replacement, "none");
        assert!(result.message.contains("No SGF was imported"));
        assert_eq!(
            result.details.get("providerErrorKind").unwrap(),
            "not_implemented"
        );
        assert_eq!(result.details.get("imagePathProvided").unwrap(), "true");
    }

    #[test]
    fn legacy_import_capture_helper_reports_external_capture_recoverable_unsupported() {
        for kind in ["external_window_capture", "external_client_capture"] {
            let result = legacy_import_capture_helper(LegacyImportCaptureHelperRequest {
                kind: kind.to_string(),
                window_title: Some("Live game".to_string()),
                ..LegacyImportCaptureHelperRequest::default()
            })
            .unwrap();

            assert_eq!(result.kind, kind);
            assert_eq!(result.status, "recoverable_unsupported");
            assert!(result.recoverable);
            assert!(!result.imported);
            assert_eq!(result.board_replacement, "none");
            assert!(result
                .message
                .contains("External window/client capture is not implemented"));
            assert_eq!(result.details.get("notImplementedBoundary").unwrap(), "true");
            assert_eq!(result.details.get("no_stale_board_replacement").unwrap(), "true");
            assert_eq!(result.details.get("boardReplacementApplied").unwrap(), "false");
            assert_eq!(result.details.get("externalCaptureCovered").unwrap(), "false");
            assert_eq!(result.details.get("nativeWindowCaptureCovered").unwrap(), "false");
            assert_eq!(result.details.get("clientCaptureCovered").unwrap(), "false");
        }
    }

    #[test]
    fn legacy_import_capture_helper_rejects_invalid_kind_or_request() {
        let empty_kind_error = legacy_import_capture_helper(LegacyImportCaptureHelperRequest {
            kind: " ".to_string(),
            ..LegacyImportCaptureHelperRequest::default()
        })
        .unwrap_err();
        assert_eq!(empty_kind_error.kind, ProviderErrorKind::InvalidRequest);
        assert!(empty_kind_error.message.contains("non-empty kind"));

        let invalid_kind_error = legacy_import_capture_helper(LegacyImportCaptureHelperRequest {
            kind: "screen_scrape".to_string(),
            ..LegacyImportCaptureHelperRequest::default()
        })
        .unwrap_err();
        assert_eq!(invalid_kind_error.kind, ProviderErrorKind::InvalidRequest);
        assert!(invalid_kind_error.message.contains("unsupported kind"));

        let invalid_timeout_error = legacy_import_capture_helper(LegacyImportCaptureHelperRequest {
            kind: "image_ocr".to_string(),
            timeout_ms: Some(0),
            ..LegacyImportCaptureHelperRequest::default()
        })
        .unwrap_err();
        assert_eq!(invalid_timeout_error.kind, ProviderErrorKind::InvalidRequest);
        assert!(invalid_timeout_error.message.contains("timeout_ms"));

        let invalid_pid_error = legacy_import_capture_helper(LegacyImportCaptureHelperRequest {
            kind: "external_window_capture".to_string(),
            process_id: Some(0),
            ..LegacyImportCaptureHelperRequest::default()
        })
        .unwrap_err();
        assert_eq!(invalid_pid_error.kind, ProviderErrorKind::InvalidRequest);
        assert!(invalid_pid_error.message.contains("process_id"));
    }

    #[test]
    fn legacy_import_capture_helper_serializes_frontend_contract_shape() {
        let result = legacy_import_capture_helper(LegacyImportCaptureHelperRequest {
            kind: "image_ocr".to_string(),
            ..LegacyImportCaptureHelperRequest::default()
        })
        .unwrap();
        let serialized = serde_json::to_value(result).unwrap();

        assert_eq!(serialized["status"], "recoverable_unsupported");
        assert_eq!(serialized["boardReplacement"], "none");
        assert!(serialized.get("board_replacement").is_none());
        assert_eq!(serialized["imported"], false);
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
