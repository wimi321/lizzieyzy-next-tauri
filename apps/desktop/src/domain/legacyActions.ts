export type LegacyActionSource = "menu" | "toolbar" | "keyboard" | "native-menu";
export type LegacyActionGroup = "File" | "Game" | "Analysis" | "View" | "Engine" | "Tools" | "Help";

export type LegacyMenuTarget =
  | "about"
  | "candidates"
  | "ownership"
  | "policy"
  | "sgf-source"
  | "timeline"
  | "profiles"
  | "assets"
  | "providers"
  | "preferences"
  | "backend-status";

export type LegacyActionId =
  | "file.new"
  | "file.open"
  | "file.save"
  | "file.saveAs"
  | "file.importSgf"
  | "game.loadSample"
  | "game.parseSgf"
  | "game.firstMove"
  | "game.previousMove"
  | "game.nextMove"
  | "game.lastMove"
  | "analysis.runReview"
  | "analysis.katagoPanel"
  | "view.candidates"
  | "view.ownership"
  | "view.policy"
  | "view.sgfSource"
  | "engine.profiles"
  | "engine.assets"
  | "tools.providers"
  | "tools.preferences"
  | "help.backendStatus"
  | "help.about";

export type LegacyActionDefinition = {
  id: LegacyActionId;
  group: LegacyActionGroup;
  label: string;
  menuPath: readonly [LegacyActionGroup, string];
  target?: LegacyMenuTarget;
  targetSelector?: string;
  shortcut?: string;
};

export const legacyActionMatrix: LegacyActionDefinition[] = [
  { id: "file.new", group: "File", label: "New", menuPath: ["File", "New"], targetSelector: "[data-testid='legacy-shell']", shortcut: "Mod+N" },
  { id: "file.open", group: "File", label: "Open", menuPath: ["File", "Open"], targetSelector: "[data-testid='toolbar-open-sgf']", shortcut: "Mod+O" },
  { id: "file.save", group: "File", label: "Save", menuPath: ["File", "Save"], targetSelector: "[data-testid='toolbar-save-sgf']", shortcut: "Mod+S" },
  { id: "file.saveAs", group: "File", label: "Save As", menuPath: ["File", "Save As"], targetSelector: "[data-testid='toolbar-save-as-sgf']", shortcut: "Mod+Shift+S" },
  { id: "file.importSgf", group: "File", label: "Import SGF", menuPath: ["File", "Import SGF"], targetSelector: "[data-testid='toolbar-import-sgf']", shortcut: "Mod+I" },
  { id: "game.loadSample", group: "Game", label: "Load sample", menuPath: ["Game", "Load sample"], targetSelector: "[data-testid='toolbar-load-sample']", shortcut: "Mod+Shift+L" },
  { id: "game.parseSgf", group: "Game", label: "Parse SGF", menuPath: ["Game", "Parse SGF"], targetSelector: "[data-testid='toolbar-parse-sgf']", shortcut: "Mod+Enter" },
  { id: "game.firstMove", group: "Game", label: "First move", menuPath: ["Game", "First move"], target: "timeline", targetSelector: "[data-testid='legacy-move-slider']", shortcut: "Mod+ArrowLeft" },
  { id: "game.previousMove", group: "Game", label: "Previous move", menuPath: ["Game", "Previous move"], target: "timeline", targetSelector: "[data-testid='legacy-move-slider']", shortcut: "Mod+Shift+ArrowLeft" },
  { id: "game.nextMove", group: "Game", label: "Next move", menuPath: ["Game", "Next move"], target: "timeline", targetSelector: "[data-testid='legacy-move-slider']", shortcut: "Mod+Shift+ArrowRight" },
  { id: "game.lastMove", group: "Game", label: "Last move", menuPath: ["Game", "Last move"], target: "timeline", targetSelector: "[data-testid='legacy-move-slider']", shortcut: "Mod+ArrowRight" },
  { id: "analysis.runReview", group: "Analysis", label: "Run review", menuPath: ["Analysis", "Run review"], targetSelector: "[data-testid='toolbar-run-review']", shortcut: "Mod+R" },
  { id: "analysis.katagoPanel", group: "Analysis", label: "KataGo panel", menuPath: ["Analysis", "KataGo panel"], target: "profiles", targetSelector: "[data-testid='engine-setup-panel']", shortcut: "Mod+Shift+K" },
  { id: "view.candidates", group: "View", label: "Candidates", menuPath: ["View", "Candidates"], target: "candidates", targetSelector: "[data-testid='analysis-panel']", shortcut: "Mod+1" },
  { id: "view.ownership", group: "View", label: "Ownership", menuPath: ["View", "Ownership"], target: "ownership", targetSelector: "[data-testid='legacy-board-pane']", shortcut: "Mod+2" },
  { id: "view.policy", group: "View", label: "Policy", menuPath: ["View", "Policy"], target: "policy", targetSelector: "[data-testid='analysis-panel']", shortcut: "Mod+3" },
  { id: "view.sgfSource", group: "View", label: "SGF source", menuPath: ["View", "SGF source"], target: "sgf-source", targetSelector: "[data-testid='sgf-source-textarea']", shortcut: "Mod+8" },
  { id: "engine.profiles", group: "Engine", label: "Profiles", menuPath: ["Engine", "Profiles"], target: "profiles", targetSelector: "[data-testid='engine-setup-panel']", shortcut: "Mod+4" },
  { id: "engine.assets", group: "Engine", label: "Assets", menuPath: ["Engine", "Assets"], target: "assets", targetSelector: "[data-testid='engine-check-assets']", shortcut: "Mod+5" },
  { id: "tools.providers", group: "Tools", label: "Providers", menuPath: ["Tools", "Providers"], target: "providers", targetSelector: "[data-testid='provider-panel']", shortcut: "Mod+6" },
  { id: "tools.preferences", group: "Tools", label: "Preferences", menuPath: ["Tools", "Preferences"], target: "preferences", targetSelector: "[data-testid='preferences-panel']", shortcut: "Mod+7" },
  { id: "help.backendStatus", group: "Help", label: "Backend status", menuPath: ["Help", "Backend status"], target: "backend-status", targetSelector: "[data-testid='legacy-statusbar']", shortcut: "Mod+/" },
  { id: "help.about", group: "Help", label: "About", menuPath: ["Help", "About"], target: "about", targetSelector: "[data-testid='legacy-about-target']", shortcut: "Mod+Shift+/" }
];

