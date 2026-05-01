use app_model::{EngineBackend, EngineProfileDto};
use serde::{Deserialize, Serialize};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc::{self, Receiver},
    Arc,
};
use std::thread;
use std::time::{Duration, Instant};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandSpec {
    pub program: String,
    pub args: Vec<String>,
    pub working_dir: Option<String>,
    pub env: Vec<(String, String)>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssetCheck {
    pub path: String,
    pub exists: bool,
    pub required: bool,
    pub label: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisRunResult {
    pub response_jsonl: String,
    pub stderr: String,
    pub exit_code: Option<i32>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisBatchRunResult {
    pub response_jsonl_lines: Vec<String>,
    pub stderr: String,
    pub exit_code: Option<i32>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisBatchProgress {
    pub response_index: usize,
    pub expected_responses: usize,
    pub response_jsonl_line: String,
}
#[derive(Debug, Clone, Default)]
pub struct AnalysisCancelToken {
    cancelled: Arc<AtomicBool>,
}
impl AnalysisCancelToken {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::SeqCst);
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::SeqCst)
    }
}
pub struct AnalysisBatchRunOptions<'a> {
    pub expected_responses: usize,
    pub timeout: Duration,
    pub cancel_token: Option<&'a AnalysisCancelToken>,
    pub on_progress: Option<&'a mut dyn FnMut(AnalysisBatchProgress)>,
}
impl<'a> AnalysisBatchRunOptions<'a> {
    pub fn new(expected_responses: usize, timeout: Duration) -> Self {
        Self {
            expected_responses,
            timeout,
            cancel_token: None,
            on_progress: None,
        }
    }
}
#[derive(Debug, Error)]
pub enum EngineManagerError {
    #[error("engine path is required")]
    MissingEnginePath,
    #[error("model path is required for KataGo analysis")]
    MissingModelPath,
    #[error("config path is required for KataGo analysis")]
    MissingConfigPath,
    #[error("engine path does not exist: {path}")]
    EnginePathNotFound { path: String },
    #[error("model path does not exist: {path}")]
    ModelPathNotFound { path: String },
    #[error("config path does not exist: {path}")]
    ConfigPathNotFound { path: String },
    #[error("working directory does not exist: {path}")]
    WorkingDirNotFound { path: String },
    #[error("failed to spawn engine `{program}`: {source}")]
    Spawn {
        program: String,
        #[source]
        source: io::Error,
    },
    #[error(
        "failed to write analysis query to engine stdin: {source}; exit_code={exit_code:?}; stderr={stderr}"
    )]
    StdinWrite {
        #[source]
        source: io::Error,
        exit_code: Option<i32>,
        stderr: String,
    },
    #[error("failed to read engine stdout: {source}; exit_code={exit_code:?}; stderr={stderr}")]
    StdoutRead {
        #[source]
        source: io::Error,
        exit_code: Option<i32>,
        stderr: String,
    },
    #[error("failed while waiting for engine process: {source}")]
    Wait {
        #[source]
        source: io::Error,
    },
    #[error("engine did not write an analysis response; exit_code={exit_code:?}; stderr={stderr}")]
    MissingStdout { exit_code: Option<i32>, stderr: String },
    #[error(
        "engine wrote fewer analysis responses than expected; expected={expected_responses}; received={received_responses}; exit_code={exit_code:?}; stdout={stdout:?}; stderr={stderr}"
    )]
    InsufficientStdout {
        expected_responses: usize,
        received_responses: usize,
        stdout: Vec<String>,
        exit_code: Option<i32>,
        stderr: String,
    },
    #[error("engine exited unsuccessfully; exit_code={exit_code:?}; stdout={stdout:?}; stderr={stderr}")]
    NonZeroExit {
        exit_code: Option<i32>,
        stdout: Option<String>,
        stderr: String,
    },
    #[error(
        "engine analysis timed out after {timeout_ms}ms; exit_code={exit_code:?}; stdout={stdout:?}; stderr={stderr}"
    )]
    Timeout {
        timeout_ms: u128,
        exit_code: Option<i32>,
        stdout: Option<String>,
        stderr: String,
    },
    #[error(
        "engine analysis was cancelled; received_responses={received_responses}; exit_code={exit_code:?}; stdout={stdout:?}; stderr={stderr}"
    )]
    Cancelled {
        received_responses: usize,
        stdout: Vec<String>,
        exit_code: Option<i32>,
        stderr: String,
    },
}

pub fn run_katago_analysis_batch(
    spec: &CommandSpec,
    query_jsonl: &str,
    expected_responses: usize,
    timeout: Duration,
) -> Result<AnalysisBatchRunResult, EngineManagerError> {
    run_katago_analysis_batch_with_options(
        spec,
        query_jsonl,
        AnalysisBatchRunOptions::new(expected_responses, timeout),
    )
}

