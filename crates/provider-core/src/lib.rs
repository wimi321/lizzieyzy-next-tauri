use app_model::{ProviderError, ProviderErrorKind, ProviderFetchRequest, ProviderFetchResult};
use std::sync::{Arc, Mutex};

pub type ProviderResult<T> = Result<T, ProviderError>;

pub fn provider_error(kind: ProviderErrorKind, message: impl Into<String>) -> ProviderError {
    ProviderError {
        kind,
        message: message.into(),
    }
}

pub fn invalid_request(message: impl Into<String>) -> ProviderError {
    provider_error(ProviderErrorKind::InvalidRequest, message)
}

pub fn invalid_url(message: impl Into<String>) -> ProviderError {
    provider_error(ProviderErrorKind::InvalidUrl, message)
}

pub fn invalid_payload(message: impl Into<String>) -> ProviderError {
    provider_error(ProviderErrorKind::InvalidPayload, message)
}

pub fn parse_failed(message: impl Into<String>) -> ProviderError {
    provider_error(ProviderErrorKind::ParseFailed, message)
}

pub fn unsupported_provider(message: impl Into<String>) -> ProviderError {
    provider_error(ProviderErrorKind::UnsupportedProvider, message)
}

pub fn transport_failed(message: impl Into<String>) -> ProviderError {
    provider_error(ProviderErrorKind::TransportFailed, message)
}

pub fn timeout(message: impl Into<String>) -> ProviderError {
    provider_error(ProviderErrorKind::Timeout, message)
}

pub fn runtime_unavailable(message: impl Into<String>) -> ProviderError {
    provider_error(ProviderErrorKind::RuntimeUnavailable, message)
}

pub fn not_implemented(message: impl Into<String>) -> ProviderError {
    provider_error(ProviderErrorKind::NotImplemented, message)
}

pub fn require_non_blank<'a>(value: &'a str, field_name: &str) -> ProviderResult<&'a str> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return Err(invalid_request(format!("{field_name} must not be empty")));
    }
    Ok(trimmed)
}

pub fn first_non_blank<'a>(values: impl IntoIterator<Item = &'a str>) -> Option<&'a str> {
    values.into_iter().map(str::trim).find(|value| !value.is_empty())
}

pub fn provider_http_error(provider: &str, status_code: u16, payload: &str, context: &str) -> ProviderError {
    let class = match status_code {
        401 => "unauthorized_or_session_expired",
        403 => "session_expired_or_forbidden",
        429 => "rate_limited",
        _ => "http_error",
    };
    let message = compact_payload_excerpt(payload);
    transport_failed(format!(
        "{provider} {context}: {class}; HTTP {status_code}; payload={message}"
    ))
}

pub fn provider_payload_preflight<'a>(
    provider: &str,
    label: &str,
    payload: &'a str,
) -> ProviderResult<&'a str> {
    let payload = payload.trim();
    if payload.is_empty() {
        return Err(invalid_payload(format!("{provider} {label} payload is empty")));
    }
    if looks_like_html_challenge(payload) {
        return Err(invalid_payload(format!(
            "{provider} {label} returned anti_bot_html_challenge; not treating it as an empty result"
        )));
    }
    Ok(payload)
}

pub fn compact_payload_excerpt(payload: &str) -> String {
    let mut text = payload.split_whitespace().collect::<Vec<_>>().join(" ");
    if text.is_empty() {
        text = "<empty>".to_string();
    }
    if text.len() > 160 {
        text.truncate(157);
        text.push_str("...");
    }
    text
}

fn looks_like_html_challenge(payload: &str) -> bool {
    let lower = payload
        .chars()
        .take(4096)
        .collect::<String>()
        .to_ascii_lowercase();
    lower.starts_with("<!doctype html")
        || lower.starts_with("<html")
        || (lower.contains("<html") && lower.contains("</html"))
        || lower.contains("captcha")
        || lower.contains("cloudflare")
        || lower.contains("anti-bot")
        || lower.contains("security challenge")
        || lower.contains("verify you are human")
}

pub trait ProviderTransport {
    fn fetch(&self, request: &ProviderFetchRequest) -> ProviderResult<ProviderFetchResult>;
}

#[derive(Debug, Clone)]
pub struct NoopProviderTransport {
    message: String,
}

impl NoopProviderTransport {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl Default for NoopProviderTransport {
    fn default() -> Self {
        Self::new("provider transport runtime is not configured")
    }
}

impl ProviderTransport for NoopProviderTransport {
    fn fetch(&self, _request: &ProviderFetchRequest) -> ProviderResult<ProviderFetchResult> {
        Err(runtime_unavailable(self.message.clone()))
    }
}

#[derive(Debug, Clone)]
pub struct StaticProviderTransport {
    result: ProviderResult<ProviderFetchResult>,
}

impl StaticProviderTransport {
    pub fn ok(result: ProviderFetchResult) -> Self {
        Self { result: Ok(result) }
    }

