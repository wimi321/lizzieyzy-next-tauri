import type { LegacyConfigMigrationApplyDto, LegacyConfigMigrationPreviewDto } from "../api/backend";
import type { AppPreferences, BoardTheme, ReviewMode } from "../domain/preferences";

type Props = {
  preferences: AppPreferences;
  status: string;
  disabled?: boolean;
  onChange: (preferences: AppPreferences) => void;
  legacyConfigPath: string;
  legacyConfigStatus: string;
  legacyConfigPreview: LegacyConfigMigrationPreviewDto | null;
  legacyConfigApplyResult: LegacyConfigMigrationApplyDto | null;
  isLegacyConfigMigrating?: boolean;
  onLegacyConfigPathChange: (path: string) => void;
  onPreviewLegacyConfigMigration: () => void;
  onApplyLegacyConfigMigration: () => void;
};

export function PreferencesPanel({
  preferences,
  status,
  disabled = false,
  onChange,
  legacyConfigPath,
  legacyConfigStatus,
  legacyConfigPreview,
  legacyConfigApplyResult,
  isLegacyConfigMigrating = false,
  onLegacyConfigPathChange,
  onPreviewLegacyConfigMigration,
  onApplyLegacyConfigMigration
}: Props) {
  function update(patch: Partial<AppPreferences>) {
    onChange({ ...preferences, ...patch });
  }

  const canRunMigration = !disabled && !isLegacyConfigMigrating && legacyConfigPath.trim().length > 0;
  const migratedFields = legacyConfigApplyResult?.migratedFields ?? legacyConfigPreview?.migratedFields ?? [];
  const warnings = legacyConfigApplyResult?.warnings ?? legacyConfigPreview?.warnings ?? [];

  return (
    <section className="preferences-panel" aria-label="Application preferences">
      <div className="preferences-header">
        <h2>Preferences</h2>
        <span>{status}</span>
      </div>
      <div className="preferences-grid">
        <Toggle label="Candidates" checked={preferences.showCandidates} disabled={disabled} onChange={(checked) => update({ showCandidates: checked })} />
        <Toggle label="Ownership" checked={preferences.showOwnership} disabled={disabled} onChange={(checked) => update({ showOwnership: checked })} />
        <Toggle label="Policy" checked={preferences.showPolicy} disabled={disabled} onChange={(checked) => update({ showPolicy: checked })} />
        <Toggle label="Auto-load cache" checked={preferences.autoLoadCache} disabled={disabled} onChange={(checked) => update({ autoLoadCache: checked })} />
        <Toggle label="Auto-save analysis" checked={preferences.autoSaveAnalysis} disabled={disabled} onChange={(checked) => update({ autoSaveAnalysis: checked })} />
        <label>
          <span>Candidates shown</span>
          <input
            type="number"
            min={1}
            max={20}
            step={1}
            value={preferences.candidateLimit}
            disabled={disabled}
            onChange={(event) => update({ candidateLimit: Number(event.target.value) })}
          />
        </label>
        <label>
          <span>Default visits</span>
          <input
            type="number"
            min={1}
            step={1}
            value={preferences.defaultMaxVisits}
            disabled={disabled}
            onChange={(event) => update({ defaultMaxVisits: Number(event.target.value) })}
          />
        </label>
        <label>
          <span>Review mode</span>
          <select value={preferences.reviewMode} disabled={disabled} onChange={(event) => update({ reviewMode: event.target.value as ReviewMode })}>
            <option value="quick">Quick</option>
            <option value="deep">Deep</option>
          </select>
        </label>
        <label>
          <span>Board theme</span>
          <select value={preferences.boardTheme} disabled={disabled} onChange={(event) => update({ boardTheme: event.target.value as BoardTheme })}>
            <option value="classic">Classic</option>
            <option value="high-contrast">High contrast</option>
          </select>
        </label>
      </div>
      <section className="legacy-config-migration" aria-label="Legacy Java/Swing config migration">
        <div className="preferences-header">
          <h3>Legacy config migration</h3>
          <span>{legacyConfigStatus}</span>
        </div>
        <label>
          <span>Legacy config path</span>
          <input
            data-testid="legacy-config-path-input"
            type="text"
            value={legacyConfigPath}
            disabled={disabled || isLegacyConfigMigrating}
            placeholder="/path/to/legacy/config"
            onChange={(event) => onLegacyConfigPathChange(event.target.value)}
          />
        </label>
        <div className="legacy-config-actions" aria-label="Legacy config migration actions">
          <button type="button" disabled={!canRunMigration} onClick={onPreviewLegacyConfigMigration}>Preview</button>
          <button type="button" disabled={!canRunMigration || legacyConfigPreview === null} onClick={onApplyLegacyConfigMigration}>Apply</button>
        </div>
        {migratedFields.length > 0 ? (
          <div className="migration-result" data-testid="legacy-config-migrated-fields">
            <strong>Migrated fields</strong>
            <ul>
              {migratedFields.map((field) => <li key={field}>{field}</li>)}
            </ul>
          </div>
        ) : null}
        {warnings.length > 0 ? (
          <div className="migration-result" data-testid="legacy-config-warnings">
            <strong>Warnings</strong>
            <ul>
              {warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          </div>
        ) : null}
        {legacyConfigApplyResult ? (
          <div className="migration-result" data-testid="legacy-config-apply-status">
            <strong>Applied</strong>
            <span>
              Preferences {legacyConfigApplyResult.preferencesWritten ? "written" : "unchanged"}; engine profiles {legacyConfigApplyResult.engineProfilesWritten ? "written" : "unchanged"}.
            </span>
          </div>
        ) : null}
      </section>
    </section>
  );
}

function Toggle({ label, checked, disabled, onChange }: { label: string; checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}
