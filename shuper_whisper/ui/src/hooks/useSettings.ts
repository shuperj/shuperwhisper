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

/**
 * Load settings once; apply each change immediately; poll status while the
 * speech model loads. Changes are applied one at a time, and a change that
 * fails reverts only the fields it touched.
 */
export function useSettings() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [options, setOptions] = useState<ConfigOptions | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [status, setStatus] = useState<AppStatus>({ state: "idle", error: null, reload_error: null });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const polling = useRef<number | null>(null);
  const queue = useRef<Promise<void>>(Promise.resolve());
  // Fields of the change whose model load is in progress, for error placement.
  const loadingKeys = useRef<(keyof AppConfig)[]>([]);

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

  const settle = useCallback(
    async (st: AppStatus) => {
      // A background load finished: show what's actually running now.
      const keys = loadingKeys.current;
      loadingKeys.current = [];
      if (st.reload_error) {
        try {
          setConfig(await getConfig());
        } catch {
          /* keep what we have */
        }
        if (keys.length) setErrors((e) => ({ ...e, [keys[0]]: st.reload_error! }));
      }
      await refreshSystem();
    },
    [refreshSystem]
  );

  const pollUntilSettled = useCallback(() => {
    if (polling.current) clearInterval(polling.current);
    polling.current = window.setInterval(async () => {
      try {
        const st = await getStatus();
        setStatus(st);
        if (st.state !== "loading") {
          clearInterval(polling.current!);
          polling.current = null;
          await settle(st);
        }
      } catch {
        /* keep polling */
      }
    }, 500);
  }, [settle]);

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
        setConfig(cfg);
        setOptions(opts);
        setDevices(devs);
        setStatus(st);
        await refreshSystem();
        if (st.state === "loading") pollUntilSettled(); // e.g. first launch, model downloading
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : "Couldn't load settings");
      } finally {
        setLoading(false);
      }
    })();
    return () => {
      if (polling.current) clearInterval(polling.current);
    };
  }, [refreshSystem, pollUntilSettled]);

  const applyNow = useCallback(
    async (patch: Partial<AppConfig>) => {
      const keys = Object.keys(patch) as (keyof AppConfig)[];
      let before: Partial<AppConfig> = {};
      setConfig((cfg) => {
        if (!cfg) return cfg;
        before = Object.fromEntries(keys.map((k) => [k, cfg[k]])) as Partial<AppConfig>;
        return { ...cfg, ...patch };
      });
      setErrors((e) => {
        const n = { ...e };
        keys.forEach((k) => delete n[k]);
        return n;
      });
      const fail = (message: string, running?: AppConfig) => {
        setConfig((cfg) => (running ? running : cfg ? { ...cfg, ...before } : cfg));
        setErrors((e) => ({ ...e, [keys[0]]: message }));
      };
      try {
        const result = await saveConfig(patch);
        if (!result.success) return fail(result.error ?? "Couldn't apply that", result.config);
        if (result.loading) {
          loadingKeys.current = keys;
          setStatus((s) => ({ ...s, state: "loading" }));
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

  // One change at a time, in the order they were made.
  const apply = useCallback(
    (patch: Partial<AppConfig>) => {
      queue.current = queue.current.then(() => applyNow(patch));
      return queue.current;
    },
    [applyNow]
  );

  return {
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
  };
}
