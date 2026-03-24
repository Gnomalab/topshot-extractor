"""
TopShot Extractor v0.9.1 — by Gnomalab Studio 2026
Smart frame extractor for photogrammetry & 3D workflows.
www.gnomalab.es

Requirements:
    pip install opencv-python numpy tkinterdnd2 Pillow customtkinter
"""

import sys, os, threading, time, json, cv2, numpy as np
import tkinter as tk, webbrowser, shutil, subprocess
import platform, urllib.request, zipfile, tarfile
from tkinter import filedialog, messagebox
from pathlib import Path
from datetime import datetime

VERSION = "0.9.1"

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    HAS_CTK = True
except ImportError:
    HAS_CTK = False
    print("ERROR: pip install customtkinter")
    sys.exit(1)

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────
APP_DIR     = Path(__file__).parent
TOOLS_DIR   = APP_DIR / "tools"
CONFIG_PATH = APP_DIR / "topshot_config.json"
PRESETS_PATH= APP_DIR / "topshot_presets.json"
RECENT_PATH = APP_DIR / "topshot_recent.json"
TOOLS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
#  COLORS  (Blender-inspired palette)
# ─────────────────────────────────────────────
C = {
    "bg0":  "#141414",   # darkest — status bar, toolbar
    "bg1":  "#1d1d1d",   # main background
    "bg2":  "#252525",   # panels
    "bg3":  "#2e2e2e",   # cards, sections
    "bg4":  "#383838",   # hover, active
    "fg":   "#e8e8e8",   # primary text
    "fg2":  "#a0a0a0",   # secondary text
    "fg3":  "#606060",   # hints, disabled
    "acc":  "#4d90f0",   # blue accent
    "acc2": "#6aaaf5",   # lighter accent
    "grn":  "#5fb55f",   # success / selected
    "red":  "#e05252",   # error / delete
    "yel":  "#d4a843",   # warning / analyzing
    "org":  "#d4793c",   # exporting
}

# CTk appearance overrides
ctk.set_appearance_mode("dark")

# ─────────────────────────────────────────────
#  FONTS
# ─────────────────────────────────────────────
FF = "Segoe UI"
FONT   = (FF, 11)
FONTB  = (FF, 11, "bold")
FONTS  = (FF, 10)
FONTXS = (FF, 9)
FONTL  = (FF, 14, "bold")
MONO   = ("Consolas", 9)

# ─────────────────────────────────────────────
#  CONFIG & PRESETS
# ─────────────────────────────────────────────
CONFIG_DEFAULTS = {
    "language": "es", "accent": "#4d90f0", "theme": "dark",
    "notify": "sound_flash",
    "smartshot_autostart": False,
    "default_mode": "auto",
    "default_blur": 30.0, "default_sim": 0.94,
    "default_shake": 35.0, "default_max": 300,
    "engine": "ffmpeg_first", "analysis_res": 320,
    "default_format": "jpg", "default_quality": 95,
    "default_size": "Original", "default_output": "",
}

SYSTEM_PRESETS = [
    {"name":"3DGS estandar","desc":"Equilibrado para Gaussian Splatting",
     "system":True,"blur":30,"sim":0.94,"shake":35,"max":300,"fmt":"jpg","quality":95,"size":"Original"},
    {"name":"Captura rapida","desc":"Videos cortos, camara en movimiento",
     "system":True,"blur":20,"sim":0.92,"shake":50,"max":200,"fmt":"jpg","quality":90,"size":"Original"},
    {"name":"Arquitectura interior","desc":"Baja shake, alta nitidez",
     "system":True,"blur":50,"sim":0.96,"shake":20,"max":400,"fmt":"jpg","quality":95,"size":"Original"},
    {"name":"Drone exterior","desc":"Alta tolerancia shake, exterior",
     "system":True,"blur":25,"sim":0.93,"shake":60,"max":250,"fmt":"jpg","quality":95,"size":"1920"},
    {"name":"Objeto de estudio","desc":"Turntable, alta calidad",
     "system":True,"blur":40,"sim":0.97,"shake":15,"max":350,"fmt":"png","quality":100,"size":"Original"},
]

def load_config():
    cfg = dict(CONFIG_DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH,"r",encoding="utf-8") as f: cfg.update(json.load(f))
    except Exception: pass
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_PATH,"w",encoding="utf-8") as f: json.dump(cfg,f,indent=2,ensure_ascii=False)
    except Exception as e: print(f"Config save: {e}")

def load_presets():
    user = []
    try:
        if PRESETS_PATH.exists():
            with open(PRESETS_PATH,"r",encoding="utf-8") as f: user = json.load(f)
    except Exception: pass
    return SYSTEM_PRESETS + user

def save_user_presets(presets):
    user = [p for p in presets if not p.get("system")]
    try:
        with open(PRESETS_PATH,"w",encoding="utf-8") as f: json.dump(user,f,indent=2,ensure_ascii=False)
    except Exception: pass

def load_recent():
    try:
        if RECENT_PATH.exists():
            with open(RECENT_PATH,"r",encoding="utf-8") as f: return json.load(f)
    except Exception: pass
    return []

def save_recent(paths):
    try:
        with open(RECENT_PATH,"w",encoding="utf-8") as f: json.dump(paths[:10],f,indent=2)
    except Exception: pass

def add_recent(path):
    r = [p for p in load_recent() if p != path]
    r.insert(0, path)
    save_recent(r[:10])

# ─────────────────────────────────────────────
#  FFMPEG
# ─────────────────────────────────────────────
FFMPEG_URLS = {
    "Windows": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "Darwin":  "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
    "Linux":   "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
}

def find_ffmpeg():
    ext = ".exe" if platform.system() == "Windows" else ""
    local = TOOLS_DIR / f"ffmpeg{ext}"
    if local.exists(): return str(local)
    return shutil.which("ffmpeg")

# ─────────────────────────────────────────────
#  QUALITY METRICS
# ─────────────────────────────────────────────
def laplacian_variance(gray):
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())

def phash(gray, size=16):
    r = cv2.resize(gray, (size,size), interpolation=cv2.INTER_AREA).astype(np.float32)
    return (r > r.mean()).flatten()

def hash_similarity(h1, h2):
    return float(np.sum(h1==h2)) / len(h1)

def optical_flow_magnitude(p, c):
    flow = cv2.calcOpticalFlowFarneback(p,c,None,0.5,3,15,3,5,1.2,0)
    mag,_ = cv2.cartToPolar(flow[...,0], flow[...,1])
    return float(mag.mean())

# ─────────────────────────────────────────────
#  VIDEO ANALYSIS
# ─────────────────────────────────────────────
def _probe_video(path):
    cap = cv2.VideoCapture(path)
    fps   = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return fps, total, w, h

