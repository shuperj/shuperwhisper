import { Loader2 } from "lucide-react";

interface ActionBarProps {
  onSave: () => void;
  onCancel: () => void;
  isSaving: boolean;
  isDirty: boolean;
}

export function ActionBar({
  onSave,
  onCancel,
  isSaving,
  isDirty,
}: ActionBarProps) {
  return (
    <div className="flex items-center gap-4 px-8 py-5 border-t border-white/[0.06]">
      <button
        onClick={onSave}
        disabled={isSaving}
        className="btn-accent px-10 py-3 rounded-lg text-sm font-medium
                   disabled:opacity-50 disabled:cursor-not-allowed
                   flex items-center gap-2"
      >
        {isSaving && <Loader2 size={14} className="animate-spin" />}
        {isSaving ? "Saving..." : "Save"}
      </button>
      <button
        onClick={onCancel}
        disabled={isSaving}
        className="btn-ghost px-10 py-3 rounded-lg text-sm font-medium
                   disabled:opacity-50"
      >
        Cancel
      </button>
      {isDirty && (
        <span className="ml-auto text-text-muted text-[11px]">
          Unsaved changes
        </span>
      )}
    </div>
  );
}
