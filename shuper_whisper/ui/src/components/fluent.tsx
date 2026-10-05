import * as RSelect from "@radix-ui/react-select";
import { Check, ChevronDown, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1">
      <h2 className="text-[14px] font-semibold mt-6 mb-1.5">{title}</h2>
      {children}
    </section>
  );
}

export function Card({
  icon: Icon,
  title,
  description,
  error,
  children,
  below,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  error?: string | null;
  children?: ReactNode;
  below?: ReactNode;
}) {
  return (
    <div className="card">
      <div className="flex items-center gap-4 px-4 py-3 min-h-[68px]">
        <Icon size={20} strokeWidth={1.5} className="shrink-0 opacity-90" />
        <div className="flex-1 min-w-0">
          <div className="text-[14px]">{title}</div>
          {description && <div className="text-[12px] text-muted leading-4 mt-0.5">{description}</div>}
          {error && <div className="text-[12px] text-error leading-4 mt-1">{error}</div>}
        </div>
        {children && <div className="shrink-0 max-w-[60%]">{children}</div>}
      </div>
      {below && <div className="border-t border-[var(--stroke)] px-4 py-3">{below}</div>}
    </div>
  );
}

export function Select({
  value,
  onChange,
  options,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  disabled?: boolean;
}) {
  const label = options.find((o) => o.value === value)?.label ?? value;
  return (
    <RSelect.Root value={value} onValueChange={onChange} disabled={disabled}>
      <RSelect.Trigger className="control h-8 min-w-[200px] max-w-[280px] px-3 flex items-center justify-between gap-2 text-[14px] outline-none">
        <span className="truncate">
          <RSelect.Value>{label}</RSelect.Value>
        </span>
        <RSelect.Icon>
          <ChevronDown size={14} className="text-muted" />
        </RSelect.Icon>
      </RSelect.Trigger>
      <RSelect.Portal>
        <RSelect.Content
          position="popper"
          sideOffset={4}
          className="rounded-lg border border-[var(--stroke)] bg-[var(--flyout)] text-[var(--text)] shadow-[0_8px_16px_rgba(0,0,0,0.14)] overflow-hidden"
        >
          <RSelect.Viewport className="p-1 max-h-[300px]">
            {options.map((o) => (
              <RSelect.Item
                key={o.value}
                value={o.value}
                className="relative flex items-center gap-2 h-8 pl-7 pr-3 rounded text-[14px] cursor-default outline-none data-[highlighted]:bg-[var(--control-hover)]"
              >
                <RSelect.ItemIndicator className="absolute left-2 text-accent">
                  <Check size={14} />
                </RSelect.ItemIndicator>
                <RSelect.ItemText>{o.label}</RSelect.ItemText>
              </RSelect.Item>
            ))}
          </RSelect.Viewport>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-3 text-[14px] disabled:opacity-50"
    >
      <span className="text-muted">{checked ? "On" : "Off"}</span>
      <span
        className={cn(
          "relative w-10 h-5 rounded-full border transition-colors",
          checked ? "bg-[var(--accent)] border-transparent" : "border-[var(--muted)]"
        )}
      >
        <span
          className={cn(
            "absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full transition-all",
            checked ? "left-[22px] bg-[var(--on-accent)]" : "left-[3px] bg-[var(--muted)]"
          )}
        />
      </span>
    </button>
  );
}

export function Button({
  onClick,
  children,
  variant = "standard",
  disabled,
}: {
  onClick: () => void;
  children: ReactNode;
  variant?: "accent" | "standard";
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "h-8 px-3 text-[14px] inline-flex items-center gap-2 whitespace-nowrap",
        variant === "accent" ? "btn-accent" : "control"
      )}
    >
      {children}
    </button>
  );
}

/** A thin bar; ``fraction`` is 0..1. */
export function ProgressBar({ fraction, label }: { fraction: number; label: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(fraction * 100)));
  return (
    <div
      className="h-1 w-full rounded-full bg-[var(--control-stroke-bottom)] overflow-hidden"
      role="progressbar"
      aria-label={label}
      aria-valuenow={pct}
    >
      <div
        className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-75"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/** Microphone level: an RMS of 0.15 or more fills the bar. */
export function LevelMeter({ level }: { level: number }) {
  return <ProgressBar fraction={level / 0.15} label="Microphone level" />;
}
