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
    target = tmp_path / "cuda"
    progress = gr.Progress()
    gr.install(progress, threading.Event(), opener=fake_pypi, target=str(target),
               check_driver=lambda: (566, 36))
    assert sorted(p.name for p in target.iterdir()) == [
        "cublas64_12.dll", "cudnn64_9.dll", "cudnn_ops64_9.dll", "runtime.json"]
    assert gr.installed(str(target))
    assert progress.to_dict() == {"state": "done", "fraction": 1.0, "message": "GPU acceleration is ready"}


def test_corrupt_download_leaves_nothing(fake_pypi, tmp_path, monkeypatch):
    wheels = list(gr.WHEELS)
    wheels[1] = gr.Wheel(wheels[1].name, wheels[1].version, wheels[1].url, "0" * 64, wheels[1].size)
    monkeypatch.setattr(gr, "WHEELS", tuple(wheels))
    target = tmp_path / "cuda"
    with pytest.raises(gr.SetupError, match="corrupted"):
        gr.install(gr.Progress(), threading.Event(), opener=fake_pypi, target=str(target),
                   check_driver=lambda: None)
    assert not target.exists() and not (tmp_path / "cuda.partial").exists()


def test_existing_runtime_kept_when_reinstall_fails(fake_pypi, tmp_path, monkeypatch):
    target = tmp_path / "cuda"
    gr.install(gr.Progress(), threading.Event(), opener=fake_pypi, target=str(target),
               check_driver=lambda: None)
    wheels = list(gr.WHEELS)
    wheels[0] = gr.Wheel(wheels[0].name, wheels[0].version, wheels[0].url, "0" * 64, wheels[0].size)
    monkeypatch.setattr(gr, "WHEELS", tuple(wheels))
    with pytest.raises(gr.SetupError):
        gr.install(gr.Progress(), threading.Event(), opener=fake_pypi, target=str(target),
                   check_driver=lambda: None)
    assert (target / "cublas64_12.dll").exists()


def test_cancel(fake_pypi, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(gr.SetupCancelled):
        gr.install(gr.Progress(), cancel, opener=fake_pypi, target=str(tmp_path / "cuda"),
                   check_driver=lambda: None)
    assert not (tmp_path / "cuda").exists()


def test_old_driver_refused_before_downloading(fake_pypi, tmp_path):
    opened = []
    with pytest.raises(gr.SetupError, match="Update your NVIDIA driver"):
        gr.install(gr.Progress(), threading.Event(),
                   opener=lambda *a, **k: opened.append(a), target=str(tmp_path / "cuda"),
                   check_driver=lambda: (472, 12))
    assert opened == []


def test_installed_requires_matching_versions(fake_pypi, tmp_path):
    target = tmp_path / "cuda"
    target.mkdir()
    (target / "runtime.json").write_text('{"wheels": {"nvidia-cublas-cu12": "0.9"}}')
    assert not gr.installed(str(target))


def test_gpu_setup_runs_in_background(fake_pypi, tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "runtime_dir", lambda: str(tmp_path / "cuda"))
    monkeypatch.setattr(gr, "driver_version", lambda: None)
    monkeypatch.setattr(gr.urllib.request, "urlopen", fake_pypi)
    finished = threading.Event()
    states = []
    setup = gr.GpuSetup()
    setup.start(on_done=lambda state: (states.append(state), finished.set()))
    assert finished.wait(5)
    assert states == ["done"]
    setup._thread.join(1)
    assert not setup.running
