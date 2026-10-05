import { useEffect, useState } from "react";
import { Cpu, Globe, Power } from "lucide-react";
import { useSettings } from "@/hooks/useSettings";
import { useTraining } from "@/hooks/useTraining";
import { getAutostart, setAutostart } from "@/lib/bridge";
import { Card, Section, Select, Toggle } from "@/components/fluent";
import { ShortcutCard } from "@/components/ShortcutCard";
import { MicrophoneCard } from "@/components/MicrophoneCard";
import { ProcessingSection } from "@/components/ProcessingSection";
import { DictionarySection } from "@/components/DictionarySection";

const MODEL_LABELS: Record<string, string> = {
  auto: "Automatic (recommended)",
  tiny: "Tiny (fastest)",
  base: "Base",
  small: "Small",
  medium: "Medium",
  "large-v3-turbo": "Large v3 Turbo",
  "large-v3": "Large v3 (most accurate)",
};

export default function App() {
  const { config, options, devices, system, status, loading, loadError, errors, apply, refreshSystem } =
    useSettings();
  const { trainingStatus, clearTraining } = useTraining();
  const [autostart, setAutostartState] = useState<boolean | null>(null);

  useEffect(() => {
    getAutostart().then(setAutostartState).catch(() => {});
  }, []);

  if (loading) return <div className="p-6 text-muted text-[13px]">Loading…</div>;
  if (loadError || !config || !options) {
    return <div className="p-6 text-error text-[13px]">{loadError ?? "Couldn't load settings"}</div>;
  }

  const modelDescription = status.state === "loading" ? "Loading the speech model…" : (system?.compute ?? "");

  return (
    <div className="h-full overflow-y-auto">
      <main className="max-w-[640px] mx-auto px-6 pt-6 pb-10">
        <h1 className="text-[28px] leading-9 font-semibold">ShuperWhisper</h1>
        {status.state === "error" && status.error && (
          <div className="card mt-4 px-4 py-3 text-[13px] text-error">{status.error}</div>
        )}

        <Section title="Dictation">
          <ShortcutCard hotkey={config.hotkey} error={errors.hotkey} onChange={(h) => apply({ hotkey: h })} />
          <MicrophoneCard
            device={config.input_device}
            devices={devices}
            error={errors.input_device}
            onChange={(d) => apply({ input_device: d })}
          />
        </Section>

        <Section title="Recognition">
          <Card icon={Cpu} title="Speech model" description={modelDescription} error={errors.model_size}>
            <Select
              value={config.model_size}
              disabled={status.state === "loading"}
              onChange={(v) => apply({ model_size: v })}
              options={options.models.map((m) => ({ value: m, label: MODEL_LABELS[m] ?? m }))}
            />
          </Card>
          <Card icon={Globe} title="Language" error={errors.language}>
            <Select
              value={config.language}
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
            onGpuReady={refreshSystem}
          />
        </Section>

        <Section title="Dictionary">
          <p className="text-[12px] text-muted mb-1">
            Words ShuperWhisper should know. If it keeps hearing a word wrong, put what it hears in “sounds like”
            and it will be swapped automatically. Train records you saying the word three times.
          </p>
          <DictionarySection trainingStatus={trainingStatus} clearTraining={clearTraining} />
        </Section>

        <Section title="General">
          <Card icon={Power} title="Start with Windows">
            {autostart !== null && (
              <Toggle
                label="Start with Windows"
                checked={autostart}
                onChange={async (on) => setAutostartState(await setAutostart(on))}
              />
            )}
          </Card>
        </Section>

        <p className="text-[12px] text-muted mt-6">Changes are saved automatically.</p>
      </main>
    </div>
  );
}
