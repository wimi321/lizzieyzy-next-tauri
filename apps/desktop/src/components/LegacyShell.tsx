import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { listenToLegacyMenuActionEvents } from "../api/backend";
import {
  legacyActionFromKeyboardEvent,
  legacyActionDefinition,
  legacyActionLabel,
  legacyActionMenuPath,
  legacyActionMatrix,
  legacyActionTestId,
  legacyShortcutAria,
  type LegacyActionDefinition,
  type LegacyActionId,
  type LegacyActionSource,
  type LegacyMenuTarget
} from "../domain/legacyActions";

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

type LegacyMenuItem = {
  action: LegacyActionDefinition;
  disabled?: boolean;
};

type LegacyMenuGroup = {
  label: string;
  items: LegacyMenuItem[];
};

type LegacyMenuActionState = {
  activeTarget: LegacyMenuTarget | null;
  lastAction: string;
  lastActionId: LegacyActionId | "";
  lastActionSource: LegacyActionSource | "";
  status: "idle" | "dispatched" | "focused" | "missing" | "blocked" | "failed";
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
    lastActionId: "",
    lastActionSource: "",
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

  function runMenuTargetAction(target: LegacyMenuTarget, action: LegacyActionDefinition, source: LegacyActionSource) {
    const focused = focusTarget(target);
    setMenuAction({
      activeTarget: target,
      lastAction: legacyActionLabel(action.id),
      lastActionId: action.id,
      lastActionSource: source,
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

  function actionData(actionId: LegacyActionId) {
    const action = legacyActionDefinition(actionId);
    return {
      "data-legacy-action": action.id,
      "data-legacy-action-group": action.group,
      "data-legacy-action-label": action.label,
      "data-legacy-action-menu-path": legacyActionMenuPath(action),
      "data-legacy-action-shortcut": action.shortcut ?? "",
      "data-legacy-action-target": action.target ?? "",
      "data-legacy-action-target-selector": action.targetSelector ?? "",
      "data-legacy-action-testid": legacyActionTestId(action.id),
      "aria-keyshortcuts": legacyShortcutAria(action.shortcut)
    };
  }

  function markActionStatus(action: LegacyActionDefinition, source: LegacyActionSource, status: LegacyMenuActionState["status"]) {
    setMenuAction({
      activeTarget: action.target ?? null,
      lastAction: legacyActionLabel(action.id),
      lastActionId: action.id,
      lastActionSource: source,
      status
    });
  }

  function isActionDisabled(actionId: LegacyActionId): boolean {
    if (actionId === "file.save") return isBusy || !canSave;
    if (
      actionId === "file.open" ||
      actionId === "file.saveAs" ||
      actionId === "file.importSgf" ||
      actionId === "game.loadSample" ||
      actionId === "game.parseSgf" ||
      actionId === "analysis.runReview"
    ) {
      return isBusy;
    }
    return false;
  }

  const dispatchLegacyAction = useCallback(async (actionId: LegacyActionId, source: LegacyActionSource) => {
    const action = legacyActionMatrix.find((candidate) => candidate.id === actionId);
    if (!action) return;
    if (isActionDisabled(action.id)) {
      markActionStatus(action, source, "blocked");
      return;
    }

    try {
      if (action.target) {
        runMenuTargetAction(action.target, action, source);
        return;
      }

      markActionStatus(action, source, "dispatched");
      switch (action.id) {
        case "file.open":
          await onOpen();
          return;
        case "file.save":
          await onSave();
          return;
        case "file.saveAs":
          await onSaveAs();
          return;
        case "file.importSgf":
          importInputRef.current?.click();
          return;
        case "game.loadSample":
          await onLoadSample();
          return;
        case "game.parseSgf":
          await onParseSgf();
          return;
        case "analysis.runReview":
          await onRunReview();
          return;
      }
    } catch {
      markActionStatus(action, source, "failed");
    }
  }, [canSave, isBusy, onLoadSample, onOpen, onParseSgf, onRunReview, onSave, onSaveAs]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const actionId = legacyActionFromKeyboardEvent(event);
      if (!actionId) return;
      event.preventDefault();
      void dispatchLegacyAction(actionId, "keyboard");
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [dispatchLegacyAction]);

  useEffect(() => {
    let cleanup: (() => void) | null = null;
    let active = true;
    listenToLegacyMenuActionEvents((actionId) => {
      void dispatchLegacyAction(actionId, "native-menu");
    }).then((unlisten) => {
      if (active) {
        cleanup = unlisten;
      } else {
        unlisten();
      }
    });
    return () => {
      active = false;
      cleanup?.();
    };
  }, [dispatchLegacyAction]);

  const menuGroups: LegacyMenuGroup[] = useMemo(() => {
    const groups = new Map<LegacyMenuGroup["label"], LegacyMenuItem[]>();
    for (const action of legacyActionMatrix) {
      const items = groups.get(action.group) ?? [];
      items.push({ action, disabled: isActionDisabled(action.id) });
      groups.set(action.group, items);
    }
    return Array.from(groups.entries()).map(([label, items]) => ({ label, items }));
  }, [canSave, isBusy]);

  return (
    <main
      className={`app-shell legacy-shell${themeClassName ? ` ${themeClassName}` : ""}`}
      data-testid="legacy-shell"
      data-active-menu-target={menuAction.activeTarget ?? ""}
      data-last-legacy-action={menuAction.lastActionId}
      data-last-legacy-action-source={menuAction.lastActionSource}
      data-last-menu-action={menuAction.lastAction}
      data-menu-action-status={menuAction.status}
      data-legacy-action-count={legacyActionMatrix.length}
      data-legacy-action-ids={legacyActionMatrix.map((action) => action.id).join(" ")}
      data-legacy-shortcut-editing-protection="input,textarea,select,[contenteditable=true]"
      data-legacy-shortcut-input-editing-protected="true"
    >
      <header className="legacy-titlebar">
        <div className="legacy-appmark">
          <h1>LizzieYzy Next</h1>
          <p>{architectureLabel}</p>
        </div>
        <nav className="legacy-menubar" aria-label="Application menu" data-testid="legacy-menubar" data-legacy-menu-groups="File Game Analysis View Engine Tools Help">
          {menuGroups.map((group) => (
            <details key={group.label} className="legacy-menu" data-legacy-menu-group={group.label}>
              <summary>{group.label}</summary>
              <div className="legacy-menu-popover">
                {group.items.map((item) => (
                  <button
                    key={item.action.id}
                    type="button"
                    disabled={item.disabled}
                    {...actionData(item.action.id)}
                    data-menu-target={item.action.target ?? undefined}
                    data-menu-path={legacyActionMenuPath(item.action)}
                    data-shortcut={item.action.shortcut ?? undefined}
                    data-target-selector={item.action.targetSelector ?? undefined}
                    aria-controls={item.action.target ? menuTargetId(item.action.target) : undefined}
                    title={item.action.shortcut}
                    data-testid={`legacy-menu-${group.label.toLowerCase()}-${item.action.label.toLowerCase().replaceAll(" ", "-")}`}
                    onClick={(event) => {
                      void dispatchLegacyAction(item.action.id, "menu");
                      event.currentTarget.closest("details")?.removeAttribute("open");
                    }}
                  >
                    {item.action.label}
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
        <button type="button" data-testid="toolbar-open-sgf" {...actionData("file.open")} onClick={() => void dispatchLegacyAction("file.open", "toolbar")} disabled={isBusy} title="Open SGF">Open</button>
        <button type="button" data-testid="toolbar-save-sgf" {...actionData("file.save")} onClick={() => void dispatchLegacyAction("file.save", "toolbar")} disabled={isBusy || !canSave} title="Save SGF">Save</button>
        <button type="button" data-testid="toolbar-save-as-sgf" {...actionData("file.saveAs")} onClick={() => void dispatchLegacyAction("file.saveAs", "toolbar")} disabled={isBusy} title="Save SGF as">Save As</button>
        <label
          className={`file-button legacy-tool-file${isBusy ? " file-button-disabled" : ""}`}
          data-testid="toolbar-import-sgf"
          {...actionData("file.importSgf")}
          title="Import SGF"
        >
          Import
          <input ref={importInputRef} id={fileInputId} type="file" accept=".sgf,.txt,application/x-go-sgf,text/plain" disabled={isBusy} onChange={(event) => {
            void onImportFile(event.target.files?.[0] ?? null);
            event.currentTarget.value = "";
          }} />
        </label>
        <span className="legacy-toolbar-divider" aria-hidden="true" />
        <button type="button" data-testid="toolbar-load-sample" {...actionData("game.loadSample")} onClick={() => void dispatchLegacyAction("game.loadSample", "toolbar")} disabled={isBusy} title="Load sample game">Sample</button>
        <button type="button" data-testid="toolbar-parse-sgf" {...actionData("game.parseSgf")} onClick={() => void dispatchLegacyAction("game.parseSgf", "toolbar")} disabled={isBusy} title="Parse SGF source">Parse</button>
        <button type="button" data-testid="toolbar-run-review" {...actionData("analysis.runReview")} onClick={() => void dispatchLegacyAction("analysis.runReview", "toolbar")} disabled={isBusy} title="Run review">Review</button>
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
          <textarea data-testid="sgf-source-textarea" data-legacy-shortcut-scope="editable" data-legacy-shortcut-protected="true" value={sgfText} onChange={(event) => onSgfTextChange(event.target.value)} disabled={isBusy} spellCheck={false} aria-label="SGF source" />
          <div className="button-row">
            <button type="button" data-testid="sgf-source-open" onClick={() => void dispatchLegacyAction("file.open", "toolbar")} disabled={isBusy}>Open</button>
            <button type="button" data-testid="sgf-source-save" onClick={() => void dispatchLegacyAction("file.save", "toolbar")} disabled={isBusy || !canSave}>Save</button>
            <button type="button" data-testid="sgf-source-save-as" onClick={() => void dispatchLegacyAction("file.saveAs", "toolbar")} disabled={isBusy}>Save As</button>
            <label
              className={`file-button${isBusy ? " file-button-disabled" : ""}`}
            >
              Import SGF
              <input type="file" accept=".sgf,.txt,application/x-go-sgf,text/plain" disabled={isBusy} onChange={(event) => {
                void onImportFile(event.target.files?.[0] ?? null);
                event.currentTarget.value = "";
              }} />
            </label>
            <button type="button" data-testid="sgf-source-load-sample" onClick={() => void dispatchLegacyAction("game.loadSample", "toolbar")} disabled={isBusy}>Load sample</button>
            <button type="button" data-testid="sgf-source-parse" onClick={() => void dispatchLegacyAction("game.parseSgf", "toolbar")} disabled={isBusy}>Parse SGF</button>
            <button type="button" data-testid="sgf-source-run-review" onClick={() => void dispatchLegacyAction("analysis.runReview", "toolbar")} disabled={isBusy}>Run review</button>
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
