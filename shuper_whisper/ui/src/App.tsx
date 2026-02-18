import { useState, useEffect } from "react";
import { useConfig } from "@/hooks/useConfig";
import { useTraining } from "@/hooks/useTraining";
import { TabNav } from "@/components/TabNav";
import { GeneralTab } from "@/components/GeneralTab";
import { FormattingTab } from "@/components/FormattingTab";
import { DictionaryTab } from "@/components/DictionaryTab";
import { ActionBar } from "@/components/ActionBar";
import { closeWindow } from "@/lib/bridge";

type Tab = "general" | "formatting" | "dictionary";

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("general");
  const {
    config,
    options,
    devices,
    isLoading,
    isSaving,
    isDirty,
    error,
    updateField,
    save,
  } = useConfig();
  const { trainingStatus, clearTraining } = useTraining();

  // Apply user colors as CSS custom properties on <html> so they cascade
  // to body::before/after ambient glows, body background, and all children.
  useEffect(() => {
    if (!config) return;
    const root = document.documentElement;
    if (config.accent_color) {
      root.style.setProperty("--sw-accent", config.accent_color);
      const r = Math.min(255, parseInt(config.accent_color.slice(1, 3), 16) + 17);
      const g = Math.min(255, parseInt(config.accent_color.slice(3, 5), 16) + 17);
      const b = Math.min(255, parseInt(config.accent_color.slice(5, 7), 16) + 17);
      root.style.setProperty(
        "--sw-accent-hover",
        `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`
      );
    }
    if (config.bg_color) {
      root.style.setProperty("--sw-bg", config.bg_color);
    }
  }, [config?.accent_color, config?.bg_color]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-text-muted text-sm">Loading...</div>
      </div>
    );
  }

  if (error || !config || !options) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-error text-sm">{error || "Failed to load config"}</div>
          <div className="text-text-muted text-xs mt-2">
            Bridge: {window.pywebview ? "connected" : "not found"}
          </div>
        </div>
      </div>
    );
  }

  const handleSave = async () => {
    const success = await save();
    if (success) {
      await closeWindow();
    }
  };

  const handleCancel = () => {
    closeWindow();
  };

  return (
    <div className="flex flex-col h-full">
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />

      <div className="flex-1 overflow-y-auto px-8 py-6">
        {activeTab === "general" && (
          <GeneralTab
            config={config}
            options={options}
            devices={devices}
            updateField={updateField}
          />
        )}
        {activeTab === "formatting" && (
          <FormattingTab
            config={config}
            options={options}
            updateField={updateField}
          />
        )}
        {activeTab === "dictionary" && (
          <DictionaryTab
            trainingStatus={trainingStatus}
            clearTraining={clearTraining}
          />
        )}
      </div>

      <ActionBar
        onSave={handleSave}
        onCancel={handleCancel}
        isSaving={isSaving}
        isDirty={isDirty}
      />
    </div>
  );
}