pub fn run_katago_analysis_batch_with_options(
    spec: &CommandSpec,
    query_jsonl: &str,
    mut options: AnalysisBatchRunOptions<'_>,
) -> Result<AnalysisBatchRunResult, EngineManagerError> {
    validate_command_spec(spec)?;

    if options.expected_responses == 0 {
        return Ok(AnalysisBatchRunResult {
            response_jsonl_lines: Vec::new(),
            stderr: String::new(),
            exit_code: None,
        });
    }

    let mut command = build_process_command(spec);
    let mut child = command.spawn().map_err(|source| EngineManagerError::Spawn {
        program: spec.program.clone(),
        source,
    })?;

    let stdout = child
        .stdout
        .take()
        .expect("stdout is piped before spawning the engine");
    let stderr = child
        .stderr
        .take()
        .expect("stderr is piped before spawning the engine");
    let stdout_rx = spawn_stdout_lines_reader(stdout);
    let stderr_rx = spawn_stderr_reader(stderr);

    if let Err(source) = write_query(&mut child, query_jsonl) {
        let _ = child.kill();
        let exit_code = child.wait().ok().and_then(|status| status.code());
        let stderr = receive_stderr(stderr_rx);
        return Err(EngineManagerError::StdinWrite {
            source,
            exit_code,
            stderr,
        });
    }

    if is_cancelled(&options) {
        let exit_code = kill_cancelled_child(&mut child)
            .ok()
            .and_then(|status| status.code());
        let stderr = receive_stderr(stderr_rx);
        return Err(EngineManagerError::Cancelled {
            received_responses: 0,
            stdout: Vec::new(),
            exit_code,
            stderr,
        });
    }

    let deadline = Instant::now() + options.timeout;
    let mut response_lines = Vec::new();
    let status = loop {
        if is_cancelled(&options) {
            let exit_code = kill_cancelled_child(&mut child)
                .ok()
                .and_then(|status| status.code());
            let stderr = receive_stderr(stderr_rx);
            return Err(EngineManagerError::Cancelled {
                received_responses: response_lines.len(),
                stdout: response_lines,
                exit_code,
                stderr,
            });
        }

        match receive_available_stdout_line(&stdout_rx) {
            Ok(Some(line)) => {
                push_batch_response_line(&mut response_lines, line, &mut options);
                if response_lines.len() >= options.expected_responses {
                    break wait_for_batch_exit(
                        &mut child,
                        deadline,
                        options.timeout,
                        &response_lines,
                        &stderr_rx,
                        &options,
                    )?;
                }
            }
            Ok(None) => {
                break wait_until_deadline(&mut child, deadline, options.timeout)?;
            }
            Err(BatchStdoutEventError::Read(source)) => {
                let _ = child.kill();
                let exit_code = child.wait().ok().and_then(|status| status.code());
                let stderr = receive_stderr(stderr_rx);
                return Err(EngineManagerError::StdoutRead {
                    source,
                    exit_code,
                    stderr,
                });
            }
            Err(BatchStdoutEventError::NoLineReady) => {}
        }

        if let Some(status) = child
            .try_wait()
            .map_err(|source| EngineManagerError::Wait { source })?
        {
            collect_remaining_stdout(
                &stdout_rx,
                &mut response_lines,
                status.code(),
                &stderr_rx,
                &mut options,
            )?;
            break status;
        }

        if Instant::now() >= deadline {
            let exit_code = kill_timed_out_child(&mut child)
                .ok()
                .and_then(|status| status.code());
            let stderr = receive_stderr(stderr_rx);
            return Err(EngineManagerError::Timeout {
                timeout_ms: options.timeout.as_millis(),
                exit_code,
                stdout: stdout_summary(&response_lines),
                stderr,
            });
        }

        thread::sleep(Duration::from_millis(10));
    };

    collect_remaining_stdout(
        &stdout_rx,
        &mut response_lines,
        status.code(),
        &stderr_rx,
        &mut options,
    )?;
    let stderr = receive_stderr(stderr_rx);

    if !status.success() {
        return Err(EngineManagerError::NonZeroExit {
            exit_code: status.code(),
            stdout: stdout_summary(&response_lines),
            stderr,
        });
    }

    if response_lines.is_empty() {
        return Err(EngineManagerError::MissingStdout {
            exit_code: status.code(),
            stderr,
        });
    }

    if response_lines.len() < options.expected_responses {
        return Err(EngineManagerError::InsufficientStdout {
            expected_responses: options.expected_responses,
            received_responses: response_lines.len(),
            stdout: response_lines,
            exit_code: status.code(),
            stderr,
        });
    }

    response_lines.truncate(options.expected_responses);
    Ok(AnalysisBatchRunResult {
        response_jsonl_lines: response_lines,
        stderr,
        exit_code: status.code(),
    })
}

pub fn build_command_spec(profile: &EngineProfileDto) -> Result<CommandSpec, EngineManagerError> {
    if profile.engine_path.trim().is_empty() {
        return Err(EngineManagerError::MissingEnginePath);
    }
    let working_dir = normalized_optional_path(profile.working_dir.as_deref());
    if let Some(working_dir) = working_dir.as_deref() {
        if !Path::new(working_dir).is_dir() {
            return Err(EngineManagerError::WorkingDirNotFound {
                path: working_dir.to_string(),
            });
        }
    }
    let program = resolve_program_path(&profile.engine_path, working_dir.as_deref());
    match profile.backend {
        EngineBackend::KataGoAnalysis => {
            let model = profile
                .model_path
                .as_ref()
                .filter(|v| !v.trim().is_empty())
                .ok_or(EngineManagerError::MissingModelPath)?;
            let config = profile
                .config_path
                .as_ref()
                .filter(|v| !v.trim().is_empty())
                .ok_or(EngineManagerError::MissingConfigPath)?;
            let model = resolve_asset_path(model, working_dir.as_deref());
            let config = resolve_asset_path(config, working_dir.as_deref());
            if !asset_exists(&model) {
                return Err(EngineManagerError::ModelPathNotFound { path: model });
            }
            if !asset_exists(&config) {
                return Err(EngineManagerError::ConfigPathNotFound { path: config });
            }
            Ok(CommandSpec {
                program,
                args: vec![
                    "analysis".into(),
                    "-config".into(),
                    config,
                    "-model".into(),
                    model,
                ],
                working_dir,
                env: vec![],
            })
        }
        EngineBackend::KataGoGtp => Ok(CommandSpec {
            program,
            args: vec!["gtp".into()],
            working_dir,
            env: vec![],
        }),
        EngineBackend::GenericGtp | EngineBackend::ReadboardSidecar => Ok(CommandSpec {
            program,
            args: vec![],
            working_dir,
            env: vec![],
        }),
    }
}

