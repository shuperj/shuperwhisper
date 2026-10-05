import { useEffect, useRef, useState } from "react";
import { Cpu, Type, Zap } from "lucide-react";
import type { AppConfig, GpuSetupProgress, GpuStatus } from "@/lib/types";
import type { FieldErrors } from "@/hooks/useSettings";
import { cancelGpuSetup, getGpuSetupProgress, getGpuStatus, setupGpu } from "@/lib/bridge";
import { Button, Card, ProgressBar, Select, Toggle } from "./fluent";

const FINISHED = ["done", "error", "cancelled"];

export function ProcessingSection({
  config,
  errors,
  apply,
  modelState,
  onGpuReady,
}: {
  config: AppConfig;
  errors: FieldErrors;
  apply: (patch: Partial<AppConfig>) => Promise<void>;
  modelState: string;
  onGpuReady: () => void;
}) {
  const [gpu, setGpu] = useState<GpuStatus | null>(null);
  const [setup, setSetup] = useState<GpuSetupProgress | null>(null);
  const timer = useRef<number | null>(null);

  const refresh = () => getGpuStatus().then(setGpu).catch(() => {});

  useEffect(() => {
    refresh();
    // A download may already be running (started from another window).
    getGpuSetupProgress()
      .then((p) => {
        if (!FINISHED.includes(p.state) && p.state !== "idle") watch();
      })
      .catch(() => {});
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, []);

  // Re-read whenever the speech model (re)loads: "in use" depends on it.
  useEffect(() => {
    if (modelState !== "loading") refresh();
  }, [config.compute, modelState]);

  const watch = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = window.setInterval(async () => {
      try {
        const p = await getGpuSetupProgress();
        setSetup(p);
        if (FINISHED.includes(p.state)) {
          clearInterval(timer.current!);
          timer.current = null;
          await refresh();
          if (p.state === "done") onGpuReady();
        }
      } catch {
        /* keep watching */
      }
    }, 300);
  };

  const start = async () => {
    setSetup({ state: "downloading", fraction: 0, message: "Starting…" });
    try {
      await setupGpu();
      watch();
    } catch (e) {
      setSetup({ state: "error", fraction: 0, message: e instanceof Error ? e.message : "Couldn't start" });
    }
  };

  const running = setup !== null && !FINISHED.includes(setup.state);
  let description: string;
  if (!gpu) description = "Checking…";
  else if (!gpu.gpu) description = "No NVIDIA graphics card found. Dictation runs on the processor.";
  else if (gpu.active) description = `${gpu.gpu}: in use`;
  else if (gpu.installed && config.compute === "cpu") description = `${gpu.gpu}: set up, but turned off below`;
  else if (gpu.installed && (modelState === "loading" || running)) description = `${gpu.gpu}: starting…`;
  else if (gpu.installed)
    description = `${gpu.gpu}: set up, but it couldn't start, so the processor is used. Updating the NVIDIA driver may help.`;
  else description = `${gpu.gpu} found. Download NVIDIA's libraries (about 1.2 GB) to turn on live typing.`;

  return (
    <>
      <Card
        icon={Zap}
        title="GPU acceleration"
        description={description}
        error={setup?.state === "error" ? setup.message : null}
        below={
          running && setup ? (
            <div className="flex flex-col gap-2">
              <ProgressBar fraction={setup.fraction} label="Download progress" />
              <span className="text-[12px] text-muted">
                {setup.message} {setup.state === "downloading" ? `${Math.round(setup.fraction * 100)}%` : ""}
              </span>
            </div>
          ) : undefined
        }
      >
        {gpu?.gpu &&
          !gpu.installed &&
          (running ? (
            <Button onClick={() => cancelGpuSetup()}>Cancel</Button>
          ) : (
            <Button variant="accent" onClick={start}>
              Set up
            </Button>
          ))}
      </Card>
      <Card
        icon={Cpu}
        title="Use GPU when available"
        description="Turn off to always use the processor."
        error={errors.compute}
      >
        <Toggle
          label="Use GPU when available"
          checked={config.compute === "auto"}
          disabled={modelState === "loading"}
          onChange={(on) => apply({ compute: on ? "auto" : "cpu" })}
        />
      </Card>
      <Card
        icon={Type}
        title="Live typing"
        description="Automatic types as you speak with GPU acceleration, and all at once when you stop on the processor."
        error={errors.live_typing}
      >
        <Select
          value={config.live_typing}
          disabled={modelState === "loading"}
          onChange={(v) => apply({ live_typing: v as AppConfig["live_typing"] })}
          options={[
            { value: "auto", label: "Automatic" },
            { value: "on", label: "Always live" },
            { value: "off", label: "Type when I stop" },
          ]}
        />
      </Card>
    </>
  );
}
