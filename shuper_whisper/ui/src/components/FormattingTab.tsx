import type { AppConfig, ConfigOptions } from "@/lib/types";
import { Sparkles, List } from "lucide-react";
import { StyledSelect } from "./StyledSelect";

interface FormattingTabProps {
  config: AppConfig;
  options: ConfigOptions;
  updateField: <K extends keyof AppConfig>(
    field: K,
    value: AppConfig[K]
  ) => void;
}

function SwitchToggle({
  icon: Icon,
  label,
  checked,
  onChange,
}: {
  icon: typeof Sparkles;
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-3.5">
      <div className="flex items-center gap-3">
        <Icon size={16} className="text-text-muted" />
        <span className="text-[13px] text-text-secondary">{label}</span>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative w-11 h-6 rounded-full transition-all duration-200 ${
          checked
            ? "bg-accent shadow-[0_0_12px_rgba(255,68,102,0.3)]"
            : "bg-white/10"
        }`}
      >
        <span
          className={`absolute top-[3px] w-[18px] h-[18px] rounded-full bg-white transition-all duration-200 shadow-sm ${
            checked ? "left-[23px]" : "left-[3px]"
          }`}
        />
      </button>
    </div>
  );
}

function SliderField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="py-3.5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[13px] text-text-secondary">{label}</span>
        <span className="glass-strong px-2.5 py-1 rounded text-[11px] text-text-primary font-medium min-w-[28px] text-center">
          {value}
        </span>
      </div>
      <div className="relative h-[6px] rounded-full bg-white/[0.06] overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-accent/60"
          style={{ width: `${pct}%` }}
        />
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value))}
        className="w-full -mt-[6px] relative z-10 opacity-0 cursor-pointer h-[20px]"
      />
    </div>
  );
}

export function FormattingTab({
  config,
  options,
  updateField,
}: FormattingTabProps) {
  const formatOptions = Object.entries(options.format_modes).map(
    ([value, label]) => ({ value, label })
  );

  return (
    <div className="space-y-6">
      {/* Default Format Mode */}
      <div>
        <label className="text-[13px] text-text-secondary block mb-2.5">
          Default Format Mode
        </label>
        <StyledSelect
          value={config.format_mode}
          onChange={(v) => updateField("format_mode", v)}
          options={formatOptions}
        />
      </div>

      {/* Smart Features */}
      <div className="glass rounded-xl p-6">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-2">
          Smart Features
        </h3>
        <SwitchToggle
          icon={Sparkles}
          label="Smart Spacing"
          checked={config.smart_spacing}
          onChange={(v) => updateField("smart_spacing", v)}
        />
        <div className="border-t border-white/[0.06]" />
        <SwitchToggle
          icon={List}
          label="Bullet Point Mode"
          checked={config.bullet_mode}
          onChange={(v) => updateField("bullet_mode", v)}
        />
      </div>

      {/* Tone Settings */}
      <div className="glass rounded-xl p-6">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-2">
          Tone Settings
        </h3>
        <SliderField
          label="Email Tone"
          value={config.email_tone}
          min={1}
          max={5}
          onChange={(v) => updateField("email_tone", v)}
        />
        <p className="text-[10px] text-text-muted mt-0.5 mb-3">
          1 = Warm &amp; friendly &nbsp; 3 = Standard &nbsp; 5 = Very formal
        </p>
        <div className="border-t border-white/[0.06]" />
        <SliderField
          label="Prompt Detail"
          value={config.prompt_detail}
          min={1}
          max={5}
          onChange={(v) => updateField("prompt_detail", v)}
        />
        <p className="text-[10px] text-text-muted mt-0.5">
          1 = Ultra-concise &nbsp; 3 = Balanced &nbsp; 5 = Comprehensive
        </p>
      </div>
    </div>
  );
}