pub fn check_assets(profile: &EngineProfileDto) -> Vec<AssetCheck> {
    let requires_analysis_assets = matches!(profile.backend, EngineBackend::KataGoAnalysis);
    let working_dir = normalized_optional_path(profile.working_dir.as_deref());
    let engine_path = resolve_program_path(&profile.engine_path, working_dir.as_deref());
    let mut checks = vec![AssetCheck {
        path: engine_path.clone(),
        exists: program_exists(&engine_path),
        required: true,
        label: "engine binary".into(),
    }];
    if let Some(working_dir) = working_dir.as_deref() {
        checks.push(AssetCheck {
            path: working_dir.to_string(),
            exists: Path::new(working_dir).is_dir(),
            required: true,
            label: "working directory".into(),
        });
    }
    if requires_analysis_assets || profile.model_path.is_some() {
        let model = profile.model_path.as_deref().unwrap_or("");
        let resolved_model = resolve_asset_path(model, working_dir.as_deref());
        checks.push(AssetCheck {
            path: resolved_model.clone(),
            exists: asset_exists(&resolved_model),
            required: requires_analysis_assets,
            label: "model".into(),
        });
    }
    if requires_analysis_assets || profile.config_path.is_some() {
        let config = profile.config_path.as_deref().unwrap_or("");
        let resolved_config = resolve_asset_path(config, working_dir.as_deref());
        checks.push(AssetCheck {
            path: resolved_config.clone(),
            exists: asset_exists(&resolved_config),
            required: requires_analysis_assets,
            label: "config".into(),
        });
    }
    checks
}

fn asset_exists(path: &str) -> bool {
    if path.trim().is_empty() {
        return false;
    }
    Path::new(path).exists()
}

fn normalized_optional_path(path: Option<&str>) -> Option<String> {
    path.map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn resolve_program_path(program: &str, working_dir: Option<&str>) -> String {
    let trimmed = program.trim();
    if trimmed.is_empty() || !should_preflight_program_path(trimmed) {
        return trimmed.to_string();
    }
    resolve_path(trimmed, working_dir)
}

fn resolve_asset_path(path: &str, working_dir: Option<&str>) -> String {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return trimmed.to_string();
    }
    resolve_path(trimmed, working_dir)
}

fn resolve_path(path: &str, working_dir: Option<&str>) -> String {
    let path = Path::new(path);
    if path.is_absolute() {
        return path.to_string_lossy().into_owned();
    }

    match working_dir.filter(|value| !value.trim().is_empty()) {
        Some(working_dir) => Path::new(working_dir).join(path),
        None => path.to_path_buf(),
    }
    .to_string_lossy()
    .into_owned()
}

fn program_exists(program: &str) -> bool {
    if program.trim().is_empty() {
        return false;
    }

    if should_preflight_program_path(program) {
        return Path::new(program).exists();
    }

    path_lookup(program).is_some()
}

fn path_lookup(program: &str) -> Option<PathBuf> {
    let path_var = std::env::var_os("PATH")?;
    std::env::split_paths(&path_var)
        .map(|dir| dir.join(program))
        .find(|candidate| candidate.exists())
}

