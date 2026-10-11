"""PDF-Slimmer 3.0 graphical interface (the old app.py remains available)."""
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

ctk.set_default_color_theme("blue")
MODES = {
    "דחיסה חזקה לסריקות": "bw",
    "דחיסה חכמה ושמירת טקסט": "smart",
    "מיטוב ללא אובדן": "lossless",
    "JBIG2 (שחור־לבן)": "jbig2",
    "גווני אפור": "gray",
    "שחור־לבן + ניקוי רקע": "bw-clean",
}
def size_fmt(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024

class PDFSlimmer(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF-Slimmer 3.0")
        self.geometry("1050x720")
        self.minsize(780, 560)
        self.events = queue.Queue()
        self.paths = []
        self.stats = {}
        self.results = {}
        self.busy = False
        self.cancel = threading.Event()
        self.mode = tk.StringVar(value="דחיסה חזקה לסריקות")
        self.dpi = tk.StringVar(value="200")
        self.workers = tk.StringVar(value="2")
        self.ocr = tk.BooleanVar(value=False)
        self.keep = tk.BooleanVar(value=True)
        self.theme = tk.StringVar(value="System")
        self.output = tk.StringVar(value=str(Path.home() / "Documents" / "PDF-Slimmer"))
        self.status = tk.StringVar(value="מוכן לעבודה")
        self._build()
        self.after(120, self._poll)

    def _label(self, parent, text, size=13, bold=False, **kwargs):
        return ctk.CTkLabel(parent, text=text, font=("Segoe UI", size, "bold" if bold else "normal"),
                            anchor="e", **kwargs)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        self.content = ctk.CTkFrame(shell, corner_radius=14)
        self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

        sidebar = ctk.CTkFrame(shell, width=184, corner_radius=14)
        sidebar.grid(row=0, column=1, sticky="ns")
        sidebar.grid_propagate(False)
        self._label(sidebar, "PDF-Slimmer", 21, True).pack(fill="x", padx=15, pady=(25, 2))
        self._label(sidebar, "גרסה 3.0", 11).pack(fill="x", padx=15)
        for caption, command in (("ראשי", lambda: self._page("home")),
                                 ("קבצים ותוצאות", lambda: self._page("results")),
                                 ("הגדרות", lambda: self._page("settings"))):
            ctk.CTkButton(sidebar, text=caption, anchor="e", command=command,
                          fg_color="transparent", text_color=("gray15","gray90"),
                          hover_color=("gray84","gray26")).pack(fill="x", padx=10, pady=7)
        self._label(sidebar, "עבודה מקומית • ללא ענן", 11).pack(side="bottom", padx=8, pady=15)

        self.pages = {}
        for name in ("home", "results", "settings"):
            page = ctk.CTkFrame(self.content, fg_color="transparent")
            page.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=20, pady=16)
            page.grid_columnconfigure(0, weight=1)
            self.pages[name] = page
        self._home(self.pages["home"])
        self._results(self.pages["results"])
        self._settings(self.pages["settings"])
        self._page("home")

    def _page(self, name):
        self.pages[name].tkraise()
        if name == "results":
            self._update_result_panel()

    def _home(self, page):
        self._label(page, "דחיסת קובצי PDF", 25, True).pack(fill="x", pady=(3, 0))
        self._label(page, "בחר קבצים, בחר רמת דחיסה והתחל", 13).pack(fill="x")
        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.pack(fill="x", pady=12)
        ctk.CTkButton(actions, text="הוסף קבצים", command=self.add_files).pack(side="right", padx=4)
        ctk.CTkButton(actions, text="הוסף תיקייה", command=self.add_folder,
                      fg_color="gray45").pack(side="right", padx=4)
        ctk.CTkButton(actions, text="נקה רשימה", command=self.clear, fg_color="gray45").pack(side="right", padx=4)
        ctk.CTkButton(actions, text="תצוגה מקדימה", command=self.preview,
                      fg_color="gray45").pack(side="right", padx=4)
        self._label(page, "קבצים שנבחרו (לחץ על קובץ כדי לבחור אותו)", 12, True).pack(fill="x")
        self.filebox = ctk.CTkScrollableFrame(page, height=145)
        self.filebox.pack(fill="both", expand=True, pady=(3, 10))
        self._label(page, "מצב דחיסה", 13, True).pack(fill="x")
        self.mode_menu = ctk.CTkOptionMenu(page, values=list(MODES), variable=self.mode, width=300)
        self.mode_menu.pack(anchor="e", pady=(4, 5))
        self._label(page, "ברירת המחדל מיועדת לסריקות. מצב חכם עשוי לחסוך פחות כדי לשמור על טקסט.",
                    11).pack(fill="x")
        self._label(page, "תיקיית פלט", 12, True).pack(fill="x", pady=(8, 0))
        folder_row = ctk.CTkFrame(page, fg_color="transparent")
        folder_row.pack(fill="x", pady=3)
        ctk.CTkButton(folder_row, text="בחר", command=self.choose_output, width=75).pack(side="right", padx=4)
        ctk.CTkEntry(folder_row, textvariable=self.output, justify="right").pack(
            side="right", fill="x", expand=True)
        footer = ctk.CTkFrame(page, fg_color="transparent")
        footer.pack(fill="x", side="bottom", pady=(8, 0))
        self.start = ctk.CTkButton(footer, text="התחל דחיסה", command=self.start_run)
        self.start.pack(side="right", padx=4)
        self.stop = ctk.CTkButton(footer, text="בטל", command=self.cancel_run,
                                  state="disabled", fg_color="gray45", width=75)
        self.stop.pack(side="right", padx=4)
        self._label(footer, "", 11, textvariable=self.status).pack(side="right", padx=8)
        self.progress = ctk.CTkProgressBar(page)
        self.progress.pack(fill="x", side="bottom", pady=(4, 0))
        self.progress.set(0)
        self._refresh_files()

    def _results(self, page):
        self._label(page, "תוצאות הדחיסה", 24, True).pack(fill="x", pady=10)
        self._label(page, "הגודל המקורי והגודל לאחר העיבוד", 12).pack(fill="x")
        self.result_panel = ctk.CTkScrollableFrame(page)
        self.result_panel.pack(fill="both", expand=True, pady=10)
        ctk.CTkButton(page, text="פתח את תיקיית הפלט", command=self.open_output).pack(anchor="e", pady=8)

    def _settings(self, page):
        self._label(page, "הגדרות מתקדמות", 24, True).pack(fill="x", pady=12)
        panel = ctk.CTkScrollableFrame(page)
        panel.pack(fill="both", expand=True)
        self._label(panel, "ערכת נושא", 13, True).pack(fill="x", pady=(8, 3))
        ctk.CTkOptionMenu(panel, variable=self.theme, values=["System", "Light", "Dark"],
                          command=ctk.set_appearance_mode).pack(anchor="e", pady=5)
        self._label(panel, "רזולוציית עיבוד (DPI)", 13, True).pack(fill="x", pady=(12, 3))
        ctk.CTkOptionMenu(panel, variable=self.dpi, values=["150", "200", "300", "400"]).pack(anchor="e")
        self._label(panel, "מספר תהליכים", 13, True).pack(fill="x", pady=(12, 3))
        ctk.CTkOptionMenu(panel, variable=self.workers, values=["1", "2", "3", "4", "6", "8"]).pack(anchor="e")
        ctk.CTkCheckBox(panel, text="אם ההמרה גדולה יותר, שמור עותק מהמקור",
                        variable=self.keep).pack(anchor="e", pady=(20, 8))
        ctk.CTkCheckBox(panel, text="חידוש OCR במסמך קיים (דורש OCRmyPDF מקומי)",
                        variable=self.ocr).pack(anchor="e", pady=8)
        self._label(panel, "המרה לשחור־לבן יכולה להסיר צבעים, קישורים ושכבת OCR.", 12).pack(fill="x", pady=20)

    def _refresh_files(self):
        for child in self.filebox.winfo_children():
            child.destroy()
        if not self.paths:
            self._label(self.filebox, "אין קבצים בתור — לחץ על 'הוסף קבצים'", 13).pack(pady=25)
        for path in self.paths:
            stat = self.stats[path]
            ctk.CTkButton(self.filebox, text=f"{Path(path).name}   •   {stat['pages']} עמ׳   •   {size_fmt(stat['bytes'])}",
                          anchor="e", fg_color=("gray83", "gray27"), text_color=("gray10","gray95"),
                          command=lambda p=path: self._select(p)).pack(fill="x", padx=4, pady=3)

    def _select(self, path):
        self.selected = path
        self.status.set(f"נבחר: {Path(path).name[:45]}")

    def add_files(self):
        for name in filedialog.askopenfilenames(filetypes=[("PDF files", "*.pdf")]):
            self._append(name)

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for item in sorted(Path(folder).glob("*.pdf")):
                self._append(str(item))

    def _append(self, name):
        path = str(Path(name).resolve())
        if path in self.paths:
            return
        try:
            info = inspect_pdf(path)
        except Exception as exc:
            messagebox.showerror("שגיאת קריאה", f"{Path(path).name}: {exc}")
            return
        self.paths.append(path)
        self.stats[path] = info
        self.selected = path
        self._refresh_files()

    def clear(self):
        if self.busy: return
        self.paths.clear()
        self.stats.clear()
        self._refresh_files()

    def choose_output(self):
        directory = filedialog.askdirectory()
        if directory:
            self.output.set(directory)

    def open_output(self):
        directory = Path(self.output.get())
        if not directory.exists():
            messagebox.showinfo("תיקיית פלט", "התיקייה עדיין לא נוצרה")
        elif os.name == "nt":
            os.startfile(str(directory))
        else:
            messagebox.showinfo("תיקיית פלט", str(directory))

    def preview(self):
        selected = getattr(self, "selected", None)
        if not selected:
            messagebox.showinfo("תצוגה מקדימה", "בחר קובץ תחילה")
            return
        window = ctk.CTkToplevel(self)
        window.title("תצוגה מקדימה")
        window.geometry("1000x680")
        window.transient(self)
        holder = ctk.CTkFrame(window)
        holder.pack(fill="both", expand=True, padx=12, pady=12)
        try:
            with fitz.open(selected) as doc:
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(1, 1), colorspace=fitz.csRGB)
                original = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            original.thumbnail((450, 550))
            mode = MODES[self.mode.get()]
            changed = ImageOps.grayscale(original)
            if mode in ("bw", "bw-clean", "jbig2"):
                if mode == "bw-clean":
                    changed = ImageOps.autocontrast(changed)
                changed = changed.point(lambda x: 255 if x >= 190 else 0, "1")
            elif mode in ("smart", "lossless"):
                changed = original.copy()
            for title, photo in [("מקור", original), ("הדמיית תוצאה", changed)]:
                pane = ctk.CTkFrame(holder)
                pane.pack(side="right", expand=True, fill="both", padx=4)
                self._label(pane, title, 15, True).pack(pady=8)
                img = ctk.CTkImage(light_image=photo, dark_image=photo, size=photo.size)
                label = ctk.CTkLabel(pane, text="", image=img)
                label.image = img
                label.pack(expand=True)
            self._label(holder, "הדמיה בלבד — איכות וגודל אמיתיים נבדקים לאחר המרה", 11).pack(side="bottom")
        except Exception as exc:
            window.destroy()
            messagebox.showerror("תצוגה מקדימה", str(exc))

    def start_run(self):
        if self.busy or not self.paths:
            return
        mode = MODES[self.mode.get()]
        if mode in ("bw", "bw-clean", "jbig2") and not messagebox.askyesno(
            "אזהרת מידע", "המרת שחור־לבן עשויה להסיר צבע ושכבת OCR. להמשיך?"):
            return
        self.busy = True
        self.cancel.clear()
        self.start.configure(state="disabled")
        self.stop.configure(state="normal")
        self.progress.set(0)
        paths = self.paths.copy()
        options = dict(mode=mode, dpi=int(self.dpi.get()), workers=int(self.workers.get()),
                       preserve_ocr=self.ocr.get(), keep_smaller=self.keep.get())
        threading.Thread(target=self._worker, args=(paths, self.output.get(), options),
                         daemon=True).start()

    def cancel_run(self):
        self.cancel.set()
        self.status.set("מבצע ביטול...")

    def _worker(self, paths, folder, options):
        for index, path in enumerate(paths):
            if self.cancel.is_set(): break
            try:
                source = Path(path)
                target = Path(folder) / f"{source.stem}_{options['mode']}.pdf"
                count = 2
                while target.exists() or target.resolve() == source:
                    target = Path(folder) / f"{source.stem}_{options['mode']}_{count}.pdf"
                    count += 1
                result = convert(path, target, cancel=self.cancel, **options)
                self.events.put(("result", path, result, None))
            except Exception as exc:
                self.events.put(("result", path, None, str(exc)))
            self.events.put(("progress", (index+1)/len(paths)))
        self.events.put(("done",))

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "result":
                    _, path, result, error = event
                    self.results[path] = (result, error)
                    self.status.set(("שגיאה: " + error[:50]) if error else f"עובד: {Path(path).name}")
                elif event[0] == "progress":
                    self.progress.set(event[1])
                elif event[0] == "done":
                    self.busy = False
                    self.start.configure(state="normal")
                    self.stop.configure(state="disabled")
                    self.status.set("בוטל" if self.cancel.is_set() else "ההמרה הושלמה")
                    self._update_result_panel()
                    self._page("results")
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _update_result_panel(self):
        for widget in self.result_panel.winfo_children():
            widget.destroy()
        if not self.results:
            self._label(self.result_panel, "לא בוצעו המרות", 13).pack(pady=25)
        for path, (res, err) in self.results.items():
            card = ctk.CTkFrame(self.result_panel)
            card.pack(fill="x", pady=5)
            self._label(card, Path(path).name, 13, True).pack(fill="x", padx=12, pady=4)
            if err:
                self._label(card, "שגיאה: " + err[:130], 12).pack(fill="x", padx=12)
            else:
                saved = 100 * (1-res["new_bytes"]/max(1, res["old_bytes"]))
                label = f"לפני: {size_fmt(res['old_bytes'])}     אחרי: {size_fmt(res['new_bytes'])}     חיסכון: {saved:.1f}%"
                if res["original_kept"]:
                    label += "     •     המקור נשמר כי לא התקבל חיסכון"
                self._label(card, label, 12).pack(fill="x", padx=12, pady=7)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    PDFSlimmer().mainloop()
