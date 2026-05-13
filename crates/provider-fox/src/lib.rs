use app_model::{
    ProviderFetchMethod, ProviderFetchRequest, ProviderFetchResult, ProviderGameMetadata,
    ProviderGameSummary, ProviderImportRequest, ProviderImportResult, ProviderKind,
};
use provider_core::{
    first_non_blank, invalid_payload, invalid_request, provider_http_error, provider_payload_preflight,
    require_non_blank, ProviderResult, ProviderTransport,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

pub const FOX_BASE_URL: &str = "https://h5.foxwq.com/yehuDiamond/chessbook_local";
pub const FOX_QUERY_USER_URL: &str = "https://newframe.foxwq.com/cgi/QueryUserInfoPanel";
pub const FOX_SGF_CGI_URLS: [&str; 2] = [
    "http://happyapp.huanle.qq.com/cgi-bin/CommonMobileCGI/TXWQFetchChess",
    "http://cgi.foxwq.com/cgi-bin/CommonMobileCGI/TXWQFetchChess",
];
pub const FOX_HTTP_CONNECT_TIMEOUT_MS: u64 = 20_000;
pub const FOX_HTTP_READ_TIMEOUT_MS: u64 = 25_000;
pub const FOX_HTTP_MAX_RETRIES: u8 = 3;
pub const FOX_MOBILE_USER_AGENT: &str =
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 \
     (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
pub const FOX_CGI_USER_AGENT: &str = "okhttp/3.12.12";
const FORM_URLENCODED: &str = "application/x-www-form-urlencoded";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FoxFetchCommand {
    UserName { user_name: String },
    Uid { uid: String, last_code: String },
    ChessId { chessid: String },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct FoxNormalizedPayload {
    pub sgf_text: String,
    pub metadata: ProviderGameMetadata,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SgfTree {
    nodes: Vec<SgfNode>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SgfNode {
    properties: Vec<SgfProperty>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SgfProperty {
    name: String,
    values: Vec<String>,
}

struct SgfParser<'a> {
    input: &'a str,
    index: usize,
}

pub fn parse_fetch_command(command: &str) -> ProviderResult<FoxFetchCommand> {
    let command = require_non_blank(command, "command")?;
    let Some((action, arguments)) = split_once_whitespace(command) else {
        return Err(invalid_request(
            "Fox command must include an action and arguments",
        ));
    };
    let arguments = require_non_blank(arguments, "arguments")?;
    match action {
        "user_name" => Ok(FoxFetchCommand::UserName {
            user_name: arguments.to_string(),
        }),
        "uid" => {
            let (uid, last_code) = match split_once_whitespace(arguments) {
                Some((uid, last_code)) => (uid, require_non_blank(last_code, "last_code")?),
                None => (arguments, "0"),
            };
            Ok(FoxFetchCommand::Uid {
                uid: require_non_blank(uid, "uid")?.to_string(),
                last_code: last_code.to_string(),
            })
        }
        "chessid" => Ok(FoxFetchCommand::ChessId {
            chessid: arguments.to_string(),
        }),
        _ => Err(invalid_request(format!(
            "unsupported Fox command action: {action}"
        ))),
    }
}

pub fn fetch_command<T: ProviderTransport + ?Sized>(
    command: &str,
    transport: &T,
) -> ProviderResult<ProviderFetchResult> {
    fetch(parse_fetch_command(command)?, transport)
}

pub fn fetch<T: ProviderTransport + ?Sized>(
    command: FoxFetchCommand,
    transport: &T,
) -> ProviderResult<ProviderFetchResult> {
    match command {
        FoxFetchCommand::UserName { user_name } => fetch_user_name(&user_name, transport),
        FoxFetchCommand::Uid { uid, last_code } => fetch_uid(&uid, &last_code, transport),
        FoxFetchCommand::ChessId { chessid } => fetch_chessid(&chessid, transport),
    }
}

pub fn query_user_request(user_name: &str) -> ProviderResult<ProviderFetchRequest> {
    let user_name = require_non_blank(user_name, "user_name")?;
    Ok(get_request(
        format!("{FOX_QUERY_USER_URL}?srcuid=0&username={}", url_encode(user_name)),
        None,
    ))
}

pub fn chess_list_request(uid: &str, last_code: &str) -> ProviderResult<ProviderFetchRequest> {
    let uid = require_non_blank(uid, "uid")?;
    let last_code = require_non_blank(last_code, "last_code")?;
    Ok(get_request(
        format!(
            "{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid={}&type=1&lastcode={}&searchkey=&uin={}",
            url_encode(uid),
            url_encode(last_code),
            url_encode(uid)
        ),
        Some(uid.to_string()),
    ))
}

pub fn cgi_sgf_requests(chessid: &str) -> ProviderResult<Vec<ProviderFetchRequest>> {
    let chessid = require_non_blank(chessid, "chessid")?;
    Ok(FOX_SGF_CGI_URLS
        .iter()
        .map(|endpoint| {
            let mut request = post_form_request(
                (*endpoint).to_string(),
                format!("chessid={}", url_encode(chessid)),
                Some(chessid.to_string()),
            );
            request
                .headers
                .insert("User-Agent".to_string(), FOX_CGI_USER_AGENT.to_string());
            request
        })
        .collect())
}

pub fn h5_sgf_request(chessid: &str) -> ProviderResult<ProviderFetchRequest> {
    let chessid = require_non_blank(chessid, "chessid")?;
    Ok(get_request(
        format!("{FOX_BASE_URL}/YHWQFetchChess?chessid={}", url_encode(chessid)),
        Some(chessid.to_string()),
    ))
}

pub fn import_payload(request: ProviderImportRequest) -> ProviderResult<ProviderImportResult> {
    let mut normalized = normalize_payload(&request.payload)?;
    normalized.metadata.source_url = normalized.metadata.source_url.or(request.source_url);
    normalized.metadata.source_id = normalized.metadata.source_id.or(request.source_id);
    merge_metadata(&mut normalized.metadata, request.metadata);

    let mut summary = metadata_summary(&normalized.metadata);
    summary.source_id = normalized.metadata.source_id.clone();
    Ok(ProviderImportResult {
        provider: ProviderKind::Fox,
        sgf_text: normalized.sgf_text,
        summary,
        metadata: normalized.metadata,
        warnings: Vec::new(),
    })
}

pub fn normalize_payload(payload: &str) -> ProviderResult<FoxNormalizedPayload> {
    let payload = provider_payload_preflight("Fox", "payload", payload)?;
    if payload.trim_start().starts_with('(') {
        let sgf_text = normalize_sgf(payload);
        let metadata = metadata_from_sgf(&sgf_text);
        return Ok(FoxNormalizedPayload { sgf_text, metadata });
    }

    let json: Value = serde_json::from_str(payload)
        .map_err(|err| invalid_payload(format!("failed to parse Fox payload JSON: {err}")))?;
    fox_provider_result_error(&json, "Fox payload")?;
    let sgf = json
        .get("chess")
        .and_then(json_scalar_string)
        .ok_or_else(|| invalid_payload("Fox payload does not contain chess SGF text"))?;
    if sgf.trim().is_empty() {
        return Err(invalid_payload("Fox payload chess SGF text is empty"));
    }

    let sgf_text = normalize_sgf(&sgf);
    let mut metadata = metadata_from_sgf(&sgf_text);
    enrich_metadata_from_json(&json, &mut metadata);
    Ok(FoxNormalizedPayload { sgf_text, metadata })
}

pub fn normalize_sgf(sgf: &str) -> String {
    sgf::normalize_fox_sgf(sgf)
}

pub fn sanitize_sgf(sgf: &str) -> String {
    sgf::sanitize_fox_sgf(sgf)
}

fn fetch_user_name<T: ProviderTransport + ?Sized>(
    user_name: &str,
    transport: &T,
) -> ProviderResult<ProviderFetchResult> {
    let user_name = require_non_blank(user_name, "user_name")?;
    if user_name.chars().all(|char| char.is_ascii_digit()) {
        let result = fetch_uid(user_name, "0", transport)?;
        return wrap_chess_list_with_user_info(result, user_name, user_name, user_name);
    }

    let user_response = fetch_request(query_user_request(user_name)?, transport)?;
    let user_info = parse_user_info(&user_response.payload, user_name)?;
    let result = fetch_uid(&user_info.uid, "0", transport)?;
    wrap_chess_list_with_user_info(result, &user_info.uid, &user_info.nickname, user_name)
}

fn fetch_uid<T: ProviderTransport + ?Sized>(
    uid: &str,
    last_code: &str,
    transport: &T,
) -> ProviderResult<ProviderFetchResult> {
    let uid = require_non_blank(uid, "uid")?;
    let last_code = require_non_blank(last_code, "last_code")?;
    let mut result = fetch_request(chess_list_request(uid, last_code)?, transport)?;
    validate_chess_list_payload(&result.payload)?;
    result.metadata.source_id = result.metadata.source_id.or_else(|| Some(uid.to_string()));
    result
        .metadata
        .extra
        .entry("fox_uid".to_string())
        .or_insert_with(|| uid.to_string());
    result
        .metadata
        .extra
        .entry("fox_last_code".to_string())
        .or_insert_with(|| last_code.to_string());
    Ok(result)
}

fn fetch_chessid<T: ProviderTransport + ?Sized>(
    chessid: &str,
    transport: &T,
) -> ProviderResult<ProviderFetchResult> {
    let chessid = require_non_blank(chessid, "chessid")?;
    let mut cgi_fallback_reasons = Vec::new();
    for request in cgi_sgf_requests(chessid)? {
        let request_url = request.url.clone();
        let response = match fetch_request(request, transport) {
            Ok(response) => response,
            Err(error) => {
                cgi_fallback_reasons.push(format!(
                    "CGI {request_url} fetch failed: {}",
                    provider_error_description(&error)
                ));
                continue;
            }
        };
        if let Some(reason) = cgi_sgf_payload_fallback_reason(&request_url, &response.payload) {
            cgi_fallback_reasons.push(reason);
            continue;
        }
        match normalize_runtime_sgf_response(response, chessid) {
            Ok(result) => return Ok(result),
            Err(error) => cgi_fallback_reasons.push(format!(
                "CGI {request_url} normalization failed: {}",
                provider_error_description(&error)
            )),
        }
    }

    let response = fetch_request(h5_sgf_request(chessid)?, transport)
        .map_err(|error| with_cgi_fallback_context(error, &cgi_fallback_reasons, "H5 fetch failed"))?;
    let mut result = normalize_runtime_sgf_response(response, chessid).map_err(|error| {
        with_cgi_fallback_context(error, &cgi_fallback_reasons, "H5 normalization failed")
    })?;
    result.warnings.extend(
        cgi_fallback_reasons
            .into_iter()
            .map(|reason| format!("Fox CGI fallback: {reason}")),
    );
    Ok(result)
}

fn fetch_request<T: ProviderTransport + ?Sized>(
    request: ProviderFetchRequest,
    transport: &T,
) -> ProviderResult<ProviderFetchResult> {
    let result = transport.fetch(&request)?;
    if !(200..400).contains(&result.status_code) {
        return Err(provider_http_error(
            "Fox",
            result.status_code,
            &result.payload,
            "transport request failed",
        ));
    }
    provider_payload_preflight("Fox", "transport response", &result.payload)?;
    Ok(result)
}

fn normalize_runtime_sgf_response(
    mut response: ProviderFetchResult,
    fallback_source_id: &str,
) -> ProviderResult<ProviderFetchResult> {
    let payload = provider_payload_preflight("Fox", "runtime SGF response", &response.payload)?;
    let normalized = normalize_payload(payload)?;
    let mut metadata = normalized.metadata;
    metadata.request_url = metadata.request_url.or_else(|| Some(response.url.clone()));
    metadata.source_id = metadata
        .source_id
        .or_else(|| Some(fallback_source_id.to_string()));
    merge_metadata(&mut metadata, response.metadata);

    response.payload = normalized_payload_text(payload, &normalized.sgf_text)?;
    response.metadata = metadata;
    Ok(response)
}

fn normalized_payload_text(payload: &str, normalized_sgf: &str) -> ProviderResult<String> {
    if payload.trim_start().starts_with('(') {
        return Ok(normalized_sgf.to_string());
    }

    let payload = provider_payload_preflight("Fox", "payload", payload)?;
    let mut json: Value = serde_json::from_str(payload)
        .map_err(|err| invalid_payload(format!("failed to parse Fox payload JSON: {err}")))?;
    let Some(object) = json.as_object_mut() else {
        return Err(invalid_payload("Fox payload JSON must be an object"));
    };
    object.insert("chess".to_string(), Value::String(normalized_sgf.to_string()));
    Ok(json.to_string())
}

fn cgi_sgf_payload_fallback_reason(url: &str, payload: &str) -> Option<String> {
    if payload.trim().is_empty() {
        return Some(format!("CGI {url} returned empty payload"));
    }
    let json = match serde_json::from_str::<Value>(payload) {
        Ok(json) => json,
        Err(error) => return Some(format!("CGI {url} returned invalid JSON: {error}")),
    };
    let result = json.get("result").and_then(json_i64);
    if result != Some(0) {
        let mut message = format!(
            "CGI {url} returned result {}",
            result
                .map(|value| value.to_string())
                .unwrap_or_else(|| "missing".to_string())
        );
        if let Some(result_message) = json.get("resultstr").and_then(json_scalar_string) {
            if !result_message.trim().is_empty() {
                message.push_str(": ");
                message.push_str(result_message.trim());
            }
        }
        return Some(message);
    }
    if json
        .get("chess")
        .and_then(json_scalar_string)
        .is_none_or(|value| value.trim().is_empty())
    {
        return Some(format!("CGI {url} returned no SGF chess text"));
    }
    None
}

fn provider_error_description(error: &app_model::ProviderError) -> String {
    format!("{:?}: {}", error.kind, error.message)
}

fn with_cgi_fallback_context(
    mut error: app_model::ProviderError,
    cgi_fallback_reasons: &[String],
    h5_context: &str,
) -> app_model::ProviderError {
    if !cgi_fallback_reasons.is_empty() {
        error.message = format!(
            "{h5_context}: {}; CGI fallback reasons: {}",
            provider_error_description(&error),
            cgi_fallback_reasons.join("; ")
        );
    }
    error
}

fn validate_chess_list_payload(payload: &str) -> ProviderResult<()> {
    let payload = provider_payload_preflight("Fox", "chess list payload", payload)?;
    let json: Value = serde_json::from_str(payload)
        .map_err(|err| invalid_payload(format!("failed to parse Fox chess list JSON: {err}")))?;
    fox_provider_result_error(&json, "Fox chess list")?;
    require_chess_list_array(&json)
}

fn fox_provider_result_error(json: &Value, context: &str) -> ProviderResult<()> {
    let result = json
        .get("result")
        .or_else(|| json.get("errcode"))
        .and_then(json_i64);
    if result.is_none_or(|result| result == 0) {
        return Ok(());
    }
    let result = result.unwrap_or(-1);
    let fallback = format!("{context} provider request failed");
    let result_message = json
        .get("resultstr")
        .and_then(json_scalar_string)
        .unwrap_or_default();
    let error_message = json
        .get("errmsg")
        .and_then(json_scalar_string)
        .unwrap_or_default();
    let message = first_non_blank([result_message.as_str(), error_message.as_str(), fallback.as_str()])
        .unwrap_or("Fox provider request failed");
    Err(invalid_payload(format!(
        "Fox provider_error result {result}: {message}"
    )))
}

fn require_chess_list_array(json: &Value) -> ProviderResult<()> {
    json.get("chesslist")
        .and_then(Value::as_array)
        .map(|_| ())
        .ok_or_else(|| invalid_payload("Fox chess list schema drift: missing chesslist array"))
}

fn parse_user_info(payload: &str, query_text: &str) -> ProviderResult<FoxUserInfo> {
    let payload = provider_payload_preflight("Fox", "user payload", payload)?;
    let json: Value = serde_json::from_str(payload)
        .map_err(|err| invalid_payload(format!("failed to parse Fox user JSON: {err}")))?;
    let result = if json.get("result").is_some() {
        json.get("result").and_then(json_i64).unwrap_or(-1)
    } else {
        json.get("errcode").and_then(json_i64).unwrap_or(-1)
    };
    if result != 0 {
        let fallback = format!("Can't find a Fox account for nickname: {query_text}");
        let result_message = json
            .get("resultstr")
            .and_then(json_scalar_string)
            .unwrap_or_default();
        let error_message = json
            .get("errmsg")
            .and_then(json_scalar_string)
            .unwrap_or_default();
        let message = first_non_blank([result_message.as_str(), error_message.as_str(), fallback.as_str()])
            .unwrap_or("Fox user lookup failed")
            .to_string();
        return Err(invalid_payload(format!(
            "Fox provider_error result {result}: {message}"
        )));
    }

    let uid = json
        .get("uid")
        .and_then(json_scalar_string)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| invalid_payload("Fox account was found, but the numeric UID was empty."))?;
    let username = json
        .get("username")
        .and_then(json_scalar_string)
        .unwrap_or_default();
    let name = json.get("name").and_then(json_scalar_string).unwrap_or_default();
    let english_name = json
        .get("englishname")
        .and_then(json_scalar_string)
        .unwrap_or_default();
    let nickname = first_non_blank([
        username.as_str(),
        name.as_str(),
        english_name.as_str(),
        query_text,
    ])
    .unwrap_or(query_text)
    .to_string();

    Ok(FoxUserInfo { uid, nickname })
}

fn wrap_chess_list_with_user_info(
    mut result: ProviderFetchResult,
    uid: &str,
    nickname: &str,
    query_text: &str,
) -> ProviderResult<ProviderFetchResult> {
    let payload = provider_payload_preflight("Fox", "chess list payload", &result.payload)?;
    let mut json: Value = serde_json::from_str(payload)
        .map_err(|err| invalid_payload(format!("failed to parse Fox chess list JSON: {err}")))?;
    fox_provider_result_error(&json, "Fox chess list")?;
    require_chess_list_array(&json)?;
    let Some(object) = json.as_object_mut() else {
        return Err(invalid_payload("Fox chess list payload JSON must be an object"));
    };
    let uid = uid.trim();
    let nickname = nickname.trim();
    let query_text = query_text.trim();
    if !uid.is_empty() {
        object.insert("fox_uid".to_string(), Value::String(uid.to_string()));
        result.metadata.source_id = result.metadata.source_id.or_else(|| Some(uid.to_string()));
        result
            .metadata
            .extra
            .insert("fox_uid".to_string(), uid.to_string());
    }
    if !nickname.is_empty() {
        object.insert("fox_nickname".to_string(), Value::String(nickname.to_string()));
        result
            .metadata
            .extra
            .insert("fox_nickname".to_string(), nickname.to_string());
    }
    if !query_text.is_empty() {
        object.insert("fox_query".to_string(), Value::String(query_text.to_string()));
        result
            .metadata
            .extra
            .insert("fox_query".to_string(), query_text.to_string());
    }
    result.payload = json.to_string();
    Ok(result)
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FoxUserInfo {
    uid: String,
    nickname: String,
}

fn metadata_from_sgf(sgf: &str) -> ProviderGameMetadata {
    let mut metadata = ProviderGameMetadata::default();
    if let Some(root) = parse_root_properties(sgf) {
        set_extra_from_property(&root, &mut metadata, "PB", "black_name");
        set_extra_from_property(&root, &mut metadata, "PW", "white_name");
        set_extra_from_property(&root, &mut metadata, "RE", "result");
        set_extra_from_property(&root, &mut metadata, "SZ", "board_size");
        set_extra_from_property(&root, &mut metadata, "KM", "komi");
        set_extra_from_property(&root, &mut metadata, "HA", "handicap");
        set_extra_from_property(&root, &mut metadata, "DT", "date");
        metadata.title = first_non_blank([
            root.get("GN").map(String::as_str).unwrap_or_default(),
            root.get("EV").map(String::as_str).unwrap_or_default(),
        ])
        .map(ToString::to_string);
    }
    metadata
}

fn metadata_summary(metadata: &ProviderGameMetadata) -> ProviderGameSummary {
    ProviderGameSummary {
        provider: ProviderKind::Fox,
        source_id: metadata.source_id.clone(),
        board_size: metadata
            .extra
            .get("board_size")
            .and_then(|value| value.parse().ok()),
        komi: metadata.extra.get("komi").and_then(|value| value.parse().ok()),
        handicap: metadata
            .extra
            .get("handicap")
            .and_then(|value| value.parse().ok()),
        black_name: metadata.extra.get("black_name").cloned(),
        white_name: metadata.extra.get("white_name").cloned(),
        result: metadata.extra.get("result").cloned(),
        date: metadata.extra.get("date").cloned(),
        move_count: None,
    }
}

fn enrich_metadata_from_json(json: &Value, metadata: &mut ProviderGameMetadata) {
    for key in ["chessid", "chess_id", "id"] {
        if let Some(value) = json.get(key).and_then(json_scalar_string) {
            if !value.trim().is_empty() {
                metadata.source_id = Some(value);
                break;
            }
        }
    }
    if let Some(value) = json.get("result").and_then(json_scalar_string) {
        metadata.provider_status = Some(value);
    }
    if let Some(value) = json.get("resultstr").and_then(json_scalar_string) {
        metadata.extra.insert("provider_message".to_string(), value);
    }
}

fn set_extra_from_property(
    root: &BTreeMap<String, String>,
    metadata: &mut ProviderGameMetadata,
    property_name: &str,
    extra_name: &str,
) {
    if let Some(value) = root.get(property_name).filter(|value| !value.trim().is_empty()) {
        metadata.extra.insert(extra_name.to_string(), value.clone());
    }
}

fn parse_root_properties(sgf: &str) -> Option<BTreeMap<String, String>> {
    let mut parser = SgfParser::new(sgf);
    parser.skip_whitespace();
    let tree = parser.parse_tree().ok()?;
    let mut out = BTreeMap::new();
    for property in tree.nodes.first()?.properties.iter() {
        if let Some(value) = property.values.first() {
            out.insert(property.name.clone(), value.clone());
        }
    }
    Some(out)
}

fn json_scalar_string(value: &Value) -> Option<String> {
    match value {
        Value::String(value) => Some(value.trim().to_string()),
        Value::Number(value) => Some(value.to_string()),
        Value::Bool(value) => Some(value.to_string()),
        _ => None,
    }
}

fn json_i64(value: &Value) -> Option<i64> {
    match value {
        Value::Number(value) => value.as_i64(),
        Value::String(value) => value.trim().parse().ok(),
        _ => None,
    }
}

fn merge_metadata(target: &mut ProviderGameMetadata, source: ProviderGameMetadata) {
    target.source_url = target.source_url.take().or(source.source_url);
    target.request_url = target.request_url.take().or(source.request_url);
    target.source_id = target.source_id.take().or(source.source_id);
    target.room_id = target.room_id.take().or(source.room_id);
    target.title = target.title.take().or(source.title);
    target.provider_status = target.provider_status.take().or(source.provider_status);
    target.extra.extend(source.extra);
}

fn get_request(url: String, source_id: Option<String>) -> ProviderFetchRequest {
    ProviderFetchRequest {
        provider: ProviderKind::Fox,
        url,
        method: ProviderFetchMethod::Get,
        headers: default_headers(FOX_MOBILE_USER_AGENT),
        body: None,
        source_url: None,
        source_id,
        timeout_ms: Some(FOX_HTTP_READ_TIMEOUT_MS),
    }
}

fn post_form_request(url: String, body: String, source_id: Option<String>) -> ProviderFetchRequest {
    let mut headers = default_headers(FOX_MOBILE_USER_AGENT);
    headers.insert("Content-Type".to_string(), FORM_URLENCODED.to_string());
    ProviderFetchRequest {
        provider: ProviderKind::Fox,
        url,
        method: ProviderFetchMethod::Post,
        headers,
        body: Some(body),
        source_url: None,
        source_id,
        timeout_ms: Some(FOX_HTTP_READ_TIMEOUT_MS),
    }
}

fn default_headers(user_agent: &str) -> BTreeMap<String, String> {
    BTreeMap::from([
        (
            "Accept".to_string(),
            "application/json,text/plain,*/*".to_string(),
        ),
        ("Connection".to_string(), "close".to_string()),
        ("User-Agent".to_string(), user_agent.to_string()),
    ])
}

fn split_once_whitespace(value: &str) -> Option<(&str, &str)> {
    let value = value.trim();
    let split_at = value.find(char::is_whitespace)?;
    let (left, right) = value.split_at(split_at);
    Some((left, right.trim()))
}

fn url_encode(value: &str) -> String {
    let mut out = String::new();
    for byte in value.as_bytes() {
        match *byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'.' | b'-' | b'*' | b'_' => {
                out.push(*byte as char);
            }
            b' ' => out.push('+'),
            byte => out.push_str(&format!("%{byte:02X}")),
        }
    }
    out
}

impl<'a> SgfParser<'a> {
    fn new(input: &'a str) -> Self {
        Self { input, index: 0 }
    }

    fn parse_tree(&mut self) -> Result<SgfTree, ()> {
        self.expect('(')?;
        self.skip_whitespace();
        let mut nodes = Vec::new();
        while self.peek() == Some(';') {
            nodes.push(self.parse_node()?);
            self.skip_whitespace();
        }
        while self.peek() == Some('(') {
            self.parse_tree()?;
            self.skip_whitespace();
        }
        self.expect(')')?;
        Ok(SgfTree { nodes })
    }

    fn parse_node(&mut self) -> Result<SgfNode, ()> {
        self.expect(';')?;
        let mut properties = Vec::new();
        loop {
            self.skip_whitespace();
            match self.peek() {
                None | Some(';') | Some('(') | Some(')') => break,
                _ => properties.push(self.parse_property()?),
            }
        }
        Ok(SgfNode { properties })
    }

    fn parse_property(&mut self) -> Result<SgfProperty, ()> {
        let name_start = self.index;
        while let Some(current) = self.peek() {
            if current.is_ascii_alphabetic() {
                self.index += current.len_utf8();
            } else {
                break;
            }
        }
        if name_start == self.index {
            return Err(());
        }
        let name = self.input[name_start..self.index].to_string();
        self.skip_whitespace();
        let mut values = Vec::new();
        while self.peek() == Some('[') {
            values.push(self.parse_value()?);
            self.skip_whitespace();
        }
        if values.is_empty() {
            return Err(());
        }
        Ok(SgfProperty { name, values })
    }

    fn parse_value(&mut self) -> Result<String, ()> {
        self.expect('[')?;
        let mut value = String::new();
        while let Some(current) = self.peek() {
            self.index += current.len_utf8();
            if current == '\\' {
                if let Some(next) = self.peek() {
                    self.index += next.len_utf8();
                    value.push(current);
                    value.push(next);
                }
            } else if current == ']' {
                return Ok(value);
            } else {
                value.push(current);
            }
        }
        Err(())
    }

    fn skip_whitespace(&mut self) {
        while let Some(current) = self.peek() {
            if current.is_whitespace() {
                self.index += current.len_utf8();
            } else {
                break;
            }
        }
    }

    fn expect(&mut self, expected: char) -> Result<(), ()> {
        if self.peek() == Some(expected) {
            self.index += expected.len_utf8();
            Ok(())
        } else {
            Err(())
        }
    }

    fn peek(&self) -> Option<char> {
        self.input[self.index..].chars().next()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use app_model::ProviderErrorKind;
    use provider_core::transport_failed;
    use std::collections::VecDeque;
    use std::sync::Mutex;

    #[test]
    fn normalize_payload_promotes_leading_setup_nodes_into_root() {
        let payload = serde_json::json!({
            "chess": "(;GM[1]FF[4]SZ[19]KM[0]HA[2]PB[Black]PW[White];AB[pd][dp];W[pp];B[dd])"
        })
        .to_string();

        let normalized = normalize_payload(&payload).unwrap();

        assert!(
            normalized.sgf_text.starts_with("(;GM[1]FF[4]"),
            "{}",
            normalized.sgf_text
        );
        assert!(normalized.sgf_text.contains("HA[2]"), "{}", normalized.sgf_text);
        assert!(
            normalized.sgf_text.contains("AB[pd][dp]"),
            "{}",
            normalized.sgf_text
        );
        assert!(
            normalized.sgf_text.contains(";W[pp];B[dd])"),
            "{}",
            normalized.sgf_text
        );
        assert!(
            !normalized.sgf_text.contains(";AB[pd][dp];"),
            "{}",
            normalized.sgf_text
        );
    }

    #[test]
    fn sanitize_removes_backslashes_outside_values_only() {
        let sgf = "\\(;GM[1]C[a\\]b];B[aa]\\)";

        assert_eq!(sanitize_sgf(sgf), "(;GM[1]C[a\\]b];B[aa])");
    }

    #[test]
    fn import_payload_extracts_metadata() {
        let request = ProviderImportRequest {
            provider: ProviderKind::Fox,
            payload: serde_json::json!({
                "result": 0,
                "chessid": "abc123",
                "chess": "(;GM[1]FF[4]SZ[19]KM[6.5]PB[Black]PW[White]RE[B+R];B[dd])"
            })
            .to_string(),
            source_url: Some("https://fox.example/game/abc123".to_string()),
            source_id: None,
            metadata: ProviderGameMetadata::default(),
        };

        let result = import_payload(request).unwrap();

        assert_eq!(result.provider, ProviderKind::Fox);
        assert_eq!(result.summary.source_id.as_deref(), Some("abc123"));
        assert_eq!(result.summary.black_name.as_deref(), Some("Black"));
        assert_eq!(result.summary.white_name.as_deref(), Some("White"));
        assert_eq!(result.summary.result.as_deref(), Some("B+R"));
        assert_eq!(
            result.metadata.source_url.as_deref(),
            Some("https://fox.example/game/abc123")
        );
    }

    #[test]
    fn normalize_payload_recovers_windowed_fox_chunks_from_json() {
        let payload = serde_json::json!({
            "chessid": "windowed-json",
            "result": 0,
            "resultstr": "ok",
            "chess": windowed_fox_sgf()
        })
        .to_string();

        let normalized = normalize_payload(&payload).unwrap();
        let document = sgf::parse_sgf(&normalized.sgf_text).unwrap();

        assert_eq!(normalized.metadata.source_id.as_deref(), Some("windowed-json"));
        assert_eq!(
            normalized.metadata.extra.get("black_name").map(String::as_str),
            Some("Black")
        );
        assert_eq!(
            normalized.metadata.extra.get("white_name").map(String::as_str),
            Some("White")
        );
        assert_eq!(normalized.metadata.provider_status.as_deref(), Some("0"));
        assert_eq!(
            normalized
                .metadata
                .extra
                .get("provider_message")
                .map(String::as_str),
            Some("ok")
        );
        assert_eq!(normalized.sgf_text.matches('(').count(), 1);
        assert_eq!(document.moves.len(), 84, "{}", normalized.sgf_text);
    }

    #[test]
    fn import_payload_recovers_windowed_fox_chunks_from_raw_sgf() {
        let request = ProviderImportRequest {
            provider: ProviderKind::Fox,
            payload: windowed_fox_sgf(),
            source_url: Some("https://fox.example/game/windowed-raw".to_string()),
            source_id: Some("windowed-raw".to_string()),
            metadata: ProviderGameMetadata::default(),
        };

        let result = import_payload(request).unwrap();
        let document = sgf::parse_sgf(&result.sgf_text).unwrap();

        assert_eq!(result.provider, ProviderKind::Fox);
        assert_eq!(result.summary.source_id.as_deref(), Some("windowed-raw"));
        assert_eq!(result.summary.black_name.as_deref(), Some("Black"));
        assert_eq!(result.summary.white_name.as_deref(), Some("White"));
        assert_eq!(
            result.metadata.source_url.as_deref(),
            Some("https://fox.example/game/windowed-raw")
        );
        assert_eq!(result.sgf_text.matches('(').count(), 1);
        assert_eq!(document.moves.len(), 84, "{}", result.sgf_text);
    }

    #[test]
    fn raw_sgf_payload_imports_without_json_wrapper() {
        let normalized = normalize_payload("(;GM[1]SZ[19];B[aa](;W[bb])(;W[cc]))").unwrap();

        assert_eq!(normalized.sgf_text, "(;GM[1]FF[4]CA[UTF-8]SZ[19];B[aa];W[bb])");
    }

    #[test]
    fn builds_legacy_fox_endpoint_requests() {
        assert_eq!(
            parse_fetch_command("uid 12345 678").unwrap(),
            FoxFetchCommand::Uid {
                uid: "12345".to_string(),
                last_code: "678".to_string()
            }
        );
        assert_eq!(
            parse_fetch_command("uid 12345").unwrap(),
            FoxFetchCommand::Uid {
                uid: "12345".to_string(),
                last_code: "0".to_string()
            }
        );

        let user_request = query_user_request("棋 手").unwrap();
        assert_eq!(
            user_request.url,
            format!("{FOX_QUERY_USER_URL}?srcuid=0&username=%E6%A3%8B+%E6%89%8B")
        );
        assert_eq!(user_request.method, ProviderFetchMethod::Get);
        assert_eq!(
            user_request.headers.get("User-Agent").map(String::as_str),
            Some(FOX_MOBILE_USER_AGENT)
        );

        let list_request = chess_list_request("12345", "678").unwrap();
        assert_eq!(
            list_request.url,
            format!(
                "{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid=12345&type=1&lastcode=678&searchkey=&uin=12345"
            )
        );
        assert_eq!(list_request.timeout_ms, Some(FOX_HTTP_READ_TIMEOUT_MS));

        let cgi_requests = cgi_sgf_requests("game 1").unwrap();
        assert_eq!(cgi_requests.len(), 2);
        assert_eq!(cgi_requests[0].url, FOX_SGF_CGI_URLS[0]);
        assert_eq!(cgi_requests[0].method, ProviderFetchMethod::Post);
        assert_eq!(cgi_requests[0].body.as_deref(), Some("chessid=game+1"));
        assert_eq!(
            cgi_requests[0].headers.get("Content-Type").map(String::as_str),
            Some(FORM_URLENCODED)
        );
        assert_eq!(
            cgi_requests[0].headers.get("User-Agent").map(String::as_str),
            Some(FOX_CGI_USER_AGENT)
        );

        let h5_request = h5_sgf_request("game 1").unwrap();
        assert_eq!(
            h5_request.url,
            format!("{FOX_BASE_URL}/YHWQFetchChess?chessid=game+1")
        );
    }

    #[test]
    fn chessid_fetch_preserves_cgi_fallback_warnings_when_h5_succeeds() {
        let transport = SequenceTransport::new(vec![
            Err(transport_failed("connection reset")),
            Ok(fetch_response(
                FOX_SGF_CGI_URLS[1],
                200,
                r#"{"result":1,"resultstr":"not found","chess":"(;SZ[19];B[aa])"}"#,
            )),
            Ok(fetch_response(
                &format!("{FOX_BASE_URL}/YHWQFetchChess?chessid=game+1"),
                200,
                r#"{"result":0,"resultstr":"ok","chessid":"game 1","chess":"(;SZ[19]PB[Black]PW[White];B[aa](;W[bb])(;W[cc]))"}"#,
            )),
        ]);

        let result = fetch_command("chessid game 1", &transport).unwrap();
        let requests = transport.requests();

        assert_eq!(requests.len(), 3);
        assert_eq!(requests[0].url, FOX_SGF_CGI_URLS[0]);
        assert_eq!(requests[1].url, FOX_SGF_CGI_URLS[1]);
        assert_eq!(
            requests[2].url,
            format!("{FOX_BASE_URL}/YHWQFetchChess?chessid=game+1")
        );
        assert_eq!(result.metadata.source_id.as_deref(), Some("game 1"));
        assert_eq!(result.metadata.provider_status.as_deref(), Some("0"));
        assert_eq!(
            result.metadata.extra.get("provider_message").map(String::as_str),
            Some("ok")
        );
        assert_eq!(result.warnings.len(), 2);
        assert!(result.warnings[0].contains("Fox CGI fallback"));
        assert!(result.warnings[0].contains(FOX_SGF_CGI_URLS[0]));
        assert!(result.warnings[0].contains("connection reset"));
        assert!(result.warnings[1].contains(FOX_SGF_CGI_URLS[1]));
        assert!(result.warnings[1].contains("result 1: not found"));
        let json: Value = serde_json::from_str(&result.payload).unwrap();
        assert_eq!(
            json["chess"].as_str().unwrap(),
            "(;GM[1]FF[4]CA[UTF-8]SZ[19]PB[Black]PW[White];B[aa];W[bb])"
        );
    }

    #[test]
    fn chessid_fetch_uses_first_valid_cgi_payload_without_h5_request() {
        let transport = SequenceTransport::new(vec![Ok(fetch_response(
            FOX_SGF_CGI_URLS[0],
            200,
            r#"{"result":0,"resultstr":"ok","chessid":"abc123","chess":"(;SZ[19];B[aa])"}"#,
        ))]);

        let result = fetch_command("chessid abc123", &transport).unwrap();

        assert_eq!(transport.requests().len(), 1);
        assert_eq!(result.url, FOX_SGF_CGI_URLS[0]);
        assert_eq!(result.metadata.source_id.as_deref(), Some("abc123"));
        assert!(result.warnings.is_empty());
        assert!(result
            .payload
            .contains(r#""chess":"(;GM[1]FF[4]CA[UTF-8]SZ[19];B[aa])""#));
    }

    #[test]
    fn user_name_fetch_queries_user_then_wraps_chess_list_with_metadata() {
        let transport = SequenceTransport::new(vec![
            Ok(fetch_response(
                &format!("{FOX_QUERY_USER_URL}?srcuid=0&username=Good+Player"),
                200,
                r#"{"result":0,"uid":2468,"username":"Good Player"}"#,
            )),
            Ok(fetch_response(
                &format!("{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid=2468&type=1&lastcode=0&searchkey=&uin=2468"),
                200,
                r#"{"result":0,"chesslist":[]}"#,
            )),
        ]);

        let result = fetch_command("user_name Good Player", &transport).unwrap();
        let requests = transport.requests();

        assert_eq!(requests.len(), 2);
        assert_eq!(
            requests[0].url,
            format!("{FOX_QUERY_USER_URL}?srcuid=0&username=Good+Player")
        );
        assert_eq!(
            requests[1].url,
            format!("{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid=2468&type=1&lastcode=0&searchkey=&uin=2468")
        );
        let json: Value = serde_json::from_str(&result.payload).unwrap();
        assert_eq!(json["fox_uid"], "2468");
        assert_eq!(json["fox_nickname"], "Good Player");
        assert_eq!(json["fox_query"], "Good Player");
        assert_eq!(result.metadata.source_id.as_deref(), Some("2468"));
        assert_eq!(
            result.metadata.extra.get("fox_query").map(String::as_str),
            Some("Good Player")
        );
    }

    #[test]
    fn numeric_user_name_fetches_list_directly() {
        let transport = SequenceTransport::new(vec![Ok(fetch_response(
            &format!("{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid=2468&type=1&lastcode=0&searchkey=&uin=2468"),
            200,
            r#"{"result":0,"chesslist":[]}"#,
        ))]);

        let result = fetch_command("user_name 2468", &transport).unwrap();

        assert_eq!(transport.requests().len(), 1);
        let json: Value = serde_json::from_str(&result.payload).unwrap();
        assert_eq!(json["fox_uid"], "2468");
        assert_eq!(json["fox_nickname"], "2468");
        assert_eq!(json["fox_query"], "2468");
    }

    #[test]
    fn cgi_fixture_payload_normalizes_through_import_path() {
        let request = ProviderImportRequest {
            provider: ProviderKind::Fox,
            payload: r#"{"result":0,"resultstr":"ok","chessid":"cgi-1","chess":"(;SZ[19]PB[Black]PW[White];B[aa](;W[bb])(;W[cc]))"}"#.to_string(),
            source_url: None,
            source_id: None,
            metadata: ProviderGameMetadata::default(),
        };

        let result = import_payload(request).unwrap();

        assert_eq!(result.summary.source_id.as_deref(), Some("cgi-1"));
        assert_eq!(
            result.sgf_text,
            "(;GM[1]FF[4]CA[UTF-8]SZ[19]PB[Black]PW[White];B[aa];W[bb])"
        );
        assert_eq!(result.metadata.provider_status.as_deref(), Some("0"));
    }

    #[test]
    fn provider_fixtures_cover_fox_success_shapes() {
        let normalized = normalize_payload(include_str!(
            "../../../tests/fixtures/provider/fox/sgf_success.json"
        ))
        .unwrap();

        assert_eq!(normalized.metadata.source_id.as_deref(), Some("fox-fixture-1"));
        assert_eq!(
            normalized.sgf_text,
            "(;GM[1]FF[4]CA[UTF-8]SZ[19]PB[Black Fixture]PW[White Fixture]RE[B+R];B[dd];W[pq])"
        );

        let transport = SequenceTransport::new(vec![
            Ok(fetch_response(
                &format!("{FOX_QUERY_USER_URL}?srcuid=0&username=Fixture+Player"),
                200,
                include_str!("../../../tests/fixtures/provider/fox/user_success.json"),
            )),
            Ok(fetch_response(
                &format!("{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid=2468&type=1&lastcode=0&searchkey=&uin=2468"),
                200,
                include_str!("../../../tests/fixtures/provider/fox/chess_list_success.json"),
            )),
        ]);

        let result = fetch_command("user_name Fixture Player", &transport).unwrap();
        let json: Value = serde_json::from_str(&result.payload).unwrap();
        assert_eq!(json["fox_uid"], "2468");
        assert_eq!(json["fox_nickname"], "Fixture Player");
        assert_eq!(json["chesslist"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn provider_fixtures_reject_fox_session_rate_limit_antibot_schema_empty_and_malformed() {
        let session = normalize_payload(include_str!(
            "../../../tests/fixtures/provider/fox/unauthorized.json"
        ))
        .unwrap_err();
        assert_eq!(session.kind, ProviderErrorKind::InvalidPayload);
        assert!(session.message.contains("provider_error"));
        assert!(session.message.contains("session expired"));

        let rate_limit = normalize_payload(include_str!(
            "../../../tests/fixtures/provider/fox/rate_limit.json"
        ))
        .unwrap_err();
        assert_eq!(rate_limit.kind, ProviderErrorKind::InvalidPayload);
        assert!(rate_limit.message.contains("too many requests"));

        let html = normalize_payload(include_str!("../../../tests/fixtures/provider/fox/anti_bot.html"))
            .unwrap_err();
        assert_eq!(html.kind, ProviderErrorKind::InvalidPayload);
        assert!(html.message.contains("anti_bot_html_challenge"));

        let schema = normalize_payload(include_str!(
            "../../../tests/fixtures/provider/fox/schema_drift.json"
        ))
        .unwrap_err();
        assert_eq!(schema.kind, ProviderErrorKind::InvalidPayload);
        assert!(schema.message.contains("does not contain chess"));

        let empty = normalize_payload(include_str!(
            "../../../tests/fixtures/provider/fox/empty_result.json"
        ))
        .unwrap_err();
        assert_eq!(empty.kind, ProviderErrorKind::InvalidPayload);
        assert!(empty.message.contains("chess SGF text is empty"));

        let malformed = normalize_payload(include_str!(
            "../../../tests/fixtures/provider/fox/malformed.json"
        ))
        .unwrap_err();
        assert_eq!(malformed.kind, ProviderErrorKind::InvalidPayload);
        assert!(malformed.message.contains("failed to parse Fox payload JSON"));
    }

    #[test]
    fn fox_http_and_chess_list_failures_are_typed_without_empty_success() {
        let unauthorized = SequenceTransport::new(vec![Ok(fetch_response(
            &format!(
                "{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid=42&type=1&lastcode=0&searchkey=&uin=42"
            ),
            401,
            include_str!("../../../tests/fixtures/provider/fox/unauthorized.json"),
        ))]);

        let error = fetch_command("uid 42", &unauthorized).unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::TransportFailed);
        assert!(error.message.contains("unauthorized_or_session_expired"));

        let rate_limited = SequenceTransport::new(vec![Ok(fetch_response(
            &format!(
                "{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid=42&type=1&lastcode=0&searchkey=&uin=42"
            ),
            429,
            include_str!("../../../tests/fixtures/provider/fox/rate_limit.json"),
        ))]);
        let error = fetch_command("uid 42", &rate_limited).unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::TransportFailed);
        assert!(error.message.contains("rate_limited"));

        let drift = SequenceTransport::new(vec![Ok(fetch_response(
            &format!(
                "{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid=42&type=1&lastcode=0&searchkey=&uin=42"
            ),
            200,
            include_str!("../../../tests/fixtures/provider/fox/schema_drift.json"),
        ))]);
        let error = fetch_command("uid 42", &drift).unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::InvalidPayload);
        assert!(error.message.contains("chess list schema drift"));
    }

    #[test]
    fn failed_h5_fallback_reports_invalid_payload() {
        let transport = SequenceTransport::new(vec![
            Ok(fetch_response(FOX_SGF_CGI_URLS[0], 200, r#"{"result":1}"#)),
            Ok(fetch_response(FOX_SGF_CGI_URLS[1], 200, "")),
            Ok(fetch_response(
                &format!("{FOX_BASE_URL}/YHWQFetchChess?chessid=abc"),
                200,
                r#"{"result":0,"chess":""}"#,
            )),
        ]);

        let error = fetch_command("chessid abc", &transport).unwrap_err();

        assert_eq!(error.kind, ProviderErrorKind::InvalidPayload);
        assert!(error.message.contains("H5 normalization failed"));
        assert!(error.message.contains(FOX_SGF_CGI_URLS[0]));
        assert!(error.message.contains("result 1"));
        assert!(error.message.contains(FOX_SGF_CGI_URLS[1]));
        assert!(error.message.contains("payload is empty"));
        assert!(error.message.contains("Fox payload chess SGF text is empty"));
    }

    #[test]
    fn http_failure_reports_transport_failed() {
        let transport = SequenceTransport::new(vec![Ok(fetch_response(
            &format!(
                "{FOX_BASE_URL}/YHWQFetchChessList?srcuid=0&dstuid=42&type=1&lastcode=0&searchkey=&uin=42"
            ),
            500,
            "server error",
        ))]);

        let error = fetch_command("uid 42", &transport).unwrap_err();

        assert_eq!(error.kind, ProviderErrorKind::TransportFailed);
    }

    fn windowed_fox_sgf() -> String {
        let mut input = String::from("(;SZ[19]PB[Black]PW[White]");
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
        input
    }

    fn test_sgf_coord(index: usize) -> String {
        let x = (index % 19) as u8;
        let y = (index / 19) as u8;
        format!("{}{}", (b'a' + x) as char, (b'a' + y) as char)
    }

    fn fetch_response(url: &str, status_code: u16, payload: &str) -> ProviderFetchResult {
        ProviderFetchResult {
            provider: ProviderKind::Fox,
            url: url.to_string(),
            status_code,
            payload: payload.to_string(),
            headers: BTreeMap::new(),
            content_type: Some("application/json".to_string()),
            metadata: ProviderGameMetadata::default(),
            warnings: Vec::new(),
        }
    }

    struct SequenceTransport {
        requests: Mutex<Vec<ProviderFetchRequest>>,
        responses: Mutex<VecDeque<ProviderResult<ProviderFetchResult>>>,
    }

    impl SequenceTransport {
        fn new(responses: Vec<ProviderResult<ProviderFetchResult>>) -> Self {
            Self {
                requests: Mutex::default(),
                responses: Mutex::new(VecDeque::from(responses)),
            }
        }

        fn requests(&self) -> Vec<ProviderFetchRequest> {
            self.requests.lock().unwrap().clone()
        }
    }

    impl ProviderTransport for SequenceTransport {
        fn fetch(&self, request: &ProviderFetchRequest) -> ProviderResult<ProviderFetchResult> {
            self.requests.lock().unwrap().push(request.clone());
            self.responses
                .lock()
                .unwrap()
                .pop_front()
                .unwrap_or_else(|| Err(transport_failed("missing test response")))
        }
    }
}