pub fn run_katago_analysis_once(
    spec: &CommandSpec,
    query_jsonl: &str,
    timeout: Duration,
) -> Result<AnalysisRunResult, EngineManagerError> {
    validate_command_spec(spec)?;

    let mut command = Command::new(&spec.program);
    command
        .args(&spec.args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(working_dir) = spec.working_dir.as_ref().filter(|value| !value.trim().is_empty()) {
        command.current_dir(working_dir);
    }
    for (key, value) in &spec.env {
        command.env(key, value);
    }

    let mut child = command.spawn().map_err(|source| EngineManagerError::Spawn {
        program: spec.program.clone(),
        source,
    })?;

    let stdout = child
        .stdout
        .take()
        .expect("stdout is piped before spawning the engine");
    let stderr = child
        .stderr
        .take()
        .expect("stderr is piped before spawning the engine");
    let stdout_rx = spawn_stdout_reader(stdout);
    let stderr_rx = spawn_stderr_reader(stderr);

    if let Err(source) = write_query(&mut child, query_jsonl) {
        let _ = child.kill();
        let exit_code = child.wait().ok().and_then(|status| status.code());
        let stderr = receive_stderr(stderr_rx);
        return Err(EngineManagerError::StdinWrite {
            source,
            exit_code,
            stderr,
        });
    }

    let deadline = Instant::now() + timeout;
    let mut stdout = None;
    let status = loop {
        if stdout.is_none() {
            match stdout_rx.try_recv() {
                Ok(Ok(Some(line))) => stdout = Some(line),
                Ok(Ok(None)) => {
                    let status = wait_until_deadline(&mut child, deadline, timeout)?;
                    let stderr = receive_stderr(stderr_rx);
                    if !status.success() {
                        return Err(EngineManagerError::NonZeroExit {
                            exit_code: status.code(),
                            stdout: None,
                            stderr,
                        });
                    }
                    return Err(EngineManagerError::MissingStdout {
                        exit_code: status.code(),
                        stderr,
                    });
                }
                Ok(Err(source)) => {
                    let _ = child.kill();
                    let exit_code = child.wait().ok().and_then(|status| status.code());
                    let stderr = receive_stderr(stderr_rx);
                    return Err(EngineManagerError::StdoutRead {
                        source,
                        exit_code,
                        stderr,
                    });
                }
                Err(mpsc::TryRecvError::Empty) => {}
                Err(mpsc::TryRecvError::Disconnected) => {
                    let status = wait_until_deadline(&mut child, deadline, timeout)?;
                    let stderr = receive_stderr(stderr_rx);
                    if !status.success() {
                        return Err(EngineManagerError::NonZeroExit {
                            exit_code: status.code(),
                            stdout: None,
                            stderr,
                        });
                    }
                    return Err(EngineManagerError::MissingStdout {
                        exit_code: status.code(),
                        stderr,
                    });
                }
            }
        }

        if let Some(status) = child
            .try_wait()
            .map_err(|source| EngineManagerError::Wait { source })?
        {
            break status;
        }

        if Instant::now() >= deadline {
            let exit_code = kill_timed_out_child(&mut child)
                .ok()
                .and_then(|status| status.code());
            let stderr = receive_stderr(stderr_rx);
            return Err(EngineManagerError::Timeout {
                timeout_ms: timeout.as_millis(),
                exit_code,
                stdout,
                stderr,
            });
        }

        thread::sleep(Duration::from_millis(10));
    };

    let stdout = match stdout {
        Some(line) => Some(line),
        None => match stdout_rx.recv_timeout(Duration::from_secs(1)) {
            Ok(Ok(Some(line))) => Some(line),
            Ok(Ok(None)) | Err(_) => None,
            Ok(Err(source)) => {
                return Err(EngineManagerError::StdoutRead {
                    source,
                    exit_code: status.code(),
                    stderr: receive_stderr(stderr_rx),
                })
            }
        },
    };
    let stderr = receive_stderr(stderr_rx);

    if !status.success() {
        return Err(EngineManagerError::NonZeroExit {
            exit_code: status.code(),
            stdout,
            stderr,
        });
    }

    match stdout {
        Some(response_jsonl) => Ok(AnalysisRunResult {
            response_jsonl,
            stderr,
            exit_code: status.code(),
        }),
        None => Err(EngineManagerError::MissingStdout {
            exit_code: status.code(),
            stderr,
        }),
    }
}

fn validate_command_spec(spec: &CommandSpec) -> Result<(), EngineManagerError> {
    if spec.program.trim().is_empty() {
        return Err(EngineManagerError::MissingEnginePath);
    }

    if should_preflight_program_path(&spec.program) && !Path::new(&spec.program).exists() {
        return Err(EngineManagerError::EnginePathNotFound {
            path: spec.program.clone(),
        });
    }

    if let Some(working_dir) = spec.working_dir.as_ref().filter(|value| !value.trim().is_empty()) {
        if !Path::new(working_dir).is_dir() {
            return Err(EngineManagerError::WorkingDirNotFound {
                path: working_dir.clone(),
            });
        }
    }

    Ok(())
}

fn should_preflight_program_path(program: &str) -> bool {
    let path = Path::new(program);
    path.is_absolute() || program.contains('/') || program.contains('\\')
}

fn build_process_command(spec: &CommandSpec) -> Command {
    let mut command = Command::new(&spec.program);
    command
        .args(&spec.args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(working_dir) = spec.working_dir.as_ref().filter(|value| !value.trim().is_empty()) {
        command.current_dir(working_dir);
    }
    for (key, value) in &spec.env {
        command.env(key, value);
    }

    command
}

fn write_query(child: &mut Child, query_jsonl: &str) -> io::Result<()> {
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(query_jsonl.as_bytes())?;
        if !query_jsonl.ends_with('\n') {
            stdin.write_all(b"\n")?;
        }
        stdin.flush()?;
    }
    Ok(())
}

fn spawn_stdout_reader(stdout: std::process::ChildStdout) -> Receiver<io::Result<Option<String>>> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        let result = reader.read_line(&mut line).map(|bytes| {
            if bytes == 0 {
                None
            } else {
                Some(trim_line_ending(line))
            }
        });
        let _ = tx.send(result);
    });
    rx
}

fn spawn_stdout_lines_reader(stdout: std::process::ChildStdout) -> Receiver<io::Result<Option<String>>> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        loop {
            let mut line = String::new();
            match reader.read_line(&mut line) {
                Ok(0) => {
                    let _ = tx.send(Ok(None));
                    break;
                }
                Ok(_) => {
                    if tx.send(Ok(Some(trim_line_ending(line)))).is_err() {
                        break;
                    }
                }
                Err(error) => {
                    let _ = tx.send(Err(error));
                    break;
                }
            }
        }
    });
    rx
}

fn spawn_stderr_reader(stderr: std::process::ChildStderr) -> Receiver<io::Result<String>> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let mut reader = BufReader::new(stderr);
        let mut output = String::new();
        let result = reader.read_to_string(&mut output).map(|_| output);
        let _ = tx.send(result);
    });
    rx
}

fn trim_line_ending(mut line: String) -> String {
    if line.ends_with('\n') {
        line.pop();
        if line.ends_with('\r') {
            line.pop();
        }
    }
    line
}

enum BatchStdoutEventError {
    NoLineReady,
    Read(io::Error),
}

