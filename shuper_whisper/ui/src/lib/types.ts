export interface DeviceRef {
  name: string;
  hostapi: string | null;
}

export interface AppConfig {
  hotkey: string;
  model_size: string;
  input_device: DeviceRef | null;
  language: string;
  compute: "auto" | "cpu";
  live_typing: "auto" | "on" | "off";
}

export interface ConfigOptions {
  models: string[];
  languages: Record<string, string>;
}

export interface DictionaryEntry {
  word: string;
  phonetic: string;
  trained: boolean;
}

export interface Device {
  index: number;
  name: string;
  hostapi: string;
  hostapi_label: string;
  channels: number;
  samplerate: number;
  is_default: boolean;
}

export interface SystemInfo {
  dark: boolean;
  accent: { light: string; dark: string };
  compute: string;
}

export interface AppStatus {
  state: "idle" | "recording" | "processing" | "loading" | "error";
  error: string | null;
  /** What the last settings change couldn't apply (it kept its old value). */
  reload_error: string | null;
}

export interface GpuStatus {
  gpu: string | null;
  installed: boolean;
  active: boolean;
}

export interface GpuSetupProgress {
  state: "idle" | "downloading" | "extracting" | "activating" | "done" | "error" | "cancelled";
  fraction: number;
  message: string;
}

export interface SaveResult {
  success: boolean;
  config?: AppConfig;
  loading?: boolean;
  error?: string;
}

export interface TrainingStatus {
  status: "recording" | "transcribing" | "round_done" | "done" | "error";
  word: string;
  round?: number;
  totalRounds?: number;
  success?: boolean;
  alreadyRecognized?: boolean;
  learnedHint?: string | null;
  matchCount?: number;
  roundSuccess?: boolean;
  transcribed?: string;
  results?: Array<{ round: number; transcribed: string; success: boolean }>;
  error?: string;
}
