export type LegacyActionSource = "menu" | "toolbar" | "keyboard" | "native-menu";

export type LegacyMenuTarget =
  | "candidates"
  | "ownership"
  | "policy"
  | "profiles"
  | "assets"
  | "providers"
  | "preferences"
  | "backend-status";

export type LegacyActionId =
  | "file.open"
  | "file.save"
  | "file.saveAs"
  | "file.importSgf"
  | "game.loadSample"
  | "game.parseSgf"
  | "analysis.runReview"
  | "analysis.katagoPanel"
  | "view.candidates"
  | "view.ownership"
  | "view.policy"
  | "engine.profiles"
  | "engine.assets"
  | "tools.providers"
  | "tools.preferences"
  | "help.backendStatus";

export type LegacyActionDefinition = {
  id: LegacyActionId;
  group: "File" | "Game" | "Analysis" | "View" | "Engine" | "Tools" | "Help";
  label: string;
  target?: LegacyMenuTarget;
  shortcut?: string;
};

export const legacyActionMatrix: LegacyActionDefinition[] = [
  { id: "file.open", group: "File", label: "Open", shortcut: "Mod+O" },
  { id: "file.save", group: "File", label: "Save", shortcut: "Mod+S" },
  { id: "file.saveAs", group: "File", label: "Save As", shortcut: "Mod+Shift+S" },
  { id: "file.importSgf", group: "File", label: "Import SGF", shortcut: "Mod+I" },
  { id: "game.loadSample", group: "Game", label: "Load sample", shortcut: "Mod+Shift+L" },
  { id: "game.parseSgf", group: "Game", label: "Parse SGF", shortcut: "Mod+Enter" },
  { id: "analysis.runReview", group: "Analysis", label: "Run review", shortcut: "Mod+R" },
  { id: "analysis.katagoPanel", group: "Analysis", label: "KataGo panel", target: "profiles", shortcut: "Mod+Shift+K" },
  { id: "view.candidates", group: "View", label: "Candidates", target: "candidates", shortcut: "Mod+1" },
  { id: "view.ownership", group: "View", label: "Ownership", target: "ownership", shortcut: "Mod+2" },
  { id: "view.policy", group: "View", label: "Policy", target: "policy", shortcut: "Mod+3" },
  { id: "engine.profiles", group: "Engine", label: "Profiles", target: "profiles", shortcut: "Mod+4" },
  { id: "engine.assets", group: "Engine", label: "Assets", target: "assets", shortcut: "Mod+5" },
  { id: "tools.providers", group: "Tools", label: "Providers", target: "providers", shortcut: "Mod+6" },
  { id: "tools.preferences", group: "Tools", label: "Preferences", target: "preferences", shortcut: "Mod+7" },
  { id: "help.backendStatus", group: "Help", label: "Backend status", target: "backend-status", shortcut: "Mod+/" }
];

const legacyActionById = new Map<LegacyActionId, LegacyActionDefinition>(
  legacyActionMatrix.map((action) => [action.id, action])
);

const legacyActionAliases = new Map<string, LegacyActionId>([
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
  ["help:backend_status", "help.backendStatus"]
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

  if (key === "o" && !event.shiftKey) return "file.open";
  if (key === "s" && !event.shiftKey) return "file.save";
  if (key === "s" && event.shiftKey) return "file.saveAs";
  if (key === "i" && !event.shiftKey) return "file.importSgf";
  if (key === "l" && event.shiftKey) return "game.loadSample";
  if (key === "enter" && !event.shiftKey) return "game.parseSgf";
  if (key === "r" && !event.shiftKey) return "analysis.runReview";
  if (key === "k" && event.shiftKey) return "analysis.katagoPanel";
  if (key === "1" && !event.shiftKey) return "view.candidates";
  if (key === "2" && !event.shiftKey) return "view.ownership";
  if (key === "3" && !event.shiftKey) return "view.policy";
  if (key === "4" && !event.shiftKey) return "engine.profiles";
  if (key === "5" && !event.shiftKey) return "engine.assets";
  if (key === "6" && !event.shiftKey) return "tools.providers";
  if (key === "7" && !event.shiftKey) return "tools.preferences";
  if (key === "/" && !event.shiftKey) return "help.backendStatus";
  return null;
}
