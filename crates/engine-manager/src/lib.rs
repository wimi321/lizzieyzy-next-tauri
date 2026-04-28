use app_model::{EngineBackend, EngineProfileDto};
use serde::{Deserialize, Serialize};
use std::path::Path;
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
#[derive(Debug, Error)]
pub enum EngineManagerError {
    #[error("engine path is required")]
    MissingEnginePath,
    #[error("model path is required for KataGo analysis")]
    MissingModelPath,
    #[error("config path is required for KataGo analysis")]
    MissingConfigPath,
}

pub fn build_command_spec(profile: &EngineProfileDto) -> Result<CommandSpec, EngineManagerError> {
    if profile.engine_path.trim().is_empty() {
        return Err(EngineManagerError::MissingEnginePath);
    }
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
            Ok(CommandSpec {
                program: profile.engine_path.clone(),
                args: vec![
                    "analysis".into(),
                    "-config".into(),
                    config.clone(),
                    "-model".into(),
                    model.clone(),
                ],
                working_dir: profile.working_dir.clone(),
                env: vec![],
            })
        }
        EngineBackend::KataGoGtp => Ok(CommandSpec {
            program: profile.engine_path.clone(),
            args: vec!["gtp".into()],
            working_dir: profile.working_dir.clone(),
            env: vec![],
        }),
        EngineBackend::GenericGtp | EngineBackend::ReadboardSidecar => Ok(CommandSpec {
            program: profile.engine_path.clone(),
            args: vec![],
            working_dir: profile.working_dir.clone(),
            env: vec![],
        }),
    }
}

pub fn check_assets(profile: &EngineProfileDto) -> Vec<AssetCheck> {
    let mut checks = vec![AssetCheck {
        path: profile.engine_path.clone(),
        exists: Path::new(&profile.engine_path).exists(),
        required: true,
        label: "engine binary".into(),
    }];
    if let Some(model) = &profile.model_path {
        checks.push(AssetCheck {
            path: model.clone(),
            exists: Path::new(model).exists(),
            required: matches!(profile.backend, EngineBackend::KataGoAnalysis),
            label: "model".into(),
        });
    }
    if let Some(config) = &profile.config_path {
        checks.push(AssetCheck {
            path: config.clone(),
            exists: Path::new(config).exists(),
            required: matches!(profile.backend, EngineBackend::KataGoAnalysis),
            label: "config".into(),
        });
    }
    checks
}
