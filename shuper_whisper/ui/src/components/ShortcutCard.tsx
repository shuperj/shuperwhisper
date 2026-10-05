import { useState } from "react";
import { Keyboard } from "lucide-react";
import { captureHotkey } from "@/lib/bridge";
import { Button, Card } from "./fluent";

const pretty = (hotkey: string) =>
  hotkey
    .split("+")
    .map((k) => (k.length === 1 ? k.toUpperCase() : k[0].toUpperCase() + k.slice(1)))
    .join(" + ");

export function ShortcutCard({
  hotkey,
  error,
  onChange,
}: {
  hotkey: string;
  error?: string;
  onChange: (h: string) => void;
}) {
  const [capturing, setCapturing] = useState(false);
  const capture = async () => {
    setCapturing(true);
    try {
      const key = await captureHotkey();
      if (key) onChange(key);
    } catch {
      /* timed out */
    } finally {
      setCapturing(false);
    }
  };
  return (
    <Card
      icon={Keyboard}
      title="Dictation shortcut"
      description="Press once to start dictating, press again to stop."
      error={error}
    >
      <Button onClick={capture} disabled={capturing}>
        {capturing ? "Press a shortcut… (Esc cancels)" : <kbd className="font-[inherit]">{pretty(hotkey)}</kbd>}
      </Button>
    </Card>
  );
}
