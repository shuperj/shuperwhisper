import { useState, useEffect, useCallback } from "react";
import type { DictionaryEntry, TrainingStatus } from "@/lib/types";
import {
  getDictionary,
  addWord,
  removeWord,
  trainWord,
} from "@/lib/bridge";
import {
  Plus,
  Trash2,
  Mic,
  Check,
  Minus,
  Loader2,
  AlertCircle,
} from "lucide-react";

interface DictionaryTabProps {
  trainingStatus: TrainingStatus | null;
  clearTraining: () => void;
}

export function DictionaryTab({
  trainingStatus,
  clearTraining,
}: DictionaryTabProps) {
  const [entries, setEntries] = useState<DictionaryEntry[]>([]);
  const [word, setWord] = useState("");
  const [phonetic, setPhonetic] = useState("");
  const [trainingWord, setTrainingWord] = useState<string | null>(null);

  const loadEntries = useCallback(async () => {
    try {
      const data = await getDictionary();
      setEntries(data);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  // Handle training status updates
  useEffect(() => {
    if (!trainingStatus) return;
    if (trainingStatus.status === "done" || trainingStatus.status === "error") {
      setTrainingWord(null);
      loadEntries();
      // Auto-clear after a delay
      const timer = setTimeout(clearTraining, 3000);
      return () => clearTimeout(timer);
    }
  }, [trainingStatus, loadEntries, clearTraining]);

  const handleAdd = async () => {
    const trimmed = word.trim();
    if (!trimmed) return;
    try {
      await addWord(trimmed, phonetic.trim());
      setWord("");
      setPhonetic("");
      await loadEntries();
    } catch {
      // silent
    }
  };

  const handleRemove = async (w: string) => {
    try {
      await removeWord(w);
      await loadEntries();
    } catch {
      // silent
    }
  };

  const handleTrain = async (w: string) => {
    setTrainingWord(w);
    clearTraining();
    try {
      await trainWord(w);
    } catch {
      setTrainingWord(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleAdd();
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Training status banner */}
      {trainingStatus && (
        <div
          className={`glass rounded-lg px-3 py-2 text-[12px] flex items-center gap-2 ${
            trainingStatus.status === "error"
              ? "border-error/30 text-error"
              : trainingStatus.status === "done" && trainingStatus.success
                ? "border-success/30 text-success"
                : trainingStatus.status === "done" && !trainingStatus.success
                  ? "border-warning/30 text-warning"
                  : "border-accent/30 text-accent"
          }`}
        >
          {trainingStatus.status === "recording" && (
            <>
              <Mic size={14} className="animate-pulse-glow text-accent" />
              <span>
                Recording &ldquo;{trainingStatus.word}&rdquo;... Speak now!
              </span>
            </>
          )}
          {trainingStatus.status === "transcribing" && (
            <>
              <Loader2 size={14} className="animate-spin" />
              <span>Transcribing...</span>
            </>
          )}
          {trainingStatus.status === "done" && trainingStatus.success && (
            <>
              <Check size={14} />
              <span>
                Trained! Got &ldquo;{trainingStatus.transcribed}&rdquo;
              </span>
            </>
          )}
          {trainingStatus.status === "done" && !trainingStatus.success && (
            <>
              <AlertCircle size={14} />
              <span>
                Expected &ldquo;{trainingStatus.word}&rdquo; but got &ldquo;
                {trainingStatus.transcribed}&rdquo;. Try adding a phonetic hint.
              </span>
            </>
          )}
          {trainingStatus.status === "error" && (
            <>
              <AlertCircle size={14} />
              <span>Error: {trainingStatus.error}</span>
            </>
          )}
        </div>
      )}

      {/* Word list */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-text-muted">
            <BookIcon />
            <p className="text-[13px] mt-2">No dictionary entries yet</p>
            <p className="text-[11px] mt-1">
              Add custom words to improve recognition
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {entries.map((entry) => (
              <div
                key={entry.word}
                className="glass rounded-lg px-3 py-2 flex items-center gap-3 group
                           hover:bg-white/[0.06] transition-colors duration-150"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-text-primary truncate">
                    {entry.word}
                  </div>
                  {entry.phonetic && (
                    <div className="text-[11px] text-text-muted truncate">
                      {entry.phonetic}
                    </div>
                  )}
                </div>

                {/* Trained status */}
                <div className="shrink-0">
                  {entry.trained ? (
                    <span className="flex items-center gap-1 text-[11px] text-success">
                      <Check size={12} />
                      Trained
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[11px] text-text-muted">
                      <Minus size={12} />
                    </span>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                  {!entry.trained && (
                    <button
                      onClick={() => handleTrain(entry.word)}
                      disabled={trainingWord !== null}
                      className={`p-1.5 rounded-md transition-colors text-text-muted hover:text-accent hover:bg-accent/10
                        ${trainingWord === entry.word ? "animate-pulse-glow text-accent" : ""}
                        disabled:opacity-40`}
                      title="Train"
                    >
                      <Mic size={14} />
                    </button>
                  )}
                  <button
                    onClick={() => handleRemove(entry.word)}
                    className="p-1.5 rounded-md transition-colors text-text-muted
                               hover:text-error hover:bg-error/10"
                    title="Remove"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add word form */}
      <div className="glass rounded-xl p-3 flex gap-2">
        <input
          type="text"
          value={word}
          onChange={(e) => setWord(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Word or phrase"
          className="glass-input flex-1 px-3 py-2 rounded-lg text-[13px]
                     text-text-primary placeholder:text-text-muted/60"
        />
        <input
          type="text"
          value={phonetic}
          onChange={(e) => setPhonetic(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Phonetic hint"
          className="glass-input w-[120px] px-3 py-2 rounded-lg text-[13px]
                     text-text-primary placeholder:text-text-muted/60"
        />
        <button
          onClick={handleAdd}
          disabled={!word.trim()}
          className="btn-accent px-3 py-2 rounded-lg disabled:opacity-30 disabled:shadow-none
                     disabled:hover:transform-none"
        >
          <Plus size={16} />
        </button>
      </div>
    </div>
  );
}

function BookIcon() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="opacity-30"
    >
      <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
    </svg>
  );
}
