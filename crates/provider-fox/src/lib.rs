use app_model::{
    ProviderGameMetadata, ProviderGameSummary, ProviderImportRequest, ProviderImportResult, ProviderKind,
};
use provider_core::{first_non_blank, invalid_payload, require_non_blank, ProviderResult};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

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
    let payload = require_non_blank(payload, "payload")?;
    if payload.trim_start().starts_with('(') {
        let sgf_text = normalize_sgf(payload);
        let metadata = metadata_from_sgf(&sgf_text);
        return Ok(FoxNormalizedPayload { sgf_text, metadata });
    }

    let json: Value = serde_json::from_str(payload)
        .map_err(|err| invalid_payload(format!("failed to parse Fox payload JSON: {err}")))?;
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

fn merge_metadata(target: &mut ProviderGameMetadata, source: ProviderGameMetadata) {
    target.source_url = target.source_url.take().or(source.source_url);
    target.request_url = target.request_url.take().or(source.request_url);
    target.source_id = target.source_id.take().or(source.source_id);
    target.room_id = target.room_id.take().or(source.room_id);
    target.title = target.title.take().or(source.title);
    target.provider_status = target.provider_status.take().or(source.provider_status);
    target.extra.extend(source.extra);
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
}
