import { useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import type { Device, DeviceRef } from "@/lib/types";
import { getMicLevel, startMicTest, stopMicTest } from "@/lib/bridge";
import { Button, Card, LevelMeter, Select } from "./fluent";

const DEFAULT = "__default__";
const MISSING = "__missing__";
const id = (name: string, hostapi: string | null) => `${name}|${hostapi ?? ""}`;

/** The listed device a saved reference points at (hostapi may be unknown). */
function findDevice(devices: Device[], ref: DeviceRef): Device | undefined {
  return (
    devices.find((d) => d.name === ref.name && (ref.hostapi === null || d.hostapi === ref.hostapi)) ??
    devices.find((d) => d.name === ref.name) ??
    devices.find((d) => d.name.slice(0, 31) === ref.name.slice(0, 31))
  );
}

export function MicrophoneCard({
  device,
  devices,
  error,
  onChange,
}: {
  device: DeviceRef | null;
  devices: Device[];
  error?: string;
  onChange: (d: DeviceRef | null) => void;
}) {
  const [testing, setTesting] = useState(false);
  const [level, setLevel] = useState(0);
  const [testError, setTestError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const stopTimer = useRef<number | null>(null);

  const stop = async () => {
    if (timer.current) clearInterval(timer.current);
    if (stopTimer.current) clearTimeout(stopTimer.current);
    timer.current = stopTimer.current = null;
    setTesting(false);
    setLevel(0);
    try {
      await stopMicTest();
    } catch {
      /* ignore */
    }
  };

  const start = async () => {
    setTestError(null);
    try {
      const result = await startMicTest(device);
      if (!result.success) {
        setTestError(result.error ?? "Couldn't open the microphone");
        return;
      }
    } catch (e) {
      setTestError(e instanceof Error ? e.message : "Couldn't open the microphone");
      return;
    }
    setTesting(true);
    timer.current = window.setInterval(async () => {
      try {
        setLevel(await getMicLevel());
      } catch {
        /* ignore */
      }
    }, 60);
    stopTimer.current = window.setTimeout(stop, 15000);
  };

  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
      if (stopTimer.current) clearTimeout(stopTimer.current);
      stopMicTest().catch(() => {});
    },
    []
  );

  const current = device ? findDevice(devices, device) : undefined;
  const options = [
    { value: DEFAULT, label: "Windows default" },
    ...devices.map((d) => ({
      value: id(d.name, d.hostapi),
      label: d.is_default ? `${d.name} (default)` : d.name,
    })),
  ];
  // A saved device that isn't plugged in right now stays visible and selected.
  if (device && !current) options.push({ value: MISSING, label: `${device.name} (not connected)` });
  const value = !device ? DEFAULT : current ? id(current.name, current.hostapi) : MISSING;

  return (
    <Card
      icon={Mic}
      title="Microphone"
      description="Voicemeeter buses and other virtual devices work too."
      error={error ?? testError}
      below={
        <div className="flex items-center gap-3">
          <Button onClick={testing ? stop : start}>{testing ? "Stop test" : "Test"}</Button>
          <div className="flex-1">
            <LevelMeter level={level} />
          </div>
        </div>
      }
    >
      <Select
        value={value}
        options={options}
        onChange={(v) => {
          if (testing) stop();
          if (v === MISSING) return;
          if (v === DEFAULT) return onChange(null);
          const d = devices.find((x) => id(x.name, x.hostapi) === v);
          if (d) onChange({ name: d.name, hostapi: d.hostapi });
        }}
      />
    </Card>
  );
}
