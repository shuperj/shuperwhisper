"""Notice when another program is using the graphics card heavily, so
efficiency mode can move dictation to the processor and free the GPU.

Reads the per-process counters Task Manager shows ("GPU Process Memory" and
"GPU Engine" through PDH), every POLL_SECONDS. No admin rights needed.
"""

import ctypes
import ctypes.wintypes as wt
import os
import re
import threading
import time
from typing import Callable, Optional

GIB = 1024 ** 3

# Always-on GPU users that aren't a reason to step aside.
IGNORED = frozenset({
    "dwm.exe", "explorer.exe", "csrss.exe", "searchhost.exe", "shellexperiencehost.exe",
    "textinputhost.exe", "startmenuexperiencehost.exe",
    "wallpaper32.exe", "wallpaper64.exe", "webwallpaper32.exe", "webwallpaper64.exe", "lively.exe",
    "shuperwhisper.exe",  # another copy of us
})


class Detector:
    """Decides from samples whether the GPU is busy with another program.

    Busy: one program holds MEMORY_BYTES of graphics memory, or keeps the 3D
    engine at LOAD_PERCENT or more for LOAD_SECONDS. Clear again after
    CLEAR_SECONDS without either.
    """

    MEMORY_BYTES = 2 * GIB
    LOAD_PERCENT = 50.0
    LOAD_SECONDS = 15.0
    CLEAR_SECONDS = 30.0

    def __init__(self):
        self.busy = False
        self.reason = ""          # the program that made it busy
        self._loaded_since: dict[str, float] = {}
        self._quiet_since: Optional[float] = None

    def update(self, programs: list[tuple[str, float, float]], now: float) -> bool:
        """``programs``: (name, graphics memory in bytes, 3D load in %)."""
        culprit = ""
        loaded = set()
        for name, memory, load in programs:
            if memory >= self.MEMORY_BYTES:
                culprit = culprit or name
            if load >= self.LOAD_PERCENT:
                loaded.add(name)
                since = self._loaded_since.setdefault(name, now)
                if now - since >= self.LOAD_SECONDS:
                    culprit = culprit or name
        self._loaded_since = {n: t for n, t in self._loaded_since.items() if n in loaded}
        if culprit:
            self.busy, self.reason, self._quiet_since = True, culprit, None
        elif self.busy:
            self._quiet_since = self._quiet_since or now
            if now - self._quiet_since >= self.CLEAR_SECONDS:
                self.busy, self.reason, self._quiet_since = False, "", None
        return self.busy


# -- PDH ------------------------------------------------------------------------

_PDH_FMT_DOUBLE = 0x200
_PDH_FMT_NOCAP100 = 0x8000
_PDH_MORE_DATA = 0x800007D2
_PID = re.compile(r"pid_(\d+)_")


class _Value(ctypes.Structure):
    _fields_ = [("CStatus", wt.DWORD), ("doubleValue", ctypes.c_double)]  # union: double at offset 8


class _Item(ctypes.Structure):
    _fields_ = [("szName", wt.LPWSTR), ("FmtValue", _Value)]


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def _process_names(parents: Optional[dict] = None) -> dict[int, str]:
    """pid -> exe name for every process, from a toolhelp snapshot (works for
    protected processes, which can't be opened). Fills ``parents`` with
    pid -> parent pid if given."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    names: dict[int, str] = {}
    if not snap or snap == wt.HANDLE(-1).value:
        return names
    entry = _PROCESSENTRY32W(dwSize=ctypes.sizeof(_PROCESSENTRY32W))
    ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        names[entry.th32ProcessID] = entry.szExeFile.lower()
        if parents is not None:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
        ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    kernel32.CloseHandle(snap)
    return names


class PdhSampler:
    """Per-process graphics memory and 3D load, keyed by program name."""

    MEMORY = r"\GPU Process Memory(*)\Dedicated Usage"
    LOAD = r"\GPU Engine(*engtype_3D)\Utilization Percentage"

    def __init__(self):
        self._pdh = ctypes.WinDLL("pdh")
        self._query = wt.HANDLE()
        self._memory = wt.HANDLE()
        self._load = wt.HANDLE()
        self._names: dict[int, str] = {}
        self._parents: dict[int, int] = {}
        if self._pdh.PdhOpenQueryW(None, None, ctypes.byref(self._query)) != 0:
            raise OSError("PdhOpenQuery failed")
        for path, handle in ((self.MEMORY, self._memory), (self.LOAD, self._load)):
            status = self._pdh.PdhAddEnglishCounterW(self._query, path, None, ctypes.byref(handle))
            if status != 0:
                raise OSError(f"GPU counter unavailable ({status:#x})")
        self._pdh.PdhCollectQueryData(self._query)  # the load is a rate: prime it

    def _values(self, counter) -> dict[int, float]:
        size, count = wt.DWORD(0), wt.DWORD(0)
        flags = _PDH_FMT_DOUBLE | _PDH_FMT_NOCAP100
        status = self._pdh.PdhGetFormattedCounterArrayW(counter, flags, ctypes.byref(size),
                                                        ctypes.byref(count), None)
        if status & 0xFFFFFFFF != _PDH_MORE_DATA or not size.value:
            return {}
        buffer = (ctypes.c_byte * size.value)()
        if self._pdh.PdhGetFormattedCounterArrayW(counter, flags, ctypes.byref(size), ctypes.byref(count),
                                                  buffer) != 0:
            return {}
        items = ctypes.cast(buffer, ctypes.POINTER(_Item))
        out: dict[int, float] = {}
        for i in range(count.value):
            item = items[i]
            match = _PID.match(item.szName or "")
            if match and item.FmtValue.CStatus in (0, 1):  # PDH_CSTATUS_VALID_DATA / NEW_DATA
                pid = int(match.group(1))
                out[pid] = out.get(pid, 0.0) + item.FmtValue.doubleValue
        return out

    def _name(self, pid: int) -> str:
        if pid not in self._names:
            self._parents = {}
            self._names = _process_names(self._parents)  # also catches protected ones like dwm.exe
        return self._names.get(pid, f"pid {pid}")

    def sample(self) -> list[tuple[str, float, float]]:
        if self._pdh.PdhCollectQueryData(self._query) != 0:
            return []
        memory, load = self._values(self._memory), self._values(self._load)
        own = os.getpid()
        out = []
        for pid in set(memory) | set(load):
            name = self._name(pid)
            if pid == own or self._parents.get(pid) == own:  # us, or our model helper
                continue
            if name not in IGNORED:
                out.append((name, memory.get(pid, 0.0), load.get(pid, 0.0)))
        return out


class GpuMonitor:
    """Samples every POLL_SECONDS on a thread; ``on_change(busy, reason)``
    runs when the verdict changes."""

    POLL_SECONDS = 5.0

    def __init__(self, on_change: Callable[[bool, str], None],
                 sampler_factory: Callable[[], object] = PdhSampler,
                 clock: Callable[[], float] = time.monotonic):
        self._on_change = on_change
        self._sampler_factory = sampler_factory
        self._clock = clock
        self.detector = Detector()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="gpu-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def _run(self) -> None:
        try:
            sampler = self._sampler_factory()
        except Exception as e:  # no GPU counters (old Windows, no GPU driver)
            print(f"[gpu] can't watch the graphics card: {e}", flush=True)
            return
        while not self._stop.wait(self.POLL_SECONDS):
            self.check(sampler)

    def check(self, sampler) -> None:
        was = self.detector.busy
        try:
            programs = sampler.sample()
        except Exception:
            return
        busy = self.detector.update(programs, self._clock())
        if busy != was:
            self._on_change(busy, self.detector.reason)
