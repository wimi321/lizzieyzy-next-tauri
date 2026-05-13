use app_model::{
    ProviderFetchMethod, ProviderFetchRequest, ProviderFetchResult, ProviderGameMetadata,
    ProviderGameSummary, ProviderImportRequest, ProviderImportResult, ProviderKind,
};
use provider_core::{
    first_non_blank, invalid_payload, invalid_url, provider_http_error, provider_payload_preflight,
    require_non_blank, ProviderResult, ProviderTransport,
};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};

const APP_KEY: &str = "3396jtzhK57XhJom";
const APP_SECRET: &str = "hfdSXRKm0DQyLmNXmNCNkZpjy2o5q1Hk";
const LIST_URL: &str = "https://api.yikeweiqi.com/v2/golive/list";
const DETAIL_URL_PREFIX: &str = "https://api-new.yikeweiqi.com/v1/golives/";
const HTTP_TIMEOUT_MS: u64 = 10_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum YikeRoomKind {
    OldLiveRoom,
    OldLiveBoard,
    GameRoom,
    NewLiveRoom,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct YikeUrlDescriptor {
    pub provider: ProviderKind,
    pub room_kind: YikeRoomKind,
    pub id: String,
    pub room_id: u64,
    pub request_url: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct YikeRequestSignature {
    pub current_time_millis: u64,
    pub nonce: u64,
}

impl YikeRequestSignature {
    pub fn now() -> Self {
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default();
        Self {
            current_time_millis: now.as_millis() as u64,
            nonce: (now.as_nanos() % 100_000_000) as u64,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct YikeLivePage {
    pub since: u64,
    pub games: Vec<YikeLiveGame>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct YikeLiveGame {
    pub id: u64,
    pub version: u64,
    pub hall: u64,
    pub room: u64,
    pub status: i64,
    pub game_name: String,
    pub black_name: String,
    pub white_name: String,
    pub black_county: String,
    pub white_county: String,
    pub game_date: String,
    pub broadcast_time: String,
    pub finish_order: String,
    pub game_result: String,
    pub live_member: String,
    pub hands_count: u64,
    pub person_times: u64,
    pub top_flag: bool,
    pub realtime_analysis_flag: bool,
    pub black_win_rate: f64,
    pub delta: f64,
}

impl YikeLiveGame {
    pub fn to_room_url(&self) -> String {
        let room_path = if self.version == 2 { "new-room" } else { "room" };
        format!(
            "https://home.yikeweiqi.com/#/live/{room_path}/{}/{}/{}",
            self.id, self.hall, self.room
        )
    }

    pub fn status_text(&self) -> String {
        match self.status {
            1 => "直播预告".to_string(),
            2 => "正在直播".to_string(),
            3 => first_non_blank([self.game_result.as_str()])
                .unwrap_or("已结束")
                .to_string(),
            _ => "未知".to_string(),
        }
    }

    pub fn time_text(&self) -> String {
        let date = first_non_blank([self.finish_order.as_str(), self.game_date.as_str()]);
        match (date, first_non_blank([self.broadcast_time.as_str()])) {
            (Some(date), Some(time)) => format!("{date} {time}"),
            (Some(date), None) => date.to_string(),
            (None, Some(time)) => time.to_string(),
            (None, None) => String::new(),
        }
    }

    pub fn player_text(&self, black: bool) -> String {
        let (name, county) = if black {
            (&self.black_name, &self.black_county)
        } else {
            (&self.white_name, &self.white_county)
        };
        match first_non_blank([county.as_str()]) {
            Some(county) => format!("{name} [{county}]"),
            None => name.to_string(),
        }
    }

    pub fn winrate_text(&self) -> String {
        if !self.realtime_analysis_flag || self.black_win_rate < 0.0 {
            return String::new();
        }
        let white_win_rate = (100.0 - self.black_win_rate).clamp(0.0, 100.0);
        let mut rate = format!(
            "黑 {}% / 白 {}%",
            format_one_decimal(self.black_win_rate),
            format_one_decimal(white_win_rate)
        );
        if self.delta.abs() > 0.01 {
            rate.push_str(&format!(" / {}目", format_one_decimal(self.delta)));
        }
        rate
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct YikeLiveDetail {
    pub sgf: String,
    pub status: i64,
    pub game_result: String,
}

pub fn signed_headers(current_time_millis: u64, nonce: u64) -> BTreeMap<String, String> {
    let current_time = current_time_millis.to_string();
    let nonce_text = nonce.to_string();
    let timestamp_hash = md5_hex(current_time.as_bytes());
    let checksum = sha1_hex(format!("{APP_SECRET}{nonce_text}{current_time}").as_bytes());
    let accesstoken = md5_hex(format!("@1%e$5*f@3{timestamp_hash}web").as_bytes());

    BTreeMap::from([
        ("AppKey".to_string(), APP_KEY.to_string()),
        ("CurTime".to_string(), current_time.clone()),
        ("CheckSum".to_string(), checksum),
        ("Nonce".to_string(), nonce_text),
        ("usertoken".to_string(), "-1".to_string()),
        ("version".to_string(), "96813".to_string()),
        ("Platform".to_string(), "web".to_string()),
        ("Content-Type".to_string(), "application/json".to_string()),
        ("timestamp".to_string(), current_time),
        ("uuid".to_string(), "web".to_string()),
        ("accept-language".to_string(), "zh-cn".to_string()),
        ("accesstoken".to_string(), accesstoken),
    ])
}

pub fn live_list_url(official: Option<&str>, page: i64, since: i64) -> String {
    let params = [
        ("p", page.max(1).to_string()),
        ("since", since.max(0).to_string()),
        ("official", official.unwrap_or("").to_string()),
        ("version", "2".to_string()),
    ];
    build_url(LIST_URL, &params)
}

pub fn live_detail_url(id: &str) -> String {
    format!("{DETAIL_URL_PREFIX}{}", form_encode(id))
}

pub fn fetch_live_list<T: ProviderTransport>(
    transport: &T,
    official: Option<&str>,
    page: i64,
    since: i64,
) -> ProviderResult<YikeLivePage> {
    fetch_live_list_with_signature(transport, official, page, since, YikeRequestSignature::now())
}

pub fn fetch_live_list_with_signature<T: ProviderTransport>(
    transport: &T,
    official: Option<&str>,
    page: i64,
    since: i64,
    signature: YikeRequestSignature,
) -> ProviderResult<YikeLivePage> {
    let url = live_list_url(official, page, since);
    let result = transport.fetch(&signed_get_request(url, None, None, signature))?;
    ensure_http_success(&result, "Yike live list request failed")?;
    parse_live_list_json(&result.payload)
}

pub fn fetch_live_detail_import<T: ProviderTransport>(
    transport: &T,
    id: &str,
) -> ProviderResult<ProviderImportResult> {
    fetch_live_detail_import_with_signature(transport, id, YikeRequestSignature::now())
}

pub fn fetch_live_detail_import_with_signature<T: ProviderTransport>(
    transport: &T,
    id: &str,
    signature: YikeRequestSignature,
) -> ProviderResult<ProviderImportResult> {
    let id = require_non_blank(id, "id")?;
    let url = live_detail_url(id);
    let result = transport.fetch(&signed_get_request(
        url.clone(),
        Some(url.clone()),
        Some(id.to_string()),
        signature,
    ))?;
    ensure_http_success(&result, "Yike live detail request failed")?;
    import_live_detail_json(&result.payload, Some(id.to_string()), None, Some(url))
}

pub fn parse_live_list_json(response: &str) -> ProviderResult<YikeLivePage> {
    let root = parse_json(response, "Yike live list")?;
    let status = object_i64(&root, "Status")
        .or_else(|| object_i64(&root, "status"))
        .ok_or_else(|| invalid_payload("Yike live list schema drift: missing Status field"))?;
    if status != 1200 {
        let message = object_string(&root, "Message")
            .or_else(|| object_string(&root, "message"))
            .unwrap_or_else(|| "Yike live list request failed".to_string());
        return Err(invalid_payload(format!(
            "Yike provider_error status {status}: {message}"
        )));
    }

    let result = root
        .get("Result")
        .and_then(Value::as_object)
        .ok_or_else(|| invalid_payload("Yike live list schema drift: missing Result object"))?;
    let since = result.get("since").and_then(value_u64).unwrap_or(0);
    let list = result
        .get("list")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid_payload("Yike live list schema drift: missing Result.list array"))?;
    let games = list.iter().filter_map(YikeLiveGame::from_value).collect();
    Ok(YikeLivePage { since, games })
}

pub fn parse_live_detail_json(response: &str) -> ProviderResult<YikeLiveDetail> {
    parse_live_detail_value(&parse_json(response, "Yike live detail")?)
}

pub fn import_live_detail_json(
    response: &str,
    source_id: Option<String>,
    source_url: Option<String>,
    request_url: Option<String>,
) -> ProviderResult<ProviderImportResult> {
    let detail = parse_live_detail_json(response)?;
    detail_to_import_result(detail, source_id, source_url, request_url)
}

pub fn parse_yike_url(raw_url: &str) -> ProviderResult<YikeUrlDescriptor> {
    let mut url = require_non_blank(raw_url, "url")?.to_string();
    if url.ends_with("/0/0") {
        url.truncate(url.len() - 4);
    }

    if let Some(captures) = new_live_full().captures(&url) {
        let id = captures[3].to_string();
        return Ok(YikeUrlDescriptor {
            provider: ProviderKind::Yike,
            room_kind: YikeRoomKind::NewLiveRoom,
            room_id: parse_u64_or(&captures[4], parse_u64_or(&id, 0)),
            request_url: live_detail_url(&id),
            id,
        });
    }

    if let Some(captures) = new_live_short().captures(&url) {
        let id = captures[3].to_string();
        return Ok(YikeUrlDescriptor {
            provider: ProviderKind::Yike,
            room_kind: YikeRoomKind::NewLiveRoom,
            room_id: parse_u64_or(&id, 0),
            request_url: live_detail_url(&id),
            id,
        });
    }

    if let Some(captures) = old_live_full().captures(&url) {
        let id = captures[3].to_string();
        let parsed_room_id = parse_i64_or(&captures[4], -1);
        let (room_kind, room_id) = if parsed_room_id < 0 {
            (YikeRoomKind::OldLiveBoard, parse_u64_or(&id, 0))
        } else {
            (YikeRoomKind::OldLiveRoom, parsed_room_id as u64)
        };
        if !id.trim().is_empty() && room_id > 0 {
            return Ok(YikeUrlDescriptor {
                provider: ProviderKind::Yike,
                room_kind,
                id: id.clone(),
                room_id,
                request_url: format!("https://api.{}/golive/dtl?id={id}&flag=1", &captures[1]),
            });
        }
    }

    if let Some(captures) = old_live_short().captures(&url) {
        let id = captures[3].to_string();
        if !id.trim().is_empty() {
            return Ok(YikeUrlDescriptor {
                provider: ProviderKind::Yike,
                room_kind: YikeRoomKind::OldLiveBoard,
                room_id: parse_u64_or(&id, 0),
                request_url: format!("https://api.{}/golive/dtl?id={id}", &captures[1]),
                id,
            });
        }
    }

    if let Some(captures) = game_room().captures(&url) {
        let room_id = parse_u64_or(&captures[3], 0);
        if room_id > 0 {
            return Ok(YikeUrlDescriptor {
                provider: ProviderKind::Yike,
                room_kind: YikeRoomKind::GameRoom,
                id: captures[3].to_string(),
                room_id,
                request_url: format!("https://api.{}/golive/dtl?id={room_id}", &captures[1]),
            });
        }
    }

    if let Some(captures) = hall_room().captures(&url) {
        let room_id = parse_u64_or(&captures[3], 0);
        if room_id > 0 {
            return Ok(YikeUrlDescriptor {
                provider: ProviderKind::Yike,
                room_kind: YikeRoomKind::GameRoom,
                id: captures[3].to_string(),
                room_id,
                request_url: format!("https://api.{}/golive/dtl?id={room_id}", &captures[1]),
            });
        }
    }

    Err(invalid_url("unsupported Yike URL"))
}

pub fn import_payload(request: ProviderImportRequest) -> ProviderResult<ProviderImportResult> {
    let payload = require_non_blank(&request.payload, "payload")?;
    let (sgf_text, mut metadata) = extract_sgf_payload(payload)?;
    metadata.source_url = metadata.source_url.or(request.source_url);
    metadata.source_id = metadata.source_id.or(request.source_id);
    merge_metadata(&mut metadata, request.metadata);

    let source_id = metadata.source_id.clone();
    let provider_result = metadata.extra.get("provider_result").cloned();
    Ok(ProviderImportResult {
        provider: ProviderKind::Yike,
        sgf_text: without_variations(&sgf_text),
        summary: ProviderGameSummary {
            provider: ProviderKind::Yike,
            source_id,
            result: provider_result,
            ..ProviderGameSummary::empty(ProviderKind::Yike)
        },
        metadata,
        warnings: Vec::new(),
    })
}

pub fn without_variations(sgf: &str) -> String {
    if sgf.is_empty() {
        return sgf.to_string();
    }
    let Some(start) = sgf.find('(') else {
        return sgf.to_string();
    };
    let chars: Vec<char> = sgf.chars().collect();
    match parse_game_tree(&chars, start) {
        Some((text, _)) => text,
        None => sgf.to_string(),
    }
}

fn extract_sgf_payload(payload: &str) -> ProviderResult<(String, ProviderGameMetadata)> {
    if payload.trim_start().starts_with('(') {
        return Ok((payload.trim().to_string(), ProviderGameMetadata::default()));
    }

    let payload = provider_payload_preflight("Yike", "payload", payload)?;
    let json: Value = serde_json::from_str(payload)
        .map_err(|err| invalid_payload(format!("failed to parse Yike payload JSON: {err}")))?;
    if let Some(detail) = extract_live_detail_value(&json)? {
        let mut metadata = ProviderGameMetadata {
            provider_status: Some(detail.status.to_string()),
            ..ProviderGameMetadata::default()
        };
        if !detail.game_result.trim().is_empty() {
            metadata
                .extra
                .insert("provider_result".to_string(), detail.game_result);
        }
        return Ok((detail.sgf, metadata));
    }

    let sgf = first_json_string(&json, &["sgf", "clean_sgf", "chess"])
        .ok_or_else(|| invalid_payload("Yike payload does not contain sgf or clean_sgf"))?;
    let mut metadata = ProviderGameMetadata::default();
    if let Some(status) = first_json_string(&json, &["status", "Status"]) {
        metadata.provider_status = Some(status);
    }
    if let Some(result) = first_json_string(&json, &["game_result", "result", "Result"]) {
        metadata.extra.insert("provider_result".to_string(), result);
    }
    Ok((sgf, metadata))
}

fn first_json_string(value: &Value, keys: &[&str]) -> Option<String> {
    match value {
        Value::Object(map) => {
            for key in keys {
                if let Some(value) = map.get(*key).and_then(json_scalar_string) {
                    if !value.trim().is_empty() {
                        return Some(value);
                    }
                }
            }
            map.values().find_map(|value| first_json_string(value, keys))
        }
        Value::Array(values) => values.iter().find_map(|value| first_json_string(value, keys)),
        _ => None,
    }
}

fn json_scalar_string(value: &Value) -> Option<String> {
    match value {
        Value::String(value) => Some(value.trim().to_string()),
        Value::Number(value) => Some(value.to_string()),
        Value::Bool(value) => Some(value.to_string()),
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

fn signed_get_request(
    url: String,
    source_url: Option<String>,
    source_id: Option<String>,
    signature: YikeRequestSignature,
) -> ProviderFetchRequest {
    ProviderFetchRequest {
        provider: ProviderKind::Yike,
        url,
        method: ProviderFetchMethod::Get,
        headers: signed_headers(signature.current_time_millis, signature.nonce),
        body: None,
        source_url,
        source_id,
        timeout_ms: Some(HTTP_TIMEOUT_MS),
    }
}

fn ensure_http_success(result: &ProviderFetchResult, context: &str) -> ProviderResult<()> {
    if result.status_code >= 400 {
        return Err(provider_http_error(
            "Yike",
            result.status_code,
            &result.payload,
            context,
        ));
    }
    provider_payload_preflight("Yike", context, &result.payload)?;
    Ok(())
}

fn detail_to_import_result(
    detail: YikeLiveDetail,
    source_id: Option<String>,
    source_url: Option<String>,
    request_url: Option<String>,
) -> ProviderResult<ProviderImportResult> {
    let sgf_text = provider_payload_preflight("Yike", "live detail sgf", &detail.sgf)?.to_string();
    let game_result = first_non_blank([detail.game_result.as_str()]).map(str::to_string);
    let mut metadata = ProviderGameMetadata {
        source_url,
        request_url,
        source_id: source_id.clone(),
        provider_status: Some(detail.status.to_string()),
        ..ProviderGameMetadata::default()
    };
    if let Some(result) = game_result.clone() {
        metadata.extra.insert("provider_result".to_string(), result);
    }

    Ok(ProviderImportResult {
        provider: ProviderKind::Yike,
        sgf_text: without_variations(&sgf_text),
        summary: ProviderGameSummary {
            provider: ProviderKind::Yike,
            source_id,
            result: game_result,
            ..ProviderGameSummary::empty(ProviderKind::Yike)
        },
        metadata,
        warnings: Vec::new(),
    })
}

fn parse_json(response: &str, label: &str) -> ProviderResult<Value> {
    let response = provider_payload_preflight("Yike", label, response)?;
    serde_json::from_str(response)
        .map_err(|err| invalid_payload(format!("failed to parse {label} JSON: {err}")))
}

fn parse_live_detail_value(root: &Value) -> ProviderResult<YikeLiveDetail> {
    let status = object_i64(root, "status")
        .or_else(|| object_i64(root, "Status"))
        .unwrap_or(-1);
    if status != 0 {
        let message = object_string(root, "message")
            .or_else(|| object_string(root, "Message"))
            .unwrap_or_else(|| "Yike live detail request failed".to_string());
        return Err(invalid_payload(format!(
            "Yike provider_error status {status}: {message}"
        )));
    }
    let result = root
        .get("result")
        .or_else(|| root.get("Result"))
        .ok_or_else(|| invalid_payload("Yike live detail response does not contain result"))?;
    Ok(YikeLiveDetail::from_value(result))
}

fn extract_live_detail_value(value: &Value) -> ProviderResult<Option<YikeLiveDetail>> {
    if value.get("result").is_some() && value.get("status").is_some() {
        return parse_live_detail_value(value).map(Some);
    }
    if value.get("sgf").is_some() || value.get("clean_sgf").is_some() {
        return Ok(Some(YikeLiveDetail::from_value(value)));
    }
    Ok(None)
}

impl YikeLiveGame {
    fn from_value(value: &Value) -> Option<Self> {
        let object = value.as_object()?;
        Some(Self {
            id: object.get("Id").and_then(value_u64).unwrap_or(0),
            version: object.get("Version").and_then(value_u64).unwrap_or(1),
            hall: object.get("hall").and_then(value_u64).unwrap_or(0),
            room: object.get("room").and_then(value_u64).unwrap_or(0),
            status: object.get("Status").and_then(value_i64).unwrap_or(0),
            game_name: object.get("GameName").and_then(value_string).unwrap_or_default(),
            black_name: object.get("BlackName").and_then(value_string).unwrap_or_default(),
            white_name: object.get("WhiteName").and_then(value_string).unwrap_or_default(),
            black_county: object
                .get("BlackCounty")
                .and_then(value_string)
                .unwrap_or_default(),
            white_county: object
                .get("WhiteCounty")
                .and_then(value_string)
                .unwrap_or_default(),
            game_date: object.get("GameDate").and_then(value_string).unwrap_or_default(),
            broadcast_time: object
                .get("BroadcastTime")
                .and_then(value_string)
                .unwrap_or_default(),
            finish_order: object
                .get("FinishOrder")
                .and_then(value_string)
                .unwrap_or_default(),
            game_result: object
                .get("GameResult")
                .and_then(value_string)
                .unwrap_or_default(),
            live_member: object
                .get("LiveMember")
                .and_then(value_string)
                .unwrap_or_default(),
            hands_count: object.get("HandsCount").and_then(value_u64).unwrap_or(0),
            person_times: object.get("PersonTimes").and_then(value_u64).unwrap_or(0),
            top_flag: object.get("TopFlag").and_then(value_i64) == Some(1),
            realtime_analysis_flag: object.get("RealtimeAnalysisFlag").and_then(value_i64) == Some(1),
            black_win_rate: object.get("BlackWinRate").and_then(value_f64).unwrap_or(-1.0),
            delta: object.get("Delta").and_then(value_f64).unwrap_or(0.0),
        })
    }
}

impl YikeLiveDetail {
    fn from_value(value: &Value) -> Self {
        let sgf = value
            .get("sgf")
            .and_then(value_string)
            .filter(|value| !value.trim().is_empty())
            .or_else(|| value.get("clean_sgf").and_then(value_string))
            .unwrap_or_default();
        Self {
            sgf,
            status: object_i64(value, "status").unwrap_or(0),
            game_result: object_string(value, "game_result").unwrap_or_default(),
        }
    }
}

fn object_i64(value: &Value, key: &str) -> Option<i64> {
    value.get(key).and_then(value_i64)
}

fn object_string(value: &Value, key: &str) -> Option<String> {
    value.get(key).and_then(value_string)
}

fn value_i64(value: &Value) -> Option<i64> {
    match value {
        Value::Number(value) => value
            .as_i64()
            .or_else(|| value.as_u64().and_then(|value| i64::try_from(value).ok())),
        Value::String(value) => value.trim().parse::<i64>().ok(),
        _ => None,
    }
}

fn value_u64(value: &Value) -> Option<u64> {
    match value {
        Value::Number(value) => value
            .as_u64()
            .or_else(|| value.as_i64().and_then(|value| u64::try_from(value).ok())),
        Value::String(value) => value.trim().parse::<u64>().ok(),
        _ => None,
    }
}

fn value_f64(value: &Value) -> Option<f64> {
    match value {
        Value::Number(value) => value.as_f64(),
        Value::String(value) => value.trim().parse::<f64>().ok(),
        _ => None,
    }
}

fn value_string(value: &Value) -> Option<String> {
    match value {
        Value::String(value) => Some(value.trim().to_string()),
        Value::Number(value) => Some(value.to_string()),
        Value::Bool(value) => Some(value.to_string()),
        _ => None,
    }
}

fn build_url(base_url: &str, params: &[(&str, String)]) -> String {
    let query = params
        .iter()
        .map(|(key, value)| format!("{}={}", form_encode(key), form_encode(value)))
        .collect::<Vec<_>>()
        .join("&");
    format!("{base_url}?{query}")
}

fn form_encode(value: &str) -> String {
    let mut encoded = String::new();
    for byte in value.as_bytes() {
        match *byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'*' => {
                encoded.push(*byte as char);
            }
            b' ' => encoded.push('+'),
            byte => encoded.push_str(&format!("%{byte:02X}")),
        }
    }
    encoded
}

fn format_one_decimal(value: f64) -> String {
    let rounded = (value * 10.0).round() / 10.0;
    if (rounded.fract()).abs() < f64::EPSILON {
        format!("{rounded:.0}")
    } else {
        format!("{rounded:.1}")
    }
}

fn sha1_hex(input: &[u8]) -> String {
    let mut message = input.to_vec();
    let bit_len = (message.len() as u64) * 8;
    message.push(0x80);
    while message.len() % 64 != 56 {
        message.push(0);
    }
    message.extend_from_slice(&bit_len.to_be_bytes());

    let mut h0 = 0x6745_2301u32;
    let mut h1 = 0xefcd_ab89u32;
    let mut h2 = 0x98ba_dcfeu32;
    let mut h3 = 0x1032_5476u32;
    let mut h4 = 0xc3d2_e1f0u32;

    for chunk in message.chunks_exact(64) {
        let mut words = [0u32; 80];
        for (index, word) in words.iter_mut().take(16).enumerate() {
            let offset = index * 4;
            *word = u32::from_be_bytes([
                chunk[offset],
                chunk[offset + 1],
                chunk[offset + 2],
                chunk[offset + 3],
            ]);
        }
        for index in 16..80 {
            words[index] =
                (words[index - 3] ^ words[index - 8] ^ words[index - 14] ^ words[index - 16]).rotate_left(1);
        }

        let mut a = h0;
        let mut b = h1;
        let mut c = h2;
        let mut d = h3;
        let mut e = h4;

        for (index, word) in words.iter().enumerate() {
            let (function, constant) = match index {
                0..=19 => (((b & c) | ((!b) & d)), 0x5a82_7999),
                20..=39 => (b ^ c ^ d, 0x6ed9_eba1),
                40..=59 => (((b & c) | (b & d) | (c & d)), 0x8f1b_bcdc),
                _ => (b ^ c ^ d, 0xca62_c1d6),
            };
            let temp = a
                .rotate_left(5)
                .wrapping_add(function)
                .wrapping_add(e)
                .wrapping_add(constant)
                .wrapping_add(*word);
            e = d;
            d = c;
            c = b.rotate_left(30);
            b = a;
            a = temp;
        }

        h0 = h0.wrapping_add(a);
        h1 = h1.wrapping_add(b);
        h2 = h2.wrapping_add(c);
        h3 = h3.wrapping_add(d);
        h4 = h4.wrapping_add(e);
    }

    hex_lower(
        &[
            h0.to_be_bytes(),
            h1.to_be_bytes(),
            h2.to_be_bytes(),
            h3.to_be_bytes(),
            h4.to_be_bytes(),
        ]
        .concat(),
    )
}

fn md5_hex(input: &[u8]) -> String {
    const SHIFTS: [u32; 64] = [
        7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
        5, 9, 14, 20, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 6, 10, 15, 21, 6, 10, 15,
        21, 6, 10, 15, 21, 6, 10, 15, 21,
    ];
    const CONSTANTS: [u32; 64] = [
        0xd76a_a478,
        0xe8c7_b756,
        0x2420_70db,
        0xc1bd_ceee,
        0xf57c_0faf,
        0x4787_c62a,
        0xa830_4613,
        0xfd46_9501,
        0x6980_98d8,
        0x8b44_f7af,
        0xffff_5bb1,
        0x895c_d7be,
        0x6b90_1122,
        0xfd98_7193,
        0xa679_438e,
        0x49b4_0821,
        0xf61e_2562,
        0xc040_b340,
        0x265e_5a51,
        0xe9b6_c7aa,
        0xd62f_105d,
        0x0244_1453,
        0xd8a1_e681,
        0xe7d3_fbc8,
        0x21e1_cde6,
        0xc337_07d6,
        0xf4d5_0d87,
        0x455a_14ed,
        0xa9e3_e905,
        0xfcef_a3f8,
        0x676f_02d9,
        0x8d2a_4c8a,
        0xfffa_3942,
        0x8771_f681,
        0x6d9d_6122,
        0xfde5_380c,
        0xa4be_ea44,
        0x4bde_cfa9,
        0xf6bb_4b60,
        0xbebf_bc70,
        0x289b_7ec6,
        0xeaa1_27fa,
        0xd4ef_3085,
        0x0488_1d05,
        0xd9d4_d039,
        0xe6db_99e5,
        0x1fa2_7cf8,
        0xc4ac_5665,
        0xf429_2244,
        0x432a_ff97,
        0xab94_23a7,
        0xfc93_a039,
        0x655b_59c3,
        0x8f0c_cc92,
        0xffef_f47d,
        0x8584_5dd1,
        0x6fa8_7e4f,
        0xfe2c_e6e0,
        0xa301_4314,
        0x4e08_11a1,
        0xf753_7e82,
        0xbd3a_f235,
        0x2ad7_d2bb,
        0xeb86_d391,
    ];

    let mut message = input.to_vec();
    let bit_len = (message.len() as u64) * 8;
    message.push(0x80);
    while message.len() % 64 != 56 {
        message.push(0);
    }
    message.extend_from_slice(&bit_len.to_le_bytes());

    let mut a0 = 0x6745_2301u32;
    let mut b0 = 0xefcd_ab89u32;
    let mut c0 = 0x98ba_dcfeu32;
    let mut d0 = 0x1032_5476u32;

    for chunk in message.chunks_exact(64) {
        let mut words = [0u32; 16];
        for (index, word) in words.iter_mut().enumerate() {
            let offset = index * 4;
            *word = u32::from_le_bytes([
                chunk[offset],
                chunk[offset + 1],
                chunk[offset + 2],
                chunk[offset + 3],
            ]);
        }

        let mut a = a0;
        let mut b = b0;
        let mut c = c0;
        let mut d = d0;

        for index in 0..64 {
            let (function, word_index) = match index {
                0..=15 => ((b & c) | ((!b) & d), index),
                16..=31 => ((d & b) | ((!d) & c), (5 * index + 1) % 16),
                32..=47 => (b ^ c ^ d, (3 * index + 5) % 16),
                _ => (c ^ (b | (!d)), (7 * index) % 16),
            };
            let next = b.wrapping_add(
                a.wrapping_add(function)
                    .wrapping_add(CONSTANTS[index])
                    .wrapping_add(words[word_index])
                    .rotate_left(SHIFTS[index]),
            );
            a = d;
            d = c;
            c = b;
            b = next;
        }

        a0 = a0.wrapping_add(a);
        b0 = b0.wrapping_add(b);
        c0 = c0.wrapping_add(c);
        d0 = d0.wrapping_add(d);
    }

    hex_lower(
        &[
            a0.to_le_bytes(),
            b0.to_le_bytes(),
            c0.to_le_bytes(),
            d0.to_le_bytes(),
        ]
        .concat(),
    )
}

fn hex_lower(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

fn parse_game_tree(chars: &[char], start: usize) -> Option<(String, usize)> {
    if chars.get(start) != Some(&'(') {
        return None;
    }

    let mut output = String::from("(");
    let mut in_value = false;
    let mut escaping = false;
    let mut copied_first_child_tree = false;
    let mut index = start + 1;
    while index < chars.len() {
        let current = chars[index];
        if in_value {
            output.push(current);
            if escaping {
                escaping = false;
            } else if current == '\\' {
                escaping = true;
            } else if current == ']' {
                in_value = false;
            }
            index += 1;
            continue;
        }

        if current == '[' {
            in_value = true;
            output.push(current);
            index += 1;
            continue;
        }

        if current == '(' {
            let (child, next_index) = parse_game_tree(chars, index)?;
            if !copied_first_child_tree {
                output.push_str(child.strip_prefix('(')?.strip_suffix(')')?);
                copied_first_child_tree = true;
            }
            index = next_index;
            continue;
        }

        if current == ')' {
            output.push(current);
            return Some((output, index + 1));
        }

        output.push(current);
        index += 1;
    }

    None
}

fn parse_u64_or(value: &str, fallback: u64) -> u64 {
    value.parse::<u64>().unwrap_or(fallback)
}

fn parse_i64_or(value: &str, fallback: i64) -> i64 {
    value.parse::<i64>().unwrap_or(fallback)
}

fn new_live_full() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(?s)^https?://.*?([^./]+\.[^./]+)/.*?(live/new-room/)([^/]+)/[0-9]+/([^/\s]+).*$")
            .expect("valid Yike regex")
    })
}

fn new_live_short() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(?s)^https?://.*?([^./]+\.[^./]+)/.*?(live/new-room/)([^/\s]+)$")
            .expect("valid Yike regex")
    })
}

fn old_live_full() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(?s)^https?://.*?([^./]+\.[^./]+)/.*?(live/room/)([^/]+)/[0-9]+/([^/\s]+).*$")
            .expect("valid Yike regex")
    })
}

