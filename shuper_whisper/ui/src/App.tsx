import { useState } from "react";
import { useConfig } from "@/hooks/useConfig";
import { useTraining } from "@/hooks/useTraining";
import { TabNav } from "@/components/TabNav";
import { GeneralTab } from "@/components/GeneralTab";
import { DictionaryTab } from "@/components/DictionaryTab";
import { ActionBar } from "@/components/ActionBar";
import { closeWindow } from "@/lib/bridge";

type Tab = "general" | "dictionary";

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
    saveError,
    updateField,
    save,
  } = useConfig();
  const { trainingStatus, clearTraining } = useTraining();

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
        {activeTab === "dictionary" && (
          <DictionaryTab
            trainingStatus={trainingStatus}
            clearTraining={clearTraining}
          />
        )}
      </div>

      {saveError && (
        <div className="mx-8 mb-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-[12px] text-red-300">
          {saveError}
        </div>
      )}

      <ActionBar
        onSave={handleSave}
        onCancel={handleCancel}
        isSaving={isSaving}
        isDirty={isDirty}
      />
    </div>
  );
}
