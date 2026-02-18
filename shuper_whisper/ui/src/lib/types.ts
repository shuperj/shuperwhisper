export interface AppConfig {
  hotkey: string;
  model_size: string;
  input_device: number | string | null;
  language: string;
  smart_spacing: boolean;
  bullet_mode: boolean;
  email_mode: boolean;
  hotkey_mode: string;
  format_mode: string;
  email_tone: number;
  prompt_detail: number;
  overlay_position: string;
  accent_color: string;
  bg_color: string;
}

export interface ConfigOptions {
  models: string[];
  languages: Record<string, string>;
  hotkey_modes: string[];
  format_modes: Record<string, string>;
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
