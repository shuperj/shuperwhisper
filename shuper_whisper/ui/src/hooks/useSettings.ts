import { useCallback, useEffect, useRef, useState } from "react";
import type { AppConfig, AppStatus, ConfigOptions, Device, SystemInfo } from "@/lib/types";
import {
  getConfig,
  getConfigOptions,
  getDevices,
  getStatus,
  getSystemInfo,
  saveConfig,
  waitForBridge,
} from "@/lib/bridge";

export type FieldErrors = Partial<Record<keyof AppConfig, string>>;

/** Load settings once; apply each change immediately; poll status while the model loads. */
export function useSettings() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [options, setOptions] = useState<ConfigOptions | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [status, setStatus] = useState<AppStatus>({ state: "idle", error: null });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const polling = useRef<number | null>(null);
  const configRef = useRef<AppConfig | null>(null);

  const refreshSystem = useCallback(async () => {
    try {
      const info = await getSystemInfo();
      setSystem(info);
      // Both variants: the stylesheet picks one with prefers-color-scheme,
      // so accent and theme can't disagree.
      const root = document.documentElement.style;
      root.setProperty("--sys-accent-light", info.accent.light);
      root.setProperty("--sys-accent-dark", info.accent.dark);
    } catch {
      /* keep the default accent */
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await waitForBridge();
        const [cfg, opts, devs, st] = await Promise.all([
          getConfig(),
          getConfigOptions(),
          getDevices(),
          getStatus(),
        ]);
        configRef.current = cfg;
        setConfig(cfg);
        setOptions(opts);
        setDevices(devs);
        setStatus(st);
        await refreshSystem();
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : "Couldn't load settings");
      } finally {
        setLoading(false);
      }
    })();
    return () => {
      if (polling.current) clearInterval(polling.current);
    };
  }, [refreshSystem]);

  const pollUntilSettled = useCallback(() => {
    if (polling.current) clearInterval(polling.current);
    polling.current = window.setInterval(async () => {
      try {
        const st = await getStatus();
        setStatus(st);
        if (st.state !== "loading") {
          clearInterval(polling.current!);
          polling.current = null;
          await refreshSystem();
        }
      } catch {
        /* keep polling */
      }
    }, 500);
  }, [refreshSystem]);

  const apply = useCallback(
    async (patch: Partial<AppConfig>) => {
      const previous = configRef.current;
      if (!previous) return;
      const next = { ...previous, ...patch };
      const keys = Object.keys(patch) as (keyof AppConfig)[];
      configRef.current = next;
      setConfig(next);
      setErrors((e) => {
        const n = { ...e };
        keys.forEach((k) => delete n[k]);
        return n;
      });
      const fail = (message: string) => {
        configRef.current = previous;
        setConfig(previous);
        setErrors((e) => ({ ...e, [keys[0]]: message }));
      };
      try {
        const result = await saveConfig(next);
        if (!result.success) return fail(result.error ?? "Couldn't apply that");
        if (result.loading) {
          setStatus({ state: "loading", error: null });
          pollUntilSettled();
        } else {
          setStatus(await getStatus());
          await refreshSystem();
        }
      } catch (e) {
        fail(e instanceof Error ? e.message : "Couldn't apply that");
      }
    },
    [pollUntilSettled, refreshSystem]
  );

  return { config, options, devices, system, status, loading, loadError, errors, apply, refreshSystem };
}
