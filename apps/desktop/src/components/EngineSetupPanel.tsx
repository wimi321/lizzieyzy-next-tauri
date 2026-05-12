import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { openUrl } from "@tauri-apps/plugin-opener";
import { checkEngineAssets, installedAppRuntimeProof, loadEngineProfilesSettings, saveEngineProfilesSettings, validateRuntimeAssetLayout } from "../api/backend";
import type { InstalledAppRuntimeProofDto, RuntimeAssetValidationDto } from "../api/backend";
import type { AssetCheckDto, EngineProfileDto, EngineProfileRecordDto, InstalledAppBundledKataGoProofDto } from "../domain/types";

const katagoSetupLinks = {
  releases: "https://github.com/lightvector/KataGo/releases",
  networks: "https://katagotraining.org/networks/",
  configs: "https://github.com/lightvector/KataGo/tree/master/cpp/configs"
} as const;

type Props = {
  disabled?: boolean;
  onRun: (profile: EngineProfileDto, maxVisits: number) => void | Promise<void>;
  onAnalyzeGame: (profile: EngineProfileDto, maxVisits: number) => void | Promise<void>;
  onCancelAnalysis?: () => void | Promise<void>;
  analysisProgress?: { completed: number; expected: number; turn: number; responseJsonl: string } | null;
  activeJobId?: string | null;
  reviewWorkflow?: {
    phase: string;
    source: string;
    message: string;
    sessionToken: string;
    activeJobId: string | null;
    completed: number;
    expected: number;
    currentTurn: number | null;
    progressVerified: boolean;
    cancelVerified: boolean;
    restartAfterCancelVerified: boolean;
    cacheRestoreVerified: boolean;
    engineFailureVerified: boolean;
    staleAnalysisPrevented: boolean;
  };
};

