import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, Loader2, Mic, Pencil, Plus, Trash2, X } from "lucide-react";
import type { DictionaryEntry, TrainingStatus } from "@/lib/types";
import { addWord, getDictionary, removeWord, trainWord, updateWord } from "@/lib/bridge";

const INPUT = "control h-8 px-2.5 text-[14px] placeholder:text-[var(--muted)] outline-none";
const ICON_BUTTON =
  "p-1.5 rounded-md transition-colors text-muted hover:bg-[var(--control-hover)] disabled:opacity-40";

function TrainingBanner({ status }: { status: TrainingStatus }) {
  const round = `Round ${status.round}/${status.totalRounds}`;
  let icon = <Loader2 size={14} className="animate-spin" />;
  let text: string;
  let tone = "text-accent";
  switch (status.status) {
    case "recording":
      icon = <Mic size={14} className="animate-pulse" />;
      text = `${round}: say “${status.word}” now`;
      break;
    case "transcribing":
      text = `${round}: listening back…`;
      break;
    case "round_done":
      icon = status.roundSuccess ? <Check size={14} /> : <Mic size={14} />;
      text = `${round}: heard “${status.transcribed}”`;
      break;
    case "done":
      icon = <Check size={14} />;
      text = status.alreadyRecognized
        ? `Trained. Whisper already recognises “${status.word}”.`
        : status.learnedHint
          ? `Trained. When Whisper hears “${status.learnedHint}” it will type “${status.word}”.`
          : "Trained.";
      break;
    default:
      icon = <AlertCircle size={14} />;
      text = `Training failed: ${status.error}`;
      tone = "text-error";
  }
  return (
    <div className={`px-4 py-2.5 text-[12px] flex items-center gap-2 ${tone}`}>
      {icon}
      <span>{text}</span>
    </div>
  );
}

export function DictionarySection({
  trainingStatus,
  clearTraining,
}: {
  trainingStatus: TrainingStatus | null;
  clearTraining: () => void;
}) {
  const [entries, setEntries] = useState<DictionaryEntry[]>([]);
  const [word, setWord] = useState("");
  const [phonetic, setPhonetic] = useState("");
  const [trainingWord, setTrainingWord] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editWord, setEditWord] = useState("");
  const [editPhonetic, setEditPhonetic] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setEntries(await getDictionary());
    } catch {
      /* keep what we have */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!trainingStatus) return;
    if (trainingStatus.status === "done" || trainingStatus.status === "error") {
      setTrainingWord(null);
      load();
      const timer = setTimeout(clearTraining, 6000);
      return () => clearTimeout(timer);
    }
  }, [trainingStatus, load, clearTraining]);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  };

  const add = () => {
    const w = word.trim();
    if (!w) return;
    run(async () => {
      const result = await addWord(w, phonetic.trim());
      if (result.success === false) throw new Error(result.error ?? "Couldn't add that word");
      setWord("");
      setPhonetic("");
    });
  };

  const train = async (w: string) => {
    setTrainingWord(w);
    clearTraining();
    setError(null);
    try {
      const result = await trainWord(w);
      if (!result.success) {
        setError(result.error ?? "Training failed");
        setTrainingWord(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Training failed");
      setTrainingWord(null);
    }
  };

  const saveEdit = () => {
    if (!editing || !editWord.trim()) return;
    run(async () => {
      const result = await updateWord(editing, editWord.trim(), editPhonetic.trim());
      if (!result.success) throw new Error(result.error ?? "Couldn't save");
      setEditing(null);
    });
  };

  return (
    <div className="card divide-y divide-[var(--stroke)]">
      {trainingStatus && <TrainingBanner status={trainingStatus} />}
      {error && <div className="px-4 py-2.5 text-[12px] text-error">{error}</div>}

      {entries.length === 0 ? (
        <div className="px-4 py-6 text-center">
          <div className="text-[14px]">No words yet</div>
          <div className="text-[12px] text-muted mt-1">Add names or jargon ShuperWhisper keeps getting wrong.</div>
        </div>
      ) : (
        <div className="max-h-[280px] overflow-y-auto divide-y divide-[var(--stroke)]">
          {entries.map((entry) =>
            editing === entry.word ? (
              <div key={entry.word} className="px-4 py-2 flex items-center gap-2">
                <input
                  className={`${INPUT} flex-1 min-w-0`}
                  value={editWord}
                  onChange={(e) => setEditWord(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveEdit();
                    if (e.key === "Escape") setEditing(null);
                  }}
                  autoFocus
                />
                <input
                  className={`${INPUT} w-[170px]`}
                  value={editPhonetic}
                  placeholder="Sounds like (optional)"
                  onChange={(e) => setEditPhonetic(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveEdit();
                    if (e.key === "Escape") setEditing(null);
                  }}
                />
                <button className={ICON_BUTTON} title="Save" onClick={saveEdit}>
                  <Check size={14} />
                </button>
                <button className={ICON_BUTTON} title="Cancel" onClick={() => setEditing(null)}>
                  <X size={14} />
                </button>
              </div>
            ) : (
              <div key={entry.word} className="px-4 py-2.5 flex items-center gap-3 group hover:bg-[var(--card-hover)]">
                <div className="flex-1 min-w-0">
                  <div className="text-[14px] truncate">{entry.word}</div>
                  {entry.phonetic && (
                    <div className="text-[12px] text-muted truncate">sounds like “{entry.phonetic}”</div>
                  )}
                </div>
                {entry.trained && (
                  <span className="flex items-center gap-1 text-[12px] text-accent shrink-0">
                    <Check size={12} /> Trained
                  </span>
                )}
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity shrink-0">
                  <button
                    className={`${ICON_BUTTON} ${trainingWord === entry.word ? "text-accent animate-pulse" : ""}`}
                    title="Train: say the word three times"
                    disabled={trainingWord !== null}
                    onClick={() => train(entry.word)}
                  >
                    <Mic size={14} />
                  </button>
                  <button
                    className={ICON_BUTTON}
                    title="Edit"
                    disabled={trainingWord !== null}
                    onClick={() => {
                      setEditing(entry.word);
                      setEditWord(entry.word);
                      setEditPhonetic(entry.phonetic);
                    }}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    className={`${ICON_BUTTON} hover:text-error`}
                    title="Remove"
                    disabled={trainingWord !== null}
                    onClick={() => run(() => removeWord(entry.word))}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            )
          )}
        </div>
      )}

      <div className="px-4 py-3 flex gap-2">
        <input
          className={`${INPUT} flex-1 min-w-0`}
          value={word}
          placeholder="Word or phrase"
          onChange={(e) => setWord(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
        />
        <input
          className={`${INPUT} w-[170px]`}
          value={phonetic}
          placeholder="Sounds like (optional)"
          onChange={(e) => setPhonetic(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
        />
        <button
          className="btn-accent h-8 px-3 inline-flex items-center gap-1 text-[14px] disabled:opacity-40"
          disabled={!word.trim()}
          onClick={add}
        >
          <Plus size={14} /> Add
        </button>
      </div>
    </div>
  );
}
