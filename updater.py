# -*- coding: utf-8 -*-
"""Crew Motorfest Randomizer - remote updater (standard library only).

Called by the launcher (tcm_launcher.pyw / the .exe) every time the app starts.
It reads a small manifest.json from the address written in update_config.json, downloads only the
files that changed (program, CSV files, photos) and installs them - like a video-game patcher.

Safety rules:
  * every downloaded file is checked against the SHA-256 in the manifest before it is installed;
  * a program file that does not compile is never installed;
  * nothing is installed unless ALL downloads succeeded (otherwise: retry at the next launch);
  * a CSV file you edited yourself is never overwritten silently (you are asked, and a .mine.bak copy is kept);
  * offline / server down / any error: the app simply starts with the files you already have.
"""
import hashlib
import json
import os
import shutil
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

UPDATER_VERSION = 1
CONFIG_FILE, STATE_FILE, LOG_FILE = "update_config.json", "update_state.json", "update_log.txt"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
TIMEOUT = 8
USER_AGENT = "TCM-Randomizer-Updater/1"


# ----------------------------------------------------------------------------- helpers
def log(base, msg):
    try:
        path = os.path.join(base, LOG_FILE)
        if os.path.isfile(path) and os.path.getsize(path) > 200_000:
            os.remove(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def kind_of(rel):
    if rel.endswith(".pyw") or rel.endswith(".py"):
        return "code"
    if rel.endswith(".csv"):
        return "data"
    return "asset"


def valid_rel(rel):
    """Only these paths may ever be written by an update (blocks '..', absolute paths, odd folders)."""
    if not isinstance(rel, str) or not rel or "\\" in rel or ":" in rel or rel.startswith("/"):
        return False
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    if len(parts) == 1:
        name = parts[0].lower()
        return name == "updater.py" or name.endswith((".pyw", ".csv", ".ico"))
    return len(parts) == 2 and parts[0] == "images" and parts[1].lower().endswith(IMAGE_EXTS)


def check_url(url):
    p = urllib.parse.urlparse(url)
    if p.scheme == "https" and p.netloc:
        return True
    return p.scheme == "http" and p.hostname in ("localhost", "127.0.0.1")   # plain http only for local tests


def local_hash(path, cache, rel):
    st = os.stat(path)
    key = [st.st_mtime_ns, st.st_size]
    c = cache.get(rel)
    if isinstance(c, list) and c[:2] == key:
        return c[2]
    h = sha256_file(path)
    cache[rel] = key + [h]
    return h


def fetch_manifest(url):
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(url + sep + "t=" + str(int(time.time())),
                                 headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read(20_000_000).decode("utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise ValueError("manifest has no 'files'")
    files = {}
    for rel, info in data["files"].items():
        sha = (info or {}).get("sha256", "") if isinstance(info, dict) else ""
        if valid_rel(rel) and isinstance(sha, str) and len(sha) == 64:
            files[rel] = {"sha256": sha.lower(), "size": int(info.get("size", -1))}
    return {"version": int(data.get("version", 0)), "base_url": data.get("base_url") or "", "files": files}


def make_plan(base, manifest, state, cache):
    synced = state.get("files", {})
    todo, conflicts, same, keep = [], [], [], []
    for rel, info in sorted(manifest["files"].items()):
        path = os.path.join(base, *rel.split("/"))
        remote = info["sha256"]
        if not os.path.isfile(path):
            todo.append(rel)
            continue
        local = local_hash(path, cache, rel)
        if local == remote:
            same.append(rel)
        elif kind_of(rel) != "data":
            todo.append(rel)                                   # program / photos: server always wins
        else:
            was = synced.get(rel)
            if was is not None and local == was:
                todo.append(rel)                               # CSV you never touched: update it
            elif was == remote:
                keep.append(rel)                               # you edited it, server unchanged: leave it
            else:
                conflicts.append(rel)                          # you edited it AND the server changed it
    remove = [r for r in synced if r not in manifest["files"] and r.startswith("images/")]
    return {"todo": todo, "conflicts": conflicts, "same": same, "keep": keep, "remove": remove}


def download(base, url_base, rel, info, version, cancelled):
    dest = os.path.join(base, *rel.split("/"))
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(part) and sha256_file(part) == info["sha256"]:
        return part                                            # already fetched during an interrupted run
    url = url_base + urllib.parse.quote(rel) + "?v=" + str(version)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(part, "wb") as f:
        while True:
            if cancelled():
                raise InterruptedError("cancelled")
            chunk = r.read(65536)
            if not chunk:
                break
            h.update(chunk)
            f.write(chunk)
    if h.hexdigest() != info["sha256"]:
        os.remove(part)
        raise ValueError("checksum mismatch for " + rel)
    if kind_of(rel) == "code":
        with open(part, "rb") as f:
            compile(f.read(), rel, "exec")                     # never install a broken program
    return part


# ----------------------------------------------------------------------------- main logic
def run_update(base, ask=None, progress=None, cancelled=lambda: False, begin_apply=lambda: True):
    """Check the server and install what changed. Returns a dict with 'status':
    'disabled' | 'offline' | 'uptodate' | 'updated' | 'cancelled' | 'error'.
    ask(list_of_conflicting_files) -> True to take the server's version, False to keep yours.
    progress(message, done, total) is optional (used by the splash window)."""
    say = progress or (lambda *a: None)
    cfg = load_json(os.path.join(base, CONFIG_FILE), {})
    url = str(cfg.get("manifest_url") or "").strip()
    if not url or cfg.get("auto_check", True) is False:
        return {"status": "disabled"}
    if not check_url(url):
        log(base, "manifest_url must start with https:// : " + url)
        return {"status": "error", "error": "manifest_url must be https"}
    state_path = os.path.join(base, STATE_FILE)
    state = load_json(state_path, {})
    state.setdefault("files", {})
    cache = state.setdefault("cache", {})
    try:
        say("Checking for updates...", 0, 0)
        manifest = fetch_manifest(url)
    except (urllib.error.URLError, OSError, ValueError) as e:
        log(base, f"offline or bad manifest ({e}); starting with local files")
        return {"status": "offline", "error": str(e)}
    try:
        url_base = manifest["base_url"] or url.split("?")[0].rsplit("/", 1)[0] + "/"
        if not url_base.endswith("/"):
            url_base += "/"
        plan = make_plan(base, manifest, state, cache)
        take_server = set()
        if plan["conflicts"]:
            say("Waiting for your choice...", 0, 0)
            if ask is not None and ask(plan["conflicts"]):
                take_server = set(plan["conflicts"])
            else:                                              # keep the user's file; remember the server version
                for rel in plan["conflicts"]:
                    state["files"][rel] = manifest["files"][rel]["sha256"]
        for rel in plan["same"]:
            state["files"][rel] = manifest["files"][rel]["sha256"]
        queue_ = plan["todo"] + sorted(take_server)
        # updater.py is installed last so a half-finished run never leaves a mismatched updater
        queue_.sort(key=lambda r: (r == "updater.py", r))
        if not queue_ and not plan["remove"]:
            state["version"] = manifest["version"] if not plan["conflicts"] else state.get("version")
            save_json(state_path, state)
            return {"status": "uptodate", "version": manifest["version"]}
        parts, total = {}, len(queue_)
        for i, rel in enumerate(queue_, start=1):
            if cancelled():
                return {"status": "cancelled"}
            say(f"Downloading update  {i}/{total}", i - 1, total)
            parts[rel] = download(base, url_base, rel, manifest["files"][rel], manifest["version"], cancelled)
        say("Installing...", total, total)
        if not begin_apply():
            return {"status": "cancelled"}
        for rel in queue_:
            dest = os.path.join(base, *rel.split("/"))
            if os.path.isfile(dest):
                kind = kind_of(rel)
                if kind == "code":
                    shutil.copy2(dest, dest + ".bak")
                elif kind == "data":
                    shutil.copy2(dest, dest + ".mine.bak")
            os.replace(parts[rel], dest)
            state["files"][rel] = manifest["files"][rel]["sha256"]
            state.get("cache", {}).pop(rel, None)
        for rel in plan["remove"]:
            dest = os.path.join(base, *rel.split("/"))
            try:
                if os.path.isfile(dest) and sha256_file(dest) == state["files"].get(rel):
                    os.remove(dest)                            # a photo removed from the server (never your own)
            except OSError:
                pass
            state["files"].pop(rel, None)
        state["version"] = manifest["version"]
        state["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_json(state_path, state)
        log(base, f"updated to v{manifest['version']}: {total} file(s) installed, {len(plan['remove'])} removed")
        return {"status": "updated", "version": manifest["version"], "installed": queue_, "removed": plan["remove"]}
    except InterruptedError:
        return {"status": "cancelled"}
    except Exception as e:                                     # network cut, disk full, bad file ... -> try again next time
        log(base, "update failed: " + repr(e) + "\n" + traceback.format_exc())
        return {"status": "error", "error": str(e)}


# ----------------------------------------------------------------------------- splash window
def run_startup_update(base):
    """Run the update with a small game-style splash window (shown only if it takes more than a moment)."""
    cfg = load_json(os.path.join(base, CONFIG_FILE), {})
    if not str(cfg.get("manifest_url") or "").strip() or cfg.get("auto_check", True) is False:
        return None
    import tkinter as tk
    from tkinter import ttk, messagebox

    BG, FG, ACCENT, PANEL = "#062B3A", "#FFF6E5", "#FF8A3D", "#0C4257"
    root = tk.Tk()
    root.withdraw()
    root.title("Crew Motorfest Randomizer")
    root.configure(bg=BG)
    root.resizable(False, False)
    w, h = 440, 150
    root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")
    icon = os.path.join(base, "app_icon.ico")
    if os.path.isfile(icon):
        try:
            root.iconbitmap(icon)
        except tk.TclError:
            pass
    tk.Label(root, text="🌺  Crew Motorfest Randomizer", bg=BG, fg=ACCENT, font=("Arial", 14, "bold")).pack(pady=(14, 4))
    msg = tk.Label(root, text="Checking for updates...", bg=BG, fg=FG, font=("Arial", 10))
    msg.pack()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
        style.configure("tcm.Horizontal.TProgressbar", troughcolor=PANEL, background=ACCENT, bordercolor=PANEL,
                        lightcolor=ACCENT, darkcolor=ACCENT)
    except tk.TclError:
        pass
    bar = ttk.Progressbar(root, length=360, mode="indeterminate", style="tcm.Horizontal.TProgressbar")
    bar.pack(pady=10)
    skip = tk.Button(root, text="Skip", bg=PANEL, fg=FG, activebackground=ACCENT, bd=0, padx=14,
                     command=lambda: on_skip())
    skip.pack()

    S = {"msg": "Checking for updates...", "done": 0, "total": 0, "finished": False, "result": None,
         "cancel": False, "applying": False, "conflicts": None, "answer": None}
    lock, answered = threading.Lock(), threading.Event()

    def progress(m, done, total):
        S["msg"], S["done"], S["total"] = m, done, total

    def ask(files):
        S["conflicts"] = files
        answered.wait()
        return S["answer"]

    def begin_apply():
        with lock:
            if S["cancel"]:
                return False
            S["applying"] = True
            return True

    def on_skip():
        with lock:
            if not S["applying"]:
                S["cancel"] = True
        if S["cancel"]:
            root.destroy()

    def worker():
        try:
            S["result"] = run_update(base, ask=ask, progress=progress, cancelled=lambda: S["cancel"], begin_apply=begin_apply)
        except Exception as e:
            log(base, "updater crashed: " + repr(e))
            S["result"] = {"status": "error", "error": str(e)}
        S["finished"] = True

    threading.Thread(target=worker, daemon=True).start()
    t0, shown = time.time(), [False]

    def show():
        if not shown[0]:
            shown[0] = True
            root.deiconify()
            root.lift()
            bar.start(12)

    def poll():
        if S["conflicts"] is not None and S["answer"] is None:
            show()
            names = "\n".join("  - " + c for c in S["conflicts"])
            S["answer"] = bool(messagebox.askyesno(
                "Update - files edited on your PC",
                "These data files were edited on your PC AND changed on the server:\n\n" + names +
                "\n\nYES  = use the server's new version (yours is saved as  *.mine.bak)\n"
                "NO   = keep your version", parent=root))
            answered.set()
        if S["total"] and bar["mode"] == "indeterminate":
            bar.stop()
            bar.configure(mode="determinate", maximum=S["total"])
        if S["total"]:
            bar["value"] = S["done"]
        msg.config(text=S["msg"])
        if S["applying"]:
            skip.config(state="disabled")
        if S["finished"]:
            root.destroy()
            return
        if not shown[0] and (time.time() - t0 > 0.6 or S["total"]):
            show()
        root.after(60, poll)

    root.after(60, poll)
    try:
        root.mainloop()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass
    return S["result"]


# ----------------------------------------------------------------------------- manual "Update" button (inside the app)
def restart_app():
    """Start a fresh copy of the app (so the new program is loaded). The caller then closes the current window."""
    import subprocess
    import sys
    frozen = getattr(sys, "frozen", False)
    args = [sys.executable] + (sys.argv[1:] if frozen else sys.argv)
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0           # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen(args, env=env, creationflags=flags, close_fds=True)


def check_now(root, base):
    """Called by the app's 'Update' button: check, download, install, then offer to restart."""
    import tkinter as tk
    from tkinter import ttk, messagebox
    cfg = load_json(os.path.join(base, CONFIG_FILE), {})
    if not str(cfg.get("manifest_url") or "").strip():
        messagebox.showinfo("Update", "No update address is set.\n\nPut it in update_config.json "
                            "(\"manifest_url\") next to the program.", parent=root)
        return
    BG, FG, ACCENT, PANEL = "#062B3A", "#FFF6E5", "#FF8A3D", "#0C4257"
    top = tk.Toplevel(root)
    top.title("Update")
    top.configure(bg=BG)
    top.resizable(False, False)
    top.transient(root)
    w, h = 420, 130
    top.geometry(f"{w}x{h}+{root.winfo_rootx() + (root.winfo_width() - w) // 2}+{root.winfo_rooty() + 120}")
    msg = tk.Label(top, text="Checking for updates...", bg=BG, fg=FG, font=("Arial", 11, "bold"))
    msg.pack(pady=(22, 8))
    bar = ttk.Progressbar(top, length=340, mode="indeterminate")
    bar.pack()
    bar.start(12)
    skip = tk.Button(top, text="Cancel", bg=PANEL, fg=FG, activebackground=ACCENT, bd=0, padx=14,
                     command=lambda: on_cancel())
    skip.pack(pady=10)
    top.grab_set()

    S = {"msg": "Checking for updates...", "done": 0, "total": 0, "finished": False, "result": None,
         "cancel": False, "applying": False, "conflicts": None, "answer": None}
    lock, answered = threading.Lock(), threading.Event()

    def progress(m, done, total):
        S["msg"], S["done"], S["total"] = m, done, total

    def ask(files):
        S["conflicts"] = files
        answered.wait()
        return S["answer"]

    def begin_apply():
        with lock:
            if S["cancel"]:
                return False
            S["applying"] = True
            return True

    def on_cancel():
        with lock:
            if not S["applying"]:
                S["cancel"] = True
                S["finished"] = True

    def worker():
        try:
            S["result"] = run_update(base, ask=ask, progress=progress, cancelled=lambda: S["cancel"], begin_apply=begin_apply)
        except Exception as e:
            log(base, "manual update crashed: " + repr(e))
            S["result"] = {"status": "error", "error": str(e)}
        S["finished"] = True

    threading.Thread(target=worker, daemon=True).start()

    def finish():
        try:
            top.grab_release()
        except tk.TclError:
            pass
        top.destroy()
        r = S["result"] or {"status": "cancelled"}
        st = r["status"]
        if st == "updated":
            n = len(r.get("installed", []))
            if messagebox.askyesno("Update installed",
                                   f"Updated to version {r['version']} ({n} file(s)).\n\nRestart the app now to use it?", parent=root):
                try:
                    restart_app()
                    root.destroy()
                except Exception as e:
                    messagebox.showerror("Update", "Could not restart automatically (" + str(e) + ").\nPlease start the app again.", parent=root)
        elif st == "uptodate":
            messagebox.showinfo("Update", f"You are up to date (version {r.get('version', '?')}).", parent=root)
        elif st == "offline":
            messagebox.showwarning("Update", "Cannot reach the update server.\nCheck your internet connection and try again.", parent=root)
        elif st == "error":
            messagebox.showwarning("Update", "The update failed (nothing was changed).\nIt will be retried next time.\n\n" + str(r.get("error", "")), parent=root)

    def poll():
        if S["conflicts"] is not None and S["answer"] is None:
            names = "\n".join("  - " + c for c in S["conflicts"])
            S["answer"] = bool(messagebox.askyesno(
                "Update - files edited on your PC",
                "These data files were edited on your PC AND changed on the server:\n\n" + names +
                "\n\nYES  = use the server's new version (yours is saved as  *.mine.bak)\n"
                "NO   = keep your version", parent=top))
            answered.set()
        if S["total"] and bar["mode"] == "indeterminate":
            bar.stop()
            bar.configure(mode="determinate", maximum=S["total"])
        if S["total"]:
            bar["value"] = S["done"]
        msg.config(text=S["msg"])
        if S["applying"]:
            skip.config(state="disabled")
        if S["finished"]:
            finish()
            return
        top.after(60, poll)

    top.after(60, poll)
