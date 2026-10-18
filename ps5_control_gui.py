#!/usr/bin/env python3
"""
PS5 Linux Control Panel
------------------------
A small GUI for:
  - Setting the fan thermal target (/sys/devices/platform/ps5-fan/target_temp)
  - Running ps5_control --fan on/off/max and --boost on/off (if installed)
  - Switching the front LED indicator color (/sys/class/leds/ps5:*:indicator)
  - Showing live CPU/NVMe temps from `sensors`
  - An always-on-top temperature overlay you can pin to any screen corner
  - Dark / Light / System themes and a font picker (Style tab)

Run this WITH root, since every control it touches needs it:
    sudo python3 ps5_control_gui.py
(or install it with install.sh and launch "PS5 Control Panel" from the app menu)

Requires: python3-tk (sudo pacman -S tk) and, for smooth anti-aliased
graphics, Pillow (sudo pacman -S python-pillow). Without Pillow the app
still works but buttons and the graph look more pixelated.
"""

import configparser
import json
import os
import pwd
import re
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageDraw, ImageTk
    HAVE_PIL = True
    RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
except Exception:  # Pillow (or its Tk bridge) missing -> fall back to plain canvas shapes
    HAVE_PIL = False
    RESAMPLE = None

LED_DIR = "/sys/class/leds"
FAN_TARGET_PATH = "/sys/devices/platform/ps5-fan/target_temp"
SETTINGS_DIR = "/var/lib/ps5-control-panel"
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")

LED_COLORS = [
    "off", "all_dim_purplish", "blue_breathe", "blue_hint_purple", "blue_rich",
    "blue_to_richblue", "blue_white_anim", "dim_cool_white", "orange_breathe",
    "orange_dim", "pink_breathe", "pink_breathe_fast", "pink_purple",
    "pink_violet_dim", "purple", "purple_white", "purplish_blue_white",
    "salmon_pink", "salmon_pink_breathe", "soft_blue_purple_1",
    "soft_blue_purple_2", "soft_orange_dim", "soft_purple", "sunrise",
    "warm_pink_dim", "white_breathe", "white_bright", "white_dim",
    "white_medium", "zoneb_both_pulse", "zoneb_orange_pulse",
    "zoneb_white_pulse",
]

CURRENT_LED = {"name": None}

# --- Themes ----------------------------------------------------------------
PALETTES = {
    "dark": {
        "bg": "#0f1116", "card": "#1a1d26", "field": "#262a36",
        "fg": "#e8eaf0", "dim": "#8b91a3", "border": "#2a3040",
        "accent": "#6bb6ff", "accent_hover": "#8cc8ff", "accent_fg": "#0b0d12",
        "btn": "#2a2f3d", "btn_hover": "#363c4e", "shadow": "#090a0e",
        "graph_bg": "#12141b", "grid": "#262a36", "grid_text": "#666c7e",
        "cpu": "#ff6b6b", "nvme": "#6bb6ff",
        "good": "#5ee08a", "warn": "#ffb454", "bad": "#ff5c5c",
    },
    "light": {
        "bg": "#e9edf4", "card": "#ffffff", "field": "#e6e9f0",
        "fg": "#1b1e27", "dim": "#6a7083", "border": "#d6dbe6",
        "accent": "#2b7de9", "accent_hover": "#4a93f2", "accent_fg": "#ffffff",
        "btn": "#e3e7f0", "btn_hover": "#d3d9e6", "shadow": "#c3c9d6",
        "graph_bg": "#f5f7fb", "grid": "#dde1ea", "grid_text": "#9096a8",
        "cpu": "#e5484d", "nvme": "#2b7de9",
        "good": "#1d9a50", "warn": "#d98200", "bad": "#d63a3a",
    },
}
OVERLAY_BG = "#0b0d12"
OVERLAY_DIM = "#8b91a3"

# --- Fonts -----------------------------------------------------------------
PREFERRED_FONTS = [
    "Inter", "Poppins", "Montserrat", "Ubuntu", "Roboto", "Fira Sans",
    "Noto Sans", "Cantarell", "JetBrains Mono", "Fira Code",
    "DejaVu Sans", "Liberation Sans",
]
SYSTEM_FONT = "System default"

