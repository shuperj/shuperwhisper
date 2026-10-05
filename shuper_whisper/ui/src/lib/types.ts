export interface DeviceRef {
  name: string;
  hostapi: string | null;
}

export interface AppConfig {
  hotkey: string;
  model_size: string;
  input_device: DeviceRef | null;
  language: string;
  overlay_position: string;
  compute: "auto" | "cpu";
}

export interface ConfigOptions {
  models: string[];
  languages: Record<string, string>;
  overlay_positions: string[];
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
