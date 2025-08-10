import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from threading import Thread
import traceback

# --- allow running this file directly or as an installed package ---
if __package__ in (None, ""):
    import sys, pathlib
    sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))  # .../media-tool/src
    from mediatool.image.pipelines.convert_webp import convert_folder_to_webp
    from mediatool.image.pipelines.blur_master import run_blur_master, WATERMARK_SETS
    from mediatool.image.pipelines.dedupe import copy_images_and_deduplicate
    from mediatool.image.pipelines.blur_script_interactive import blur_folder
    from mediatool.video.pipelines.transcode_ffmpeg import transcode_h264
    from mediatool.video.pipelines.extract_frames import extract_frames
else:
    from ..image.pipelines.convert_webp import convert_folder_to_webp
    from ..image.pipelines.blur_master import run_blur_master, WATERMARK_SETS
    from ..image.pipelines.dedupe import copy_images_and_deduplicate
    from ..image.pipelines.blur_script_interactive import blur_folder
    from ..video.pipelines.transcode_ffmpeg import transcode_h264
    from ..video.pipelines.extract_frames import extract_frames

# High-DPI on Windows
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# =============== Watermark settings dialog =================
class WatermarkSettingsDialog(tk.Toplevel):
    """Dialog to edit WATERMARK_SETS and global WM params."""
    def __init__(self, master, current_sets: dict, max_w, max_h, quality, opacity, on_save):
        super().__init__(master)
        self.title("WaterMark Path Setting")
        self.transient(master)
        self.grab_set()
        self.resizable(True, True)

        self._on_save = on_save
        self.rows = []  # list of (name_var, port_var, land_var)
        self.columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        frm = ttk.Frame(self, padding=16)
        frm.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(3, weight=1)

        ttk.Label(frm, text="WATERMARK_SETS", font=("Segoe UI Semibold", 12))\
            .grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 8))

        ttk.Label(frm, text="Name").grid(row=1, column=0, sticky="w", padx=(0, 6))
        ttk.Label(frm, text="Portrait path").grid(row=1, column=1, sticky="w", padx=(0, 6))
        ttk.Label(frm, text="Landscape path").grid(row=1, column=3, sticky="w", padx=(0, 6))

        r = 2
        for name, paths in current_sets.items():
            self._add_row(frm, r, name, paths.get("port", ""), paths.get("land", ""))
            r += 1

        ttk.Button(frm, text="Add New Set", style="Material.Outlined.TButton",
                   command=lambda: self._add_row(frm, len(self.rows)+2, "Enter Name", "", ""))\
            .grid(row=r, column=0, pady=(10, 0), sticky="w")

        r += 1
        ttk.Separator(frm).grid(row=r, column=0, columnspan=5, sticky="ew", pady=12)
        r += 1

        self.max_w = tk.IntVar(value=max_w)
        self.max_h = tk.IntVar(value=max_h)
        self.quality = tk.IntVar(value=quality)
        self.opacity = tk.DoubleVar(value=opacity)

        ttk.Label(frm, text="MAX_WIDTH").grid(row=r, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.max_w).grid(row=r, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(frm, text="MAX_HEIGHT").grid(row=r, column=2, sticky="w")
        ttk.Entry(frm, textvariable=self.max_h).grid(row=r, column=3, sticky="ew")
        r += 1
        ttk.Label(frm, text="IMG_QUALITY").grid(row=r, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.quality).grid(row=r, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(frm, text="WM_OPACITY").grid(row=r, column=2, sticky="w")
        ttk.Entry(frm, textvariable=self.opacity).grid(row=r, column=3, sticky="ew")
        r += 1

        ttk.Button(frm, text="Save", style="Material.TButton", command=self._save)\
            .grid(row=r, column=0, pady=(12, 0), sticky="w")

    def _add_row(self, parent, grid_row, name, port, land):
        name_var = tk.StringVar(value=name)
        port_var = tk.StringVar(value=port)
        land_var = tk.StringVar(value=land)

        idx = len(self.rows) + 2
        ttk.Entry(parent, textvariable=name_var).grid(row=idx, column=0, sticky="ew", padx=(0, 6))
        ttk.Entry(parent, textvariable=port_var).grid(row=idx, column=1, sticky="ew")
        ttk.Button(parent, text="Browse…",
                   command=lambda v=port_var: self._browse(v)).grid(row=idx, column=2, padx=6)
        ttk.Entry(parent, textvariable=land_var).grid(row=idx, column=3, sticky="ew")
        ttk.Button(parent, text="Browse…",
                   command=lambda v=land_var: self._browse(v)).grid(row=idx, column=4, padx=6)

        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(3, weight=1)
        self.rows.append((name_var, port_var, land_var))

    def _browse(self, var: tk.StringVar):
        p = filedialog.askopenfilename(
            title="Choose image",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tiff")]
        )
        if p:
            var.set(p)

    def _save(self):
        out = {}
        for name_var, port_var, land_var in self.rows:
            n = name_var.get().strip()
            p = port_var.get().strip()
            l = land_var.get().strip()
            if n and p and l:
                out[n] = {"port": p, "land": l}
        self._on_save(out, self.max_w.get(), self.max_h.get(), self.quality.get(),
                      float(self.opacity.get()))
        self.destroy()


# ================================ APP ================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Media Tool")
        self.geometry("1280x820")
        self.minsize(1024, 1024)

        # init state BEFORE building UI (used during panel build)
        self.watermark_sets = dict(WATERMARK_SETS)
        self.max_width = tk.IntVar(value=4000)
        self.max_height = tk.IntVar(value=4000)
        self.img_quality = tk.IntVar(value=80)
        self.wm_opacity = tk.DoubleVar(value=0.7)

        self._init_style()
        self._build_header()
        self._build_tabs()
        self._bind_shortcuts()

    # ---------- Theming ----------
    def _init_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")   # allows recoloring entries etc.
        except tk.TclError:
            pass

        self.COLORS = {
            "bg":        "#17121f",
            "surface":   "#1E1E1E",
            "field":     "#24202e",
            "onSurface": "#ffffff",
            "muted":     "#A7B0BC",
            "outline":   "#2A2F36",
            "primary":   "#9451be",
            "primary_d": "#9B66DC",
            "primary_l": "#CF9CFF",
            "accent":    "#03DAC6",
        }
        c = self.COLORS

        self.configure(bg=c["bg"])
        style.configure(".", background=c["bg"], foreground=c["onSurface"], font=("Segoe UI", 12))
        style.configure("TSeparator", background=c["outline"])

        # Tabs
        style.configure("TNotebook", background=c["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(28, 12), font=("Segoe UI", 11, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", c["surface"])],
                  foreground=[("selected", c["onSurface"]), ("!selected", c["muted"])])

        # Labels / cards
        style.configure("Header.TLabel", font=("Segoe UI Semibold", 18), background=c["bg"])
        style.configure("Card.TFrame", background=c["surface"])
        style.configure("Card.TLabel", background=c["surface"], foreground=c["onSurface"])

        # Radios
        style.configure("Segment.TRadiobutton",
                        padding=(18, 10),
                        background=c["bg"], foreground=c["muted"],
                        borderwidth=1, relief="flat")
        style.map("Segment.TRadiobutton",
                  background=[("selected", c["primary"]), ("active", c["surface"])],
                  foreground=[("selected", "#000000"), ("!selected", c["muted"])])

        # Fields
        style.configure("TEntry",
                        fieldbackground=c["field"], background=c["field"],
                        foreground=c["onSurface"], insertcolor=c["onSurface"])
        style.map("TEntry",
                  fieldbackground=[("readonly", c["field"]), ("disabled", "#202020")],
                  foreground=[("disabled", "#7a7a7a")])

        style.configure("TSpinbox",
                        fieldbackground=c["field"], background=c["field"],
                        foreground=c["onSurface"], insertcolor=c["onSurface"])
        style.map("TSpinbox",
                  fieldbackground=[("readonly", c["field"]), ("disabled", "#202020")],
                  foreground=[("disabled", "#7a7a7a")])

        style.configure("TCombobox",
                        fieldbackground=c["field"], background=c["field"],
                        foreground=c["onSurface"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", c["field"]), ("disabled", "#202020")],
                  foreground=[("disabled", "#7a7a7a")])

        # Bars
        style.configure("TScale", background=c["surface"], troughcolor=c["outline"])
        style.configure("Accent.Horizontal.TProgressbar",
                        troughcolor=c["surface"], background=c["accent"],
                        bordercolor=c["surface"], lightcolor=c["accent"], darkcolor=c["accent"])

        # Buttons
        style.configure("Material.TButton",
                        background=c["primary"], foreground="#000000",
                        padding=(18, 12), borderwidth=0,
                        focusthickness=3, focuscolor=c["primary_l"])
        style.map("Material.TButton",
                  background=[("active", c["primary_l"]), ("pressed", c["primary_d"]), ("disabled", "#3a3a3a")],
                  foreground=[("disabled", "#7a7a7a")])

        style.configure("Material.Outlined.TButton",
                        background=c["surface"], foreground=c["onSurface"],
                        padding=(18, 12), bordercolor=c["primary"], borderwidth=2,
                        focusthickness=3, focuscolor=c["accent"])
        style.map("Material.Outlined.TButton",
                  background=[("active", "#23262d"), ("pressed", "#20232a")],
                  foreground=[("disabled", "#7a7a7a")])

    # ---------- Layout ----------
    def _build_header(self):
        head = ttk.Frame(self, padding=(20, 16))
        head.pack(side="top", fill="x")

        ttk.Label(head, text="Workspace", style="Header.TLabel").pack(side="left")

        self.segment_var = tk.StringVar(value="IMAGE")
        seg = ttk.Frame(head)
        seg.pack(side="right")

        ttk.Radiobutton(seg, text="IMAGE", value="IMAGE",
                        variable=self.segment_var, style="Segment.TRadiobutton",
                        command=self._on_switch).grid(row=0, column=0, sticky="nsew")
        ttk.Separator(seg, orient="vertical").grid(row=0, column=1, sticky="ns", padx=1)
        ttk.Radiobutton(seg, text="VIDEO", value="VIDEO",
                        variable=self.segment_var, style="Segment.TRadiobutton",
                        command=self._on_switch).grid(row=0, column=2, sticky="nsew")

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # IMAGE
        t1 = ttk.Frame(self.nb, style="Card.TFrame", padding=24)
        self.nb.add(t1, text="IMAGE")
        self._image_tab(t1)

        # VIDEO
        t2 = ttk.Frame(self.nb, style="Card.TFrame", padding=24)
        self.nb.add(t2, text="VIDEO")
        self._video_tab(t2)

        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _image_tab(self, parent):
        ttk.Label(parent, text="Image tools", style="Card.TLabel",
                  font=("Segoe UI Semibold", 14)).grid(row=0, column=0, sticky="w")
        ttk.Separator(parent).grid(row=1, column=0, columnspan=8, sticky="ew", pady=12)

        # top buttons
        btns = ttk.Frame(parent, style="Card.TFrame")
        btns.grid(row=2, column=0, sticky="w", pady=8)

        ttk.Button(btns, text="Convert to WEBP", style="Material.TButton",
                   command=self._run_webp).grid(row=0, column=0, padx=(0, 12), pady=6)
        ttk.Button(btns, text="Blur Master", style="Material.TButton",
                   command=self._toggle_blur_panel).grid(row=0, column=1, padx=(0, 12), pady=6)
        ttk.Button(btns, text="REMOVE DUPLICATE", style="Material.TButton",
                   command=self._run_dedupe).grid(row=0, column=2, padx=(0, 12), pady=6)
        ttk.Button(btns, text="QUICK BLUR", style="Material.TButton",
                   command=self._toggle_qb_panel).grid(row=0, column=3, padx=(0, 12), pady=6)

        # Blur Master settings panel (hidden until clicked)
        self.blur_panel = ttk.Frame(parent, style="Card.TFrame", padding=16)
        self.blur_panel.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        parent.grid_rowconfigure(3, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        self._build_blur_panel(self.blur_panel)
        self.blur_panel.grid_remove()

        # Quick Blur panel (hidden until clicked)
        self.qb_panel = ttk.Frame(parent, style="Card.TFrame", padding=16)
        self.qb_panel.grid(row=4, column=0, sticky="nsew", pady=(12, 0))
        parent.grid_rowconfigure(4, weight=1)
        self._build_qb_panel(self.qb_panel)
        self.qb_panel.grid_remove()

    # ---- Quick Blur panel ----
    def _toggle_qb_panel(self):
        # auto-hide the other panel to keep UI tidy
        if self.blur_panel.winfo_ismapped():
            self.blur_panel.grid_remove()
        if self.qb_panel.winfo_ismapped():
            self.qb_panel.grid_remove()
        else:
            self.qb_panel.grid()

    def _build_qb_panel(self, p):
        # state
        self.qb_in = tk.StringVar(value="")
        self.qb_out = tk.StringVar(value="")
        self.qb_radius = tk.IntVar(value=78)
        self.qb_selected_files = []  # list of chosen files (or empty to use folder)

        p.columnconfigure(1, weight=1)

        r = 0
        ttk.Label(p, text="Quick Blur", style="Card.TLabel",
                  font=("Segoe UI Semibold", 13)).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1

        ttk.Label(p, text="Input (folder or files)").grid(row=r, column=0, sticky="w")
        ttk.Entry(p, textvariable=self.qb_in).grid(row=r, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(p, text="Choose files…", style="Material.Outlined.TButton",
                   command=self._qb_choose_files).grid(row=r, column=2, sticky="w")
        r += 1

        ttk.Label(p, text="(or) Choose folder").grid(row=r, column=0, sticky="w")
        ttk.Button(p, text="Choose folder…", style="Material.Outlined.TButton",
                   command=self._qb_choose_folder).grid(row=r, column=1, sticky="w", padx=(6, 0))
        r += 1

        ttk.Label(p, text="Output folder (optional)").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(p, textvariable=self.qb_out).grid(row=r, column=1, sticky="ew", padx=(6, 6), pady=(6, 0))
        ttk.Button(p, text="Choose…", style="Material.Outlined.TButton",
                   command=self._qb_choose_out).grid(row=r, column=2, sticky="w", pady=(6, 0))
        r += 1

        ttk.Label(p, text="Blur radius").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(p, from_=0, to=500, textvariable=self.qb_radius, width=8)\
            .grid(row=r, column=1, sticky="w", padx=(6, 6), pady=(6, 0))
        r += 1

        self.qb_progress = ttk.Progressbar(p, mode="determinate",
                                           style="Accent.Horizontal.TProgressbar")
        self.qb_progress.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(10, 8))
        r += 1

        ttk.Button(p, text="Run", style="Material.TButton",
                   command=self._run_quick_blur_panel).grid(row=r, column=0, sticky="w")

    # ---- Blur Master panel ----
    def _build_blur_panel(self, p):
        # Vars
        self.enable_copy = tk.BooleanVar(value=False)
        self.copy_interval = tk.IntVar(value=6)
        self.source_dir = tk.StringVar(value="")
        self.dest_name = tk.StringVar(value="third_photos")
        self.blur_kernel = tk.IntVar(value=151)
        self.padding = tk.IntVar(value=60)
        self.circle_scale = tk.DoubleVar(value=1.0)

        # Classes
        self.class_vars = {}
        for name in [
            'FEMALE_GENITALIA_EXPOSED','MALE_GENITALIA_EXPOSED',
            'FEMALE_BREAST_EXPOSED','ANUS_EXPOSED','BUTTOCKS_EXPOSED','ANUS_COVERED'
        ]:
            self.class_vars[name] = tk.BooleanVar(value=True)

        self.wm_vars = {}
        p.columnconfigure(1, weight=1)
        p.columnconfigure(3, weight=1)

        r = 0
        ttk.Label(p, text="Blur Master", style="Card.TLabel",
                  font=("Segoe UI Semibold", 13)).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1

        ttk.Checkbutton(p, text="ENABLE_PHOTO_COPYING", variable=self.enable_copy)\
            .grid(row=r, column=0, sticky="w", pady=4)
        ttk.Label(p, text="COPY_INTERVAL").grid(row=r, column=1, sticky="e")
        ttk.Spinbox(p, from_=1, to=999, textvariable=self.copy_interval, width=6)\
            .grid(row=r, column=2, sticky="w", padx=(6, 12))
        r += 1

        ttk.Label(p, text="SOURCE_DIRECTORY").grid(row=r, column=0, sticky="w")
        ttk.Entry(p, textvariable=self.source_dir).grid(row=r, column=1, columnspan=2, sticky="ew", padx=(6, 6))
        ttk.Button(p, text="Choose…", style="Material.Outlined.TButton",
                   command=lambda: self._pick_dir(self.source_dir)).grid(row=r, column=3, sticky="w")
        r += 1

        ttk.Label(p, text="CUSTOM_DEST_FOLDER_NAME").grid(row=r, column=0, sticky="w")
        ttk.Entry(p, textvariable=self.dest_name).grid(row=r, column=1, sticky="ew", padx=(6, 6))
        r += 1

        ttk.Label(p, text="BLUR_KERNEL_SIZE").grid(row=r, column=0, sticky="w")
        ttk.Spinbox(p, from_=3, to=999, increment=2, textvariable=self.blur_kernel, width=6)\
            .grid(row=r, column=1, sticky="w", padx=(6, 12))
        ttk.Label(p, text="PADDING").grid(row=r, column=2, sticky="e")
        ttk.Spinbox(p, from_=0, to=500, textvariable=self.padding, width=6)\
            .grid(row=r, column=3, sticky="w", padx=(6, 0))
        r += 1

        ttk.Label(p, text="CIRCLE_RADIUS_SCALE").grid(row=r, column=0, sticky="w")
        ttk.Scale(p, from_=0.5, to=2.5, orient="horizontal", variable=self.circle_scale)\
            .grid(row=r, column=1, columnspan=3, sticky="ew", padx=(6, 0))
        r += 1

        ttk.Label(p, text="CLASSES_TO_CHECK").grid(row=r, column=0, sticky="w", pady=(8, 2))
        r += 1
        cls_frame = ttk.Frame(p, style="Card.TFrame")
        cls_frame.grid(row=r, column=0, columnspan=4, sticky="ew")
        cols = 3
        for i, (name, var) in enumerate(self.class_vars.items()):
            ttk.Checkbutton(cls_frame, text=name, variable=var)\
                .grid(row=i // cols, column=i % cols, sticky="w", padx=(0, 18), pady=2)
        r += 1

        ttk.Label(p, text="Watermark", style="Card.TLabel").grid(row=r, column=0, sticky="w", pady=(10, 2))
        ttk.Button(p, text="WaterMark Path Setting", style="Material.Outlined.TButton",
                   command=self._open_wm_settings).grid(row=r, column=1, sticky="w")
        r += 1

        self.wm_checks_frame = ttk.Frame(p, style="Card.TFrame")
        self.wm_checks_frame.grid(row=r, column=0, columnspan=4, sticky="ew", pady=(4, 8))
        self._refresh_wm_checkboxes()
        r += 1

        self.progress = ttk.Progressbar(p, mode="indeterminate", style="Accent.Horizontal.TProgressbar")
        self.progress.grid(row=r, column=0, columnspan=4, sticky="ew", pady=(6, 8))
        r += 1

        ttk.Button(p, text="RUN", style="Material.TButton", command=self._run_blur_master)\
            .grid(row=r, column=0, sticky="w")

    def _refresh_wm_checkboxes(self):
        sets = getattr(self, "watermark_sets", None) or dict(WATERMARK_SETS)
        self.watermark_sets = sets

        if hasattr(self, "wm_checks_frame"):
            for w in self.wm_checks_frame.winfo_children():
                w.destroy()
        self.wm_vars = {}

        cols = 4
        for i, name in enumerate(sets.keys()):
            var = tk.BooleanVar(value=False)
            self.wm_vars[name] = var
            ttk.Checkbutton(self.wm_checks_frame, text=name, variable=var)\
                .grid(row=i // cols, column=i % cols, sticky="w", padx=(0, 18), pady=2)

    def _open_wm_settings(self):
        def on_save(new_sets, max_w, max_h, quality, opacity):
            self.watermark_sets = new_sets or {}
            self.max_width.set(max_w)
            self.max_height.set(max_h)
            self.img_quality.set(quality)
            self.wm_opacity.set(opacity)
            self._refresh_wm_checkboxes()
        WatermarkSettingsDialog(self, self.watermark_sets or {}, self.max_width.get(),
                                self.max_height.get(), self.img_quality.get(),
                                self.wm_opacity.get(), on_save)

    def _toggle_blur_panel(self):
        # auto-hide the other panel to keep UI tidy
        if self.qb_panel.winfo_ismapped():
            self.qb_panel.grid_remove()
        if self.blur_panel.winfo_ismapped():
            self.blur_panel.grid_remove()
        else:
            self.blur_panel.grid()

    def _video_tab(self, parent):
        ttk.Label(parent, text="Video tools", style="Card.TLabel",
                  font=("Segoe UI Semibold", 14)).grid(row=0, column=0, sticky="w")
        ttk.Separator(parent).grid(row=1, column=0, columnspan=6, sticky="ew", pady=12)

        btns = ttk.Frame(parent, style="Card.TFrame")
        btns.grid(row=2, column=0, sticky="w", pady=8)

        ttk.Button(btns, text="Transcode H.264", style="Material.TButton",
                   command=self._run_transcode).grid(row=0, column=0, padx=(0, 12), pady=6)
        ttk.Button(btns, text="Extract Frames", style="Material.Outlined.TButton",
                   command=self._run_frames).grid(row=0, column=1, padx=(0, 12), pady=6)

        parent.grid_columnconfigure(0, weight=1)

    # ---------- Behavior ----------
    def _bind_shortcuts(self):
        self.bind_all("<Control-KeyPress-1>", lambda e: self._select_tab("IMAGE"))
        self.bind_all("<Control-KeyPress-2>", lambda e: self._select_tab("VIDEO"))

    def _on_switch(self):
        self._select_tab(self.segment_var.get())

    def _on_tab_changed(self, _):
        idx = self.nb.index(self.nb.select())
        self.segment_var.set("IMAGE" if idx == 0 else "VIDEO")

    def _select_tab(self, name: str):
        self.nb.select(0 if name == "IMAGE" else 1)
        self.segment_var.set(name)

    # ---------- Actions ----------
    def _pick_dir(self, var: tk.StringVar):
        p = filedialog.askdirectory(title="Choose folder")
        if p:
            var.set(p)

    def _run_webp(self):
        folder = filedialog.askdirectory(title="Pick folder with images")
        if not folder:
            return
        def work():
            try:
                ok, total = convert_folder_to_webp(folder, recursive=True)
                self.after(0, lambda: messagebox.showinfo("WEBP", f"Converted {ok}/{total} files."))
            except Exception:
                msg = traceback.format_exc()
                self.after(0, lambda m=msg: messagebox.showerror("WEBP error", m))
        Thread(target=work, daemon=True).start()

    def _chosen_brand(self) -> str:
        for name, var in self.wm_vars.items():
            if var.get():
                return name
        return ""  # none selected -> skip watermark

    def _run_blur_master(self):
        folder = self.source_dir.get().strip()
        if not folder:
            folder = filedialog.askdirectory(title="Pick SOURCE_DIRECTORY")
            if not folder:
                return
            self.source_dir.set(folder)

        brand = self._chosen_brand()
        self.progress.start(15)

        def work():
            try:
                k = self.blur_kernel.get()
                if k % 2 == 0:
                    k += 1
                result = run_blur_master(
                    source_directory=folder,
                    enable_photo_copying=self.enable_copy.get(),
                    copy_interval=int(self.copy_interval.get()),
                    custom_dest_folder_name=self.dest_name.get().strip() or "third_photos",
                    classes_to_check=[n for n, v in self.class_vars.items() if v.get()],
                    blur_kernel_size=k,
                    padding=int(self.padding.get()),
                    circle_radius_scale=float(self.circle_scale.get()),
                    watermark_brand=brand,  # "" -> skip
                    watermark_sets=self.watermark_sets,
                    max_width=int(self.max_width.get()),
                    max_height=int(self.max_height.get()),
                    img_quality=int(self.img_quality.get()),
                    wm_opacity=float(self.wm_opacity.get()),
                )
                msg = f"Censored: {result['censored_folder']}"
                if result.get("watermarked_folder"):
                    msg += f"\nWatermarked: {result['watermarked_folder']}"
                self.after(0, lambda m=msg: messagebox.showinfo("Blur Master", m))
            except Exception:
                msg = traceback.format_exc()
                self.after(0, lambda m=msg: messagebox.showerror("Blur Master error", m))
            finally:
                self.after(0, self.progress.stop)
        Thread(target=work, daemon=True).start()

    def _run_transcode(self):
        f = filedialog.askopenfilename(title="Pick a video")
        if not f:
            return
        def work():
            try:
                out = transcode_h264(f)
                self.after(0, lambda o=out: messagebox.showinfo("Transcode", f"Saved: {o}"))
            except Exception:
                msg = traceback.format_exc()
                self.after(0, lambda m=msg: messagebox.showerror("FFmpeg error", m))
        Thread(target=work, daemon=True).start()

    # Quick Blur helpers
    def _qb_choose_files(self):
        from pathlib import Path
        files = filedialog.askopenfilenames(
            title="Choose images",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tiff;*.webp"),
                       ("All files", "*.*")]
        )
        if files:
            self.qb_selected_files = list(files)
            self.qb_in.set(str(Path(files[0]).parent))

    def _qb_choose_folder(self):
        d = filedialog.askdirectory(title="Choose input folder")
        if d:
            self.qb_selected_files = []  # use folder
            self.qb_in.set(d)

    def _qb_choose_out(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.qb_out.set(d)

    def _run_frames(self):
        f = filedialog.askopenfilename(title="Pick a video")
        if not f:
            return
        def work():
            try:
                out = extract_frames(f, fps=1)
                self.after(0, lambda o=out: messagebox.showinfo("Frames", f"Frames in: {o}"))
            except Exception:
                msg = traceback.format_exc()
                self.after(0, lambda m=msg: messagebox.showerror("FFmpeg error", m))
        Thread(target=work, daemon=True).start()

    def _run_dedupe(self):
        folder = filedialog.askdirectory(title="Pick SOURCE folder to deduplicate")
        if not folder:
            return

        prog = tk.Toplevel(self)
        prog.title("Removing duplicates…")
        prog.transient(self)
        prog.grab_set()
        prog.resizable(False, False)
        ttk.Label(prog, text="Scanning images…").grid(row=0, column=0, padx=16, pady=(16, 8))
        pb = ttk.Progressbar(prog, mode="determinate",
                             style="Accent.Horizontal.TProgressbar", length=420)
        pb.grid(row=1, column=0, padx=16, pady=(0, 16))
        prog.update_idletasks()

        def progress(done, total, _msg=None):
            def ui():
                pb.configure(maximum=max(total, 1))
                pb["value"] = done
            self.after(0, ui)

        def work():
            try:
                summary = copy_images_and_deduplicate(folder, progress=progress)
                msg = (
                    f"Scanned: {summary['total_scanned']}\n"
                    f"Copied unique: {summary['copied_unique']}\n"
                    f"Skipped duplicates: {summary['skipped_duplicates']}\n"
                    f"Output: {summary['output']}"
                )
                self.after(0, lambda m=msg: messagebox.showinfo("Duplicate Remover", m))
            except Exception:
                err = traceback.format_exc()
                self.after(0, lambda e=err: messagebox.showerror("Duplicate Remover error", e))
            finally:
                self.after(0, prog.destroy)

        Thread(target=work, daemon=True).start()

    def _run_quick_blur_panel(self):
        input_path = self.qb_in.get().strip()
        files = self.qb_selected_files or None
        if not input_path and not files:
            messagebox.showerror("Quick Blur", "Please choose input files or a folder.")
            return

        self.qb_progress.configure(value=0, maximum=1)

        def progress(done, total, _name=None):
            def ui():
                self.qb_progress.configure(maximum=max(total, 1))
                self.qb_progress["value"] = done
            self.after(0, ui)

        def work():
            try:
                summary = blur_folder(
                    input_folder=input_path or (files[0] if files else ""),
                    radius=int(self.qb_radius.get()),
                    output_folder=(self.qb_out.get().strip() or None),
                    progress=progress,
                    files=files
                )
                msg = (f"Input: {summary['input']}\n"
                       f"Output: {summary['output']}\n"
                       f"Images found: {summary['total']}\n"
                       f"Processed: {summary['processed']}\n"
                       f"Failed: {summary['failed']}\n"
                       f"Radius: {summary['radius']}")
                self.after(0, lambda m=msg: messagebox.showinfo("Quick Blur", m))
            except Exception:
                err = traceback.format_exc()
                self.after(0, lambda e=err: messagebox.showerror("Quick Blur error", e))

        Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
