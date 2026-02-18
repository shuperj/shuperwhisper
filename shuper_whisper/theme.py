"""Unified dark theme configuration for ShuperWhisper UI.

Extends the overlay's color palette to create a cohesive visual design
across settings dialog and overlay components.
"""

from tkinter import ttk

# Color Palette - extends overlay's existing colors
THEME = {
    # Base colors (from overlay)
    'bg_dark': '#1a1a2e',        # Primary background (overlay pill)
    'bg_medium': '#252538',      # Secondary background
    'bg_light': '#2f2f44',       # Tertiary background
    'border': '#3a3a5c',         # Border color (overlay pill border)
    'accent': '#ff4466',         # Accent/focus color (recording glow)

    # Text colors
    'text_primary': '#e8e8ee',   # Primary text (high contrast)
    'text_secondary': '#cccccc', # Secondary text (overlay mode text)
    'text_muted': '#888888',     # Muted text (overlay arrows)

    # Control colors
    'control_bg': '#2f2f44',     # Input backgrounds
    'control_border': '#4a4a6a', # Input borders (overlay idle bars)
    'control_focus': '#ff4466',  # Focus indicator (matches accent)
    'control_hover': '#3f3f54',  # Hover state

    # Semantic colors
    'success': '#66cc88',        # Success indicators
    'warning': '#ffaa44',        # Warning indicators
    'error': '#ff4466',          # Error indicators (matches accent)

    # Widget-specific
    'treeview_bg': '#1e1e32',    # Treeview background
    'treeview_alt': '#232338',   # Alternating row color
    'treeview_select': '#3a3a5c',# Selected row
}

# Typography - consistent with overlay's Segoe UI
FONTS = {
    'heading': ('Segoe UI', 10, 'bold'),    # Section headers
    'body': ('Segoe UI', 9),                # Regular text, labels
    'small': ('Segoe UI', 8),               # Helper text
    'mono': ('Consolas', 9),                # Code/hotkey display
}


