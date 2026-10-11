"""PDF-Slimmer 3.1 — compact Windows 11 inspired Hebrew desktop UI."""
import multiprocessing
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk
import fitz
from PIL import Image, ImageOps
from engine import convert, inspect_pdf

MODES = {
    "דחיסה חזקה לסריקות": "bw",
    "שחור־לבן וניקוי רקע": "bw-clean",
    "דחיסה חכמה (שמירת טקסט)": "smart",
    "מיטוב ללא אובדן": "lossless",
    "JBIG2": "jbig2",
    "גווני אפור": "gray",
}
BLUE = "#2563EB"
def readable(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF-Slimmer")
        self.geometry("1120x735")
        self.minsize(810, 560)
        self.paths, self.info, self.results = [], {}, {}
        self.selected = None
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.mode = tk.StringVar(value="דחיסה חזקה לסריקות")
        self.dpi = tk.StringVar(value="200")
        self.workers = tk.StringVar(value="2")
        self.keep = tk.BooleanVar(value=True)
        self.ocr = tk.BooleanVar(value=False)
        self.theme = tk.StringVar(value="System")
        self.output = tk.StringVar(value=str(Path.home() / "Documents" / "PDF-Slimmer"))
        self.status = tk.StringVar(value="מוכן להתחלה")
        self._build()
        self.after(100, self._poll)

    def label(self, parent, text, size=13, bold=False, **kw):
        return ctk.CTkLabel(parent, text=text, anchor="e",
                            font=("Segoe UI", size, "bold" if bold else "normal"), **kw)

    def button(self, parent, text, command, secondary=False, width=105):
        return ctk.CTkButton(parent, text=text, command=command, width=width,
                             corner_radius=8, height=34,
                             fg_color=("gray82", "gray29") if secondary else BLUE,
                             text_color=("gray13", "gray96") if secondary else "white",
                             hover_color=("gray73", "gray36") if secondary else "#1D4ED8")

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(17, 8))
        self.label(header, "PDF-Slimmer", 25, True).pack(side="right")
        self.label(header, "דחיסת קובצי PDF • באופן מקומי", 12,
                   text_color=("gray45", "gray65")).pack(side="right", padx=15)
        self.button(header, "הגדרות", self.settings, True, 85).pack(side="left", padx=4)
        self.button(header, "תצוגה מקדימה", self.preview, True, 128).pack(side="left", padx=4)

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=1, column=0, sticky="nsew", padx=22, pady=6)
        center.grid_columnconfigure(0, weight=1)
        center.grid_columnconfigure(1, weight=0)
        center.grid_rowconfigure(0, weight=1)
        main = ctk.CTkFrame(center, corner_radius=12)
        main.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)
        action = ctk.CTkFrame(main, fg_color="transparent")
        action.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 7))
        self.label(action, "רשימת הקבצים", 17, True).pack(side="right")
        self.button(action, "הוסף קבצים", self.add_files).pack(side="left", padx=3)
        self.button(action, "הוסף תיקייה", self.add_folder, True).pack(side="left", padx=3)
        self.button(action, "נקה", self.clear, True, 62).pack(side="left", padx=3)
        self.summary = self.label(main, "לא נוספו קבצים", 12,
                                  text_color=("gray44", "gray65"))
        self.summary.grid(row=1, column=0, sticky="e", padx=18, pady=(0, 5))
        self.filebox = ctk.CTkScrollableFrame(main, fg_color="transparent")
        self.filebox.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 12))

        panel = ctk.CTkFrame(center, width=290, corner_radius=12)
        panel.grid(row=0, column=1, sticky="ns")
        panel.grid_propagate(False)
        self.label(panel, "הגדרות מהירות", 17, True).pack(fill="x", padx=18, pady=(20, 9))
        self.label(panel, "מצב דחיסה", 12).pack(fill="x", padx=18)
        ctk.CTkOptionMenu(panel, variable=self.mode, values=list(MODES),
                          width=255, height=36, corner_radius=8).pack(padx=16, pady=(4, 15))
        self.label(panel, "רזולוציית סריקה", 12).pack(fill="x", padx=18)
        ctk.CTkOptionMenu(panel, variable=self.dpi, values=["150", "200", "300", "400"],
                          width=255).pack(padx=16, pady=(4, 15))
        ctk.CTkCheckBox(panel, text="שמור את המקור כשאין חיסכון",
                        variable=self.keep).pack(anchor="e", padx=18, pady=(5, 10))
        self.label(panel, "המרת שחור־לבן עלולה להסיר OCR וצבעים.",
                   11, wraplength=250, text_color=("gray45", "gray65")).pack(fill="x", padx=16, pady=12)
        self.label(panel, "סיכום עיבוד", 16, True).pack(fill="x", padx=18, pady=(15, 4))
        self.totals = self.label(panel, "0 קבצים", 13)
        self.totals.pack(fill="x", padx=18)
        self._refresh()

        footer = ctk.CTkFrame(self, corner_radius=12)
        footer.grid(row=2, column=0, sticky="ew", padx=22, pady=(6, 18))
        footer.grid_columnconfigure(0, weight=1)
        self.start_button = self.button(footer, "התחל דחיסה", self.start, width=132)
        self.start_button.pack(side="right", padx=(8, 12), pady=13)
        self.stop_button = self.button(footer, "בטל", self.stop, True, 68)
        self.stop_button.configure(state="disabled")
        self.stop_button.pack(side="right", pady=13)
        self.label(footer, "", 12, textvariable=self.status).pack(side="right", padx=12)
        self.progress = ctk.CTkProgressBar(footer, width=210)
        self.progress.pack(side="left", fill="x", expand=True, padx=15)
        self.progress.set(0)

    def _refresh(self):
        for child in self.filebox.winfo_children():
            child.destroy()
        if not self.paths:
            self.label(self.filebox, "הוסף קובצי PDF כדי להתחיל", 14).pack(fill="x", pady=35)
        for p in self.paths:
            data = self.info[p]
            result = self.results.get(p)
            if result:
                if isinstance(result, str):
                    detail = "שגיאה: " + result[:65]
                else:
                    saving = 100 * (1 - result["new_bytes"] / max(1, result["old_bytes"]))
                    detail = f"{readable(result['new_bytes'])}  •  חיסכון {saving:.1f}%"
                    if result["original_kept"]:
                        detail += "  •  המקור נשמר"
            else:
                detail = f"{readable(data['bytes'])}  •  {data['pages']} עמודים  •  ממתין"
            row = ctk.CTkFrame(self.filebox, corner_radius=8)
            row.pack(fill="x", padx=5, pady=4)
            self.button(row, "בחר", lambda path=p: self.select(path),
                        True, 54).pack(side="left", padx=8, pady=8)
            column = ctk.CTkFrame(row, fg_color="transparent")
            column.pack(side="right", fill="x", expand=True, padx=12, pady=5)
            self.label(column, Path(p).name, 13, True).pack(fill="x")
            self.label(column, detail, 11, text_color=("gray45", "gray65")).pack(fill="x")
        self.summary.configure(text=f"{len(self.paths)} קבצים נבחרו")
        old_total = sum(i["bytes"] for i in self.info.values())
        new_total = sum(r["new_bytes"] for r in self.results.values() if isinstance(r, dict))
        finished = sum(isinstance(r, dict) for r in self.results.values())
        self.totals.configure(text=f"{len(self.paths)} קבצים  •  {readable(old_total)}\n"
                                   + (f"עובדו {finished}  •  תוצאה {readable(new_total)}" if finished else "טרם בוצעה המרה"))

    def select(self, p):
        self.selected = p
        self.status.set("נבחר: " + Path(p).name[:45])

    def add_files(self):
        for p in filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")]):
            self._add(p)

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for p in sorted(Path(folder).glob("*.pdf")):
                self._add(str(p))

    def _add(self, p):
        path = str(Path(p).resolve())
        if path in self.paths:
            return
        try:
            info = inspect_pdf(path)
        except Exception as exc:
            messagebox.showerror("שגיאת קובץ", str(exc))
            return
        self.paths.append(path)
        self.info[path] = info
        self.selected = path
        self._refresh()

    def clear(self):
        if self.busy:
            return
        self.paths.clear()
        self.info.clear()
        self.results.clear()
        self.selected = None
        self._refresh()

    def settings(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("הגדרות PDF-Slimmer")
        dialog.geometry("520x450")
        dialog.transient(self)
        frame = ctk.CTkScrollableFrame(dialog)
        frame.pack(fill="both", expand=True, padx=14, pady=14)
        self.label(frame, "הגדרות מתקדמות", 20, True).pack(fill="x", pady=12)
        self.label(frame, "מספר תהליכים", 13).pack(fill="x")
        ctk.CTkOptionMenu(frame, variable=self.workers, values=["1", "2", "3", "4", "6", "8"]).pack(anchor="e", pady=8)
        ctk.CTkCheckBox(frame, text="חידוש OCR (נדרשת התקנת OCRmyPDF)", variable=self.ocr).pack(anchor="e", pady=14)
        self.label(frame, "ערכת נושא", 13).pack(fill="x")
        ctk.CTkOptionMenu(frame, variable=self.theme, values=["System", "Light", "Dark"],
                          command=ctk.set_appearance_mode).pack(anchor="e", pady=8)
        self.label(frame, "תיקיית תוצאות", 13).pack(fill="x", pady=7)
        ctk.CTkEntry(frame, textvariable=self.output, justify="right").pack(fill="x", pady=5)
        self.button(frame, "בחר תיקייה", lambda: self._choose_folder(), True).pack(anchor="e", pady=8)
        self.label(frame, "שינויים נשמרים עד סגירת התוכנה. המערכת אינה מורידה דבר בזמן ההמרה.",
                   11, wraplength=445).pack(fill="x", pady=10)

    def _choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output.set(folder)

    def preview(self):
        if not self.selected:
            messagebox.showinfo("תצוגה מקדימה", "בחר תחילה קובץ")
            return
        window = ctk.CTkToplevel(self)
        window.title("לפני ואחרי • המחשה")
        window.geometry("1020x680")
        wrapper = ctk.CTkFrame(window)
        wrapper.pack(fill="both", expand=True, padx=12, pady=12)
        try:
            with fitz.open(self.selected) as pdf:
                pix = pdf[0].get_pixmap(matrix=fitz.Matrix(1, 1), colorspace=fitz.csRGB)
                source = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            source.thumbnail((460, 550))
            mode = MODES[self.mode.get()]
            result = source.copy()
            if mode in ("bw", "bw-clean", "jbig2", "gray"):
                result = ImageOps.grayscale(source)
                if mode in ("bw-clean",):
                    result = ImageOps.autocontrast(result)
                if mode in ("bw", "bw-clean", "jbig2"):
                    result = result.point(lambda v: 255 if v >= 190 else 0, "1")
            for title, image in (("מקור", source), ("הדמיית תוצאה", result)):
                pane = ctk.CTkFrame(wrapper)
                pane.pack(side="right", fill="both", expand=True, padx=4, pady=4)
                self.label(pane, title, 16, True).pack(pady=9)
                photo = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
                label = ctk.CTkLabel(pane, text="", image=photo)
                label.image = photo
                label.pack(expand=True)
            self.label(wrapper, "הדמיה בלבד; אינה מייצגת את גודל הקובץ הסופי.", 11).pack(side="bottom")
        except Exception as exc:
            window.destroy()
            messagebox.showerror("שגיאת תצוגה", str(exc))

    def start(self):
        if self.busy or not self.paths:
            return
        mode = MODES[self.mode.get()]
        if mode in ("bw", "bw-clean", "jbig2") and not messagebox.askyesno(
            "אזהרה", "מצב זה עלול להסיר OCR, קישורים וצבעים. להמשיך?"):
            return
        self.busy = True
        self.cancel.clear()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.set(0)
        options = dict(mode=mode, dpi=int(self.dpi.get()), workers=int(self.workers.get()),
                       preserve_ocr=self.ocr.get(), keep_smaller=self.keep.get())
        self.results = {}
        self._refresh()
        threading.Thread(target=self._worker, args=(self.paths.copy(), self.output.get(), options),
                         daemon=True).start()

    def stop(self):
        self.cancel.set()
        self.status.set("מבטל עיבוד...")

    def _worker(self, paths, folder, options):
        for index, p in enumerate(paths):
            if self.cancel.is_set():
                break
            try:
                source = Path(p)
                target = Path(folder) / (source.stem + "_" + options["mode"] + ".pdf")
                n = 2
                while target.exists() or target.resolve() == source:
                    target = Path(folder) / (source.stem + "_" + options["mode"] + f"_{n}.pdf")
                    n += 1
                result = convert(source, target, cancel=self.cancel, **options)
                self.events.put(("result", p, result))
            except Exception as exc:
                self.events.put(("result", p, str(exc)))
            self.events.put(("progress", (index + 1) / len(paths)))
        self.events.put(("done",))

    def _poll(self):
        try:
            while True:
                msg = self.events.get_nowait()
                if msg[0] == "result":
                    self.results[msg[1]] = msg[2]
                    self.status.set("סיים: " + Path(msg[1]).name[:40])
                    self._refresh()
                elif msg[0] == "progress":
                    self.progress.set(msg[1])
                else:
                    self.busy = False
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.status.set("בוטל" if self.cancel.is_set() else "העיבוד הושלם")
        except queue.Empty:
            pass
        self.after(100, self._poll)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    App().mainloop()
