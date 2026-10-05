"""Small window for `ShuperWhisper.exe --setup-gpu` (run by the installer)."""

import webview

from . import gpu_runtime

_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  :root { --bg:#f3f3f3; --fg:#1a1a1a; --muted:#5f5f5f; --accent:#0067c0; --track:rgba(0,0,0,.1); --error:#c42b1c; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#202020; --fg:#fff; --muted:#c5c5c5; --accent:#4cc2ff; --track:rgba(255,255,255,.12); --error:#ff99a4; } }
  body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
         font:14px/20px "Segoe UI Variable Text","Segoe UI",sans-serif; user-select:none; }
  h1 { font-size:20px; line-height:28px; font-weight:600; margin:0 0 4px; }
  p { margin:0 0 16px; color:var(--muted); font-size:13px; }
  .track { height:4px; border-radius:2px; background:var(--track); overflow:hidden; }
  .bar { height:100%; width:0; background:var(--accent); transition:width .2s; }
  .row { display:flex; justify-content:space-between; align-items:center; margin-top:16px; gap:12px; }
  #msg { font-size:12px; color:var(--muted); } #msg.error { color:var(--error); }
  button { font:inherit; padding:5px 16px; border-radius:4px; border:1px solid var(--track);
           background:transparent; color:var(--fg); flex:none; }
</style></head><body>
  <h1>Setting up GPU acceleration</h1>
  <p>Downloading NVIDIA's libraries (about 1.3 GB) so ShuperWhisper can type live as you speak.</p>
  <div class="track"><div class="bar" id="bar"></div></div>
  <div class="row"><span id="msg">Starting…</span><button id="btn" onclick="act()">Cancel</button></div>
<script>
  var finished = false;
  function act() { finished ? pywebview.api.close() : pywebview.api.cancel(); }
  function tick() {
    pywebview.api.progress().then(function (p) {
      document.getElementById('bar').style.width = (p.fraction * 100) + '%';
      var msg = document.getElementById('msg');
      msg.textContent = p.message + (p.state === 'downloading' ? ' ' + Math.round(p.fraction * 100) + '%' : '');
      msg.className = p.state === 'error' ? 'error' : '';
      if (['done', 'error', 'cancelled'].indexOf(p.state) >= 0) {
        finished = true;
        document.getElementById('btn').textContent = 'Close';
        if (p.state === 'done') setTimeout(function () { pywebview.api.close(); }, 1500);
      } else { setTimeout(tick, 250); }
    });
  }
  window.addEventListener('pywebviewready', function () { pywebview.api.start().then(tick); });
</script></body></html>"""


class _Api:
    def __init__(self, setup: gpu_runtime.GpuSetup):
        self._setup = setup
        self.window = None

    def start(self):
        if gpu_runtime.installed():
            self._setup.progress = gpu_runtime.Progress(state="done", message="Already set up")
            return
        self._setup.start()

    def progress(self):
        return self._setup.progress.to_dict()

    def cancel(self):
        self._setup.cancel()

    def close(self):
        if self.window:
            self.window.destroy()


def run_setup_window() -> int:
    setup = gpu_runtime.GpuSetup()
    api = _Api(setup)
    api.window = webview.create_window("Set up GPU acceleration", html=_HTML, js_api=api,
                                       width=480, height=230, resizable=False)
    webview.start()
    setup.cancel()  # window closed mid-download
    return 0 if gpu_runtime.installed() else 1