const legacyActionById = new Map<LegacyActionId, LegacyActionDefinition>(
  legacyActionMatrix.map((action) => [action.id, action])
);

const legacyActionAliases = new Map<string, LegacyActionId>([
  ["new", "file.new"],
  ["file.new", "file.new"],
  ["file:new", "file.new"],
  ["open", "file.open"],
  ["file.open", "file.open"],
  ["file:open", "file.open"],
  ["save", "file.save"],
  ["file.save", "file.save"],
  ["file:save", "file.save"],
  ["save-as", "file.saveAs"],
  ["save_as", "file.saveAs"],
  ["file.save-as", "file.saveAs"],
  ["file.save_as", "file.saveAs"],
  ["file.saveAs", "file.saveAs"],
  ["file:save-as", "file.saveAs"],
  ["file:save_as", "file.saveAs"],
  ["import-sgf", "file.importSgf"],
  ["import_sgf", "file.importSgf"],
  ["file.import-sgf", "file.importSgf"],
  ["file.import_sgf", "file.importSgf"],
  ["file.importSgf", "file.importSgf"],
  ["file:import-sgf", "file.importSgf"],
  ["file:import_sgf", "file.importSgf"],
  ["load-sample", "game.loadSample"],
  ["load_sample", "game.loadSample"],
  ["game.load-sample", "game.loadSample"],
  ["game.load_sample", "game.loadSample"],
  ["game.loadSample", "game.loadSample"],
  ["game:load-sample", "game.loadSample"],
  ["game:load_sample", "game.loadSample"],
  ["parse-sgf", "game.parseSgf"],
  ["parse_sgf", "game.parseSgf"],
  ["game.parse-sgf", "game.parseSgf"],
  ["game.parse_sgf", "game.parseSgf"],
  ["game.parseSgf", "game.parseSgf"],
  ["game:parse-sgf", "game.parseSgf"],
  ["game:parse_sgf", "game.parseSgf"],
  ["first-move", "game.firstMove"],
  ["first_move", "game.firstMove"],
  ["game.first-move", "game.firstMove"],
  ["game.first_move", "game.firstMove"],
  ["game.firstMove", "game.firstMove"],
  ["game:first-move", "game.firstMove"],
  ["game:first_move", "game.firstMove"],
  ["previous-move", "game.previousMove"],
  ["previous_move", "game.previousMove"],
  ["game.previous-move", "game.previousMove"],
  ["game.previous_move", "game.previousMove"],
  ["game.previousMove", "game.previousMove"],
  ["game:previous-move", "game.previousMove"],
  ["game:previous_move", "game.previousMove"],
  ["next-move", "game.nextMove"],
  ["next_move", "game.nextMove"],
  ["game.next-move", "game.nextMove"],
  ["game.next_move", "game.nextMove"],
  ["game.nextMove", "game.nextMove"],
  ["game:next-move", "game.nextMove"],
  ["game:next_move", "game.nextMove"],
  ["last-move", "game.lastMove"],
  ["last_move", "game.lastMove"],
  ["game.last-move", "game.lastMove"],
  ["game.last_move", "game.lastMove"],
  ["game.lastMove", "game.lastMove"],
  ["game:last-move", "game.lastMove"],
  ["game:last_move", "game.lastMove"],
  ["run-review", "analysis.runReview"],
  ["run_review", "analysis.runReview"],
  ["analysis.run-review", "analysis.runReview"],
  ["analysis.run_review", "analysis.runReview"],
  ["analysis.runReview", "analysis.runReview"],
  ["analysis:run-review", "analysis.runReview"],
  ["analysis:run_review", "analysis.runReview"],
  ["katago-panel", "analysis.katagoPanel"],
  ["katago_panel", "analysis.katagoPanel"],
  ["analysis.katago-panel", "analysis.katagoPanel"],
  ["analysis.katago_panel", "analysis.katagoPanel"],
  ["analysis.katagoPanel", "analysis.katagoPanel"],
  ["analysis:katago-panel", "analysis.katagoPanel"],
  ["analysis:katago_panel", "analysis.katagoPanel"],
  ["candidates", "view.candidates"],
  ["view.candidates", "view.candidates"],
  ["view:candidates", "view.candidates"],
  ["ownership", "view.ownership"],
  ["view.ownership", "view.ownership"],
  ["view:ownership", "view.ownership"],
  ["policy", "view.policy"],
  ["view.policy", "view.policy"],
  ["view:policy", "view.policy"],
  ["sgf-source", "view.sgfSource"],
  ["sgf_source", "view.sgfSource"],
  ["view.sgf-source", "view.sgfSource"],
  ["view.sgf_source", "view.sgfSource"],
  ["view.sgfSource", "view.sgfSource"],
  ["view:sgf-source", "view.sgfSource"],
  ["view:sgf_source", "view.sgfSource"],
  ["profiles", "engine.profiles"],
  ["engine.profiles", "engine.profiles"],
  ["engine:profiles", "engine.profiles"],
  ["assets", "engine.assets"],
  ["engine.assets", "engine.assets"],
  ["engine:assets", "engine.assets"],
  ["providers", "tools.providers"],
  ["tools.providers", "tools.providers"],
  ["tools:providers", "tools.providers"],
  ["preferences", "tools.preferences"],
  ["tools.preferences", "tools.preferences"],
  ["tools:preferences", "tools.preferences"],
  ["backend-status", "help.backendStatus"],
  ["backend_status", "help.backendStatus"],
  ["help.backend-status", "help.backendStatus"],
  ["help.backend_status", "help.backendStatus"],
  ["help.backendStatus", "help.backendStatus"],
  ["help:backend-status", "help.backendStatus"],
  ["help:backend_status", "help.backendStatus"],
  ["about", "help.about"],
  ["help.about", "help.about"],
  ["help:about", "help.about"]
]);

