import { cn } from "@/lib/utils";
import { Settings, Type, BookOpen } from "lucide-react";

type Tab = "general" | "formatting" | "dictionary";

const tabs: { id: Tab; label: string; icon: typeof Settings }[] = [
  { id: "general", label: "General", icon: Settings },
  { id: "formatting", label: "Formatting", icon: Type },
  { id: "dictionary", label: "Dictionary", icon: BookOpen },
];

interface TabNavProps {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
}

export function TabNav({ activeTab, onTabChange }: TabNavProps) {
  return (
    <div className="flex border-b border-white/[0.06] px-6 pt-4">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "relative flex items-center gap-2.5 px-5 py-3.5 text-[13px] font-medium",
              "transition-all duration-200 rounded-t-lg",
              isActive
                ? "text-accent"
                : "text-text-muted hover:text-text-secondary"
            )}
          >
            <Icon size={15} strokeWidth={isActive ? 2 : 1.5} />
            {tab.label}
            {isActive && (
              <span className="absolute bottom-0 left-2 right-2 h-[2px] bg-accent rounded-full" />
            )}
          </button>
        );
      })}
    </div>
  );
}
