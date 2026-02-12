"""Settings dialog using tkinter."""

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from .audio import AudioRecorder
from .config import SUPPORTED_LANGUAGES, AppConfig


def open_settings_dialog(
    config: AppConfig,
    on_save: Callable[[AppConfig], None],
) -> None:
    """Open a modal settings dialog. Blocks until the dialog is closed.

    Args:
        config: Current application configuration.
        on_save: Called with the new AppConfig when the user clicks Save.
    """
    root = tk.Tk()
    root.title("ShuperWhisper Settings")
    root.resizable(False, False)

    # Center the window
    root.update_idletasks()
    w, h = 420, 460
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    pad = {"padx": 10, "pady": 4}

    # --- Hotkey ---
    ttk.Label(root, text="Hotkey:").grid(row=0, column=0, sticky="w", **pad)
    hotkey_var = tk.StringVar(value=config.hotkey)
    ttk.Entry(root, textvariable=hotkey_var, width=30).grid(
        row=0, column=1, sticky="ew", **pad
    )

    # --- Model size ---
    ttk.Label(root, text="Model:").grid(row=1, column=0, sticky="w", **pad)
    model_var = tk.StringVar(value=config.model_size)
    model_combo = ttk.Combobox(
        root,
        textvariable=model_var,
        values=list(AppConfig.VALID_MODELS),
        state="readonly",
        width=28,
    )
    model_combo.grid(row=1, column=1, sticky="ew", **pad)

    # --- Language ---
    ttk.Label(root, text="Language:").grid(row=2, column=0, sticky="w", **pad)
    lang_display = [f"{code} - {name}" for code, name in SUPPORTED_LANGUAGES.items()]
    lang_codes = list(SUPPORTED_LANGUAGES.keys())
    lang_var = tk.StringVar()
    try:
        idx = lang_codes.index(config.language)
        lang_var.set(lang_display[idx])
    except ValueError:
        lang_var.set(lang_display[0])
    lang_combo = ttk.Combobox(
        root, textvariable=lang_var, values=lang_display, state="readonly", width=28
    )
    lang_combo.grid(row=2, column=1, sticky="ew", **pad)

    # --- Input device ---
    ttk.Label(root, text="Input Device:").grid(row=3, column=0, sticky="w", **pad)
    try:
        devices = AudioRecorder.list_devices()
        device_names = ["System Default"] + [
            f"[{d['index']}] {d['name']}" for d in devices
        ]
        device_indices = [None] + [d["index"] for d in devices]
    except Exception:
        device_names = ["System Default"]
        device_indices = [None]

    device_var = tk.StringVar()
    if config.input_device is None:
        device_var.set("System Default")
    else:
        # Find matching device
        matched = False
        for i, idx in enumerate(device_indices):
            if idx == config.input_device:
                device_var.set(device_names[i])
                matched = True
                break
        if not matched:
            device_var.set(f"Device {config.input_device}")

    device_combo = ttk.Combobox(
        root, textvariable=device_var, values=device_names, state="readonly", width=28
    )
    device_combo.grid(row=3, column=1, sticky="ew", **pad)

    # --- Separator ---
    ttk.Separator(root, orient="horizontal").grid(
        row=4, column=0, columnspan=2, sticky="ew", pady=8, padx=10
    )

    # --- Smart features ---
    ttk.Label(root, text="Smart Features", font=("", 9, "bold")).grid(
        row=5, column=0, columnspan=2, sticky="w", **pad
    )

    smart_spacing_var = tk.BooleanVar(value=config.smart_spacing)
    ttk.Checkbutton(root, text="Smart spacing", variable=smart_spacing_var).grid(
        row=6, column=0, columnspan=2, sticky="w", **pad
    )

    bullet_var = tk.BooleanVar(value=config.bullet_mode)
    ttk.Checkbutton(root, text="Bullet point mode", variable=bullet_var).grid(
        row=7, column=0, columnspan=2, sticky="w", **pad
    )

    email_var = tk.BooleanVar(value=config.email_mode)
    ttk.Checkbutton(root, text="Email formatting", variable=email_var).grid(
        row=8, column=0, columnspan=2, sticky="w", **pad
    )

    # --- Separator ---
    ttk.Separator(root, orient="horizontal").grid(
        row=9, column=0, columnspan=2, sticky="ew", pady=8, padx=10
    )

    # --- Autostart ---
    autostart_var = tk.BooleanVar(value=config.autostart)
    ttk.Checkbutton(root, text="Start with Windows", variable=autostart_var).grid(
        row=10, column=0, columnspan=2, sticky="w", **pad
    )

    # --- Buttons ---
    btn_frame = ttk.Frame(root)
    btn_frame.grid(row=11, column=0, columnspan=2, pady=16)

    def _on_save():
        # Extract language code from display string
        lang_sel = lang_var.get()
        lang_code = "en"
        for i, display in enumerate(lang_display):
            if display == lang_sel:
                lang_code = lang_codes[i]
                break

        # Extract device index
        dev_sel = device_var.get()
        input_device = None
        for i, name in enumerate(device_names):
            if name == dev_sel:
                input_device = device_indices[i]
                break

        new_config = AppConfig(
            hotkey=hotkey_var.get().strip() or "ctrl+shift+space",
            model_size=model_var.get(),
            input_device=input_device,
            language=lang_code,
            autostart=autostart_var.get(),
            smart_spacing=smart_spacing_var.get(),
            bullet_mode=bullet_var.get(),
            email_mode=email_var.get(),
        )
        new_config.validate()
        on_save(new_config)
        root.destroy()

    def _on_cancel():
        root.destroy()

    ttk.Button(btn_frame, text="Save", command=_on_save, width=12).pack(
        side="left", padx=8
    )
    ttk.Button(btn_frame, text="Cancel", command=_on_cancel, width=12).pack(
        side="left", padx=8
    )

    root.mainloop()