# --- Overlay placement -----------------------------------------------------
CORNERS = [
    ("top-left", "↖  Top left"),
    ("top-right", "↗  Top right"),
    ("bottom-left", "↙  Bottom left"),
    ("bottom-right", "↘  Bottom right"),
]
EDGE_MARGIN = 20
BOTTOM_EXTRA = 44  # leave room for a taskbar/panel along the bottom

SS = 4  # supersampling factor for anti-aliased shapes


# --- Settings & system theme detection -------------------------------------
def load_settings():
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass  # settings are a nicety; never crash over them


def real_user_home():
    uid = os.environ.get("PKEXEC_UID") or os.environ.get("SUDO_UID")
    try:
        if uid:
            return pwd.getpwuid(int(uid)).pw_dir
    except Exception:
        pass
    return os.path.expanduser("~")


def detect_system_theme():
    """Best-effort: 'dark' or 'light' from the logged-in user's desktop settings."""
    home = real_user_home()

    # KDE Plasma: judge by the window background colour of the active scheme
    try:
        cp = configparser.RawConfigParser(strict=False)
        cp.optionxform = str
        cp.read(os.path.join(home, ".config", "kdeglobals"))
        rgb = cp.get("Colors:Window", "BackgroundNormal")
        r, g, b = [int(x) for x in rgb.split(",")[:3]]
        return "dark" if (0.299 * r + 0.587 * g + 0.114 * b) < 128 else "light"
    except Exception:
        pass

    # GTK
    for ver in ("gtk-4.0", "gtk-3.0"):
        try:
            cp = configparser.RawConfigParser(strict=False)
            cp.read(os.path.join(home, ".config", ver, "settings.ini"))
            if cp.get("Settings", "gtk-application-prefer-dark-theme", fallback="") == "1":
                return "dark"
            name = cp.get("Settings", "gtk-theme-name", fallback="")
            if name:
                return "dark" if "dark" in name.lower() else "light"
        except Exception:
            pass

    return "dark"


# --- Helpers ---------------------------------------------------------------
def temp_color(value, pal):
    """Green / amber / red depending on how hot it is."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return pal["dim"]
    if v < 65:
        return pal["good"]
    if v < 80:
        return pal["warn"]
    return pal["bad"]


def hex_rgba(h, alpha=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def rounded_image(w, h, boxes):
    """Anti-aliased rounded rectangles as a Tk image.
    boxes: list of (x1, y1, x2, y2, radius, '#hex') drawn back to front."""
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x1, y1, x2, y2, r, color in boxes:
        d.rounded_rectangle([x1 * SS, y1 * SS, x2 * SS - 1, y2 * SS - 1],
                            radius=r * SS, fill=hex_rgba(color))
    return ImageTk.PhotoImage(img.resize((w, h), RESAMPLE))


def poly_round(canvas, x1, y1, x2, y2, r, fill):
    """Fallback (no Pillow): rounded rectangle from a smoothed polygon."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    canvas.create_polygon(pts, smooth=True, fill=fill, outline="")


def make_app_icon():
    """64x64 anti-aliased window icon (gauge)."""
    size = 64
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=14 * SS, fill=hex_rgba("#1a1d26"))
    c = big // 2
    d.ellipse([c - 18 * SS, c - 18 * SS, c + 18 * SS, c + 18 * SS], outline=hex_rgba("#6bb6ff"), width=4 * SS)
    for dx, dy in [(0, -14), (12, 8), (-12, 8)]:
        d.line([(c, c), (c + dx * SS, c + dy * SS)], fill=hex_rgba("#ff6b6b"), width=4 * SS)
    d.ellipse([c - 4 * SS, c - 4 * SS, c + 4 * SS, c + 4 * SS], fill=hex_rgba("#ffffff"))
    return ImageTk.PhotoImage(img.resize((size, size), RESAMPLE))


def require_root():
    if os.geteuid() != 0:
        tmp = tk.Tk()
        tmp.withdraw()
        messagebox.showerror(
            "Needs root",
            "This app writes to /sys files that need root.\n\n"
            "Launch it from the app menu (PS5 Control Panel) or run:\n"
            "  sudo python3 ps5_control_gui.py",
        )
        raise SystemExit(1)


def write_sysfs(path, value):
    try:
        with open(path, "w") as f:
            f.write(str(value))
        return True
    except Exception as e:
        messagebox.showerror("Write failed", f"{path}\n\n{e}")
        return False


