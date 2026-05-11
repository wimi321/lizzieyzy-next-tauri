import { useRef, type ReactNode } from "react";

type LegacyShellProps = {
  themeClassName?: string;
  architectureLabel: string;
  backendStatusLabel: string;
  cacheBadge: ReactNode;
  board: ReactNode;
  chart: ReactNode;
  analysisPanel: ReactNode;
  providerPanel: ReactNode;
  enginePanel: ReactNode;
  preferencesPanel: ReactNode;
  documentName: string;
  documentTitle: string;
  dirty: boolean;
  sgfText: string;
  currentMove: number;
  maxMove: number;
  message: string;
  isBusy: boolean;
  canSave: boolean;
  onOpen: () => void | Promise<void>;
  onSave: () => void | Promise<void>;
  onSaveAs: () => void | Promise<void>;
  onImportFile: (file: File | null) => void | Promise<void>;
  onLoadSample: () => void | Promise<void>;
  onParseSgf: () => void | Promise<void>;
  onRunReview: () => void | Promise<void>;
  onSgfTextChange: (value: string) => void;
  onMoveChange: (moveNumber: number) => void;
};

export function LegacyShell({
  themeClassName = "",
  architectureLabel,
  backendStatusLabel,
  cacheBadge,
  board,
  chart,
  analysisPanel,
  providerPanel,
  enginePanel,
  preferencesPanel,
  documentName,
  documentTitle,
  dirty,
  sgfText,
  currentMove,
  maxMove,
  message,
  isBusy,
  canSave,
  onOpen,
  onSave,
  onSaveAs,
  onImportFile,
  onLoadSample,
  onParseSgf,
  onRunReview,
  onSgfTextChange,
  onMoveChange
}: LegacyShellProps) {
  const fileInputId = "legacy-shell-import-sgf";
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const menuGroups = [
    {
      label: "File",
      items: [
        { label: "Open", onSelect: onOpen, disabled: isBusy },
        { label: "Save", onSelect: onSave, disabled: isBusy || !canSave },
        { label: "Save As", onSelect: onSaveAs, disabled: isBusy },
        { label: "Import SGF", onSelect: () => importInputRef.current?.click(), disabled: isBusy }
      ]
    },
    {
      label: "Game",
      items: [
        { label: "Load sample", onSelect: onLoadSample, disabled: isBusy },
        { label: "Parse SGF", onSelect: onParseSgf, disabled: isBusy }
      ]
    },
    {
      label: "Analysis",
      items: [
        { label: "Run review", onSelect: onRunReview, disabled: isBusy },
        { label: "KataGo panel", disabled: true }
      ]
    },
    {
      label: "View",
      items: [
        { label: "Candidates", disabled: true },
        { label: "Ownership", disabled: true },
        { label: "Policy", disabled: true }
      ]
    },
    {
      label: "Engine",
      items: [
        { label: "Profiles", disabled: true },
        { label: "Assets", disabled: true }
      ]
    },
    {
      label: "Tools",
      items: [
        { label: "Providers", disabled: true },
        { label: "Preferences", disabled: true }
      ]
    },
    {
      label: "Help",
      items: [
        { label: "Backend status", disabled: true }
      ]
    }
  ];

  return (
    <main className={`app-shell legacy-shell${themeClassName ? ` ${themeClassName}` : ""}`}>
      <header className="legacy-titlebar">
        <div className="legacy-appmark">
          <h1>LizzieYzy Next</h1>
          <p>{architectureLabel}</p>
        </div>
        <nav className="legacy-menubar" aria-label="Application menu">
          {menuGroups.map((group) => (
            <details key={group.label} className="legacy-menu">
              <summary>{group.label}</summary>
              <div className="legacy-menu-popover">
                {group.items.map((item) => (
                  <button key={item.label} type="button" disabled={item.disabled} onClick={() => void item.onSelect?.()}>
                    {item.label}
                  </button>
                ))}
              </div>
            </details>
          ))}
        </nav>
        <div className="legacy-title-status">
          {cacheBadge}
          <span className="status-pill">{backendStatusLabel}</span>
        </div>
      </header>

      <section className="legacy-toolbar" aria-label="Main toolbar">
        <button type="button" onClick={() => void onOpen()} disabled={isBusy} title="Open SGF">Open</button>
        <button type="button" onClick={() => void onSave()} disabled={isBusy || !canSave} title="Save SGF">Save</button>
        <button type="button" onClick={() => void onSaveAs()} disabled={isBusy} title="Save SGF as">Save As</button>
        <label className={`file-button legacy-tool-file${isBusy ? " file-button-disabled" : ""}`} title="Import SGF">
          Import
          <input ref={importInputRef} id={fileInputId} type="file" accept=".sgf,.txt,application/x-go-sgf,text/plain" disabled={isBusy} onChange={(event) => {
            void onImportFile(event.target.files?.[0] ?? null);
            event.currentTarget.value = "";
          }} />
        </label>
        <span className="legacy-toolbar-divider" aria-hidden="true" />
        <button type="button" onClick={() => void onLoadSample()} disabled={isBusy} title="Load sample game">Sample</button>
        <button type="button" onClick={() => void onParseSgf()} disabled={isBusy} title="Parse SGF source">Parse</button>
        <button type="button" onClick={() => void onRunReview()} disabled={isBusy} title="Run review">Review</button>
        <span className="legacy-toolbar-spacer" />
        <div className="legacy-document-chip" title={documentTitle}>
          <strong>{documentName}{dirty ? " *" : ""}</strong>
          <span>{dirty ? "Unsaved" : "Saved"}</span>
        </div>
      </section>

      <section className="workspace legacy-workspace">
        <div className="left-pane legacy-board-pane">
          <div className="legacy-board-stage">{board}</div>
          <div className="legacy-chart-strip">{chart}</div>
          <div className="timeline-row legacy-timeline">
            <span>Move {currentMove}</span>
            <input className="move-slider" type="range" min={0} max={maxMove} value={Math.min(currentMove, maxMove)} onChange={(event) => onMoveChange(Number(event.target.value))} />
            <span>{maxMove}</span>
          </div>
        </div>
        <div className="legacy-right-pane">{analysisPanel}</div>
      </section>

      <section className="bottom-dock legacy-bottom-dock" aria-label="Controls and setup">
        <section className="sgf-tools legacy-sgf-panel" aria-label="SGF source">
          <div className="document-row">
            <strong title={documentTitle}>{documentName}{dirty ? " *" : ""}</strong>
            <span>{dirty ? "Unsaved changes" : "Saved"}</span>
          </div>
          <textarea value={sgfText} onChange={(event) => onSgfTextChange(event.target.value)} spellCheck={false} aria-label="SGF source" />
          <div className="button-row">
            <button type="button" onClick={() => void onOpen()} disabled={isBusy}>Open</button>
            <button type="button" onClick={() => void onSave()} disabled={isBusy || !canSave}>Save</button>
            <button type="button" onClick={() => void onSaveAs()} disabled={isBusy}>Save As</button>
            <label className={`file-button${isBusy ? " file-button-disabled" : ""}`}>
              Import SGF
              <input type="file" accept=".sgf,.txt,application/x-go-sgf,text/plain" disabled={isBusy} onChange={(event) => {
                void onImportFile(event.target.files?.[0] ?? null);
                event.currentTarget.value = "";
              }} />
            </label>
            <button type="button" onClick={() => void onLoadSample()} disabled={isBusy}>Load sample</button>
            <button type="button" onClick={() => void onParseSgf()} disabled={isBusy}>Parse SGF</button>
            <button type="button" onClick={() => void onRunReview()} disabled={isBusy}>Run review</button>
          </div>
        </section>
        {providerPanel}
        {enginePanel}
        {preferencesPanel}
      </section>

      <footer className="legacy-statusbar" role="status">
        <span>{message}</span>
      </footer>
    </main>
  );
}
