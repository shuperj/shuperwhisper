"""Settings dialog using tkinter with tabbed interface."""

import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from .audio import AudioRecorder
from .config import (
    FORMAT_MODE_LABELS,
    SUPPORTED_LANGUAGES,
    VALID_FORMAT_MODES,
    VALID_HOTKEY_MODES,
    VALID_OVERLAY_POSITIONS,
    AppConfig,
)
from .dictionary import WordDictionary
from .theme import FONTS, THEME, configure_theme


def open_settings_dialog(
    config: AppConfig,
    on_save: Callable[[AppConfig], None],
    dictionary: Optional[WordDictionary] = None,
    recorder: Optional[AudioRecorder] = None,
    transcriber=None,
) -> None:
    """Open a tabbed settings dialog. Blocks until closed."""
    root = tk.Tk()
    root.title("ShuperWhisper Settings")
    root.resizable(False, False)

    w, h = 520, 620
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Apply dark theme
    configure_theme(root)

    # Set dark title bar on Windows 11
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int),
        )
    except Exception:
        pass  # Non-Windows or API unavailable

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=16, pady=(8, 12))

    pad = {"padx": 20, "pady": 8}

    # ── Tab 1: General ──────────────────────────────────────────────
    general_frame = ttk.Frame(notebook)
    notebook.add(general_frame, text="General")

    # Hotkey - interactive key capture
    ttk.Label(general_frame, text="Hotkey:").grid(row=0, column=0, sticky="w", **pad)
    hotkey_var = tk.StringVar(value=config.hotkey)
    hotkey_entry = ttk.Entry(general_frame, textvariable=hotkey_var, width=28)
    hotkey_entry.grid(row=0, column=1, sticky="ew", **pad)

    def _on_hotkey_focus_in(event):
        """Prepare to capture key combination."""
        hotkey_entry.select_range(0, tk.END)
        hotkey_var.set("Press keys...")

    def _on_hotkey_press(event):
        """Capture key combination for hotkey."""
        # Get modifiers
        mods = []
        if event.state & 0x4:  # Control
            mods.append("ctrl")
        if event.state & 0x1:  # Shift
            mods.append("shift")
        if event.state & 0x20000:  # Alt
            mods.append("alt")

        # Get the key name
        key = event.keysym.lower()

        # Ignore standalone modifier keys
        if key in ("control_l", "control_r", "shift_l", "shift_r", "alt_l", "alt_r",
                   "win_l", "win_r", "super_l", "super_r"):
            return "break"

        # Ignore just modifier state without a trigger key
        if not key or key in mods:
            return "break"

        # Build hotkey string
        if mods:
            hotkey_str = "+".join(mods) + "+" + key
        else:
            hotkey_str = key

        hotkey_var.set(hotkey_str)
        hotkey_entry.select_clear()
        return "break"

    def _on_hotkey_focus_out(event):
        """Restore original hotkey if user didn't complete the combo."""
        if hotkey_var.get() == "Press keys...":
            hotkey_var.set(config.hotkey)

    hotkey_entry.bind("<FocusIn>", _on_hotkey_focus_in)
    hotkey_entry.bind("<KeyPress>", _on_hotkey_press)
    hotkey_entry.bind("<FocusOut>", _on_hotkey_focus_out)

    # Info label about smart hotkey behavior
    info_label = ttk.Label(
        general_frame,
        text="Quick tap = toggle mode | Hold = hold mode",
        style="Muted.TLabel",
    )
    info_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 8))

    # Model
    ttk.Label(general_frame, text="Model:").grid(row=2, column=0, sticky="w", **pad)
    model_var = tk.StringVar(value=config.model_size)
    ttk.Combobox(
        general_frame,
        textvariable=model_var,
        values=list(AppConfig.VALID_MODELS),
        state="readonly",
        width=26,
    ).grid(row=2, column=1, sticky="ew", **pad)

    # Language
    ttk.Label(general_frame, text="Language:").grid(row=3, column=0, sticky="w", **pad)
    lang_display = [f"{code} - {name}" for code, name in SUPPORTED_LANGUAGES.items()]
    lang_codes = list(SUPPORTED_LANGUAGES.keys())
    lang_var = tk.StringVar()
    try:
        idx = lang_codes.index(config.language)
        lang_var.set(lang_display[idx])
    except ValueError:
        lang_var.set(lang_display[0])
    ttk.Combobox(
        general_frame, textvariable=lang_var, values=lang_display,
        state="readonly", width=26,
    ).grid(row=3, column=1, sticky="ew", **pad)

    # Input device
    ttk.Label(general_frame, text="Input Device:").grid(row=4, column=0, sticky="w", **pad)
    try:
        devices = AudioRecorder.list_devices()
        device_names = ["System Default"] + [f"[{d['index']}] {d['name']}" for d in devices]
        device_indices = [None] + [d["index"] for d in devices]
    except Exception:
        device_names = ["System Default"]
        device_indices = [None]

    device_var = tk.StringVar()
    if config.input_device is None:
        device_var.set("System Default")
    else:
        matched = False
        for i, dev_idx in enumerate(device_indices):
            if dev_idx == config.input_device:
                device_var.set(device_names[i])
                matched = True
                break
        if not matched:
            device_var.set(f"Device {config.input_device}")

    ttk.Combobox(
        general_frame, textvariable=device_var, values=device_names,
        state="readonly", width=26,
    ).grid(row=4, column=1, sticky="ew", **pad)

    # Overlay position
    ttk.Label(general_frame, text="Overlay Position:").grid(row=5, column=0, sticky="w", **pad)
    pos_labels = {"top_center": "Top Center", "center": "Center", "bottom_center": "Bottom Center"}
    pos_var = tk.StringVar(value=pos_labels.get(config.overlay_position, "Top Center"))
    ttk.Combobox(
        general_frame, textvariable=pos_var,
        values=list(pos_labels.values()), state="readonly", width=26,
    ).grid(row=5, column=1, sticky="ew", **pad)

    # ── Tab 2: Formatting ───────────────────────────────────────────
    format_frame = ttk.Frame(notebook)
    notebook.add(format_frame, text="Formatting")

    # Default format mode
    ttk.Label(format_frame, text="Default Format Mode:").grid(
        row=0, column=0, sticky="w", **pad
    )
    fmt_display = list(FORMAT_MODE_LABELS.values())
    fmt_keys = list(FORMAT_MODE_LABELS.keys())
    fmt_var = tk.StringVar()
    try:
        fmt_idx = fmt_keys.index(config.format_mode)
        fmt_var.set(fmt_display[fmt_idx])
    except ValueError:
        fmt_var.set(fmt_display[0])
    ttk.Combobox(
        format_frame, textvariable=fmt_var, values=fmt_display,
        state="readonly", width=26,
    ).grid(row=0, column=1, sticky="ew", **pad)

    # Smart features
    ttk.Separator(format_frame, orient="horizontal").grid(
        row=1, column=0, columnspan=3, sticky="ew", pady=12, padx=20
    )
    ttk.Label(format_frame, text="Smart Features", style="Heading.TLabel").grid(
        row=2, column=0, columnspan=3, sticky="w", **pad
    )

    smart_spacing_var = tk.BooleanVar(value=config.smart_spacing)
    ttk.Checkbutton(format_frame, text="Smart spacing", variable=smart_spacing_var).grid(
        row=3, column=0, columnspan=3, sticky="w", **pad
    )
    bullet_var = tk.BooleanVar(value=config.bullet_mode)
    ttk.Checkbutton(format_frame, text="Bullet point mode", variable=bullet_var).grid(
        row=4, column=0, columnspan=3, sticky="w", **pad
    )
    # Tone settings
    ttk.Separator(format_frame, orient="horizontal").grid(
        row=5, column=0, columnspan=3, sticky="ew", pady=12, padx=20
    )
    ttk.Label(format_frame, text="Tone Settings", style="Heading.TLabel").grid(
        row=6, column=0, columnspan=3, sticky="w", **pad
    )

    # Email Tone (1-5)
    ttk.Label(format_frame, text="Email Tone:").grid(row=7, column=0, sticky="w", **pad)
    email_tone_var = tk.IntVar(value=config.email_tone)
    email_tone_scale = ttk.Scale(
        format_frame, from_=1, to=5, variable=email_tone_var,
        orient="horizontal", length=200,
    )
    email_tone_scale.grid(row=7, column=1, sticky="ew", **pad)
    email_tone_label = ttk.Label(format_frame, text=str(config.email_tone))
    email_tone_label.grid(row=7, column=2, **pad)
    email_tone_scale.configure(
        command=lambda v: email_tone_label.configure(text=str(int(float(v))))
    )
    ttk.Label(
        format_frame,
        text="1 = Warm & friendly   3 = Standard   5 = Very formal",
        style="Muted.TLabel",
    ).grid(row=8, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 8))

    # Prompt Detail (1-5)
    ttk.Label(format_frame, text="Prompt Detail:").grid(row=9, column=0, sticky="w", **pad)
    prompt_detail_var = tk.IntVar(value=config.prompt_detail)
    prompt_detail_scale = ttk.Scale(
        format_frame, from_=1, to=5, variable=prompt_detail_var,
        orient="horizontal", length=200,
    )
    prompt_detail_scale.grid(row=9, column=1, sticky="ew", **pad)
    prompt_detail_label = ttk.Label(format_frame, text=str(config.prompt_detail))
    prompt_detail_label.grid(row=9, column=2, **pad)
    prompt_detail_scale.configure(
        command=lambda v: prompt_detail_label.configure(text=str(int(float(v))))
    )
    ttk.Label(
        format_frame,
        text="1 = Ultra-concise   3 = Balanced   5 = Comprehensive",
        style="Muted.TLabel",
    ).grid(row=10, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 8))

    # ── Tab 3: Dictionary ───────────────────────────────────────────
    dict_frame = ttk.Frame(notebook)
    notebook.add(dict_frame, text="Dictionary")

    ttk.Label(dict_frame, text="Custom words for improved recognition:", style="Heading.TLabel").grid(
        row=0, column=0, columnspan=3, sticky="w", **pad
    )

    # Word list
    columns = ("word", "phonetic", "trained")
    tree = ttk.Treeview(dict_frame, columns=columns, show="headings", height=10)
    tree.heading("word", text="Word/Phrase")
    tree.heading("phonetic", text="Phonetic Hint")
    tree.heading("trained", text="Trained")
    tree.column("word", width=160)
    tree.column("phonetic", width=160)
    tree.column("trained", width=60, anchor="center")
    tree.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=20, pady=4)

    scrollbar = ttk.Scrollbar(dict_frame, orient="vertical", command=tree.yview)
    scrollbar.grid(row=1, column=3, sticky="ns", pady=4)
    tree.configure(yscrollcommand=scrollbar.set)

    def _refresh_tree():
        tree.delete(*tree.get_children())
        if dictionary:
            for entry in dictionary.entries:
                trained_mark = "Yes" if entry.trained else ""
                tree.insert("", "end", values=(entry.word, entry.phonetic, trained_mark))

    _refresh_tree()

    # Add word controls
    add_frame = ttk.Frame(dict_frame)
    add_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=20, pady=6)

    ttk.Label(add_frame, text="Word:").pack(side="left")
    word_entry = ttk.Entry(add_frame, width=16)
    word_entry.pack(side="left", padx=4)
    ttk.Label(add_frame, text="Phonetic:").pack(side="left")
    phonetic_entry = ttk.Entry(add_frame, width=16)
    phonetic_entry.pack(side="left", padx=4)

    def _add_word():
        word = word_entry.get().strip()
        if not word:
            return
        phonetic = phonetic_entry.get().strip()
        if dictionary:
            dictionary.add(word, phonetic)
            _refresh_tree()
            word_entry.delete(0, "end")
            phonetic_entry.delete(0, "end")

    ttk.Button(add_frame, text="Add", command=_add_word, width=6).pack(side="left", padx=4)

    # Action buttons
    btn_frame = ttk.Frame(dict_frame)
    btn_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=20, pady=6)

    def _remove_word():
        sel = tree.selection()
        if not sel:
            return
        word = tree.item(sel[0])["values"][0]
        if dictionary:
            dictionary.remove(str(word))
            _refresh_tree()

    def _train_word():
        sel = tree.selection()
        if not sel or not recorder or not transcriber:
            messagebox.showinfo("Training", "Select a word and ensure the app is running.")
            return
        word = str(tree.item(sel[0])["values"][0])

        def _do_train():
            messagebox.showinfo("Training", f"Say '{word}' now. Recording for 3 seconds...")
            recorder.start_recording()
            time.sleep(3)
            audio = recorder.stop_recording()
            if audio is None:
                messagebox.showerror("Training", "No audio captured.")
                return
            result = transcriber.transcribe(audio)
            if result.strip().lower() == word.strip().lower():
                if dictionary:
                    dictionary.mark_trained(word)
                    root.after(0, _refresh_tree)
                messagebox.showinfo("Training", f"Recognized correctly: '{result}'")
            else:
                messagebox.showwarning(
                    "Training",
                    f"Heard '{result}' instead of '{word}'.\n"
                    f"Try adding a phonetic hint to improve recognition.",
                )

        threading.Thread(target=_do_train, daemon=True).start()

    ttk.Button(btn_frame, text="Remove", command=_remove_word, width=10).pack(side="left", padx=4)
    ttk.Button(btn_frame, text="Train", command=_train_word, width=10).pack(side="left", padx=4)

    # ── Save / Cancel ───────────────────────────────────────────────
    bottom_frame = ttk.Frame(root)
    bottom_frame.pack(fill="x", padx=16, pady=12)

    def _on_save():
        # Extract language code
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

        # Extract format mode key
        fmt_sel = fmt_var.get()
        format_mode = "normal"
        for i, display in enumerate(fmt_display):
            if display == fmt_sel:
                format_mode = fmt_keys[i]
                break

        # Extract overlay position key
        pos_sel = pos_var.get()
        overlay_pos = "top_center"
        for key, label in pos_labels.items():
            if label == pos_sel:
                overlay_pos = key
                break

        new_config = AppConfig(
            hotkey=hotkey_var.get().strip() or "ctrl+shift+space",
            model_size=model_var.get(),
            input_device=input_device,
            language=lang_code,
            smart_spacing=smart_spacing_var.get(),
            bullet_mode=bullet_var.get(),
            email_mode=False,
            hotkey_mode="smart",  # Always smart mode now
            format_mode=format_mode,
            email_tone=int(float(email_tone_var.get())),
            prompt_detail=int(float(prompt_detail_var.get())),
            overlay_position=overlay_pos,
        )
        new_config.validate()
        try:
            on_save(new_config)
            print("Settings saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
            return
        root.destroy()

    def _on_cancel():
        root.destroy()

    ttk.Button(bottom_frame, text="Save", command=_on_save, width=12, style="Accent.TButton").pack(side="left", padx=8)
    ttk.Button(bottom_frame, text="Cancel", command=_on_cancel, width=12).pack(side="left", padx=8)

    root.mainloop()
