import { useState, useEffect, useCallback } from "react";
import type { DictionaryEntry, TrainingStatus } from "@/lib/types";
import {
  getDictionary,
  addWord,
  removeWord,
  updateWord,
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
  Pencil,
  X,
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
  const [editingEntry, setEditingEntry] = useState<string | null>(null);
  const [editWord, setEditWord] = useState("");
  const [editPhonetic, setEditPhonetic] = useState("");

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
      const timer = setTimeout(clearTraining, 5000);
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

  const handleStartEdit = (entry: DictionaryEntry) => {
    setEditingEntry(entry.word);
    setEditWord(entry.word);
    setEditPhonetic(entry.phonetic);
  };

  const handleSaveEdit = async () => {
    if (!editingEntry || !editWord.trim()) return;
    try {
      const result = await updateWord(
        editingEntry,
        editWord.trim(),
        editPhonetic.trim()
      );
      if (result.success) {
        setEditingEntry(null);
        await loadEntries();
      }
    } catch {
      // silent
    }
  };

  const handleCancelEdit = () => {
    setEditingEntry(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleAdd();
  };

  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSaveEdit();
    if (e.key === "Escape") handleCancelEdit();
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Training status banner */}
      {trainingStatus && (
        <div
          className={`glass rounded-lg px-3 py-2 text-[12px] flex items-center gap-2 ${
            trainingStatus.status === "error"
              ? "border-error/30 text-error"
              : trainingStatus.status === "done"
                ? "border-success/30 text-success"
                : trainingStatus.status === "round_done" &&
                    trainingStatus.roundSuccess
                  ? "border-success/30 text-success"
                  : trainingStatus.status === "round_done"
                    ? "border-accent/30 text-accent"
                    : "border-accent/30 text-accent"
          }`}
        >
          {trainingStatus.status === "recording" && (
            <>
              <Mic size={14} className="animate-pulse-glow text-accent" />
              <span>
                Round {trainingStatus.round}/{trainingStatus.totalRounds}:
                Recording &ldquo;{trainingStatus.word}&rdquo;&hellip; Speak now!
              </span>
            </>
          )}
          {trainingStatus.status === "transcribing" && (
            <>
              <Loader2 size={14} className="animate-spin" />
              <span>
                Round {trainingStatus.round}/{trainingStatus.totalRounds}:
                Transcribing&hellip;
              </span>
            </>
          )}
          {trainingStatus.status === "round_done" && (
            <>
              {trainingStatus.roundSuccess ? (
                <Check size={14} className="text-success" />
              ) : (
                <Mic size={14} className="text-accent" />
              )}
              <span>
                Round {trainingStatus.round}/{trainingStatus.totalRounds}:
                Heard &ldquo;{trainingStatus.transcribed}&rdquo;
                {trainingStatus.roundSuccess && " \u2714"}
              </span>
            </>
          )}
          {trainingStatus.status === "done" &&
            trainingStatus.alreadyRecognized && (
              <>
                <Check size={14} />
                <span>
                  Trained! Whisper already recognizes &ldquo;
                  {trainingStatus.word}&rdquo;.
                </span>
              </>
            )}
          {trainingStatus.status === "done" &&
            !trainingStatus.alreadyRecognized &&
            trainingStatus.learnedHint && (
              <>
                <Check size={14} />
                <span>
                  Trained! Learned hint &ldquo;{trainingStatus.learnedHint}
                  &rdquo; for &ldquo;{trainingStatus.word}&rdquo;.
                </span>
              </>
            )}
          {trainingStatus.status === "done" &&
            !trainingStatus.alreadyRecognized &&
            !trainingStatus.learnedHint && (
              <>
                <Check size={14} />
                <span>Trained!</span>
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
            {entries.map((entry) =>
              editingEntry === entry.word ? (
                <div
                  key={entry.word}
                  className="glass rounded-lg px-3 py-2 flex items-center gap-2"
                >
                  <input
                    type="text"
                    value={editWord}
                    onChange={(e) => setEditWord(e.target.value)}
                    onKeyDown={handleEditKeyDown}
                    className="glass-input flex-1 px-2 py-1 rounded text-[13px]
                               text-text-primary"
                    autoFocus
                  />
                  <input
                    type="text"
                    value={editPhonetic}
                    onChange={(e) => setEditPhonetic(e.target.value)}
                    onKeyDown={handleEditKeyDown}
                    placeholder="Phonetic"
                    className="glass-input w-[100px] px-2 py-1 rounded text-[11px]
                               text-text-primary placeholder:text-text-muted/60"
                  />
                  <button
                    onClick={handleSaveEdit}
                    className="p-1.5 rounded-md transition-colors text-success
                               hover:bg-success/10"
                    title="Save"
                  >
                    <Check size={14} />
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="p-1.5 rounded-md transition-colors text-text-muted
                               hover:bg-white/10"
                    title="Cancel"
                  >
                    <X size={14} />
                  </button>
                </div>
              ) : (
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
                    <button
                      onClick={() => handleStartEdit(entry)}
                      disabled={trainingWord !== null}
                      className="p-1.5 rounded-md transition-colors text-text-muted
                                 hover:text-accent hover:bg-accent/10 disabled:opacity-40"
                      title="Edit"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => handleRemove(entry.word)}
                      disabled={trainingWord !== null}
                      className="p-1.5 rounded-md transition-colors text-text-muted
                                 hover:text-error hover:bg-error/10 disabled:opacity-40"
                      title="Remove"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              )
            )}
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