export function legacyActionDefinition(id: LegacyActionId): LegacyActionDefinition {
  return legacyActionById.get(id) ?? legacyActionMatrix[0];
}

export function normalizeLegacyActionId(value: unknown): LegacyActionId | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  return legacyActionAliases.get(trimmed) ?? legacyActionAliases.get(trimmed.toLowerCase()) ?? null;
}

export function legacyActionLabel(id: LegacyActionId): string {
  const action = legacyActionDefinition(id);
  return `${action.group}:${action.label}`;
}

export function legacyActionMenuPath(action: LegacyActionDefinition): string {
  return action.menuPath.join(" > ");
}

export function legacyActionTestId(id: LegacyActionId): string {
  return `legacy-action-${id.replaceAll(".", "-")}`;
}

export function legacyShortcutAria(shortcut: string | undefined): string | undefined {
  if (!shortcut) return undefined;
  const mac = shortcut.replace("Mod", "Meta");
  const control = shortcut.replace("Mod", "Control");
  return mac === control ? mac : `${mac} ${control}`;
}

export function shouldIgnoreLegacyShortcut(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
}

export function legacyActionFromKeyboardEvent(event: KeyboardEvent): LegacyActionId | null {
  if (shouldIgnoreLegacyShortcut(event.target)) return null;
  const usesModifier = event.metaKey || event.ctrlKey;
  if (!usesModifier || event.altKey) return null;
  const key = event.key.toLowerCase();

  if (key === "n" && !event.shiftKey) return "file.new";
  if (key === "o" && !event.shiftKey) return "file.open";
  if (key === "s" && !event.shiftKey) return "file.save";
  if (key === "s" && event.shiftKey) return "file.saveAs";
  if (key === "i" && !event.shiftKey) return "file.importSgf";
  if (key === "l" && event.shiftKey) return "game.loadSample";
  if (key === "enter" && !event.shiftKey) return "game.parseSgf";
  if (key === "arrowleft" && !event.shiftKey) return "game.firstMove";
  if (key === "arrowleft" && event.shiftKey) return "game.previousMove";
  if (key === "arrowright" && event.shiftKey) return "game.nextMove";
  if (key === "arrowright" && !event.shiftKey) return "game.lastMove";
  if (key === "r" && !event.shiftKey) return "analysis.runReview";
  if (key === "k" && event.shiftKey) return "analysis.katagoPanel";
  if (key === "1" && !event.shiftKey) return "view.candidates";
  if (key === "2" && !event.shiftKey) return "view.ownership";
  if (key === "3" && !event.shiftKey) return "view.policy";
  if (key === "4" && !event.shiftKey) return "engine.profiles";
  if (key === "5" && !event.shiftKey) return "engine.assets";
  if (key === "6" && !event.shiftKey) return "tools.providers";
  if (key === "7" && !event.shiftKey) return "tools.preferences";
  if (key === "8" && !event.shiftKey) return "view.sgfSource";
  if (key === "/" && !event.shiftKey) return "help.backendStatus";
  if (key === "/" && event.shiftKey) return "help.about";
  return null;
}