def configure_theme(root) -> ttk.Style:
    """Configure ttk.Style with ShuperWhisper dark theme.

    Args:
        root: The root tkinter window

    Returns:
        Configured ttk.Style instance
    """
    style = ttk.Style(root)

    # Use 'clam' theme as base — the default Windows themes
    # ('vista', 'winnative') ignore most style.configure color settings
    style.theme_use('clam')

    # ── Configure base window ──
    root.configure(bg=THEME['bg_dark'])

    # ── TFrame (base container) ──
    style.configure('TFrame',
        background=THEME['bg_dark'])

    # ── TLabel (text labels) ──
    style.configure('TLabel',
        background=THEME['bg_dark'],
        foreground=THEME['text_primary'],
        font=FONTS['body'])

    # Heading variant for section headers
    style.configure('Heading.TLabel',
        background=THEME['bg_dark'],
        foreground=THEME['text_primary'],
        font=FONTS['heading'])

    # Muted variant for helper text
    style.configure('Muted.TLabel',
        background=THEME['bg_dark'],
        foreground=THEME['text_muted'],
        font=FONTS['small'])

    # ── TEntry (text input) ──
    style.configure('TEntry',
        fieldbackground=THEME['control_bg'],
        foreground=THEME['text_primary'],
        bordercolor=THEME['control_border'],
        lightcolor=THEME['control_border'],
        darkcolor=THEME['control_border'],
        insertcolor=THEME['text_primary'],  # Cursor color
        padding=(6, 4))  # Internal text padding

    style.map('TEntry',
        fieldbackground=[('readonly', THEME['bg_medium'])],
        bordercolor=[('focus', THEME['control_focus'])],
        lightcolor=[('focus', THEME['control_focus'])],
        darkcolor=[('focus', THEME['control_focus'])])

    # ── TCombobox (dropdown) ──
    style.configure('TCombobox',
        fieldbackground=THEME['control_bg'],
        foreground=THEME['text_primary'],
        background=THEME['control_bg'],
        bordercolor=THEME['control_border'],
        arrowcolor=THEME['text_secondary'],
        insertcolor=THEME['text_primary'],
        padding=(6, 4))  # Internal text padding

    style.map('TCombobox',
        fieldbackground=[
            ('readonly', THEME['control_bg']),
            ('disabled', THEME['bg_medium'])
        ],
        foreground=[
            ('readonly', THEME['text_primary']),
            ('disabled', THEME['text_muted'])
        ],
        bordercolor=[('focus', THEME['control_focus'])],
        arrowcolor=[
            ('disabled', THEME['text_muted']),
            ('pressed', THEME['accent'])
        ])

    # Configure combobox dropdown list
    root.option_add('*TCombobox*Listbox.background', THEME['control_bg'])
    root.option_add('*TCombobox*Listbox.foreground', THEME['text_primary'])
    root.option_add('*TCombobox*Listbox.selectBackground', THEME['accent'])
    root.option_add('*TCombobox*Listbox.selectForeground', THEME['text_primary'])

    # ── TButton (clickable button) ──
    style.configure('TButton',
        background=THEME['control_bg'],
        foreground=THEME['text_primary'],
        bordercolor=THEME['control_border'],
        lightcolor=THEME['control_border'],
        darkcolor=THEME['control_border'],
        font=FONTS['body'],
        padding=(12, 6))

    style.map('TButton',
        background=[
            ('active', THEME['control_hover']),
            ('pressed', THEME['border'])
        ],
        foreground=[('disabled', THEME['text_muted'])],
        bordercolor=[('focus', THEME['control_focus'])])

    # Accent button variant (for primary actions)
    style.configure('Accent.TButton',
        background=THEME['accent'],
        foreground=THEME['text_primary'],
        bordercolor=THEME['accent'],
        font=FONTS['body'],
        padding=(12, 6))

    style.map('Accent.TButton',
        background=[
            ('active', '#ff5577'),  # Lighter on hover
            ('pressed', '#ee3355')   # Darker on press
        ])

    # ── TCheckbutton (checkbox) ──
    style.configure('TCheckbutton',
        background=THEME['bg_dark'],
        foreground=THEME['text_primary'],
        font=FONTS['body'],
        padding=(4, 2))

    style.map('TCheckbutton',
        background=[('active', THEME['bg_dark'])],
        foreground=[('disabled', THEME['text_muted'])])

    # ── TScale (slider) ──
    style.configure('TScale',
        background=THEME['bg_dark'],
        troughcolor=THEME['control_bg'],
        bordercolor=THEME['control_border'],
        lightcolor=THEME['control_border'],
        darkcolor=THEME['control_border'])

    style.map('TScale',
        troughcolor=[('active', THEME['control_hover'])],
        bordercolor=[('focus', THEME['control_focus'])])

    # ── Horizontal.TScale (horizontal slider) ──
    style.configure('Horizontal.TScale',
        background=THEME['accent'])  # Slider thumb color

    # ── TNotebook (tabbed interface) ──
    style.configure('TNotebook',
        background=THEME['bg_dark'],
        bordercolor=THEME['border'],
        lightcolor=THEME['border'],
        darkcolor=THEME['border'])

    style.configure('TNotebook.Tab',
        background=THEME['bg_medium'],
        foreground=THEME['text_secondary'],
        bordercolor=THEME['border'],
        lightcolor=THEME['border'],
        darkcolor=THEME['border'],
        font=FONTS['body'],
        padding=(12, 6))

    style.map('TNotebook.Tab',
        background=[
            ('selected', THEME['bg_dark']),
            ('active', THEME['control_hover'])
        ],
        foreground=[
            ('selected', THEME['text_primary']),
            ('active', THEME['text_primary'])
        ],
        expand=[('selected', (1, 1, 1, 0))])  # Expand selected tab

    # ── TSeparator (horizontal/vertical line) ──
    style.configure('TSeparator',
        background=THEME['border'])

    # ── Treeview (table/list) ──
    style.configure('Treeview',
        background=THEME['treeview_bg'],
        foreground=THEME['text_primary'],
        fieldbackground=THEME['treeview_bg'],
        bordercolor=THEME['border'],
        lightcolor=THEME['border'],
        darkcolor=THEME['border'],
        font=FONTS['body'])

    style.map('Treeview',
        background=[
            ('selected', THEME['treeview_select']),
            ('active', THEME['control_hover'])
        ],
        foreground=[('selected', THEME['text_primary'])])

    # Treeview heading (column headers)
    style.configure('Treeview.Heading',
        background=THEME['bg_medium'],
        foreground=THEME['text_primary'],
        bordercolor=THEME['border'],
        lightcolor=THEME['border'],
        darkcolor=THEME['border'],
        font=FONTS['heading'])

    style.map('Treeview.Heading',
        background=[('active', THEME['control_hover'])],
        foreground=[('active', THEME['text_primary'])])

    # ── Scrollbar ──
    style.configure('Vertical.TScrollbar',
        background=THEME['control_bg'],
        troughcolor=THEME['bg_medium'],
        bordercolor=THEME['border'],
        arrowcolor=THEME['text_secondary'])

    style.map('Vertical.TScrollbar',
        background=[
            ('active', THEME['control_hover']),
            ('pressed', THEME['border'])
        ])

    return style
