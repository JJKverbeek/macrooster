#!/usr/bin/env python3
# macrooster_setup.py — MacRooster grafische installatiewizard
# Vereist alleen Python 3.9+ (standaard op elke recente Mac)

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from xml.sax.saxutils import escape

APP_DIR     = Path.home() / ".macrooster"
CONFIG_FILE = APP_DIR / "config.json"
PLIST_LABEL = "com.macrooster.app"


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).parent.resolve()


SCRIPT_DIR = _resource_dir()

PROVIDERS: dict[str, tuple[str, int]] = {
    "Gmail":                   ("imap.gmail.com",         993),
    "iCloud (Apple Mail)":     ("imap.mail.me.com",       993),
    "Outlook / Microsoft 365": ("outlook.office365.com",  993),
    "KPN Mail":                ("imap.kpnmail.nl",        993),
    "Ziggo":                   ("imap.ziggo.nl",          993),
    "Anders (handmatig)":      ("",                       993),
}

COLORS: dict[str, str] = {
    "Rood (McDonald's rood)": "red",
    "Oranje":                 "orange",
    "Geel":                   "yellow",
    "Groen":                  "green",
    "Blauw":                  "blue",
    "Paars":                  "purple",
    "Bruin":                  "brown",
    "Grijs":                  "gray",
}

BG      = "#ffffff"
RED     = "#DA291C"
FONT    = "Helvetica Neue"
TEXT    = "#1f1f1f"
MUTED   = "#6b6b6b"


