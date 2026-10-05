/** pywebview exposes a JS API on `window.pywebview.api`.
 *  ALL data communication between React and Python goes through this bridge,
 *  and every call has a timeout so a stuck backend can't freeze the page.
 */

import type {
  AppConfig,
  AppStatus,
  ConfigOptions,
  Device,
  DeviceRef,
  DictionaryEntry,
  GpuSetupProgress,
  GpuStatus,
  SaveResult,
  SystemInfo,
} from "./types";

interface PyWebViewAPI {
  close_window: () => Promise<void>;
  capture_hotkey: (timeout?: number) => Promise<string | null>;
  get_devices: () => Promise<Device[]>;
  get_config: () => Promise<AppConfig>;
  save_config: (data: Partial<AppConfig>) => Promise<SaveResult>;
  get_config_options: () => Promise<ConfigOptions>;
  get_status: () => Promise<AppStatus>;
  get_system_info: () => Promise<SystemInfo>;
  start_mic_test: (ref: DeviceRef | null) => Promise<{ success: boolean; error?: string }>;
  get_mic_level: () => Promise<number>;
  stop_mic_test: () => Promise<void>;
  get_autostart: () => Promise<boolean>;
  set_autostart: (enabled: boolean) => Promise<boolean>;
  get_gpu_status: () => Promise<GpuStatus>;
  setup_gpu: () => Promise<{ success: boolean }>;
  get_gpu_setup_progress: () => Promise<GpuSetupProgress>;
  cancel_gpu_setup: () => Promise<void>;
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
  train_word: (word: string) => Promise<{ success: boolean; error?: string }>;
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

function api(): PyWebViewAPI {
  const a = getApi();
  if (!a) throw new Error("Bridge not available");
  return a;
}

export function withTimeout<T>(p: Promise<T>, ms = 5000): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("ShuperWhisper didn't respond")), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      }
    );
  });
}

/** Ready once pywebview has filled in the API's functions: `window.pywebview`
 *  itself appears earlier, and calling into it then throws. */
function bridgeReady(): boolean {
  return typeof window.pywebview?.api?.get_config === "function";
}

let ready: Promise<void> | null = null;

/** pywebview injects the API object asynchronously. Every call waits for it,
 *  so nothing can run too early (the installed build loads slower than dev). */
export function waitForBridge(): Promise<void> {
  if (!ready) {
    ready = new Promise((resolve, reject) => {
      if (bridgeReady()) return resolve();
      const started = Date.now();
      const check = () => {
        if (bridgeReady()) {
          window.removeEventListener("pywebviewready", check);
          clearInterval(interval);
          resolve();
        } else if (Date.now() - started > 10_000) {
          clearInterval(interval);
          ready = null; // let a later call try again
          reject(new Error("ShuperWhisper didn't connect to this window. Close it and open Settings again."));
        }
      };
      window.addEventListener("pywebviewready", check);
      const interval = setInterval(check, 50);
    });
  }
  return ready;
}

/** Call the Python side once it's connected; ``ms`` bounds the call itself. */
function call<T>(fn: (a: PyWebViewAPI) => Promise<T>, ms?: number): Promise<T> {
  return waitForBridge().then(() => withTimeout(fn(api()), ms));
}

// Hotkey capture waits for the user, so it gets their 10 s plus slack.
export const captureHotkey = () => call((a) => a.capture_hotkey(10), 12_000);
export const closeWindow = () => call((a) => a.close_window());

export const getConfig = () => call((a) => a.get_config());
export const saveConfig = (config: Partial<AppConfig>) => call((a) => a.save_config(config), 10_000);
export const getConfigOptions = () => call((a) => a.get_config_options());
export const getDevices = () => call((a) => a.get_devices(), 8000);

export const getStatus = () => call((a) => a.get_status());
export const getSystemInfo = () => call((a) => a.get_system_info());
export const startMicTest = (ref: DeviceRef | null) => call((a) => a.start_mic_test(ref));
export const getMicLevel = () => call((a) => a.get_mic_level(), 1000);
export const stopMicTest = () => call((a) => a.stop_mic_test());
export const getAutostart = () => call((a) => a.get_autostart());
export const setAutostart = (on: boolean) => call((a) => a.set_autostart(on));
export const getGpuStatus = () => call((a) => a.get_gpu_status(), 8000);
export const setupGpu = () => call((a) => a.setup_gpu());
export const getGpuSetupProgress = () => call((a) => a.get_gpu_setup_progress(), 2000);
export const cancelGpuSetup = () => call((a) => a.cancel_gpu_setup());

export const getDictionary = () => call((a) => a.get_dictionary());
export const addWord = (word: string, phonetic = "") => call((a) => a.add_word(word, phonetic));
export const removeWord = (word: string) => call((a) => a.remove_word(word));
export const updateWord = (oldWord: string, newWord: string, phonetic = "") =>
  call((a) => a.update_word(oldWord, newWord, phonetic));
// Training records three rounds of ~3 s plus transcription.
export const trainWord = (word: string) => call((a) => a.train_word(word), 30_000);
