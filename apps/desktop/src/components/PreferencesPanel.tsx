import type { AppPreferences, BoardTheme, ReviewMode } from "../domain/preferences";

type Props = {
  preferences: AppPreferences;
  status: string;
  disabled?: boolean;
  onChange: (preferences: AppPreferences) => void;
};

export function PreferencesPanel({ preferences, status, disabled = false, onChange }: Props) {
  function update(patch: Partial<AppPreferences>) {
    onChange({ ...preferences, ...patch });
  }

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
