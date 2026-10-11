"""Hebrew RTL-oriented desktop user interface for PDF-Slimmer."""
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from engine import convert, inspect_pdf, Cancelled

LABELS = {'smart': 'חכמה — זיהוי אוטומטי של סוג המסמך',
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
        self._build()
        self.after(100, self._poll)

    def _build(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill='both', expand=True)
        ttk.Label(root, text='PDF-Slimmer 2.0  |  דחיסה חכמה של PDF',
                  font=('Segoe UI', 18, 'bold'), anchor='e').pack(fill='x', pady=(0, 12))
        actions = ttk.Frame(root)
        actions.pack(fill='x', pady=5)
        ttk.Button(actions, text='הוסף קובצי PDF', command=self._add).pack(side='right', padx=5)
        ttk.Button(actions, text='הסר מסומנים', command=self._remove).pack(side='right', padx=5)
        ttk.Button(actions, text='נקה רשימה', command=self._clear).pack(side='right', padx=5)
        listing = ttk.Frame(root)
        listing.pack(fill='both', expand=True, pady=8)
        self.tree = ttk.Treeview(listing, columns=('file', 'size', 'pages', 'result'), show='headings', height=9)
        for key, label, width in [('file', 'שם קובץ', 350), ('size', 'גודל מקורי', 110),
                                  ('pages', 'עמודים', 75), ('result', 'תוצאה', 240)]:
            self.tree.heading(key, text=label, anchor='e')
            self.tree.column(key, width=width, anchor='e')
        bar = ttk.Scrollbar(listing, command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        options = ttk.LabelFrame(root, text='אפשרויות עיבוד', padding=10)
        options.pack(fill='x', pady=8)
        for mode in LABELS:
            ttk.Radiobutton(options, text=LABELS[mode], variable=self.mode,
                            value=mode).pack(anchor='e')
        optline = ttk.Frame(options)
        optline.pack(fill='x', pady=4)
        ttk.Checkbutton(optline, text='אם אין חיסכון, שמור עותק של המקור',
                        variable=self.keep).pack(side='right', padx=15)
        ttk.Checkbutton(optline, text='חידוש OCR במסמך סרוק המכיל טקסט', variable=self.preserve_ocr).pack(side='right', padx=10)
        ttk.Label(optline, text='תהליכים:').pack(side='right')
        ttk.Combobox(optline, values=[1,2,3,4,6,8], textvariable=self.workers, width=3, state='readonly').pack(side='right', padx=4)
        ttk.Label(optline, text='רזולוציה (DPI):').pack(side='right')
        ttk.Combobox(optline, values=[150, 200, 300, 400], textvariable=self.dpi,
                     width=6, state='readonly').pack(side='right', padx=6)
        ttk.Label(root, text='שימו לב: במצבי שחור־לבן קישורים וסימניות עשויים להימחק. לשחזור OCR דרושה התקנת OCRmyPDF.',
                  anchor='e', foreground='#9A5300').pack(fill='x')
        pathline = ttk.Frame(root)
        pathline.pack(fill='x', pady=10)
        ttk.Button(pathline, text='בחר תיקיית פלט', command=self._browse).pack(side='right')
        ttk.Entry(pathline, textvariable=self.folder, justify='right').pack(side='right', fill='x', expand=True, padx=8)
        bottom = ttk.Frame(root)
        bottom.pack(fill='x', pady=8)
        self.start_button = ttk.Button(bottom, text='התחל המרה', command=self._start)
        self.start_button.pack(side='right', padx=5)
        self.cancel_button = ttk.Button(bottom, text='בטל', command=self._cancel, state='disabled')
        self.cancel_button.pack(side='right', padx=5)
        ttk.Label(bottom, textvariable=self.status).pack(side='right', padx=15)
        self.progress = ttk.Progressbar(bottom, mode='determinate')
        self.progress.pack(side='left', fill='x', expand=True, padx=8)

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
        if self.mode.get() in ('bw', 'bw-clean') and not messagebox.askyesno('אזהרת שכבת טקסט',
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