    pub fn err(error: ProviderError) -> Self {
        Self { result: Err(error) }
    }
}

impl ProviderTransport for StaticProviderTransport {
    fn fetch(&self, _request: &ProviderFetchRequest) -> ProviderResult<ProviderFetchResult> {
        self.result.clone()
    }
}

#[derive(Debug, Clone, Default)]
pub struct RecordingProviderTransport {
    requests: Arc<Mutex<Vec<ProviderFetchRequest>>>,
    result: Arc<Mutex<Option<ProviderResult<ProviderFetchResult>>>>,
}

impl RecordingProviderTransport {
    pub fn with_result(result: ProviderResult<ProviderFetchResult>) -> Self {
        Self {
            requests: Arc::default(),
            result: Arc::new(Mutex::new(Some(result))),
        }
    }

    pub fn requests(&self) -> ProviderResult<Vec<ProviderFetchRequest>> {
        self.requests
            .lock()
            .map(|requests| requests.clone())
            .map_err(|_| runtime_unavailable("provider transport request log is unavailable"))
    }
}

impl ProviderTransport for RecordingProviderTransport {
    fn fetch(&self, request: &ProviderFetchRequest) -> ProviderResult<ProviderFetchResult> {
        self.requests
            .lock()
            .map_err(|_| runtime_unavailable("provider transport request log is unavailable"))?
            .push(request.clone());
        self.result
            .lock()
            .map_err(|_| runtime_unavailable("provider transport result is unavailable"))?
            .clone()
            .unwrap_or_else(|| Err(runtime_unavailable("provider transport result is not configured")))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use app_model::{ProviderFetchMethod, ProviderGameMetadata, ProviderKind};
    use std::collections::BTreeMap;

    #[test]
    fn require_non_blank_trims_valid_input() {
        assert_eq!(require_non_blank("  abc  ", "value").unwrap(), "abc");
    }

    #[test]
    fn require_non_blank_reports_invalid_request() {
        let error = require_non_blank(" ", "payload").unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::InvalidRequest);
        assert_eq!(error.message, "payload must not be empty");
    }

    #[test]
    fn provider_payload_preflight_rejects_empty_and_html_challenges() {
        let empty = provider_payload_preflight("Yike", "live list", "  ").unwrap_err();
        assert_eq!(empty.kind, ProviderErrorKind::InvalidPayload);
        assert!(empty.message.contains("payload is empty"));

        let challenge = provider_payload_preflight(
            "Fox",
            "payload",
            "<html><title>Security Challenge</title><body>captcha</body></html>",
        )
        .unwrap_err();
        assert_eq!(challenge.kind, ProviderErrorKind::InvalidPayload);
        assert!(challenge.message.contains("anti_bot_html_challenge"));

        assert_eq!(
            provider_payload_preflight("Fox", "payload", r#"{"result":0}"#).unwrap(),
            r#"{"result":0}"#
        );
    }

    #[test]
    fn provider_http_error_has_typed_session_and_rate_limit_messages() {
        let unauthorized = provider_http_error("Yike", 401, r#"{"message":"expired"}"#, "detail");
        assert_eq!(unauthorized.kind, ProviderErrorKind::TransportFailed);
        assert!(unauthorized.message.contains("unauthorized_or_session_expired"));
        assert!(unauthorized.message.contains("HTTP 401"));

        let rate_limited = provider_http_error("Fox", 429, "too many requests", "list");
        assert_eq!(rate_limited.kind, ProviderErrorKind::TransportFailed);
        assert!(rate_limited.message.contains("rate_limited"));
        assert!(rate_limited.message.contains("too many requests"));
    }

    #[test]
    fn noop_transport_reports_runtime_unavailable_without_network() {
        let transport = NoopProviderTransport::default();
        let error = transport.fetch(&fetch_request()).unwrap_err();

        assert_eq!(error.kind, ProviderErrorKind::RuntimeUnavailable);
        assert_eq!(error.message, "provider transport runtime is not configured");
    }

    #[test]
    fn static_transport_returns_injected_result() {
        let result = ProviderFetchResult {
            provider: ProviderKind::Yike,
            url: "https://example.test/game".to_string(),
            status_code: 200,
            payload: "(;GM[1])".to_string(),
            headers: BTreeMap::new(),
            content_type: Some("application/json".to_string()),
            metadata: ProviderGameMetadata::default(),
            warnings: Vec::new(),
        };
        let transport = StaticProviderTransport::ok(result.clone());

        assert_eq!(transport.fetch(&fetch_request()).unwrap(), result);
    }

    #[test]
    fn recording_transport_captures_requests_for_offline_tests() {
        let result = ProviderFetchResult {
            provider: ProviderKind::Fox,
            url: "https://example.test/fox".to_string(),
            status_code: 200,
            payload: "{}".to_string(),
            headers: BTreeMap::new(),
            content_type: None,
            metadata: ProviderGameMetadata::default(),
            warnings: Vec::new(),
        };
        let transport = RecordingProviderTransport::with_result(Ok(result));
        let request = fetch_request();

        transport.fetch(&request).unwrap();

        assert_eq!(transport.requests().unwrap(), vec![request]);
    }

    fn fetch_request() -> ProviderFetchRequest {
        ProviderFetchRequest {
            provider: ProviderKind::Yike,
            url: "https://example.test/game".to_string(),
            method: ProviderFetchMethod::Get,
            headers: BTreeMap::new(),
            body: None,
            source_url: None,
            source_id: None,
            timeout_ms: Some(100),
        }
    }
}