def run_cmd(args):
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        messagebox.showerror("Command failed", f"{' '.join(args)}\n\n{e.stderr}")
        return False
    except FileNotFoundError:
        messagebox.showerror(
            "Not found",
            f"'{args[0]}' isn't installed yet.\n\n"
            "Build it with:\n  cd ps5-linux-tools && sudo ./install.sh",
        )
        return False


def get_sensors_text():
    try:
        out = subprocess.run(["sensors"], capture_output=True, text=True, check=True)
        return out.stdout
    except Exception:
        return "sensors not available"


def parse_temps(text):
    cpu = re.search(r"Tctl:\s+\+([\d.]+)", text)
    nvme = re.search(r"Composite:\s+\+([\d.]+)", text)
    return (
        cpu.group(1) if cpu else "?",
        nvme.group(1) if nvme else "?",
    )


# --- Custom widgets --------------------------------------------------------
class RoundButton(tk.Canvas):
    """Rounded button with hover highlight, a soft shadow and a pressed-in effect."""

    RADIUS = 11

    def __init__(self, master, text, command, pal, family, accent=False, size=10):
        self.font = tkfont.Font(family=family, size=size, weight="bold")
        self.bw = self.font.measure(text) + 40
        self.bh = self.font.metrics("linespace") + 18
        super().__init__(master, width=self.bw, height=self.bh + 3, bg=pal["card"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text = text
        self.command = command
        self.pal = pal
        self.accent = accent
        self.hover = False
        self.pressed = False
        self.images = {}
        self.redraw()
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<ButtonRelease-1>", self.on_release)

    def colors(self):
        p = self.pal
        if self.accent:
            return p["accent"], p["accent_hover"], p["accent_fg"]
        return p["btn"], p["btn_hover"], p["fg"]

    def redraw(self):
        base, hov, fg = self.colors()
        fill = hov if self.hover else base
        dy = 2 if self.pressed else 0
        self.delete("all")
        if HAVE_PIL:
            key = (self.hover, self.pressed)
            if key not in self.images:
                boxes = []
                if not self.pressed:
                    boxes.append((0, 3, self.bw, self.bh + 3, self.RADIUS, self.pal["shadow"]))
                boxes.append((0, dy, self.bw, self.bh + dy, self.RADIUS, fill))
                self.images[key] = rounded_image(self.bw, self.bh + 3, boxes)
            self.create_image(0, 0, anchor="nw", image=self.images[key])
        else:
            if not self.pressed:
                poly_round(self, 1, 3, self.bw - 1, self.bh + 2, self.RADIUS, self.pal["shadow"])
            poly_round(self, 1, dy, self.bw - 1, self.bh + dy - 1, self.RADIUS, fill)
        self.create_text(self.bw // 2, self.bh // 2 + dy, text=self.text, fill=fg, font=self.font)

    def on_enter(self, _e):
        self.hover = True
        self.redraw()

    def on_leave(self, _e):
        self.hover = False
        self.pressed = False
        self.redraw()

    def on_press(self, _e):
        self.pressed = True
        self.redraw()

    def on_release(self, e):
        was_pressed = self.pressed
        self.pressed = False
        self.redraw()
        if was_pressed and 0 <= e.x <= self.bw and 0 <= e.y <= self.bh + 3:
            self.command()


class TabButton(tk.Canvas):
    """Pill-shaped tab: filled with the accent colour when selected, soft highlight on hover."""

    def __init__(self, master, text, command, pal, family, size=10):
        self.font = tkfont.Font(family=family, size=size, weight="bold")
        self.tw = self.font.measure(text) + 40
        self.th = self.font.metrics("linespace") + 16
        super().__init__(master, width=self.tw, height=self.th, bg=pal["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text = text
        self.command = command
        self.pal = pal
        self.selected = False
        self.hover = False
        self.images = {}
        self.redraw()
        self.bind("<Enter>", lambda _e: self.set_hover(True))
        self.bind("<Leave>", lambda _e: self.set_hover(False))
        self.bind("<ButtonRelease-1>", lambda _e: self.command())

    def set_hover(self, value):
        self.hover = value
        self.redraw()

    def set_selected(self, value):
        self.selected = value
        self.redraw()

    def redraw(self):
        p = self.pal
        self.delete("all")
        if self.selected:
            fill, fg = p["accent"], p["accent_fg"]
        elif self.hover:
            fill, fg = p["card"], p["fg"]
        else:
            fill, fg = None, p["dim"]
        if fill:
            r = self.th // 2
            if HAVE_PIL:
                if fill not in self.images:
                    self.images[fill] = rounded_image(self.tw, self.th, [(0, 0, self.tw, self.th, r, fill)])
                self.create_image(0, 0, anchor="nw", image=self.images[fill])
            else:
                poly_round(self, 1, 1, self.tw - 1, self.th - 1, r, fill)
        self.create_text(self.tw // 2, self.th // 2, text=self.text, fill=fg, font=self.font)


class Overlay(tk.Toplevel):
    """Small borderless always-on-top box showing live temperatures."""

    def __init__(self, master, family):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.configure(bg=OVERLAY_BG, highlightthickness=1, highlightbackground="#2f3547")
        try:
            self.attributes("-topmost", True)
            self.attributes("-alpha", 0.85)
        except tk.TclError:
            pass

        self.cpu_name = tk.Label(self, text="CPU", bg=OVERLAY_BG)
        self.cpu_name.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=(8, 0))
        self.cpu_val = tk.Label(self, text="?°C", fg=OVERLAY_DIM, bg=OVERLAY_BG, width=7, anchor="e")
        self.cpu_val.grid(row=0, column=1, padx=(0, 12), pady=(8, 0))
        self.nvme_name = tk.Label(self, text="NVMe", bg=OVERLAY_BG)
        self.nvme_name.grid(row=1, column=0, sticky="w", padx=(12, 8), pady=(0, 8))
        self.nvme_val = tk.Label(self, text="?°C", fg=OVERLAY_DIM, bg=OVERLAY_BG, width=7, anchor="e")
        self.nvme_val.grid(row=1, column=1, padx=(0, 12), pady=(0, 8))

        self.corner = "top-right"
        self.set_font(family)
        self.cpu_name.config(fg=PALETTES["dark"]["cpu"])
        self.nvme_name.config(fg=PALETTES["dark"]["nvme"])

    def set_font(self, family):
        for w in (self.cpu_name, self.nvme_name):
            w.config(font=(family, 10, "bold"))
        for w in (self.cpu_val, self.nvme_val):
            w.config(font=(family, 15, "bold"))

    def set_temps(self, cpu, nvme):
        dark = PALETTES["dark"]
        self.cpu_val.config(text=f"{cpu}°C", fg=temp_color(cpu, dark))
        self.nvme_val.config(text=f"{nvme}°C", fg=temp_color(nvme, dark))

    def move_to(self, corner):
        self.corner = corner
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = EDGE_MARGIN if "left" in corner else sw - w - EDGE_MARGIN
        y = EDGE_MARGIN if "top" in corner else sh - h - EDGE_MARGIN - BOTTOM_EXTRA
        self.geometry(f"+{x}+{y}")

    def show(self):
        self.move_to(self.corner)
        self.deiconify()
        self.lift()
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

    def hide(self):
        self.withdraw()


# --- Main window -----------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PS5 Control Panel")
        self.geometry("500x700")
        self.minsize(480, 660)

        if HAVE_PIL:
            try:
                self.app_icon = make_app_icon()
                self.iconphoto(True, self.app_icon)
            except Exception:
                pass

        self.cpu_history = deque(maxlen=60)   # ~3 minutes at 3s refresh
        self.nvme_history = deque(maxlen=60)
        self.graph_img = None

        self.default_family = tkfont.nametofont("TkDefaultFont").actual("family")
        available = set(tkfont.families())
        self.font_choices = [SYSTEM_FONT] + [f for f in PREFERRED_FONTS if f in available]

        saved = load_settings()
        self.theme_var = tk.StringVar(value=saved.get("theme", "dark"))
        default_font = self.font_choices[1] if len(self.font_choices) > 1 else SYSTEM_FONT
        font_name = saved.get("font", default_font)
        if font_name not in self.font_choices:
            font_name = default_font
        self.font_var = tk.StringVar(value=font_name)

        self.overlay_on = tk.BooleanVar(value=bool(saved.get("overlay_on", False)))
        corner = saved.get("corner", "top-right")
        self.corner_var = tk.StringVar(value=corner if corner in dict(CORNERS) else "top-right")
        try:
            alpha = int(saved.get("alpha", 85))
        except (TypeError, ValueError):
            alpha = 85
        self.alpha_var = tk.IntVar(value=min(max(alpha, 30), 100))
        self.target_var = tk.IntVar(value=self.read_current_target())
        self.led_var = tk.StringVar(value="off")

        self.container = None
        self.current_tab = 0
        self.tab_buttons = []
        self.tab_frames = []
        self.resolve_look()
        self.overlay = Overlay(self, self.family)
        self.overlay.corner = self.corner_var.get()
        self.on_alpha(None)

        self.build_ui()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if self.overlay_on.get():
            self.after(400, self.toggle_overlay)
        self.after(500, self.refresh_temps)

    # ---- look & feel ------------------------------------------------------
    def resolve_look(self):
        choice = self.theme_var.get()
        name = detect_system_theme() if choice == "system" else choice
        self.pal = PALETTES.get(name, PALETTES["dark"])
        font = self.font_var.get()
        self.family = self.default_family if font == SYSTEM_FONT else font
        for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            try:
                tkfont.nametofont(fname).configure(family=self.family)
            except tk.TclError:
                pass
        tkfont.nametofont("TkDefaultFont").configure(size=10)

    def f(self, size, bold=False):
        return (self.family, size, "bold") if bold else (self.family, size)

    def setup_style(self):
        p = self.pal
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=p["card"], foreground=p["fg"], fieldbackground=p["field"],
                    bordercolor=p["border"], lightcolor=p["card"], darkcolor=p["card"],
                    focuscolor=p["card"])
        s.configure("TFrame", background=p["card"])
        s.configure("Page.TFrame", background=p["bg"])
        s.configure("TLabel", background=p["card"], foreground=p["fg"])
        s.configure("Dim.TLabel", foreground=p["dim"])
        s.configure("Section.TLabel", foreground=p["accent"], font=self.f(9, True))
        s.configure("TRadiobutton", background=p["card"], foreground=p["fg"], indicatorcolor=p["field"])
        s.map("TRadiobutton", background=[("active", p["card"])], indicatorcolor=[("selected", p["accent"])])
        s.configure("TCheckbutton", background=p["card"], foreground=p["fg"], indicatorcolor=p["field"])
        s.map("TCheckbutton", background=[("active", p["card"])], indicatorcolor=[("selected", p["accent"])])
        s.configure("Horizontal.TScale", background=p["accent"], troughcolor=p["field"],
                    bordercolor=p["card"], lightcolor=p["accent"], darkcolor=p["accent"])
        s.map("Horizontal.TScale", background=[("active", p["accent_hover"])])
        s.configure("TCombobox", fieldbackground=p["field"], background=p["field"], foreground=p["fg"],
                    arrowcolor=p["fg"], selectbackground=p["field"], selectforeground=p["fg"],
                    padding=6)
        s.map("TCombobox", fieldbackground=[("readonly", p["field"])], foreground=[("readonly", p["fg"])])
        self.option_add("*TCombobox*Listbox.background", p["field"])
        self.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", p["accent_fg"])
        self.option_add("*TCombobox*Listbox.font", self.f(10))

    def btn(self, parent, text, command, accent=False):
        return RoundButton(parent, text, command, self.pal, self.family, accent=accent)

    def card(self, parent, title, pady=(0, 12)):
        """A bordered card with a small section title. Returns the frame to fill."""
        p = self.pal
        outer = tk.Frame(parent, bg=p["card"], highlightthickness=1,
                         highlightbackground=p["border"], highlightcolor=p["border"])
        outer.pack(fill="x", pady=pady)
        inner = ttk.Frame(outer, padding=(16, 12, 16, 14))
        inner.pack(fill="both", expand=True)
        ttk.Label(inner, text=title.upper(), style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        return inner

    # ---- (re)build the whole window --------------------------------------
    def build_ui(self):
        p = self.pal
        self.configure(bg=p["bg"])
        self.setup_style()
        self.container = tk.Frame(self, bg=p["bg"])
        self.container.pack(fill="both", expand=True)

        header = tk.Frame(self.container, bg=p["bg"])
        header.pack(fill="x", padx=20, pady=(18, 12))
        tk.Label(header, text="PS5", fg=p["accent"], bg=p["bg"], font=self.f(22, True)).pack(side="left")
        tk.Label(header, text="Control Panel", fg=p["fg"], bg=p["bg"], font=self.f(22)).pack(
            side="left", padx=(8, 0))

        bar = tk.Frame(self.container, bg=p["bg"])
        bar.pack(fill="x", padx=18, pady=(0, 12))
        content = tk.Frame(self.container, bg=p["bg"])
        content.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        self.tab_buttons = []
        self.tab_frames = []
        tabs = [("Monitor", self.build_monitor), ("Cooling", self.build_cooling),
                ("LED", self.build_led), ("Style", self.build_style)]
        for i, (title, builder) in enumerate(tabs):
            frame = ttk.Frame(content, style="Page.TFrame")
            builder(frame)
            self.tab_frames.append(frame)
            tb = TabButton(bar, title, lambda i=i: self.select_tab(i), p, self.family)
            tb.pack(side="left", padx=(0, 6))
            self.tab_buttons.append(tb)
        self.select_tab(self.current_tab)

        self.overlay.set_font(self.family)

    def select_tab(self, index):
        self.current_tab = index
        for frame in self.tab_frames:
            frame.pack_forget()
        self.tab_frames[index].pack(fill="both", expand=True)
        for j, tb in enumerate(self.tab_buttons):
            tb.set_selected(j == index)

    def rebuild(self):
        if self.container is not None:
            self.container.destroy()
        self.resolve_look()
        self.build_ui()

    # ---- tabs -------------------------------------------------------------
    def build_monitor(self, tab):
        p = self.pal
        temps = self.card(tab, "Temperatures")
        row = ttk.Frame(temps)
        row.pack(fill="x")
        self.cpu_big_label = self.temp_block(row, "CPU")
        self.nvme_big_label = self.temp_block(row, "NVMe")

        self.graph = tk.Canvas(temps, height=130, bg=p["graph_bg"], highlightthickness=0)
        self.graph.pack(fill="x", pady=(12, 0))
        self.graph.bind("<Configure>", lambda _e: self.draw_graph())

        ov = self.card(tab, "Screen overlay", pady=(0, 0))
        ttk.Checkbutton(ov, text="Show temperature overlay (always on top)",
                        variable=self.overlay_on, command=self.toggle_overlay).pack(anchor="w")

        ttk.Label(ov, text="Position", style="Dim.TLabel").pack(anchor="w", pady=(12, 2))
        grid = ttk.Frame(ov)
        grid.pack(fill="x")
        for i, (value, label) in enumerate(CORNERS):
            ttk.Radiobutton(grid, text=label, value=value, variable=self.corner_var,
                            command=self.on_corner_change).grid(
                row=i // 2, column=i % 2, sticky="w", padx=(0, 22), pady=3)

        ttk.Label(ov, text="Opacity", style="Dim.TLabel").pack(anchor="w", pady=(10, 2))
        scale = ttk.Scale(ov, from_=30, to=100, orient="horizontal", variable=self.alpha_var,
                          command=self.on_alpha)
        scale.pack(fill="x")
        scale.bind("<ButtonRelease-1>", lambda _e: self.persist())

    def temp_block(self, parent, name):
        col = ttk.Frame(parent)
        col.pack(side="left", expand=True)
        ttk.Label(col, text=name, style="Dim.TLabel").pack()
        value = ttk.Label(col, text="?°C", font=self.f(26, True))
        value.pack()
        return value

    def build_cooling(self, tab):
        p = self.pal
        fan = self.card(tab, "Fan thermal target")
        self.target_big_label = ttk.Label(fan, text=f"{self.target_var.get()}°C",
                                          font=self.f(30, True), foreground=p["accent"])
        self.target_big_label.pack()
        self.target_hint = ttk.Label(fan, text="Lower = fan works harder, sooner", style="Dim.TLabel")
        self.target_hint.pack(pady=(0, 8))
        scale = ttk.Scale(fan, from_=40, to=95, orient="horizontal",
                          variable=self.target_var, command=self.on_scale_move)
        scale.pack(fill="x", pady=4)
        range_row = ttk.Frame(fan)
        range_row.pack(fill="x")
        ttk.Label(range_row, text="40°C  max cooling", style="Dim.TLabel").pack(side="left")
        ttk.Label(range_row, text="min cooling  95°C", style="Dim.TLabel").pack(side="right")
        self.btn(fan, "Apply target", self.apply_target, accent=True).pack(pady=(14, 0))

        pc = self.card(tab, "ps5_control  (fixed fan patterns)", pady=(0, 0))
        row = ttk.Frame(pc)
        row.pack(pady=(0, 8))
        for col, (text, arg) in enumerate([("Fan On", "on"), ("Fan Off", "off"), ("Fan Max", "max")]):
            self.btn(row, text, lambda a=arg: run_cmd(["ps5_control", "--fan", a])).grid(
                row=0, column=col, padx=5)
        row2 = ttk.Frame(pc)
        row2.pack()
        for col, (text, arg) in enumerate([("Boost On", "on"), ("Boost Off", "off")]):
            self.btn(row2, text, lambda a=arg: run_cmd(["ps5_control", "--boost", a])).grid(
                row=0, column=col, padx=5)

    def build_led(self, tab):
        led = self.card(tab, "Front LED indicator", pady=(0, 0))
        ttk.Label(led, text="Pick a color or animation", style="Dim.TLabel").pack(anchor="w", pady=(0, 6))
        combo = ttk.Combobox(led, textvariable=self.led_var, values=LED_COLORS, state="readonly")
        combo.pack(fill="x")
        self.btn(led, "Set color", self.set_led, accent=True).pack(pady=(16, 0))

    def build_style(self, tab):
        theme = self.card(tab, "Theme")
        for value, label in [("dark", "Dark"), ("light", "Light"), ("system", "System  (follow my desktop)")]:
            ttk.Radiobutton(theme, text=label, value=value, variable=self.theme_var,
                            command=self.on_theme_change).pack(anchor="w", pady=3)

        font = self.card(tab, "Font", pady=(0, 0))
        combo = ttk.Combobox(font, textvariable=self.font_var, values=self.font_choices, state="readonly")
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", lambda _e: self.on_font_change())
        ttk.Label(font, text="The quick brown fox 0123456789 °C",
                  font=self.f(13, True)).pack(anchor="w", pady=(12, 6))
        ttk.Label(font, style="Dim.TLabel", wraplength=400, justify="left",
                  text="Only installed fonts are listed. To get more, install one, "
                       "e.g. sudo pacman -S inter-font, then reopen the app.").pack(anchor="w")

    # ---- style handlers ---------------------------------------------------
    def on_theme_change(self):
        self.persist()
        self.after(10, self.rebuild)

    def on_font_change(self):
        self.persist()
        self.after(10, self.rebuild)

    def persist(self):
        save_settings({
            "theme": self.theme_var.get(),
            "font": self.font_var.get(),
            "overlay_on": bool(self.overlay_on.get()),
            "corner": self.corner_var.get(),
            "alpha": int(self.alpha_var.get()),
        })

    # ---- overlay handlers -------------------------------------------------
    def toggle_overlay(self):
        if self.overlay_on.get():
            self.overlay.show()
        else:
            self.overlay.hide()
        self.persist()

    def on_corner_change(self):
        self.overlay.corner = self.corner_var.get()
        if self.overlay_on.get():
            self.overlay.show()
        self.persist()

    def on_alpha(self, _value):
        try:
            self.overlay.attributes("-alpha", float(self.alpha_var.get()) / 100.0)
        except tk.TclError:
            pass

    def on_close(self):
        self.persist()
        self.overlay.destroy()
        self.destroy()

    # ---- fan --------------------------------------------------------------
    def on_scale_move(self, _value):
        self.target_big_label.config(text=f"{int(float(self.target_var.get()))}°C")
        self.target_hint.config(text="Not applied yet - press Apply target", foreground=self.pal["warn"])

    def read_current_target(self):
        try:
            with open(FAN_TARGET_PATH) as f:
                return int(f.read().strip())
        except Exception:
            return 86

    def apply_target(self):
        val = int(self.target_var.get())
        if write_sysfs(FAN_TARGET_PATH, val):
            self.target_big_label.config(text=f"{val}°C")
            self.target_hint.config(text="Applied", foreground=self.pal["good"])

    # ---- temps ------------------------------------------------------------
    def refresh_temps(self):
        text = get_sensors_text()
        cpu, nvme = parse_temps(text)
        self.cpu_big_label.config(text=f"{cpu}°C", foreground=temp_color(cpu, self.pal))
        self.nvme_big_label.config(text=f"{nvme}°C", foreground=temp_color(nvme, self.pal))
        self.overlay.set_temps(cpu, nvme)
        try:
            self.cpu_history.append(float(cpu))
        except ValueError:
            pass
        try:
            self.nvme_history.append(float(nvme))
        except ValueError:
            pass
        self.draw_graph()
        self.after(3000, self.refresh_temps)

    def graph_points(self, history, w, h, pad):
        lo, hi = 20.0, 95.0
        vals = list(history)
        # light smoothing so the line isn't jagged
        sm = []
        for i in range(len(vals)):
            window = vals[max(0, i - 1):i + 2]
            sm.append(sum(window) / len(window))
        step = (w - 2 * pad) / max(1, (len(sm) - 1))
        pts = []
        for i, t in enumerate(sm):
            frac = min(max((t - lo) / (hi - lo), 0), 1)
            pts.append((pad + i * step, h - pad - frac * (h - 2 * pad)))
        return pts

    def draw_graph(self):
        p = self.pal
        c = self.graph
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 20 or h < 20:
            return
        pad = 8
        grid_rows = [(0.0, "95"), (0.5, "57"), (1.0, "20")]

        if HAVE_PIL:
            ss = 3
            img = Image.new("RGBA", (w * ss, h * ss), hex_rgba(p["graph_bg"]))
            d = ImageDraw.Draw(img)
            for frac, _label in grid_rows:
                y = (pad + frac * (h - 2 * pad)) * ss
                d.line([(pad * ss, y), ((w - pad) * ss, y)], fill=hex_rgba(p["grid"]), width=ss)
            for history, color in ((self.nvme_history, p["nvme"]), (self.cpu_history, p["cpu"])):
                if len(history) < 2:
                    continue
                pts = [(x * ss, y * ss) for x, y in self.graph_points(history, w, h, pad)]
                layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                ImageDraw.Draw(layer).polygon(
                    pts + [(pts[-1][0], (h - pad) * ss), (pts[0][0], (h - pad) * ss)],
                    fill=hex_rgba(color, 38))
                img.alpha_composite(layer)
                d = ImageDraw.Draw(img)
                d.line(pts, fill=hex_rgba(color), width=int(2.2 * ss), joint="curve")
                x, y = pts[-1]
                r = 3.5 * ss
                d.ellipse([x - r, y - r, x + r, y + r], fill=hex_rgba(color))
            self.graph_img = ImageTk.PhotoImage(img.resize((w, h), RESAMPLE))
            c.create_image(0, 0, anchor="nw", image=self.graph_img)
        else:
            for frac, _label in grid_rows:
                y = pad + frac * (h - 2 * pad)
                c.create_line(pad, y, w - pad, y, fill=p["grid"])
            for history, color in ((self.nvme_history, p["nvme"]), (self.cpu_history, p["cpu"])):
                if len(history) >= 2:
                    flat = [v for xy in self.graph_points(history, w, h, pad) for v in xy]
                    c.create_line(*flat, fill=color, width=2, smooth=True)

        for frac, label in grid_rows:
            y = pad + frac * (h - 2 * pad)
            c.create_text(w - pad - 2, y - 7, text=label, fill=p["grid_text"], anchor="e", font=self.f(7))
        c.create_oval(pad + 2, pad + 3, pad + 10, pad + 11, fill=p["cpu"], outline="")
        c.create_text(pad + 16, pad + 7, text="CPU", fill=p["fg"], anchor="w", font=self.f(8, True))
        c.create_oval(pad + 52, pad + 3, pad + 60, pad + 11, fill=p["nvme"], outline="")
        c.create_text(pad + 66, pad + 7, text="NVMe", fill=p["fg"], anchor="w", font=self.f(8, True))

    # ---- LED --------------------------------------------------------------
    def set_led(self):
        new_name = self.led_var.get()
        old_name = CURRENT_LED["name"]
        if old_name and old_name != "off":
            write_sysfs(f"{LED_DIR}/ps5:{old_name}:indicator/brightness", 0)
        if new_name != "off":
            if write_sysfs(f"{LED_DIR}/ps5:{new_name}:indicator/brightness", 1):
                CURRENT_LED["name"] = new_name
        else:
            CURRENT_LED["name"] = None


if __name__ == "__main__":
    require_root()
    App().mainloop()