fn old_live_short() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(?s)^https?://.*?([^./]+\.[^./]+)/.*?(live/room/)([^/\s]+)$").expect("valid Yike regex")
    })
}

fn game_room() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(?s)^https?://.*?([^./]+\.[^./]+)/.*?(game/[a-zA-Z]+/)[0-9]+/([^/\s]+).*$")
            .expect("valid Yike regex")
    })
}

fn hall_room() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(?s)^https?://.*?([^./]+\.[^./]+)/.*?(room=)([0-9]+)(&hall).*$")
            .expect("valid Yike regex")
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use app_model::ProviderErrorKind;
    use provider_core::{timeout, RecordingProviderTransport, StaticProviderTransport};
    use std::collections::BTreeMap;

    #[test]
    fn builds_legacy_signed_headers_deterministically() {
        let headers = signed_headers(1_700_000_000_123, 12_345_678);

        assert_eq!(headers.get("AppKey").map(String::as_str), Some(APP_KEY));
        assert_eq!(headers.get("CurTime").map(String::as_str), Some("1700000000123"));
        assert_eq!(headers.get("Nonce").map(String::as_str), Some("12345678"));
        assert_eq!(
            headers.get("CheckSum").map(String::as_str),
            Some("52501c4e5494abcf371d6ea8ec68198ea5cabeeb")
        );
        assert_eq!(
            headers.get("accesstoken").map(String::as_str),
            Some("fe7f02285cbe1c0b6501b77c37afaa3e")
        );
        assert_eq!(headers.get("Platform").map(String::as_str), Some("web"));
        assert_eq!(
            headers.get("Content-Type").map(String::as_str),
            Some("application/json")
        );
    }

    #[test]
    fn constructs_legacy_list_and_detail_urls() {
        assert_eq!(
            live_list_url(Some("official live"), -3, -1),
            "https://api.yikeweiqi.com/v2/golive/list?p=1&since=0&official=official+live&version=2"
        );
        assert_eq!(
            live_detail_url("room id/1"),
            "https://api-new.yikeweiqi.com/v1/golives/room+id%2F1"
        );
    }

    #[test]
    fn parses_live_list_json() {
        let page = parse_live_list_json(
            r#"{
                "Status": 1200,
                "Result": {
                    "since": 42,
                    "list": [{
                        "Id": 186031,
                        "Version": 2,
                        "hall": 7,
                        "room": 9,
                        "Status": 3,
                        "GameName": "Title",
                        "BlackName": "Black",
                        "WhiteName": "White",
                        "BlackCounty": "CN",
                        "WhiteCounty": "JP",
                        "GameDate": "2026-04-30",
                        "BroadcastTime": "20:00",
                        "FinishOrder": "",
                        "GameResult": "B+R",
                        "LiveMember": "caster",
                        "HandsCount": 123,
                        "PersonTimes": 4567,
                        "TopFlag": 1,
                        "RealtimeAnalysisFlag": 1,
                        "BlackWinRate": 64.25,
                        "Delta": 1.04
                    }]
                }
            }"#,
        )
        .unwrap();

        assert_eq!(page.since, 42);
        assert_eq!(page.games.len(), 1);
        let game = &page.games[0];
        assert_eq!(game.id, 186_031);
        assert_eq!(game.status_text(), "B+R");
        assert_eq!(game.time_text(), "2026-04-30 20:00");
        assert_eq!(game.player_text(true), "Black [CN]");
        assert_eq!(game.winrate_text(), "黑 64.3% / 白 35.8% / 1目");
        assert_eq!(
            game.to_room_url(),
            "https://home.yikeweiqi.com/#/live/new-room/186031/7/9"
        );
    }

    #[test]
    fn parses_live_detail_json_and_imports_metadata() {
        let response = r#"{
            "status": 0,
            "result": {
                "sgf": "",
                "clean_sgf": "(;GM[1]SZ[19];B[aa](;W[bb])(;W[cc]))",
                "status": 3,
                "game_result": "W+2.5"
            }
        }"#;

        let detail = parse_live_detail_json(response).unwrap();
        assert_eq!(detail.status, 3);
        assert_eq!(detail.game_result, "W+2.5");

        let result = import_live_detail_json(
            response,
            Some("186031".to_string()),
            Some("https://home.yikeweiqi.com/#/live/new-room/186031/0/0".to_string()),
            Some("https://api-new.yikeweiqi.com/v1/golives/186031".to_string()),
        )
        .unwrap();

        assert_eq!(result.sgf_text, "(;GM[1]SZ[19];B[aa];W[bb])");
        assert_eq!(result.summary.source_id.as_deref(), Some("186031"));
        assert_eq!(result.summary.result.as_deref(), Some("W+2.5"));
        assert_eq!(result.metadata.provider_status.as_deref(), Some("3"));
        assert_eq!(
            result.metadata.extra.get("provider_result").map(String::as_str),
            Some("W+2.5")
        );
    }

    #[test]
    fn provider_fixtures_cover_yike_success_and_empty_list_shapes() {
        let page = parse_live_list_json(include_str!(
            "../../../tests/fixtures/provider/yike/live_list_success.json"
        ))
        .unwrap();

        assert_eq!(page.since, 99);
        assert_eq!(page.games.len(), 1);
        assert_eq!(page.games[0].id, 186_031);
        assert_eq!(page.games[0].status_text(), "B+R");

        let detail = import_live_detail_json(
            include_str!("../../../tests/fixtures/provider/yike/live_detail_success.json"),
            Some("fixture-detail".to_string()),
            None,
            None,
        )
        .unwrap();
        assert_eq!(detail.summary.source_id.as_deref(), Some("fixture-detail"));
        assert_eq!(detail.summary.result.as_deref(), Some("W+R"));
        assert_eq!(
            detail.sgf_text,
            "(;GM[1]SZ[19]PB[Black Fixture]PW[White Fixture]RE[W+R];B[dd];W[pq])"
        );

        let empty = parse_live_list_json(include_str!(
            "../../../tests/fixtures/provider/yike/empty_result.json"
        ))
        .unwrap();
        assert_eq!(empty.since, 100);
        assert!(empty.games.is_empty());
    }

    #[test]
    fn provider_fixtures_reject_yike_session_rate_limit_antibot_schema_and_malformed() {
        let unauthorized = parse_live_list_json(include_str!(
            "../../../tests/fixtures/provider/yike/unauthorized.json"
        ))
        .unwrap_err();
        assert_eq!(unauthorized.kind, ProviderErrorKind::InvalidPayload);
        assert!(unauthorized.message.contains("session expired"));

        let rate_limit = parse_live_list_json(include_str!(
            "../../../tests/fixtures/provider/yike/rate_limit.json"
        ))
        .unwrap_err();
        assert_eq!(rate_limit.kind, ProviderErrorKind::InvalidPayload);
        assert!(rate_limit.message.contains("too many requests"));

        let html = parse_live_list_json(include_str!(
            "../../../tests/fixtures/provider/yike/anti_bot.html"
        ))
        .unwrap_err();
        assert_eq!(html.kind, ProviderErrorKind::InvalidPayload);
        assert!(html.message.contains("anti_bot_html_challenge"));

        let schema = parse_live_list_json(include_str!(
            "../../../tests/fixtures/provider/yike/schema_drift.json"
        ))
        .unwrap_err();
        assert_eq!(schema.kind, ProviderErrorKind::InvalidPayload);
        assert!(schema.message.contains("schema drift"));

        let malformed = parse_live_list_json(include_str!(
            "../../../tests/fixtures/provider/yike/malformed.json"
        ))
        .unwrap_err();
        assert_eq!(malformed.kind, ProviderErrorKind::InvalidPayload);
        assert!(malformed.message.contains("failed to parse Yike live list JSON"));
    }

    #[test]
    fn yike_http_status_failures_are_typed_without_empty_success() {
        let signature = YikeRequestSignature {
            current_time_millis: 1,
            nonce: 2,
        };
        let unauthorized = StaticProviderTransport::ok(fetch_result(
            401,
            include_str!("../../../tests/fixtures/provider/yike/unauthorized.json"),
        ));
        let error = fetch_live_detail_import_with_signature(&unauthorized, "186031", signature).unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::TransportFailed);
        assert!(error.message.contains("unauthorized_or_session_expired"));

        let rate_limited = StaticProviderTransport::ok(fetch_result(
            429,
            include_str!("../../../tests/fixtures/provider/yike/rate_limit.json"),
        ));
        let error = fetch_live_detail_import_with_signature(&rate_limited, "186031", signature).unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::TransportFailed);
        assert!(error.message.contains("rate_limited"));
    }

    #[test]
    fn import_payload_preserves_detail_result_metadata() {
        let request = ProviderImportRequest {
            provider: ProviderKind::Yike,
            payload: r#"{
                "status": 0,
                "result": {
                    "clean_sgf": "(;GM[1]SZ[19];B[aa])",
                    "status": 2,
                    "game_result": "B+R"
                }
            }"#
            .to_string(),
            source_url: None,
            source_id: Some("live-1".to_string()),
            metadata: ProviderGameMetadata::default(),
        };

        let result = import_payload(request).unwrap();

        assert_eq!(result.sgf_text, "(;GM[1]SZ[19];B[aa])");
        assert_eq!(result.summary.result.as_deref(), Some("B+R"));
        assert_eq!(result.metadata.provider_status.as_deref(), Some("2"));
    }

    #[test]
    fn fetch_live_detail_uses_transport_without_real_network() {
        let transport = RecordingProviderTransport::with_result(Ok(fetch_result(
            200,
            r#"{
                "status": 0,
                "result": {
                    "sgf": "(;GM[1]SZ[19];B[aa])",
                    "status": 2,
                    "game_result": ""
                }
            }"#,
        )));

        let result = fetch_live_detail_import_with_signature(
            &transport,
            "186031",
            YikeRequestSignature {
                current_time_millis: 1_700_000_000_123,
                nonce: 12_345_678,
            },
        )
        .unwrap();

        assert_eq!(result.summary.source_id.as_deref(), Some("186031"));
        let requests = transport.requests().unwrap();
        assert_eq!(requests.len(), 1);
        assert_eq!(requests[0].url, "https://api-new.yikeweiqi.com/v1/golives/186031");
        assert_eq!(requests[0].method, ProviderFetchMethod::Get);
        assert_eq!(requests[0].timeout_ms, Some(HTTP_TIMEOUT_MS));
        assert_eq!(
            requests[0].headers.get("CheckSum").map(String::as_str),
            Some("52501c4e5494abcf371d6ea8ec68198ea5cabeeb")
        );
    }

    #[test]
    fn maps_transport_http_and_payload_failures_to_structured_errors() {
        let transport = StaticProviderTransport::ok(fetch_result(502, "bad gateway"));
        let error = fetch_live_detail_import_with_signature(
            &transport,
            "186031",
            YikeRequestSignature {
                current_time_millis: 1,
                nonce: 2,
            },
        )
        .unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::TransportFailed);
        assert!(error.message.contains("HTTP 502"));

        let transport = StaticProviderTransport::ok(fetch_result(200, "{"));
        let error = fetch_live_detail_import_with_signature(
            &transport,
            "186031",
            YikeRequestSignature {
                current_time_millis: 1,
                nonce: 2,
            },
        )
        .unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::InvalidPayload);

        let transport = StaticProviderTransport::err(timeout("request timed out"));
        let error = fetch_live_detail_import_with_signature(
            &transport,
            "186031",
            YikeRequestSignature {
                current_time_millis: 1,
                nonce: 2,
            },
        )
        .unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::Timeout);
    }

    #[test]
    fn parses_old_live_room_url() {
        let info = parse_yike_url("https://home.yikeweiqi.com/#/live/room/18328/1/15630642").unwrap();

        assert_eq!(info.room_kind, YikeRoomKind::OldLiveRoom);
        assert_eq!(info.id, "18328");
        assert_eq!(info.room_id, 15_630_642);
        assert_eq!(
            info.request_url,
            "https://api.yikeweiqi.com/golive/dtl?id=18328&flag=1"
        );
    }

    #[test]
    fn parses_old_live_board_url_with_zero_room_suffix() {
        let info = parse_yike_url("https://home.yikeweiqi.com/#/live/room/4903/0/0").unwrap();

        assert_eq!(info.room_kind, YikeRoomKind::OldLiveBoard);
        assert_eq!(info.id, "4903");
        assert_eq!(info.request_url, "https://api.yikeweiqi.com/golive/dtl?id=4903");
    }

    #[test]
    fn parses_new_live_room_url() {
        let info = parse_yike_url("https://home.yikeweiqi.com/#/live/new-room/186031/0/0").unwrap();

        assert_eq!(info.room_kind, YikeRoomKind::NewLiveRoom);
        assert_eq!(info.id, "186031");
        assert_eq!(
            info.request_url,
            "https://api-new.yikeweiqi.com/v1/golives/186031"
        );
    }

    #[test]
    fn parses_yike_game_room_url() {
        let info = parse_yike_url("https://home.yikeweiqi.com/#/game/play/1/15630642").unwrap();

        assert_eq!(info.room_kind, YikeRoomKind::GameRoom);
        assert_eq!(info.room_id, 15_630_642);
        assert_eq!(
            info.request_url,
            "https://api.yikeweiqi.com/golive/dtl?id=15630642"
        );
    }

    #[test]
    fn parses_hall_room_url() {
        let info = parse_yike_url("https://home.yikeweiqi.com/#/?room=15630642&hall=true").unwrap();

        assert_eq!(info.room_kind, YikeRoomKind::GameRoom);
        assert_eq!(info.room_id, 15_630_642);
    }

    #[test]
    fn rejects_invalid_url() {
        let error = parse_yike_url("https://example.com/nope").unwrap_err();

        assert_eq!(error.kind, ProviderErrorKind::InvalidUrl);
    }

    #[test]
    fn keeps_first_variation_as_mainline_and_drops_siblings() {
        let sgf = "(;GM[1]SZ[19];B[aa](;W[bb];B[cc])(;W[dd];B[ee]);W[ff])";

        assert_eq!(without_variations(sgf), "(;GM[1]SZ[19];B[aa];W[bb];B[cc];W[ff])");
    }

    #[test]
    fn imports_json_payload_without_network() {
        let request = ProviderImportRequest {
            provider: ProviderKind::Yike,
            payload: serde_json::json!({"sgf":"(;GM[1]SZ[19];B[aa](;W[bb])(;W[cc]))"}).to_string(),
            source_url: None,
            source_id: Some("186031".to_string()),
            metadata: ProviderGameMetadata::default(),
        };

        let result = import_payload(request).unwrap();

        assert_eq!(result.provider, ProviderKind::Yike);
        assert_eq!(result.summary.source_id.as_deref(), Some("186031"));
        assert_eq!(result.sgf_text, "(;GM[1]SZ[19];B[aa];W[bb])");
    }

    fn fetch_result(status_code: u16, payload: &str) -> ProviderFetchResult {
        ProviderFetchResult {
            provider: ProviderKind::Yike,
            url: "https://api-new.yikeweiqi.com/v1/golives/186031".to_string(),
            status_code,
            payload: payload.to_string(),
            headers: BTreeMap::new(),
            content_type: Some("application/json".to_string()),
            metadata: ProviderGameMetadata::default(),
            warnings: Vec::new(),
        }
    }
}
