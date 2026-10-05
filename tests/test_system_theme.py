from shuper_whisper.system_theme import DEFAULT_ACCENTS, parse_accent_palette


def test_palette_picks_dark1_for_light_mode_and_light2_for_dark_mode():
    colours = [(0x99, 0xEB, 0xFF), (0x4C, 0xC2, 0xFF), (0x00, 0x91, 0xF8), (0x00, 0x78, 0xD4),
               (0x00, 0x67, 0xC0), (0x00, 0x3E, 0x92), (0x00, 0x1A, 0x68), (0xF7, 0x63, 0x0C)]
    raw = b"".join(bytes([r, g, b, 0]) for r, g, b in colours)
    assert parse_accent_palette(raw) == {"light": "#0067c0", "dark": "#4cc2ff"}


def test_bad_palette_falls_back():
    assert parse_accent_palette(b"\x00\x01") == DEFAULT_ACCENTS
