import csv, math, os, random, re, sys, unicodedata, tkinter as tk
from tkinter import ttk

# Pillow is optional: with it, photos can be PNG/JPG/WEBP and are resized nicely.
# Without it, only PNG/GIF photos work.   Install with:  pip install pillow
try:
    from PIL import Image, ImageOps, ImageTk
    RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ----------------------------------------------------------------------------- look & feel
THEME = "hawaii"        # "hawaii" or "classic": change this one word to switch the look
THEMES = {
    "hawaii": dict(
        DARK="#062B3A", PANEL="#0C4257",                  # deep lagoon night / cards
        ACCENT="#FF8A3D", ACCENT_HOVER="#E0701F", ON_ACCENT="#04202B",   # sunset orange buttons
        TEXT="#FFF6E5", MUTED="#9FD0D6", DIM="#6FA3AC",   # sand white / misty teal
        BTN2="#15667F", BTN2_HOVER="#1E8099",             # secondary (ocean) buttons
        TROUGH="#0A3547", THUMB_IDLE="#2E7F93",           # scrollbars
        PHOTO_BG="#082F3F", PHOTO_TXT="#6FA3AC",
        RES_TA="#3EE8D2", RES_N="#FF6B9D", RES_GR="#FFC857", WARN="#FFD166"),   # lagoon / hibiscus / sun
    "classic": dict(
        DARK="#121212", PANEL="#1E1E1E",
        ACCENT="#FFCC00", ACCENT_HOVER="#CCA300", ON_ACCENT="#000000",
        TEXT="#FFFFFF", MUTED="#AAAAAA", DIM="#888888",
        BTN2="#2A2A2A", BTN2_HOVER="#444444",
        TROUGH="#2A2A2A", THUMB_IDLE="#444444",
        PHOTO_BG="#151515", PHOTO_TXT="#555555",
        RES_TA="#00E5FF", RES_N="#FF3366", RES_GR="#FFCC00", WARN="#FFAA33"),
}
_P = THEMES.get(THEME, THEMES["hawaii"])
DARK, PANEL = _P["DARK"], _P["PANEL"]
ACCENT, ACCENT_HOVER, ON_ACCENT = _P["ACCENT"], _P["ACCENT_HOVER"], _P["ON_ACCENT"]
TEXT, MUTED, DIM = _P["TEXT"], _P["MUTED"], _P["DIM"]
BTN2, BTN2_HOVER, TROUGH, THUMB_IDLE = _P["BTN2"], _P["BTN2_HOVER"], _P["TROUGH"], _P["THUMB_IDLE"]
PHOTO_BG, PHOTO_TXT = _P["PHOTO_BG"], _P["PHOTO_TXT"]
RES_TA, RES_N, RES_GR, WARN = _P["RES_TA"], _P["RES_N"], _P["RES_GR"], _P["WARN"]
HAWAII = (THEME == "hawaii")
APP_TITLE = "🌺  THE CREW MOTORFEST  ·  ULTIMATE RANDOMIZER  🌴" if HAWAII else "🏎️ THE CREW MOTORFEST ULTIMATE DASHBOARD"
GREETING = "Aloha! 🌺" if HAWAII else "Welcome!"

# The app always works inside its own folder (CSV files, brands.csv, images/), wherever it is launched from,
# whether it runs as this script (.pyw, no console window) or as a built .exe.
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
try:
    os.chdir(BASE_DIR)
except OSError:
    pass
IMAGES_DIR = os.path.join(BASE_DIR, "images")   # put vehicle photos here
IMG_W, IMG_H = 160, 90                          # photo size in the result panels
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

# Display order of the categories (same as in the game).
# Categories not listed here are placed at the end, alphabetically.
CATEGORY_ORDER = [
    "street tier 1", "street tier 2", "drift", "cup car", "racing", "dragster",
    "hypercar", "alpha gp", "motocross", "rally raid", "demolition", "rally",
    "monster", "powerboat", "plane", "helicopter", "jet",
]

# Categories that are NOT available in Grand Race (hidden from the Grand Race selection menus).
GRAND_RACE_EXCLUDED = {"cup car", "dragster", "demolition", "powerboat", "plane", "helicopter"}
ALL_BRANDS, ALL_COUNTRIES, ALL_PLAYLISTS = "All brands", "All countries", "All playlists"

class DarkScrollbar(tk.Canvas):
    """Always-visible vertical scrollbar in the app's dark/yellow style."""
    def __init__(self, parent, command, **kw):
        super().__init__(parent, width=12, bg=TROUGH, highlightthickness=0, bd=0, **kw)
        self.command = command
        self.first, self.last = 0.0, 1.0
        self.drag_offset = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag_offset", None))

    def set(self, first, last):          # called by the scrolled widget
        self.first, self.last = float(first), float(last)
        self.redraw()

    def thumb_bounds(self):
        h = max(self.winfo_height(), 1)
        y0 = self.first * h
        y1 = max(self.last * h, y0 + 24)   # minimum thumb size
        return h, y0, min(y1, h)

    def redraw(self):
        self.delete("all")
        h, y0, y1 = self.thumb_bounds()
        scrollable = (self.last - self.first) < 0.999
        self.create_rectangle(1, y0, 11, y1, fill=ACCENT if scrollable else THUMB_IDLE, outline="")

    def on_press(self, e):
        h, y0, y1 = self.thumb_bounds()
        if y0 <= e.y <= y1:
            self.drag_offset = e.y - y0
        else:                              # click in the trough: jump there
            self.drag_offset = (y1 - y0) / 2
            self.command("moveto", max(0.0, (e.y - self.drag_offset) / h))

    def on_drag(self, e):
        if self.drag_offset is not None:
            h = max(self.winfo_height(), 1)
            self.command("moveto", max(0.0, (e.y - self.drag_offset) / h))