fn receive_available_stdout_line(
    rx: &Receiver<io::Result<Option<String>>>,
) -> Result<Option<String>, BatchStdoutEventError> {
    match rx.try_recv() {
        Ok(Ok(line)) => Ok(line),
        Ok(Err(error)) => Err(BatchStdoutEventError::Read(error)),
        Err(mpsc::TryRecvError::Empty) => Err(BatchStdoutEventError::NoLineReady),
        Err(mpsc::TryRecvError::Disconnected) => Ok(None),
    }
}

fn collect_remaining_stdout(
    rx: &Receiver<io::Result<Option<String>>>,
    response_lines: &mut Vec<String>,
    exit_code: Option<i32>,
    stderr_rx: &Receiver<io::Result<String>>,
    options: &mut AnalysisBatchRunOptions<'_>,
) -> Result<(), EngineManagerError> {
    loop {
        match rx.recv_timeout(Duration::from_secs(1)) {
            Ok(Ok(Some(line))) => push_batch_response_line(response_lines, line, options),
            Ok(Ok(None)) | Err(_) => return Ok(()),
            Ok(Err(source)) => {
                return Err(EngineManagerError::StdoutRead {
                    source,
                    exit_code,
                    stderr: receive_stderr_ref(stderr_rx),
                });
            }
        }
    }
}

fn wait_until_deadline(
    child: &mut Child,
    deadline: Instant,
    timeout: Duration,
) -> Result<ExitStatus, EngineManagerError> {
    loop {
        if let Some(status) = child
            .try_wait()
            .map_err(|source| EngineManagerError::Wait { source })?
        {
            return Ok(status);
        }

        if Instant::now() >= deadline {
            let exit_code = kill_timed_out_child(child).ok().and_then(|status| status.code());
            return Err(EngineManagerError::Timeout {
                timeout_ms: timeout.as_millis(),
                exit_code,
                stdout: None,
                stderr: String::new(),
            });
        }

        thread::sleep(Duration::from_millis(10));
    }
}

fn wait_for_batch_exit(
    child: &mut Child,
    deadline: Instant,
    timeout: Duration,
    response_lines: &[String],
    stderr_rx: &Receiver<io::Result<String>>,
    options: &AnalysisBatchRunOptions<'_>,
) -> Result<ExitStatus, EngineManagerError> {
    loop {
        if is_cancelled(options) {
            let exit_code = kill_cancelled_child(child).ok().and_then(|status| status.code());
            return Err(EngineManagerError::Cancelled {
                received_responses: response_lines.len(),
                stdout: response_lines.to_vec(),
                exit_code,
                stderr: receive_stderr_ref(stderr_rx),
            });
        }

        if let Some(status) = child
            .try_wait()
            .map_err(|source| EngineManagerError::Wait { source })?
        {
            return Ok(status);
        }

        if Instant::now() >= deadline {
            let exit_code = kill_timed_out_child(child).ok().and_then(|status| status.code());
            return Err(EngineManagerError::Timeout {
                timeout_ms: timeout.as_millis(),
                exit_code,
                stdout: stdout_summary(response_lines),
                stderr: receive_stderr_ref(stderr_rx),
            });
        }

        thread::sleep(Duration::from_millis(10));
    }
}

fn is_cancelled(options: &AnalysisBatchRunOptions<'_>) -> bool {
    options
        .cancel_token
        .map(AnalysisCancelToken::is_cancelled)
        .unwrap_or(false)
}

fn push_batch_response_line(
    response_lines: &mut Vec<String>,
    line: String,
    options: &mut AnalysisBatchRunOptions<'_>,
) {
    let response_index = response_lines.len() + 1;
    if response_index <= options.expected_responses {
        if let Some(on_progress) = options.on_progress.as_deref_mut() {
            on_progress(AnalysisBatchProgress {
                response_index,
                expected_responses: options.expected_responses,
                response_jsonl_line: line.clone(),
            });
        }
    }
    response_lines.push(line);
}

fn kill_timed_out_child(child: &mut Child) -> io::Result<ExitStatus> {
    match child.kill() {
        Ok(()) => child.wait(),
        Err(error) if error.kind() == io::ErrorKind::InvalidInput => child.wait(),
        Err(error) => Err(error),
    }
}

fn kill_cancelled_child(child: &mut Child) -> io::Result<ExitStatus> {
    kill_timed_out_child(child)
}

fn receive_stderr(rx: Receiver<io::Result<String>>) -> String {
    receive_stderr_ref(&rx)
}

fn receive_stderr_ref(rx: &Receiver<io::Result<String>>) -> String {
    match rx.recv_timeout(Duration::from_secs(5)) {
        Ok(Ok(stderr)) => stderr,
        Ok(Err(error)) => format!("<failed to read stderr: {error}>"),
        Err(_) => String::new(),
    }
}

