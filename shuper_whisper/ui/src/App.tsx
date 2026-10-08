import { useEffect, useState } from "react";
import { Cpu, Globe, Hand, Leaf, Power } from "lucide-react";
import { useSettings } from "@/hooks/useSettings";
import type { AppConfig } from "@/lib/types";
import { useTraining } from "@/hooks/useTraining";
import { getAutostart, getStatus, setAutostart } from "@/lib/bridge";
import { Card, Section, Select, Toggle } from "@/components/fluent";
import { ShortcutCard } from "@/components/ShortcutCard";
import { MicrophoneCard } from "@/components/MicrophoneCard";
import { ProcessingSection } from "@/components/ProcessingSection";
import { DictionarySection } from "@/components/DictionarySection";

// Memory and accuracy from benchmarks/results/*-full.md (live typing, real speech).
const MODEL_LABELS: Record<string, string> = {
  auto: "Automatic: Base (recommended)",
  "large-v3-turbo": "Large v3 Turbo (1.5 GB)",
  small: "Small (1 GB)",
  base: "Base (0.6 GB)",
  tiny: "Tiny (0.4 GB)",
};

export default function App() {
  const {
    config,
    options,
    devices,
    system,
    status,
    loading,
    loadError,
    errors,
    apply,
    refreshSystem,
    pollUntilSettled,
  } = useSettings();
  const { trainingStatus, clearTraining } = useTraining();
  const [autostart, setAutostartState] = useState<boolean | null>(null);
  const [autostartError, setAutostartError] = useState<string | null>(null);

  useEffect(() => {
    getAutostart().then(setAutostartState).catch(() => {});
  }, []);

  // Efficiency mode can switch on by itself (a game starts), so keep its card current.
  const [efficiency, setEfficiency] = useState<{ on: boolean; reason: string }>({ on: false, reason: "" });
  useEffect(() => {
    const read = () =>
      getStatus()
        .then((st) => setEfficiency({ on: !!st.efficient, reason: st.efficiency_reason ?? "" }))
        .catch(() => {});
    read();
    const timer = window.setInterval(read, 5000);
    return () => clearInterval(timer);
  }, []);

  if (loading) return <div className="p-6 text-muted text-[13px]">Loading…</div>;
  if (loadError || !config || !options) {
    return <div className="p-6 text-error text-[13px]">{loadError ?? "Couldn't load settings"}</div>;
  }

  const busy = status.state === "loading";
  const modelDescription = busy
    ? "Loading the speech model…"
    : `${system?.compute ?? ""}. Turbo is the most accurate; on hard audio Small gets about twice as many words wrong, Base and Tiny three times.`;

  return (
    <div className="h-full overflow-y-auto">
      <main className="max-w-[640px] mx-auto px-6 pt-6 pb-10">
        <h1 className="text-[28px] leading-9 font-semibold">ShuperWhisper</h1>
        {status.state === "error" && status.error && (
          <div className="card mt-4 px-4 py-3 text-[13px] text-error">{status.error}</div>
        )}

        <Section title="Dictation">
          <ShortcutCard
            hotkey={config.hotkey}
            error={errors.hotkey}
            disabled={busy}
            onChange={(h) => apply({ hotkey: h })}
          />
          <Card
            icon={Hand}
            title="How the shortcut works"
            description={
              config.shortcut === "double"
                ? "Hold it to talk, or double-tap to start and tap once to stop. A single tap does nothing."
                : "Hold it to talk, or tap to start and tap again to stop."
            }
            error={errors.shortcut}
          >
            <Select
              value={config.shortcut}
              disabled={busy}
              onChange={(v) => apply({ shortcut: v as AppConfig["shortcut"] })}
              options={[
                { value: "tap", label: "Tap or hold" },
                { value: "double", label: "Double-tap or hold" },
              ]}
            />
          </Card>
          <MicrophoneCard
            device={config.input_device}
            devices={devices}
            error={errors.input_device}
            disabled={busy}
            onChange={(d) => apply({ input_device: d })}
          />
        </Section>

        <Section title="Recognition">
          <Card icon={Cpu} title="Speech model" description={modelDescription} error={errors.model_size}>
            <Select
              value={config.model_size}
              disabled={busy}
              onChange={(v) => apply({ model_size: v })}
              options={options.models.map((m) => ({ value: m, label: MODEL_LABELS[m] ?? m }))}
            />
          </Card>
          <Card icon={Globe} title="Language" error={errors.language}>
            <Select
              value={config.language}
              disabled={busy}
              onChange={(v) => apply({ language: v })}
              options={Object.entries(options.languages).map(([value, label]) => ({ value, label }))}
            />
          </Card>
        </Section>

        <Section title="Processing">
          <ProcessingSection
            config={config}
            errors={errors}
            apply={apply}
            modelState={status.state}
            onGpuReady={() => {
              refreshSystem();
              pollUntilSettled();
            }}
          />
          <Card
            icon={Leaf}
            title="Efficiency mode"
            description={
              (efficiency.on ? `On now: ${efficiency.reason}. ` : "") +
              "Runs dictation on the processor and frees the graphics card. Automatic turns it on while a game or another program uses the graphics card heavily."
            }
            error={errors.efficiency}
          >
            <Select
              value={config.efficiency}
              disabled={busy}
              onChange={(v) => apply({ efficiency: v as AppConfig["efficiency"] })}
              options={[
                { value: "auto", label: "Automatic" },
                { value: "on", label: "On" },
                { value: "off", label: "Off" },
              ]}
            />
          </Card>
        </Section>

        <Section title="Dictionary">
          <p className="text-[12px] text-muted mb-1">
            Words ShuperWhisper should know. If it keeps hearing a word wrong, put what it hears in “sounds like”
            and it will be swapped automatically. Train records you saying the word three times.
          </p>
          <DictionarySection trainingStatus={trainingStatus} clearTraining={clearTraining} />
        </Section>

        <Section title="General">
          <Card icon={Power} title="Start with Windows" error={autostartError}>
            {autostart !== null && (
              <Toggle
                label="Start with Windows"
                checked={autostart}
                onChange={async (on) => {
                  setAutostartError(null);
                  try {
                    setAutostartState(await setAutostart(on));
                  } catch (e) {
                    setAutostartError(e instanceof Error ? e.message : "Couldn't change that");
                  }
                }}
              />
            )}
          </Card>
        </Section>

        <p className="text-[12px] text-muted mt-6">Changes are saved automatically.</p>
      </main>
    </div>
  );
}
