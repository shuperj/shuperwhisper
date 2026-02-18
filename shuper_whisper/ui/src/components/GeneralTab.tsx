import { useState } from "react";
import type { AppConfig, ConfigOptions, Device } from "@/lib/types";
import { captureHotkey } from "@/lib/bridge";
import { Keyboard, Mic, Globe, MapPin, Palette } from "lucide-react";
import { StyledSelect } from "./StyledSelect";

interface GeneralTabProps {
  config: AppConfig;
  options: ConfigOptions;
  devices: Device[];
  updateField: <K extends keyof AppConfig>(
    field: K,
    value: AppConfig[K]
  ) => void;
}

function FieldRow({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Keyboard;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-4 py-4">
      <div className="flex items-center gap-3 w-[150px] shrink-0">
        <Icon size={16} className="text-text-muted" />
        <label className="text-[13px] text-text-secondary">{label}</label>
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}


export function GeneralTab({
  config,
  options,
  devices,
  updateField,
}: GeneralTabProps) {
  const [isCapturing, setIsCapturing] = useState(false);

  const handleCaptureHotkey = async () => {
    setIsCapturing(true);
    try {
      const key = await captureHotkey();
      if (key) {
        updateField("hotkey", key);
      }
    } finally {
      setIsCapturing(false);
    }
  };

  const languageOptions = Object.entries(options.languages).map(
    ([code, name]) => ({
      value: code,
      label: `${name}`,
    })
  );

  const modelOptions = options.models.map((m) => ({
    value: m,
    label: m.charAt(0).toUpperCase() + m.slice(1),
  }));

  const deviceOptions = [
    { value: "__default__", label: "System Default" },
    ...devices.map((d) => ({
      value: String(d.index),
      label: d.name,
    })),
  ];

  const positionLabels: Record<string, string> = {
    top_center: "Top Center",
    center: "Center",
    bottom_center: "Bottom Center",
  };
  const positionOptions = options.overlay_positions.map((p) => ({
    value: p,
    label: positionLabels[p] || p,
  }));

  return (
    <div>
      {/* Hotkey */}
      <FieldRow icon={Keyboard} label="Hotkey">
        <button
          onClick={handleCaptureHotkey}
          className={`glass-input w-full px-4 py-2.5 rounded-lg text-[13px] text-left
            ${isCapturing ? "border-accent animate-pulse-glow text-accent" : "text-text-primary"}`}
        >
          {isCapturing ? "Press keys..." : config.hotkey}
        </button>
      </FieldRow>

      <p className="text-[11px] text-text-muted pl-[162px] -mt-2 mb-2">
        Quick tap = toggle mode | Hold = hold mode
      </p>

      <div className="border-t border-white/[0.06]" />

      {/* Model */}
      <FieldRow icon={Mic} label="Model">
        <StyledSelect
          value={config.model_size}
          onChange={(v) => updateField("model_size", v)}
          options={modelOptions}
        />
      </FieldRow>

      <div className="border-t border-white/[0.06]" />

      {/* Language */}
      <FieldRow icon={Globe} label="Language">
        <StyledSelect
          value={config.language}
          onChange={(v) => updateField("language", v)}
          options={languageOptions}
        />
      </FieldRow>

      <div className="border-t border-white/[0.06]" />

      {/* Input Device */}
      <FieldRow icon={Mic} label="Input Device">
        <StyledSelect
          value={config.input_device !== null ? String(config.input_device) : "__default__"}
          onChange={(v) =>
            updateField("input_device", v === "__default__" ? null : parseInt(v))
          }
          options={deviceOptions}
        />
      </FieldRow>

      <div className="border-t border-white/[0.06]" />

      {/* Overlay Position */}
      <FieldRow icon={MapPin} label="Overlay Position">
        <StyledSelect
          value={config.overlay_position}
          onChange={(v) => updateField("overlay_position", v)}
          options={positionOptions}
        />
      </FieldRow>

      {/* Appearance */}
      <div className="glass rounded-xl p-6 mt-6">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-5">
          Appearance
        </h3>
        <div className="flex items-center gap-10">
          <div className="flex items-center gap-3">
            <Palette size={16} className="text-text-muted" />
            <label className="text-[13px] text-text-secondary">Accent</label>
            <input
              type="color"
              value={config.accent_color}
              onChange={(e) => updateField("accent_color", e.target.value)}
              className="w-10 h-10"
            />
          </div>
          <div className="flex items-center gap-3">
            <Palette size={16} className="text-text-muted" />
            <label className="text-[13px] text-text-secondary">Background</label>
            <input
              type="color"
              value={config.bg_color}
              onChange={(e) => updateField("bg_color", e.target.value)}
              className="w-10 h-10"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
