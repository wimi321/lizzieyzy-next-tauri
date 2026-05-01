import { invoke } from "@tauri-apps/api/core";
import { defaultAppPreferences, normalizeAppPreferences, type AppPreferences } from "../domain/preferences";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

const browserPreferencesKey = "lizzieyzy-next-app-preferences";
const isTauriRuntime = () => typeof window !== "undefined" && window.__TAURI_INTERNALS__ !== undefined;

export async function loadAppPreferences(): Promise<AppPreferences> {
  if (!isTauriRuntime()) return loadBrowserPreferences();
  return normalizeAppPreferences(await invoke<AppPreferences>("load_app_preferences"));
}

export async function saveAppPreferences(preferences: AppPreferences): Promise<AppPreferences> {
  const normalized = normalizeAppPreferences(preferences);
  if (!isTauriRuntime()) {
    saveBrowserPreferences(normalized);
    return normalized;
  }
  return normalizeAppPreferences(await invoke<AppPreferences>("save_app_preferences", { preferences: normalized }));
}

function loadBrowserPreferences(): AppPreferences {
  if (typeof window === "undefined") return defaultAppPreferences;
  const raw = window.localStorage.getItem(browserPreferencesKey);
  if (!raw) return defaultAppPreferences;
  try {
    return normalizeAppPreferences(JSON.parse(raw) as Partial<AppPreferences>);
  } catch {
    return defaultAppPreferences;
  }
}

function saveBrowserPreferences(preferences: AppPreferences) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(browserPreferencesKey, JSON.stringify(preferences));
}