class SetupWizard:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("MacRooster — Installatie")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.logo_img: tk.PhotoImage | None = None
        self.small_logo_img: tk.PhotoImage | None = None
        self._apply_window_icon()

        w, h = 540, 520
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth()  - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        try:
            ttk.Style().theme_use("aqua")
        except tk.TclError:
            pass

        self._define_vars()
        self._build_ui()
        self._show_page(0)

    # ── Tkinter variables ─────────────────────────────────────────────────────

    def _define_vars(self) -> None:
        cfg = self._load_existing_config()

        self.name_var     = tk.StringVar(value=cfg.get("employee_name", ""))
        self.interval_var = tk.StringVar(value=str(cfg.get("check_interval_hours", 24)))
        self.provider_var = tk.StringVar(value=self._provider_name_for_config(cfg))
        self.imap_var     = tk.StringVar(value=cfg.get("imap_server", ""))
        self.email_var    = tk.StringVar(value=cfg.get("email_address", ""))
        self.password_var = tk.StringVar(value=cfg.get("email_password", ""))
        self.sender_var   = tk.StringVar(value=cfg.get("search_sender", "Rooster.1222@nl.mcd.com"))
        self.subject_var  = tk.StringVar(value=cfg.get("search_subject", "rooster"))
        self.cal_name_var = tk.StringVar(value=cfg.get("calendar_name", "Werk"))
        self.color_var    = tk.StringVar(value=self._color_name_for_config(cfg))
        self.alarm_var    = tk.StringVar(value=str(cfg.get("alarm_minutes_before", 120)))

    def _load_existing_config(self) -> dict:
        if not CONFIG_FILE.exists():
            return {}
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _provider_name_for_config(self, cfg: dict) -> str:
        imap_server = cfg.get("imap_server", "")
        for provider_name, (server, _port) in PROVIDERS.items():
            if provider_name != "Anders (handmatig)" and server == imap_server:
                return provider_name
        return "Anders (handmatig)" if imap_server else "Gmail"

    def _color_name_for_config(self, cfg: dict) -> str:
        current = cfg.get("calendar_color", "red")
        for label, value in COLORS.items():
            if value == current:
                return label
        return "Rood (McDonald's rood)"

    # ── UI skeleton ───────────────────────────────────────────────────────────

    def _load_logo(self, max_size: int) -> tk.PhotoImage | None:
        logo_path = SCRIPT_DIR / "assets" / "macrooster-logo.png"
        if not logo_path.exists():
            return None
        try:
            image = tk.PhotoImage(file=str(logo_path))
        except tk.TclError:
            return None

        scale = max(image.width() / max_size, image.height() / max_size, 1)
        divisor = max(int(scale), 1)
        return image.subsample(divisor, divisor)

    def _apply_window_icon(self) -> None:
        icon = self._load_logo(64)
        if icon is None:
            return
        self.small_logo_img = icon
        self.root.iconphoto(True, self.small_logo_img)

    def _build_ui(self) -> None:
        # Red header bar
        header = tk.Frame(self.root, bg=RED, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        title_wrap = tk.Frame(header, bg=RED)
        title_wrap.pack(side="left", padx=16)
        self.logo_img = self._load_logo(34)
        if self.logo_img is not None:
            tk.Label(title_wrap, image=self.logo_img, bg=RED).pack(side="left", padx=(0, 10))
        tk.Label(title_wrap, text="MacRooster",
                 font=(FONT, 22, "bold"), bg=RED, fg="white").pack(side="left")

        # Step indicator
        self.step_lbl = tk.Label(self.root, text="", font=(FONT, 11),
                                  fg="#999", bg=BG)
        self.step_lbl.pack(pady=(8, 0))

        ttk.Separator(self.root).pack(fill="x", padx=24)

        # Scrollable content area
        self.content = tk.Frame(self.root, bg=BG, padx=32, pady=12)
        self.content.pack(fill="both", expand=True)

        ttk.Separator(self.root).pack(fill="x", padx=24)

        # Navigation buttons
        nav = tk.Frame(self.root, bg=BG, pady=12, padx=24)
        nav.pack(fill="x")
        self.back_btn = ttk.Button(nav, text="← Terug",   command=self._prev)
        self.back_btn.pack(side="left")
        self.next_btn = ttk.Button(nav, text="Volgende →", command=self._next)
        self.next_btn.pack(side="right")

        self.pages = [
            self._page_welcome,
            self._page_email,
            self._page_filters,
            self._page_calendar,
            self._page_confirm,
        ]

    def _clear(self) -> None:
        for w in self.content.winfo_children():
            w.destroy()

    def _show_page(self, idx: int) -> None:
        self._clear()
        self.current = idx
        n = len(self.pages)
        self.step_lbl.config(text=f"Stap {idx + 1} van {n}")
        self.pages[idx]()
        self.back_btn.config(state="normal" if idx > 0 else "disabled")
        if idx == n - 1:
            self.next_btn.config(text="Installeren ✓", command=self._install)
        else:
            self.next_btn.config(text="Volgende →",    command=self._next)

    def _next(self) -> None:
        if self._validate():
            self._show_page(self.current + 1)

    def _prev(self) -> None:
        self._show_page(self.current - 1)

    # ── Helper widgets ────────────────────────────────────────────────────────

    def _heading(self, text: str) -> None:
        tk.Label(self.content, text=text, font=(FONT, 16, "bold"),
                 bg=BG, fg=TEXT, anchor="w").pack(fill="x", pady=(6, 12))

    def _label(self, text: str) -> None:
        tk.Label(self.content, text=text, font=(FONT, 12),
                 bg=BG, fg=TEXT, anchor="w").pack(fill="x", pady=(10, 2))

    def _entry(self, var: tk.StringVar, *, show: str = "", width: int = 34) -> ttk.Entry:
        e = ttk.Entry(self.content, textvariable=var, show=show, width=width)
        e.pack(anchor="w")
        return e

    def _tip(self, text: str) -> None:
        tk.Label(self.content, text=text, font=(FONT, 11),
                 fg=MUTED, bg=BG, justify="left", wraplength=460).pack(anchor="w", pady=(6, 0))

    # ── Pages ─────────────────────────────────────────────────────────────────

    def _page_welcome(self) -> None:
        self._heading("Welkom bij MacRooster!")
        tk.Label(self.content,
                 text=(
                     "Deze app haalt automatisch jouw werkrooster op uit\n"
                     "je e-mail en zet je diensten in Apple Agenda.\n\n"
                     "Doorloop de stappen hieronder. Dit duurt maar 2 minuten."
                 ),
                 font=(FONT, 13), bg=BG, fg=TEXT, justify="left").pack(anchor="w")

        ttk.Separator(self.content).pack(fill="x", pady=16)

        self._label("Jouw naam (precies zoals in het rooster):")
        self._entry(self.name_var)

        self._label("Hoe vaak controleren (in uren):")
        self._entry(self.interval_var, width=8)
        self._tip("Standaard: 24 uur. Vul 1 in voor elk uur, 12 voor tweemaal per dag, enz.")

    def _page_email(self) -> None:
        self._heading("E-mailinstellingen")

        self._label("E-mailprovider:")
        cb = ttk.Combobox(self.content, textvariable=self.provider_var,
                          values=list(PROVIDERS), state="readonly", width=33)
        cb.pack(anchor="w")
        cb.bind("<<ComboboxSelected>>", lambda _: self._refresh_email_hints())

        self._label("E-mailadres:")
        self._entry(self.email_var)

        self._label("Wachtwoord / App-wachtwoord:")
        self._entry(self.password_var, show="●")

        self.gmail_tip_lbl = tk.Label(self.content,
            text=(
                "ℹ  Gmail vereist een App-wachtwoord — niet je gewone wachtwoord.\n"
                "   Ga naar myaccount.google.com → Beveiliging → App-wachtwoorden."
            ),
            font=(FONT, 11), fg=MUTED, bg=BG, justify="left", wraplength=460)

        self.manual_frame = tk.Frame(self.content, bg=BG)
        tk.Label(self.manual_frame, text="IMAP-server (bijv. imap.example.com):",
                 font=(FONT, 12), bg=BG, fg=TEXT).pack(anchor="w", pady=(10, 2))
        ttk.Entry(self.manual_frame, textvariable=self.imap_var, width=34).pack(anchor="w")

        self._refresh_email_hints()

    def _refresh_email_hints(self) -> None:
        provider = self.provider_var.get()
        if provider == "Gmail":
            self.gmail_tip_lbl.pack(anchor="w", pady=(10, 0))
        else:
            self.gmail_tip_lbl.pack_forget()
        if provider == "Anders (handmatig)":
            self.manual_frame.pack(anchor="w")
        else:
            self.manual_frame.pack_forget()

    def _page_filters(self) -> None:
        self._heading("Zoekfilters")
        tk.Label(self.content,
                 text="Hoe herkent de app een rooster-e-mail? De standaardwaarden\nwerken bij de meeste McDonald's vestigingen.",
                 font=(FONT, 13), bg=BG, fg=TEXT, justify="left").pack(anchor="w")

        self._label("Deel van naam / e-mailadres van de afzender:")
        self._entry(self.sender_var)

        self._label("Trefwoord in het onderwerp:")
        self._entry(self.subject_var)

        self._tip("Weet je het niet zeker? Laat de standaardwaarden gewoon staan.")

    def _page_calendar(self) -> None:
        self._heading("Agenda-instellingen")

        self._label("Naam van de agenda in Agenda.app:")
        self._entry(self.cal_name_var, width=26)

        self._label("Agendakleur:")
        ttk.Combobox(self.content, textvariable=self.color_var,
                     values=list(COLORS), state="readonly", width=30).pack(anchor="w")

        self._label("Herinnering (minuten voor aanvang):")
        self._entry(self.alarm_var, width=8)

    def _page_confirm(self) -> None:
        self._heading("Klaar om te installeren!")
        cfg = self._build_config()
        lines = (
            f"  Naam:          {cfg['employee_name']}\n"
            f"  E-mail:        {cfg['email_address']}\n"
            f"  Provider:      {cfg['imap_server']}\n"
            f"  Agenda:        {cfg['calendar_name']}\n"
            f"  Kleur:         {cfg['calendar_color']}\n"
            f"  Interval:      elke {cfg['check_interval_hours']} uur\n"
            f"  Herinnering:   {cfg['alarm_minutes_before']} min van tevoren"
        )
        tk.Label(self.content, text=lines, font=("Courier New", 12),
                 bg="#f5f5f5", fg="#333", justify="left",
                 relief="flat", padx=12, pady=10).pack(fill="x", pady=(0, 14))

        tk.Label(self.content,
                 text="Klik op Installeren om:\n  1. pdfplumber te installeren\n  2. De configuratie op te slaan\n  3. De achtergrond-service te starten",
                 font=(FONT, 13), bg=BG, fg=TEXT, justify="left").pack(anchor="w")

        self.progress   = ttk.Progressbar(self.content, mode="indeterminate", length=460)
        self.status_lbl = tk.Label(self.content, text="", font=(FONT, 11), fg=MUTED, bg=BG)

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate(self) -> bool:
        p = self.current
        if p == 0:
            if not self.name_var.get().strip():
                messagebox.showwarning("Vereist veld", "Vul jouw naam in zoals die in het rooster staat.")
                return False
            try:
                if int(self.interval_var.get()) < 1:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Ongeldig interval", "Voer een getal van minimaal 1 in.")
                return False
        elif p == 1:
            if not self.email_var.get().strip():
                messagebox.showwarning("Vereist veld", "Vul je e-mailadres in.")
                return False
            if not self.password_var.get():
                messagebox.showwarning("Vereist veld", "Vul je wachtwoord in.")
                return False
            if self.provider_var.get() == "Anders (handmatig)" and not self.imap_var.get().strip():
                messagebox.showwarning("Vereist veld", "Vul de IMAP-server in.")
                return False
        return True

    # ── Build config dict ─────────────────────────────────────────────────────

    def _build_config(self) -> dict:
        provider = self.provider_var.get()
        server, port = PROVIDERS.get(provider, ("imap.gmail.com", 993))
        if provider == "Anders (handmatig)":
            server = self.imap_var.get().strip()

        return {
            "employee_name":        self.name_var.get().strip(),
            "check_interval_hours": int(self.interval_var.get() or 24),
            "imap_server":          server,
            "imap_port":            port,
            "email_address":        self.email_var.get().strip(),
            "email_password":       self.password_var.get(),
            "search_sender":        self.sender_var.get().strip() or "Rooster.1222@nl.mcd.com",
            "search_subject":       self.subject_var.get().strip() or "rooster",
            "calendar_name":        self.cal_name_var.get().strip() or "Werk",
            "calendar_color":       COLORS.get(self.color_var.get(), "red"),
            "alarm_minutes_before": int(self.alarm_var.get() or 120),
            "location":             "McDonald's Lemmer, Vissersburen 18, 8531 HC Lemmer",
            "notify_on_new_shifts": True,
        }

    # ── Installation ──────────────────────────────────────────────────────────

    def _install(self) -> None:
        if not self._validate():
            return
        self.next_btn.config(state="disabled")
        self.back_btn.config(state="disabled")
        self.progress.pack(anchor="w", pady=(20, 4))
        self.status_lbl.pack(anchor="w")
        self.progress.start(10)
        self.root.update()
        try:
            self._run_steps()
        except Exception as exc:
            self.progress.stop()
            self.progress.pack_forget()
            messagebox.showerror("Installatie mislukt", str(exc))
            self.next_btn.config(state="normal")
            self.back_btn.config(state="normal")

    def _status(self, text: str) -> None:
        self.status_lbl.config(text=text)
        self.root.update()

    def _run_steps(self) -> None:
        # 1. pdfplumber
        self._status("pdfplumber installeren…")
        if not getattr(sys, "frozen", False):
            self._install_pdfplumber()

        # 2. Copy scripts in source mode; packaged app uses its own bundled binary.
        self._status("Bestanden voorbereiden…")
        APP_DIR.mkdir(parents=True, exist_ok=True)
        if not getattr(sys, "frozen", False):
            for name in ("macrooster_core.py", "macrooster_setup.py", "macrooster_app.py"):
                src = SCRIPT_DIR / name
                if src.exists():
                    shutil.copy2(src, APP_DIR / name)
                    (APP_DIR / name).chmod(0o755)

        # 3. Write config
        self._status("Configuratie opslaan…")
        config = self._build_config()
        CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False))
        CONFIG_FILE.chmod(0o600)

        # 4. launchd plist
        self._status("Achtergrond-service instellen…")
        self._setup_launchd(config)

        # Done
        self.progress.stop()
        self._status("✓ Installatie voltooid!")
        messagebox.showinfo(
            "Geïnstalleerd!",
            "MacRooster is succesvol geïnstalleerd!\n\n"
            "De app controleert je e-mail automatisch op de ingestelde tijden "
            "en zet nieuwe diensten direct in je agenda.\n\n"
            "Je hoeft verder niets te doen. Je kunt dit venster sluiten."
        )
        self.root.destroy()

    def _install_pdfplumber(self) -> None:
        attempts = [
            [sys.executable, "-m", "pip", "install", "pdfplumber", "--quiet", "--break-system-packages"],
            [sys.executable, "-m", "pip", "install", "pdfplumber", "--quiet"],
            ["pip3", "install", "pdfplumber", "--quiet"],
        ]
        errors: list[str] = []

        for cmd in attempts:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
            except FileNotFoundError:
                continue

            if result.returncode == 0:
                return

            stderr = result.stderr.strip() or result.stdout.strip() or "onbekende fout"
            errors.append(f"{' '.join(cmd)} -> {stderr}")

        raise RuntimeError("pip install mislukt:\n" + "\n".join(errors))

    def _setup_launchd(self, config: dict) -> None:
        plist_dir  = Path.home() / "Library" / "LaunchAgents"
        plist_path = plist_dir / f"{PLIST_LABEL}.plist"
        plist_dir.mkdir(parents=True, exist_ok=True)

        interval = config["check_interval_hours"] * 3600
        out_log  = str(APP_DIR / "macrooster_out.log")
        err_log  = str(APP_DIR / "macrooster_err.log")
        arguments = self._service_program_arguments()
        xml_arguments = "\n".join(f"        <string>{escape(arg)}</string>" for arg in arguments)

        plist_path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>             <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{xml_arguments}
    </array>
    <key>StartInterval</key>     <integer>{interval}</integer>
    <key>RunAtLoad</key>         <true/>
    <key>StandardOutPath</key>   <string>{out_log}</string>
    <key>StandardErrorPath</key> <string>{err_log}</string>
    <key>KeepAlive</key>         <false/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
""")

        uid = str(getattr(os, "getuid", lambda: 0)())
        commands = [
            ["launchctl", "bootout", f"gui/{uid}", str(plist_path)],
            ["launchctl", "unload", str(plist_path)],
        ]
        for cmd in commands:
            subprocess.run(cmd, capture_output=True, text=True)

        load_attempts = [
            ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
            ["launchctl", "load", str(plist_path)],
        ]
        last_error = "onbekende fout"
        for cmd in load_attempts:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return
            last_error = result.stderr.strip() or result.stdout.strip() or last_error

        raise RuntimeError(f"launchd activeren mislukt:\n{last_error}")

    def _service_program_arguments(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [str(Path(sys.executable).resolve()), "--run-check"]
        return [sys.executable, str(APP_DIR / "macrooster_app.py"), "--run-check"]

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    SetupWizard().run()
