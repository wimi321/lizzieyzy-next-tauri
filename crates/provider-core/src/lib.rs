use app_model::{ProviderError, ProviderErrorKind};

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

#[cfg(test)]
mod tests {
    use super::*;

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
}