def _scale_gray(frame, aw=320):
    h, w = frame.shape[:2]
    if w <= aw: return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    s = aw/w
    return cv2.cvtColor(cv2.resize(frame,(aw,int(h*s)),interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)

def _analyze_ffmpeg(video_path, ffmpeg_bin, fps, total, width, height, duration,
                    t_in, t_out, analysis_w, progress_cb, log_cb, cancel_flag):
    import tempfile, glob, shutil as _sh
    log_cb("ffmpeg: extrayendo I-frames...")
    tmp = Path(tempfile.mkdtemp(prefix="topshot_"))
    try:
        vf = f"select=eq(pict_type\\,I),scale={analysis_w}:-2"
        cmd = [ffmpeg_bin]
        if t_in > 0: cmd += ["-ss", str(t_in)]
        cmd += ["-i", video_path]
        if t_out < duration: cmd += ["-to", str(t_out)]
        cmd += ["-vf", vf, "-vsync", "vfr", "-q:v", "5",
                str(tmp/"frame_%08d.jpg"), "-y", "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        if r.returncode != 0: log_cb("ffmpeg fallo, usando OpenCV..."); return None
        files = sorted(glob.glob(str(tmp/"frame_*.jpg")))
        if not files: log_cb("ffmpeg sin frames"); return None
        log_cb(f"ffmpeg: {len(files)} I-frames")

        # Optional: get timestamps from ffprobe
        iframe_times = []
        try:
            probe_bin = ffmpeg_bin.replace("ffmpeg","ffprobe")
            if shutil.which(probe_bin) or os.path.isfile(probe_bin):
                pr = subprocess.run([probe_bin,"-v","quiet","-select_streams","v:0",
                    "-show_entries","packet=pts_time,flags","-of","csv=p=0",video_path],
                    capture_output=True, text=True, timeout=60)
                for line in pr.stdout.splitlines():
                    parts = line.strip().split(",")
                    if len(parts)>=2 and "K" in parts[-1]:
                        try:
                            t = float(parts[0])
                            if t_in <= t <= t_out: iframe_times.append(t)
                        except ValueError: pass
        except Exception: pass

        candidates = []; prev_gray = None; n = len(files)
        for i, fp in enumerate(files):
            if cancel_flag(): return None
            fr = cv2.imread(fp)
            if fr is None: continue
            gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            blur = laplacian_variance(gray)
            flow = optical_flow_magnitude(prev_gray, gray) if prev_gray is not None else 0.0
            h = phash(gray)
            ts = iframe_times[i] if i < len(iframe_times) else t_in + (i/max(n-1,1))*(t_out-t_in)
            candidates.append({"frame_idx":int(ts*fps),"timestamp":ts,"blur":blur,
                                "flow":flow,"hash":h,"frame":None,"video_path":video_path,
                                "selected":False,"reject_reason":"","excluded":False})
            prev_gray = gray
            progress_cb(int(i/max(n-1,1)*80))
        return candidates
    finally:
        _sh.rmtree(tmp, ignore_errors=True)

def _analyze_opencv(video_path, fps, total, width, height, duration,
                    t_in, t_out, analysis_w, progress_cb, log_cb, cancel_flag):
    log_cb("OpenCV: analizando frames...")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened(): return None
    f_in  = max(0, int(t_in*fps))
    f_out = min(total, int(t_out*fps))
    step  = max(1, int(fps*0.5))
    candidates = []; prev_gray = None
    frames_range = list(range(f_in, f_out, step))
    for idx, i in enumerate(frames_range):
        if cancel_flag(): cap.release(); return None
        cap.set(cv2.CAP_PROP_POS_FRAMES, i); ret, frame = cap.read()
        if not ret: break
        gray = _scale_gray(frame, analysis_w)
        blur = laplacian_variance(gray)
        flow = optical_flow_magnitude(prev_gray, gray) if prev_gray is not None else 0.0
        h = phash(gray)
        candidates.append({"frame_idx":i,"timestamp":i/fps,"blur":blur,"flow":flow,
                            "hash":h,"frame":frame,"video_path":video_path,
                            "selected":False,"reject_reason":"","excluded":False})
        prev_gray = gray
        progress_cb(int(idx/max(len(frames_range)-1,1)*80))
    cap.release()
    return candidates

def _reload_fullres(candidates, fps, progress_cb, log_cb, cancel_flag):
    sel = [c for c in candidates if c.get("selected") and not c.get("excluded") and c.get("frame") is None]
    if not sel: return True
    log_cb(f"Cargando {len(sel)} frames a resolucion completa...")
    cap = cv2.VideoCapture(sel[0]["video_path"])
    if not cap.isOpened(): return False
    for i, c in enumerate(sel):
        if cancel_flag(): cap.release(); return False
        cap.set(cv2.CAP_PROP_POS_FRAMES, c["frame_idx"]); ret, fr = cap.read()
        if ret: c["frame"] = fr
        progress_cb(80 + int(i/max(len(sel)-1,1)*16))
    cap.release()
    return True

def analyze_video(video_path, t_in, t_out, analysis_w, progress_cb, log_cb, cancel_flag):
    fps, total, width, height = _probe_video(video_path)
    duration = total/fps if fps > 0 else 0
    t_in  = max(0.0, t_in)
    t_out = min(duration, t_out if t_out > 0 else duration)
    log_cb(f"{Path(video_path).name}  {width}x{height} | {fps:.1f}fps | {duration:.1f}s")
    log_cb(f"Zona: {t_in:.1f}s -> {t_out:.1f}s")
    ffmpeg = find_ffmpeg()
    log_cb(f"Motor: {'ffmpeg' if ffmpeg else 'OpenCV'}")
    t0 = time.time()
    if ffmpeg:
        cands = _analyze_ffmpeg(video_path, ffmpeg, fps, total, width, height, duration,
                                t_in, t_out, analysis_w, progress_cb, log_cb, cancel_flag)
        if cands is None and not cancel_flag():
            cands = _analyze_opencv(video_path, fps, total, width, height, duration,
                                    t_in, t_out, analysis_w, progress_cb, log_cb, cancel_flag)
    else:
        cands = _analyze_opencv(video_path, fps, total, width, height, duration,
                                t_in, t_out, analysis_w, progress_cb, log_cb, cancel_flag)
    if cands is None: return None, None
    log_cb(f"{len(cands)} candidatos en {time.time()-t0:.1f}s")
    progress_cb(80)
    return cands, {"fps":fps,"total_frames":total,"duration":duration,"video_path":video_path,
                   "width":width,"height":height,"ffmpeg":ffmpeg is not None,
                   "t_in":t_in,"t_out":t_out}

# ─────────────────────────────────────────────
#  SELECTION
# ─────────────────────────────────────────────
def smart_select(candidates, blur_pct, sim_thr, shake_thr, max_frames):
    if not candidates: return []
    for c in candidates: c["selected"]=False; c["reject_reason"]=""
    bt = float(np.percentile([c["blur"] for c in candidates], blur_pct))
    last_h = None; sel = []
    for c in candidates:
        if c["blur"] < bt:       c["reject_reason"]="blur";  continue
        if c["flow"] > shake_thr: c["reject_reason"]="shake"; continue
        if last_h is not None and hash_similarity(last_h, c["hash"]) >= sim_thr:
                                  c["reject_reason"]="dup";   continue
        c["selected"] = True; last_h = c["hash"]; sel.append(c)
        if max_frames > 0 and len(sel) >= max_frames: break
    return sel

def manual_select(candidates, count):
    for c in candidates: c["selected"]=False; c["reject_reason"]=""
    if not candidates or count <= 0: return []
    count = min(count, len(candidates)); sel = []
    for i in np.linspace(0, len(candidates)-1, count, dtype=int):
        candidates[i]["selected"] = True; sel.append(candidates[i])
    return sel

# ─────────────────────────────────────────────
#  VIDEO PLAYER  (tk.Canvas — works inside CTk)
# ─────────────────────────────────────────────
class VideoPlayer:
    def __init__(self, parent, on_time_change=None):
        self._cap       = None
        self._fps       = 25.0
        self._total     = 0
        self._duration  = 0.0
        self._playing   = False
        self._current_f = 0
        self._lock      = threading.Lock()
        self._photo     = None
        self._on_time_change = on_time_change

        self.canvas = tk.Canvas(parent, bg="#0a0a0a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._on_resize())

        self._hint_id = self.canvas.create_text(
            20, 20, text="Arrastra un video o usa Abrir",
            fill=C["fg3"], font=FONT, anchor="nw")

    def load(self, path):
        self.stop()
        with self._lock:
            if self._cap: self._cap.release()
            self._cap = cv2.VideoCapture(path)
            if not self._cap.isOpened(): return False
            self._fps      = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
            self._total    = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self._duration = self._total / self._fps
            self._current_f = 0
        self._show_frame(0)
        return True

    def stop(self):
        self._playing = False

    def play(self):
        if not self._cap or self._playing: return
        self._playing = True
        threading.Thread(target=self._play_loop, daemon=True).start()

    def pause(self):
        self._playing = False

    def toggle(self):
        if self._playing: self.pause()
        else: self.play()

    def seek(self, timestamp):
        if not self._cap: return
        f = max(0, min(self._total-1, int(timestamp * self._fps)))
        self._current_f = f
        self._show_frame(f)

    def seek_frame(self, delta):
        self.seek((self._current_f + delta) / self._fps)

    @property
    def current_time(self):
        return self._current_f / self._fps if self._fps > 0 else 0

    @property
    def duration(self):
        return self._duration

    def _play_loop(self):
        interval = 1.0 / max(self._fps, 1.0)
        display_interval = max(interval, 1.0/30.0)
        t_start = time.time(); f_start = self._current_f
        while self._playing:
            elapsed = time.time() - t_start
            target_f = f_start + int(elapsed / interval)
            target_f = min(target_f, self._total - 1)
            if target_f > self._current_f:
                self._current_f = target_f
                self._show_frame(self._current_f)
            if self._current_f >= self._total - 1:
                self._playing = False; break
            time.sleep(display_interval * 0.5)

    def _show_frame(self, frame_idx):
        if not self._cap: return
        with self._lock:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = self._cap.read()
        if not ret: return
        h, w = frame.shape[:2]
        if w > 960:
            s = 960/w
            frame = cv2.resize(frame, (960, int(h*s)), interpolation=cv2.INTER_LINEAR)
        if self.canvas.winfo_exists():
            self.canvas.after(0, self._display_frame, frame, frame_idx)

    def _display_frame(self, frame, frame_idx):
        if not self.canvas.winfo_exists(): return
        self._current_f = frame_idx
        cw = self.canvas.winfo_width() or 640
        ch = self.canvas.winfo_height() or 360
        if HAS_PIL:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            img.thumbnail((cw, ch), Image.BILINEAR)
            ph = ImageTk.PhotoImage(img)
            self._photo = ph
            self.canvas.delete("all")
            self.canvas.create_image(cw//2, ch//2, image=ph, anchor="center")
        else:
            self.canvas.delete("all")
            self.canvas.create_text(cw//2, ch//2,
                text=f"t={self.current_time:.2f}s  (pip install Pillow)",
                fill=C["fg2"], font=FONT)
        if self._on_time_change:
            self._on_time_change(self.current_time)

    def _on_resize(self):
        if self._cap: self._show_frame(self._current_f)

    def release(self):
        self.stop()
        if self._cap: self._cap.release(); self._cap = None


# ─────────────────────────────────────────────
#  MAIN APP
# ─────────────────────────────────────────────
if HAS_DND:
    class _Base(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self):
            super().__init__()
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class _Base(ctk.CTk):
        pass

class TopShotApp(_Base):
    def __init__(self):
        super().__init__()
        self._cfg      = load_config()
        self._presets  = load_presets()
        self.title(f"TopShot Extractor  v{VERSION}")
        self.geometry("1180x700")
        self.minsize(900, 580)
        self.configure(fg_color=C["bg1"])

        # State
        self._video_path   = ""
        self._info         = None
        self._candidates   = None
        self._selected     = []
        self._running      = False
        self._cancel_flag  = False
        self._traces_ok    = False
        self._last_out     = None
        self._preview_idx  = 0
        self._preview_photos = []
        self._thumb_imgs   = []
        self._player       = None
        self._spinner_active = False
        self._t_in = 0.0
        self._t_out = 0.0
        self._ffmpeg_path = find_ffmpeg()

        self._build_ui()
        self._show_welcome()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

    # ─────────────────────────────────────────
    #  BUILD CHROME
    # ─────────────────────────────────────────
    def _build_ui(self):
        # TOOLBAR — semaphore workflow buttons
        self._toolbar = ctk.CTkFrame(self, fg_color=C["bg0"], height=38, corner_radius=0)
        self._toolbar.pack(fill="x")
        self._toolbar.pack_propagate(False)

        ctk.CTkLabel(self._toolbar, text="TopShot",
                     font=ctk.CTkFont(FF, 13, "bold"),
                     text_color=C["fg"]).pack(side="left", padx=(12,8))

        self._tb_open    = self._tb_btn("Abrir",     self._browse_file, color=C["acc"])
        self._tb_sep()
        self._tb_analyze = self._tb_btn("Analizar",  self._start_analyze, locked=True)
        self._tb_review  = self._tb_btn("Revisar",   self._open_review,   locked=True)
        self._tb_export  = self._tb_btn("Exportar",  self._export,        locked=True)
        self._tb_sep()
        self._tb_prefs   = self._tb_btn("Preferencias", self._open_prefs)

        # ffmpeg badge
        self._ffmpeg_lbl = ctk.CTkLabel(self._toolbar, text="", font=ctk.CTkFont(FF,9),
                                         text_color=C["grn"], cursor="hand2")
        self._ffmpeg_lbl.pack(side="right", padx=10)
        self._ffmpeg_lbl.bind("<Button-1>", lambda _: self._open_ffmpeg_dialog())
        self._update_ffmpeg_badge()

        # SOURCE BAR
        self._source_bar = ctk.CTkFrame(self, fg_color=C["bg0"], height=22, corner_radius=0)
        self._source_lbl = ctk.CTkLabel(self._source_bar, text="", font=ctk.CTkFont("Consolas",8),
                                         text_color=C["fg2"], anchor="w")
        self._source_lbl.pack(side="left", padx=10)

        # MAIN
        self._main = ctk.CTkFrame(self, fg_color=C["bg1"], corner_radius=0)
        self._main.pack(fill="both", expand=True)

        # STATUS BAR
        self._statusbar = ctk.CTkFrame(self, fg_color=C["bg0"], height=20, corner_radius=0)
        self._statusbar.pack(fill="x")
        self._statusbar.pack_propagate(False)
        self._status_dot = ctk.CTkLabel(self._statusbar, text="o", font=ctk.CTkFont("Consolas",8),
                                         text_color=C["fg3"], width=16)
        self._status_dot.pack(side="left", padx=(8,0))
        self._status_var = tk.StringVar(value="Arrastra un video para comenzar")
        ctk.CTkLabel(self._statusbar, textvariable=self._status_var,
                     font=ctk.CTkFont("Consolas",8), text_color=C["fg2"]).pack(side="left")
        self._spinner_lbl = ctk.CTkLabel(self._statusbar, text="",
                                          font=ctk.CTkFont("Consolas",8,"bold"), text_color=C["yel"])
        self._spinner_lbl.pack(side="left", padx=6)
        ctk.CTkLabel(self._statusbar, text=f"TopShot v{VERSION}  by Gnomalab Studio 2026",
                     font=ctk.CTkFont("Consolas",8), text_color=C["fg3"]).pack(side="right", padx=8)

    def _tb_btn(self, label, cmd, locked=False, color=None):
        """Toolbar button. color=None means gray (locked style). Pass C['acc'] etc for colored."""
        bg  = color if color else C["bg3"]
        fg  = "white" if color else (C["fg3"] if locked else C["fg"])
        b = ctk.CTkButton(self._toolbar, text=label,
                          fg_color=bg, text_color=fg,
                          hover_color=C["bg4"],
                          font=ctk.CTkFont(FF,10),
                          corner_radius=4,
                          height=26, width=0,
                          state="disabled" if locked else "normal",
                          command=cmd if not locked else None)
        b.pack(side="left", padx=2, pady=4)
        return b

    def _tb_semaphore(self, step):
        """Update toolbar buttons like a semaphore: step = 'open'|'ready'|'analyzed'|'exported'"""
        # step=open: Abrir=blue, rest=gray
        # step=ready: Abrir=green-check, Analizar=yellow(pulsing), rest=gray
        # step=analyzing: Analizar=orange(processing)
        # step=analyzed: Analizar=green, Revisar=blue, Exportar=blue
        # step=exported: all green
        if step=="open":
            self._tb_open.configure(fg_color=C["acc"], text_color="white", state="normal")
        elif step=="ready":
            self._tb_open.configure(fg_color=C["grn"], text_color="white")
            if hasattr(self,"_tb_analyze"):
                self._tb_analyze.configure(fg_color=C["yel"], text_color="#1a1a1a",
                                            state="normal", command=self._start_analyze)
            self._lock_btn(self._tb_review); self._lock_btn(self._tb_export)
        elif step=="analyzing":
            if hasattr(self,"_tb_analyze"):
                self._tb_analyze.configure(fg_color=C["org"], text_color="white",
                                            text="Cancelar", command=self._do_cancel)
        elif step=="analyzed":
            self._tb_open.configure(fg_color=C["grn"], text_color="white")
            if hasattr(self,"_tb_analyze"):
                self._tb_analyze.configure(fg_color=C["grn"], text_color="white",
                                            text="Analizar", state="normal",
                                            command=self._start_analyze)
            if hasattr(self,"_tb_review"):
                self._tb_review.configure(fg_color=C["acc"], text_color="white",
                                           state="normal", command=self._open_review)
            if hasattr(self,"_tb_export"):
                self._tb_export.configure(fg_color=C["acc"], text_color="white",
                                           state="normal", command=self._export)
        elif step=="exported":
            for btn in (self._tb_analyze, self._tb_review, self._tb_export):
                if hasattr(self,btn.__class__.__name__): pass
            if hasattr(self,"_tb_export"):
                self._tb_export.configure(fg_color=C["grn"], text_color="white")

    def _tb_sep(self):
        ctk.CTkFrame(self._toolbar, fg_color=C["bg4"], width=1,
                     corner_radius=0).pack(side="left", fill="y", pady=8, padx=3)

    def _unlock_btn(self, btn, color=None):
        if btn is None: return
        btn.configure(state="normal", fg_color=color or C["bg3"],
                      text_color="white" if color else C["fg"])

    def _lock_btn(self, btn):
        if btn is None: return
        btn.configure(state="disabled", fg_color=C["bg3"], text_color=C["fg3"])

    def _update_ffmpeg_badge(self):
        self._ffmpeg_path = find_ffmpeg()
        if self._ffmpeg_path:
            self._ffmpeg_lbl.configure(text="ffmpeg OK", text_color=C["grn"])
        else:
            self._ffmpeg_lbl.configure(text="ffmpeg ? (clic)", text_color=C["yel"])

    # ─────────────────────────────────────────
    #  WELCOME SCREEN
    # ─────────────────────────────────────────
    def _show_welcome(self):
        for w in self._main.winfo_children(): w.destroy()
        self._source_bar.pack_forget()

        frame = ctk.CTkFrame(self._main, fg_color=C["bg1"], corner_radius=0)
        frame.pack(fill="both", expand=True)

        # LEFT panel
        left = ctk.CTkFrame(frame, fg_color=C["bg2"], width=240, corner_radius=0)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="Seleccion de fuente",
                     font=ctk.CTkFont(FF,14,"bold"),
                     text_color=C["fg"]).pack(anchor="w", padx=16, pady=(18,12))

        # SmartShot card
        ss = ctk.CTkFrame(left, fg_color=C["acc"], corner_radius=8)
        ss.pack(fill="x", padx=12, pady=(0,8))
        ctk.CTkLabel(ss, text="SmartShot", font=ctk.CTkFont(FF,12,"bold"),
                     text_color="white").pack(anchor="w", padx=12, pady=(10,2))
        ctk.CTkLabel(ss, text="Analiza y exporta automaticamente.\nSin configurar nada.",
                     font=ctk.CTkFont(FF,10), text_color="#dde8fc",
                     justify="left").pack(anchor="w", padx=12, pady=(0,8))
        ctk.CTkButton(ss, text="Iniciar SmartShot",
                      fg_color="white", text_color=C["acc"],
                      hover_color="#e8f0fd",
                      font=ctk.CTkFont(FF,10,"bold"),
                      corner_radius=6, height=30,
                      command=self._smartshot_from_dialog).pack(padx=12, pady=(0,10), fill="x")

        ctk.CTkFrame(left, fg_color=C["bg4"], height=1, corner_radius=0).pack(fill="x", pady=8)

        for label, desc, cmd in [
            ("Abrir video",   "MP4, MOV, AVI, MKV, MTS", self._browse_file),
            ("Abrir carpeta", "Procesar varios videos",   self._open_queue),
        ]:
            btn = ctk.CTkFrame(left, fg_color=C["bg3"], corner_radius=8, cursor="hand2")
            btn.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(btn, text=label, font=ctk.CTkFont(FF,11,"bold"),
                         text_color=C["fg"]).pack(anchor="w", padx=12, pady=(8,0))
            ctk.CTkLabel(btn, text=desc, font=ctk.CTkFont(FF,9),
                         text_color=C["fg3"]).pack(anchor="w", padx=12, pady=(0,8))
            btn.bind("<Button-1>", lambda e, c=cmd: c())
            for child in btn.winfo_children():
                child.bind("<Button-1>", lambda e, c=cmd: c())

        ctk.CTkFrame(left, fg_color=C["bg4"], height=1, corner_radius=0).pack(fill="x", pady=8)
        ctk.CTkLabel(left, text="Recientes", font=ctk.CTkFont(FF,9,"bold"),
                     text_color=C["fg3"]).pack(anchor="w", padx=16, pady=(0,4))

        recent = load_recent()
        if recent:
            for p in recent[:5]:
                name = Path(p).name
                ctk.CTkButton(left, text=f"  {name}",
                              fg_color="transparent", text_color=C["fg2"],
                              hover_color=C["bg3"],
                              font=ctk.CTkFont(FF,9),
                              anchor="w", height=28,
                              command=lambda path=p: self._set_video(path)).pack(
                              fill="x", padx=8, pady=1)
        else:
            ctk.CTkLabel(left, text="Sin archivos recientes",
                         font=ctk.CTkFont(FF,9), text_color=C["fg3"]).pack(anchor="w", padx=16)

        # Footer links
        foot = ctk.CTkFrame(left, fg_color=C["bg2"], corner_radius=0)
        foot.pack(side="bottom", fill="x", pady=8, padx=12)
        ctk.CTkFrame(left, fg_color=C["bg4"], height=1, corner_radius=0).pack(
            side="bottom", fill="x")
        for lbl, cb in [("gnomalab.es", lambda: webbrowser.open("https://www.gnomalab.es")),
                        ("Preferencias", self._open_prefs)]:
            ctk.CTkButton(foot, text=lbl, fg_color="transparent",
                          text_color=C["acc2"], hover_color=C["bg3"],
                          font=ctk.CTkFont(FF,9), height=24,
                          command=cb).pack(side="left", padx=(0,8))

        # RIGHT drop zone
        right = ctk.CTkFrame(frame, fg_color=C["bg1"], corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        drop_border = ctk.CTkFrame(right, fg_color=C["acc"], corner_radius=12)
        drop_border.pack(fill="both", expand=True, padx=20, pady=20)
        drop_inner = ctk.CTkFrame(drop_border, fg_color=C["bg2"], corner_radius=10)
        drop_inner.pack(fill="both", expand=True, padx=2, pady=2)

        ctk.CTkLabel(drop_inner, text="Arrastra tu video aqui",
                     font=ctk.CTkFont(FF,16,"bold"),
                     text_color=C["fg"]).pack(pady=(60,8))
        ctk.CTkLabel(drop_inner, text="o usa el panel izquierdo para seleccionar",
                     font=ctk.CTkFont(FF,11), text_color=C["fg2"]).pack()

        fmt_row = ctk.CTkFrame(drop_inner, fg_color="transparent", corner_radius=0)
        fmt_row.pack(pady=16)
        for fmt in ["MP4","MOV","AVI","MKV","MTS"]:
            ctk.CTkLabel(fmt_row, text=fmt, fg_color=C["bg3"],
                         text_color=C["fg2"],
                         font=ctk.CTkFont(FF,10),
                         corner_radius=4,
                         width=50, height=26).pack(side="left", padx=4)

        ctk.CTkButton(drop_inner, text="Seleccionar archivo",
                      fg_color=C["acc"], text_color="white",
                      hover_color=C["acc2"],
                      font=ctk.CTkFont(FF,11,"bold"),
                      corner_radius=8, height=36,
                      command=self._browse_file).pack(pady=(8,0))

        if HAS_DND:
            drop_inner.drop_target_register(DND_FILES)
            drop_inner.dnd_bind("<<Drop>>", self._on_drop)

    # ─────────────────────────────────────────
    #  EDITOR SCREEN
    # ─────────────────────────────────────────
    def _show_editor(self):
        for w in self._main.winfo_children(): w.destroy()
        self._source_bar.pack(fill="x", after=self._toolbar)
        self._traces_ok = False

        ed = ctk.CTkFrame(self._main, fg_color=C["bg1"], corner_radius=0)
        ed.pack(fill="both", expand=True)

        # ── LEFT PANEL ──
        left = ctk.CTkScrollableFrame(ed, fg_color=C["bg2"], width=260, corner_radius=0,
                                       scrollbar_button_color=C["bg4"],
                                       scrollbar_button_hover_color=C["acc"])
        left.pack(side="left", fill="y")

        info = self._info or {}
        dur  = max(info.get("duration",1), 1)
        self._t_in  = 0.0
        self._t_out = dur

        # Mode section
        self._section_hdr(left, "MODO DE ANALISIS")
        mode_row = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0)
        mode_row.pack(fill="x", padx=8, pady=4)
        self._mode_var = tk.StringVar(value=self._cfg.get("default_mode","auto"))
        self._mode_auto_btn = ctk.CTkRadioButton(mode_row, text="Automatico",
                                                   variable=self._mode_var, value="auto",
                                                   command=self._on_mode_change,
                                                   font=ctk.CTkFont(FF,10),
                                                   text_color=C["fg"],
                                                   fg_color=C["acc"])
        self._mode_auto_btn.pack(side="left", padx=(0,12))
        self._mode_man_btn = ctk.CTkRadioButton(mode_row, text="Manual",
                                                  variable=self._mode_var, value="manual",
                                                  command=self._on_mode_change,
                                                  font=ctk.CTkFont(FF,10),
                                                  text_color=C["fg"],
                                                  fg_color=C["acc"])
        self._mode_man_btn.pack(side="left")

        # Manual count slider — shown here (next to auto params)
        self._manual_count = tk.IntVar(value=200)
        self._manual_frame = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0)
        man_row = ctk.CTkFrame(self._manual_frame, fg_color="transparent", corner_radius=0)
        man_row.pack(fill="x", padx=8, pady=(0,2))
        ctk.CTkLabel(man_row, text="Frames a seleccionar",
                     font=ctk.CTkFont(FF,9), text_color=C["fg2"], anchor="w").pack(side="left", fill="x", expand=True)
        self._man_lbl = ctk.CTkLabel(man_row, text="200", width=56,
                                      font=ctk.CTkFont(FF,9,"bold"),
                                      fg_color=C["bg3"], text_color=C["fg"], corner_radius=4)
        self._man_lbl.pack(side="right")
        ctk.CTkSlider(self._manual_frame, from_=10, to=1000,
                      variable=self._manual_count,
                      fg_color=C["bg0"], progress_color=C["acc"],
                      button_color=C["acc2"], button_hover_color="white",
                      command=lambda v: self._man_lbl.configure(text=str(int(v)))
                      ).pack(fill="x", padx=8, pady=(0,6))
        if self._mode_var.get() != "manual":
            self._manual_frame.pack_forget()

        # Auto params
        self._section_hdr(left, "PARAMETROS DETECCION")
        self._blur_pct   = tk.DoubleVar(value=self._cfg.get("default_blur",30))
        self._sim_thr    = tk.DoubleVar(value=self._cfg.get("default_sim",0.94))
        self._shake_thr  = tk.DoubleVar(value=self._cfg.get("default_shake",35))
        self._max_frames = tk.IntVar(value=self._cfg.get("default_max",300))

        self._blur_lbl   = self._param_slider(left,"Nitidez minima",self._blur_pct,5,70,1,lambda v:f"{int(v)}%")
        self._sim_lbl    = self._param_slider(left,"Anti-duplicados",self._sim_thr,0.80,0.99,0.01,lambda v:f"{v:.2f}")
        self._shake_lbl  = self._param_slider(left,"Anti-shake",self._shake_thr,5,80,5,lambda v:f"{int(v)}px")
        self._maxf_lbl   = self._param_slider(left,"Max. frames",self._max_frames,0,1000,25,
                                               lambda v:"sin lim." if int(v)==0 else str(int(v)))

        # Results
        self._section_hdr(left, "RESULTADO")
        res_grid = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0)
        res_grid.pack(fill="x", padx=8, pady=4)
        res_grid.columnconfigure((0,1,2,3), weight=1)
        self._stat_sel   = self._stat_cell(res_grid, 0, "Selec.",  "—", C["grn"])
        self._stat_blur  = self._stat_cell(res_grid, 1, "Blur",    "—", C["fg3"])
        self._stat_shake = self._stat_cell(res_grid, 2, "Shake",   "—", C["fg3"])
        self._stat_dup   = self._stat_cell(res_grid, 3, "Duplic.", "—", C["fg3"])

        # ── EXPORT OPTIONS (collapsible) ──
        self._adv_open = False
        adv_hdr = ctk.CTkFrame(left, fg_color=C["bg3"], corner_radius=0, height=24)
        adv_hdr.pack(fill="x", pady=(8,0)); adv_hdr.pack_propagate(False)
        ctk.CTkFrame(adv_hdr, fg_color=C["acc"], width=3, corner_radius=0).pack(side="left", fill="y")
        self._adv_arrow = ctk.CTkLabel(adv_hdr, text=">  OPCIONES DE EXPORTACION",
                                        font=ctk.CTkFont(FF,8,"bold"),
                                        text_color=C["fg3"], cursor="hand2")
        self._adv_arrow.pack(side="left", padx=6)

        self._adv_body = ctk.CTkFrame(left, fg_color=C["bg2"], corner_radius=0)

        def _toggle_adv(_=None):
            self._adv_open = not self._adv_open
            if self._adv_open:
                self._adv_body.pack(fill="x")
                self._adv_arrow.configure(text="v  OPCIONES DE EXPORTACION")
            else:
                self._adv_body.pack_forget()
                self._adv_arrow.configure(text=">  OPCIONES DE EXPORTACION")

        adv_hdr.bind("<Button-1>", _toggle_adv)
        self._adv_arrow.bind("<Button-1>", _toggle_adv)

        ab = self._adv_body
        self._limit_size    = tk.StringVar(value=self._cfg.get("default_size","Original"))
        self._custom_w      = tk.StringVar(value="")
        self._custom_h      = tk.StringVar(value="")
        self._fmt           = tk.StringVar(value=self._cfg.get("default_format","jpg"))
        self._jpg_q         = tk.IntVar(value=self._cfg.get("default_quality",95))
        self._write_report  = tk.BooleanVar(value=True)
        self._vertical_mode = tk.BooleanVar(value=False)
        self._custom_out    = tk.StringVar(value=self._cfg.get("default_output",""))
        self._out_mode      = tk.StringVar(value="auto")

        # Resolución — dropdown menu
        res_row = ctk.CTkFrame(ab, fg_color="transparent", corner_radius=0)
        res_row.pack(fill="x", padx=8, pady=(6,3))
        ctk.CTkLabel(res_row, text="Resolucion:", font=ctk.CTkFont(FF,9),
                     text_color=C["fg2"], width=70).pack(side="left")
        ctk.CTkOptionMenu(res_row, variable=self._limit_size,
                          values=["Original","3840 (4K)","2560 (2K)","1920 (Full HD)",
                                  "1280 (HD)","960","720","Custom"],
                          fg_color=C["bg3"], button_color=C["bg4"],
                          button_hover_color=C["acc"], text_color=C["fg"],
                          font=ctk.CTkFont(FF,9), width=130, corner_radius=4,
                          command=lambda v: self._on_size_change(v)).pack(side="left", padx=(4,6))
        # Vertical/Horizontal toggle
        self._orient_btn = ctk.CTkButton(res_row, text="Horizontal",
                                          width=80, height=24,
                                          fg_color=C["bg3"], text_color=C["fg2"],
                                          hover_color=C["bg4"], corner_radius=4,
                                          font=ctk.CTkFont(FF,8),
                                          command=self._toggle_orientation)
        self._orient_btn.pack(side="left")

        # Custom WxH
        self._custom_size_row = ctk.CTkFrame(ab, fg_color="transparent", corner_radius=0)
        csr = self._custom_size_row
        for lbl_t, var in [("W:", self._custom_w), ("H:", self._custom_h)]:
            ctk.CTkLabel(csr, text=lbl_t, font=ctk.CTkFont(FF,9), text_color=C["fg2"]).pack(side="left")
            ctk.CTkEntry(csr, textvariable=var, width=54, height=24,
                         font=ctk.CTkFont(FF,9), fg_color=C["bg0"], text_color=C["fg"],
                         border_color=C["bg4"], corner_radius=4).pack(side="left", padx=(2,6))
        ctk.CTkLabel(csr, text="px", font=ctk.CTkFont(FF,8), text_color=C["fg3"]).pack(side="left")
        # hidden until Custom selected

        # Format
        fmt_row = ctk.CTkFrame(ab, fg_color="transparent", corner_radius=0)
        fmt_row.pack(fill="x", padx=8, pady=(0,3))
        ctk.CTkLabel(fmt_row, text="Formato:", font=ctk.CTkFont(FF,9),
                     text_color=C["fg2"], width=70).pack(side="left")
        for val, lbl in [("jpg","JPG"),("png","PNG")]:
            ctk.CTkRadioButton(fmt_row, text=lbl, variable=self._fmt, value=val,
                               font=ctk.CTkFont(FF,9), text_color=C["fg2"],
                               fg_color=C["acc"], radiobutton_width=14, radiobutton_height=14
                               ).pack(side="left", padx=(0,10))

        # Quality slider
        q_row = ctk.CTkFrame(ab, fg_color="transparent", corner_radius=0)
        q_row.pack(fill="x", padx=8, pady=(0,3))
        ctk.CTkLabel(q_row, text="Calidad JPG:", font=ctk.CTkFont(FF,9),
                     text_color=C["fg2"], width=70).pack(side="left")
        self._q_lbl = ctk.CTkLabel(q_row, text=str(self._jpg_q.get()), width=32,
                                    font=ctk.CTkFont(FF,9,"bold"),
                                    fg_color=C["bg3"], text_color=C["fg"], corner_radius=4)
        self._q_lbl.pack(side="right")
        ctk.CTkSlider(q_row, from_=60, to=100, variable=self._jpg_q,
                      fg_color=C["bg0"], progress_color=C["acc"],
                      button_color=C["acc2"], button_hover_color="white",
                      command=lambda v: self._q_lbl.configure(text=str(int(v)))
                      ).pack(side="left", fill="x", expand=True, padx=(0,6))

        ctk.CTkCheckBox(ab, text="Generar reporte .txt",
                        variable=self._write_report,
                        font=ctk.CTkFont(FF,9), text_color=C["fg2"],
                        fg_color=C["acc"], checkmark_color="white",
                        corner_radius=3).pack(anchor="w", padx=8, pady=(0,4))

        # Output folder selector (inside export options)
        ctk.CTkFrame(ab, fg_color=C["bg4"], height=1, corner_radius=0).pack(fill="x", pady=(0,4))
        ctk.CTkLabel(ab, text="Guardar en:", font=ctk.CTkFont(FF,9,"bold"),
                     text_color=C["fg2"]).pack(anchor="w", padx=8, pady=(0,3))
        out_radio_row = ctk.CTkFrame(ab, fg_color="transparent", corner_radius=0)
        out_radio_row.pack(fill="x", padx=8, pady=(0,3))
        for val, lbl in [("auto","Junto al video"),("custom","Elegir carpeta")]:
            ctk.CTkRadioButton(out_radio_row, text=lbl, variable=self._out_mode, value=val,
                               font=ctk.CTkFont(FF,9), text_color=C["fg2"], fg_color=C["acc"],
                               radiobutton_width=14, radiobutton_height=14,
                               command=self._toggle_out).pack(side="left", padx=(0,10))
        out_path_row = ctk.CTkFrame(ab, fg_color="transparent", corner_radius=0)
        out_path_row.pack(fill="x", padx=8, pady=(0,8))
        self._out_entry = ctk.CTkEntry(out_path_row, textvariable=self._custom_out,
                                        font=ctk.CTkFont("Consolas",8),
                                        fg_color=C["bg0"], text_color=C["fg"],
                                        border_color=C["bg4"], height=26,
                                        state="disabled")
        self._out_entry.pack(side="left", fill="x", expand=True)
        self._out_browse = ctk.CTkButton(out_path_row, text="...", width=28, height=26,
                                          fg_color=C["bg3"], text_color=C["fg"],
                                          hover_color=C["bg4"], corner_radius=4,
                                          state="disabled", command=self._browse_out)
        self._out_browse.pack(side="left", padx=(3,0))

        # (console is placed at the bottom of the right panel)

        # ── RIGHT PANEL ──
        right = ctk.CTkFrame(ed, fg_color=C["bg1"], corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        # Video player
        player_frame = ctk.CTkFrame(right, fg_color="#0a0a0a", corner_radius=0)
        player_frame.pack(fill="both", expand=True)
        if self._player: self._player.release()
        self._player = VideoPlayer(player_frame, on_time_change=self._on_player_time)
        if self._video_path: self._player.load(self._video_path)

        # ── KEYBOARD SHORTCUTS ──
        def _kb(e):
            k = e.keysym.lower()
            if k=="space":         self._toggle_play()
            elif k=="i":           self._mark_in()
            elif k=="o":           self._mark_out()
            elif k=="left":        self._player.seek_frame(-1)
            elif k=="right":       self._player.seek_frame(1)
            elif k=="shift_left" or (e.state&1 and k=="left"):   self._player.seek_frame(-10)
            elif k=="shift_right" or (e.state&1 and k=="right"): self._player.seek_frame(10)
            elif k=="home":        self._player.seek(0)
            elif k=="end":         self._player.seek(self._player.duration-0.01)
            elif k=="return" and self._candidates:  self._start_analyze()
            elif k=="e" and self._selected:         self._export()
        self.bind("<KeyPress>", _kb)
        self.bind("<Shift-Left>",  lambda e: self._player.seek_frame(-10))
        self.bind("<Shift-Right>", lambda e: self._player.seek_frame(10))

        # Transport row 1: playback
        t1 = ctk.CTkFrame(right, fg_color=C["bg3"], corner_radius=0, height=36)
        t1.pack(fill="x")
        t1.pack_propagate(False)

        self._time_var = tk.StringVar(value="0:00 / 0:00")
        ctk.CTkLabel(t1, textvariable=self._time_var,
                     font=ctk.CTkFont("Consolas",9), text_color=C["fg2"],
                     width=120).pack(side="left", padx=8)

        for txt, cmd in [
            ("|<", lambda: self._player.seek(0)),
            ("<<", lambda: self._player.seek_frame(-10)),
            ("<",  lambda: self._player.seek_frame(-1)),
        ]:
            ctk.CTkButton(t1, text=txt, width=30, height=26,
                          fg_color=C["bg4"], text_color=C["fg"],
                          hover_color=C["bg3"], font=ctk.CTkFont("Consolas",9),
                          corner_radius=4,
                          command=cmd).pack(side="left", padx=1, pady=4)

        self._play_btn = ctk.CTkButton(t1, text=" PLAY ", height=26,
                                        fg_color=C["acc"], text_color="white",
                                        hover_color=C["acc2"],
                                        font=ctk.CTkFont(FF,10,"bold"),
                                        corner_radius=6,
                                        command=self._toggle_play)
        self._play_btn.pack(side="left", padx=6, pady=4)

        for txt, cmd in [
            (">",   lambda: self._player.seek_frame(1)),
            (">>",  lambda: self._player.seek_frame(10)),
            (">|",  lambda: self._player.seek(self._player.duration-0.01)),
        ]:
            ctk.CTkButton(t1, text=txt, width=30, height=26,
                          fg_color=C["bg4"], text_color=C["fg"],
                          hover_color=C["bg3"], font=ctk.CTkFont("Consolas",9),
                          corner_radius=4,
                          command=cmd).pack(side="left", padx=1, pady=4)

        # Transport row 2: IN/OUT
        t2 = ctk.CTkFrame(right, fg_color=C["bg0"], corner_radius=0, height=32)
        t2.pack(fill="x")
        t2.pack_propagate(False)

        ctk.CTkButton(t2, text="[ Marcar IN", height=24,
                      fg_color="#1e3a1e", text_color="#7ec87e",
                      hover_color="#2a4a2a",
                      font=ctk.CTkFont(FF,10,"bold"),
                      corner_radius=5,
                      command=self._mark_in).pack(side="left", padx=(6,2), pady=4)
        ctk.CTkButton(t2, text="Marcar OUT ]", height=24,
                      fg_color="#1e3a1e", text_color="#7ec87e",
                      hover_color="#2a4a2a",
                      font=ctk.CTkFont(FF,10,"bold"),
                      corner_radius=5,
                      command=self._mark_out).pack(side="left", padx=(0,8), pady=4)

        self._inout_var = tk.StringVar(value="IN 0:00   OUT 0:00")
        ctk.CTkLabel(t2, textvariable=self._inout_var,
                     font=ctk.CTkFont("Consolas",9), text_color=C["fg2"]).pack(side="left")
        ctk.CTkButton(t2, text="Reset", width=50, height=24,
                      fg_color=C["bg3"], text_color=C["fg3"],
                      hover_color=C["bg4"], font=ctk.CTkFont(FF,8),
                      corner_radius=4,
                      command=self._reset_inout).pack(side="right", padx=6, pady=4)

        # Scrub timeline
        tl_frame = tk.Frame(right, bg=C["bg0"], height=24)
        tl_frame.pack(fill="x")
        self._tl_canvas = tk.Canvas(tl_frame, bg="#141414", height=24,
                                     highlightthickness=0, cursor="hand2")
        self._tl_canvas.pack(fill="both", expand=True, padx=4, pady=2)
        self._tl_dur = dur
        self.after(80, self._draw_timeline)
        self._tl_drag = None
        self._tl_drag_start_x = 0
        self._tl_drag_start_in = 0.0
        self._tl_drag_start_out = dur

        def _tl_time_from_x(x):
            w = self._tl_canvas.winfo_width() or 400
            return max(0.0, min(dur, x/w*dur))

        def _tl_press(e):
            w = self._tl_canvas.winfo_width() or 400
            xin  = int(self._t_in /dur*w)
            xout = int(self._t_out/dur*w)
            xp   = int((self._player.current_time if self._player else 0)/dur*w)
            if abs(e.x-xin)<=10:   self._tl_drag="in"
            elif abs(e.x-xout)<=10: self._tl_drag="out"
            else:
                if self._player: self._player.seek(_tl_time_from_x(e.x))
                self._tl_drag="play"

        def _tl_move(e):
            if not self._tl_drag: return
            t = _tl_time_from_x(e.x)
            if self._tl_drag=="in":
                self._t_in = max(0.0, min(t, self._t_out-1))
                self._update_inout_display()
            elif self._tl_drag=="out":
                self._t_out = min(dur, max(t, self._t_in+1))
                self._update_inout_display()
            elif self._tl_drag=="play":
                if self._player: self._player.seek(t)
            self._draw_timeline()

        def _tl_release(e): self._tl_drag = None

        self._tl_canvas.bind("<ButtonPress-1>",   _tl_press)
        self._tl_canvas.bind("<B1-Motion>",        _tl_move)
        self._tl_canvas.bind("<ButtonRelease-1>",  _tl_release)
        self._tl_canvas.bind("<Configure>",        lambda e: self._draw_timeline())

        # Progress bar
        prog_row = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        prog_row.pack(fill="x", padx=8, pady=(4,2))
        self._progress = ctk.CTkProgressBar(prog_row, fg_color=C["bg0"],
                                             progress_color=C["acc"],
                                             corner_radius=4, height=8)
        self._progress.set(0)
        self._progress.pack(side="left", fill="x", expand=True)
        self._pct_var = tk.StringVar(value="")
        ctk.CTkLabel(prog_row, textvariable=self._pct_var,
                     font=ctk.CTkFont(FF,9,"bold"), text_color=C["acc2"],
                     width=44).pack(side="left", padx=(6,0))

        # Filmstrip
        film_hdr = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        film_hdr.pack(fill="x", padx=8, pady=(4,2))
        ctk.CTkLabel(film_hdr, text="FRAMES SELECCIONADOS",
                     font=ctk.CTkFont(FF,8,"bold"), text_color=C["fg3"]).pack(side="left")
        self._film_count_lbl = ctk.CTkLabel(film_hdr, text="",
                                             font=ctk.CTkFont(FF,8), text_color=C["fg3"])
        self._film_count_lbl.pack(side="left", padx=6)

        film_outer = tk.Frame(right, bg=C["bg0"], height=82)
        film_outer.pack(fill="x", padx=8)
        film_outer.pack_propagate(False)
        self._film_canvas = tk.Canvas(film_outer, bg=C["bg0"],
                                       highlightthickness=0, bd=0)
        fhsb = tk.Scrollbar(film_outer, orient="horizontal",
                             command=self._film_canvas.xview,
                             bg=C["bg3"], troughcolor=C["bg0"],
                             relief="flat", width=6)
        fhsb.pack(side="bottom", fill="x")
        self._film_canvas.configure(xscrollcommand=fhsb.set)
        self._film_canvas.pack(fill="both", expand=True)
        self._film_inner = tk.Frame(self._film_canvas, bg=C["bg0"])
        self._film_canvas.create_window((0,0), window=self._film_inner, anchor="nw")
        self._film_inner.bind("<Configure>",
            lambda e: self._film_canvas.configure(scrollregion=self._film_canvas.bbox("all")))
        tk.Label(self._film_inner, text="Analiza el video para ver los frames",
                 bg=C["bg0"], fg=C["fg3"], font=(FF,9)).pack(pady=22, padx=16)

        # ── CONSOLE — full width, taller now that bottom bar is gone ──
        con_hdr = ctk.CTkFrame(right, fg_color=C["bg0"], corner_radius=0, height=24)
        con_hdr.pack(fill="x"); con_hdr.pack_propagate(False)
        ctk.CTkFrame(con_hdr, fg_color=C["acc"], width=3, corner_radius=0).pack(side="left", fill="y")
        ctk.CTkLabel(con_hdr, text="CONSOLA", font=ctk.CTkFont(FF,9,"bold"),
                     text_color=C["fg3"]).pack(side="left", padx=6)
        ctk.CTkButton(con_hdr, text="Limpiar", width=60, height=18,
                      fg_color=C["bg3"], text_color=C["fg3"], hover_color=C["bg4"],
                      font=ctk.CTkFont(FF,8), corner_radius=3,
                      command=self._console_clear).pack(side="right", padx=(0,4), pady=3)
        ctk.CTkButton(con_hdr, text="Guardar log", width=76, height=18,
                      fg_color=C["bg3"], text_color=C["fg3"], hover_color=C["bg4"],
                      font=ctk.CTkFont(FF,8), corner_radius=3,
                      command=self._console_save).pack(side="right", padx=(0,2), pady=3)
        self._open_folder_btn = ctk.CTkButton(con_hdr, text="Ver carpeta exportada",
                                               width=140, height=18,
                                               fg_color=C["bg3"], text_color=C["fg3"],
                                               hover_color=C["bg4"],
                                               font=ctk.CTkFont(FF,8), corner_radius=3,
                                               state="disabled",
                                               command=self._open_folder)
        self._open_folder_btn.pack(side="right", padx=(0,4), pady=3)

        self._console_text = ctk.CTkTextbox(right, height=110, fg_color=C["bg0"],
                                             text_color=C["fg2"],
                                             font=ctk.CTkFont("Consolas",11),
                                             corner_radius=0, state="disabled")
        self._console_text.pack(fill="x")
        self._console_text._textbox.tag_configure("success", foreground=C["grn"])
        self._console_text._textbox.tag_configure("warning", foreground=C["yel"])
        self._console_text._textbox.tag_configure("error",   foreground=C["red"])
        self._console_text._textbox.tag_configure("ts",      foreground=C["fg3"])

    # ─────────────────────────────────────────
    #  UI HELPERS
    # ─────────────────────────────────────────
    def _section_hdr(self, parent, title):
        f = ctk.CTkFrame(parent, fg_color=C["bg3"], corner_radius=0, height=22)
        f.pack(fill="x", pady=(8,1))
        f.pack_propagate(False)
        ctk.CTkFrame(f, fg_color=C["acc"], width=3, corner_radius=0).pack(side="left", fill="y")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(FF,8,"bold"),
                     text_color=C["fg3"]).pack(side="left", padx=6)

    def _show_analyzing_overlay(self, active=True):
        """Show/hide a pulsing 'Analizando...' overlay on the player canvas."""
        if not hasattr(self,"_player") or not self._player: return
        ca = self._player.canvas
        if not active:
            ca.delete("overlay_bg"); ca.delete("overlay_txt"); return
        def _pulse(i=0):
            if not self._spinner_active: ca.delete("overlay_bg"); ca.delete("overlay_txt"); return
            cw = ca.winfo_width() or 640; ch = ca.winfo_height() or 360
            alpha_colors = ["#1a2a1a","#1e341e","#223c22","#264426"]
            bg = alpha_colors[i % len(alpha_colors)]
            ca.delete("overlay_bg"); ca.delete("overlay_txt")
            ca.create_rectangle(0, ch//2-30, cw, ch//2+30,
                                 fill=bg, outline="", tags="overlay_bg")
            dots = "." * ((i % 3) + 1)
            ca.create_text(cw//2, ch//2,
                           text=f"  Analizando{dots}  ",
                           fill=C["grn"], font=(FF, 16, "bold"),
                           anchor="center", tags="overlay_txt")
            self.after(500, _pulse, i+1)
        _pulse()

    def _toggle_orientation(self, _=None):
        if not hasattr(self,"_vertical_mode"): return
        self._vertical_mode.set(not self._vertical_mode.get())
        label = "Vertical" if self._vertical_mode.get() else "Horizontal"
        if hasattr(self,"_orient_btn"):
            self._orient_btn.configure(
                text=label,
                fg_color=C["acc"] if self._vertical_mode.get() else C["bg3"],
                text_color="white" if self._vertical_mode.get() else C["fg2"])

    def _on_size_change(self, value=None):
        val = self._limit_size.get()
        # Normalize — strip label part like "1920 (Full HD)" → "1920"
        if val and "(" in val:
            val = val.split("(")[0].strip()
            self._limit_size.set(val)
        if hasattr(self,"_custom_size_row"):
            if val == "Custom":
                self._custom_size_row.pack(fill="x", padx=8, pady=(0,4))
            else:
                self._custom_size_row.pack_forget()

    def _param_slider(self, parent, label, var, mn, mx, res, fmt):
        """Slider with editable value field — click value to type directly."""
        row = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=8, pady=1)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(FF,9),
                     text_color=C["fg2"], anchor="w").pack(side="left", fill="x", expand=True)
        lv = tk.StringVar(value=fmt(var.get()))
        # Editable entry — user can type or drag slider
        entry = ctk.CTkEntry(row, textvariable=lv, width=56, height=22,
                             font=ctk.CTkFont(FF,9,"bold"),
                             fg_color=C["bg3"], text_color=C["fg"],
                             border_color=C["bg4"], justify="right", corner_radius=4)
        entry.pack(side="right")

        def _from_entry(*_):
            try:
                raw = lv.get().replace("%","").replace("px","").replace("sinlim.","0").strip()
                v = float(raw)
                v = max(mn, min(mx, v))
                var.set(round(v/res)*res if res < 1 else round(v/res)*res)
                lv.set(fmt(var.get()))
            except Exception: lv.set(fmt(var.get()))

        entry.bind("<Return>", _from_entry)
        entry.bind("<FocusOut>", _from_entry)

        def _cmd(v): lv.set(fmt(float(v)))
        ctk.CTkSlider(parent, from_=mn, to=mx, variable=var,
                      fg_color=C["bg0"], progress_color=C["acc"],
                      button_color=C["acc2"], button_hover_color="white",
                      command=_cmd).pack(fill="x", padx=8, pady=(0,6))
        return lv

    def _stat_cell(self, parent, col, label, val, color):
        f = ctk.CTkFrame(parent, fg_color=C["bg3"], corner_radius=6)
        f.grid(row=0, column=col, padx=2, sticky="ew", ipady=2)
        ctk.CTkFrame(f, fg_color=color if color!=C["fg3"] else C["bg4"],
                     height=2, corner_radius=0).pack(fill="x")
        ctk.CTkLabel(f, text=label, font=ctk.CTkFont(FF,7),
                     text_color=C["fg3"]).pack(pady=(2,0))
        lbl = ctk.CTkLabel(f, text=val, font=ctk.CTkFont(FF,12,"bold"),
                           text_color=color)
        lbl.pack(pady=(0,2))
        return lbl

    def _ctk_row(self, parent, label, widget):
        row = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(FF,9),
                     text_color=C["fg2"], width=80).pack(side="left")
        widget.pack(side="left")

    # ─────────────────────────────────────────
    #  CONSOLE
    # ─────────────────────────────────────────
    def _log(self, msg, level="info"):
        if not hasattr(self, "_console_text"): return
        ts = datetime.now().strftime("%H:%M:%S")
        tb = self._console_text._textbox
        tb.configure(state="normal")
        tb.insert("end", f"[{ts}] ", "ts")
        tag = {"success":"success","warning":"warning","error":"error"}.get(level,"")
        tb.insert("end", msg+"\n", tag if tag else ())
        tb.see("end")
        tb.configure(state="disabled")
        # Auto-open on error: scroll to bottom
        if level == "error":
            try: self._console_text.configure(height=120)
            except Exception: pass

    def _console_clear(self):
        if hasattr(self,"_console_text"):
            self._console_text.configure(state="normal")
            self._console_text.delete("0.0","end")
            self._console_text.configure(state="disabled")

    def _console_save(self):
        if not hasattr(self,"_console_text"): return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text","*.txt")],
            initialfile=f"topshot_log_{datetime.now():%Y%m%d_%H%M%S}.txt")
        if path:
            try:
                with open(path,"w",encoding="utf-8") as f:
                    f.write(self._console_text.get("0.0","end"))
                self._log("Log guardado.","success")
            except Exception as e:
                self._log(f"Error: {e}","error")

    # ─────────────────────────────────────────
    #  TIMELINE
    # ─────────────────────────────────────────
    def _draw_timeline(self):
        if not hasattr(self,"_tl_canvas"): return
        ca = self._tl_canvas
        w  = ca.winfo_width() or 400; h = 24
        dur = getattr(self,"_tl_dur",1) or 1
        tin   = self._t_in
        tout  = self._t_out
        tplay = self._player.current_time if (self._player and self._player._cap) else 0

        x1 = max(0, int(tin/dur*w))
        x2 = min(w, int(tout/dur*w))
        xp = max(0, min(w, int(tplay/dur*w)))

        ca.delete("all")
        ca.create_rectangle(0,9,w,15, fill=C["bg3"],outline="")
        ca.create_rectangle(x1,9,x2,15, fill=C["acc"],outline="")
        ca.create_rectangle(x1-5,3,x1+5,h-3, fill=C["acc"],outline="")
        ca.create_text(x1,2, text="IN",  font=("Segoe UI",6), fill=C["acc2"], anchor="n")
        ca.create_rectangle(x2-5,3,x2+5,h-3, fill=C["acc"],outline="")
        ca.create_text(x2,2, text="OUT", font=("Segoe UI",6), fill=C["acc2"], anchor="n")
        ca.create_line(xp,2,xp,h-2, fill="white", width=2)

    # ─────────────────────────────────────────
    #  PLAYER CONTROLS
    # ─────────────────────────────────────────
    def _on_player_time(self, t):
        if not hasattr(self,"_time_var"): return
        dur = self._player.duration
        self._time_var.set(f"{int(t//60)}:{int(t%60):02d} / {int(dur//60)}:{int(dur%60):02d}")
        if hasattr(self,"_play_btn"):
            self._play_btn.configure(text=" PAUSE " if self._player._playing else " PLAY ")
        self._draw_timeline()

    def _toggle_play(self):
        if not self._player: return
        self._player.toggle()
        if hasattr(self,"_play_btn"):
            self._play_btn.configure(text=" PAUSE " if self._player._playing else " PLAY ")

    def _mark_in(self):
        if not self._player: return
        t = self._player.current_time
        if t >= self._t_out: t = 0.0
        self._t_in = round(t, 2)
        self._update_inout_display(); self._draw_timeline()
        if self._candidates: self.after(50, self._run_selection)

    def _mark_out(self):
        if not self._player: return
        t = self._player.current_time
        if t <= self._t_in: t = self._player.duration
        self._t_out = round(t, 2)
        self._update_inout_display(); self._draw_timeline()
        if self._candidates: self.after(50, self._run_selection)

    def _reset_inout(self):
        dur = (self._player.duration if self._player else 0) or (self._info or {}).get("duration",0)
        self._t_in = 0.0; self._t_out = dur
        self._update_inout_display(); self._draw_timeline()
        if self._candidates: self.after(50, self._run_selection)

    def _update_inout_display(self):
        if not hasattr(self,"_inout_var"): return
        def fmt(t): return f"{int(t//60)}:{int(t%60):02d}"
        self._inout_var.set(f"IN {fmt(self._t_in)}   OUT {fmt(self._t_out)}")

    def _get_inout(self):
        dur = (self._info or {}).get("duration",0) or 9999
        tin  = max(0.0, min(self._t_in,  dur-1))
        tout = max(tin+1, min(self._t_out, dur))
        return tin, tout

    def _set_state(self, state):
        colors = {"idle":C["fg3"],"ready":C["acc2"],"analyzing":C["yel"],
                  "done":C["grn"],"exporting":C["org"],"exported":C["grn"]}
        dot_txt = {"analyzing":"*","exporting":"*"}.get(state,"o")
        color = colors.get(state, C["fg3"])
        if hasattr(self,"_status_dot"):
            self._status_dot.configure(text=dot_txt, text_color=color)
        # Flash the status bar bg yellow while processing
        if hasattr(self,"_statusbar"):
            bar_color = C["bg0"] if state not in ("analyzing","exporting") else C["bg0"]
            self._statusbar.configure(fg_color=bar_color)
        if state in ("analyzing","exporting"):
            self._start_spinner(state)
            self._flash_status_bar(state)
        else:
            self._stop_spinner()
            if hasattr(self,"_statusbar"):
                self._statusbar.configure(fg_color=C["bg0"])

    def _flash_status_bar(self, state):
        """Pulse the status dot yellow while processing."""
        colors = [C["yel"], C["fg3"]] if state=="analyzing" else [C["org"], C["fg3"]]
        def pulse(i=0):
            if not self._spinner_active: return
            if hasattr(self,"_status_dot"):
                self._status_dot.configure(text_color=colors[i%2])
            self.after(600, pulse, i+1)
        pulse()

    def _start_spinner(self, state="analyzing"):
        self._spinner_active = True
        frames = ["Analizando .","Analizando ..","Analizando ..."]
        if state=="exporting": frames = ["Exportando .","Exportando ..","Exportando ..."]
        def tick(i=0):
            if not self._spinner_active: return
            if hasattr(self,"_spinner_lbl"): self._spinner_lbl.configure(text=frames[i%3])
            self.after(500, tick, i+1)
        tick()

    def _stop_spinner(self):
        self._spinner_active = False
        if hasattr(self,"_spinner_lbl"): self._spinner_lbl.configure(text="")

    def _flash_analyze_btn(self):
        if not hasattr(self,"_tb_analyze"): return
        seq = [C["acc2"], C["acc"]] * 3
        def step(i=0):
            if i >= len(seq): return
            try: self._tb_analyze.configure(fg_color=seq[i])
            except Exception: pass
            self.after(220, step, i+1)
        self.after(300, step)

    # ─────────────────────────────────────────
    #  FILMSTRIP
    # ─────────────────────────────────────────
    def _clear_filmstrip(self):
        if not hasattr(self,"_film_inner"): return
        for w in self._film_inner.winfo_children(): w.destroy()
        self._thumb_imgs.clear()
        if hasattr(self,"_film_count_lbl"): self._film_count_lbl.configure(text="")
        tk.Label(self._film_inner, text="Analiza el video para ver los frames",
                 bg=C["bg0"], fg=C["fg3"], font=(FF,9)).pack(pady=22, padx=16)

    def _build_filmstrip(self, selected):
        if not hasattr(self,"_film_inner"): return
        for w in self._film_inner.winfo_children(): w.destroy()
        self._thumb_imgs.clear()
        active = [c for c in selected if not c.get("excluded")]
        if not active:
            tk.Label(self._film_inner, text="Sin frames", bg=C["bg0"], fg=C["fg3"],
                     font=(FF,9)).pack(pady=22); return
        MAX = 80; shown = active[:MAX]
        self._film_count_lbl.configure(text=f"{len(active)} frames"+(" ..." if len(active)>MAX else ""))
        TW, TH = 90, 50
        for i, c in enumerate(shown):
            cell = tk.Frame(self._film_inner, bg=C["bg3"], cursor="hand2")
            cell.pack(side="left", padx=2, pady=3)
            cell.bind("<Button-1>", lambda e, idx=i: self._show_preview_frame(idx))
            cell.bind("<Delete>", lambda e, c=c: self._exclude_frame(c))
            if HAS_PIL and c.get("frame") is not None:
                rgb = cv2.cvtColor(c["frame"], cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb); img.thumbnail((TW,TH), Image.LANCZOS)
                pad = Image.new("RGB",(TW,TH),(30,30,30))
                pad.paste(img,((TW-img.width)//2,(TH-img.height)//2))
                ph = ImageTk.PhotoImage(pad); self._thumb_imgs.append(ph)
                lbl = tk.Label(cell, image=ph, bg=C["bg3"], relief="flat", bd=0)
                lbl.pack()
                lbl.bind("<Button-1>", lambda e, idx=i: self._show_preview_frame(idx))
                lbl.bind("<Delete>", lambda e, c=c: self._exclude_frame(c))
            else:
                tk.Label(cell, text=f"#{i+1}", bg=C["bg3"], fg=C["fg2"],
                         font=(FF,9), width=10, height=3).pack()
            bot = tk.Frame(cell, bg=C["bg3"]); bot.pack(fill="x")
            tk.Label(bot, text=f"{c['timestamp']:.1f}s", bg=C["bg3"],
                     fg=C["fg3"], font=("Segoe UI",7)).pack(side="left", padx=2)
            del_btn = tk.Button(bot, text="DEL", bg="#5a1a1a", fg="#ff6b6b",
                                 font=("Segoe UI",7,"bold"), relief="flat",
                                 padx=3, pady=0, cursor="hand2",
                                 activebackground="#7a2a2a", activeforeground="white",
                                 command=lambda c=c: self._exclude_frame(c))
            del_btn.pack(side="right", padx=1)

    def _exclude_frame(self, c):
        c["excluded"] = True
        n = len([x for x in self._selected if not x.get("excluded")])
        if hasattr(self,"_stat_sel"): self._stat_sel.configure(text=str(n))
        self._build_filmstrip(self._selected)

    def _show_preview_frame(self, idx):
        if not self._selected: return
        active = [c for c in self._selected if not c.get("excluded")]
        if not active or idx >= len(active): return
        self._preview_idx = idx; c = active[idx]
        if c.get("frame") is None:
            self._load_preview_frames_bg(); return
        if not HAS_PIL or not self._player: return
        try:
            rgb = cv2.cvtColor(c["frame"], cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
        except Exception as e:
            self._log(f"Preview error: {e}","error"); return
        ca = self._player.canvas
        ca.update_idletasks()
        cw = ca.winfo_width() or 640; ch = ca.winfo_height() or 400
        img.thumbnail((cw,ch), Image.LANCZOS)
        ph = ImageTk.PhotoImage(img)
        self._preview_photos = [ph]
        ca.delete("all")
        ca.create_image(cw//2, ch//2, image=ph, anchor="center")
        bn = min(100, int(c.get("blur",0)/3))
        ca.create_rectangle(0,ch-22,cw,ch, fill="#1a1a1a", outline="")
        ca.create_text(cw//2, ch-11,
            text=f"  Frame {idx+1}/{len(active)}  t={c['timestamp']:.2f}s  nitidez {bn}%",
            fill="white", font=("Segoe UI",8), anchor="center")
        ca.create_text(24, ch//2, text="<", fill="white",
                       font=("Segoe UI",18,"bold"), anchor="center", tags="nav_prev")
        ca.create_text(cw-24, ch//2, text=">", fill="white",
                       font=("Segoe UI",18,"bold"), anchor="center", tags="nav_next")
        ca.tag_bind("nav_prev","<Button-1>", lambda e: self._nav_preview(-1))
        ca.tag_bind("nav_next","<Button-1>", lambda e: self._nav_preview(1))

    def _nav_preview(self, d):
        if not self._selected: return
        active = [c for c in self._selected if not c.get("excluded")]
        if not active: return
        self._preview_idx = max(0, min(len(active)-1, self._preview_idx+d))
        self._show_preview_frame(self._preview_idx)

    def _load_preview_frames_bg(self):
        sel = [c for c in (self._selected or []) if c.get("frame") is None][:80]
        if not sel: return
        vp = sel[0].get("video_path","")
        if not vp or not os.path.isfile(vp): return
        def run():
            try:
                cap = cv2.VideoCapture(vp)
                if not cap.isOpened(): return
                for c in sel:
                    if self._cancel_flag: break
                    cap.set(cv2.CAP_PROP_POS_FRAMES, c["frame_idx"])
                    ret, frame = cap.read()
                    if ret: c["frame"] = frame
                cap.release()
                def on_loaded():
                    self._build_filmstrip(self._selected)
                    active = [c for c in self._selected if not c.get("excluded")]
                    if active and active[0].get("frame") is not None:
                        self.after(100, self._show_preview_frame, 0)
                self.after(0, on_loaded)
            except Exception as e:
                self.after(0, self._log, f"Preview load: {e}", "warning")
        threading.Thread(target=run, daemon=True).start()

    # ─────────────────────────────────────────
    #  EVENTS
    # ─────────────────────────────────────────
    def _on_drop(self, e):
        path = e.data.strip().strip("{}").strip('"').strip("'")
        self._set_video(path)

    def _on_drop_canvas(self, e):
        self._on_drop(e)

    def _browse_file(self, _=None):
        p = filedialog.askopenfilename(
            filetypes=[("Videos","*.mp4 *.mov *.avi *.mkv *.mts *.m4v *.MP4 *.MOV"),("Todos","*.*")])
        if p: self._set_video(p)

    def _browse_out(self):
        d = filedialog.askdirectory()
        if d: self._custom_out.set(d)

    def _toggle_out(self):
        c = self._out_mode.get()=="custom"
        if hasattr(self,"_out_entry"):
            self._out_entry.configure(state="normal" if c else "disabled")
        if hasattr(self,"_out_browse"):
            self._out_browse.configure(state="normal" if c else "disabled")

    def _on_mode_change(self):
        if not hasattr(self,"_manual_frame"): return
        if self._mode_var.get()=="manual":
            self._manual_frame.pack(fill="x")
        else:
            self._manual_frame.pack_forget()
        if self._candidates: self._run_selection()

    def _set_video(self, path):
        path = path.strip().strip('"').strip("'")
        if not os.path.isfile(path):
            messagebox.showerror("Error", f"Archivo no encontrado:\n{path}"); return
        same = (self._video_path == path) and bool(self._candidates)
        self._video_path = path
        fps, total, w, h = _probe_video(path); dur = total/fps if fps > 0 else 0
        self._info = {"fps":fps,"total_frames":total,"width":w,"height":h,
                      "duration":dur,"video_path":path,"ffmpeg":bool(self._ffmpeg_path),
                      "t_in":0,"t_out":dur}
        name = Path(path).name
        add_recent(path)
        if not same:
            self._candidates = None
        self._selected = []
        self._show_editor()
        self._source_lbl.configure(
            text=f"  {name}   {w}x{h}  |  {fps:.2f}fps  |  {dur:.1f}s")
        self._reset_stats()
        if not same: self._clear_filmstrip()
        self._unlock_btn(self._tb_review); self._unlock_btn(self._tb_export)  # keep locked via state
        # Explicitly restore Analizar button with correct command (was None when locked at start)
        if hasattr(self,"_tb_analyze"):
            self._tb_analyze.configure(state="normal", fg_color=C["acc"],
                                        text_color="white", command=self._start_analyze)
        if hasattr(self,"_review_btn_w"):
            self._review_btn_w.configure(state="disabled", fg_color="#1e2a3e", text_color=C["fg3"])
        if hasattr(self,"_export_btn_w"):
            self._export_btn_w.configure(state="disabled", fg_color="#1e3a1e", text_color=C["fg3"])
        self._log(f"Video: {name}  {w}x{h} | {fps:.1f}fps | {dur:.1f}s")
        self._status_var.set("Marca IN/OUT si necesitas, luego pulsa  Analizar")
        self._set_state("ready")
        self._tb_semaphore("ready")
        self._flash_analyze_btn()
        # Update IN/OUT
        self._t_in = 0.0; self._t_out = dur
        self._update_inout_display()

    def _reset_stats(self):
        for attr in ("_stat_sel","_stat_blur","_stat_shake","_stat_dup"):
            if hasattr(self, attr): getattr(self, attr).configure(text="—")
        if hasattr(self,"_progress"): self._progress.set(0)
        if hasattr(self,"_pct_var"): self._pct_var.set("")

    # ─────────────────────────────────────────
    #  ANALYZE
    # ─────────────────────────────────────────
    def _cancel_btn_toolbar(self):
        self._tb_semaphore("analyzing")

    def _restore_analyze_btn(self):
        if not hasattr(self,"_tb_analyze"): return
        self._tb_analyze.configure(text="Analizar", fg_color=C["grn"],
                                    text_color="white", state="normal",
                                    command=self._start_analyze)

    def _start_analyze(self, smartshot=False):
        if not self._video_path:
            messagebox.showwarning("","Primero carga un video."); return
        if self._running: return
        if not hasattr(self,"_tb_analyze"): return
        self._cancel_flag = False; self._running = True
        self._candidates = None; self._selected = []
        self._traces_ok = False
        self._reset_stats(); self._clear_filmstrip()
        self._lock_btn(self._tb_analyze)
        self._lock_btn(self._tb_review); self._lock_btn(self._tb_export)
        if hasattr(self,"_review_btn_w"):
            self._review_btn_w.configure(state="disabled", text_color=C["fg3"])
        if hasattr(self,"_export_btn_w"):
            self._export_btn_w.configure(state="disabled", text_color=C["fg3"])
        self._cancel_btn_toolbar()
        if hasattr(self,"_progress"): self._progress.set(0)
        self._set_state("analyzing")
        self._show_analyzing_overlay(True)
        tin, tout = self._get_inout()
        self._log(f"Analizando zona {tin:.1f}s -> {tout:.1f}s")
        ares = self._cfg.get("analysis_res", 320)

        def pcb(p):
            self.after(0, lambda x=p: [
                self._progress.set(x/100) if hasattr(self,"_progress") else None,
                self._pct_var.set(f"{int(x)}%") if hasattr(self,"_pct_var") else None,
                self._status_var.set(f"Analizando... {int(x)}%")])
        def lcb(m): self.after(0, lambda msg=m: self._log(msg))
        def run():
            try:
                cands, info = analyze_video(self._video_path, tin, tout, ares,
                                             pcb, lcb, lambda: self._cancel_flag)
                self.after(0, self._analyze_done, cands, info, smartshot)
            except Exception as e:
                self.after(0, self._log, f"Error en analisis: {e}", "error")
                self.after(0, self._analyze_done, None, None, False)
        threading.Thread(target=run, daemon=True).start()

    def _analyze_done(self, candidates, info, smartshot=False):
        self._running = False
        self._restore_analyze_btn()
        self._show_analyzing_overlay(False)
        if candidates is None:
            self._status_var.set("Cancelado.")
            self._set_state("idle"); return
        self._candidates = candidates
        if info: self._info.update(info)
        self._run_selection()
        self._tb_semaphore("analyzed")
        if hasattr(self,"_progress"): self._progress.set(1.0)
        if hasattr(self,"_pct_var"): self._pct_var.set("100%")
        self._set_state("done")
        badge = "ffmpeg" if (info or {}).get("ffmpeg") else "OpenCV"
        self._status_var.set(f"Analisis completado [{badge}] — Ajusta parametros o exporta")
        self._play_done()
        if smartshot: self.after(200, self._export, True)

    def _run_selection(self):
        if not self._candidates: return
        try:
            mode = self._mode_var.get() if hasattr(self,"_mode_var") else "auto"
            if mode == "manual":
                count = self._manual_count.get() if hasattr(self,"_manual_count") else 200
                sel = manual_select(self._candidates, count)
                rb=rs=rd=0
                self._log(f"Manual: {len(sel)} frames seleccionados uniformemente.")
            else:
                sel = smart_select(self._candidates,
                                   self._blur_pct.get() if hasattr(self,"_blur_pct") else 30,
                                   self._sim_thr.get()  if hasattr(self,"_sim_thr")  else 0.94,
                                   self._shake_thr.get() if hasattr(self,"_shake_thr") else 35,
                                   self._max_frames.get() if hasattr(self,"_max_frames") else 300)
                rb = sum(1 for c in self._candidates if c.get("reject_reason")=="blur")
                rs = sum(1 for c in self._candidates if c.get("reject_reason")=="shake")
                rd = sum(1 for c in self._candidates if c.get("reject_reason")=="dup")
        except Exception as e:
            self._log(f"Error en seleccion: {e}", "error"); return

        self._selected = sel
        n = len([c for c in sel if not c.get("excluded")])
        if hasattr(self,"_stat_sel"):   self._stat_sel.configure(text=str(n), text_color=C["grn"])
        if hasattr(self,"_stat_blur"):  self._stat_blur.configure(text=str(rb), text_color=C["yel"] if rb else C["fg3"])
        if hasattr(self,"_stat_shake"): self._stat_shake.configure(text=str(rs), text_color=C["yel"] if rs else C["fg3"])
        if hasattr(self,"_stat_dup"):   self._stat_dup.configure(text=str(rd), text_color=C["fg2"] if rd else C["fg3"])
        self._build_filmstrip(sel)

        if n > 0:
            # Toolbar semaphore handles Revisar/Exportar buttons
            self._tb_semaphore("analyzed")
            active = [c for c in sel if not c.get("excluded")]
            if active:
                if active[0].get("frame") is not None:
                    self.after(150, self._show_preview_frame, 0)
                else:
                    self._load_preview_frames_bg()
        else:
            self._lock_btn(self._tb_review); self._lock_btn(self._tb_export)
            self._log("Sin frames seleccionados. Ajusta los parametros.", "warning")

        if not self._traces_ok:
            for v in (self._blur_pct, self._sim_thr, self._shake_thr,
                      self._max_frames, self._manual_count):
                v.trace_add("write", lambda *_: self._run_selection())
            self._traces_ok = True

    # ─────────────────────────────────────────
    #  REVIEW WINDOW
    # ─────────────────────────────────────────
    def _open_review(self):
        if not self._selected: return
        active = [c for c in self._selected if not c.get("excluded")]
        if not active: return
        win = ctk.CTkToplevel(self)
        win.title("Revisar frames seleccionados")
        win.geometry("1000x600")
        win.configure(fg_color=C["bg1"])
        win.grab_set()

        hdr = ctk.CTkFrame(win, fg_color=C["acc"], corner_radius=0, height=44)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  Revisar frames seleccionados",
                     font=ctk.CTkFont(FF,12,"bold"), text_color="white").pack(side="left", padx=12)
        ctk.CTkButton(hdr, text="Confirmar seleccion", height=30,
                      fg_color="#1e3a1e", text_color=C["grn"],
                      hover_color="#2a4a2a",
                      font=ctk.CTkFont(FF,10,"bold"), corner_radius=6,
                      command=lambda: [self._confirm_review(items,win)]).pack(side="right", padx=10, pady=6)
        ctk.CTkButton(hdr, text="Cerrar", height=30, width=80,
                      fg_color=C["bg3"], text_color=C["fg"],
                      hover_color=C["bg4"], corner_radius=6,
                      command=win.destroy).pack(side="right", pady=6)

        items = [dict(c) for c in active]
        scroll = ctk.CTkScrollableFrame(win, fg_color=C["bg1"], corner_radius=0,
                                         scrollbar_button_color=C["bg4"])
        scroll.pack(fill="both", expand=True)

        # Grid
        COLS = 5; TW = 180; TH = 101
        cells = []
        for i, c in enumerate(items):
            row, col = divmod(i, COLS)
            cell = ctk.CTkFrame(scroll, fg_color=C["bg2"], corner_radius=8)
            cell.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            scroll.columnconfigure(col, weight=1)
            cells.append(cell)
            excl = c.get("excluded", False)

            if HAS_PIL and c.get("frame") is not None:
                try:
                    rgb = cv2.cvtColor(c["frame"], cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(rgb); img.thumbnail((TW,TH), Image.LANCZOS)
                    pad = Image.new("RGB",(TW,TH),(30,30,30))
                    pad.paste(img,((TW-img.width)//2,(TH-img.height)//2))
                    ph = ImageTk.PhotoImage(pad)
                    lbl = tk.Label(cell._canvas, image=ph, bg=C["bg2"], relief="flat")
                    lbl.image = ph
                    lbl.pack(padx=4, pady=(4,0))
                except Exception:
                    ctk.CTkLabel(cell, text=f"#{i+1}", font=ctk.CTkFont(FF,10),
                                 text_color=C["fg2"]).pack(pady=20)
            else:
                ctk.CTkLabel(cell, text=f"#{i+1}", font=ctk.CTkFont(FF,10),
                             text_color=C["fg2"]).pack(pady=20)

            info_row = ctk.CTkFrame(cell, fg_color="transparent", corner_radius=0)
            info_row.pack(fill="x", padx=4, pady=2)
            bn = min(100, int(c.get("blur",0)/3))
            bc = C["grn"] if bn>60 else C["yel"] if bn>30 else C["red"]
            ctk.CTkLabel(info_row, text=f"t={c['timestamp']:.1f}s",
                         font=ctk.CTkFont(FF,8), text_color=C["fg2"]).pack(side="left")
            ctk.CTkLabel(info_row, text=f"{bn}%",
                         font=ctk.CTkFont(FF,8,"bold"), text_color=bc).pack(side="left", padx=4)

            def _toggle(idx=i, c=c, cell=cell):
                c["excluded"] = not c.get("excluded",False)
                cell.configure(fg_color="#3a1a1a" if c["excluded"] else C["bg2"])
            ctk.CTkButton(cell, text="Excluir" if not excl else "Incluir",
                          height=22, font=ctk.CTkFont(FF,8),
                          fg_color="#5a1a1a" if not excl else C["bg3"],
                          text_color="#ff6b6b" if not excl else C["fg2"],
                          hover_color="#7a2a2a",
                          corner_radius=4,
                          command=_toggle).pack(padx=4, pady=(0,4), fill="x")

        win.protocol("WM_DELETE_WINDOW", win.destroy)

    def _confirm_review(self, items, win):
        for c in self._selected:
            for item in items:
                if item["timestamp"] == c["timestamp"]:
                    c["excluded"] = item.get("excluded", False)
        n = len([c for c in self._selected if not c.get("excluded")])
        if hasattr(self,"_stat_sel"): self._stat_sel.configure(text=str(n))
        self._build_filmstrip(self._selected)
        self._log(f"Revision: {n} frames confirmados.", "success")
        win.destroy()

    # ─────────────────────────────────────────
    #  EXPORT
    # ─────────────────────────────────────────
    def _export(self, smartshot=False):
        if not self._selected:
            messagebox.showwarning("","No hay frames seleccionados."); return
        if self._running: return
        video = self._video_path
        if self._out_mode.get()=="auto":
            out_dir = str(Path(video).parent / (Path(video).stem+"_topshot"))
        else:
            out_dir = self._custom_out.get().strip()
            if not out_dir: messagebox.showwarning("","Elige una carpeta de salida."); return
        self._last_out = out_dir; os.makedirs(out_dir, exist_ok=True)
        self._cancel_flag = False; self._running = True
        if hasattr(self,"_export_btn_w"): self._export_btn_w.configure(state="disabled")
        self._cancel_btn_toolbar()
        if hasattr(self,"_progress"): self._progress.set(0)
        self._set_state("exporting")
        active = [c for c in self._selected if not c.get("excluded")]
        self._log(f"Exportando {len(active)} frames -> {out_dir}")

        ext = "jpg" if self._fmt.get()=="jpg" else "png"
        enc = [cv2.IMWRITE_JPEG_QUALITY, self._jpg_q.get()] if ext=="jpg" else [cv2.IMWRITE_PNG_COMPRESSION,3]
        lstr = self._limit_size.get()
        maxdim = 0 if lstr=="Original" else (int(lstr) if lstr.isdigit() else 0)
        sel  = list(active); info = self._info or {}
        wrep = self._write_report.get(); _ss = smartshot

        def resize(fr):
            if maxdim==0: return fr
            h,w=fr.shape[:2]
            if max(h,w)<=maxdim: return fr
            s=maxdim/max(h,w)
            return cv2.resize(fr,(int(w*s),int(h*s)),interpolation=cv2.INTER_AREA)

        def run():
            try:
                if any(c.get("frame") is None for c in sel):
                    self.after(0, lambda: self._status_var.set("Cargando frames a resolucion completa..."))
                    def rp(p): self.after(0, lambda x=p: [
                        self._progress.set(x/100) if hasattr(self,"_progress") else None,
                        self._pct_var.set(f"{int(x)}%") if hasattr(self,"_pct_var") else None])
                    ok = _reload_fullres(self._candidates, info.get("fps",25.0), rp,
                                         lambda m: self.after(0, lambda msg=m: self._log(msg)),
                                         lambda: self._cancel_flag)
                    if not ok:
                        self.after(0,self._log,"Error cargando frames.","error")
                        self.after(0,self._export_done,0,out_dir,_ss); return
                saved=0; fnames=[]
                for i,c in enumerate(sel):
                    if self._cancel_flag: break
                    if c.get("frame") is None: continue
                    ts=c["timestamp"]; fn=f"frame_{i:05d}_t{ts:.2f}s.{ext}"
                    try:
                        if cv2.imwrite(os.path.join(out_dir,fn), resize(c["frame"]), enc):
                            saved+=1; fnames.append((fn,ts))
                    except Exception as we:
                        self.after(0,self._log,f"Frame {i}: {we}","warning")
                    pct = 80+int((i+1)/len(sel)*18)
                    self.after(0, lambda p=pct: [
                        self._progress.set(p/100) if hasattr(self,"_progress") else None,
                        self._pct_var.set(f"{p}%") if hasattr(self,"_pct_var") else None,
                        self._status_var.set(f"Exportando... {p}%")])
                if wrep and fnames:
                    try:
                        with open(os.path.join(out_dir,"_topshot_report.txt"),"w",encoding="utf-8") as f:
                            f.write(f"TopShot Extractor v{VERSION}\n"+"="*40+"\n")
                            f.write(f"Fecha: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                            f.write(f"Video: {info.get('video_path','?')}\n")
                            f.write(f"Exportados: {saved}\n"+"="*40+"\n")
                            for fn,ts in fnames: f.write(f"  {fn}  t={ts:.3f}s\n")
                    except Exception: pass
                self.after(0, self._export_done, saved, out_dir, _ss)
            except Exception as e:
                self.after(0,self._log,f"Error exportacion: {e}","error")
                self.after(0,self._export_done,0,out_dir,_ss)
        threading.Thread(target=run, daemon=True).start()

    def _export_done(self, saved, out_dir, smartshot=False):
        self._running = False
        self._restore_analyze_btn()
        self._tb_semaphore("exported")
        if hasattr(self,"_progress"): self._progress.set(1.0)
        if hasattr(self,"_pct_var"): self._pct_var.set("100%")
        self._set_state("exported")
        self._status_var.set(f"{saved} frames exportados correctamente")
        self._log(f"{saved} frames guardados en: {out_dir}", "success")
        self._play_done()
        if hasattr(self,"_open_folder_btn"):
            self._open_folder_btn.configure(state="normal", text_color=C["grn"])
        if smartshot:
            self._show_smartshot_summary(saved, out_dir)

    def _show_smartshot_summary(self, saved, out_dir):
        d = ctk.CTkToplevel(self)
        d.title("SmartShot completado"); d.geometry("400x200")
        d.configure(fg_color=C["bg2"]); d.grab_set()
        hdr = ctk.CTkFrame(d, fg_color=C["grn"], corner_radius=0, height=40)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  SmartShot completado",
                     font=ctk.CTkFont(FF,12,"bold"), text_color="#16161f").pack(side="left", padx=12)
        body = ctk.CTkFrame(d, fg_color="transparent", corner_radius=0)
        body.pack(fill="both", expand=True, padx=20, pady=16)
        ctk.CTkLabel(body, text=f"{saved} frames exportados correctamente",
                     font=ctk.CTkFont(FF,13,"bold"), text_color=C["grn"]).pack(anchor="w")
        ctk.CTkLabel(body, text=out_dir, font=ctk.CTkFont("Consolas",8),
                     text_color=C["fg2"]).pack(anchor="w", pady=(6,0))
        btns = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        btns.pack(pady=(16,0))
        ctk.CTkButton(btns, text="Ver carpeta",
                      fg_color=C["acc"], text_color="white",
                      hover_color=C["acc2"], corner_radius=6,
                      command=lambda:[self._open_folder(),d.destroy()]).pack(side="left")
        ctk.CTkButton(btns, text="Cerrar",
                      fg_color=C["bg3"], text_color=C["fg"],
                      hover_color=C["bg4"], corner_radius=6,
                      command=d.destroy).pack(side="left", padx=8)

    # ─────────────────────────────────────────
    #  MISC
    # ─────────────────────────────────────────
    def _do_cancel(self):
        self._cancel_flag = True; self._running = False
        self._restore_analyze_btn()
        self._status_var.set("Cancelado.")
        self._log("Cancelado.", "warning")
        self._set_state("idle")

    def _play_done(self):
        notify = self._cfg.get("notify","sound_flash")
        if notify=="silent": return
        try:
            if sys.platform=="win32":
                import winsound; winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else: self.bell()
        except Exception: pass

    def _open_folder(self):
        if self._last_out and os.path.isdir(self._last_out):
            if sys.platform=="win32":    os.startfile(self._last_out)
            elif sys.platform=="darwin": os.system(f'open "{self._last_out}"')
            else:                        os.system(f'xdg-open "{self._last_out}"')

    def _open_prefs(self):
        win = ctk.CTkToplevel(self)
        win.title("Preferencias"); win.geometry("680x540")
        win.configure(fg_color=C["bg1"]); win.grab_set()

        hdr = ctk.CTkFrame(win, fg_color=C["acc"], corner_radius=0, height=40)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  Preferencias — TopShot Extractor",
                     font=ctk.CTkFont(FF,12,"bold"), text_color="white").pack(side="left",padx=12)

        main = ctk.CTkFrame(win, fg_color="transparent", corner_radius=0)
        main.pack(fill="both", expand=True)

        # Sidebar tabs
        sidebar = ctk.CTkFrame(main, fg_color=C["bg2"], width=160, corner_radius=0)
        sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)
        content = ctk.CTkFrame(main, fg_color=C["bg1"], corner_radius=0)
        content.pack(side="left", fill="both", expand=True)

        _tab_btns = {}
        _current_tab = [None]

        def show_tab(key):
            for k,b in _tab_btns.items():
                b.configure(fg_color=C["acc"] if k==key else "transparent",
                            text_color="white" if k==key else C["fg2"])
            for w in content.winfo_children(): w.destroy()
            _current_tab[0] = key
            getattr(self, f"_prefs_{key}")(content, prefs_vars)

        def tab_btn(key, icon, label):
            b = ctk.CTkButton(sidebar, text=f"  {icon}  {label}",
                              fg_color="transparent",
                              text_color=C["fg2"], font=ctk.CTkFont(FF,11),
                              hover_color=C["bg3"], anchor="w", corner_radius=6,
                              height=38, command=lambda k=key: show_tab(k))
            b.pack(fill="x", pady=2, padx=6)
            _tab_btns[key] = b

        tab_btn("interfaz",   "*",  "Interfaz")
        tab_btn("deteccion",  "#",  "Deteccion")
        tab_btn("exportacion","~",  "Exportacion")
        tab_btn("preajustes", "=",  "Preajustes")
        tab_btn("ayuda",      "?",  "Ayuda")

        # Shared prefs vars
        prefs_vars = {
            "lang":    tk.StringVar(value=self._cfg.get("language","es")),
            "theme":   tk.StringVar(value=self._cfg.get("theme","dark")),
            "accent":  tk.StringVar(value=self._cfg.get("accent",C["acc"])),
            "notify":  tk.StringVar(value=self._cfg.get("notify","sound_flash")),
            "mode":    tk.StringVar(value=self._cfg.get("default_mode","auto")),
            "ss_auto": tk.BooleanVar(value=self._cfg.get("smartshot_autostart",False)),
            "ares":    tk.StringVar(value=str(self._cfg.get("analysis_res",320))),
            "blur":    tk.DoubleVar(value=self._cfg.get("default_blur",30)),
            "sim":     tk.DoubleVar(value=self._cfg.get("default_sim",0.94)),
            "shake":   tk.DoubleVar(value=self._cfg.get("default_shake",35)),
            "maxf":    tk.IntVar(value=self._cfg.get("default_max",300)),
            "fmt":     tk.StringVar(value=self._cfg.get("default_format","jpg")),
            "size":    tk.StringVar(value=self._cfg.get("default_size","Original")),
            "quality": tk.IntVar(value=self._cfg.get("default_quality",95)),
            "outdir":  tk.StringVar(value=self._cfg.get("default_output","")),
        }

        show_tab("interfaz")

        # Footer
        foot = ctk.CTkFrame(win, fg_color=C["bg2"], corner_radius=0, height=44)
        foot.pack(fill="x"); foot.pack_propagate(False)

        def _save():
            a = prefs_vars["accent"].get()
            self._cfg.update({
                "language":prefs_vars["lang"].get(),
                "theme":prefs_vars["theme"].get(),
                "accent":a,
                "notify":prefs_vars["notify"].get(),
                "default_mode":prefs_vars["mode"].get(),
                "smartshot_autostart":prefs_vars["ss_auto"].get(),
                "analysis_res":int(prefs_vars["ares"].get()),
                "default_blur":prefs_vars["blur"].get(),
                "default_sim":prefs_vars["sim"].get(),
                "default_shake":prefs_vars["shake"].get(),
                "default_max":prefs_vars["maxf"].get(),
                "default_format":prefs_vars["fmt"].get(),
                "default_size":prefs_vars["size"].get(),
                "default_quality":prefs_vars["quality"].get(),
                "default_output":prefs_vars["outdir"].get(),
            })
            save_config(self._cfg)
            # Apply accent color live
            C["acc"] = a
            C["acc2"] = a
            self._log("Preferencias guardadas.","success")
            win.destroy()

        ctk.CTkButton(foot, text="Guardar", height=30, fg_color=C["acc"],
                      text_color="white", hover_color=C["acc2"], corner_radius=6,
                      font=ctk.CTkFont(FF,10,"bold"), command=_save
                      ).pack(side="right", padx=10, pady=6)
        ctk.CTkButton(foot, text="Cancelar", height=30, fg_color=C["bg3"],
                      text_color=C["fg"], hover_color=C["bg4"], corner_radius=6,
                      font=ctk.CTkFont(FF,10), command=win.destroy
                      ).pack(side="right", pady=6)

    def _prefs_section(self, parent, title):
        f = ctk.CTkFrame(parent, fg_color=C["bg3"], corner_radius=0, height=26)
        f.pack(fill="x", pady=(12,3)); f.pack_propagate(False)
        ctk.CTkFrame(f, fg_color=C["acc"], width=4, corner_radius=0).pack(side="left",fill="y")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(FF,10,"bold"),
                     text_color=C["fg2"]).pack(side="left",padx=8)

    def _prefs_row(self, parent, label, widget_fn):
        r = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        r.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(r, text=label, font=ctk.CTkFont(FF,11),
                     text_color=C["fg"], width=180, anchor="w").pack(side="left")
        widget_fn(r)

    def _prefs_pills(self, parent, options, var):
        for val, lbl in options:
            ctk.CTkRadioButton(parent, text=lbl, variable=var, value=val,
                               font=ctk.CTkFont(FF,11), text_color=C["fg"],
                               fg_color=C["acc"]).pack(side="left", padx=(0,12))

    def _prefs_interfaz(self, parent, v):
        s = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        s.pack(fill="both", expand=True)
        self._prefs_section(s,"IDIOMA / LANGUAGE")
        self._prefs_row(s,"Idioma",lambda p: self._prefs_pills(p,[("es","Espanol"),("en","English")],v["lang"]))
        self._prefs_section(s,"APARIENCIA")
        self._prefs_row(s,"Tema",lambda p: self._prefs_pills(p,[("dark","Oscuro"),("light","Claro")],v["theme"]))
        # Color swatches
        r = ctk.CTkFrame(s, fg_color="transparent", corner_radius=0)
        r.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(r, text="Color de acento", font=ctk.CTkFont(FF,10),
                     text_color=C["fg2"], width=170, anchor="w").pack(side="left")
        ACCENTS = ["#4d90f0","#7c6af7","#06b6d4","#22c55e","#f97316","#ec4899","#ef4444","#eab308"]
        for hex_c in ACCENTS:
            sw = tk.Label(r, bg=hex_c, width=2, height=1, cursor="hand2", relief="flat")
            sw.pack(side="left", padx=2)
            sw.bind("<Button-1>", lambda e, h=hex_c: v["accent"].set(h))
        def _custom_color():
            from tkinter.colorchooser import askcolor
            col = askcolor(color=v["accent"].get(), title="Color de acento")
            if col and col[1]: v["accent"].set(col[1])
        ctk.CTkButton(r, text="+ Custom", width=64, height=20,
                      fg_color=C["bg3"], text_color=C["fg2"],
                      hover_color=C["bg4"], font=ctk.CTkFont(FF,8),
                      corner_radius=4, command=_custom_color).pack(side="left",padx=6)
        self._prefs_section(s,"AL TERMINAR")
        self._prefs_row(s,"Notificacion",lambda p: self._prefs_pills(p,
            [("sound_flash","Sonido+flash"),("sound","Solo sonido"),("silent","Silencio")],v["notify"]))

    def _prefs_deteccion(self, parent, v):
        s = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        s.pack(fill="both", expand=True)
        self._prefs_section(s,"MODO DE ARRANQUE")
        self._prefs_row(s,"Modo inicial",lambda p: self._prefs_pills(p,
            [("auto","Automatico"),("manual","Manual")],v["mode"]))
        r2 = ctk.CTkFrame(s, fg_color="transparent", corner_radius=0)
        r2.pack(fill="x", padx=12, pady=2)
        ctk.CTkCheckBox(r2, text="SmartShot: arrancar automaticamente al cargar video",
                        variable=v["ss_auto"], fg_color=C["acc"], checkmark_color="white",
                        font=ctk.CTkFont(FF,10), text_color=C["fg2"], corner_radius=3).pack(anchor="w")
        self._prefs_section(s,"MOTOR DE ANALISIS")
        self._prefs_row(s,"Resolucion analisis",lambda p: [
            ctk.CTkRadioButton(p,text=l,variable=v["ares"],value=val,
                fg_color=C["acc"],text_color=C["fg"],font=ctk.CTkFont(FF,9)).pack(side="left",padx=(0,8))
            for val,l in [("320","320px (rapido)"),("480","480px"),("640","640px (preciso)")]])
        self._prefs_section(s,"VALORES POR DEFECTO — MODO AUTOMATICO")
        for label,key,mn,mx,res,fmt in [
            ("Nitidez minima","blur",5,70,1,lambda v:f"{int(v)}%"),
            ("Anti-duplicados","sim",0.80,0.99,0.01,lambda v:f"{v:.2f}"),
            ("Anti-shake","shake",5,80,5,lambda v:f"{int(v)}px"),
            ("Max. frames","maxf",0,1000,25,lambda v:"sin limite" if int(v)==0 else str(int(v))),
        ]:
            self._prefs_row(s,label,lambda p,k=key,mn=mn,mx=mx,res=res,f=fmt,var=v[key]:
                            self._mini_slider(p,var,mn,mx,res,f))

    def _mini_slider(self, parent, var, mn, mx, res, fmt):
        lv = tk.StringVar(value=fmt(var.get()))
        ctk.CTkLabel(parent,textvariable=lv,width=60,font=ctk.CTkFont(FF,9,"bold"),
                     fg_color=C["bg3"],text_color=C["fg"],corner_radius=4).pack(side="right")
        def _cmd(val): lv.set(fmt(float(val)))
        ctk.CTkSlider(parent,from_=mn,to=mx,variable=var,
                      fg_color=C["bg0"],progress_color=C["acc"],
                      button_color=C["acc2"],button_hover_color="white",
                      command=_cmd).pack(side="left",fill="x",expand=True)

    def _prefs_exportacion(self, parent, v):
        s = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        s.pack(fill="both", expand=True)
        self._prefs_section(s,"FORMATO Y CALIDAD")
        self._prefs_row(s,"Formato",lambda p: self._prefs_pills(p,[("jpg","JPG"),("png","PNG")],v["fmt"]))
        self._prefs_row(s,"Tamano maximo",lambda p: [
            ctk.CTkRadioButton(p,text=l,variable=v["size"],value=val,
                fg_color=C["acc"],text_color=C["fg"],font=ctk.CTkFont(FF,9)).pack(side="left",padx=(0,6))
            for val,l in [("Original","Orig"),("3840","4K"),("1920","1080p"),("1280","720p")]])
        self._prefs_row(s,"Calidad JPG",lambda p: self._mini_slider(p,v["quality"],60,100,1,lambda x:str(int(x))))
        self._prefs_section(s,"CARPETA DE SALIDA")
        def out_w(p):
            e = ctk.CTkEntry(p,textvariable=v["outdir"],width=200,height=28,
                             fg_color=C["bg2"],text_color=C["fg"],
                             border_color=C["bg4"],font=ctk.CTkFont(FF,9))
            e.pack(side="left")
            ctk.CTkButton(p,text="...",width=28,height=28,
                          fg_color=C["bg2"],text_color=C["fg"],hover_color=C["bg4"],
                          corner_radius=4,
                          command=lambda:v["outdir"].set(filedialog.askdirectory() or v["outdir"].get())
                          ).pack(side="left",padx=4)
        self._prefs_row(s,"Carpeta por defecto",out_w)

    def _prefs_preajustes(self, parent, v):
        s = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        s.pack(fill="both", expand=True)
        presets = load_presets()
        self._prefs_section(s,"PREAJUSTES DISPONIBLES")
        for p in presets:
            card = ctk.CTkFrame(s, fg_color=C["bg3"], corner_radius=8)
            card.pack(fill="x", padx=12, pady=3)
            top = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
            top.pack(fill="x", padx=10, pady=6)
            badge = "sistema" if p.get("system") else "personal"
            badge_color = C["acc"] if p.get("system") else C["grn"]
            ctk.CTkLabel(top,text=p["name"],font=ctk.CTkFont(FF,10,"bold"),
                         text_color=C["fg"]).pack(side="left")
            ctk.CTkLabel(top,text=f"  [{badge}]",font=ctk.CTkFont(FF,8),
                         text_color=badge_color).pack(side="left")
            info = f"Nitidez {p.get('blur',30)}%  |  Shake {p.get('shake',35)}px  |  Max {p.get('max',300)}  |  {p.get('fmt','jpg').upper()}"
            ctk.CTkLabel(card,text=info,font=ctk.CTkFont(FF,8),
                         text_color=C["fg3"]).pack(anchor="w",padx=10,pady=(0,6))
        self._prefs_section(s,"IMPORTAR / EXPORTAR PREAJUSTE")
        btn_row = ctk.CTkFrame(s,fg_color="transparent",corner_radius=0)
        btn_row.pack(fill="x",padx=12,pady=6)
        ctk.CTkButton(btn_row,text="Exportar preajuste activo .json",height=28,
                      fg_color=C["bg3"],text_color=C["fg"],hover_color=C["bg4"],
                      corner_radius=5,font=ctk.CTkFont(FF,9),
                      command=lambda:self._export_preset_json()).pack(side="left",padx=(0,8))
        ctk.CTkButton(btn_row,text="Importar .json",height=28,
                      fg_color=C["bg3"],text_color=C["fg"],hover_color=C["bg4"],
                      corner_radius=5,font=ctk.CTkFont(FF,9),
                      command=lambda:self._import_preset_json()).pack(side="left")

    def _prefs_ayuda(self, parent, v):
        s = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        s.pack(fill="both", expand=True)
        self._prefs_section(s,f"TOPSHOT EXTRACTOR v{VERSION}")
        ctk.CTkLabel(s,text="by Gnomalab Studio 2026  |  www.gnomalab.es",
                     font=ctk.CTkFont(FF,11),text_color=C["fg2"],
                     justify="left").pack(anchor="w",padx=14,pady=6)

        self._prefs_section(s,"ATAJOS DE TECLADO")
        shortcuts = [
            ("Espacio",     "Play / Pause"),
            ("I",           "Marcar punto IN"),
            ("O",           "Marcar punto OUT"),
            ("Flecha Izq",  "Retroceder 1 frame"),
            ("Flecha Der",  "Avanzar 1 frame"),
            ("Shift + Izq", "Retroceder 10 frames"),
            ("Shift + Der", "Avanzar 10 frames"),
            ("Inicio",      "Ir al principio"),
            ("Fin",         "Ir al final"),
            ("E",           "Exportar frames seleccionados"),
        ]
        for key, desc in shortcuts:
            row = ctk.CTkFrame(s, fg_color="transparent", corner_radius=0)
            row.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(row, text=key, font=ctk.CTkFont("Consolas",10,"bold"),
                         fg_color=C["bg3"], text_color=C["acc2"],
                         corner_radius=4, width=120).pack(side="left")
            ctk.CTkLabel(row, text=desc, font=ctk.CTkFont(FF,10),
                         text_color=C["fg2"]).pack(side="left", padx=10)

        self._prefs_section(s,"ALGORITMO DE DETECCION")
        algo_text = (
            "1. Laplacian Variance — mide nitidez. Frame borroso = baja varianza, se descarta.\n\n"
            "2. Optical Flow (Farneback) — mide movimiento. Flujo alto = shake de camara.\n\n"
            "3. Perceptual Hash — detecta frames duplicados comparando 16x16px binarizados."
        )
        ctk.CTkLabel(s,text=algo_text,font=ctk.CTkFont(FF,10),text_color=C["fg2"],
                     justify="left",wraplength=440).pack(anchor="w",padx=14,pady=6)
        self._prefs_section(s,"ENLACES")
        ctk.CTkButton(s,text="gnomalab.es",height=30,fg_color=C["bg3"],
                      text_color=C["acc2"],hover_color=C["bg4"],corner_radius=5,
                      font=ctk.CTkFont(FF,10),
                      command=lambda:webbrowser.open("https://www.gnomalab.es")).pack(
                      anchor="w",padx=14,pady=6)

    def _export_preset_json(self):
        p = load_presets()[0]  # export first preset as example
        path = filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("JSON","*.json")], initialfile="preajuste.json")
        if path:
            with open(path,"w",encoding="utf-8") as f: json.dump(p,f,indent=2)

    def _import_preset_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not path: return
        try:
            with open(path,"r",encoding="utf-8") as f: p = json.load(f)
            p["system"] = False
            user = [x for x in load_presets() if not x.get("system")]
            user.append(p)
            save_user_presets(user)
            self._log(f"Preajuste '{p.get('name','?')}' importado.","success")
        except Exception as e:
            messagebox.showerror("Error",f"No se pudo importar:\n{e}")

    def _open_queue(self):
        messagebox.showinfo("Cola","Cola de procesamiento por lotes — v1.0.0")

    def _open_ffmpeg_dialog(self):
        if self._ffmpeg_path:
            messagebox.showinfo("ffmpeg", f"ffmpeg disponible:\n{self._ffmpeg_path}"); return

        win = ctk.CTkToplevel(self)
        win.title("Instalar ffmpeg"); win.geometry("460x300")
        win.configure(fg_color=C["bg1"]); win.grab_set()

        hdr = ctk.CTkFrame(win, fg_color=C["org"], corner_radius=0, height=40)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  Instalar ffmpeg automaticamente",
                     font=ctk.CTkFont(FF,12,"bold"), text_color="white").pack(side="left", padx=12)

        body = ctk.CTkFrame(win, fg_color="transparent", corner_radius=0)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(body,
            text="ffmpeg acelera el analisis hasta 20x.\nSe instalara en la carpeta 'tools' junto a la app.\nNo modifica el sistema ni el PATH.",
            font=ctk.CTkFont(FF,10), text_color=C["fg"],
            justify="left").pack(anchor="w", pady=(0,12))

        log_box = ctk.CTkTextbox(body, height=80, fg_color=C["bg0"],
                                  text_color=C["fg2"], font=ctk.CTkFont("Consolas",8),
                                  corner_radius=6, state="disabled")
        log_box.pack(fill="x")

        prog = ctk.CTkProgressBar(body, fg_color=C["bg0"], progress_color=C["org"],
                                   corner_radius=4, height=8)
        prog.set(0); prog.pack(fill="x", pady=(8,0))

        cancel_flag = [False]
        install_btn = [None]

        def log_msg(msg):
            log_box.configure(state="normal")
            log_box.insert("end", msg+"\n")
            log_box.see("end")
            log_box.configure(state="disabled")

        def do_install():
            install_btn[0].configure(state="disabled", text="Instalando...")
            cancel_flag[0] = False

            def pcb(p):
                win.after(0, lambda x=p: [prog.set(x/100)])
            def lcb(m):
                win.after(0, lambda msg=m: log_msg(msg))

            def run():
                # Simplified downloader
                system = platform.system()
                url = FFMPEG_URLS.get(system)
                if not url:
                    win.after(0, lambda: log_msg(f"Sistema no soportado: {system}")); return
                ext = ".exe" if system=="Windows" else ""
                dest = TOOLS_DIR / f"ffmpeg{ext}"
                archive = TOOLS_DIR / ("ff_tmp.zip" if url.endswith(".zip") else "ff_tmp.tar.xz")
                lcb(f"Descargando ffmpeg para {system}...")
                try:
                    def _hook(block, bsize, total):
                        if cancel_flag[0]: raise InterruptedError()
                        if total>0: pcb(min(80,int(block*bsize/total*80)))
                    urllib.request.urlretrieve(url, archive, reporthook=_hook)
                    lcb("Extrayendo...")
                    pcb(85)
                    if url.endswith(".zip"):
                        import zipfile as zf
                        with zf.ZipFile(archive,"r") as z:
                            for name in z.namelist():
                                if Path(name).name in (f"ffmpeg{ext}","ffmpeg") and "bin" in name:
                                    z.extract(name, TOOLS_DIR/"ff_extracted")
                                    src = TOOLS_DIR/"ff_extracted"/name
                                    shutil.copy2(src, dest); break
                    else:
                        with tarfile.open(archive,"r:xz") as t:
                            for m in t.getmembers():
                                if m.name.endswith("/ffmpeg") and "bin" in m.name:
                                    m.name=Path(m.name).name; t.extract(m,TOOLS_DIR); break
                    if system!="Windows" and dest.exists():
                        dest.chmod(0o755)
                    archive.unlink(missing_ok=True)
                    shutil.rmtree(TOOLS_DIR/"ff_extracted",ignore_errors=True)
                    pcb(100)
                    if dest.exists():
                        lcb("ffmpeg instalado correctamente!")
                        win.after(0, lambda: [
                            self._update_ffmpeg_badge(),
                            self._log("ffmpeg instalado.","success")])
                        win.after(1500, win.destroy)
                    else:
                        lcb("Error: no se encontro el binario.")
                except InterruptedError:
                    lcb("Cancelado.")
                except Exception as e:
                    lcb(f"Error: {e}")
                    win.after(0, lambda: install_btn[0].configure(state="normal", text="Reintentar"))

            threading.Thread(target=run, daemon=True).start()

        btn_row = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        btn_row.pack(fill="x", pady=(10,0))
        ib = ctk.CTkButton(btn_row, text="Descargar e instalar",
                           fg_color=C["org"], text_color="white",
                           hover_color="#e88a4a",
                           font=ctk.CTkFont(FF,10,"bold"),
                           corner_radius=6, height=32,
                           command=do_install)
        ib.pack(side="left")
        install_btn[0] = ib
        ctk.CTkButton(btn_row, text="Cancelar", height=32,
                      fg_color=C["bg3"], text_color=C["fg"],
                      hover_color=C["bg4"], corner_radius=6,
                      command=lambda: [cancel_flag.__setitem__(0,True), win.destroy()]
                      ).pack(side="left", padx=8)

    def _smartshot_from_dialog(self):
        p = filedialog.askopenfilename(
            filetypes=[("Videos","*.mp4 *.mov *.avi *.mkv *.mts *.m4v *.MP4 *.MOV"),("Todos","*.*")])
        if p:
            self._set_video(p)
            self.after(500, self._start_analyze, True)

    def _on_close(self):
        if self._player: self._player.release()
        self.destroy()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    missing = []
    try:    import cv2
    except: missing.append("opencv-python")
    try:    import numpy
    except: missing.append("numpy")
    try:    import customtkinter
    except: missing.append("customtkinter")
    if missing:
        import subprocess
        subprocess.check_call([sys.executable,"-m","pip","install"]+missing)
        print("Dependencias instaladas. Reinicia la app.")
        sys.exit(0)
    if not HAS_PIL:  print("[INFO] pip install Pillow  (para miniaturas)")
    if not HAS_DND:  print("[INFO] pip install tkinterdnd2  (para drag&drop)")
    app = TopShotApp()
    app.mainloop()
