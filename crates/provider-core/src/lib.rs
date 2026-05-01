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