class UltimateMotorfestRandomizer:
    def __init__(self, root):
        self.root = root
        self.root.title("The Crew Motorfest Ultimate Randomizer Pro" + self.version_suffix())
        self.root.geometry("950x700")
        self.root.configure(bg=DARK)
        self.vehicles, self.races, self.all_categories, self.category_vars = [], [], [], {}
        self.image_index, self.image_cache = {}, {}
        self.wheel_targets = []                       # (area, canvas) pairs scrolled by the mouse wheel
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(ev, self.on_wheel)
        self.TMAP = {
            "asphalt": ["street tier 1", "street tier 2", "drift", "racing", "dragster", "hypercar", "alpha gp", "cup car"],
            "off-road": ["motocross", "rally raid", "demolition", "rally", "monster", "demolition derby", "monster truck"],
            "sea": ["powerboat"], "air": ["plane", "helicopter", "jet"]
        }
        self.load_all_data()
        self.build_image_index()
        self.create_layout()

    @staticmethod
    def version_suffix():
        """' - data v23' in the window title when the remote updater has installed a version (see updater.py)."""
        try:
            import json
            with open(os.path.join(BASE_DIR, "update_state.json"), encoding="utf-8") as f:
                v = json.load(f).get("version")
            return f"  -  update v{v}" if v else ""
        except Exception:
            return ""

    # ---------------------------------------------------------------- data
    def load_all_data(self):
        for p, lst in [("vehicles.csv", self.vehicles), ("races.csv", self.races)]:
            if os.path.exists(p):
                with open(p, mode="r", encoding="utf-8", errors="replace") as f:
                    r = csv.DictReader(f)
                    if r.fieldnames:
                        r.fieldnames = [n.strip() for n in r.fieldnames if n]
                        lst.extend(list(r))
        # brands.csv: which brand and country each vehicle belongs to (matched on the start of the vehicle name)
        self.brand_rules, self.country_order, self.brand_cache = [], [], {}
        if os.path.exists("brands.csv"):
            with open("brands.csv", mode="r", encoding="utf-8-sig", errors="replace", newline="") as f:
                for row in csv.DictReader(f):
                    row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                    prefix = self.plain_name(row.get("Name Starts With", ""))
                    if row.get("Country") and row.get("Brand") and prefix:
                        self.brand_rules.append((prefix, row["Brand"], row["Country"]))
                        if row["Country"] not in self.country_order:      # keep the file's order (= flag order)
                            self.country_order.append(row["Country"])
        # playlists.csv: the in-game playlist(s) each race belongs to (columns: Playlist, Race Name)
        self.race_playlists, self.playlist_order = {}, []
        if os.path.exists("playlists.csv"):
            with open("playlists.csv", mode="r", encoding="utf-8-sig", errors="replace", newline="") as f:
                for row in csv.DictReader(f):
                    row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                    pl, race = row.get("Playlist", ""), row.get("Race Name", "")
                    if pl and race:
                        names = self.race_playlists.setdefault(race.lower(), [])
                        if pl not in names:
                            names.append(pl)
                        if pl not in self.playlist_order:          # keep the file's order
                            self.playlist_order.append(pl)
        # race_rules.csv: which categories (or specific vehicles) are allowed on each phase of each race
        self.race_rules, raw_rules = {}, {}
        if os.path.exists("race_rules.csv"):
            with open("race_rules.csv", mode="r", encoding="utf-8-sig", errors="replace", newline="") as f:
                for row in csv.DictReader(f):
                    row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                    name, cat = row.get("Race Name", ""), row.get("Category", "")
                    try:
                        phase = int(row.get("Phase") or 1)
                    except ValueError:
                        continue
                    if name and cat:
                        only = row.get("Only", "").lower() in ("yes", "y", "true", "1", "x")
                        raw_rules.setdefault((name.lower(), phase), []).append((self.plain_name(cat), self.plain_name(row.get("Vehicle Name", "")), only))
        for key, rows in raw_rules.items():          # per phase: {"only": bool, "cats": whole categories, "veh": (category, vehicle) pairs}
            only = any(o for _, _, o in rows)
            use = [x for x in rows if x[2]] if only else rows
            self.race_rules[key] = {"only": only, "cats": {c for c, v, _ in use if not v}, "veh": {(c, v) for c, v, _ in use if v}}
        # Merge spellings that only differ by letter case: keep the one with the most capitals
        # (e.g. 'Rally raid' and 'Rally Raid' -> 'Rally Raid').
        variants = {}
        for v in self.vehicles:
            c = (v.get("Category") or "").strip()
            if c:
                variants.setdefault(c.lower(), set()).add(c)
        canon = {k: max(s, key=lambda x: (sum(ch.isupper() for ch in x), x)) for k, s in variants.items()}
        for v in self.vehicles:
            c = (v.get("Category") or "").strip()
            if c:
                v["Category"] = canon[c.lower()]
        cats = set(canon.values())
        self.all_categories = sorted(cats, key=self.category_sort_key) if cats else ["Street Racing", "Hypercar"]

    @staticmethod
    def category_sort_key(name):
        """Sort by game order; ignores case and accents (e.g. 'Helicopter' variants match 'helicopter')."""
        plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()
        idx = CATEGORY_ORDER.index(plain) if plain in CATEGORY_ORDER else len(CATEGORY_ORDER)
        return (idx, plain, name)

    @staticmethod
    def plain_name(name):
        """Lower-case, accent-free version of a category name."""
        return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()

    def vehicle_brand_country(self, vehicle_name):
        """(brand, country) of a vehicle: the longest matching 'Name Starts With' rule wins."""
        key = self.plain_name(vehicle_name or "")
        if key not in self.brand_cache:
            best = None
            for prefix, brand, country in self.brand_rules:
                if (key == prefix or key.startswith(prefix + " ")) and (best is None or len(prefix) > best[0]):
                    best = (len(prefix), brand, country)
            self.brand_cache[key] = (best[1], best[2]) if best else ("", "")
        return self.brand_cache[key]

    def brands_for_country(self, country=""):
        """Brands in alphabetical order (only those of `country` if one is given)."""
        return sorted({b for _, b, c in self.brand_rules if not country or c == country}, key=str.lower)

    def on_gr_country_change(self, _event=None):
        country = self.gr_country.get()
        brands = [ALL_BRANDS] + self.brands_for_country("" if country == ALL_COUNTRIES else country)
        self.gr_brand.configure(values=brands)
        if self.gr_brand.get() not in brands:
            self.gr_brand.set(ALL_BRANDS)

    def grand_race_categories(self):
        return [c for c in self.all_categories if self.plain_name(c) not in GRAND_RACE_EXCLUDED]

    def get_allowed_terrains(self):
        ac = [c.lower() for c, var in self.category_vars.items() if var.get()]
        if not ac: return list(self.TMAP.keys())
        return [t for t, cats in self.TMAP.items() if any(c in ac for c in cats)]

    def get_filtered_vehicles(self, forced_cat=None):
        if forced_cat:
            return [v for v in self.vehicles if v.get("Category", "").strip().lower() == forced_cat.strip().lower()]
        allowed = [c for c, var in self.category_vars.items() if var.get()]
        return [v for v in self.vehicles if v.get("Category", "").strip() in allowed] if allowed else self.vehicles

    # -------------------------------------------------------------- photos
    @staticmethod
    def photo_key(name):
        """Normalize a vehicle name / file name so they can be matched
        (ignores case, extra spaces and characters Windows forbids in file names)."""
        cleaned = re.sub(r'[\\/:*?"<>|]', "", name)
        return " ".join(cleaned.split()).lower()

    def build_image_index(self):
        """Scan the 'images' folder (created if missing). File name = vehicle name, e.g.
        images/Abarth 500 (2008).jpg
        For a vehicle listed in several categories, add ' - Category' to get a different photo
        per category, e.g. images/Abarth 500 (2008) - Monster.png"""
        os.makedirs(IMAGES_DIR, exist_ok=True)
        for fn in os.listdir(IMAGES_DIR):
            stem, ext = os.path.splitext(fn)
            if ext.lower() in IMAGE_EXTS:
                self.image_index[self.photo_key(stem)] = os.path.join(IMAGES_DIR, fn)

    def find_photo_path(self, vehicle_name, category=None):
        """Look for 'Name - Category' first, then for 'Name' alone."""
        if category:
            path = self.image_index.get(self.photo_key(f"{vehicle_name} - {category}"))
            if path:
                return path
        return self.image_index.get(self.photo_key(vehicle_name))

    def load_vehicle_photo(self, vehicle_name, category=None):
        path = self.find_photo_path(vehicle_name, category)
        if not path:
            return None
        if path in self.image_cache:
            return self.image_cache[path]
        photo = None
        try:
            if PIL_OK:
                img = Image.open(path).convert("RGB")
                img = ImageOps.fit(img, (IMG_W, IMG_H), RESAMPLE)   # fills the whole box (centered crop)
                photo = ImageTk.PhotoImage(img)
            else:
                photo = tk.PhotoImage(file=path)
                f = max(1, -(-photo.width() // IMG_W), -(-photo.height() // IMG_H))
                if f > 1:
                    photo = photo.subsample(f)
        except Exception:
            photo = None
        self.image_cache[path] = photo   # keeps a reference so Tk does not discard the image
        return photo

    def make_photo_box(self, parent, vehicle_name, category=None):
        box = tk.Canvas(parent, width=IMG_W, height=IMG_H, bg=PHOTO_BG, highlightthickness=0, bd=0)
        photo = self.load_vehicle_photo(vehicle_name, category)
        if photo:
            box.create_image(IMG_W // 2, IMG_H // 2, image=photo)
        else:
            box.create_text(IMG_W // 2, IMG_H // 2, text="NO PHOTO", fill=PHOTO_TXT, font=("Arial", 9, "bold"))
        return box

    # ------------------------------------------------------------- filters
    def enable_wheel_scroll(self, area, canvas):
        """Mouse wheel scrolls `canvas` while the pointer is over `area` (several areas can coexist)."""
        self.wheel_targets.append((area, canvas))

    def on_wheel(self, e):
        try:
            w = self.root.winfo_containing(e.x_root, e.y_root)
        except KeyError:
            return
        while w is not None:
            for area, canvas in self.wheel_targets:
                if w == area:
                    if canvas.yview() != (0.0, 1.0):
                        up = e.num == 4 or getattr(e, "delta", 0) > 0
                        canvas.yview_scroll(-2 if up else 2, "units")
                    return
            w = w.master

    def make_scroll_list(self, parent):
        """Scrollable column (dark scrollbar + mouse wheel). Returns (inner frame to fill, canvas)."""
        canvas = tk.Canvas(parent, bg=PANEL, highlightthickness=0, width=300, yscrollincrement=20)
        sb = DarkScrollbar(parent, command=canvas.yview)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=5)    # packed BEFORE the canvas: always visible
        inner = tk.Frame(canvas, bg=PANEL)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        self.enable_wheel_scroll(parent, canvas)
        return inner, canvas

    def set_all_filters(self, value):
        for var in self.category_vars.values():
            var.set(value)

    def make_filter_row(self, parent, cat):
        """Filter row: empty square = unchecked, fully yellow square = checked."""
        var = tk.BooleanVar(value=True)
        self.category_vars[cat] = var

        row = tk.Frame(parent, bg=PANEL, cursor="hand2")
        row.pack(anchor="w", fill="x", padx=10, pady=3)

        box = tk.Canvas(row, width=18, height=18, bg=PANEL, highlightthickness=0, cursor="hand2")
        box.pack(side="left")
        label = tk.Label(row, text=cat, bg=PANEL, fg=TEXT, font=("Arial", 9), cursor="hand2")
        label.pack(side="left", padx=(8, 0))

        def redraw(*_):
            box.delete("all")
            box.create_rectangle(2, 2, 16, 16, outline=ACCENT, width=2, fill=ACCENT if var.get() else "")
            label.config(fg=TEXT if var.get() else DIM)

        def toggle(_event=None):
            var.set(not var.get())

        var.trace_add("write", redraw)
        for w in (row, box, label):
            w.bind("<Button-1>", toggle)
        redraw()

    # ------------------------------------------------------ result display
    def make_display_panel(self, parent):
        panel = tk.Frame(parent, bg=PANEL, bd=2, relief="solid", highlightbackground=ACCENT)
        panel.pack(fill="both", expand=True)
        return panel

    def fresh_inner(self, panel):
        """Empty the panel and return a new frame centered inside it."""
        for w in panel.winfo_children():
            w.destroy()
        inner = tk.Frame(panel, bg=PANEL)
        inner.place(relx=0.5, rely=0.5, anchor="center")
        return inner

    def show_message(self, panel, text, wrap=520):
        inner = self.fresh_inner(panel)
        tk.Label(inner, text=text, fg=TEXT, bg=PANEL, font=("Arial", 11, "italic"), justify="center", wraplength=wrap).pack()

    def show_result(self, panel, title, track, entries, color):
        """entries = list of dicts with 'stage', 'name', 'category'. Photo on the left, text on the right."""
        inner = self.fresh_inner(panel)
        tk.Label(inner, text=title, fg=color, bg=PANEL, font=("Arial", 13, "bold")).pack()
        if track:
            tk.Label(inner, text=track, fg=color, bg=PANEL, font=("Arial", 12, "bold")).pack(pady=(2, 0))
        tk.Frame(inner, height=2, bg=color).pack(fill="x", pady=8)
        for e in entries:
            row = tk.Frame(inner, bg=PANEL)
            row.pack(fill="x", pady=5)
            self.make_photo_box(row, e["name"], e.get("category")).pack(side="left")
            info = tk.Frame(row, bg=PANEL)
            info.pack(side="left", padx=(14, 0))
            tk.Label(info, text=e["stage"], fg=color, bg=PANEL, font=("Arial", 10, "bold")).pack(anchor="w")
            tk.Label(info, text=e["name"], fg=TEXT, bg=PANEL, font=("Arial", 13, "bold"), wraplength=380, justify="left").pack(anchor="w")
            if e.get("category"):
                tk.Label(info, text=e["category"], fg=MUTED, bg=PANEL, font=("Arial", 10)).pack(anchor="w")

    # -------------------------------------------------------------- layout
    def create_layout(self):
        self.apply_ttk_theme()
        if HAWAII:
            self.banner = tk.Canvas(self.root, height=80, bg=DARK, highlightthickness=0, bd=0)
            self.banner.pack(fill="x")
            self.banner.bind("<Configure>", self.draw_banner)
        else:
            ttk.Label(self.root, text=APP_TITLE, font=("Arial", 16, "bold"), foreground=ACCENT, background=DARK).pack(pady=(10, 5))

        # Big tab bar spanning the full width: each tab takes half of the bar
        tab_bar = tk.Frame(self.root, bg=DARK)
        tab_bar.pack(fill="x", padx=15, pady=(5, 8))
        container = tk.Frame(self.root, bg=DARK)
        container.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.tabs, self.tab_buttons = {}, {}
        for name in ("Time Attack", "Grand Race", "Tournament Mode"):
            self.tabs[name] = tk.Frame(container, bg=DARK)
            btn = tk.Button(tab_bar, text=name, font=("Arial", 15, "bold"), bd=0, relief="flat", cursor="hand2",
                            command=lambda n=name: self.show_tab(n))
            btn.pack(side="left", expand=True, fill="x", padx=3, ipady=12)
            self.tab_buttons[name] = btn

        self.build_time_attack_tab(self.tabs["Time Attack"])
        self.build_grand_race_tab(self.tabs["Grand Race"])
        self.build_tournament_tab(self.tabs["Tournament Mode"])
        self.show_tab("Time Attack")
        # "Update" button, top right: checks the update server now (see updater.py / update_config.json)
        self.update_btn = tk.Button(self.root, text="\u27f3 Update", font=("Arial", 9, "bold"), fg=ON_ACCENT, bg=ACCENT,
                                    activebackground=ACCENT_HOVER, activeforeground=ON_ACCENT, bd=0, cursor="hand2",
                                    command=self.check_for_updates)
        self.update_btn.place(relx=1.0, x=-12, y=10, anchor="ne")
        self.update_btn.lift()

    def check_for_updates(self):
        try:
            if BASE_DIR not in sys.path:
                sys.path.insert(0, BASE_DIR)
            import updater
            updater.check_now(self.root, BASE_DIR)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Update", f"The updater could not start:\n{e}", parent=self.root)

    def apply_ttk_theme(self):
        """Dropdown menus (ttk) in the app's colours."""
        try:
            style = ttk.Style()
            style.theme_use("clam")
            style.configure("TCombobox", fieldbackground=BTN2, background=BTN2_HOVER, foreground=TEXT, arrowcolor=TEXT,
                            bordercolor=BTN2_HOVER, lightcolor=BTN2, darkcolor=BTN2, selectbackground=BTN2, selectforeground=TEXT)
            style.map("TCombobox",
                      fieldbackground=[("readonly", BTN2), ("disabled", TROUGH)],
                      foreground=[("readonly", TEXT), ("disabled", DIM)],
                      selectbackground=[("readonly", BTN2)], selectforeground=[("readonly", TEXT)],
                      background=[("active", BTN2_HOVER), ("readonly", BTN2)],
                      arrowcolor=[("disabled", DIM)])
            self.root.option_add("*TCombobox*Listbox.background", PANEL)
            self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
            self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
            self.root.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)
        except Exception:
            pass

    @staticmethod
    def sunset_color(t):
        """Colour at position t (0..1) of the sunset gradient: orange -> hibiscus pink -> purple."""
        stops = [(255, 138, 61), (255, 107, 157), (140, 92, 214)]
        pos = min(max(t, 0.0), 1.0) * (len(stops) - 1)
        i = min(int(pos), len(stops) - 2)
        f = pos - i
        r, g, b = (round(stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f) for k in range(3))
        return f"#{r:02X}{g:02X}{b:02X}"

    def draw_banner(self, _event=None):
        """Sunset gradient with two waves along the bottom edge, and the app title."""
        c = self.banner
        c.delete("all")
        w, h = max(c.winfo_width(), 2), int(c.cget("height"))
        step = 3
        for x in range(0, w, step):
            c.create_rectangle(x, 0, x + step, h, fill=self.sunset_color(x / max(w - 1, 1)), outline="")
        for amp, shift, base, color in ((6, 0.0, 22, BTN2), (5, 1.9, 12, DARK)):
            pts = [0, h]
            for x in range(0, w + 8, 8):
                pts += [x, h - base + amp * math.sin(x / 40.0 + shift)]
            pts += [w, h]
            c.create_polygon(pts, fill=color, outline="")
        c.create_text(w // 2 + 2, h // 2 - 8 + 2, text=APP_TITLE, fill="#3A1A4A", font=("Arial", 18, "bold"))
        c.create_text(w // 2, h // 2 - 8, text=APP_TITLE, fill=TEXT, font=("Arial", 18, "bold"))

    def show_tab(self, name):
        """Show one tab's content and highlight its button (yellow = active)."""
        for n, frame in self.tabs.items():
            if n == name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        for n, btn in self.tab_buttons.items():
            active = (n == name)
            btn.config(bg=ACCENT if active else PANEL, fg=ON_ACCENT if active else TEXT,
                       activebackground=ACCENT_HOVER if active else BTN2,
                       activeforeground=ON_ACCENT if active else TEXT)

    def build_time_attack_tab(self, tab):
        # Bottom buttons are packed first so they always stay visible
        dock = tk.Frame(tab, bg=DARK)
        dock.pack(fill="x", side="bottom", pady=(10, 5), padx=5)
        modes = [("Time Attack", self.execute_time_attack), ("1-Phase Race", lambda: self.execute_multi_phase(1)),
                 ("2-Phase Race", lambda: self.execute_multi_phase(2)), ("3-Phase Race", lambda: self.execute_multi_phase(3))]
        for txt, cmd in modes:
            tk.Button(dock, text=txt, font=("Arial", 10, "bold"), fg=ON_ACCENT, bg=ACCENT, activebackground=ACCENT_HOVER, activeforeground=ON_ACCENT, command=cmd).pack(side="left", expand=True, fill="both", padx=4, ipady=6)

        workspace = tk.Frame(tab, bg=DARK)
        workspace.pack(fill="both", expand=True, padx=5, pady=(10, 0))

        left = tk.Frame(workspace, bg=PANEL, bd=1, relief="solid", width=250)
        left.pack(side="left", fill="both", padx=(0, 10))
        left.pack_propagate(False)
        tk.Label(left, text=" VEHICLE FILTERS", fg=ACCENT, bg=PANEL, font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        # Select all / Deselect all buttons (always visible, above the scrolling list)
        btns = tk.Frame(left, bg=PANEL)
        btns.pack(fill="x", padx=10, pady=(0, 5))
        tk.Button(btns, text="Select all", font=("Arial", 9, "bold"), fg=ON_ACCENT, bg=ACCENT, activebackground=ACCENT_HOVER, activeforeground=ON_ACCENT, bd=0,
                  command=lambda: self.set_all_filters(True)).pack(side="left", expand=True, fill="x", padx=(0, 3), ipady=2)
        tk.Button(btns, text="Deselect all", font=("Arial", 9, "bold"), fg=ON_ACCENT, bg=ACCENT, activebackground=ACCENT_HOVER, activeforeground=ON_ACCENT, bd=0,
                  command=lambda: self.set_all_filters(False)).pack(side="left", expand=True, fill="x", padx=(3, 0), ipady=2)

        canvas = tk.Canvas(left, bg=PANEL, highlightthickness=0, yscrollincrement=20)
        sb = DarkScrollbar(left, command=canvas.yview)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=5)    # packed BEFORE the canvas: always visible
        sf = tk.Frame(canvas, bg=PANEL)
        win = canvas.create_window((0, 0), window=sf, anchor="nw")
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        self.enable_wheel_scroll(left, canvas)

        for cat in self.all_categories:
            self.make_filter_row(sf, cat)

        right = tk.Frame(workspace, bg=DARK)
        right.pack(side="right", fill="both", expand=True)
        pbar = tk.Frame(right, bg=PANEL, bd=1, relief="solid")
        pbar.pack(fill="x", pady=(0, 8))
        tk.Label(pbar, text="Playlist:", fg=ACCENT, bg=PANEL, font=("Arial", 11, "bold")).pack(side="left", padx=(10, 4), pady=8)
        self.ta_playlist = self.make_playlist_combo(pbar, 40)
        self.ta_playlist.pack(side="left", padx=(0, 10), pady=5)
        if not self.playlist_order:
            tk.Label(pbar, text="(playlists.csv not found)", fg=MUTED, bg=PANEL, font=("Arial", 9, "italic")).pack(side="left")
        self.ta_panel = self.make_display_panel(right)
        self.show_message(self.ta_panel, f"{GREETING} Pick a mode below to generate your challenge.")

    def build_grand_race_tab(self, tab):
        dock = tk.Frame(tab, bg=DARK)
        dock.pack(fill="x", side="bottom", pady=(10, 5), padx=5)
        tk.Button(dock, text="🏆 Generate Grand Race Build", font=("Arial", 10, "bold"), fg=ON_ACCENT, bg=ACCENT, activebackground=ACCENT_HOVER, activeforeground=ON_ACCENT,
                  command=self.execute_grand_race).pack(side="left", expand=True, fill="both", padx=4, ipady=6)

        gr = tk.Frame(tab, bg=PANEL, bd=1, relief="solid")
        gr.pack(fill="x", padx=5, pady=(10, 4))
        tk.Label(gr, text="Grand Race Lineup Selection:", fg=ACCENT, bg=PANEL, font=("Arial", 11, "bold")).pack(side="left", padx=10, pady=8)

        gr_cats = self.grand_race_categories()
        self.gr_combo1 = ttk.Combobox(gr, values=gr_cats, width=13, state="readonly")
        self.gr_combo2 = ttk.Combobox(gr, values=gr_cats, width=13, state="readonly")
        self.gr_combo3 = ttk.Combobox(gr, values=gr_cats, width=13, state="readonly")
        self.gr_combo1.pack(side="left", padx=5, pady=5)
        self.gr_combo2.pack(side="left", padx=5, pady=5)
        self.gr_combo3.pack(side="left", padx=5, pady=5)

        if gr_cats:
            self.gr_combo1.set(gr_cats[0])
            self.gr_combo2.set(gr_cats[1 if len(gr_cats) > 1 else 0])
            self.gr_combo3.set(gr_cats[2 if len(gr_cats) > 2 else 0])

        # Optional filters applied to the three sectors: brand (A-Z) and country (same order as the in-game flags)
        gf = tk.Frame(tab, bg=PANEL, bd=1, relief="solid")
        gf.pack(fill="x", padx=5, pady=(0, 10))
        tk.Label(gf, text="Brand:", fg=ACCENT, bg=PANEL, font=("Arial", 11, "bold")).pack(side="left", padx=(10, 4), pady=8)
        self.gr_brand = ttk.Combobox(gf, values=[ALL_BRANDS] + self.brands_for_country(), width=24, state="readonly" if self.brand_rules else "disabled")
        self.gr_brand.pack(side="left", padx=(0, 14), pady=5)
        self.gr_brand.set(ALL_BRANDS)
        tk.Label(gf, text="Country:", fg=ACCENT, bg=PANEL, font=("Arial", 11, "bold")).pack(side="left", padx=(0, 4), pady=8)
        self.gr_country = ttk.Combobox(gf, values=[ALL_COUNTRIES] + self.country_order, width=22, state="readonly" if self.brand_rules else "disabled")
        self.gr_country.pack(side="left", padx=(0, 10), pady=5)
        self.gr_country.set(ALL_COUNTRIES)
        self.gr_country.bind("<<ComboboxSelected>>", self.on_gr_country_change)
        if not self.brand_rules:
            tk.Label(gf, text="(brands.csv not found)", fg=MUTED, bg=PANEL, font=("Arial", 9, "italic")).pack(side="left")

        holder = tk.Frame(tab, bg=DARK)
        holder.pack(fill="both", expand=True, padx=5)
        self.gr_panel = self.make_display_panel(holder)
        self.show_message(self.gr_panel, "Pick one category per sector above (and optionally a brand and/or a country), then press the button to generate your Grand Race lineup.", wrap=700)

    # ------------------------------------------------------- tournament mode
    @staticmethod
    def read_count(var, default=5):
        try:
            n = int(str(var.get()).strip())
        except ValueError:
            n = default
        return max(1, min(n, 99))

    @staticmethod
    def race_key(race):
        return (race.get("Race Name") or "").strip().lower()

    @staticmethod
    def vehicle_key(veh):
        return ((veh.get("Vehicle Name") or "").strip().lower(), (veh.get("Category") or "").strip().lower())

    def playlists_of(self, race):
        return self.race_playlists.get(self.race_key(race), [])

    def playlist_text(self, race):
        return " · ".join(self.playlists_of(race))

    def in_playlist(self, race, playlist):
        return not playlist or playlist in self.playlists_of(race)

    @staticmethod
    def selected_playlist(combo):
        value = combo.get()
        return "" if value == ALL_PLAYLISTS else value

    def make_playlist_combo(self, parent, width):
        combo = ttk.Combobox(parent, values=[ALL_PLAYLISTS] + self.playlist_order, width=width,
                             state="readonly" if self.playlist_order else "disabled")
        combo.set(ALL_PLAYLISTS)
        return combo

    def terrain_for_category(self, category):
        """Terrain of a vehicle category (asphalt / off-road / sea / air), or None if unknown."""
        plain = self.plain_name(category or "")
        for terrain, cats in self.TMAP.items():
            if plain in cats:
                return terrain
        return None

    def single_phase_races(self, terrain=None):
        """Races with exactly one terrain (multi-phase races are left out), without duplicates.
        If `terrain` is given, only races on that terrain are kept."""
        pool, seen = [], set()
        for r in self.races:
            terrains = [t.strip().lower() for t in (r.get("Terrain") or "").split("/") if t.strip()]
            key = self.race_key(r)
            if len(terrains) == 1 and key and key not in seen and (terrain is None or terrains[0] == terrain):
                seen.add(key)
                pool.append(r)
        return pool

    def default_categories(self, terrain):
        """Categories every phase of that terrain accepts by default (Dragster only exists on its own races)."""
        return [c for c in self.TMAP.get(terrain, []) if c != "dragster"]

    def races_for_category(self, category):
        """Single-phase races on which the WHOLE category is allowed (tournament mode).
        A race accepts its terrain's categories plus whatever race_rules.csv adds;
        rows flagged Only=yes mean the race accepts nothing but the listed rows."""
        plain = self.plain_name(category or "")
        pool = []
        for r in self.single_phase_races():
            race_terrain = (r.get("Terrain") or "").strip().lower()
            rule = self.race_rules.get((self.race_key(r), 1))
            if rule and rule["only"]:
                ok = plain in rule["cats"]
            else:
                ok = plain in self.default_categories(race_terrain) or bool(rule and plain in rule["cats"])
            if ok:
                pool.append(r)
        return pool

    def category_vehicles(self, category):
        pool, seen = [], set()
        for v in self.vehicles:
            if (v.get("Category") or "").strip().lower() == (category or "").strip().lower():
                key = self.vehicle_key(v)
                if key[0] and key not in seen:
                    seen.add(key)
                    pool.append(v)
        return pool

    def reroll_selected(self, items, sel, pool, key):
        """Replace the ticked items (in place) by new ones from `pool`, never creating duplicates.
        Returns None if nothing is ticked, else (number changed, True if the pool ran short)."""
        idxs = [i for i, s in enumerate(sel) if s.get()]
        if not idxs:
            return None
        shown = {key(x) for x in items}
        kept = {key(items[i]) for i in range(len(items)) if i not in idxs}
        fresh = [x for x in pool if key(x) not in shown]                     # never shown before
        again = [x for x in pool if key(x) in shown and key(x) not in kept]  # last resort: the ones being replaced
        random.shuffle(fresh)
        random.shuffle(again)
        candidates = fresh + again
        changed = 0
        for i in idxs:
            if not candidates:
                break
            items[i] = candidates.pop(0)
            changed += 1
        for s in sel:
            s.set(False)
        return changed, len(fresh) < len(idxs)

    def build_tournament_tab(self, tab):
        self.tour_races, self.tour_race_sel = [], []
        self.tour_vehicles, self.tour_veh_sel = [], []
        self.tour_status = tk.StringVar(value="")

        # Bottom buttons are packed first so they always stay visible
        dock = tk.Frame(tab, bg=DARK)
        dock.pack(fill="x", side="bottom", pady=(10, 5), padx=5)
        for txt, cmd in [("🎲 Roll Races", self.tour_roll_races), ("🔁 Reroll Selected Races", self.tour_reroll_races),
                         ("🎲 Roll Vehicles", self.tour_roll_vehicles), ("🔁 Reroll Selected Vehicles", self.tour_reroll_vehicles)]:
            tk.Button(dock, text=txt, font=("Arial", 10, "bold"), fg=ON_ACCENT, bg=ACCENT, activebackground=ACCENT_HOVER, activeforeground=ON_ACCENT,
                      command=cmd).pack(side="left", expand=True, fill="both", padx=4, ipady=6)

        # Settings: how many races / vehicles, and which vehicle category
        bar = tk.Frame(tab, bg=PANEL, bd=1, relief="solid")
        bar.pack(fill="x", padx=5, pady=(10, 4))
        self.tour_race_n, self.tour_veh_n = tk.StringVar(value="5"), tk.StringVar(value="5")

        def label(text):
            tk.Label(bar, text=text, fg=ACCENT, bg=PANEL, font=("Arial", 11, "bold")).pack(side="left", padx=(12, 4), pady=8)

        def spin(var):
            tk.Spinbox(bar, from_=1, to=99, width=4, textvariable=var, justify="center", font=("Arial", 11, "bold"),
                       bg=BTN2, fg=TEXT, insertbackground=ACCENT, buttonbackground=BTN2_HOVER, relief="flat").pack(side="left", padx=(0, 8))

        label("Races:")
        spin(self.tour_race_n)
        label("Vehicles:")
        spin(self.tour_veh_n)
        label("Vehicle category:")
        self.tour_cat = ttk.Combobox(bar, values=self.all_categories, width=16, state="readonly")
        self.tour_cat.pack(side="left", padx=(0, 10), pady=5)
        if self.all_categories:
            self.tour_cat.set(self.all_categories[0])

        bar2 = tk.Frame(tab, bg=PANEL, bd=1, relief="solid")
        bar2.pack(fill="x", padx=5, pady=(0, 4))
        tk.Label(bar2, text="Playlist (races):", fg=ACCENT, bg=PANEL, font=("Arial", 11, "bold")).pack(side="left", padx=(12, 4), pady=8)
        self.tour_playlist = self.make_playlist_combo(bar2, 44)
        self.tour_playlist.pack(side="left", padx=(0, 10), pady=5)
        if not self.playlist_order:
            tk.Label(bar2, text="(playlists.csv not found)", fg=MUTED, bg=PANEL, font=("Arial", 9, "italic")).pack(side="left")

        tk.Label(tab, textvariable=self.tour_status, fg=WARN, bg=DARK, font=("Arial", 10, "italic"),
                 anchor="w", height=1).pack(fill="x", padx=10)

        # Two scrollable columns: races on the left, vehicles on the right
        cols = tk.Frame(tab, bg=DARK)
        cols.pack(fill="both", expand=True, padx=5, pady=(2, 0))
        cols.columnconfigure(0, weight=1, uniform="tour")
        cols.columnconfigure(1, weight=1, uniform="tour")
        cols.rowconfigure(0, weight=1)
        self.tour_race_title, self.tour_race_inner, self.tour_race_canvas = self.build_tournament_column(cols, 0, "🏁 RACES", "race")
        self.tour_veh_title, self.tour_veh_inner, self.tour_veh_canvas = self.build_tournament_column(cols, 1, "🚗 VEHICLES", "veh")
        self.render_tour_races()
        self.render_tour_vehicles()

    def build_tournament_column(self, parent, col, title, kind):
        frame = tk.Frame(parent, bg=PANEL, bd=2, relief="solid")
        frame.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0))
        head = tk.Frame(frame, bg=PANEL)
        head.pack(fill="x", padx=10, pady=(8, 4))
        title_lbl = tk.Label(head, text=title, fg=ACCENT, bg=PANEL, font=("Arial", 12, "bold"))
        title_lbl.pack(side="left")
        for txt, val in (("Select none", False), ("Select all", True)):
            tk.Button(head, text=txt, font=("Arial", 8, "bold"), fg=TEXT, bg=BTN2, activebackground=BTN2_HOVER,
                      activeforeground=TEXT, bd=0, cursor="hand2",
                      command=lambda v=val: self.tour_select(kind, v)).pack(side="right", padx=(4, 0), ipadx=4, ipady=1)
        body = tk.Frame(frame, bg=PANEL)
        body.pack(fill="both", expand=True)
        inner, canvas = self.make_scroll_list(body)
        return title_lbl, inner, canvas

    def render_tournament_list(self, inner, canvas, items, sel, build_row, empty_text, keep_scroll=False):
        """Redraw one column. Click a row (or its square) to tick it for a reroll."""
        pos = canvas.yview()[0] if keep_scroll else 0.0
        for w in inner.winfo_children():
            w.destroy()
        if not items:
            tk.Label(inner, text=empty_text, fg=MUTED, bg=PANEL, font=("Arial", 11, "italic"),
                     justify="center", wraplength=300).pack(padx=10, pady=40)
        for i, item in enumerate(items):
            row = tk.Frame(inner, bg=PANEL, cursor="hand2")
            row.pack(fill="x", padx=8, pady=4)
            box = tk.Canvas(row, width=18, height=18, bg=PANEL, highlightthickness=0, cursor="hand2")
            box.pack(side="left", padx=(0, 8))
            clickable = [row, box] + build_row(row, i, item)

            def redraw(var=sel[i], box=box):
                box.delete("all")
                box.create_rectangle(2, 2, 16, 16, outline=ACCENT, width=2, fill=ACCENT if var.get() else "")

            def toggle(_e=None, var=sel[i], redraw=redraw):
                var.set(not var.get())
                redraw()

            redraw()
            for w in clickable:
                w.bind("<Button-1>", toggle)
        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.yview_moveto(pos)

    def render_tour_races(self, keep_scroll=False):
        def build_row(row, i, race):
            num = tk.Label(row, text=f"{i + 1:02d}", fg=ACCENT, bg=PANEL, font=("Arial", 14, "bold"), width=3, cursor="hand2")
            num.pack(side="left")
            info = tk.Frame(row, bg=PANEL, cursor="hand2")
            info.pack(side="left", fill="x", expand=True)
            l1 = tk.Label(info, text=(race.get("Race Name") or "").strip(), fg=TEXT, bg=PANEL, font=("Arial", 12, "bold"),
                          wraplength=240, justify="left", cursor="hand2")
            l1.pack(anchor="w")
            l2 = tk.Label(info, text=self.playlist_text(race) or "—", fg=MUTED, bg=PANEL, font=("Arial", 10), cursor="hand2")
            l2.pack(anchor="w")
            return [num, info, l1, l2]

        self.tour_race_title.config(text=f"🏁 RACES ({len(self.tour_races)})")
        self.render_tournament_list(self.tour_race_inner, self.tour_race_canvas, self.tour_races, self.tour_race_sel, build_row,
                                    "No races yet.\nSet the quantity above and press “Roll Races”.", keep_scroll)

    def render_tour_vehicles(self, keep_scroll=False):
        def build_row(row, i, veh):
            name, cat = (veh.get("Vehicle Name") or "").strip(), (veh.get("Category") or "").strip()
            photo = self.make_photo_box(row, name, cat)
            photo.pack(side="left")
            info = tk.Frame(row, bg=PANEL, cursor="hand2")
            info.pack(side="left", padx=(10, 0), fill="x", expand=True)
            l1 = tk.Label(info, text=name, fg=TEXT, bg=PANEL, font=("Arial", 12, "bold"), wraplength=190, justify="left", cursor="hand2")
            l1.pack(anchor="w")
            l2 = tk.Label(info, text=cat, fg=MUTED, bg=PANEL, font=("Arial", 10), cursor="hand2")
            l2.pack(anchor="w")
            return [photo, info, l1, l2]

        self.tour_veh_title.config(text=f"🚗 VEHICLES ({len(self.tour_vehicles)})")
        self.render_tournament_list(self.tour_veh_inner, self.tour_veh_canvas, self.tour_vehicles, self.tour_veh_sel, build_row,
                                    "No vehicles yet.\nPick a category and a quantity above, then press “Roll Vehicles”.", keep_scroll)

    def tour_select(self, kind, value):
        if kind == "race":
            for s in self.tour_race_sel:
                s.set(value)
            self.render_tour_races(keep_scroll=True)
        else:
            for s in self.tour_veh_sel:
                s.set(value)
            self.render_tour_vehicles(keep_scroll=True)

    def tour_roll_races(self):
        # Races match the requested vehicle category: e.g. Hypercar -> asphalt, Rally Raid -> off-road
        cat = self.tour_cat.get()
        playlist = self.selected_playlist(self.tour_playlist)
        label = f"single-phase races for {cat}" + (f" in “{playlist}”" if playlist else "")
        pool = [r for r in self.races_for_category(cat) if self.in_playlist(r, playlist)]
        if not pool:
            self.tour_status.set(f"❌ No {label} found in races.csv.")
            return
        n = self.read_count(self.tour_race_n)
        self.tour_races = random.sample(pool, min(n, len(pool)))
        self.tour_race_sel = [tk.BooleanVar(value=False) for _ in self.tour_races]
        self.tour_status.set(f"Only {len(pool)} {label} exist: showing all of them." if n > len(pool) else "")
        self.render_tour_races()

    def tour_reroll_races(self):
        if not self.tour_races:
            self.tour_status.set("Roll some races first.")
            return
        playlist = self.selected_playlist(self.tour_playlist)
        pool = [r for r in self.races_for_category(self.tour_cat.get()) if self.in_playlist(r, playlist)]
        res = self.reroll_selected(self.tour_races, self.tour_race_sel, pool, self.race_key)
        if res is None:
            self.tour_status.set("Tick at least one race (click it) to reroll it.")
            return
        self.tour_status.set("Not enough other races left: some may come back." if res[1] else "")
        self.render_tour_races(keep_scroll=True)

    def tour_roll_vehicles(self):
        cat = self.tour_cat.get()
        pool = self.category_vehicles(cat)
        if not pool:
            self.tour_status.set(f"❌ No vehicles found in category “{cat}”.")
            return
        n = self.read_count(self.tour_veh_n)
        self.tour_vehicles = random.sample(pool, min(n, len(pool)))
        self.tour_veh_sel = [tk.BooleanVar(value=False) for _ in self.tour_vehicles]
        self.tour_status.set(f"Only {len(pool)} vehicles in {cat}: showing all of them." if n > len(pool) else "")
        self.render_tour_vehicles()

    def tour_reroll_vehicles(self):
        if not self.tour_vehicles:
            self.tour_status.set("Roll some vehicles first.")
            return
        cat = self.tour_cat.get()
        res = self.reroll_selected(self.tour_vehicles, self.tour_veh_sel, self.category_vehicles(cat), self.vehicle_key)
        if res is None:
            self.tour_status.set("Tick at least one vehicle (click it) to reroll it.")
            return
        self.tour_status.set(f"Not enough other vehicles left in {cat}: some may come back." if res[1] else "")
        self.render_tour_vehicles(keep_scroll=True)

    # ------------------------------------------------------------ generators
    def phase_candidates(self, race, idx, sector, pool):
        """Vehicles allowed on phase `idx` (1-based) of `race`, among `pool` = [(vehicle, plain category, plain name)].
        A phase accepts its terrain's categories plus the rows race_rules.csv adds (blank Vehicle Name = whole category).
        Rows flagged Only=yes mean the phase accepts nothing but those rows."""
        rule = self.race_rules.get((self.race_key(race), idx))
        if rule and rule["only"]:
            return [v for v, cat, name in pool if cat in rule["cats"] or (cat, name) in rule["veh"]]
        base = self.default_categories(sector)
        if rule:
            return [v for v, cat, name in pool if cat in base or cat in rule["cats"] or (cat, name) in rule["veh"]]
        return [v for v, cat, name in pool if cat in base]

    def eligible_races(self, phase_count=None, playlist=""):
        """(race, phases, candidates per phase) for every race that can be raced with the checked vehicle categories."""
        pool = [(v, self.plain_name(v.get("Category", "")), self.plain_name(v.get("Vehicle Name", ""))) for v in self.get_filtered_vehicles()]
        out = []
        for r in self.races:
            phases = [t.strip().lower() for t in (r.get("Terrain") or "").split("/") if t.strip()]
            if not phases or (phase_count and len(phases) != phase_count) or not self.in_playlist(r, playlist):
                continue
            cands = [self.phase_candidates(r, i, s, pool) for i, s in enumerate(phases, start=1)]
            if all(cands):
                out.append((r, phases, cands))
        return out

    def track_text(self, race):
        text = f"🏁 TRACK: {race.get('Race Name','').strip()}"
        playlist = self.playlist_text(race)
        return text + (f"\n🎵 PLAYLIST: {playlist}" if playlist else "")

    def build_entries(self, phases, cands):
        entries = []
        for idx in range(1, len(phases) + 1):
            veh = random.choice(cands[idx - 1])
            stage = f"STAGE {idx}" if len(phases) > 1 else "VEHICLE"
            entries.append({"stage": stage, "name": veh.get("Vehicle Name", "").strip(), "category": veh.get("Category", "").strip()})
        return entries

    def execute_time_attack(self):
        if not self.vehicles or not self.races: return
        playlist = self.selected_playlist(self.ta_playlist)
        fr = self.eligible_races(playlist=playlist)
        if not fr:
            self.show_message(self.ta_panel, "❌ Error: no race " + (f"of “{playlist}” " if playlist else "") + "can be raced with the checked vehicle filters!")
            return
        race, phases, cands = random.choice(fr)
        track = self.track_text(race)
        self.show_result(self.ta_panel, "⏱️ TIME ATTACK SOLO CHALLENGE ⏱️", track, self.build_entries(phases, cands), RES_TA)

    def execute_multi_phase(self, ph_count):
        if not self.vehicles or not self.races: return
        playlist = self.selected_playlist(self.ta_playlist)
        vr = self.eligible_races(ph_count, playlist)
        if not vr:
            self.show_message(self.ta_panel, f"❌ No {ph_count}-phase race " + (f"of “{playlist}” " if playlist else "") + "fits your checked vehicle filters!")
            return
        sel_race, r_phases, cands = random.choice(vr)
        track = self.track_text(sel_race)
        self.show_result(self.ta_panel, f"⚡ {ph_count}-PHASE CHALLENGE SELECTION ⚡", track, self.build_entries(r_phases, cands), RES_N)

    def execute_grand_race(self):
        chosen = [self.gr_combo1.get(), self.gr_combo2.get(), self.gr_combo3.get()]
        brand = "" if self.gr_brand.get() == ALL_BRANDS else self.gr_brand.get()
        country = "" if self.gr_country.get() == ALL_COUNTRIES else self.gr_country.get()
        entries = []
        for pos, chosen_class in enumerate(chosen, start=1):
            pool = self.get_filtered_vehicles(forced_cat=chosen_class)
            if brand or country:
                pool = [v for v in pool
                        if (not brand or self.vehicle_brand_country(v.get("Vehicle Name", ""))[0] == brand)
                        and (not country or self.vehicle_brand_country(v.get("Vehicle Name", ""))[1] == country)]
            v_name = random.choice(pool).get("Vehicle Name", "").strip() if pool else "No vehicles found for this filter!"
            entries.append({"stage": f"SECTOR {pos}", "name": v_name, "category": chosen_class})
        self.show_result(self.gr_panel, "🏆 OFFICIAL GRAND RACE ROUTE BLUEPRINT SET 🏆", None, entries, RES_GR)

if __name__ == "__main__":
    try:    # Windows: own taskbar icon instead of the Python one
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TCM.UltimateRandomizer")
    except Exception:
        pass
    app_root = tk.Tk()
    icon_path = os.path.join(BASE_DIR, "app_icon.ico")
    if os.path.exists(icon_path):
        try:
            app_root.iconbitmap(icon_path)
        except tk.TclError:
            pass
    app = UltimateMotorfestRandomizer(app_root)
    app_root.mainloop()