fn stdout_summary(lines: &[String]) -> Option<String> {
    if lines.is_empty() {
        None
    } else {
        Some(lines.join("\n"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::{Path, PathBuf};
    use std::sync::atomic::{AtomicU64, Ordering as AtomicOrdering};

    static NEXT_TEST_TEMP_ID: AtomicU64 = AtomicU64::new(0);

    struct TestTempDir {
        path: PathBuf,
    }

    impl TestTempDir {
        fn new(label: &str) -> Self {
            let unique = format!(
                "{}-{}-{}",
                std::process::id(),
                NEXT_TEST_TEMP_ID.fetch_add(1, AtomicOrdering::Relaxed),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            );
            let path = std::env::temp_dir()
                .join("lizzieyzy-engine-manager-tests")
                .join(format!("{label}-{unique}"));
            std::fs::create_dir_all(&path).unwrap();
            Self { path }
        }

        fn path(&self) -> &Path {
            &self.path
        }
    }

    impl Drop for TestTempDir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.path);
        }
    }

    #[cfg(unix)]
    fn fake_engine_spec(temp_dir: &TestTempDir, script: &str) -> CommandSpec {
        let script_path = temp_dir.path().join("fake-engine.sh");
        std::fs::write(&script_path, format!("#!/bin/sh\n{script}\n")).unwrap();

        CommandSpec {
            program: "/bin/sh".into(),
            args: vec![script_path.to_string_lossy().into_owned()],
            working_dir: None,
            env: vec![],
        }
    }

    #[test]
    fn check_assets_resolves_relative_engine_model_and_config_under_working_dir() {
        let temp_dir = TestTempDir::new("assets");
        let working_dir = temp_dir.path();
        let engine_path = "bin/katago".to_string();
        std::fs::create_dir_all(working_dir.join("models")).unwrap();
        std::fs::create_dir_all(working_dir.join("configs")).unwrap();
        std::fs::create_dir_all(working_dir.join("bin")).unwrap();
        std::fs::write(working_dir.join(&engine_path), "").unwrap();
        std::fs::write(working_dir.join("models").join("model.bin"), "").unwrap();
        std::fs::write(working_dir.join("configs").join("analysis.cfg"), "").unwrap();

        let profile = EngineProfileDto {
            name: "test profile".into(),
            engine_path: engine_path.clone(),
            model_path: Some("models/model.bin".into()),
            config_path: Some("configs/analysis.cfg".into()),
            working_dir: Some(working_dir.to_string_lossy().into_owned()),
            backend: EngineBackend::KataGoAnalysis,
        };

        let checks = check_assets(&profile);

        assert_eq!(checks[0].path, working_dir.join(engine_path).to_string_lossy());
        assert_eq!(checks[1].path, working_dir.to_string_lossy());
        assert_eq!(
            checks[2].path,
            working_dir.join("models").join("model.bin").to_string_lossy()
        );
        assert_eq!(
            checks[3].path,
            working_dir.join("configs").join("analysis.cfg").to_string_lossy()
        );
        assert!(checks[0].exists);
        assert!(checks[1].exists);
        assert!(checks[2].exists);
        assert!(checks[3].exists);
    }

    #[test]
    fn check_assets_reports_empty_model_and_config_paths_as_missing() {
        let temp_dir = TestTempDir::new("empty-assets");
        let working_dir = temp_dir.path();

        let profile = EngineProfileDto {
            name: "test profile".into(),
            engine_path: "katago".into(),
            model_path: Some("".into()),
            config_path: Some("   ".into()),
            working_dir: Some(working_dir.to_string_lossy().into_owned()),
            backend: EngineBackend::KataGoAnalysis,
        };

        let checks = check_assets(&profile);

        assert_eq!(checks[2].path, "");
        assert_eq!(checks[3].path, "");
        assert!(!checks[2].exists);
        assert!(!checks[3].exists);
        assert!(checks[2].required);
        assert!(checks[3].required);
    }

    #[test]
    fn check_assets_reports_none_model_and_config_paths_as_missing_for_katago_analysis() {
        let temp_dir = TestTempDir::new("none-assets");
        let working_dir = temp_dir.path();
        let engine_path = working_dir.join("katago");
        std::fs::write(&engine_path, "").unwrap();

        let profile = EngineProfileDto {
            name: "test profile".into(),
            engine_path: engine_path.to_string_lossy().into_owned(),
            model_path: None,
            config_path: None,
            working_dir: Some(working_dir.to_string_lossy().into_owned()),
            backend: EngineBackend::KataGoAnalysis,
        };

        let checks = check_assets(&profile);

        assert_eq!(checks.len(), 4);
        assert_eq!(checks[0].label, "engine binary");
        assert!(checks[0].exists);
        assert!(checks[0].required);
        assert_eq!(checks[1].label, "working directory");
        assert!(checks[1].exists);
        assert!(checks[1].required);
        assert_eq!(checks[2].label, "model");
        assert_eq!(checks[2].path, "");
        assert!(!checks[2].exists);
        assert!(checks[2].required);
        assert_eq!(checks[3].label, "config");
        assert_eq!(checks[3].path, "");
        assert!(!checks[3].exists);
        assert!(checks[3].required);
    }

    #[test]
    fn build_command_spec_resolves_relative_katago_assets_under_working_dir() {
        let temp_dir = TestTempDir::new("command-spec-assets");
        let working_dir = temp_dir.path();
        std::fs::create_dir_all(working_dir.join("bin")).unwrap();
        std::fs::create_dir_all(working_dir.join("models")).unwrap();
        std::fs::create_dir_all(working_dir.join("configs")).unwrap();
        std::fs::write(working_dir.join("bin").join("katago"), "").unwrap();
        std::fs::write(working_dir.join("models").join("model.bin"), "").unwrap();
        std::fs::write(working_dir.join("configs").join("analysis.cfg"), "").unwrap();

        let profile = EngineProfileDto {
            name: "test profile".into(),
            engine_path: "bin/katago".into(),
            model_path: Some("models/model.bin".into()),
            config_path: Some("configs/analysis.cfg".into()),
            working_dir: Some(working_dir.to_string_lossy().into_owned()),
            backend: EngineBackend::KataGoAnalysis,
        };

        let spec = build_command_spec(&profile).unwrap();

        assert_eq!(
            spec.program,
            working_dir.join("bin").join("katago").to_string_lossy()
        );
        assert_eq!(spec.working_dir.as_deref(), Some(working_dir.to_str().unwrap()));
        assert_eq!(
            spec.args,
            vec![
                "analysis",
                "-config",
                working_dir.join("configs").join("analysis.cfg").to_str().unwrap(),
                "-model",
                working_dir.join("models").join("model.bin").to_str().unwrap(),
            ]
        );
    }

    #[test]
    fn build_command_spec_reports_missing_model_path() {
        let temp_dir = TestTempDir::new("missing-model");
        let working_dir = temp_dir.path();
        std::fs::write(working_dir.join("analysis.cfg"), "").unwrap();

        let profile = EngineProfileDto {
            name: "test profile".into(),
            engine_path: "katago".into(),
            model_path: Some("missing.bin".into()),
            config_path: Some("analysis.cfg".into()),
            working_dir: Some(working_dir.to_string_lossy().into_owned()),
            backend: EngineBackend::KataGoAnalysis,
        };

        let err = build_command_spec(&profile).unwrap_err();

        assert!(matches!(err, EngineManagerError::ModelPathNotFound { .. }));
    }

    #[test]
    #[cfg(unix)]
    fn analysis_once_reads_one_json_response() {
        let temp_dir = TestTempDir::new("analysis-once");
        let spec = fake_engine_spec(
            &temp_dir,
            r#"read line; printf '{"id":"ok"}\n'; printf 'debug line\n' >&2"#,
        );

        let result = run_katago_analysis_once(&spec, r#"{"id":"query"}"#, Duration::from_secs(2)).unwrap();

        assert_eq!(result.response_jsonl, r#"{"id":"ok"}"#);
        assert_eq!(result.exit_code, Some(0));
        assert!(result.stderr.contains("debug line"));
    }

    #[test]
    #[cfg(unix)]
    fn analysis_batch_reads_multiple_json_responses() {
        let temp_dir = TestTempDir::new("batch-multiple");
        let spec = fake_engine_spec(
            &temp_dir,
            r#"read line; printf '{"id":"batch-1","turnNumber":0}\n'; printf '{"id":"batch-1","turnNumber":1}\n'; printf 'batch debug\n' >&2"#,
        );

        let result =
            run_katago_analysis_batch(&spec, r#"{"id":"query"}"#, 2, Duration::from_secs(2)).unwrap();

        assert_eq!(
            result.response_jsonl_lines,
            vec![
                r#"{"id":"batch-1","turnNumber":0}"#,
                r#"{"id":"batch-1","turnNumber":1}"#
            ]
        );
        assert_eq!(result.exit_code, Some(0));
        assert!(result.stderr.contains("batch debug"));
    }

    #[test]
    #[cfg(unix)]
    fn analysis_batch_with_options_reports_progress_for_each_expected_response() {
        let temp_dir = TestTempDir::new("batch-progress");
        let spec = fake_engine_spec(
            &temp_dir,
            r#"read line; printf '{"id":"batch-1","turnNumber":0}\n'; printf '{"id":"batch-1","turnNumber":1}\n'"#,
        );
        let mut progress = Vec::new();
        let mut on_progress = |event: AnalysisBatchProgress| progress.push(event);

        let result = run_katago_analysis_batch_with_options(
            &spec,
            r#"{"id":"query"}"#,
            AnalysisBatchRunOptions {
                expected_responses: 2,
                timeout: Duration::from_secs(2),
                cancel_token: None,
                on_progress: Some(&mut on_progress),
            },
        )
        .unwrap();

        assert_eq!(result.response_jsonl_lines.len(), 2);
        assert_eq!(progress.len(), 2);
        assert_eq!(progress[0].response_index, 1);
        assert_eq!(progress[0].expected_responses, 2);
        assert_eq!(
            progress[0].response_jsonl_line,
            r#"{"id":"batch-1","turnNumber":0}"#
        );
        assert_eq!(progress[1].response_index, 2);
        assert_eq!(
            progress[1].response_jsonl_line,
            r#"{"id":"batch-1","turnNumber":1}"#
        );
    }

    #[test]
    #[cfg(unix)]
    fn analysis_batch_cancel_token_kills_process_and_returns_partial_stdout() {
        let temp_dir = TestTempDir::new("cancel-batch");
        let marker = temp_dir.path().join("marker");
        let mut spec = fake_engine_spec(
            &temp_dir,
            r#"read line; printf '{"id":"batch-1","turnNumber":0}\n'; sleep 2; printf survived > "$MARKER""#,
        );
        spec.env
            .push(("MARKER".into(), marker.to_string_lossy().into_owned()));
        let cancel_token = AnalysisCancelToken::new();
        let callback_token = cancel_token.clone();
        let mut on_progress = move |_event: AnalysisBatchProgress| callback_token.cancel();

        let error = run_katago_analysis_batch_with_options(
            &spec,
            r#"{"id":"query"}"#,
            AnalysisBatchRunOptions {
                expected_responses: 2,
                timeout: Duration::from_secs(5),
                cancel_token: Some(&cancel_token),
                on_progress: Some(&mut on_progress),
            },
        )
        .unwrap_err();

        match error {
            EngineManagerError::Cancelled {
                received_responses,
                stdout,
                ..
            } => {
                assert_eq!(received_responses, 1);
                assert_eq!(stdout, vec![r#"{"id":"batch-1","turnNumber":0}"#]);
            }
            other => panic!("unexpected error: {other:?}"),
        }
        assert!(!marker.exists());
    }

    #[test]
    #[cfg(unix)]
    fn analysis_batch_returns_katago_error_json_as_stdout() {
        let temp_dir = TestTempDir::new("batch-error-json");
        let spec = fake_engine_spec(
            &temp_dir,
            r#"read line; printf '{"id":"batch-1","error":"bad query"}\n'"#,
        );

        let result =
            run_katago_analysis_batch(&spec, r#"{"id":"query"}"#, 1, Duration::from_secs(2)).unwrap();

        assert_eq!(
            result.response_jsonl_lines,
            vec![r#"{"id":"batch-1","error":"bad query"}"#]
        );
        assert_eq!(result.exit_code, Some(0));
    }

    #[test]
    #[cfg(unix)]
    fn analysis_batch_truncates_stdout_to_expected_responses() {
        let temp_dir = TestTempDir::new("batch-truncate");
        let spec = fake_engine_spec(
            &temp_dir,
            r#"read line; printf '{"id":"batch-1","turnNumber":0}\n'; printf '{"id":"batch-1","turnNumber":1}\n'; printf '{"id":"batch-1","turnNumber":2}\n'"#,
        );

        let result =
            run_katago_analysis_batch(&spec, r#"{"id":"query"}"#, 2, Duration::from_secs(2)).unwrap();

        assert_eq!(
            result.response_jsonl_lines,
            vec![
                r#"{"id":"batch-1","turnNumber":0}"#,
                r#"{"id":"batch-1","turnNumber":1}"#
            ]
        );
        assert_eq!(result.exit_code, Some(0));
    }

    #[test]
    #[cfg(unix)]
    fn analysis_batch_with_zero_expected_responses_returns_empty_without_spawning() {
        let temp_dir = TestTempDir::new("zero-batch");
        let marker = temp_dir.path().join("marker");
        let mut spec = fake_engine_spec(&temp_dir, r#"printf launched > "$MARKER"; exit 99"#);
        spec.env
            .push(("MARKER".into(), marker.to_string_lossy().into_owned()));

        let result =
            run_katago_analysis_batch(&spec, r#"{"id":"query"}"#, 0, Duration::from_secs(2)).unwrap();

        assert!(result.response_jsonl_lines.is_empty());
        assert_eq!(result.stderr, "");
        assert_eq!(result.exit_code, None);
        assert!(!marker.exists());
    }

    #[test]
    #[cfg(unix)]
    fn analysis_batch_reports_insufficient_stdout() {
        let temp_dir = TestTempDir::new("batch-insufficient");
        let spec = fake_engine_spec(&temp_dir, r#"read line; printf '{"id":"only"}\n'"#);

        let error =
            run_katago_analysis_batch(&spec, r#"{"id":"query"}"#, 2, Duration::from_secs(2)).unwrap_err();

        match error {
            EngineManagerError::InsufficientStdout {
                expected_responses,
                received_responses,
                stdout,
                exit_code,
                ..
            } => {
                assert_eq!(expected_responses, 2);
                assert_eq!(received_responses, 1);
                assert_eq!(stdout, vec![r#"{"id":"only"}"#]);
                assert_eq!(exit_code, Some(0));
            }
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    #[cfg(unix)]
    fn analysis_batch_non_zero_exit_includes_stderr() {
        let temp_dir = TestTempDir::new("batch-non-zero");
        let spec = fake_engine_spec(&temp_dir, "read line; printf 'bad batch\\n' >&2; exit 7");

        let error = run_katago_analysis_batch(&spec, "{}", 1, Duration::from_secs(2)).unwrap_err();

        match error {
            EngineManagerError::NonZeroExit {
                exit_code, stderr, ..
            } => {
                assert_eq!(exit_code, Some(7));
                assert!(stderr.contains("bad batch"));
            }
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    #[cfg(unix)]
    fn analysis_batch_timeout_kills_process() {
        let temp_dir = TestTempDir::new("timeout-batch");
        let marker = temp_dir.path().join("marker");
        let mut spec = fake_engine_spec(&temp_dir, r#"read line; sleep 2; printf survived > "$MARKER""#);
        spec.env
            .push(("MARKER".into(), marker.to_string_lossy().into_owned()));

        let error = run_katago_analysis_batch(&spec, "{}", 1, Duration::from_millis(100)).unwrap_err();

        assert!(matches!(error, EngineManagerError::Timeout { .. }));
        assert!(!marker.exists());
    }

    #[test]
    fn missing_engine_path_is_reported_before_spawn() {
        let temp_dir = TestTempDir::new("missing");
        let path = temp_dir.path().join("katago");
        let spec = CommandSpec {
            program: path.to_string_lossy().into_owned(),
            args: vec![],
            working_dir: None,
            env: vec![],
        };

        let error = run_katago_analysis_once(&spec, "{}", Duration::from_secs(1)).unwrap_err();

        assert!(matches!(error, EngineManagerError::EnginePathNotFound { .. }));
    }

    #[test]
    #[cfg(unix)]
    fn non_zero_exit_includes_stderr() {
        let temp_dir = TestTempDir::new("non-zero");
        let spec = fake_engine_spec(&temp_dir, "read line; printf 'bad news\\n' >&2; exit 7");

        let error = run_katago_analysis_once(&spec, "{}", Duration::from_secs(2)).unwrap_err();

        match error {
            EngineManagerError::NonZeroExit {
                exit_code, stderr, ..
            } => {
                assert_eq!(exit_code, Some(7));
                assert!(stderr.contains("bad news"));
            }
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    #[cfg(unix)]
    fn timeout_kills_process() {
        let temp_dir = TestTempDir::new("timeout");
        let spec = fake_engine_spec(&temp_dir, "sleep 2");

        let error = run_katago_analysis_once(&spec, "{}", Duration::from_millis(100)).unwrap_err();

        assert!(matches!(error, EngineManagerError::Timeout { .. }));
    }
}
