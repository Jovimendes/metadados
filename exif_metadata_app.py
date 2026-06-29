import calendar
import json
import re
import subprocess
import threading
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


EXIFTOOL = Path(r"C:\Program Files\ExifToolGUI\exiftool.exe")
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".png",
    ".heic",
    ".heif",
    ".webp",
}
VIDEO_EXTENSIONS = {
    ".mov",
    ".mp4",
    ".mpg",
    ".mpeg",
}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
CLEAR_LOCATION = "clear_location"

MONTH_NAMES = [
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def normalize_path_key(path_value):
    if not path_value:
        return ""
    return str(Path(path_value)).replace("/", "\\").lower()


def first_present(item, names):
    for name in names:
        value = item.get(name)
        if value:
            return value
    return ""


def date_from_filename(path):
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", path.name)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}-{month}-{day} (nome do arquivo)"


def format_location(item):
    gps = get_gps(item)
    if gps:
        lat, lon = gps
        return f"{lat:.6f}, {lon:.6f}"
    position = item.get("GPSPosition")
    if position:
        return str(position)
    return "Sem GPS"


def get_gps(item):
    lat = item.get("GPSLatitude")
    lon = item.get("GPSLongitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return lat, lon
    coordinates = item.get("GPSCoordinates")
    if coordinates:
        numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", str(coordinates))
        if len(numbers) >= 2:
            return float(numbers[0]), float(numbers[1])
    return None


def is_video(path):
    return path.suffix.lower() in VIDEO_EXTENSIONS


def split_file_batches(files, base_args, max_command_chars=24000, max_batch_files=None):
    base_length = len(subprocess.list2cmdline([str(arg) for arg in base_args]))
    batch = []
    batch_length = base_length
    for path in files:
        path_arg = str(path)
        path_length = len(subprocess.list2cmdline([path_arg])) + 1
        batch_is_full = max_batch_files and len(batch) >= max_batch_files
        command_is_long = batch_length + path_length > max_command_chars
        if batch and (batch_is_full or command_is_long):
            yield batch
            batch = []
            batch_length = base_length
        batch.append(path)
        batch_length += path_length
    if batch:
        yield batch


class DatePicker(tk.Toplevel):
    def __init__(self, master, initial_date, callback):
        super().__init__(master)
        self.title("Selecionar data")
        self.resizable(False, False)
        self.callback = callback
        self.selected = initial_date or date.today()
        self.year = tk.IntVar(value=self.selected.year)
        self.month = tk.IntVar(value=self.selected.month)

        self.transient(master)
        self.grab_set()

        top = ttk.Frame(self, padding=10)
        top.grid(row=0, column=0, sticky="nsew")

        ttk.Button(top, text="<", width=3, command=self.previous_month).grid(row=0, column=0)
        self.month_combo = ttk.Combobox(top, values=MONTH_NAMES, state="readonly", width=12)
        self.month_combo.current(self.month.get() - 1)
        self.month_combo.grid(row=0, column=1, columnspan=2, padx=4)
        self.month_combo.bind("<<ComboboxSelected>>", self.month_changed)

        self.year_spin = ttk.Spinbox(
            top,
            from_=1900,
            to=2100,
            textvariable=self.year,
            width=6,
            command=self.render_days,
        )
        self.year_spin.grid(row=0, column=3, columnspan=2, padx=4)
        self.year_spin.bind("<Return>", self.render_days)
        self.year_spin.bind("<FocusOut>", self.render_days)
        ttk.Button(top, text=">", width=3, command=self.next_month).grid(row=0, column=6)

        weekdays = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
        for col, label in enumerate(weekdays):
            ttk.Label(top, text=label, width=5, anchor="center").grid(row=1, column=col, pady=(8, 2))

        self.days_frame = ttk.Frame(top)
        self.days_frame.grid(row=2, column=0, columnspan=7)

        ttk.Button(top, text="Hoje", command=self.pick_today).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(top, text="Cancelar", command=self.destroy).grid(row=3, column=4, columnspan=3, sticky="ew", pady=(10, 0))

        self.render_days()

    def month_changed(self, _event=None):
        self.month.set(self.month_combo.current() + 1)
        self.render_days()

    def previous_month(self):
        month = self.month.get() - 1
        year = self.year.get()
        if month == 0:
            month = 12
            year -= 1
        self.month.set(month)
        self.year.set(year)
        self.month_combo.current(month - 1)
        self.render_days()

    def next_month(self):
        month = self.month.get() + 1
        year = self.year.get()
        if month == 13:
            month = 1
            year += 1
        self.month.set(month)
        self.year.set(year)
        self.month_combo.current(month - 1)
        self.render_days()

    def pick_today(self):
        self.select_day(date.today())

    def select_day(self, selected_date):
        self.callback(selected_date)
        self.destroy()

    def render_days(self):
        for widget in self.days_frame.winfo_children():
            widget.destroy()

        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self.year.get(), self.month.get())

        for row, week in enumerate(weeks):
            for col, day in enumerate(week):
                in_month = day.month == self.month.get()
                button = ttk.Button(
                    self.days_frame,
                    text=str(day.day),
                    width=5,
                    command=lambda chosen=day: self.select_day(chosen),
                )
                button.grid(row=row, column=col, padx=1, pady=1)
                if not in_month:
                    button.state(["disabled"])


class ExifMetadataApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Alterador de Metadados EXIF")
        self.geometry("1040x680")
        self.minsize(900, 560)

        self.folder_var = tk.StringVar()
        self.new_date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        self.time_var = tk.StringVar(value="12:00:00")
        self.city_var = tk.StringVar()
        self.coords_var = tk.StringVar(value="Coordenadas: nao pesquisadas")
        self.change_date_var = tk.BooleanVar(value=True)
        self.change_location_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Selecione uma pasta para comecar.")
        self.progress_var = tk.DoubleVar(value=0)
        self.files = []
        self.selected_files = {}
        self.coordinates = None
        self.city_lookup_after = None
        self.reverse_city_cache = {}

        self.create_widgets()
        self.validate_exiftool()

    def create_widgets(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        folder_bar = ttk.Frame(root)
        folder_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        folder_bar.columnconfigure(1, weight=1)

        ttk.Label(folder_bar, text="Pasta").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(folder_bar, textvariable=self.folder_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(folder_bar, text="Buscar...", command=self.choose_folder).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(folder_bar, text="Carregar midias", command=self.scan_folder).grid(row=0, column=3, padx=(8, 0))

        table_frame = ttk.Frame(root)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("selected", "file", "photo_date", "photo_location", "photo_city")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("selected", text="Alterar")
        self.tree.heading("file", text="Nome do arquivo")
        self.tree.heading("photo_date", text="Data")
        self.tree.heading("photo_location", text="GPS")
        self.tree.heading("photo_city", text="Cidade")
        self.tree.column("selected", width=70, anchor="center", stretch=False)
        self.tree.column("file", width=520, anchor="w")
        self.tree.column("photo_date", width=170, anchor="w")
        self.tree.column("photo_location", width=190, anchor="w")
        self.tree.column("photo_city", width=180, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Button-1>", self.on_table_click)

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=yscroll.set)

        selection_bar = ttk.Frame(root)
        selection_bar.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        selection_bar.columnconfigure(4, weight=1)
        ttk.Button(selection_bar, text="Marcar todas", command=self.select_all_files).grid(row=0, column=0, sticky="w")
        ttk.Button(selection_bar, text="Desmarcar todas", command=self.clear_all_files).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(selection_bar, text="Marcar selecionadas", command=self.mark_selected_files).grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Label(selection_bar, text="Selecione linhas com Ctrl/Shift ou clique em [x] / [ ].").grid(row=0, column=3, sticky="w", padx=(12, 0))

        form = ttk.LabelFrame(root, text="Novos metadados", padding=12)
        form.grid(row=3, column=0, sticky="ew", pady=(12, 8))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(4, weight=1)

        ttk.Checkbutton(form, text="Alterar data", variable=self.change_date_var).grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.new_date_var, width=14).grid(row=0, column=1, sticky="w", padx=(8, 4))
        ttk.Button(form, text="Calendario...", command=self.open_date_picker).grid(row=0, column=2, sticky="w")
        ttk.Label(form, text="Hora").grid(row=0, column=3, sticky="e", padx=(16, 8))
        ttk.Entry(form, textvariable=self.time_var, width=10).grid(row=0, column=4, sticky="w")

        ttk.Checkbutton(form, text="Alterar local", variable=self.change_location_var).grid(row=1, column=0, sticky="w", pady=(10, 0))
        city_entry = ttk.Entry(form, textvariable=self.city_var)
        city_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 4), pady=(10, 0))
        city_entry.bind("<KeyRelease>", self.schedule_city_lookup)
        ttk.Button(form, text="Pesquisar cidade", command=self.lookup_city).grid(row=1, column=3, sticky="w", padx=(16, 8), pady=(10, 0))
        ttk.Label(form, textvariable=self.coords_var).grid(row=1, column=4, sticky="w", pady=(10, 0))

        action_bar = ttk.Frame(root)
        action_bar.grid(row=4, column=0, sticky="ew")
        action_bar.columnconfigure(0, weight=1)
        ttk.Label(action_bar, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Progressbar(
            action_bar,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
            length=180,
        ).grid(row=0, column=1, sticky="e", padx=(8, 12))
        ttk.Button(action_bar, text="Aplicar metadados na pasta", command=self.apply_metadata).grid(row=0, column=2, sticky="e")

    def validate_exiftool(self):
        if not EXIFTOOL.exists():
            messagebox.showerror(
                "ExifTool nao encontrado",
                f"Nao encontrei o ExifTool em:\n{EXIFTOOL}",
            )
            self.status_var.set("ExifTool nao encontrado.")

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Selecione a pasta com imagens e videos")
        if folder:
            self.folder_var.set(folder)
            self.scan_folder()

    def scan_folder(self):
        folder = Path(self.folder_var.get().strip())
        if not folder.exists() or not folder.is_dir():
            messagebox.showwarning("Pasta invalida", "Selecione uma pasta existente.")
            return
        if not EXIFTOOL.exists():
            self.validate_exiftool()
            return

        self.set_busy("Lendo arquivos e metadados...")
        threading.Thread(target=self.scan_worker, args=(folder,), daemon=True).start()

    def scan_worker(self, folder):
        media_files = [path for path in folder.rglob("*") if path.suffix.lower() in MEDIA_EXTENSIONS]
        rows = []
        if media_files:
            base_args = [
                str(EXIFTOOL),
                "-json",
                "-n",
                "-DateTimeOriginal",
                "-CreateDate",
                "-ModifyDate",
                "-MediaCreateDate",
                "-MediaModifyDate",
                "-TrackCreateDate",
                "-TrackModifyDate",
                "-FileModifyDate",
                "-GPSLatitude",
                "-GPSLongitude",
                "-GPSPosition",
                "-GPSCoordinates",
            ]
            metadata = []
            errors = []
            try:
                for batch in split_file_batches(media_files, base_args):
                    args = [*base_args, *[str(path) for path in batch]]
                    result = subprocess.run(
                        args,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    if result.stdout.strip():
                        metadata.extend(json.loads(result.stdout))
                    if result.returncode != 0:
                        errors.append(result.stderr.strip() or "Falha ao ler um lote de arquivos.")
            except (OSError, json.JSONDecodeError) as exc:
                self.after(0, lambda error=str(exc): self.scan_failed(error))
                return

            if errors and not metadata:
                self.after(0, lambda: self.scan_failed("\n\n".join(errors)))
                return
            metadata_by_source = {
                normalize_path_key(item.get("SourceFile", "")): item
                for item in metadata
            }
            for media_file in media_files:
                item = metadata_by_source.get(normalize_path_key(media_file))
                if not item:
                    item = {}
                photo_date = first_present(
                    item,
                    [
                        "DateTimeOriginal",
                        "CreateDate",
                        "ModifyDate",
                        "MediaCreateDate",
                        "MediaModifyDate",
                        "TrackCreateDate",
                        "TrackModifyDate",
                        "FileModifyDate",
                    ],
                )
                if not photo_date:
                    photo_date = date_from_filename(media_file) or "Sem data EXIF"
                location = format_location(item)
                gps = get_gps(item)
                city = self.reverse_geocode_city(*gps) if gps else "Sem GPS"
                rows.append((media_file, photo_date, location, city))

        self.after(0, lambda: self.populate_table(rows))

    def scan_failed(self, output):
        self.set_ready("Falha ao ler arquivos e metadados.")
        messagebox.showerror("Erro ao carregar pasta", output or "Nao foi possivel ler os arquivos.")

    def populate_table(self, rows):
        self.files = [row[0] for row in rows]
        self.selected_files = {str(path): True for path in self.files}
        for item in self.tree.get_children():
            self.tree.delete(item)
        base = Path(self.folder_var.get().strip())
        for image, photo_date, location, city in rows:
            display_name = str(image.relative_to(base)) if image.is_relative_to(base) else image.name
            self.tree.insert(
                "",
                "end",
                iid=str(image),
                values=("[x]", display_name, photo_date, location, city),
            )
        self.set_ready(f"{len(rows)} arquivo(s) encontrado(s), {len(rows)} marcado(s) para alterar.")

    def on_table_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        column = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if region != "cell" or column != "#1" or not row_id:
            return
        self.toggle_file_selection(row_id)

    def toggle_file_selection(self, row_id):
        selected = not self.selected_files.get(row_id, True)
        self.selected_files[row_id] = selected
        values = list(self.tree.item(row_id, "values"))
        values[0] = "[x]" if selected else "[ ]"
        self.tree.item(row_id, values=values)
        self.update_selection_status()

    def select_all_files(self):
        for row_id in self.tree.get_children():
            self.selected_files[row_id] = True
            values = list(self.tree.item(row_id, "values"))
            values[0] = "[x]"
            self.tree.item(row_id, values=values)
        self.update_selection_status()

    def mark_selected_files(self):
        selected_rows = self.tree.selection()
        if not selected_rows:
            messagebox.showwarning(
                "Nenhuma linha selecionada",
                "Selecione uma ou mais linhas da tabela usando Ctrl ou Shift.",
            )
            return
        for row_id in selected_rows:
            self.selected_files[row_id] = True
            values = list(self.tree.item(row_id, "values"))
            values[0] = "[x]"
            self.tree.item(row_id, values=values)
        self.update_selection_status()

    def clear_all_files(self):
        for row_id in self.tree.get_children():
            self.selected_files[row_id] = False
            values = list(self.tree.item(row_id, "values"))
            values[0] = "[ ]"
            self.tree.item(row_id, values=values)
        self.update_selection_status()

    def get_selected_files(self):
        return [
            path
            for path in self.files
            if self.selected_files.get(str(path), False)
        ]

    def update_selection_status(self):
        total = len(self.files)
        selected = len(self.get_selected_files())
        self.status_var.set(f"{total} arquivo(s) carregado(s), {selected} marcado(s) para alterar.")

    def reverse_geocode_city(self, lat, lon):
        cache_key = (round(lat, 4), round(lon, 4))
        if cache_key in self.reverse_city_cache:
            return self.reverse_city_cache[cache_key]

        try:
            query = urllib.parse.urlencode({
                "lat": lat,
                "lon": lon,
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 10,
            })
            request = urllib.request.Request(
                f"https://nominatim.openstreetmap.org/reverse?{query}",
                headers={"User-Agent": "ExifMetadataApp/1.0"},
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                result = json.loads(response.read().decode("utf-8"))
            address = result.get("address", {})
            city = (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
                or address.get("county")
                or address.get("state")
                or "Cidade nao encontrada"
            )
        except Exception:
            city = "Cidade nao encontrada"

        self.reverse_city_cache[cache_key] = city
        return city

    def open_date_picker(self):
        initial = self.parse_date(silent=True) or date.today()
        DatePicker(self, initial, lambda selected: self.new_date_var.set(selected.strftime("%Y-%m-%d")))

    def schedule_city_lookup(self, _event=None):
        if self.city_lookup_after:
            self.after_cancel(self.city_lookup_after)
        self.city_lookup_after = self.after(900, self.lookup_city)

    def lookup_city(self):
        city = self.city_var.get().strip()
        if len(city) < 3:
            self.coordinates = None
            self.coords_var.set("Coordenadas: digite uma cidade")
            return

        self.coords_var.set("Coordenadas: pesquisando...")
        threading.Thread(target=self.lookup_city_worker, args=(city,), daemon=True).start()

    def lookup_city_worker(self, city):
        try:
            query = urllib.parse.urlencode({"q": city, "format": "json", "limit": 1})
            request = urllib.request.Request(
                f"https://nominatim.openstreetmap.org/search?{query}",
                headers={"User-Agent": "ExifMetadataApp/1.0"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                results = json.loads(response.read().decode("utf-8"))
            if not results:
                self.after(0, lambda: self.city_not_found(city))
                return
            first = results[0]
            lat = float(first["lat"])
            lon = float(first["lon"])
            label = first.get("display_name", city)
            self.after(0, lambda: self.city_found(lat, lon, label))
        except Exception as exc:
            self.after(0, lambda: self.city_lookup_failed(exc))

    def city_found(self, lat, lon, label):
        self.coordinates = (lat, lon)
        self.coords_var.set(f"Coordenadas: {lat:.6f}, {lon:.6f}")
        self.status_var.set(f"Cidade encontrada: {label}")

    def city_not_found(self, city):
        self.coordinates = None
        self.coords_var.set("Coordenadas: nao encontradas")
        self.status_var.set(f"Nao encontrei coordenadas para: {city}")

    def city_lookup_failed(self, exc):
        self.coordinates = None
        self.coords_var.set("Coordenadas: erro na pesquisa")
        self.status_var.set(f"Falha ao buscar cidade: {exc}")

    def parse_date(self, silent=False):
        try:
            return datetime.strptime(self.new_date_var.get().strip(), "%Y-%m-%d").date()
        except ValueError:
            if not silent:
                messagebox.showwarning("Data invalida", "Use o formato AAAA-MM-DD ou selecione pelo calendario.")
            return None

    def parse_time(self):
        raw = self.time_var.get().strip()
        try:
            datetime.strptime(raw, "%H:%M:%S")
            return raw
        except ValueError:
            messagebox.showwarning("Hora invalida", "Use o formato HH:MM:SS.")
            return None

    def apply_metadata(self):
        folder = Path(self.folder_var.get().strip())
        if not folder.exists() or not folder.is_dir():
            messagebox.showwarning("Pasta invalida", "Selecione uma pasta existente.")
            return
        if not self.files:
            messagebox.showwarning("Sem arquivos", "Carregue uma pasta com imagens ou videos antes de aplicar.")
            return
        selected_files = self.get_selected_files()
        if not selected_files:
            messagebox.showwarning("Nenhum arquivo marcado", "Marque pelo menos um arquivo para alterar.")
            return
        if not self.change_date_var.get() and not self.change_location_var.get():
            messagebox.showwarning("Nenhuma opcao marcada", "Marque alterar data, alterar local, ou ambos.")
            return

        date_value = None
        if self.change_date_var.get():
            chosen_date = self.parse_date()
            chosen_time = self.parse_time()
            if not chosen_date or not chosen_time:
                return
            date_value = f"{chosen_date.strftime('%Y:%m:%d')} {chosen_time}"

        coordinates = None
        if self.change_location_var.get():
            if not self.city_var.get().strip():
                self.coordinates = None
                coordinates = CLEAR_LOCATION
            elif not self.coordinates:
                messagebox.showwarning("Local sem coordenadas", "Pesquise uma cidade valida antes de aplicar o local.")
                return
            else:
                coordinates = self.coordinates

        confirm = messagebox.askyesno(
            "Confirmar alteracao",
            f"Aplicar metadados em {len(selected_files)} arquivo(s) marcado(s)?\n\n"
            "Os arquivos originais serao alterados diretamente, sem criar backup _original.",
        )
        if not confirm:
            return

        self.progress_var.set(0)
        self.set_busy(f"Aplicando metadados... 0% (0/{len(selected_files)})")
        threading.Thread(target=self.apply_worker, args=(date_value, coordinates, selected_files), daemon=True).start()

    def apply_worker(self, date_value, coordinates, selected_files):
        image_files = [path for path in selected_files if not is_video(path)]
        video_files = [path for path in selected_files if is_video(path)]
        total_files = len(selected_files)
        processed_files = 0
        outputs = []
        errors = []

        def report_progress(done_in_batch):
            nonlocal processed_files
            processed_files += done_in_batch
            percent = round((processed_files / total_files) * 100) if total_files else 100
            text = f"Aplicando metadados... {percent}% ({processed_files}/{total_files})"
            self.after(0, lambda: self.set_apply_progress(percent, text))

        if image_files:
            result = self.run_exiftool_update(
                self.build_image_update_args(date_value, coordinates),
                image_files,
                progress_callback=report_progress,
            )
            outputs.append(result.stdout.strip())
            if result.returncode != 0:
                errors.append(result.stderr.strip() or result.stdout.strip())

        if video_files:
            result = self.run_exiftool_update(
                self.build_video_update_args(date_value, coordinates),
                video_files,
                progress_callback=report_progress,
            )
            outputs.append(result.stdout.strip())
            if result.returncode != 0:
                errors.append(result.stderr.strip() or result.stdout.strip())

        if errors:
            self.after(0, lambda: self.apply_failed("\n\n".join(error for error in errors if error)))
            return
        output = "\n".join(part for part in outputs if part)
        self.after(0, lambda: self.apply_finished(output))

    def build_image_update_args(self, date_value, coordinates):
        args = []
        if date_value:
            args.extend([
                f"-DateTimeOriginal={date_value}",
                f"-CreateDate={date_value}",
                f"-ModifyDate={date_value}",
            ])
        if coordinates == CLEAR_LOCATION:
            args.extend(self.build_clear_location_args(include_video_tags=False))
        elif coordinates:
            lat, lon = coordinates
            args.extend([
                f"-GPSLatitude={abs(lat)}",
                f"-GPSLongitude={abs(lon)}",
                f"-GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
                f"-GPSLongitudeRef={'E' if lon >= 0 else 'W'}",
            ])
        return args

    def build_video_update_args(self, date_value, coordinates):
        args = []
        if date_value:
            args.extend([
                f"-QuickTime:CreateDate={date_value}",
                f"-QuickTime:ModifyDate={date_value}",
                f"-QuickTime:TrackCreateDate={date_value}",
                f"-QuickTime:TrackModifyDate={date_value}",
                f"-QuickTime:MediaCreateDate={date_value}",
                f"-QuickTime:MediaModifyDate={date_value}",
                f"-XMP:CreateDate={date_value}",
                f"-XMP:ModifyDate={date_value}",
                f"-XMP:DateCreated={date_value}",
            ])
        if coordinates == CLEAR_LOCATION:
            args.extend(self.build_clear_location_args(include_video_tags=True))
        elif coordinates:
            lat, lon = coordinates
            signed_coordinates = f"{lat:.8f} {lon:.8f}"
            args.extend([
                f"-Keys:GPSCoordinates={signed_coordinates}",
                f"-UserData:GPSCoordinates={signed_coordinates}",
                f"-XMP:GPSLatitude={abs(lat)}",
                f"-XMP:GPSLongitude={abs(lon)}",
                f"-XMP:GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
                f"-XMP:GPSLongitudeRef={'E' if lon >= 0 else 'W'}",
            ])
        return args

    def build_clear_location_args(self, include_video_tags):
        args = [
            "-GPS:all=",
            "-XMP:GPSLatitude=",
            "-XMP:GPSLongitude=",
            "-XMP:GPSLatitudeRef=",
            "-XMP:GPSLongitudeRef=",
        ]
        if include_video_tags:
            args.extend([
                "-Keys:GPSCoordinates=",
                "-UserData:GPSCoordinates=",
                "-QuickTime:GPSCoordinates=",
            ])
        return args

    def run_exiftool_update(self, update_args, files, progress_callback=None):
        base_args = [str(EXIFTOOL), "-P", "-overwrite_original", *update_args]
        outputs = []
        errors = []
        return_code = 0
        try:
            for batch in split_file_batches(files, base_args, max_batch_files=1):
                args = [*base_args, *[str(path) for path in batch]]
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if result.stdout.strip():
                    outputs.append(result.stdout.strip())
                if result.stderr.strip():
                    errors.append(result.stderr.strip())
                if result.returncode != 0:
                    return_code = result.returncode
                if progress_callback:
                    progress_callback(len(batch))
        except OSError as exc:
            return_code = 1
            errors.append(str(exc))

        return subprocess.CompletedProcess(
            args=base_args,
            returncode=return_code,
            stdout="\n".join(outputs),
            stderr="\n".join(errors),
        )

    def apply_finished(self, output):
        self.set_ready("Metadados aplicados. Recarregando tabela...")
        self.scan_folder()
        messagebox.showinfo("Concluido", output.strip() or "Metadados aplicados com sucesso.")

    def apply_failed(self, output):
        self.set_ready("Falha ao aplicar metadados.")
        messagebox.showerror("Erro do ExifTool", output.strip() or "O ExifTool retornou erro.")

    def set_apply_progress(self, percent, text):
        self.progress_var.set(percent)
        self.status_var.set(text)

    def set_busy(self, text):
        self.status_var.set(text)
        if not text.startswith("Aplicando metadados"):
            self.progress_var.set(0)
        self.config(cursor="watch")

    def set_ready(self, text):
        self.status_var.set(text)
        if not text.startswith("Metadados aplicados"):
            self.progress_var.set(0)
        self.config(cursor="")


if __name__ == "__main__":
    app = ExifMetadataApp()
    app.mainloop()
