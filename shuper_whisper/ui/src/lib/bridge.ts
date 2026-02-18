/** pywebview exposes a JS API on `window.pywebview.api`.
 *  ALL data communication between React and Python goes through this bridge.
 */

import type {
  AppConfig,
  ConfigOptions,
  Device,
  DictionaryEntry,
} from "./types";

interface PyWebViewAPI {
  // Window
  close_window: () => Promise<void>;

  // Hotkey
  capture_hotkey: (timeout?: number) => Promise<string | null>;

  // Devices
  get_devices: () => Promise<Device[]>;

  // Config
  get_config: () => Promise<AppConfig>;
  save_config: (
    data: Partial<AppConfig>
  ) => Promise<{ success: boolean; config: AppConfig; error?: string }>;
  get_config_options: () => Promise<ConfigOptions>;

  // Dictionary
  get_dictionary: () => Promise<DictionaryEntry[]>;
  add_word: (
    word: string,
    phonetic: string
  ) => Promise<DictionaryEntry & { success?: boolean; error?: string }>;
  remove_word: (word: string) => Promise<boolean>;
  update_word: (
    old_word: string,
    new_word: string,
    phonetic: string
  ) => Promise<{ success: boolean; error?: string }>;
  train_word: (
    word: string
  ) => Promise<{ success: boolean; transcribed?: string; error?: string }>;
}

declare global {
  interface Window {
    pywebview?: { api: PyWebViewAPI };
    __onTrainingStatus?: (data: unknown) => void;
  }
}

function getApi(): PyWebViewAPI | null {
  return window.pywebview?.api ?? null;
}

// ------------------------------------------------------------------
// Bridge readiness — pywebview injects the API object asynchronously
// ------------------------------------------------------------------

export function waitForBridge(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.pywebview) return resolve();

    let resolved = false;
    const done = () => {
      if (resolved) return;
      resolved = true;
      resolve();
    };

    // Listen for the standard pywebview event
    window.addEventListener("pywebviewready", done, { once: true });

    // Poll as fallback in case the event fired before our listener
    const interval = setInterval(() => {
      if (window.pywebview) {
        clearInterval(interval);
        done();
      }
    }, 100);

    // Timeout after 10 seconds
    setTimeout(() => {
      clearInterval(interval);
      if (!resolved) {
        resolved = true;
        if (window.pywebview) {
          resolve();
        } else {
          reject(new Error("pywebview bridge not available after 10s"));
        }
      }
    }, 10_000);
  });
}

export function isBridgeAvailable(): boolean {
  return getApi() !== null;
}

// ------------------------------------------------------------------
// Window management
// ------------------------------------------------------------------

export async function closeWindow(): Promise<void> {
  const api = getApi();
  if (!api) {
    window.close();
    return;
  }
  return api.close_window();
}

// ------------------------------------------------------------------
// Hotkey capture
// ------------------------------------------------------------------

export async function captureHotkey(
  timeout: number = 10
): Promise<string | null> {
  const api = getApi();
  if (!api) {
    console.warn("pywebview bridge not available");
    return null;
  }
  return api.capture_hotkey(timeout);
}

// ------------------------------------------------------------------
// Config
// ------------------------------------------------------------------

export async function getConfig(): Promise<AppConfig> {
  const api = getApi();
  if (!api) throw new Error("Bridge not available");
  return api.get_config();
}

export async function saveConfig(
  config: Partial<AppConfig>
): Promise<{ success: boolean; config: AppConfig }> {
  const api = getApi();
  if (!api) throw new Error("Bridge not available");
  return api.save_config(config);
}

export async function getConfigOptions(): Promise<ConfigOptions> {
  const api = getApi();
  if (!api) throw new Error("Bridge not available");
  return api.get_config_options();
}

// ------------------------------------------------------------------
// Devices
// ------------------------------------------------------------------

export async function getDevices(): Promise<Device[]> {
  const api = getApi();
  if (!api) return [];
  return api.get_devices();
}

// ------------------------------------------------------------------
// Dictionary
// ------------------------------------------------------------------

export async function getDictionary(): Promise<DictionaryEntry[]> {
  const api = getApi();
  if (!api) return [];
  return api.get_dictionary();
}

export async function addWord(
  word: string,
  phonetic: string = ""
): Promise<DictionaryEntry> {
  const api = getApi();
  if (!api) throw new Error("Bridge not available");
  return api.add_word(word, phonetic);
}

export async function removeWord(word: string): Promise<boolean> {
  const api = getApi();
  if (!api) return false;
  return api.remove_word(word);
}

export async function updateWord(
  oldWord: string,
  newWord: string,
  phonetic: string = ""
): Promise<{ success: boolean; error?: string }> {
  const api = getApi();
  if (!api) throw new Error("Bridge not available");
  return api.update_word(oldWord, newWord, phonetic);
}

export async function trainWord(
  word: string
): Promise<{ success: boolean; transcribed?: string }> {
  const api = getApi();
  if (!api) throw new Error("Bridge not available");
  return api.train_word(word);
}
