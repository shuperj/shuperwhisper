import * as Select from "@radix-ui/react-select";
import { ChevronDown, Check } from "lucide-react";

interface StyledSelectProps {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}

export function StyledSelect({ value, onChange, options }: StyledSelectProps) {
  const selectedLabel = options.find((o) => o.value === value)?.label ?? value;

  return (
    <Select.Root value={value} onValueChange={onChange}>
      <Select.Trigger
        className="glass-input w-full px-4 py-3 rounded-lg text-[13px]
                   text-text-primary flex items-center justify-between
                   cursor-pointer outline-none"
      >
        <Select.Value>{selectedLabel}</Select.Value>
        <Select.Icon>
          <ChevronDown size={14} className="text-text-muted" />
        </Select.Icon>
      </Select.Trigger>

      <Select.Portal>
        <Select.Content
          className="bg-[#252538] border border-white/10 rounded-lg shadow-xl
                     overflow-hidden z-50"
          position="popper"
          sideOffset={4}
        >
          <Select.Viewport className="p-1 max-h-[260px]">
            {options.map((opt) => (
              <Select.Item
                key={opt.value}
                value={opt.value}
                className="flex items-center gap-2 px-3.5 py-2.5 text-[13px]
                           text-text-primary rounded-md cursor-pointer
                           outline-none data-[highlighted]:bg-white/10
                           data-[state=checked]:text-accent"
              >
                <Select.ItemIndicator className="w-4">
                  <Check size={12} />
                </Select.ItemIndicator>
                <Select.ItemText>{opt.label}</Select.ItemText>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
