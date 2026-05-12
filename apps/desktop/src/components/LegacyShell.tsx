import { useEffect, useRef, useState, type ReactNode } from "react";

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

type LegacyMenuTarget =
  | "candidates"
  | "ownership"
  | "policy"
  | "profiles"
  | "assets"
  | "providers"
  | "preferences"
  | "backend-status";

type LegacyMenuItem = {
  label: string;
  onSelect?: () => void | Promise<void>;
  disabled?: boolean;
  target?: LegacyMenuTarget;
};

type LegacyMenuGroup = {
  label: string;
  items: LegacyMenuItem[];
};

type LegacyMenuActionState = {
  activeTarget: LegacyMenuTarget | null;
  lastAction: string;
  status: "idle" | "focused" | "missing";
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
  const boardPaneRef = useRef<HTMLDivElement | null>(null);
  const analysisPaneRef = useRef<HTMLDivElement | null>(null);
  const bottomDockRef = useRef<HTMLElement | null>(null);
  const statusbarRef = useRef<HTMLElement | null>(null);
  const focusResetRef = useRef<number | null>(null);
  const highlightedElementRef = useRef<HTMLElement | null>(null);
  const [highlightedTarget, setHighlightedTarget] = useState<LegacyMenuTarget | null>(null);
  const [menuAction, setMenuAction] = useState<LegacyMenuActionState>({
    activeTarget: null,
    lastAction: "",
    status: "idle"
  });

  useEffect(() => {
    return () => {
      if (focusResetRef.current !== null) window.clearTimeout(focusResetRef.current);
      highlightedElementRef.current?.classList.remove("legacy-focus-highlight");
      focusResetRef.current = null;
      highlightedElementRef.current = null;
    };
  }, []);

  function focusTarget(target: LegacyMenuTarget): boolean {
    const targetElement = resolveTargetElement(target);
    if (!targetElement) return false;

    if (focusResetRef.current !== null) {
      window.clearTimeout(focusResetRef.current);
      focusResetRef.current = null;
    }
    highlightedElementRef.current?.classList.remove("legacy-focus-highlight");
    ensureMenuTargetElement(targetElement, target);

    targetElement.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    if (!canFocusElement(targetElement) && !targetElement.hasAttribute("tabindex")) targetElement.setAttribute("tabindex", "-1");
    targetElement.focus({ preventScroll: true });
    targetElement.classList.add("legacy-focus-highlight");
    highlightedElementRef.current = targetElement;
    setHighlightedTarget(target);
    focusResetRef.current = window.setTimeout(() => {
      setHighlightedTarget(null);
      highlightedElementRef.current?.classList.remove("legacy-focus-highlight");
      highlightedElementRef.current = null;
    }, 1400);
    return true;
  }

  function runMenuTargetAction(target: LegacyMenuTarget, actionLabel: string) {
    const focused = focusTarget(target);
    setMenuAction({
      activeTarget: target,
      lastAction: actionLabel,
      status: focused ? "focused" : "missing"
    });
  }

  function resolveTargetElement(target: LegacyMenuTarget): HTMLElement | null {
    if (target === "candidates" || target === "ownership" || target === "policy") {
      activateBoardOverlay(target);
      return findAnalysisSection(target) ?? boardPaneRef.current;
    }

    if (target === "profiles" || target === "assets") {
      const enginePanelElement = bottomDockRef.current?.querySelector<HTMLElement>(".engine-setup-panel") ?? null;
      if (target === "assets") {
        return findButtonByText(enginePanelElement, "Check assets") ?? enginePanelElement;
      }
      return enginePanelElement?.querySelector<HTMLElement>("select") ?? enginePanelElement;
    }

    if (target === "providers") {
      return bottomDockRef.current?.querySelector<HTMLElement>(".provider-panel") ?? null;
    }

    if (target === "preferences") {
      return bottomDockRef.current?.querySelector<HTMLElement>(".preferences-panel") ?? null;
    }

    return statusbarRef.current;
  }

  function activateBoardOverlay(target: "candidates" | "ownership" | "policy") {
    const label = target === "candidates" ? "Candidates" : target === "ownership" ? "Ownership" : "Policy";
    const buttons = Array.from(boardPaneRef.current?.querySelectorAll<HTMLButtonElement>("[aria-pressed]") ?? []);
    const overlayButton = buttons.find((button) => button.textContent?.trim() === label);
    if (overlayButton && !overlayButton.disabled) overlayButton.click();
  }

  function findAnalysisSection(target: "candidates" | "ownership" | "policy"): HTMLElement | null {
    const heading = target === "ownership" ? "Position" : target === "candidates" ? "Candidates" : "Policy";
    const headings = Array.from(analysisPaneRef.current?.querySelectorAll<HTMLHeadingElement>("h2, h3") ?? []);
    return headings.find((item) => item.textContent?.trim() === heading)?.closest("section") ?? analysisPaneRef.current;
  }

  function findButtonByText(root: HTMLElement | null, label: string): HTMLElement | null {
    const buttons = Array.from(root?.querySelectorAll<HTMLButtonElement>("button") ?? []);
    return buttons.find((button) => button.textContent?.trim() === label) ?? null;
  }

  function canFocusElement(element: HTMLElement): boolean {
    return /^(A|BUTTON|INPUT|SELECT|TEXTAREA)$/.test(element.tagName);
  }

  function menuTargetId(target: LegacyMenuTarget): string {
    return `legacy-menu-target-${target}`;
  }

  function ensureMenuTargetElement(element: HTMLElement, target: LegacyMenuTarget) {
    element.id = menuTargetId(target);
    element.dataset.menuTarget = target;
    element.dataset.legacyMenuTargetId = menuTargetId(target);
  }

  function menuActionLabel(groupLabel: string, itemLabel: string): string {
    return `${groupLabel}:${itemLabel}`;
  }

  const menuGroups: LegacyMenuGroup[] = [
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
        { label: "KataGo panel", target: "profiles" }
      ]
    },
    {
      label: "View",
      items: [
        { label: "Candidates", target: "candidates" },
        { label: "Ownership", target: "ownership" },
        { label: "Policy", target: "policy" }
      ]
    },
    {
      label: "Engine",
      items: [
        { label: "Profiles", target: "profiles" },
        { label: "Assets", target: "assets" }
      ]
    },
    {
      label: "Tools",
      items: [
        { label: "Providers", target: "providers" },
        { label: "Preferences", target: "preferences" }
      ]
    },
    {
      label: "Help",
      items: [
        { label: "Backend status", target: "backend-status" }
      ]
    }
  ];

  return (
    <main
      className={`app-shell legacy-shell${themeClassName ? ` ${themeClassName}` : ""}`}
      data-testid="legacy-shell"
      data-active-menu-target={menuAction.activeTarget ?? ""}
      data-last-menu-action={menuAction.lastAction}
      data-menu-action-status={menuAction.status}
    >
      <header className="legacy-titlebar">
        <div className="legacy-appmark">
          <h1>LizzieYzy Next</h1>
          <p>{architectureLabel}</p>
        </div>
        <nav className="legacy-menubar" aria-label="Application menu" data-testid="legacy-menubar">
          {menuGroups.map((group) => (
            <details key={group.label} className="legacy-menu">
              <summary>{group.label}</summary>
              <div className="legacy-menu-popover">
                {group.items.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    disabled={item.disabled}
                    data-menu-target={item.target ?? undefined}
                    aria-controls={item.target ? menuTargetId(item.target) : undefined}
                    data-testid={`legacy-menu-${group.label.toLowerCase()}-${item.label.toLowerCase().replaceAll(" ", "-")}`}
                    onClick={(event) => {
                      if (item.target) {
                        runMenuTargetAction(item.target, menuActionLabel(group.label, item.label));
                      } else {
                        void item.onSelect?.();
                      }
                      event.currentTarget.closest("details")?.removeAttribute("open");
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </details>
          ))}
        </nav>
        <div className={`legacy-title-status${highlightedTarget === "backend-status" ? " legacy-focus-highlight" : ""}`} data-testid="legacy-backend-status">
          {cacheBadge}
          <span className="status-pill">{backendStatusLabel}</span>
        </div>
      </header>
      <span className="legacy-menu-action-status" aria-live="polite" data-testid="legacy-menu-action-status">
        {menuAction.status === "idle" ? "" : `${menuAction.lastAction}:${menuAction.status}`}
      </span>

      <section className="legacy-toolbar" aria-label="Main toolbar" data-testid="legacy-toolbar">
        <button type="button" data-testid="toolbar-open-sgf" onClick={() => void onOpen()} disabled={isBusy} title="Open SGF">Open</button>
        <button type="button" data-testid="toolbar-save-sgf" onClick={() => void onSave()} disabled={isBusy || !canSave} title="Save SGF">Save</button>
        <button type="button" data-testid="toolbar-save-as-sgf" onClick={() => void onSaveAs()} disabled={isBusy} title="Save SGF as">Save As</button>
        <label className={`file-button legacy-tool-file${isBusy ? " file-button-disabled" : ""}`} data-testid="toolbar-import-sgf" title="Import SGF">
          Import
          <input ref={importInputRef} id={fileInputId} type="file" accept=".sgf,.txt,application/x-go-sgf,text/plain" disabled={isBusy} onChange={(event) => {
            void onImportFile(event.target.files?.[0] ?? null);
            event.currentTarget.value = "";
          }} />
        </label>
        <span className="legacy-toolbar-divider" aria-hidden="true" />
        <button type="button" data-testid="toolbar-load-sample" onClick={() => void onLoadSample()} disabled={isBusy} title="Load sample game">Sample</button>
        <button type="button" data-testid="toolbar-parse-sgf" onClick={() => void onParseSgf()} disabled={isBusy} title="Parse SGF source">Parse</button>
        <button type="button" data-testid="toolbar-run-review" onClick={() => void onRunReview()} disabled={isBusy} title="Run review">Review</button>
        <span className="legacy-toolbar-spacer" />
        <div className="legacy-document-chip" title={documentTitle}>
          <strong>{documentName}{dirty ? " *" : ""}</strong>
          <span>{dirty ? "Unsaved" : "Saved"}</span>
        </div>
      </section>

      <section className="workspace legacy-workspace">
        <div
          ref={boardPaneRef}
          className={`left-pane legacy-board-pane${highlightedTarget === "candidates" || highlightedTarget === "ownership" || highlightedTarget === "policy" ? " legacy-focus-highlight" : ""}`}
          data-testid="legacy-board-pane"
        >
          <div className="legacy-board-stage">{board}</div>
          <div className="legacy-chart-strip">{chart}</div>
          <div className="timeline-row legacy-timeline">
            <span>Move {currentMove}</span>
            <input className="move-slider" type="range" min={0} max={maxMove} value={Math.min(currentMove, maxMove)} onChange={(event) => onMoveChange(Number(event.target.value))} />
            <span>{maxMove}</span>
          </div>
        </div>
        <div ref={analysisPaneRef} className="legacy-right-pane" data-testid="legacy-analysis-pane">{analysisPanel}</div>
      </section>

      <section ref={bottomDockRef} className="bottom-dock legacy-bottom-dock" aria-label="Controls and setup" data-testid="legacy-bottom-dock">
        <section className="sgf-tools legacy-sgf-panel" aria-label="SGF source">
          <div className="document-row">
            <strong title={documentTitle}>{documentName}{dirty ? " *" : ""}</strong>
            <span>{dirty ? "Unsaved changes" : "Saved"}</span>
          </div>
          <textarea data-testid="sgf-source-textarea" value={sgfText} onChange={(event) => onSgfTextChange(event.target.value)} disabled={isBusy} spellCheck={false} aria-label="SGF source" />
          <div className="button-row">
            <button type="button" data-testid="sgf-source-open" onClick={() => void onOpen()} disabled={isBusy}>Open</button>
            <button type="button" data-testid="sgf-source-save" onClick={() => void onSave()} disabled={isBusy || !canSave}>Save</button>
            <button type="button" data-testid="sgf-source-save-as" onClick={() => void onSaveAs()} disabled={isBusy}>Save As</button>
            <label className={`file-button${isBusy ? " file-button-disabled" : ""}`}>
              Import SGF
              <input type="file" accept=".sgf,.txt,application/x-go-sgf,text/plain" disabled={isBusy} onChange={(event) => {
                void onImportFile(event.target.files?.[0] ?? null);
                event.currentTarget.value = "";
              }} />
            </label>
            <button type="button" data-testid="sgf-source-load-sample" onClick={() => void onLoadSample()} disabled={isBusy}>Load sample</button>
            <button type="button" data-testid="sgf-source-parse" onClick={() => void onParseSgf()} disabled={isBusy}>Parse SGF</button>
            <button type="button" data-testid="sgf-source-run-review" onClick={() => void onRunReview()} disabled={isBusy}>Run review</button>
          </div>
        </section>
        {providerPanel}
        {enginePanel}
        {preferencesPanel}
      </section>

      <footer
        ref={statusbarRef}
        id="legacy-menu-target-backend-status"
        className={`legacy-statusbar${highlightedTarget === "backend-status" ? " legacy-focus-highlight" : ""}`}
        role="status"
        tabIndex={-1}
        data-menu-target="backend-status"
        data-testid="legacy-statusbar"
      >
        <span>{message}</span>
      </footer>
    </main>
  );
}
