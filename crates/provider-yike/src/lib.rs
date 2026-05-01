use app_model::{
    ProviderGameMetadata, ProviderGameSummary, ProviderImportRequest, ProviderImportResult, ProviderKind,
};
use provider_core::{invalid_payload, invalid_url, require_non_blank, ProviderResult};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::OnceLock;

const DETAIL_URL_PREFIX: &str = "https://api-new.yikeweiqi.com/v1/golives/";

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
            request_url: detail_url(&id),
            id,
        });
    }

    if let Some(captures) = new_live_short().captures(&url) {
        let id = captures[3].to_string();
        return Ok(YikeUrlDescriptor {
            provider: ProviderKind::Yike,
            room_kind: YikeRoomKind::NewLiveRoom,
            room_id: parse_u64_or(&id, 0),
            request_url: detail_url(&id),
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
    Ok(ProviderImportResult {
        provider: ProviderKind::Yike,
        sgf_text: without_variations(&sgf_text),
        summary: ProviderGameSummary {
            provider: ProviderKind::Yike,
            source_id,
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

    let json: Value = serde_json::from_str(payload)
        .map_err(|err| invalid_payload(format!("failed to parse Yike payload JSON: {err}")))?;
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

fn detail_url(id: &str) -> String {
    format!("{DETAIL_URL_PREFIX}{id}")
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
}