export function EngineSetupPanel({ disabled = false, onRun, onAnalyzeGame, onCancelAnalysis, analysisProgress = null, activeJobId = null, reviewWorkflow }: Props) {
  const [profiles, setProfiles] = useState<EngineProfileRecordDto[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("default");
  const [profileName, setProfileName] = useState("Local KataGo");
  const [enginePath, setEnginePath] = useState("");
  const [modelPath, setModelPath] = useState("");
  const [configPath, setConfigPath] = useState("");
  const [workingDir, setWorkingDir] = useState("");
  const [maxVisits, setMaxVisits] = useState("800");
  const [profileStatus, setProfileStatus] = useState("Loading profile...");
  const [assetChecks, setAssetChecks] = useState<AssetCheckDto[]>([]);
  const [runtimeAssetValidation, setRuntimeAssetValidation] = useState<RuntimeAssetValidationDto | null>(null);
  const [runtimeAssetStatus, setRuntimeAssetStatus] = useState("Checking bundled/runtime assets...");
  const [installedRuntimeProof, setInstalledRuntimeProof] = useState<InstalledAppRuntimeProofDto | null>(null);
  const [installedRuntimeProofStatus, setInstalledRuntimeProofStatus] = useState("Checking installed app launch proof...");

  const visits = Number(maxVisits);
  const isAnalysisActive = activeJobId !== null;
  const missingRequiredAssets = assetChecks.filter((check) => check.required && !check.exists);
  const hasKnownMissingRequiredAssets = missingRequiredAssets.length > 0;
  const progressLabel = analysisProgress
    ? `${analysisProgress.completed}/${analysisProgress.expected || "?"} positions, move ${analysisProgress.turn}`
    : isAnalysisActive
      ? "Starting analysis..."
      : "";
  const progressPercent = analysisProgress && analysisProgress.expected > 0
    ? Math.min(100, Math.round((analysisProgress.completed / analysisProgress.expected) * 100))
    : 0;
  const canRun =
    !disabled &&
    enginePath.trim().length > 0 &&
    modelPath.trim().length > 0 &&
    configPath.trim().length > 0 &&
    Number.isFinite(visits) &&
    visits > 0 &&
    !hasKnownMissingRequiredAssets;
  const canSave = profileName.trim().length > 0 && Number.isFinite(visits) && visits > 0;
  const canDeleteProfile = selectedProfileId !== "default" && profiles.length > 1;
  const localAssetCheckStatus = assetChecks.length === 0
    ? "not-checked"
    : hasKnownMissingRequiredAssets
      ? "missing-required"
      : "ready";
  const runtimeAssetCheckStatus = runtimeAssetValidation
    ? runtimeAssetValidation.placeholders.length > 0 || runtimeAssetValidation.missing.length > 0
      ? "problems"
      : runtimeAssetValidation.layout.candidates.length > 0
        ? "ready"
        : "unavailable"
    : runtimeAssetStatus.startsWith("Runtime asset check failed")
      ? "error"
      : "checking";
  const selectedProfile = profiles.find((profile) => profile.id === selectedProfileId) ?? null;
  const installedRuntimeSummary = installedRuntimeProof ? summarizeInstalledRuntimeProof(installedRuntimeProof) : null;
  const bundledProfileProof = installedRuntimeProof ? extractBundledKataGoProof(installedRuntimeProof) : null;
  const bundledProfile = bundledProfileProof ? validBundledProfile(bundledProfileProof.profile) : null;
  const canUseBundledProfile = !disabled && bundledProfile !== null;
  const bundledProfileStatus = bundledProfile
    ? "Bundled KataGo profile available."
    : bundledProfileProof
      ? "Bundled KataGo profile unavailable; configure local KataGo assets below."
      : "Bundled KataGo profile unavailable; installed runtime assets were not reported.";
  const installedProofStatus = installedRuntimeSummary?.proofStatus
    ?? (installedRuntimeProofStatus.startsWith("Checking") ? "checking" : classifyInstalledProofMessage(installedRuntimeProofStatus));

  useEffect(() => {
    let isMounted = true;
    loadEngineProfilesSettings()
      .then((settings) => {
        if (!isMounted) return;
        const selected = settings.profiles.find((profile) => profile.id === settings.selected_profile_id) ?? settings.profiles[0];
        setProfiles(settings.profiles);
        setSelectedProfileId(selected?.id ?? "default");
        if (!selected) {
          setProfileStatus("Default profile ready.");
          return;
        }
        applyProfileRecord(selected);
        setProfileStatus(settings.profiles.length > 1 ? "Profiles loaded." : "Profile loaded.");
      })
      .catch((error: unknown) => {
        if (isMounted) setProfileStatus(`Load failed: ${errorMessage(error)}`);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    validateRuntimeAssetLayout()
      .then((validation) => {
        if (!isMounted) return;
        setRuntimeAssetValidation(validation);
        setRuntimeAssetStatus(runtimeAssetSummary(validation));
      })
      .catch((error: unknown) => {
        if (isMounted) setRuntimeAssetStatus(`Runtime asset check failed: ${errorMessage(error)}`);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    refreshInstalledRuntimeProof(() => isMounted);
    return () => {
      isMounted = false;
    };
  }, []);

  function applyProfileRecord(record: EngineProfileRecordDto) {
    setProfileName(record.profile.name);
    setEnginePath(record.profile.engine_path);
    setModelPath(record.profile.model_path ?? "");
    setConfigPath(record.profile.config_path ?? "");
    setWorkingDir(record.profile.working_dir ?? "");
    setMaxVisits(String(record.max_visits));
    setAssetChecks([]);
  }

  function buildProfile(): EngineProfileDto {
    return {
      name: profileName.trim() || "Local KataGo",
      engine_path: enginePath.trim(),
      model_path: optionalPath(modelPath),
      config_path: optionalPath(configPath),
      working_dir: optionalPath(workingDir),
      backend: "kata_go_analysis"
    };
  }

  function buildProfileRecord(id = selectedProfileId): EngineProfileRecordDto {
    return {
      id,
      profile: buildProfile(),
      max_visits: Math.floor(visits)
    };
  }

  function updatePath(setter: (value: string) => void, value: string, message?: string) {
    setter(value);
    if (assetChecks.length > 0) {
      setAssetChecks([]);
      setProfileStatus("Path changed. Check assets again.");
    } else if (message) {
      setProfileStatus(message);
    }
  }

  async function persistProfiles(nextProfiles: EngineProfileRecordDto[], selectedId: string, successMessage: string) {
    const saved = await saveEngineProfilesSettings({ selected_profile_id: selectedId, profiles: nextProfiles });
    const selected = saved.profiles.find((profile) => profile.id === saved.selected_profile_id) ?? saved.profiles[0];
    setProfiles(saved.profiles);
    setSelectedProfileId(saved.selected_profile_id);
    if (selected) applyProfileRecord(selected);
    setProfileStatus(successMessage);
  }

  async function handleSelectProfile(profileId: string) {
    const profile = profiles.find((item) => item.id === profileId);
    if (!profile) return;
    setSelectedProfileId(profileId);
    applyProfileRecord(profile);
    setProfileStatus(`Selected ${profile.profile.name}.`);
    try {
      await saveEngineProfilesSettings({ selected_profile_id: profileId, profiles });
    } catch (error) {
      setProfileStatus(`Select saved locally but persistence failed: ${errorMessage(error)}`);
    }
  }

  async function handleAddProfile() {
    const id = `profile-${Date.now().toString(36)}`;
    const nextProfile: EngineProfileRecordDto = {
      ...buildProfileRecord(id),
      profile: {
        ...buildProfile(),
        name: nextProfileName(profiles)
      }
    };
    try {
      await persistProfiles([...profiles.map((profile) => profile.id === selectedProfileId ? buildProfileRecord(profile.id) : profile), nextProfile], id, "Profile added.");
    } catch (error) {
      setProfileStatus(`Add failed: ${errorMessage(error)}`);
    }
  }

  async function handleDeleteProfile() {
    if (!canDeleteProfile) return;
    const nextProfiles = profiles.filter((profile) => profile.id !== selectedProfileId);
    const nextSelected = nextProfiles.find((profile) => profile.id === "default")?.id ?? nextProfiles[0]?.id ?? "default";
    try {
      await persistProfiles(nextProfiles, nextSelected, "Profile deleted.");
    } catch (error) {
      setProfileStatus(`Delete failed: ${errorMessage(error)}`);
    }
  }

  async function handlePickPath(label: string, currentValue: string, directory: boolean, setter: (value: string) => void) {
    try {
      const selected = await open({
        title: `Select ${label}`,
        directory,
        multiple: false,
        defaultPath: currentValue.trim() || undefined
      });
      const selectedPath = Array.isArray(selected) ? selected[0] : selected;
      if (!selectedPath) {
        setProfileStatus(`${label} selection canceled.`);
        return;
      }
      updatePath(setter, selectedPath, `${label} selected. Check assets again.`);
    } catch (error) {
      setProfileStatus(`Native picker unavailable: ${errorMessage(error)}`);
    }
  }

  function handleRun() {
    if (hasKnownMissingRequiredAssets) {
      setProfileStatus(assetStatus(assetChecks));
      return;
    }
    if (!canRun) return;
    void onRun(buildProfile(), Math.floor(visits));
  }

  function handleAnalyzeGame() {
    if (hasKnownMissingRequiredAssets) {
      setProfileStatus(assetStatus(assetChecks));
      return;
    }
    if (!canRun) return;
    void onAnalyzeGame(buildProfile(), Math.floor(visits));
  }

  async function handleSaveProfile() {
    if (!canSave) return;
    try {
      const currentRecord = buildProfileRecord(selectedProfileId);
      const nextProfiles = profiles.some((profile) => profile.id === selectedProfileId)
        ? profiles.map((profile) => profile.id === selectedProfileId ? currentRecord : profile)
        : [...profiles, currentRecord];
      await persistProfiles(nextProfiles, selectedProfileId, "Profile saved.");
      setProfileStatus("Profile saved.");
    } catch (error) {
      setProfileStatus(`Save failed: ${errorMessage(error)}`);
    }
  }

  async function handleCheckAssets() {
    try {
      const checks = await checkEngineAssets(buildProfile());
      setAssetChecks(checks);
      setProfileStatus(assetStatus(checks));
    } catch (error) {
      setProfileStatus(`Check failed: ${errorMessage(error)}`);
    }
  }

  async function handleCheckRuntimeAssets() {
    setRuntimeAssetStatus("Checking bundled/runtime assets...");
    try {
      const validation = await validateRuntimeAssetLayout();
      setRuntimeAssetValidation(validation);
      setRuntimeAssetStatus(runtimeAssetSummary(validation));
    } catch (error) {
      setRuntimeAssetStatus(`Runtime asset check failed: ${errorMessage(error)}`);
    }
  }

  async function handleUseBundledProfile() {
    if (!bundledProfile) {
      setProfileStatus("Bundled KataGo profile unavailable. Configure local KataGo assets below.");
      return;
    }
    const adoptedVisits = Number.isFinite(visits) && visits > 0 ? Math.floor(visits) : 800;
    const record: EngineProfileRecordDto = {
      id: "bundled-katago",
      profile: {
        ...bundledProfile,
        name: bundledProfile.name.trim() || "Bundled KataGo",
        backend: "kata_go_analysis"
      },
      max_visits: adoptedVisits
    };
    const nextProfiles = profiles.some((profile) => profile.id === record.id)
      ? profiles.map((profile) => profile.id === record.id ? record : profile)
      : [...profiles, record];
    try {
      await persistProfiles(nextProfiles, record.id, "Bundled KataGo profile saved and selected.");
      setAssetChecks([]);
    } catch (error) {
      setProfileStatus(`Bundled profile adoption failed: ${errorMessage(error)}`);
    }
  }

  async function handleOpenSetupLink(label: string, url: string) {
    try {
      await openExternalUrl(url);
      setProfileStatus(`Opened ${label}.`);
    } catch (error) {
      setProfileStatus(`Open ${label} failed: ${errorMessage(error)}`);
    }
  }

  async function refreshInstalledRuntimeProof(shouldApply: () => boolean = () => true) {
    if (!shouldApply()) return;
    setInstalledRuntimeProofStatus("Checking installed app launch proof...");
    try {
      const proof = await installedAppRuntimeProof();
      if (!shouldApply()) return;
      const summary = summarizeInstalledRuntimeProof(proof);
      setInstalledRuntimeProof(proof);
      setInstalledRuntimeProofStatus(installedProofSummaryMessage(summary));
    } catch (error) {
      if (!shouldApply()) return;
      setInstalledRuntimeProof(null);
      setInstalledRuntimeProofStatus(`Installed app proof unavailable: ${errorMessage(error)}`);
    }
  }

  return (
    <section
      className="engine-setup-panel"
      aria-label="KataGo engine setup"
      data-testid="engine-setup-panel"
      data-legacy-target="engine-setup"
      data-profile-count={profiles.length}
      data-selected-profile-id={selectedProfileId}
      data-selected-profile-name={selectedProfile?.profile.name ?? profileName}
      data-engine-profile-status={profileStatus}
      data-local-asset-check-status={localAssetCheckStatus}
      data-runtime-asset-check-status={runtimeAssetCheckStatus}
      data-missing-required-asset-count={missingRequiredAssets.length}
      data-runtime-asset-candidate-count={runtimeAssetValidation?.layout.candidates.length ?? 0}
      data-runtime-asset-missing-count={runtimeAssetValidation?.missing.length ?? 0}
      data-runtime-asset-placeholder-count={runtimeAssetValidation?.placeholders.length ?? 0}
      data-bundled-profile-available={String(bundledProfile !== null)}
    >
      <div
        className="engine-run-row"
        aria-label="Installed app engine/profile proof"
        data-testid="engine-runtime-proof"
        data-legacy-target="engine-assets"
        data-profile-count={profiles.length}
        data-selected-profile-id={selectedProfileId}
        data-local-asset-check-status={localAssetCheckStatus}
        data-runtime-asset-check-status={runtimeAssetCheckStatus}
        data-installed-runtime-proof-status={installedProofStatus}
        data-installed-runtime-source-kind={installedRuntimeSummary?.sourceKind ?? "unknown"}
        data-installed-runtime-source={installedRuntimeSummary?.runtimeSource ?? ""}
        data-installed-runtime-asset-status={installedRuntimeSummary?.assetStatus ?? "unknown"}
        data-installed-engine-launch-status={installedRuntimeSummary?.launchStatus ?? "unknown"}
        data-installed-engine-launch-availability={installedRuntimeSummary?.launchAvailability ?? "unknown"}
        data-local-profile-fallback={String(installedRuntimeSummary?.localProfileFallback ?? true)}
        data-can-run-katago={String(canRun)}
      >
        <strong>Engine runtime</strong>
        <span data-testid="engine-profile-runtime-status" data-profile-count={profiles.length} data-selected-profile-id={selectedProfileId}>
          {profiles.length > 0 ? `${profiles.length} profile${profiles.length === 1 ? "" : "s"} loaded` : "Profiles loading"}
        </span>
        <span data-testid="engine-asset-check-runtime-status" data-local-asset-check-status={localAssetCheckStatus}>
          Local assets: {localAssetCheckStatus.replaceAll("-", " ")}
        </span>
        <span data-testid="engine-runtime-asset-check-status" data-runtime-asset-check-status={runtimeAssetCheckStatus}>
          Runtime assets: {runtimeAssetCheckStatus.replaceAll("-", " ")}
        </span>
      </div>
      <div
        className="engine-run-row"
        data-testid="engine-profiles-target"
        data-legacy-target="engine-profiles"
        data-profile-count={profiles.length}
        data-selected-profile-id={selectedProfileId}
        data-profile-status={profileStatus}
      >
        <label>
          <span>Profile</span>
          <select data-testid="engine-profile-select" value={selectedProfileId} onChange={(event) => void handleSelectProfile(event.target.value)}>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>{profile.profile.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Name</span>
          <input value={profileName} onChange={(event) => setProfileName(event.target.value)} placeholder="Local KataGo" />
        </label>
        <button type="button" onClick={() => void handleAddProfile()} disabled={!canSave}>Add profile</button>
        <button type="button" onClick={() => void handleDeleteProfile()} disabled={!canDeleteProfile}>Delete profile</button>
      </div>
      <div
        className="engine-run-row"
        aria-label="Bundled runtime asset status"
        data-testid="engine-assets-target"
        data-legacy-target="engine-assets"
        data-runtime-asset-check-status={runtimeAssetCheckStatus}
        data-runtime-asset-candidate-count={runtimeAssetValidation?.layout.candidates.length ?? 0}
        data-runtime-asset-missing-count={runtimeAssetValidation?.missing.length ?? 0}
        data-runtime-asset-placeholder-count={runtimeAssetValidation?.placeholders.length ?? 0}
      >
        <strong>Bundled/runtime assets</strong>
        <button type="button" data-testid="engine-runtime-assets-refresh" onClick={() => void handleCheckRuntimeAssets()} disabled={disabled} title="Refresh runtime assets">Refresh</button>
        <span className="message">{runtimeAssetStatus}</span>
      </div>
      {runtimeAssetValidation && (
        <p
          className="message"
          data-testid="engine-runtime-assets-detail"
          data-runtime-asset-check-status={runtimeAssetCheckStatus}
        >
          {runtimeAssetValidation.layout.resourceDir ? `Resource dir: ${runtimeAssetValidation.layout.resourceDir}. ` : "Resource dir unavailable. "}
          {runtimeAssetValidation.layout.candidates.length > 0
            ? runtimeAssetValidation.checks.map((check) => `${check.status.toUpperCase()} ${check.source} ${check.label}: ${check.path}`).join(" | ")
            : "No runtime asset candidates are visible in this environment."}
        </p>
      )}
      {runtimeAssetValidation && runtimeAssetMessages(runtimeAssetValidation).length > 0 && (
        <p className="message">
          {runtimeAssetMessages(runtimeAssetValidation).join(" | ")}
        </p>
      )}
      <section
        className="engine-runtime-proof-details"
        aria-label="Installed app bundled KataGo launch proof"
        data-testid="engine-installed-app-launch-proof"
        data-legacy-target="engine-assets"
        data-proof-status={installedProofStatus}
        data-runtime-source-kind={installedRuntimeSummary?.sourceKind ?? "unknown"}
        data-runtime-source={installedRuntimeSummary?.runtimeSource ?? ""}
        data-asset-validation-status={installedRuntimeSummary?.assetStatus ?? "unknown"}
        data-profile-status={installedRuntimeSummary?.profileStatus ?? "unknown"}
        data-profile-source={installedRuntimeSummary?.profileSource ?? "unknown"}
        data-launch-status={installedRuntimeSummary?.launchStatus ?? "unknown"}
        data-launch-availability={installedRuntimeSummary?.launchAvailability ?? "unknown"}
        data-local-profile-fallback={String(installedRuntimeSummary?.localProfileFallback ?? true)}
        data-release-parity="false"
        data-large-model-bundled="false"
        data-bundled-profile-available={String(bundledProfile !== null)}
        data-bundled-profile-status={bundledProfileProof?.status ?? "unavailable"}
      >
        <div className="engine-run-row">
          <strong>Installed app launch proof</strong>
          <button type="button" data-testid="engine-installed-app-proof-refresh" onClick={() => void refreshInstalledRuntimeProof()} disabled={disabled} title="Refresh installed app proof">Refresh proof</button>
          <span data-testid="engine-installed-app-runtime-source">
            Source: {installedRuntimeSummary?.sourceKind ?? installedProofStatus}
          </span>
          <span data-testid="engine-installed-app-asset-validation-status">
            Runtime validation: {installedRuntimeSummary?.assetStatus ?? installedProofStatus}
          </span>
          <span data-testid="engine-installed-app-launch-attempt-status">
            Launch attempt: {installedRuntimeSummary ? `${installedRuntimeSummary.launchAvailability} (${installedRuntimeSummary.launchStatus})` : installedProofStatus}
          </span>
        </div>
        <p className="message" data-testid="engine-installed-app-local-profile-fallback">
          {installedRuntimeSummary
            ? installedRuntimeSummary.localProfileFallback
              ? `Local profile fallback remains available: ${installedRuntimeSummary.launchMessage ?? "bundled launch is not treated as ready."}`
              : "Bundled/runtime launch proof is available; local profile configuration is still editable below."
            : installedRuntimeProofStatus}
        </p>
        {installedRuntimeSummary && (
          <p className="message">
            Profile: {installedRuntimeSummary.profileStatus} via {installedRuntimeSummary.profileSource}. Bundle: {installedRuntimeSummary.bundleStatus}. This is scoped installed-app runtime evidence, not signing, notarization, release, or large-model bundling proof.
          </p>
        )}
        <div
          className="engine-run-row"
          aria-label="Bundled KataGo profile adoption"
          data-testid="engine-bundled-profile-adoption"
          data-bundled-profile-available={String(bundledProfile !== null)}
          data-bundled-profile-status={bundledProfileProof?.status ?? "unavailable"}
        >
          <strong>Bundled KataGo profile</strong>
          <span data-testid="engine-bundled-profile-status">
            {bundledProfileStatus}
          </span>
          <button
            type="button"
            data-testid="engine-use-bundled-profile"
            onClick={() => void handleUseBundledProfile()}
            disabled={!canUseBundledProfile}
            title={bundledProfile ? "Save and select bundled-katago profile" : "Bundled runtime assets are unavailable; configure local KataGo assets"}
          >
            Use bundled profile
          </button>
        </div>
      </section>
      <p className="message">
        Large KataGo models are not bundled by this repository. Keep using the local asset configuration below unless an installed app package supplies runtime assets.
      </p>
      <section
        className="engine-run-row"
        aria-label="KataGo setup assistant"
        data-testid="engine-katago-setup-assistant"
        data-release-parity="false"
        data-large-model-bundled="false"
      >
        <strong>KataGo setup assistant</strong>
        <span className="message">Official setup links for local engine, network, and config assets.</span>
        <button
          type="button"
          data-testid="engine-open-katago-releases"
          onClick={() => void handleOpenSetupLink("KataGo releases", katagoSetupLinks.releases)}
        >
          KataGo releases
        </button>
        <button
          type="button"
          data-testid="engine-open-katago-networks"
          onClick={() => void handleOpenSetupLink("KataGo networks", katagoSetupLinks.networks)}
        >
          KataGo networks
        </button>
        <button
          type="button"
          data-testid="engine-open-katago-configs"
          onClick={() => void handleOpenSetupLink("KataGo config examples", katagoSetupLinks.configs)}
        >
          KataGo config examples
        </button>
      </section>
      <div className="engine-run-row" aria-label="Local asset configuration" data-testid="engine-local-assets-target" data-legacy-target="engine-assets">
        <strong>Local asset configuration</strong>
      </div>
      <div className="engine-grid">
        <label>
          <span>Engine</span>
          <div className="path-input-row">
            <input data-testid="engine-path-input" value={enginePath} onChange={(event) => updatePath(setEnginePath, event.target.value)} placeholder="/path/to/katago" aria-invalid={isKnownMissing(assetChecks, "engine binary")} title={pathCheckTitle(assetChecks, "engine binary")} />
            <button type="button" className="path-picker-button" onClick={() => void handlePickPath("Engine", enginePath, false, setEnginePath)}>
              Browse
            </button>
          </div>
        </label>
        <label>
          <span>Model</span>
          <div className="path-input-row">
            <input data-testid="engine-model-input" value={modelPath} onChange={(event) => updatePath(setModelPath, event.target.value)} placeholder="/path/to/model.bin.gz" aria-invalid={isKnownMissing(assetChecks, "model")} title={pathCheckTitle(assetChecks, "model")} />
            <button type="button" className="path-picker-button" onClick={() => void handlePickPath("Model", modelPath, false, setModelPath)}>
              Browse
            </button>
          </div>
        </label>
        <label>
          <span>Config</span>
          <div className="path-input-row">
            <input data-testid="engine-config-input" value={configPath} onChange={(event) => updatePath(setConfigPath, event.target.value)} placeholder="/path/to/analysis.cfg" aria-invalid={isKnownMissing(assetChecks, "config")} title={pathCheckTitle(assetChecks, "config")} />
            <button type="button" className="path-picker-button" onClick={() => void handlePickPath("Config", configPath, false, setConfigPath)}>
              Browse
            </button>
          </div>
        </label>
        <label>
          <span>Work dir</span>
          <div className="path-input-row">
            <input data-testid="engine-working-dir-input" value={workingDir} onChange={(event) => updatePath(setWorkingDir, event.target.value)} placeholder="Optional" aria-invalid={isKnownMissing(assetChecks, "working directory")} title={pathCheckTitle(assetChecks, "working directory")} />
            <button type="button" className="path-picker-button" onClick={() => void handlePickPath("Work dir", workingDir, true, setWorkingDir)}>
              Browse
            </button>
          </div>
        </label>
      </div>
      <div className="engine-run-row" data-testid="engine-actions-target" data-legacy-target="analysis-actions" data-can-run-katago={String(canRun)}>
        <label>
          <span>Max visits</span>
          <input type="number" min={1} step={1} value={maxVisits} onChange={(event) => setMaxVisits(event.target.value)} />
        </label>
        <button data-testid="engine-run-katago" onClick={handleRun} disabled={!canRun}>{disabled ? "Running..." : "Run KataGo"}</button>
        <button data-testid="engine-analyze-game" onClick={handleAnalyzeGame} disabled={!canRun} title="Analyze every move">{disabled ? "Running..." : "Analyze game"}</button>
        {isAnalysisActive && <button data-testid="engine-cancel-analysis" onClick={() => void onCancelAnalysis?.()} disabled={!onCancelAnalysis}>Cancel</button>}
        <button data-testid="engine-save-profile" onClick={() => void handleSaveProfile()} disabled={!canSave}>Save profile</button>
        <button data-testid="engine-check-assets" onClick={() => void handleCheckAssets()} disabled={disabled}>Check assets</button>
      </div>
      {reviewWorkflow && (
        <section
          className="analysis-progress"
          aria-label="KataGo review workflow status"
          aria-live="polite"
          data-testid="katago-review-workflow-status"
          data-review-phase={reviewWorkflow.phase}
          data-review-source={reviewWorkflow.source}
          data-review-session-token={reviewWorkflow.sessionToken}
          data-active-job-id={reviewWorkflow.activeJobId ?? ""}
          data-progress-verified={String(reviewWorkflow.progressVerified)}
          data-cancel-verified={String(reviewWorkflow.cancelVerified)}
          data-restart-after-cancel-verified={String(reviewWorkflow.restartAfterCancelVerified)}
          data-cache-restore-verified={String(reviewWorkflow.cacheRestoreVerified)}
          data-engine-failure-verified={String(reviewWorkflow.engineFailureVerified)}
          data-stale-analysis-prevented={String(reviewWorkflow.staleAnalysisPrevented)}
        >
          <strong>{reviewStatusLabel(reviewWorkflow.phase, reviewWorkflow.source)}</strong>
          <span>{reviewWorkflow.message}</span>
          <span>
            {reviewWorkflow.completed}/{reviewWorkflow.expected || "?"} positions
            {reviewWorkflow.currentTurn !== null ? `, move ${reviewWorkflow.currentTurn}` : ""}
            {reviewWorkflow.activeJobId ? `, job ${reviewWorkflow.activeJobId}` : ""}
          </span>
        </section>
      )}
      {(isAnalysisActive || analysisProgress) && (
        <div
          className="analysis-progress"
          aria-live="polite"
          data-testid="katago-analysis-progress"
          data-progress-verified={String(Boolean(analysisProgress))}
          data-active-job-id={activeJobId ?? ""}
          data-current-position={analysisProgress?.completed ?? 0}
          data-expected-positions={analysisProgress?.expected ?? 0}
        >
          <div className="analysis-progress-track">
            <span style={{ width: `${progressPercent}%` }} />
          </div>
          <span>{progressLabel}</span>
        </div>
      )}
      <p className="message" data-testid="engine-profile-status-message" data-engine-profile-status={profileStatus}>{profileStatus}</p>
      {assetChecks.length > 0 && (
        <p className="message" data-testid="engine-local-asset-check-details" data-local-asset-check-status={localAssetCheckStatus}>
          {assetChecks.map((check) => `${check.exists ? "OK" : "Missing"} ${check.label}${check.path ? `: ${check.path}` : ""}`).join(" | ")}
        </p>
      )}
    </section>
  );
}

function reviewStatusLabel(phase: string, source: string): string {
  if (phase === "cache-restored") return "Review restored from cache";
  if (phase === "cancelled") return "Review cancelled";
  if (phase === "error") return "Review needs attention";
  if (phase === "completed") return source === "fake" ? "Browser review complete" : "KataGo review complete";
  if (phase === "running") return source === "fake" ? "Browser review running" : "KataGo review running";
  if (phase === "cancelling") return "Cancelling review";
  if (phase === "starting") return "Starting review";
  return "Review ready";
}

function optionalPath(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function assetStatus(checks: AssetCheckDto[]): string {
  const missingRequired = checks.filter((check) => check.required && !check.exists);
  if (missingRequired.length === 0) return "Assets ready.";
  return `Missing required: ${missingRequired.map((check) => `${check.label}${check.path ? ` (${check.path})` : ""}`).join(", ")}.`;
}

function runtimeAssetSummary(validation: RuntimeAssetValidationDto): string {
  const candidateCount = validation.layout.candidates.length;
  const missingCount = validation.missing.length;
  const placeholderCount = validation.placeholders.length;
  const problemCount = missingCount + placeholderCount;
  if (candidateCount === 0) {
    return validation.warnings[0] ?? "Runtime asset layout unavailable.";
  }
  if (problemCount === 0) return `Runtime asset layout visible: ${candidateCount} candidates.`;
  return `Runtime asset layout visible: ${candidateCount} candidates, ${missingCount} missing, ${placeholderCount} placeholder.`;
}

function runtimeAssetMessages(validation: RuntimeAssetValidationDto): string[] {
  const messages = [
    ...validation.warnings,
    ...validation.placeholders.map((placeholder) => placeholder.message)
  ];
  return Array.from(new Set(messages.filter((message) => message.trim().length > 0)));
}

function extractBundledKataGoProof(proof: InstalledAppRuntimeProofDto): InstalledAppBundledKataGoProofDto | null {
  return proof.bundledKatago ?? proof.bundledKataGo ?? proof.bundled_katago ?? null;
}

function validBundledProfile(profile: InstalledAppBundledKataGoProofDto["profile"]): EngineProfileDto | null {
  if (!profile) return null;
  if (profile.backend !== "kata_go_analysis") return null;
  if (profile.engine_path.trim().length === 0) return null;
  if (!profile.model_path || profile.model_path.trim().length === 0) return null;
  if (!profile.config_path || profile.config_path.trim().length === 0) return null;
  return profile;
}

async function openExternalUrl(url: string): Promise<void> {
  try {
    await openUrl(url);
    return;
  } catch (tauriError) {
    if (typeof window === "undefined") {
      throw tauriError;
    }
    const opened = window.open(url, "_blank", "noopener,noreferrer");
    if (opened === null) {
      throw tauriError;
    }
    opened.opener = null;
  }
}

type InstalledRuntimeSummary = {
  proofStatus: string;
  sourceKind: string;
  runtimeSource: string;
  assetStatus: string;
  profileStatus: string;
  profileSource: string;
  launchStatus: string;
  launchAvailability: string;
  launchMessage: string | null;
  bundleStatus: string;
  localProfileFallback: boolean;
};

function summarizeInstalledRuntimeProof(proof: InstalledAppRuntimeProofDto): InstalledRuntimeSummary {
  const runtimeSource = stringField(proof.runtime, "source") ?? "unknown";
  const assetStatus = summarizeInstalledAssetStatus(proof.assets);
  const profileStatus = stringField(proof.profileStatus, "status") ?? stringField(proof.profileStatus, "result") ?? "observed";
  const profileSource = stringField(proof.profileStatus, "source") ?? stringField(proof.profileStatus, "profileSource") ?? stringField(proof.profileStatus, "kind") ?? "local-profile-fallback";
  const launchStatus = stringField(proof.engineLaunchAttempt, "status")
    ?? stringField(proof.engineLaunchAttempt, "result")
    ?? stringField(proof.engineLaunchAttempt, "outcome")
    ?? "observed";
  const launchAvailability = summarizeLaunchAvailability(proof.engineLaunchAttempt, launchStatus);
  const launchMessage = stringField(proof.engineLaunchAttempt, "message")
    ?? stringField(proof.engineLaunchAttempt, "error")
    ?? stringField(proof.engineLaunchAttempt, "reason");
  const bundleStatus = booleanField(proof.bundle, "appBundleExists") === true
    ? "bundle-observed"
    : booleanField(proof.bundle, "resourceDirExists") === true
      ? "resource-dir-observed"
      : "bundle-unavailable";
  return {
    proofStatus: classifyProofStatus(proof.status),
    sourceKind: runtimeSourceKind(runtimeSource),
    runtimeSource,
    assetStatus,
    profileStatus,
    profileSource,
    launchStatus,
    launchAvailability,
    launchMessage,
    bundleStatus,
    localProfileFallback: assetStatus !== "ready" || launchAvailability !== "available"
  };
}

function installedProofSummaryMessage(summary: InstalledRuntimeSummary): string {
  return `Installed app proof ${summary.proofStatus}: source ${summary.sourceKind}, runtime assets ${summary.assetStatus}, launch ${summary.launchAvailability}.`;
}

function summarizeInstalledAssetStatus(assets: InstalledAppRuntimeProofDto["assets"]): string {
  const validation = assets.validation ?? assets.runtimeAssetValidation ?? null;
  const missing = validation?.missing.length ?? assets.missing?.length ?? 0;
  const placeholders = validation?.placeholders.length ?? assets.placeholders?.length ?? 0;
  const raw = (assets.status ?? "").toLowerCase();
  if (missing + placeholders > 0) return "problem";
  if (/unavailable|missing|skipped|not[_ -]?found|not[_ -]?configured/.test(raw)) return "unavailable";
  if (/error|fail/.test(raw)) return "error";
  if (/problem|invalid|placeholder/.test(raw)) return "problem";
  if (/ready|ok|available/.test(raw)) return "ready";
  if ((validation?.checks.length ?? assets.checks?.length ?? 0) > 0) return "observed";
  return "unavailable";
}

function summarizeLaunchAvailability(value: Record<string, unknown>, status: string): string {
  const available = booleanField(value, "available")
    ?? booleanField(value, "success")
    ?? booleanField(value, "launched")
    ?? booleanField(value, "engineAvailable");
  if (available === true) return "available";
  if (available === false) return "unavailable";
  const normalized = status.toLowerCase();
  if (/missing|unavailable|not[_ -]?found|not[_ -]?configured|skipped/.test(normalized)) return "unavailable";
  if (/error|fail/.test(normalized)) return "error";
  if (/problem|invalid/.test(normalized)) return "problem";
  if (/success|launched|available|ok/.test(normalized)) return "available";
  return "observed";
}

function classifyProofStatus(status: string): string {
  const normalized = status.toLowerCase();
  if (/pass|ok|ready|available|observed/.test(normalized)) return "observed";
  if (/unavailable|missing|skipped|not[_ -]?found/.test(normalized)) return "unavailable";
  if (/error|fail|problem|invalid/.test(normalized)) return "error";
  return normalized || "observed";
}

function classifyInstalledProofMessage(message: string): string {
  const normalized = message.toLowerCase();
  if (/checking/.test(normalized)) return "checking";
  if (/unavailable|browser fallback|requires the tauri/.test(normalized)) return "unavailable";
  if (/error|failed|fail/.test(normalized)) return "error";
  return "observed";
}

function runtimeSourceKind(source: string): string {
  const normalized = source.toLowerCase();
  if (normalized.includes("packaged") || normalized.includes("installed")) return "packaged-app";
  if (normalized.includes("tauri-dev") || normalized.includes("dev")) return "tauri-dev";
  if (normalized.includes("browser")) return "browser-fallback";
  return normalized || "unknown";
}

function stringField(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function booleanField(record: Record<string, unknown>, key: string): boolean | null {
  const value = record[key];
  return typeof value === "boolean" ? value : null;
}

function isKnownMissing(checks: AssetCheckDto[], label: string): boolean {
  return checks.some((check) => check.label === label && check.required && !check.exists);
}

function pathCheckTitle(checks: AssetCheckDto[], label: string): string | undefined {
  const check = checks.find((item) => item.label === label);
  if (!check) return undefined;
  return check.exists ? `Resolved path: ${check.path}` : `Missing required ${label}${check.path ? `: ${check.path}` : ""}`;
}

function nextProfileName(profiles: EngineProfileRecordDto[]): string {
  const existing = new Set(profiles.map((profile) => profile.profile.name));
  let index = profiles.length + 1;
  let name = `KataGo Profile ${index}`;
  while (existing.has(name)) {
    index += 1;
    name = `KataGo Profile ${index}`;
  }
  return name;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
