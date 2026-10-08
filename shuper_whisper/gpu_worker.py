"""Run the speech model in a helper process whenever the GPU may be used.

CUDA keeps a couple of hundred MB of graphics memory per process (context,
cuBLAS/cuDNN handles) until that process exits, and ctranslate2 has no way
to give it back. So the GPU model lives in a small child process: when
efficiency mode moves dictation to the processor, the child is ended and
every byte of its graphics memory goes with it. The main app never touches
CUDA itself.

RemoteTranscriber has Transcriber's interface. If the helper dies or hangs
(a driver reset, say), it carries on with a local model on the processor.
"""

import multiprocessing
import threading
from typing import Optional

from .transcriber import Transcriber, resolve_model_size

CALL_TIMEOUT = 60.0    # one transcription
LOAD_TIMEOUT = 600.0   # a model load, which may download it first


def _info(t: Transcriber) -> dict:
    return {"device": t.device, "model_size": t.model_size, "live": t.live, "loaded": t.loaded}


def _serve(conn, kwargs: dict) -> None:
    """The helper process: own a Transcriber and answer requests until "stop"."""
    t = Transcriber(**kwargs)
    while True:
        try:
            op, *args = conn.recv()
        except (EOFError, OSError):
            return  # the app went away
        if op == "stop":
            return
        try:
            if op == "load":
                t.load_model()
                result = None
            elif op == "transcribe":
                result = t.transcribe(*args)
            elif op == "words":
                audio, prompt, hotwords, beam, timestamps = args
                result = t.transcribe_words(audio, initial_prompt=prompt, hotwords=hotwords,
                                            beam_size=beam, timestamps=timestamps)
            elif op == "language":
                t.language = args[0]
                result = None
            else:
                raise ValueError(f"unknown request {op!r}")
            conn.send(("ok", result, _info(t)))
        except Exception as e:
            conn.send(("error", str(e), _info(t)))


def _spawn(kwargs: dict):
    """Start the helper; returns (connection, process)."""
    ctx = multiprocessing.get_context("spawn")
    ours, theirs = ctx.Pipe()
    process = ctx.Process(target=_serve, args=(theirs, kwargs), daemon=True, name="shuperwhisper-model")
    process.start()
    theirs.close()
    return ours, process


class HelperStopped(RuntimeError):
    """The helper process died or stopped answering."""


class RemoteTranscriber:
    """A Transcriber running in a helper process."""

    def __init__(self, model_size: str = "auto", language: str = "en", compute: str = "auto",
                 live_typing: str = "auto", spawn=_spawn):
        self._kwargs = {"model_size": model_size, "language": language, "compute": compute,
                        "live_typing": live_typing}
        self._requested = (model_size, compute, live_typing)
        self._language = language
        self._info = {"device": None, "model_size": model_size, "live": False, "loaded": False}
        self._spawn = spawn
        self._conn = None
        self._process = None
        self._lock = threading.Lock()
        self._local: Optional[Transcriber] = None  # after the helper failed

    # -- plumbing -------------------------------------------------------------------

    def _request(self, timeout: float, op: str, *args):
        with self._lock:
            if self._conn is None:
                raise HelperStopped("the speech model's helper process isn't running")
            try:
                self._conn.send((op, *args))
                if not self._conn.poll(timeout):
                    raise HelperStopped("the speech model's helper process stopped answering")
                status, result, info = self._conn.recv()
            except (EOFError, OSError) as e:
                raise HelperStopped(f"the speech model's helper process stopped ({e})") from e
        self._info = info
        if status != "ok":
            raise RuntimeError(result)
        return result

    def _fall_back_to_cpu(self, why: Exception) -> Transcriber:
        """The helper is gone: carry on with a local model on the processor."""
        print(f"[model] {why}; using the processor", flush=True)
        self.close()
        local = Transcriber(model_size=self._kwargs["model_size"], language=self._language,
                            compute="cpu", live_typing=self._kwargs["live_typing"])
        local.load_model()
        self._local = local
        return local

    def _run(self, timeout: float, op: str, *args):
        if self._local:
            return None
        try:
            return self._request(timeout, op, *args)
        except HelperStopped as e:
            self._fall_back_to_cpu(e)
            return None

    # -- Transcriber's interface --------------------------------------------------------

    def load_model(self) -> None:
        self._conn, self._process = self._spawn(dict(self._kwargs, language=self._language))
        try:
            self._request(LOAD_TIMEOUT, "load")
        except Exception:
            self.close()
            raise

    def transcribe(self, audio, initial_prompt=None, hotwords=None) -> str:
        if not self._local:
            try:
                return self._request(CALL_TIMEOUT, "transcribe", audio, initial_prompt, hotwords)
            except HelperStopped as e:
                self._fall_back_to_cpu(e)
        return self._local.transcribe(audio, initial_prompt=initial_prompt, hotwords=hotwords)

    def transcribe_words(self, audio, initial_prompt=None, hotwords=None, beam_size: int = 1,
                         timestamps: bool = False) -> list:
        if not self._local:
            try:
                return self._request(CALL_TIMEOUT, "words", audio, initial_prompt, hotwords, beam_size, timestamps)
            except HelperStopped as e:
                self._fall_back_to_cpu(e)
        return self._local.transcribe_words(audio, initial_prompt=initial_prompt, hotwords=hotwords,
                                            beam_size=beam_size, timestamps=timestamps)

    def close(self) -> None:
        """End the helper process (its graphics memory goes with it)."""
        conn, process = self._conn, self._process
        self._conn = self._process = None
        if conn is not None:
            try:
                conn.send(("stop",))
            except (OSError, EOFError):
                pass
            conn.close()
        if process is not None:
            process.join(3.0)
            if process.is_alive():
                process.terminate()
                process.join(2.0)

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        self._language = value
        if self._local:
            self._local.language = value
        else:
            self._run(CALL_TIMEOUT, "language", value)

    def needs_reload_for(self, language: str) -> bool:
        device = self.device
        return (self._requested[0] == "auto" and device is not None
                and resolve_model_size("auto", device, self.live, language) != self.model_size)

    @property
    def requested(self) -> tuple[str, str, str]:
        return self._requested

    @property
    def device(self) -> Optional[str]:
        return self._local.device if self._local else self._info["device"]

    @property
    def model_size(self) -> str:
        return self._local.model_size if self._local else self._info["model_size"]

    @property
    def live(self) -> bool:
        return self._local.live if self._local else self._info["live"]

    @property
    def loaded(self) -> bool:
        if self._local:
            return self._local.loaded
        return bool(self._info["loaded"]) and self._process is not None and self._process.is_alive()
