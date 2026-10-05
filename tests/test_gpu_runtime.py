"""GPU runtime downloader against a fake 'PyPI' serving tiny wheels."""

import hashlib
import io
import threading
import zipfile

import pytest

from shuper_whisper import gpu_runtime as gr


def make_wheel(lib: str, dlls: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in dlls.items():
            zf.writestr(f"nvidia/{lib}/bin/{name}", data)
        zf.writestr(f"nvidia/{lib}/include/{lib}.h", b"header")
        zf.writestr(f"nvidia_{lib}_cu12-1.0.dist-info/METADATA", b"meta")
    return buf.getvalue()


@pytest.fixture
def fake_pypi(monkeypatch):
    blobs = {
        "https://x/cublas.whl": make_wheel("cublas", {"cublas64_12.dll": b"A" * 3000}),
        "https://x/cudnn.whl": make_wheel("cudnn", {"cudnn64_9.dll": b"B" * 3000,
                                                    "cudnn_ops64_9.dll": b"C" * 10}),
    }
    monkeypatch.setattr(gr, "WHEELS", tuple(
        gr.Wheel(f"nvidia-{lib}-cu12", "1.0", url, hashlib.sha256(blob).hexdigest(), len(blob))
        for lib, (url, blob) in zip(("cublas", "cudnn"), blobs.items())))
    return lambda url, timeout=None: io.BytesIO(blobs[url])


def test_installs_only_dlls_and_marks_complete(fake_pypi, tmp_path):
    base = tmp_path / "cuda"
    progress = gr.Progress()
    gr.install(progress, threading.Event(), opener=fake_pypi, target=str(base),
               check_driver=lambda: (566, 36))
    folder = base / gr.version_tag()
    assert sorted(p.name for p in folder.iterdir()) == [
        "cublas64_12.dll", "cudnn64_9.dll", "cudnn_ops64_9.dll", "runtime.json"]
    assert sorted(p.name for p in base.iterdir()) == [gr.version_tag()]
    assert gr.installed(str(base))
    assert progress.to_dict() == {"state": "done", "fraction": 1.0, "message": "GPU acceleration is ready"}


def test_corrupt_download_leaves_nothing(fake_pypi, tmp_path, monkeypatch):
    wheels = list(gr.WHEELS)
    wheels[1] = gr.Wheel(wheels[1].name, wheels[1].version, wheels[1].url, "0" * 64, wheels[1].size)
    monkeypatch.setattr(gr, "WHEELS", tuple(wheels))
    base = tmp_path / "cuda"
    with pytest.raises(gr.SetupError, match="corrupted"):
        gr.install(gr.Progress(), threading.Event(), opener=fake_pypi, target=str(base),
                   check_driver=lambda: None)
    assert list(base.iterdir()) == []


def test_new_version_installs_beside_a_loaded_old_one(fake_pypi, tmp_path, monkeypatch):
    base = tmp_path / "cuda"
    old = base / "cublas-0.9_cudnn-0.9"
    old.mkdir(parents=True)
    (old / "cudnn64_9.dll").write_bytes(b"in use")
    (old / "runtime.json").write_text("{}")
    gr.install(gr.Progress(), threading.Event(), opener=fake_pypi, target=str(base),
               check_driver=lambda: None)
    assert (old / "cudnn64_9.dll").exists()              # never touched while it may be loaded
    assert gr.installed(str(base))
    gr.cleanup(str(base))                                  # next startup, before CUDA loads
    assert sorted(p.name for p in base.iterdir()) == [gr.version_tag()]


def test_already_installed_is_a_no_op(fake_pypi, tmp_path):
    base = tmp_path / "cuda"
    gr.install(gr.Progress(), threading.Event(), opener=fake_pypi, target=str(base),
               check_driver=lambda: None)
    opened = []
    p = gr.Progress()
    gr.install(p, threading.Event(), opener=lambda *a, **k: opened.append(a), target=str(base))
    assert opened == [] and p.state == "done"


def test_cancel(fake_pypi, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(gr.SetupCancelled):
        gr.install(gr.Progress(), cancel, opener=fake_pypi, target=str(tmp_path / "cuda"),
                   check_driver=lambda: None)
    assert list((tmp_path / "cuda").iterdir()) == []


def test_old_driver_refused_before_downloading(fake_pypi, tmp_path):
    opened = []
    with pytest.raises(gr.SetupError, match="Update your NVIDIA driver"):
        gr.install(gr.Progress(), threading.Event(),
                   opener=lambda *a, **k: opened.append(a), target=str(tmp_path / "cuda"),
                   check_driver=lambda: (472, 12))
    assert opened == []


def test_installed_requires_matching_versions(fake_pypi, tmp_path):
    folder = tmp_path / "cuda" / gr.version_tag()
    folder.mkdir(parents=True)
    (folder / "runtime.json").write_text('{"wheels": {"nvidia-cublas-cu12": "0.9"}}')
    assert not gr.installed(str(tmp_path / "cuda"))


def test_gpu_setup_runs_in_background(fake_pypi, tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "runtime_dir", lambda: str(tmp_path / "cuda"))
    monkeypatch.setattr(gr, "driver_version", lambda: None)
    monkeypatch.setattr(gr.urllib.request, "urlopen", fake_pypi)
    finished = threading.Event()
    states = []
    setup = gr.GpuSetup()
    activated = []
    setup.start(on_installed=lambda: activated.append(setup.progress.state),
                on_done=lambda state: (states.append(state), finished.set()))
    assert finished.wait(5)
    assert states == ["done"] and activated == ["activating"]
    setup._thread.join(1)
    assert not setup.running
