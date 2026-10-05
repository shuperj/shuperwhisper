import { useState, useEffect, useCallback, useRef } from "react";
import type { AppConfig, ConfigOptions, Device } from "@/lib/types";
import {
  waitForBridge,
  getConfig,
  saveConfig,
  getConfigOptions,
  getDevices,
} from "@/lib/bridge";

export function useConfig() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [options, setOptions] = useState<ConfigOptions | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const originalConfig = useRef<AppConfig | null>(null);

  useEffect(() => {
    async function load() {
      try {
        await waitForBridge();
        const [cfg, opts, devs] = await Promise.all([
          getConfig(),
          getConfigOptions(),
          getDevices(),
        ]);
        setConfig(cfg);
        originalConfig.current = { ...cfg };
        setOptions(opts);
        setDevices(devs);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load config");
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  const updateField = useCallback(
    <K extends keyof AppConfig>(field: K, value: AppConfig[K]) => {
      setConfig((prev) => (prev ? { ...prev, [field]: value } : prev));
    },
    []
  );

  const save = useCallback(async (): Promise<boolean> => {
    if (!config) return false;
    setIsSaving(true);
    setSaveError(null);
    try {
      const result = await saveConfig(config);
      if (!result.success) {
        setSaveError(result.error ?? "Couldn't save settings");
        return false;
      }
      originalConfig.current = { ...config };
      return true;
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Couldn't save settings");
      return false;
    } finally {
      setIsSaving(false);
    }
  }, [config]);

  const isDirty =
    config !== null &&
    originalConfig.current !== null &&
    JSON.stringify(config) !== JSON.stringify(originalConfig.current);

  return {
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
  };
}
