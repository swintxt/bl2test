import os, re, json, shutil, time, zipfile, tempfile, threading, urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

API = "https://api.github.com/repos/bl-sdk/willow2-mod-manager/releases/latest"
CFG = os.path.join(os.path.expanduser("~"), ".bl2sdkhub.json")
ROOTS = {"willowgame", "binaries", "engine", "sdk_mods"}
SINGLE = {".sdkmod": "sdk_mods", ".ini": "WillowGame/Config", ".u": "WillowGame/CookedPCConsole",
          ".upk": "WillowGame/CookedPCConsole", ".dll": "Binaries/Win32", ".txt": "Binaries|Binaries/Win32"}


def plan_zip(names, stem):
    """Куда распаковывать ZIP: префикс внутри папки игры."""
    n = [x.replace("\\", "/") for x in names if x and not x.endswith("/")]
    tops = {x.split("/")[0].lower() for x in n}
    if tops & ROOTS:
        return ""
    if len({x.split("/")[0] for x in n}) == 1 and all("/" in x for x in n):
        return "sdk_mods/"
    return "sdk_mods/%s/" % stem


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BL2 SDK Hub")
        self.geometry("620x520")
        try:
            self.cfg = json.load(open(CFG))
        except Exception:
            self.cfg = {}
        self.ver = tk.StringVar(value=self.cfg.get("ver", "Borderlands 2"))
        self.game = tk.StringVar(value=self.cfg.get(self.ver.get(), ""))
        f = ttk.Frame(self, padding=8); f.pack(fill="both", expand=True)
        cb = ttk.Combobox(f, textvariable=self.ver, state="readonly",
                          values=["Borderlands 2", "Borderlands 2 Remastered"])
        cb.pack(fill="x"); cb.bind("<<ComboboxSelected>>", self.chg)
        r = ttk.Frame(f); r.pack(fill="x", pady=4)
        ttk.Entry(r, textvariable=self.game).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Папка игры", command=self.pick).pack(side="left")
        for t, c in (("1. Установить SDK (скачать автоматически)", self.sdk_auto),
                     ("   или SDK из своего ZIP", self.sdk_zip),
                     ("2. Установить мод (.py .sdkmod .zip .txt .ini .u .upk)", self.mod),
                     ("Откатить последнюю установку", self.rollback)):
            ttk.Button(f, text=t, command=c).pack(fill="x", pady=1)
        ttk.Label(f, text="Установленные Python-моды (sdk_mods):").pack(anchor="w", pady=(6, 0))
        self.lb = tk.Listbox(f, height=7); self.lb.pack(fill="x")
        ttk.Button(f, text="Удалить выбранный мод", command=self.rm).pack(fill="x")
        self.out = tk.Text(f, height=9, state="disabled"); self.out.pack(fill="both", expand=True, pady=4)
        self.refresh()

    def say(self, t):
        self.out.config(state="normal"); self.out.insert("end", t + "\n")
        self.out.config(state="disabled"); self.out.see("end"); self.update_idletasks()

    def save(self):
        self.cfg["ver"] = self.ver.get(); self.cfg[self.ver.get()] = self.game.get()
        json.dump(self.cfg, open(CFG, "w"))

    def chg(self, _=None):
        self.cfg["ver"] = self.ver.get(); self.game.set(self.cfg.get(self.ver.get(), "")); self.refresh()

    def pick(self):
        d = filedialog.askdirectory()
        if d:
            self.game.set(d); self.save(); self.refresh()

    def g(self):
        g = self.game.get()
        if not (os.path.isdir(os.path.join(g, "Binaries")) or os.path.isdir(os.path.join(g, "WillowGame"))):
            messagebox.showerror("Ошибка", "Укажите папку игры (где Binaries и WillowGame)")
            return None
        self.save(); return g

    def refresh(self):
        self.lb.delete(0, "end")
        d = os.path.join(self.game.get(), "sdk_mods")
        if os.path.isdir(d):
            for x in sorted(os.listdir(d)):
                self.lb.insert("end", x)

    def write(self, g, rel, data, bdir):
        dst = os.path.normpath(os.path.join(g, *rel.split("/")))
        if not dst.startswith(os.path.normpath(g)):
            return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            b = os.path.join(bdir, os.path.relpath(dst, g))
            os.makedirs(os.path.dirname(b), exist_ok=True); shutil.copy2(dst, b)
        open(dst, "wb").write(data)

    def extract(self, g, zpath, stem):
        z = zipfile.ZipFile(zpath)
        pre = plan_zip(z.namelist(), stem)
        bdir = os.path.join(g, "_hub_backup", time.strftime("%Y%m%d_%H%M%S"))
        n = 0
        for m in z.infolist():
            if m.is_dir():
                continue
            self.write(g, pre + m.filename.replace("\\", "/"), z.read(m), bdir); n += 1
        self.say("Файлов: %d (в %s)" % (n, pre or "корень игры"))

    def sdk_zip(self):
        g = self.g()
        p = g and filedialog.askopenfilename(filetypes=[("ZIP", "*.zip")])
        if p:
            self.extract(g, p, "sdk"); self.say("Готово. Запустите игру: в меню должен быть пункт MODS."); self.refresh()

    def sdk_auto(self):
        g = self.g()
        if g:
            threading.Thread(target=self._auto, args=(g,), daemon=True).start()

    def _auto(self, g):
        try:
            self.say("Ищу последнюю версию SDK на GitHub...")
            req = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "bl2hub"}), timeout=60)
            rel = json.load(req(API))
            zs = [a for a in rel["assets"] if a["name"].lower().endswith(".zip")]
            c = [a for a in zs if re.search(r"bl2|borderlands.?2|willow2", a["name"].lower()) and "tps" not in a["name"].lower()] or zs
            a = c[0]
            if len(c) > 1:
                i = simpledialog.askinteger("Выбор", "\n".join("%d) %s" % (k + 1, x["name"]) for k, x in enumerate(c)) + "\nНомер:")
                a = c[(i or 1) - 1]
            self.say("Скачиваю " + a["name"])
            tmp = os.path.join(tempfile.gettempdir(), a["name"])
            open(tmp, "wb").write(req(a["browser_download_url"]).read())
            self.extract(g, tmp, "sdk")
            self.say("SDK установлен. Нужен Visual C++ Redistributable. Запустите игру: пункт MODS.")
            self.refresh()
        except Exception as e:
            self.say("Не вышло: %s\nСкачайте ZIP вручную с github.com/bl-sdk/willow2-mod-manager/releases и нажмите «SDK из своего ZIP»." % e)

    def mod(self):
        g = self.g()
        if not g:
            return
        p = filedialog.askopenfilename()
        if not p:
            return
        ext = os.path.splitext(p)[1].lower(); stem = os.path.splitext(os.path.basename(p))[0]
        bdir = os.path.join(g, "_hub_backup", time.strftime("%Y%m%d_%H%M%S"))
        try:
            if ext == ".zip":
                self.extract(g, p, stem)
            elif ext == ".py":
                self.write(g, "sdk_mods/%s/__init__.py" % stem, open(p, "rb").read(), bdir)
                self.say("Python-мод установлен: " + stem)
            elif ext in SINGLE:
                for d in SINGLE[ext].split("|"):
                    self.write(g, d + "/" + os.path.basename(p), open(p, "rb").read(), bdir)
                self.say("Установлено: " + os.path.basename(p))
            else:
                self.say("Неподдерживаемый тип: " + ext)
        except Exception as e:
            self.say("Ошибка: %s" % e)
        self.refresh()

    def rm(self):
        s = self.lb.curselection(); g = self.g()
        if s and g and messagebox.askyesno("Удалить", "Удалить мод?"):
            n = self.lb.get(s[0]); p = os.path.join(g, "sdk_mods", n)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            self.say("Удалён " + n); self.refresh()

    def rollback(self):
        g = self.g()
        if not g:
            return
        root = os.path.join(g, "_hub_backup")
        if not os.path.isdir(root) or not os.listdir(root):
            self.say("Нет копий"); return
        last = os.path.join(root, sorted(os.listdir(root))[-1])
        for dp, _, fs in os.walk(last):
            for f in fs:
                s = os.path.join(dp, f); d = os.path.join(g, os.path.relpath(s, last))
                os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy2(s, d)
        shutil.rmtree(last); self.say("Восстановлено из копии"); self.refresh()


if __name__ == "__main__":
    App().mainloop()
