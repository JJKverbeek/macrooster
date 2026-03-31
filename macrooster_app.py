#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import macrooster_core
from macrooster_setup import SetupWizard

APP_NAME = "MacRooster"
TEXT = "#1f1f1f"
MUTED = "#6b6b6b"
BG = "#ffffff"
RED = "#DA291C"
GOLD = "#FFC72C"
SURFACE = "#FFF8F2"
BORDER = "#E7DDD4"
BUTTON_BG = "#F5F2EF"
DELETE_BG = "#FFF1F0"


def resource_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / relative_path
    return Path(__file__).resolve().parent / relative_path


def run_background_check() -> int:
    config = macrooster_core.load_config()
    if not config.get("email_address") or not config.get("email_password"):
        return 1
    macrooster_core.run_check(config)
    return 0


def ensure_app_in_applications() -> bool:
    if not getattr(sys, "frozen", False):
        return True

    app_bundle = Path(sys.executable).resolve().parents[2]
    if app_bundle.parent == Path("/Applications"):
        return True

    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        "Sleep Eerst Naar Programma's",
        "Sleep MacRooster eerst naar de map Programma's en open de app daarna vanuit Programma's.",
        parent=root,
    )
    root.destroy()
    return False


def setup_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), "--setup"]
    return [sys.executable, str(Path(__file__).resolve()), "--setup"]


def is_configured() -> bool:
    config = macrooster_core.load_config()
    return bool(config.get("email_address") and config.get("email_password"))


class HomeWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("MacRooster")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.logo_img: tk.PhotoImage | None = None
        self.small_logo_img: tk.PhotoImage | None = None
        self._apply_window_icon()
        self._build_ui()

    def _apply_window_icon(self) -> None:
        logo_path = resource_path("assets/macrooster-logo.png")
        if not logo_path.exists():
            return
        try:
            icon = tk.PhotoImage(file=str(logo_path))
        except tk.TclError:
            return
        self.small_logo_img = icon.subsample(max(icon.width() // 64, 1), max(icon.height() // 64, 1))
        self.root.iconphoto(True, self.small_logo_img)

    def _load_logo(self, max_size: int) -> tk.PhotoImage | None:
        logo_path = resource_path("assets/macrooster-logo.png")
        if not logo_path.exists():
            return None
        try:
            image = tk.PhotoImage(file=str(logo_path))
        except tk.TclError:
            return None

        scale = max(image.width() / max_size, image.height() / max_size, 1)
        divisor = max(int(scale), 1)
        return image.subsample(divisor, divisor)

    def _build_ui(self) -> None:
        w, h = 640, 520
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        body = tk.Frame(self.root, bg=BG, padx=28, pady=24)
        body.pack(fill="both", expand=True)

        config = macrooster_core.load_config()
        hero = tk.Frame(body, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER, padx=20, pady=20)
        hero.pack(fill="x")

        left = tk.Frame(hero, bg=SURFACE)
        left.pack(side="left", fill="y")
        right = tk.Frame(hero, bg=SURFACE)
        right.pack(side="left", fill="both", expand=True, padx=(18, 0))

        self.logo_img = self._load_logo(108)
        logo_holder = tk.Frame(left, bg="white", width=116, height=116, highlightthickness=1, highlightbackground=BORDER)
        logo_holder.pack()
        logo_holder.pack_propagate(False)
        if self.logo_img is not None:
            tk.Label(logo_holder, image=self.logo_img, bg="white").pack(expand=True)
        else:
            tk.Label(logo_holder, text="M", font=("Helvetica Neue", 44, "bold"), bg="white", fg=RED).pack(expand=True)

        tk.Label(
            right,
            text="MacRooster",
            font=("Helvetica Neue", 28, "bold"),
            bg=SURFACE,
            fg=TEXT,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            right,
            text="Je werkrooster automatisch uit e-mail naar Apple Agenda.",
            font=("Helvetica Neue", 13),
            bg=SURFACE,
            fg=MUTED,
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(6, 14))

        stats = tk.Frame(right, bg=SURFACE)
        stats.pack(fill="x")
        self._stat_card(stats, "E-mail", config.get("email_address", "Niet ingesteld")).pack(side="left", fill="x", expand=True)
        self._stat_card(stats, "Agenda", config.get("calendar_name", "Werk")).pack(side="left", fill="x", expand=True, padx=10)
        self._stat_card(stats, "Controle", f"Elke {config.get('check_interval_hours', 24)} uur").pack(side="left", fill="x", expand=True)

        actions_title = tk.Label(
            body,
            text="Acties",
            font=("Helvetica Neue", 17, "bold"),
            bg=BG,
            fg=TEXT,
            anchor="w",
        )
        actions_title.pack(fill="x", pady=(22, 10))

        self.status_var = tk.StringVar(value="Klaar om te controleren of instellingen aan te passen.")
        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x")

        self.check_btn = self._action_button(
            actions,
            title="Nieuwe uren controleren",
            subtitle="Controleer direct of er nieuwe diensten in je mailbox staan.",
            bg=RED,
            fg="#000000",
            subtitle_fg="#000000",
            command=self.run_check,
        )
        self.check_btn.pack(fill="x")

        self.settings_btn = self._action_button(
            actions,
            title="Instellingen wijzigen",
            subtitle="Pas je e-mail, agenda, filters en herinneringen aan.",
            bg=BUTTON_BG,
            fg=TEXT,
            subtitle_fg=MUTED,
            command=self.open_settings,
        )
        self.settings_btn.pack(fill="x", pady=(12, 0))

        self.delete_btn = self._action_button(
            actions,
            title="MacRooster verwijderen",
            subtitle="Stop de achtergrondservice en verwijder alle lokale gegevens.",
            bg=DELETE_BG,
            fg="#A61B11",
            subtitle_fg="#B4534B",
            command=self.uninstall,
        )
        self.delete_btn.pack(fill="x", pady=(12, 0))

        footer = tk.Frame(body, bg=BG, pady=18)
        footer.pack(fill="x")
        status_dot = tk.Canvas(footer, width=12, height=12, bg=BG, highlightthickness=0)
        status_dot.create_oval(2, 2, 10, 10, fill=GOLD, outline=GOLD)
        status_dot.pack(side="left")

        self.status_lbl = tk.Label(
            footer,
            textvariable=self.status_var,
            font=("Helvetica Neue", 11),
            bg=BG,
            fg=MUTED,
            justify="left",
            anchor="w",
            wraplength=560,
        )
        self.status_lbl.pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _stat_card(self, parent: tk.Widget, title: str, value: str) -> tk.Frame:
        frame = tk.Frame(parent, bg="white", highlightthickness=1, highlightbackground=BORDER, padx=12, pady=10)
        tk.Label(frame, text=title.upper(), font=("Helvetica Neue", 10, "bold"), bg="white", fg=MUTED, anchor="w").pack(fill="x")
        tk.Label(frame, text=value, font=("Helvetica Neue", 12), bg="white", fg=TEXT, anchor="w").pack(fill="x", pady=(4, 0))
        return frame

    def _action_button(
        self,
        parent: tk.Widget,
        *,
        title: str,
        subtitle: str,
        bg: str,
        fg: str,
        subtitle_fg: str,
        command,
    ) -> tk.Button:
        button = tk.Button(
            parent,
            command=command,
            bg=bg,
            activebackground=bg,
            fg=fg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            padx=18,
            pady=16,
            cursor="hand2",
            anchor="w",
            justify="left",
            font=("Helvetica Neue", 13, "bold"),
            text=f"{title}\n{subtitle}",
        )
        button.configure(
            disabledforeground=fg,
            wraplength=560,
        )
        return button

    def run(self) -> None:
        self.root.mainloop()

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.check_btn.config(state=state)
        self.settings_btn.config(state=state)
        self.delete_btn.config(state=state)

    def run_check(self) -> None:
        self.set_busy(True)
        self.status_var.set("Bezig met controleren op nieuwe uren…")
        thread = threading.Thread(target=self._run_check_worker, daemon=True)
        thread.start()

    def _run_check_worker(self) -> None:
        try:
            config = macrooster_core.load_config()
            if not config.get("email_address") or not config.get("email_password"):
                raise RuntimeError("Vul eerst je e-mailadres en wachtwoord in via Instellingen wijzigen.")
            added = macrooster_core.run_check(config)
            self.root.after(0, lambda: self._finish_check(added, None))
        except Exception as exc:
            self.root.after(0, lambda: self._finish_check(0, str(exc)))

    def _finish_check(self, added: int, error: str | None) -> None:
        self.set_busy(False)
        if error:
            self.status_var.set(f"Controle mislukt: {error}")
            messagebox.showerror("Controle mislukt", error, parent=self.root)
            return

        if added > 0:
            msg = f"{added} nieuwe dienst(en) toegevoegd aan je agenda."
        else:
            msg = "Geen nieuwe diensten gevonden."
        self.status_var.set(msg)
        messagebox.showinfo("Controle klaar", msg, parent=self.root)

    def open_settings(self) -> None:
        subprocess.Popen(setup_command())
        self.status_var.set("De instellingenwizard is geopend in een nieuw venster.")

    def uninstall(self) -> None:
        if not messagebox.askyesno(
            "MacRooster verwijderen",
            "Weet je zeker dat je MacRooster wilt verwijderen?\n\n"
            "Dit stopt de achtergrondservice en verwijdert je instellingen.",
            parent=self.root,
        ):
            return

        try:
            self._remove_background_service()
            shutil.rmtree(macrooster_core.APP_DIR, ignore_errors=True)
            if getattr(sys, "frozen", False):
                self._schedule_app_removal()
                final_msg = (
                    "MacRooster is verwijderd.\n\n"
                    "De app wordt nu afgesloten en daarna automatisch verwijderd uit Programma's."
                )
            else:
                final_msg = "MacRooster instellingen en achtergrondservice zijn verwijderd."
            messagebox.showinfo("Verwijderd", final_msg, parent=self.root)
            self.root.destroy()
        except Exception as exc:
            messagebox.showerror("Verwijderen mislukt", str(exc), parent=self.root)

    def _remove_background_service(self) -> None:
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.macrooster.app.plist"
        uid = str(getattr(os, "getuid", lambda: 0)())
        for cmd in (
            ["launchctl", "bootout", f"gui/{uid}", str(plist_path)],
            ["launchctl", "unload", str(plist_path)],
        ):
            subprocess.run(cmd, capture_output=True, text=True)
        if plist_path.exists():
            plist_path.unlink()

    def _schedule_app_removal(self) -> None:
        app_bundle = Path(sys.executable).resolve().parents[2]
        script_path = Path("/tmp") / f"macrooster_uninstall_{os.getpid()}.sh"
        script_path.write_text(
            "#!/bin/sh\n"
            "sleep 2\n"
            f"rm -rf {shlex.quote(str(app_bundle))}\n"
            f"rm -f {shlex.quote(str(script_path))}\n",
            encoding="utf-8",
        )
        script_path.chmod(0o700)
        subprocess.Popen(["/bin/sh", str(script_path)], start_new_session=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="McDonald's rooster automatisch uit e-mail naar Apple Agenda",
    )
    parser.add_argument("--run-check", action="store_true", help="Voer achtergrondcontrole uit")
    parser.add_argument("--status", action="store_true", help="Toon status in Terminal")
    parser.add_argument("--reset", action="store_true", help="Wis verwerkte status")
    parser.add_argument("--setup", action="store_true", help="Open de grafische setupwizard")
    args = parser.parse_args()

    if args.run_check:
        sys.exit(run_background_check())

    if args.status:
        macrooster_core.show_status()
        return

    if args.reset:
        if macrooster_core.STATE_FILE.exists():
            macrooster_core.STATE_FILE.unlink()
            print("✓ Staat gewist. Alle e-mails worden bij de volgende run opnieuw verwerkt.")
        else:
            print("Geen staatbestand gevonden — er valt niets te wissen.")
        return

    if not ensure_app_in_applications():
        return

    if args.setup or not is_configured():
        SetupWizard().run()
        return

    HomeWindow().run()


if __name__ == "__main__":
    main()
