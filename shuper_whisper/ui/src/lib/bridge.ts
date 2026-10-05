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

/** pywebview injects the API object asynchronously. */
export function waitForBridge(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.pywebview) return resolve();
    let resolved = false;
    const done = () => {
      if (resolved) return;
      resolved = true;
      resolve();
    };
    window.addEventListener("pywebviewready", done, { once: true });
    const interval = setInterval(() => {
      if (window.pywebview) {
        clearInterval(interval);
        done();
      }
    }, 100);
    setTimeout(() => {
      clearInterval(interval);
      if (!resolved) {
        resolved = true;
        if (window.pywebview) resolve();
        else reject(new Error("pywebview bridge not available after 10s"));
      }
    }, 10_000);
  });
}

// Hotkey capture waits for the user, so it gets their 10 s plus slack.
export const captureHotkey = () => withTimeout(api().capture_hotkey(10), 12_000);
export const closeWindow = () => withTimeout(api().close_window());

export const getConfig = () => withTimeout(api().get_config());
export const saveConfig = (config: Partial<AppConfig>) => withTimeout(api().save_config(config), 10_000);
export const getConfigOptions = () => withTimeout(api().get_config_options());
export const getDevices = () => withTimeout(api().get_devices(), 8000);

export const getStatus = () => withTimeout(api().get_status());
export const getSystemInfo = () => withTimeout(api().get_system_info());
export const startMicTest = (ref: DeviceRef | null) => withTimeout(api().start_mic_test(ref));
export const getMicLevel = () => withTimeout(api().get_mic_level(), 1000);
export const stopMicTest = () => withTimeout(api().stop_mic_test());
export const getAutostart = () => withTimeout(api().get_autostart());
export const setAutostart = (on: boolean) => withTimeout(api().set_autostart(on));
export const getGpuStatus = () => withTimeout(api().get_gpu_status(), 8000);
export const setupGpu = () => withTimeout(api().setup_gpu());
export const getGpuSetupProgress = () => withTimeout(api().get_gpu_setup_progress(), 2000);
export const cancelGpuSetup = () => withTimeout(api().cancel_gpu_setup());

export const getDictionary = () => withTimeout(api().get_dictionary());
export const addWord = (word: string, phonetic = "") => withTimeout(api().add_word(word, phonetic));
export const removeWord = (word: string) => withTimeout(api().remove_word(word));
export const updateWord = (oldWord: string, newWord: string, phonetic = "") =>
  withTimeout(api().update_word(oldWord, newWord, phonetic));
// Training records three rounds of ~3 s plus transcription.
export const trainWord = (word: string) => withTimeout(api().train_word(word), 30_000);
