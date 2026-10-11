"""Hebrew RTL-oriented desktop user interface for PDF-Slimmer."""
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageOps, ImageTk
import fitz
from engine import convert, inspect_pdf, Cancelled

LABELS = {'jbig2': 'JBIG2 ללא אובדן פיקסלים — נדרש מקודד מקומי',
          'smart': 'חכמה — זיהוי אוטומטי של סוג המסמך',
          'lossless': 'ללא אובדן — מיטוב PDF קיים',
          'gray': 'גווני אפור (ניסיון לשמר טקסט וחיפוש)',
          'bw': 'שחור־לבן — דחיסה חזקה',
          'bw-clean': 'שחור־לבן — ניקוי רקע'}

def human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.1f} {unit}'
        n /= 1024

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PDF-Slimmer | מקטין קובצי PDF')
        self.geometry('900x640')
        self.minsize(740, 540)
        self.files = []
        self.events = queue.Queue()
        self.running = False
        self.mode = tk.StringVar(value='smart')
        self.workers = tk.IntVar(value=2)
        self.preserve_ocr = tk.BooleanVar(value=True)
        self.cancel_event = threading.Event()
        self.dpi = tk.IntVar(value=200)
        self.keep = tk.BooleanVar(value=True)
        self.folder = tk.StringVar(value=str(Path.home() / 'Documents' / 'PDF-Slimmer'))
        self.status = tk.StringVar(value='מוכן לעבודה')
        self._configure_style()
        self._build()
        self.after(100, self._poll)

    def _configure_style(self):
        style = ttk.Style(self)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        style.configure('Treeview', rowheight=31, font=('Segoe UI', 10))
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'))
        style.configure('TLabelframe.Label', font=('Segoe UI', 10, 'bold'))
        style.configure('TButton', padding=(12, 7))

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill='both', expand=True)
        # Reserve the action footer first: resizing must never hide the controls.
        bottom = ttk.Frame(root)
        bottom.pack(side='bottom', fill='x', pady=(6, 0))
        self.start_button = ttk.Button(bottom, text='התחל המרה', command=self._start)
        self.start_button.pack(side='right', padx=5)
        self.cancel_button = ttk.Button(bottom, text='בטל', command=self._cancel, state='disabled')
        self.cancel_button.pack(side='right', padx=5)
        ttk.Label(bottom, textvariable=self.status).pack(side='right', padx=10)
        self.progress = ttk.Progressbar(bottom, mode='determinate')
        self.progress.pack(side='left', fill='x', expand=True, padx=8)

        pathline = ttk.Frame(root)
        pathline.pack(side='bottom', fill='x', pady=(4, 4))
        ttk.Button(pathline, text='בחר תיקיית פלט', command=self._browse).pack(side='right')
        ttk.Entry(pathline, textvariable=self.folder, justify='right').pack(side='right', fill='x', expand=True, padx=8)
        ttk.Label(root, text='שימו לב: המרת שחור־לבן עשויה להסיר קישורים, סימניות ושכבות טקסט.',
                  anchor='e', foreground='#9A5300').pack(side='bottom', fill='x', pady=(2, 0))

        options = ttk.LabelFrame(root, text='אפשרויות עיבוד', padding=(10, 5))
        options.pack(side='bottom', fill='x', pady=(4, 2))
        mode_grid = ttk.Frame(options)
        mode_grid.pack(fill='x')
        modes = list(LABELS.items())
        for index, (mode, label) in enumerate(modes):
            # Two columns instead of six tall rows.
            col = 1 - (index % 2)
            row = index // 2
            ttk.Radiobutton(mode_grid, text=label, variable=self.mode, value=mode).grid(
                row=row, column=col, sticky='e', padx=12, pady=2)
        mode_grid.columnconfigure(0, weight=1)
        mode_grid.columnconfigure(1, weight=1)

        settings_top = ttk.Frame(options)
        settings_top.pack(fill='x', pady=(6, 2))
        ttk.Checkbutton(settings_top, text='אם אין חיסכון, שמור את המקור',
                        variable=self.keep).pack(side='right', padx=8)
        ttk.Checkbutton(settings_top, text='חידוש OCR כשהמקור מכיל טקסט',
                        variable=self.preserve_ocr).pack(side='right', padx=8)

        settings_bottom = ttk.Frame(options)
        settings_bottom.pack(fill='x', pady=(2, 0))
        ttk.Label(settings_bottom, text='תהליכים:').pack(side='right')
        ttk.Combobox(settings_bottom, values=[1, 2, 3, 4, 6, 8],
                     textvariable=self.workers, width=3, state='readonly').pack(side='right', padx=5)
        ttk.Label(settings_bottom, text='רזולוציה (DPI):').pack(side='right', padx=(12, 0))
        ttk.Combobox(settings_bottom, values=[150, 200, 300, 400],
                     textvariable=self.dpi, width=6, state='readonly').pack(side='right', padx=5)

        ttk.Label(root, text='PDF-Slimmer 2.0  |  דחיסה חכמה של PDF',
                  font=('Segoe UI', 17, 'bold'), anchor='e').pack(side='top', fill='x', pady=(0, 7))
        actions = ttk.Frame(root)
        actions.pack(side='top', fill='x', pady=(0, 5))
        ttk.Button(actions, text='הוסף קובצי PDF', command=self._add).pack(side='right', padx=4)
        ttk.Button(actions, text='הסר מסומנים', command=self._remove).pack(side='right', padx=4)
        ttk.Button(actions, text='נקה רשימה', command=self._clear).pack(side='right', padx=4)
        ttk.Button(actions, text='תצוגה מקדימה', command=self._preview).pack(side='right', padx=4)
        listing = ttk.Frame(root)
        listing.pack(side='top', fill='both', expand=True, pady=(3, 0))
        self.tree = ttk.Treeview(listing, columns=('file', 'size', 'pages', 'result'),
                                 show='headings', height=5)
        for key, label, width in [('file', 'שם קובץ', 350), ('size', 'גודל מקורי', 110),
                                  ('pages', 'עמודים', 75), ('result', 'תוצאה', 240)]:
            self.tree.heading(key, text=label, anchor='e')
            self.tree.column(key, width=width, anchor='e')
        bar = ttk.Scrollbar(listing, command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)

    def _add(self):
        for name in filedialog.askopenfilenames(filetypes=[('PDF', '*.pdf')]):
            p = Path(name)
            if str(p) in self.files:
                continue
            try:
                info = inspect_pdf(p)
                self.files.append(str(p))
                self.tree.insert('', 'end', iid=str(p), values=(p.name, human_size(info['bytes']), info['pages'], 'ממתין'))
            except Exception as exc:
                messagebox.showerror('לא ניתן לפתוח', f'{p.name}\n{exc}')

    def _preview(self):
        chosen = self.tree.selection()
        if not chosen:
            messagebox.showinfo('תצוגה מקדימה', 'בחר תחילה קובץ מהרשימה')
            return
        window = tk.Toplevel(self)
        window.title('תצוגה מקדימה — עמוד ראשון')
        window.geometry('1040x680')
        holder = ttk.Frame(window, padding=12)
        holder.pack(fill='both', expand=True)
        views = ttk.Frame(holder)
        views.pack(fill='both', expand=True)
        try:
            with fitz.open(chosen[0]) as pdf:
                pix = pdf[0].get_pixmap(matrix=fitz.Matrix(1.0, 1.0), colorspace=fitz.csRGB, alpha=False)
                original = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            max_h, max_w = 580, 470
            original.thumbnail((max_w, max_h))
            modified = ImageOps.grayscale(original)
            selected = self.mode.get()
            if selected in ('bw', 'bw-clean', 'jbig2'):
                if selected == 'bw-clean':
                    modified = ImageOps.autocontrast(modified, cutoff=1)
                modified = modified.point(lambda v: 255 if v >= 190 else 0, mode='1')
            frame_left = ttk.Frame(views)
            frame_right = ttk.Frame(views)
            frame_left.pack(side='left', expand=True, fill='both')
            frame_right.pack(side='right', expand=True, fill='both')
            for frame, title, im in ((frame_left, 'מקור', original), (frame_right, 'הדגמת ההמרה', modified)):
                ttk.Label(frame, text=title, font=('Segoe UI', 12, 'bold')).pack(pady=4)
                photo = ImageTk.PhotoImage(im)
                label = ttk.Label(frame, image=photo)
                label.image = photo
                label.pack(expand=True)
            ttk.Label(holder, text='הדמיה בלבד: אינה משקפת את גודל הקובץ הסופי, דחיסה או OCR.', anchor='e').pack(fill='x')
        except Exception as exc:
            window.destroy()
            messagebox.showerror('שגיאת תצוגה', str(exc))

    def _remove(self):
        if self.running:
            return
        for item in self.tree.selection():
            self.tree.delete(item)
            self.files.remove(item)

    def _clear(self):
        if self.running:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.files.clear()

    def _browse(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder.set(folder)

    def _start(self):
        if self.running or not self.files:
            return
        if self.mode.get() in ('bw', 'bw-clean', 'jbig2') and not messagebox.askyesno('אזהרת שכבת טקסט',
            'המרת שחור־לבן משטחת דפים לתמונות ועלולה לבטל OCR, טקסט ניתן לבחירה, קישורים וסימניות. להמשיך?'):
            return
        self.running = True
        self.cancel_event.clear()
        self.cancel_button.configure(state='normal')
        self.start_button.configure(state='disabled')
        self.progress['maximum'] = len(self.files)
        self.progress['value'] = 0
        tasks = list(self.files)
        threading.Thread(target=self._worker, args=(tasks, self.mode.get(), int(self.dpi.get()),
                          self.folder.get(), self.keep.get(), int(self.workers.get()), self.preserve_ocr.get()), daemon=True).start()

    def _cancel(self):
        self.cancel_event.set()
        self.status.set('מבטל לאחר העמוד הנוכחי...')

    def _worker(self, paths, mode, dpi, folder, keep, workers, preserve_ocr):
        output_dir = Path(folder)
        for index, name in enumerate(paths):
            if self.cancel_event.is_set():
                break
            source = Path(name)
            target = output_dir / f'{source.stem}_{mode}.pdf'
            i = 2
            while target.exists() or target.resolve() == source.resolve():
                target = output_dir / f'{source.stem}_{mode}_{i}.pdf'
                i += 1
            try:
                result = convert(source, target, mode, dpi, keep, workers=workers,
                                 preserve_ocr=preserve_ocr, cancel=self.cancel_event)
                saving = (1-result['new_bytes']/max(1,result['old_bytes']))*100
                message = f"{human_size(result['new_bytes'])} | חיסכון {saving:.1f}%"
                if result['original_kept']:
                    message += ' | המקור נשמר'
            except Exception as exc:
                message = 'שגיאה: ' + str(exc)[:120]
            self.events.put(('row', name, message, index+1))
        self.events.put(('done',))

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'row':
                    _, name, message, progress = event
                    if self.tree.exists(name):
                        vals = list(self.tree.item(name, 'values'))
                        vals[3] = message
                        self.tree.item(name, values=vals)
                    self.progress['value'] = progress
                    self.status.set(f'טופלו {progress} מתוך {len(self.files)}')
                else:
                    self.running = False
                    self.start_button.configure(state='normal')
                    self.cancel_button.configure(state='disabled')
                    self.status.set('בוטל' if self.cancel_event.is_set() else 'העיבוד הסתיים; קבצי המקור לא שונו')
        except queue.Empty:
            pass
        self.after(100, self._poll)

if __name__ == '__main__':
    App().mainloop()
