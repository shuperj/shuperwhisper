"""Build dist/ShuperWhisper (PyInstaller one-folder) for packaging/installer.iss.

    python packaging/build.py

The CUDA runtime is never bundled: the installer offers to download it
(ShuperWhisper.exe --setup-gpu) when it finds an NVIDIA card.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXCLUDE = ("nvidia", "ctranslate2.converters", "torch", "transformers", "tensorflow",
            "numba", "llvmlite", "scipy", "pandas", "sklearn", "matplotlib", "IPython")


def run(cmd, cwd=ROOT):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, shell=(os.name == "nt" and cmd[0] == "npm"))


def main() -> None:
    ui = os.path.join(ROOT, "shuper_whisper", "ui")
    run(["npm", "ci"], cwd=ui)
    run(["npm", "run", "build"], cwd=ui)
    run([sys.executable, "packaging/convert_icon.py"])
    run([sys.executable, "packaging/create_wizard_images.py"])
    # comtypes generates the UIAutomation wrapper on first use; do it now so
    # PyInstaller can bundle comtypes.gen.
    run([sys.executable, "-c", "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')"])
    run([
        sys.executable, "-m", "PyInstaller", "main.py",
        "--name", "ShuperWhisper", "--noconsole", "--noconfirm", "--onedir",
        "--icon", "packaging/ShuperWhisper.ico",
        "--add-data", f"shuper_whisper/ui/dist{os.pathsep}shuper_whisper/ui/dist",
        "--collect-data", "faster_whisper",
        "--collect-binaries", "ctranslate2",
        "--collect-submodules", "comtypes.gen",
        "--hidden-import", "comtypes.gen.UIAutomationClient",
        # Keep the pip CUDA wheels out even if they're installed in this env,
        # and ctranslate2's model-converter extras (torch, transformers...),
        # which the app never imports but PyInstaller would follow.
        *[arg for module in _EXCLUDE for arg in ("--exclude-module", module)],
    ])
    print("\nBuilt dist/ShuperWhisper. Now compile packaging/installer.iss with Inno Setup.")


if __name__ == "__main__":
    main()
