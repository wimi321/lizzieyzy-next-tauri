use app_model::{
    MoveDto, MoveVertex, PlayerColor, PointDto, PositionDto, ReadboardSidecarProbeRequest,
    ReadboardSidecarProbeResult, ReadboardSidecarSyncSnapshotRequest, ReadboardSidecarSyncSnapshotResult,
    StoneDto,
};
use go_core::{
    decide_readboard_sync, Color, ReadBoardLocalContext, ReadBoardProvider, ReadBoardProviderKind,
    ReadBoardSnapshot, ReadBoardSyncDecision, ReadBoardSyncError, ReadBoardSyncInput,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    net::{TcpStream, ToSocketAddrs},
    path::{Path, PathBuf},
    time::Duration,
};
use thiserror::Error;

pub const READBOARD_JAR_NAME: &str = "readboard-1.6.2-shaded.jar";
pub const DEFAULT_PIPE_NAME: &str = "lizzieyzy-readboard";
pub const DEFAULT_SOCKET_HOST: &str = "127.0.0.1";
pub const DEFAULT_SOCKET_PORT: u16 = 39081;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ReadboardSidecarOptions {
    pub search_roots: Vec<PathBuf>,
    pub java_program: PathBuf,
}

impl Default for ReadboardSidecarOptions {
    fn default() -> Self {
        Self {
            search_roots: default_search_roots(),
            java_program: PathBuf::from("java"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReadboardCandidateKind {
    NativeExe,
    NativeBat,
    JavaJar,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadboardCandidateStatus {
    pub kind: ReadboardCandidateKind,
    pub path: PathBuf,
    pub exists: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReadboardLaunchTarget {
    Native {
        path: PathBuf,
    },
    JavaJar {
        jar_path: PathBuf,
        java_program: PathBuf,
    },
}

impl ReadboardLaunchTarget {
    pub fn path(&self) -> &Path {
        match self {
            Self::Native { path } => path,
            Self::JavaJar { jar_path, .. } => jar_path,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadboardLaunchSpec {
    pub native_candidates: Vec<ReadboardCandidateStatus>,
    pub java_candidates: Vec<ReadboardCandidateStatus>,
    pub selected: Option<ReadboardLaunchTarget>,
    pub warnings: Vec<ReadboardSidecarWarning>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReadboardWarningCode {
    EndpointOnly,
    EndpointUnavailable,
    UnsupportedEndpoint,
    MissingNative,
    MissingJava,
    RuntimeUnavailable,
    UnsupportedProvider,
    IgnoredToken,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadboardSidecarWarning {
    pub code: ReadboardWarningCode,
    pub message: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub path: Option<PathBuf>,
}

impl ReadboardSidecarWarning {
    fn new(code: ReadboardWarningCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            path: None,
        }
    }

    pub fn as_dto_string(&self) -> String {
        match &self.path {
            Some(path) => format!("{:?}: {} ({})", self.code, self.message, path.display()),
            None => format!("{:?}: {}", self.code, self.message),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadboardProbeReport {
    pub available: bool,
    pub endpoint: Option<String>,
    pub version: Option<String>,
    pub launch_spec: ReadboardLaunchSpec,
    pub warnings: Vec<ReadboardSidecarWarning>,
}

impl ReadboardProbeReport {
    pub fn into_dto(self) -> ReadboardSidecarProbeResult {
        ReadboardSidecarProbeResult {
            available: self.available,
            endpoint: self.endpoint,
            version: self.version,
            warnings: self
                .warnings
                .into_iter()
                .map(|warning| warning.as_dto_string())
                .collect(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReadboardTransport {
    Pipe { name: String },
    Socket { host: String, port: u16 },
}

impl Default for ReadboardTransport {
    fn default() -> Self {
        Self::Socket {
            host: DEFAULT_SOCKET_HOST.to_string(),
            port: DEFAULT_SOCKET_PORT,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadboardCommandSpec {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub env: BTreeMap<String, String>,
    pub working_dir: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ParsedReadboardLine {
    pub snapshot_id: Option<String>,
    pub snapshot: ReadBoardSnapshot,
    pub warnings: Vec<ReadboardSidecarWarning>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadboardSyncOutcome {
    pub snapshot_id: String,
    pub snapshot: ReadBoardSnapshot,
    pub decision: ReadBoardSyncDecision,
    pub position: PositionDto,
    pub warnings: Vec<ReadboardSidecarWarning>,
}

impl ReadboardSyncOutcome {
    pub fn into_dto(self) -> ReadboardSidecarSyncSnapshotResult {
        ReadboardSidecarSyncSnapshotResult {
            snapshot_id: self.snapshot_id,
            position: Some(self.position),
            warnings: self
                .warnings
                .into_iter()
                .map(|warning| warning.as_dto_string())
                .collect(),
        }
    }
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ReadboardSidecarError {
    #[error("readboard launch target is unavailable")]
    MissingLaunchTarget,
    #[error("failed to read controlled readboard image `{path}`: {message}")]
    ImageRead { path: String, message: String },
    #[error("failed to decode controlled readboard image base64: {0}")]
    ImageBase64(String),
    #[error("failed to decode controlled readboard image bytes: {0}")]
    ImageDecode(String),
    #[error("controlled readboard image confidence is too low: {0}")]
    ImageLowConfidence(String),
    #[error("readboard protocol line is empty")]
    EmptyProtocolLine,
    #[error("readboard protocol field `{0}` is missing")]
    MissingField(&'static str),
    #[error("readboard protocol field `{field}` has invalid value `{value}`")]
    InvalidField { field: &'static str, value: String },
    #[error("readboard protocol field `{field}` is duplicated")]
    DuplicateField { field: String },
    #[error("readboard sync failed: {0}")]
    Sync(#[from] ReadBoardSyncError),
}

pub fn resolve_launch_spec(options: &ReadboardSidecarOptions) -> ReadboardLaunchSpec {
    let native_candidates = native_candidate_paths(&options.search_roots)
        .into_iter()
        .map(|(kind, path)| ReadboardCandidateStatus {
            kind,
            exists: executable_or_file_exists(&path),
            path,
        })
        .collect::<Vec<_>>();
    let java_candidates = java_candidate_paths(&options.search_roots)
        .into_iter()
        .map(|path| ReadboardCandidateStatus {
            kind: ReadboardCandidateKind::JavaJar,
            exists: path.is_file(),
            path,
        })
        .collect::<Vec<_>>();

    let selected = native_candidates
        .iter()
        .find(|candidate| candidate.exists)
        .map(|candidate| ReadboardLaunchTarget::Native {
            path: candidate.path.clone(),
        })
        .or_else(|| {
            java_candidates
                .iter()
                .find(|candidate| candidate.exists)
                .map(|candidate| ReadboardLaunchTarget::JavaJar {
                    jar_path: candidate.path.clone(),
                    java_program: options.java_program.clone(),
                })
        });

    let mut warnings = Vec::new();
    if native_candidates.iter().all(|candidate| !candidate.exists) {
        warnings.push(ReadboardSidecarWarning::new(
            ReadboardWarningCode::MissingNative,
            "no native readboard.exe/readboard.bat candidate was found",
        ));
    }
    if java_candidates.iter().all(|candidate| !candidate.exists) {
        warnings.push(ReadboardSidecarWarning::new(
            ReadboardWarningCode::MissingJava,
            format!("no Java fallback {READBOARD_JAR_NAME} candidate was found"),
        ));
    }
    if selected.is_none() {
        warnings.push(ReadboardSidecarWarning::new(
            ReadboardWarningCode::RuntimeUnavailable,
            "readboard sidecar runtime is unavailable from configured search roots",
        ));
    }

    ReadboardLaunchSpec {
        native_candidates,
        java_candidates,
        selected,
        warnings,
    }
}

pub fn probe_readboard_sidecar(
    request: &ReadboardSidecarProbeRequest,
    options: &ReadboardSidecarOptions,
) -> ReadboardProbeReport {
    let launch_spec = resolve_launch_spec(options);
    let mut warnings = launch_spec.warnings.clone();
    let endpoint = request
        .endpoint
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty());
    let endpoint_available = endpoint
        .map(|endpoint| probe_endpoint(endpoint, request.timeout_ms, &mut warnings))
        .unwrap_or(false);
    if endpoint.is_some() && launch_spec.selected.is_none() && !endpoint_available {
        warnings.push(ReadboardSidecarWarning::new(
            ReadboardWarningCode::EndpointOnly,
            "supplied endpoint was not reachable and no local launch target was found",
        ));
    }
    let available = if endpoint.is_some() {
        endpoint_available
    } else {
        launch_spec.selected.is_some()
    };
    ReadboardProbeReport {
        available,
        endpoint: endpoint.map(str::to_string),
        version: launch_spec
            .selected
            .as_ref()
            .and_then(|target| version_from_target_path(target.path())),
        launch_spec,
        warnings,
    }
}

fn probe_endpoint(
    endpoint: &str,
    timeout_ms: Option<u64>,
    warnings: &mut Vec<ReadboardSidecarWarning>,
) -> bool {
    let timeout = Duration::from_millis(timeout_ms.unwrap_or(1_000).max(1));
    let Some((host, port)) = endpoint_socket_addr(endpoint) else {
        warnings.push(ReadboardSidecarWarning::new(
            ReadboardWarningCode::UnsupportedEndpoint,
            format!("readboard endpoint `{endpoint}` is not a host:port or http(s) URL"),
        ));
        return false;
    };
    let address = if host.contains(':') {
        format!("[{host}]:{port}")
    } else {
        format!("{host}:{port}")
    };
    let addrs = match address.to_socket_addrs() {
        Ok(addrs) => addrs.collect::<Vec<_>>(),
        Err(err) => {
            warnings.push(ReadboardSidecarWarning::new(
                ReadboardWarningCode::EndpointUnavailable,
                format!("readboard endpoint `{endpoint}` could not be resolved: {err}"),
            ));
            return false;
        }
    };
    if addrs
        .iter()
        .any(|addr| TcpStream::connect_timeout(addr, timeout).is_ok())
    {
        return true;
    }
    warnings.push(ReadboardSidecarWarning::new(
        ReadboardWarningCode::EndpointUnavailable,
        format!("readboard endpoint `{endpoint}` did not accept a TCP connection"),
    ));
    false
}

fn endpoint_socket_addr(endpoint: &str) -> Option<(String, u16)> {
    let trimmed = endpoint.trim();
    if trimmed.is_empty() {
        return None;
    }
    if let Some((scheme, rest)) = trimmed.split_once("://") {
        let default_port = match scheme.to_ascii_lowercase().as_str() {
            "http" => 80,
            "https" => 443,
            _ => return None,
        };
        let authority = rest
            .split(['/', '?', '#'])
            .next()
            .unwrap_or_default()
            .rsplit('@')
            .next()
            .unwrap_or_default();
        return parse_authority(authority, Some(default_port));
    }
    parse_authority(trimmed, None)
}

fn parse_authority(authority: &str, default_port: Option<u16>) -> Option<(String, u16)> {
    let authority = authority.trim();
    if authority.is_empty() {
        return None;
    }
    if let Some(rest) = authority.strip_prefix('[') {
        let (host, tail) = rest.split_once(']')?;
        let port = tail
            .strip_prefix(':')
            .and_then(|value| value.parse::<u16>().ok())
            .or(default_port)?;
        return Some((host.to_string(), port));
    }
    match authority.rsplit_once(':') {
        Some((host, port)) if !host.is_empty() => Some((host.to_string(), port.parse::<u16>().ok()?)),
        _ => default_port.map(|port| (authority.to_string(), port)),
    }
}

pub fn build_command_spec(
    target: &ReadboardLaunchTarget,
    transport: &ReadboardTransport,
) -> Result<ReadboardCommandSpec, ReadboardSidecarError> {
    let working_dir = target.path().parent().map(Path::to_path_buf);
    let (program, mut args) = match target {
        ReadboardLaunchTarget::Native { path } => (path.clone(), Vec::new()),
        ReadboardLaunchTarget::JavaJar {
            jar_path,
            java_program,
        } => (
            java_program.clone(),
            vec!["-jar".to_string(), jar_path.display().to_string()],
        ),
    };
    append_transport_args(&mut args, transport);
    Ok(ReadboardCommandSpec {
        program,
        args,
        env: transport_env(transport),
        working_dir,
    })
}

pub fn build_selected_command_spec(
    launch_spec: &ReadboardLaunchSpec,
    transport: &ReadboardTransport,
) -> Result<ReadboardCommandSpec, ReadboardSidecarError> {
    let target = launch_spec
        .selected
        .as_ref()
        .ok_or(ReadboardSidecarError::MissingLaunchTarget)?;
    build_command_spec(target, transport)
}

pub fn parse_snapshot_line(line: &str) -> Result<ParsedReadboardLine, ReadboardSidecarError> {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return Err(ReadboardSidecarError::EmptyProtocolLine);
    }
    if is_legacy_code_payload(trimmed) {
        let board_size =
            infer_square_board_size(trimmed.len()).ok_or_else(|| ReadboardSidecarError::InvalidField {
                field: "codes",
                value: trimmed.to_string(),
            })?;
        let snapshot = ReadBoardSnapshot::from_legacy_codes(
            board_size,
            parse_code_chars(trimmed)?,
            None,
            ReadBoardProvider::default(),
        )?;
        return Ok(ParsedReadboardLine {
            snapshot_id: None,
            snapshot,
            warnings: Vec::new(),
        });
    }

    let fields = parse_key_values(trimmed)?;
    let codes = required_field(&fields, "codes")?;
    let board_size = optional_u8(&fields, "board_size")?
        .or_else(|| infer_square_board_size(codes.len()))
        .ok_or(ReadboardSidecarError::MissingField("board_size"))?;
    let provider = parse_provider(
        fields.get("provider").map(String::as_str),
        fields.get("source").cloned(),
    )?;
    let snapshot = ReadBoardSnapshot::from_legacy_codes(
        board_size,
        parse_code_chars(codes)?,
        optional_u32(&fields, "move_number")?,
        provider,
    )?;
    Ok(ParsedReadboardLine {
        snapshot_id: fields.get("snapshot_id").cloned(),
        snapshot,
        warnings: ignored_field_warnings(&fields),
    })
}

pub fn sync_snapshot_line(
    request: &ReadboardSidecarSyncSnapshotRequest,
    protocol_line: &str,
    first_sync: bool,
    local: ReadBoardLocalContext,
) -> Result<ReadboardSyncOutcome, ReadboardSidecarError> {
    let parsed = parse_snapshot_line(protocol_line)?;
    let decision = decide_readboard_sync(&ReadBoardSyncInput {
        first_sync,
        snapshot: parsed.snapshot.clone(),
        local,
    })?;
    let snapshot_id = request
        .snapshot_id
        .clone()
        .or(parsed.snapshot_id)
        .unwrap_or_else(|| "readboard-snapshot".to_string());
    let position = snapshot_to_position(&parsed.snapshot);
    Ok(ReadboardSyncOutcome {
        snapshot_id,
        snapshot: parsed.snapshot,
        decision,
        position,
        warnings: parsed.warnings,
    })
}

pub fn sync_snapshot_image(
    request: &ReadboardSidecarSyncSnapshotRequest,
) -> Result<ReadboardSyncOutcome, ReadboardSidecarError> {
    let image_bytes = read_controlled_image_bytes(request)?;
    sync_snapshot_image_bytes(request, &image_bytes)
}

pub fn sync_snapshot_image_bytes(
    request: &ReadboardSidecarSyncSnapshotRequest,
    image_bytes: &[u8],
) -> Result<ReadboardSyncOutcome, ReadboardSidecarError> {
    let snapshot = controlled_image_snapshot(image_bytes)?;
    let local = ReadBoardLocalContext {
        board_size: snapshot.board_size,
        positions: Vec::new(),
        current_index: 0,
        main_end_index: 0,
    };
    let decision = decide_readboard_sync(&ReadBoardSyncInput {
        first_sync: true,
        snapshot: snapshot.clone(),
        local,
    })?;
    let snapshot_id = request
        .snapshot_id
        .clone()
        .unwrap_or_else(|| "controlled-image-snapshot".to_string());
    let position = snapshot_to_position(&snapshot);
    Ok(ReadboardSyncOutcome {
        snapshot_id,
        snapshot,
        decision,
        position,
        warnings: vec![
            ReadboardSidecarWarning::new(
                ReadboardWarningCode::UnsupportedProvider,
                "scoped controlled image import decoded a synthetic/controlled board image",
            ),
            ReadboardSidecarWarning::new(
                ReadboardWarningCode::UnsupportedProvider,
                "this is not full OCR and does not support arbitrary client screenshots",
            ),
        ],
    })
}

pub fn snapshot_to_position(snapshot: &ReadBoardSnapshot) -> PositionDto {
    let move_number = snapshot
        .remote_move_number
        .unwrap_or_else(|| snapshot.occupied_count());
    let to_play = if snapshot_black_to_play(snapshot) {
        PlayerColor::Black
    } else {
        PlayerColor::White
    };
    PositionDto {
        board_size: snapshot.board_size,
        move_number,
        to_play,
        stones: snapshot
            .stones
            .iter()
            .enumerate()
            .filter_map(|(index, stone)| {
                stone.map(|color| StoneDto {
                    x: (index % snapshot.board_size as usize) as u8,
                    y: (index / snapshot.board_size as usize) as u8,
                    color: color_to_dto(color),
                })
            })
            .collect(),
        captures_black: 0,
        captures_white: 0,
        last_move: snapshot.last_move.map(|marker| MoveDto {
            color: color_to_dto(marker.color),
            vertex: MoveVertex::Point(PointDto {
                x: marker.point.x,
                y: marker.point.y,
            }),
            move_number,
        }),
        errors: Vec::new(),
    }
}

fn native_candidate_paths(roots: &[PathBuf]) -> Vec<(ReadboardCandidateKind, PathBuf)> {
    let mut candidates = Vec::new();
    for root in roots {
        for relative in [
            "readboard.exe",
            "readboard.bat",
            "bin/readboard.exe",
            "bin/readboard.bat",
            "readboard/readboard.exe",
            "readboard/readboard.bat",
            "Contents/MacOS/readboard",
        ] {
            let kind = if relative.ends_with(".bat") {
                ReadboardCandidateKind::NativeBat
            } else {
                ReadboardCandidateKind::NativeExe
            };
            candidates.push((kind, root.join(relative)));
        }
    }
    dedupe_kind_paths(candidates)
}

fn java_candidate_paths(roots: &[PathBuf]) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    for root in roots {
        for relative in [
            READBOARD_JAR_NAME,
            &format!("app/{READBOARD_JAR_NAME}"),
            &format!("lib/app/{READBOARD_JAR_NAME}"),
            &format!("Contents/app/{READBOARD_JAR_NAME}"),
            &format!("Contents/Resources/{READBOARD_JAR_NAME}"),
            &format!("readboard/{READBOARD_JAR_NAME}"),
        ] {
            paths.push(root.join(relative));
        }
    }
    dedupe_paths(paths)
}

fn default_search_roots() -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Ok(home) = env::var("READBOARD_HOME") {
        if !home.trim().is_empty() {
            roots.push(PathBuf::from(home));
        }
    }
    if let Ok(exe) = env::current_exe() {
        if let Some(parent) = exe.parent() {
            roots.push(parent.to_path_buf());
            if let Some(grandparent) = parent.parent() {
                roots.push(grandparent.to_path_buf());
            }
        }
    }
    if let Ok(current_dir) = env::current_dir() {
        roots.push(current_dir);
    }
    dedupe_paths(roots)
}

fn executable_or_file_exists(path: &Path) -> bool {
    fs::metadata(path).is_ok_and(|metadata| metadata.is_file())
}

fn dedupe_kind_paths(
    candidates: Vec<(ReadboardCandidateKind, PathBuf)>,
) -> Vec<(ReadboardCandidateKind, PathBuf)> {
    let mut seen = BTreeSet::new();
    candidates
        .into_iter()
        .filter(|(kind, path)| seen.insert((*kind, path.clone())))
        .collect()
}

fn dedupe_paths(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut seen = BTreeSet::new();
    paths
        .into_iter()
        .filter(|path| seen.insert(path.clone()))
        .collect()
}

fn version_from_target_path(path: &Path) -> Option<String> {
    path.file_name()
        .and_then(|name| name.to_str())
        .and_then(|name| name.strip_prefix("readboard-"))
        .and_then(|name| name.strip_suffix("-shaded.jar"))
        .map(ToOwned::to_owned)
}

fn append_transport_args(args: &mut Vec<String>, transport: &ReadboardTransport) {
    match transport {
        ReadboardTransport::Pipe { name } => {
            args.push("--pipe".to_string());
            args.push(name.clone());
        }
        ReadboardTransport::Socket { host, port } => {
            args.push("--socket".to_string());
            args.push(format!("{host}:{port}"));
        }
    }
}

fn transport_env(transport: &ReadboardTransport) -> BTreeMap<String, String> {
    let mut env = BTreeMap::new();
    match transport {
        ReadboardTransport::Pipe { name } => {
            env.insert("READBOARD_TRANSPORT".to_string(), "pipe".to_string());
            env.insert("READBOARD_PIPE_NAME".to_string(), name.clone());
        }
        ReadboardTransport::Socket { host, port } => {
            env.insert("READBOARD_TRANSPORT".to_string(), "socket".to_string());
            env.insert("READBOARD_SOCKET_ADDR".to_string(), format!("{host}:{port}"));
        }
    }
    env
}

fn is_legacy_code_payload(value: &str) -> bool {
    !value.is_empty() && value.bytes().all(|byte| matches!(byte, b'0'..=b'4'))
}

fn infer_square_board_size(len: usize) -> Option<u8> {
    let size = (len as f64).sqrt() as usize;
    (size * size == len && (2..=25).contains(&size)).then_some(size as u8)
}

fn parse_code_chars(value: &str) -> Result<Vec<u8>, ReadboardSidecarError> {
    value
        .chars()
        .map(|ch| {
            ch.to_digit(10)
                .filter(|digit| *digit <= 4)
                .map(|digit| digit as u8)
                .ok_or_else(|| ReadboardSidecarError::InvalidField {
                    field: "codes",
                    value: ch.to_string(),
                })
        })
        .collect()
}

fn parse_key_values(line: &str) -> Result<BTreeMap<String, String>, ReadboardSidecarError> {
    let mut fields = BTreeMap::new();
    let mut tokens = line.split_whitespace();
    if matches!(tokens.clone().next(), Some("snapshot" | "readboard_snapshot")) {
        tokens.next();
    }
    for token in tokens {
        let Some((key, value)) = token.split_once('=') else {
            return Err(ReadboardSidecarError::InvalidField {
                field: "token",
                value: token.to_string(),
            });
        };
        let normalized = key.trim().to_ascii_lowercase();
        if fields
            .insert(normalized.clone(), value.trim().to_string())
            .is_some()
        {
            return Err(ReadboardSidecarError::DuplicateField { field: normalized });
        }
    }
    Ok(fields)
}

fn required_field<'a>(
    fields: &'a BTreeMap<String, String>,
    field: &'static str,
) -> Result<&'a str, ReadboardSidecarError> {
    fields
        .get(field)
        .map(String::as_str)
        .ok_or(ReadboardSidecarError::MissingField(field))
}

fn optional_u8(
    fields: &BTreeMap<String, String>,
    field: &'static str,
) -> Result<Option<u8>, ReadboardSidecarError> {
    fields
        .get(field)
        .map(|value| {
            value.parse().map_err(|_| ReadboardSidecarError::InvalidField {
                field,
                value: value.clone(),
            })
        })
        .transpose()
}

fn optional_u32(
    fields: &BTreeMap<String, String>,
    field: &'static str,
) -> Result<Option<u32>, ReadboardSidecarError> {
    fields
        .get(field)
        .map(|value| {
            value.parse().map_err(|_| ReadboardSidecarError::InvalidField {
                field,
                value: value.clone(),
            })
        })
        .transpose()
}

fn parse_provider(
    raw: Option<&str>,
    source: Option<String>,
) -> Result<ReadBoardProvider, ReadboardSidecarError> {
    let kind = match raw.unwrap_or("generic") {
        "generic" => ReadBoardProviderKind::Generic,
        "fox_live" | "fox-live" | "foxlive" => ReadBoardProviderKind::FoxLive,
        "fox_record" | "fox-record" | "foxrecord" => ReadBoardProviderKind::FoxRecord,
        value => {
            return Err(ReadboardSidecarError::InvalidField {
                field: "provider",
                value: value.to_string(),
            })
        }
    };
    Ok(ReadBoardProvider { kind, source })
}

fn ignored_field_warnings(fields: &BTreeMap<String, String>) -> Vec<ReadboardSidecarWarning> {
    fields
        .keys()
        .filter(|key| {
            !matches!(
                key.as_str(),
                "board_size" | "codes" | "move_number" | "provider" | "source" | "snapshot_id"
            )
        })
        .map(|key| {
            ReadboardSidecarWarning::new(
                ReadboardWarningCode::IgnoredToken,
                format!("ignored readboard protocol field `{key}`"),
            )
        })
        .collect()
}

fn read_controlled_image_bytes(
    request: &ReadboardSidecarSyncSnapshotRequest,
) -> Result<Vec<u8>, ReadboardSidecarError> {
    if let Some(path) = request
        .image_path
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        return fs::read(path).map_err(|err| ReadboardSidecarError::ImageRead {
            path: path.to_string(),
            message: err.to_string(),
        });
    }
    if let Some(encoded) = request
        .image_base64
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        use base64::Engine;
        return base64::engine::general_purpose::STANDARD
            .decode(encoded)
            .map_err(|err| ReadboardSidecarError::ImageBase64(err.to_string()));
    }
    Err(ReadboardSidecarError::ImageLowConfidence(
        "image_path or image_base64 is required".to_string(),
    ))
}

fn controlled_image_snapshot(image_bytes: &[u8]) -> Result<ReadBoardSnapshot, ReadboardSidecarError> {
    let image = image::load_from_memory(image_bytes)
        .map_err(|err| ReadboardSidecarError::ImageDecode(err.to_string()))?
        .to_rgb8();
    let (width, height) = image.dimensions();
    let side = width.min(height);
    if side < 95 {
        return Err(ReadboardSidecarError::ImageLowConfidence(format!(
            "image is too small for controlled board sampling: {width}x{height}"
        )));
    }
    let aspect_delta = width.abs_diff(height);
    if aspect_delta.saturating_mul(100) > side.saturating_mul(8) {
        return Err(ReadboardSidecarError::ImageLowConfidence(format!(
            "controlled board image must be approximately square: {width}x{height}"
        )));
    }

    let origin_x = (width - side) as f32 / 2.0;
    let origin_y = (height - side) as f32 / 2.0;
    let margin = (side as f32 * 0.055).max(4.0);
    let background = average_rgb(
        &image,
        origin_x + side as f32 * 0.12,
        origin_y + side as f32 * 0.12,
        (side as f32 * 0.012).clamp(2.0, 8.0),
    );
    if !looks_like_controlled_board_background(background) {
        return Err(ReadboardSidecarError::ImageLowConfidence(format!(
            "controlled board background was not detected; sampled rgb={background:?}"
        )));
    }

    let candidates = [19usize, 13usize]
        .into_iter()
        .filter_map(|board_size| {
            controlled_image_snapshot_candidate(
                &image,
                board_size,
                origin_x,
                origin_y,
                side as f32,
                margin,
                background,
            )
        })
        .collect::<Vec<_>>();
    let Some(best) = candidates
        .into_iter()
        .max_by_key(|candidate| (candidate.grid_confidence, candidate.occupied))
    else {
        return Err(ReadboardSidecarError::ImageLowConfidence(
            "no controlled 13x13 or 19x19 board grid was detected".to_string(),
        ));
    };
    Ok(best.snapshot)
}

struct ControlledImageCandidate {
    snapshot: ReadBoardSnapshot,
    occupied: usize,
    grid_confidence: usize,
}

fn controlled_image_snapshot_candidate(
    image: &image::RgbImage,
    board_size: usize,
    origin_x: f32,
    origin_y: f32,
    side: f32,
    margin: f32,
    background: [u8; 3],
) -> Option<ControlledImageCandidate> {
    let spacing = (side - margin * 2.0) / (board_size as f32 - 1.0);
    let sample_radius = (spacing * 0.22).clamp(2.0, 8.0);
    let grid_radius = (spacing * 0.045).clamp(1.0, 3.0);
    let background_luma = rgb_luma(background);
    let mut stones = Vec::with_capacity(board_size * board_size);
    let mut occupied = 0usize;
    let mut grid_confidence = 0usize;

    for y in 0..board_size {
        for x in 0..board_size {
            let sample_x = origin_x + margin + x as f32 * spacing;
            let sample_y = origin_y + margin + y as f32 * spacing;
            let grid_rgb = average_rgb(image, sample_x, sample_y, grid_radius);
            let stone_rgb = average_rgb(image, sample_x, sample_y, sample_radius);
            let stone = classify_controlled_stone(stone_rgb);
            if stone.is_some() {
                occupied += 1;
            }
            if stone.is_some() || rgb_luma(grid_rgb).saturating_add(35) < background_luma {
                grid_confidence += 1;
            }
            stones.push(stone);
        }
    }

    let minimum_grid_confidence = board_size * board_size * 3 / 5;
    if occupied == 0 || grid_confidence < minimum_grid_confidence {
        return None;
    }

    Some(ControlledImageCandidate {
        snapshot: ReadBoardSnapshot {
            board_size: board_size as u8,
            stones,
            last_move: None,
            remote_move_number: Some(occupied as u32),
            provider: ReadBoardProvider {
                kind: ReadBoardProviderKind::Generic,
                source: Some("controlled_image_import".to_string()),
            },
        },
        occupied,
        grid_confidence,
    })
}

fn average_rgb(image: &image::RgbImage, x: f32, y: f32, radius: f32) -> [u8; 3] {
    let (width, height) = image.dimensions();
    let min_x = (x - radius).floor().max(0.0) as u32;
    let max_x = (x + radius).ceil().min(width.saturating_sub(1) as f32) as u32;
    let min_y = (y - radius).floor().max(0.0) as u32;
    let max_y = (y + radius).ceil().min(height.saturating_sub(1) as f32) as u32;
    let mut total = [0u32; 3];
    let mut count = 0u32;
    for py in min_y..=max_y {
        for px in min_x..=max_x {
            let pixel = image.get_pixel(px, py).0;
            total[0] += u32::from(pixel[0]);
            total[1] += u32::from(pixel[1]);
            total[2] += u32::from(pixel[2]);
            count += 1;
        }
    }
    [
        (total[0] / count.max(1)) as u8,
        (total[1] / count.max(1)) as u8,
        (total[2] / count.max(1)) as u8,
    ]
}

fn classify_controlled_stone(rgb: [u8; 3]) -> Option<Color> {
    let [r, g, b] = rgb;
    let luma = rgb_luma(rgb);
    let spread = r.max(g).max(b) - r.min(g).min(b);
    if luma < 80 {
        Some(Color::Black)
    } else if luma > 220 && spread < 38 {
        Some(Color::White)
    } else {
        None
    }
}

fn looks_like_controlled_board_background(rgb: [u8; 3]) -> bool {
    let [r, g, b] = rgb;
    let luma = rgb_luma(rgb);
    let spread = r.max(g).max(b) - r.min(g).min(b);
    (90..=215).contains(&luma) && spread > 35
}

fn rgb_luma(rgb: [u8; 3]) -> u16 {
    let [r, g, b] = rgb;
    (u16::from(r) * 54 + u16::from(g) * 183 + u16::from(b) * 19) / 256
}

fn snapshot_black_to_play(snapshot: &ReadBoardSnapshot) -> bool {
    if let Some(marker) = snapshot.last_move {
        return marker.color == Color::White;
    }
    if snapshot.provider.kind.is_fox() {
        if let Some(move_number) = snapshot.remote_move_number {
            return move_number & 1 == 0;
        }
    }
    snapshot.occupied_count() & 1 == 0
}

fn color_to_dto(color: Color) -> PlayerColor {
    match color {
        Color::Black => PlayerColor::Black,
        Color::White => PlayerColor::White,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use go_core::{Point, ReadBoardLocalPosition, ReadBoardMarker};
    use image::{ImageEncoder, Rgb, RgbImage};
    use serde::{Deserialize, Serialize};
    use sha2::{Digest, Sha256};
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    use std::io::Cursor;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn resolves_native_and_java_layout_candidates() {
        let root = temp_root("resolve-candidates");
        let native = root.join("bin").join("readboard.exe");
        let jar = root.join("lib").join("app").join(READBOARD_JAR_NAME);
        touch(&native);
        touch(&jar);

        let spec = resolve_launch_spec(&ReadboardSidecarOptions {
            search_roots: vec![root.clone()],
            java_program: PathBuf::from("java"),
        });

        assert!(spec
            .native_candidates
            .iter()
            .any(|candidate| candidate.path == native && candidate.exists));
        assert!(spec
            .java_candidates
            .iter()
            .any(|candidate| candidate.path == jar && candidate.exists));
        assert_eq!(
            spec.selected,
            Some(ReadboardLaunchTarget::Native { path: native })
        );

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn builds_java_fallback_pipe_command_without_spawning() {
        let jar = PathBuf::from("/opt/readboard/lib/app/readboard-1.6.2-shaded.jar");
        let target = ReadboardLaunchTarget::JavaJar {
            jar_path: jar.clone(),
            java_program: PathBuf::from("/usr/bin/java"),
        };

        let spec = build_command_spec(
            &target,
            &ReadboardTransport::Pipe {
                name: "rb-test".to_string(),
            },
        )
        .unwrap();

        assert_eq!(spec.program, PathBuf::from("/usr/bin/java"));
        assert_eq!(
            spec.args,
            vec![
                "-jar".to_string(),
                jar.display().to_string(),
                "--pipe".to_string(),
                "rb-test".to_string(),
            ]
        );
        assert_eq!(spec.env["READBOARD_TRANSPORT"], "pipe");
        assert_eq!(spec.env["READBOARD_PIPE_NAME"], "rb-test");
        assert_eq!(spec.working_dir, Some(PathBuf::from("/opt/readboard/lib/app")));
    }

    #[test]
    fn invalid_legacy_codes_are_rejected() {
        let error =
            parse_snapshot_line("snapshot board_size=2 codes=0009").expect_err("code 9 should be rejected");

        assert!(matches!(
            error,
            ReadboardSidecarError::InvalidField { field: "codes", .. }
        ));
    }

    #[test]
    fn parses_simple_snapshot_line_with_legacy_marker() {
        let parsed = parse_snapshot_line(
            "snapshot snapshot_id=s1 board_size=2 provider=fox_live source=room-1 move_number=1 codes=3000",
        )
        .unwrap();

        assert_eq!(parsed.snapshot_id, Some("s1".to_string()));
        assert_eq!(parsed.snapshot.board_size, 2);
        assert_eq!(parsed.snapshot.remote_move_number, Some(1));
        assert_eq!(parsed.snapshot.provider.kind, ReadBoardProviderKind::FoxLive);
        assert_eq!(
            parsed.snapshot.last_move,
            Some(ReadBoardMarker {
                point: Point { x: 0, y: 0 },
                color: Color::Black,
            })
        );
    }

    #[test]
    fn sync_snapshot_line_calls_go_core_decision() {
        let request = ReadboardSidecarSyncSnapshotRequest {
            snapshot_id: Some("from-request".to_string()),
            ..Default::default()
        };
        let local = ReadBoardLocalContext {
            board_size: 2,
            positions: vec![ReadBoardLocalPosition::new(vec![None; 4], None, 0, true)],
            current_index: 0,
            main_end_index: 0,
        };

        let outcome = sync_snapshot_line(
            &request,
            "snapshot board_size=2 move_number=1 codes=1000",
            false,
            local,
        )
        .unwrap();

        assert_eq!(outcome.snapshot_id, "from-request");
        assert_eq!(
            outcome.decision,
            ReadBoardSyncDecision::AppendMove {
                point: Point { x: 0, y: 0 },
                color: Color::Black,
                move_number: 1,
                black_to_play: false,
            }
        );
        assert_eq!(outcome.position.stones.len(), 1);
        assert_eq!(outcome.position.to_play, PlayerColor::White);
    }

    #[test]
    fn sync_snapshot_image_path_decodes_controlled_board() {
        let root = temp_root("image-path");
        fs::create_dir_all(&root).unwrap();
        let image_path = root.join("controlled-board.png");
        let image_bytes = controlled_board_png();
        fs::write(&image_path, image_bytes).unwrap();
        let request = ReadboardSidecarSyncSnapshotRequest {
            snapshot_id: Some("path-snapshot".to_string()),
            image_path: Some(image_path.display().to_string()),
            ..Default::default()
        };

        let outcome = sync_snapshot_image(&request).unwrap();

        let _ = fs::remove_dir_all(root);
        assert_eq!(outcome.snapshot_id, "path-snapshot");
        assert_eq!(outcome.position.board_size, 19);
        assert_eq!(outcome.position.move_number, 3);
        assert_eq!(outcome.position.stones.len(), 3);
        assert!(outcome
            .position
            .stones
            .iter()
            .any(|stone| { stone.x == 3 && stone.y == 3 && stone.color == PlayerColor::Black }));
        assert!(outcome
            .position
            .stones
            .iter()
            .any(|stone| { stone.x == 15 && stone.y == 15 && stone.color == PlayerColor::White }));
        assert!(outcome
            .warnings
            .iter()
            .any(|warning| warning.message.contains("controlled image import")));
        assert!(outcome
            .warnings
            .iter()
            .any(|warning| warning.message.contains("not full OCR")));
    }

    #[test]
    fn sync_snapshot_image_base64_decodes_controlled_board() {
        use base64::Engine;
        let request = ReadboardSidecarSyncSnapshotRequest {
            snapshot_id: Some("base64-snapshot".to_string()),
            image_base64: Some(base64::engine::general_purpose::STANDARD.encode(controlled_board_png())),
            ..Default::default()
        };

        let outcome = sync_snapshot_image(&request).unwrap();

        assert_eq!(outcome.snapshot_id, "base64-snapshot");
        assert_eq!(outcome.position.board_size, 19);
        assert_eq!(outcome.position.stones.len(), 3);
    }

    #[test]
    fn sync_snapshot_image_rejects_bad_base64() {
        let request = ReadboardSidecarSyncSnapshotRequest {
            image_base64: Some("not valid base64@@".to_string()),
            ..Default::default()
        };

        let error = sync_snapshot_image(&request).unwrap_err();

        assert!(matches!(error, ReadboardSidecarError::ImageBase64(_)));
    }

    #[test]
    fn sync_snapshot_image_rejects_invalid_image_bytes() {
        let request = ReadboardSidecarSyncSnapshotRequest {
            image_base64: Some("bm90LWEtcG5n".to_string()),
            ..Default::default()
        };

        let error = sync_snapshot_image(&request).unwrap_err();

        assert!(matches!(error, ReadboardSidecarError::ImageDecode(_)));
    }

    #[test]
    fn sync_snapshot_image_rejects_low_confidence_non_board() {
        use base64::Engine;
        let image = RgbImage::from_pixel(180, 180, Rgb([240, 240, 240]));
        let request = ReadboardSidecarSyncSnapshotRequest {
            image_base64: Some(base64::engine::general_purpose::STANDARD.encode(png_bytes(image))),
            ..Default::default()
        };

        let error = sync_snapshot_image(&request).unwrap_err();

        assert!(matches!(error, ReadboardSidecarError::ImageLowConfidence(_)));
    }

    #[test]
    fn sync_snapshot_image_reports_unreadable_path() {
        let request = ReadboardSidecarSyncSnapshotRequest {
            image_path: Some(
                temp_root("missing-image")
                    .join("missing.png")
                    .display()
                    .to_string(),
            ),
            ..Default::default()
        };

        let error = sync_snapshot_image(&request).unwrap_err();

        assert!(matches!(error, ReadboardSidecarError::ImageRead { .. }));
    }

    #[test]
    fn sync_snapshot_image_fixtures_have_metadata_and_path_base64_equivalence() {
        use base64::Engine;
        let metadata = read_fixture_metadata();
        let valid = metadata
            .fixtures
            .iter()
            .filter(|fixture| fixture.kind == "valid_controlled_board")
            .collect::<Vec<_>>();
        assert!(valid.len() >= 2);

        for fixture in valid {
            assert_fixture_digest(fixture);
            let path = fixture_path(&fixture.path);
            let bytes = fs::read(&path).unwrap();
            let path_outcome = sync_snapshot_image(&ReadboardSidecarSyncSnapshotRequest {
                snapshot_id: Some(format!("path-{}", fixture.board_size.unwrap())),
                image_path: Some(path.display().to_string()),
                ..Default::default()
            })
            .unwrap();
            let base64_outcome = sync_snapshot_image(&ReadboardSidecarSyncSnapshotRequest {
                snapshot_id: Some(format!("base64-{}", fixture.board_size.unwrap())),
                image_base64: Some(base64::engine::general_purpose::STANDARD.encode(bytes)),
                ..Default::default()
            })
            .unwrap();

            assert_eq!(path_outcome.position.board_size, fixture.board_size.unwrap());
            assert_eq!(path_outcome.position.stones.len(), fixture.stone_count.unwrap());
            assert_eq!(
                base64_outcome.position.board_size,
                path_outcome.position.board_size
            );
            assert_eq!(
                base64_outcome.position.stones.len(),
                path_outcome.position.stones.len()
            );
            assert_eq!(
                fingerprint(&path_outcome.snapshot),
                fingerprint(&base64_outcome.snapshot)
            );
            assert_eq!(
                fingerprint(&path_outcome.position),
                fingerprint(&base64_outcome.position)
            );
            assert!(path_outcome
                .warnings
                .iter()
                .any(|warning| warning.message.contains("not full OCR")));
        }
    }

    #[test]
    fn sync_snapshot_image_fixture_failures_are_not_importable() {
        let metadata = read_fixture_metadata();
        for fixture in metadata
            .fixtures
            .iter()
            .filter(|fixture| fixture.kind != "valid_controlled_board")
        {
            assert_fixture_digest(fixture);
            let error = sync_snapshot_image(&ReadboardSidecarSyncSnapshotRequest {
                snapshot_id: Some(format!("failure-{}", fixture.kind)),
                image_path: Some(fixture_path(&fixture.path).display().to_string()),
                ..Default::default()
            })
            .expect_err("invalid/non-board fixture must not decode to a default board");

            match fixture.expected_error.as_deref() {
                Some("ImageLowConfidence") => {
                    assert!(matches!(error, ReadboardSidecarError::ImageLowConfidence(_)))
                }
                Some("ImageDecode") => {
                    assert!(matches!(error, ReadboardSidecarError::ImageDecode(_)))
                }
                other => panic!("unsupported fixture expectedError: {other:?}"),
            }
        }
    }

    #[test]
    fn probe_reports_missing_candidates_with_structured_warnings() {
        let root = temp_root("probe-missing");
        fs::create_dir_all(&root).unwrap();
        let report = probe_readboard_sidecar(
            &ReadboardSidecarProbeRequest {
                endpoint: None,
                timeout_ms: Some(100),
            },
            &ReadboardSidecarOptions {
                search_roots: vec![root.clone()],
                java_program: PathBuf::from("java"),
            },
        );

        assert!(!report.available);
        assert!(report
            .warnings
            .iter()
            .any(|warning| warning.code == ReadboardWarningCode::MissingNative));
        assert!(report
            .warnings
            .iter()
            .any(|warning| warning.code == ReadboardWarningCode::MissingJava));
        assert!(report
            .warnings
            .iter()
            .any(|warning| warning.code == ReadboardWarningCode::RuntimeUnavailable));

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn probe_does_not_mark_unprobeable_endpoint_available() {
        let root = temp_root("probe-fake-endpoint");
        fs::create_dir_all(&root).unwrap();
        let report = probe_readboard_sidecar(
            &ReadboardSidecarProbeRequest {
                endpoint: Some("local-test-endpoint".to_string()),
                timeout_ms: Some(10),
            },
            &ReadboardSidecarOptions {
                search_roots: vec![root.clone()],
                java_program: PathBuf::from("java"),
            },
        );

        assert!(!report.available);
        assert_eq!(report.endpoint.as_deref(), Some("local-test-endpoint"));
        assert!(report
            .warnings
            .iter()
            .any(|warning| warning.code == ReadboardWarningCode::UnsupportedEndpoint));

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn probe_does_not_let_launch_target_mask_bad_endpoint() {
        let root = temp_root("probe-bad-endpoint-with-launch-target");
        let native = root.join("bin").join("readboard.exe");
        touch(&native);

        let report = probe_readboard_sidecar(
            &ReadboardSidecarProbeRequest {
                endpoint: Some("local-test-endpoint".to_string()),
                timeout_ms: Some(10),
            },
            &ReadboardSidecarOptions {
                search_roots: vec![root.clone()],
                java_program: PathBuf::from("java"),
            },
        );

        assert!(!report.available);
        assert!(report.launch_spec.selected.is_some());
        assert_eq!(report.endpoint.as_deref(), Some("local-test-endpoint"));
        assert!(report
            .warnings
            .iter()
            .any(|warning| warning.code == ReadboardWarningCode::UnsupportedEndpoint));

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn probe_marks_reachable_tcp_endpoint_available_without_launch_target() {
        let root = temp_root("probe-tcp-endpoint");
        fs::create_dir_all(&root).unwrap();
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());

        let report = probe_readboard_sidecar(
            &ReadboardSidecarProbeRequest {
                endpoint: Some(endpoint.clone()),
                timeout_ms: Some(100),
            },
            &ReadboardSidecarOptions {
                search_roots: vec![root.clone()],
                java_program: PathBuf::from("java"),
            },
        );

        assert!(report.available);
        assert_eq!(report.endpoint.as_deref(), Some(endpoint.as_str()));

        let _ = fs::remove_dir_all(root);
    }

    fn temp_root(label: &str) -> PathBuf {
        let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        env::temp_dir().join(format!("readboard-sidecar-{label}-{nanos}"))
    }

    fn fixture_path(relative: &str) -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").join(relative)
    }

    fn read_fixture_metadata() -> ReadboardImageFixtureMetadata {
        let path = fixture_path("tests/fixtures/readboard-images/metadata.json");
        serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap()
    }

    fn assert_fixture_digest(fixture: &ReadboardImageFixture) {
        let path = fixture_path(&fixture.path);
        let bytes = fs::read(path).unwrap();
        assert_eq!(bytes.len() as u64, fixture.bytes);
        let digest = Sha256::digest(&bytes);
        assert_eq!(format!("{digest:x}"), fixture.sha256);
    }

    fn fingerprint(value: &impl Serialize) -> u64 {
        let json = serde_json::to_string(value).unwrap();
        let mut hasher = DefaultHasher::new();
        json.hash(&mut hasher);
        hasher.finish()
    }

    #[derive(Debug, Deserialize)]
    struct ReadboardImageFixtureMetadata {
        fixtures: Vec<ReadboardImageFixture>,
    }

    #[derive(Debug, Deserialize)]
    #[serde(rename_all = "camelCase")]
    struct ReadboardImageFixture {
        path: String,
        bytes: u64,
        sha256: String,
        kind: String,
        board_size: Option<u8>,
        stone_count: Option<usize>,
        expected_error: Option<String>,
    }

    fn controlled_board_png() -> Vec<u8> {
        let side = 400u32;
        let mut image = RgbImage::from_pixel(side, side, Rgb([205, 154, 80]));
        let margin = 22.0f32;
        let spacing = (side as f32 - margin * 2.0) / 18.0;
        for index in 0..19 {
            let coord = (margin + index as f32 * spacing).round() as u32;
            for pixel in margin as u32..=(side - margin as u32) {
                image.put_pixel(coord, pixel, Rgb([45, 35, 20]));
                image.put_pixel(pixel, coord, Rgb([45, 35, 20]));
            }
        }
        draw_stone(&mut image, 3, 3, Rgb([12, 12, 12]));
        draw_stone(&mut image, 10, 4, Rgb([12, 12, 12]));
        draw_stone(&mut image, 15, 15, Rgb([245, 245, 240]));
        png_bytes(image)
    }

    fn draw_stone(image: &mut RgbImage, board_x: u32, board_y: u32, color: Rgb<u8>) {
        let side = image.width();
        let margin = 22.0f32;
        let spacing = (side as f32 - margin * 2.0) / 18.0;
        let center_x = (margin + board_x as f32 * spacing).round() as i32;
        let center_y = (margin + board_y as f32 * spacing).round() as i32;
        let radius = 8i32;
        for y in center_y - radius..=center_y + radius {
            for x in center_x - radius..=center_x + radius {
                if x < 0 || y < 0 || x >= side as i32 || y >= image.height() as i32 {
                    continue;
                }
                let dx = x - center_x;
                let dy = y - center_y;
                if dx * dx + dy * dy <= radius * radius {
                    image.put_pixel(x as u32, y as u32, color);
                }
            }
        }
    }

    fn png_bytes(image: RgbImage) -> Vec<u8> {
        let mut bytes = Vec::new();
        let mut cursor = Cursor::new(&mut bytes);
        image::codecs::png::PngEncoder::new(&mut cursor)
            .write_image(
                image.as_raw(),
                image.width(),
                image.height(),
                image::ExtendedColorType::Rgb8,
            )
            .unwrap();
        bytes
    }

    fn touch(path: &Path) {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, b"test").unwrap();
    }
}
