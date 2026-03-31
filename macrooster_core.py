#!/usr/bin/env python3
# =============================================================================
#  macrooster_core.py  —  McDonald's Rooster → Apple Calendar (automatisch)
#  
#  Wat dit doet:
#    1. Logt in op je e-mail via IMAP (Gmail, iCloud, Outlook, enz.)
#    2. Zoekt naar e-mails met een rooster van McDonald's
#    3. Extraheert de PDF-bijlage en leest jouw diensten
#    4. Schrijft de diensten DIRECT naar Apple Calendar (geen popups)
#    5. Onthoudt welke e-mails al verwerkt zijn → nooit dubbele agenda-items
#
#  Gebruik:
#    python3 macrooster_core.py --setup      ← eerste keer instellen (doe dit eerst)
#    python3 macrooster_core.py              ← e-mails controleren (ook via launchd)
#    python3 macrooster_core.py --status     ← wat is er tot nu toe verwerkt?
#    python3 macrooster_core.py --reset      ← opnieuw beginnen (wist geheugen)
#
#  Vereisten:
#    pip3 install pdfplumber            ← enige externe bibliotheek
#    Python 3.9+                        ← al aanwezig op elke recente Mac
# =============================================================================

from __future__ import annotations  # maakt type-hints compatibel met Python 3.9

import argparse
import email
import email.header
import getpass
import hashlib
import imaplib
import io
import json
import logging
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Probeer pdfplumber te importeren; geef duidelijke fout als het niet geïnstalleerd is
try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False


# =============================================================================
# SECTIE 1 — PADEN & CONSTANTEN
# =============================================================================

APP_DIR     = Path.home() / ".macrooster"
CONFIG_FILE = APP_DIR / "config.json"
STATE_FILE  = APP_DIR / "state.json"
LOG_FILE    = APP_DIR / "macrooster.log"

# Maandnamen in het Engels — AppleScript begrijpt deze altijd, ongeacht de
# systeemtaal. Dit is de sleutel tot betrouwbare datuminvoer zonder locale-problemen.
MONTH_EN = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Beschikbare agendakleuren (AppleScript RGB-kleuren)
CALENDAR_COLORS: dict[str, str] = {
    "red":    "{65535, 0, 0}",
    "orange": "{65535, 42405, 0}",
    "yellow": "{65535, 52428, 0}",
    "green":  "{0, 46000, 12000}",
    "blue":   "{0, 32768, 65535}",
    "purple": "{39321, 17476, 52428}",
    "brown":  "{39321, 26214, 13107}",
    "gray":   "{39064, 39064, 39064}",
}

# Afdeling-codes naar leesbare namen (voor de agenda-itemtitel)
DEPT_LABELS: dict[str, str] = {
    "DRI":  "Drive-Thru",
    "DRA":  "Drive-Thru Area",
    "MFY":  "McCafé / Floor",
    "FRI":  "Frites",
    "SHF":  "Shift",
    "MAN":  "Manager",
    "HOS":  "Hospitality",
    "MPS":  "MPS",
    "CAFE": "Café",
    "L-L":  "Lobby",
    "HAVI": "HAVI",
    "TBS":  "TBS",
    "TODO": "Overig",
}


# =============================================================================
# SECTIE 2 — STANDAARD CONFIGURATIE
# =============================================================================

DEFAULT_CONFIG: dict = {
    # ── Persoonlijk ──────────────────────────────────────────────────────────
    "employee_name": "",                       # jouw naam zoals in het rooster (ingevuld tijdens setup)
    "check_interval_hours": 24,               # hoe vaak e-mail controleren (in uren)

    # ── E-mail (IMAP) ────────────────────────────────────────────────────────
    "imap_server":    "imap.gmail.com",       # gmail / icloud / outlook etc.
    "imap_port":      993,                    # 993 = SSL, altijd goed
    "email_address":  "",                     # jouw e-mailadres
    "email_password": "",                     # App-wachtwoord (NIET je gewone wachtwoord!)

    # ── Zoekfilters (welke e-mails zijn roostermails?) ───────────────────────
    "search_sender":  "Rooster.1222@nl.mcd.com",            # deel van naam of e-mailadres afzender
    "search_subject": "rooster",              # trefwoord in het onderwerp

    # ── Apple Calendar ───────────────────────────────────────────────────────
    "calendar_name":  "Werk",                 # naam van de agenda in Agenda.app
    "calendar_color": "red",                  # agendakleur (red/orange/yellow/green/blue/purple/brown/gray)
    "location":       "McDonald's Lemmer, Vissersburen 18, 8531 HC Lemmer",

    # ── Meldingen ────────────────────────────────────────────────────────────
    "notify_on_new_shifts": True,             # macOS-melding bij nieuwe diensten
    "alarm_minutes_before": 120,              # herinnering X minuten voor dienst
}


# =============================================================================
# SECTIE 3 — LOGGING
# =============================================================================

def _setup_logging() -> logging.Logger:
    """Stel een logger in die naar bestand én console schrijft."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("macrooster")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # Bestand: alles opslaan (DEBUG+), max 1 MB, 3 back-ups
        fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%d-%m %H:%M:%S"))

        # Console: alleen INFO en hoger (niet te veel ruis)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(message)s"))

        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger


log = _setup_logging()


# =============================================================================
# SECTIE 4 — CONFIGURATIE LADEN / OPSLAAN
# =============================================================================

def load_config() -> dict:
    """Laad de configuratie. Ontbrekende sleutels worden aangevuld met standaardwaarden."""
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            config.update(saved)
        except Exception as exc:
            log.warning(f"Config kon niet worden geladen ({exc}), standaardwaarden gebruikt.")
    return config


def save_config(config: dict) -> None:
    """Sla de configuratie op. Bestandsrechten worden ingesteld op 600 (alleen eigenaar)."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.chmod(CONFIG_FILE, 0o600)  # beschermt je wachtwoord


# =============================================================================
# SECTIE 5 — TOESTAND (welke e-mails / diensten zijn al verwerkt?)
# =============================================================================

def load_state() -> dict:
    """Laad de verwerkte e-mail-IDs en toegevoegde dienst-UIDs."""
    if not STATE_FILE.exists():
        return {"processed_message_ids": [], "added_event_uids": []}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"processed_message_ids": [], "added_event_uids": []}


def save_state(state: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def is_email_processed(message_id: str, state: dict) -> bool:
    return message_id in state.get("processed_message_ids", [])


def mark_email_processed(message_id: str, state: dict) -> None:
    ids = state.setdefault("processed_message_ids", [])
    if message_id not in ids:
        ids.append(message_id)
    state["processed_message_ids"] = ids[-500:]  # houd het bestand klein


def is_event_added(uid: str, state: dict) -> bool:
    return uid in state.get("added_event_uids", [])


def mark_event_added(uid: str, state: dict) -> None:
    uids = state.setdefault("added_event_uids", [])
    if uid not in uids:
        uids.append(uid)
    state["added_event_uids"] = uids[-2000:]


# =============================================================================
# SECTIE 6 — E-MAIL LEZEN (IMAP)
# =============================================================================

def connect_imap(config: dict) -> imaplib.IMAP4_SSL:
    """
    Maak verbinding met de IMAP-server en log in.
    Gooit een duidelijke fout als inloggen mislukt.
    """
    log.info(f"Verbinden met {config['imap_server']}:{config['imap_port']}…")
    mail = imaplib.IMAP4_SSL(config["imap_server"], config["imap_port"])
    mail.login(config["email_address"], config["email_password"])
    log.info("  ✓ Ingelogd")
    return mail


def search_roster_emails(mail: imaplib.IMAP4_SSL, config: dict) -> list[bytes]:
    """
    Zoek in de inbox naar rooster-e-mails.
    Strategie: eerst op onderwerp, dan op afzender als terugval.
    Geeft een lijst van IMAP-UIDs (bytes) terug.
    """
    mail.select("INBOX")
    subject_kw = config["search_subject"]
    sender_kw  = config["search_sender"]

    # Probeer op onderwerp te zoeken
    typ, data = mail.uid("search", None, f'SUBJECT "{subject_kw}"')
    uids = data[0].split() if typ == "OK" and data[0] else []

    # Als dat niets oplevert, zoek op afzender
    if not uids:
        log.debug("Geen resultaten op onderwerp, probeer op afzender…")
        typ, data = mail.uid("search", None, f'FROM "{sender_kw}"')
        uids = data[0].split() if typ == "OK" and data[0] else []

    log.info(f"  {len(uids)} rooster-e-mail(s) gevonden in inbox")
    return uids


DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}

# Matches the last "d+ monthname" in a subject, e.g. "8 februari" or "6 april"
_END_DATE_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(DUTCH_MONTHS) + r")\b",
    re.IGNORECASE,
)


def parse_end_date_from_subject(subject: str) -> Optional[date]:
    """
    Extraheer de einddatum uit een rooster-onderwerp zoals
    'Rooster 2 t/m 8 februari' of 'Rooster 31 maart t/m 6 april'.
    Geeft None terug als er geen datum gevonden wordt.
    """
    matches = _END_DATE_RE.findall(subject)
    if not matches:
        return None
    day_str, month_str = matches[-1]  # laatste treffer = einddatum
    day   = int(day_str)
    month = DUTCH_MONTHS[month_str.lower()]
    year  = datetime.now().year
    try:
        end_date = date(year, month, day)
        # Als de datum meer dan 6 maanden in de toekomst ligt is het waarschijnlijk
        # vorig jaar (bijv. "december" gelezen in januari).
        if (end_date - datetime.now().date()).days > 180:
            end_date = date(year - 1, month, day)
        return end_date
    except ValueError:
        return None


def fetch_email_headers(mail: imaplib.IMAP4_SSL, uid: bytes) -> tuple[str, str]:
    """Haal Message-ID en Subject op in één goedkope headeraanroep."""
    typ, data = mail.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT)])")
    if typ != "OK" or not data or not data[0]:
        return "", ""
    msg = email.message_from_bytes(data[0][1])
    return msg.get("Message-ID", "").strip(), msg.get("Subject", "").strip()


def fetch_email_message(mail: imaplib.IMAP4_SSL, uid: bytes) -> Optional[email.message.Message]:
    """Haal de volledige e-mail op via UID. Geeft None terug bij een fout."""
    typ, data = mail.uid("fetch", uid, "(RFC822)")
    if typ != "OK" or not data or not data[0]:
        return None
    return email.message_from_bytes(data[0][1])


def get_message_id(msg: email.message.Message) -> str:
    """
    Haal de unieke Message-ID op uit de e-mailheader.
    Dit is de sleutel voor deduplicatie: dezelfde e-mail krijgt altijd dezelfde ID.
    """
    return msg.get("Message-ID", "").strip()


def extract_pdf_attachments(msg: email.message.Message) -> list[bytes]:
    """
    Doorloop alle e-mailonderdelen (MIME-parts) en verzamel PDF-bijlagen.
    Geeft een lijst van ruwe PDF-bytes terug (meestal slechts één).
    """
    pdfs = []
    for part in msg.walk():
        content_type = part.get_content_type()
        filename     = part.get_filename() or ""

        # Detecteer PDFs op basis van content-type of bestandsnaam
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            payload = part.get_payload(decode=True)
            if payload:
                pdfs.append(payload)
                log.debug(f"  PDF-bijlage: '{filename or 'naamloos'}' ({len(payload):,} bytes)")

    return pdfs


def get_email_body_text(msg: email.message.Message) -> str:
    """
    Haal de platte tekst uit het e-maillichaam.
    Wordt gebruikt als terugval wanneer er geen PDF-bijlage is.
    """
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    return ""


# =============================================================================
# SECTIE 7 — PDF TEKST EXTRACTIE
# =============================================================================

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extraheer alle tekst uit een PDF-bestand in het geheugen.
    
    pdfplumber is uitstekend voor tabelvormige PDFs (zoals roosters):
    het behoudt de indeling en woordvolgorde beter dan andere bibliotheken.
    """
    if not PDFPLUMBER_OK:
        log.error("pdfplumber is niet geïnstalleerd. Voer uit: pip3 install pdfplumber")
        return ""

    text_pages = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                # x_tolerance en y_tolerance bepalen hoe tekens worden gegroepeerd
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text:
                    text_pages.append(text)
                log.debug(f"  PDF pagina {i}: {len(text or '')} tekens")
    except Exception as exc:
        log.error(f"PDF extractie mislukt: {exc}")
        return ""

    return "\n".join(text_pages)


# =============================================================================
# SECTIE 8 — ROOSTER PARSER
# =============================================================================

# Dit reguliere expressie patroon matcht één rij in het rooster.
#
# Voorbeeld van een rij:
#   "Jort Verbeek  donderdag (02-04-2026) 14:00 22:00 DRI 8,00"
# Of een vervolgrrij (naam ontbreekt):
#   "vrijdag (03-04-2026) 15:00 23:00 DRI 8,00"
#
# Named groups: name (optioneel), day, date, start, end, dept

SHIFT_ROW_RE = re.compile(
    r"""
    (?:                                              # optionele naam-blok
        (?P<name>
            [A-Z][a-zÀ-ÿ'\-]+                      #   voornaam
            (?:\s+[A-Za-zÀ-ÿ'\-]+)+                #   achternaam (1 of meer woorden)
        )
        \s+
    )?
    (?P<day>maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)
    \s*\((?P<date>\d{2}-\d{2}-\d{4})\)             # (dd-mm-yyyy)
    \s+(?P<start>\d{1,2}:\d{2})                     # begintijd
    \s+(?P<end>\d{1,2}:\d{2})                       # eindtijd
    \s+(?P<dept>[\w][\w\-]*)                         # afdelingscode
    \s+[\d,]+                                        # uren-kolom (we herberekenen)
    """,
    re.VERBOSE | re.IGNORECASE,
)

NAME_ONLY_RE = re.compile(
    r"^[A-Z][a-zÀ-ÿ'\-]+(?:\s+[A-Za-zÀ-ÿ'\-]+)+$"
)


def make_shift_uid(shift: dict, employee: str) -> str:
    """
    Maak een stabiele unieke ID voor een dienst.
    
    Hoe deduplicatie werkt:
      - De UID wordt berekend op basis van begintijd + eindtijd + afdeling + naam.
      - Dezelfde dienst → altijd dezelfde UID.
      - Zowel Apple Calendar als onze eigen state-check gebruiken deze UID.
      - Hetzelfde rooster twee keer verwerken? Geen duplicaten.
      - Dienst is verzet? Nieuwe tijden → nieuwe UID → wél toegevoegd.
    """
    raw = (
        f"{shift['start'].isoformat()}"
        f"|{shift['end'].isoformat()}"
        f"|{shift['dept']}"
        f"|{employee.lower()}"
    )
    return hashlib.md5(raw.encode()).hexdigest() + "@mcdonalds-lemmer"


def parse_roster_for_employee(text: str, employee: str) -> list[dict]:
    """
    Parseer de volledige roostertekst en extraheer de diensten van één medewerker.
    
    De parser loopt regel voor regel en houdt bij welke medewerker 'actief' is.
    Zodra een naam-regel de doelmedewerker aangeeft, worden de volgende dienst-regels
    verzameld totdat een andere naam opduikt.
    """
    shifts:           list[dict] = []
    current_employee: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Sla lege regels en te korte regels over
        if not line or len(line) < 10:
            continue

        m = SHIFT_ROW_RE.search(line)

        if not m:
            # Geen dienstrij — misschien een naam-alleen rij?
            if NAME_ONLY_RE.match(line):
                current_employee = line
            continue

        # Bijhouden welke medewerker actief is
        if m.group("name"):
            current_employee = m.group("name").strip()

        if not current_employee:
            continue

        # Alleen diensten van onze medewerker
        if employee.lower() not in current_employee.lower():
            continue

        # ── Tijden parsen ─────────────────────────────────────────────────
        date_str = m.group("date")    # "02-04-2026"
        start_dt = datetime.strptime(f"{date_str} {m.group('start')}", "%d-%m-%Y %H:%M")
        end_dt   = datetime.strptime(f"{date_str} {m.group('end')}",   "%d-%m-%Y %H:%M")

        # Nachtdienst fix: eindtijd vóór begintijd → volgende dag
        # Voorbeeld: 17:00 → 01:00 wordt 17:00 → 01:00+1dag
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
            log.debug(f"  Nachtdienst gedetecteerd: eindtijd +1 dag")

        dept       = m.group("dept").upper()
        dept_label = DEPT_LABELS.get(dept, dept)

        shift = {
            "start":   start_dt,
            "end":     end_dt,
            "dept":    dept,
            "summary": f"Werk – {dept_label}",
            "date":    start_dt.date(),
        }
        shift["uid"] = make_shift_uid(shift, employee)
        if start_dt.date() >= datetime.now().date():
            shifts.append(shift)

    return shifts


# =============================================================================
# SECTIE 9 — APPLE CALENDAR SCHRIJVEN (via AppleScript)
# =============================================================================
#
# Waarom AppleScript en geen .ics?
#   - AppleScript schrijft DIRECT naar de agenda → geen import-dialoog
#   - Werkt met lokale agenda's én iCloud
#   - We kunnen duplicaten controleren vóórdat we iets toevoegen
#
# Waarom datum via property-setters (year/month/day/time)?
#   - AppleScript parseer-notatie is locale-afhankelijk ("2 april" vs "April 2")
#   - Month-constanten (January, February…) zijn ALTIJD Engels in AppleScript,
#     ongeacht de systeemtaal → locale-onafhankelijk en betrouwbaar


def _build_applescript_date(var_name: str, dt: datetime) -> str:
    """
    Genereer AppleScript-code die een datum-variabele instelt.
    Gebruikt property-setters met Engelse maandconstanten (locale-proof).
    
    Voorbeeld output voor dt = 2026-04-02 14:00:
        set startDate to current date
        set year of startDate to 2026
        set month of startDate to April
        set day of startDate to 2
        set time of startDate to 50400
    """
    month_constant      = MONTH_EN[dt.month]
    seconds_since_mid   = dt.hour * 3600 + dt.minute * 60
    return (
        f"set {var_name} to current date\n"
        f"    set day of {var_name} to 1\n"
        f"    set year of {var_name} to {dt.year}\n"
        f"    set month of {var_name} to {month_constant}\n"
        f"    set day of {var_name} to {dt.day}\n"
        f"    set time of {var_name} to {seconds_since_mid}"
    )


def add_events_to_calendar_batch(shifts: list[dict], config: dict) -> Optional[list[str]]:
    """
    Voeg meerdere diensten toe aan Apple Calendar in één enkele AppleScript-aanroep.
    Geeft een lijst van UIDs terug die succesvol zijn toegevoegd.
    """
    if not shifts:
        return []

    cal_name   = config["calendar_name"]
    location   = config["location"]
    alarm_mins = -abs(config.get("alarm_minutes_before", 120))
    color_key  = config.get("calendar_color", "red")
    cal_color  = CALENDAR_COLORS.get(color_key, "red")

    shift_blocks = []
    for shift in shifts:
        summary    = shift["summary"]
        uid        = shift["uid"]
        dept_label = DEPT_LABELS.get(shift["dept"], shift["dept"])
        notes      = (
            f"Afdeling: {dept_label}\\n"
            f"Locatie: {location}\\n"
            f"Medewerker: {config['employee_name']}"
        )
        start_code = _build_applescript_date("startDate", shift["start"])
        end_code   = _build_applescript_date("endDate",   shift["end"])

        shift_blocks.append(f"""
    {start_code}
    {end_code}
    set matchCount to count of (every event of targetCal whose ¬
        summary is "{summary}" and start date is startDate)
    if matchCount = 0 then
        set newEvent to make new event at end of events of targetCal with properties ¬
            {{summary:"{summary}", ¬
              start date:startDate, ¬
              end date:endDate, ¬
              location:"{location}", ¬
              description:"{notes}"}}
        tell newEvent
            make new display alarm with properties {{trigger interval:{alarm_mins}}}
        end tell
        set addedUIDs to addedUIDs & "{uid}|"
    end if""")

    all_blocks = "\n".join(shift_blocks)

    script = f"""
tell application "Calendar"

    set targetCal to missing value
    repeat with c in every calendar
        if name of c is "{cal_name}" then
            set targetCal to c
            exit repeat
        end if
    end repeat
    if targetCal is missing value then
        set targetCal to first calendar whose writable is true
    end if

    set color of targetCal to {cal_color}

    set addedUIDs to ""
    {all_blocks}

    return addedUIDs
end tell
"""

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            err = result.stderr.strip()
            log.error(f"  AppleScript-fout: {err}")
            if "not authorized" in err.lower() or "permission" in err.lower():
                log.error("  → Ga naar Systeeminstellingen → Privacy → Agenda en geef toegang.")
            return None

        return [u for u in result.stdout.strip().split("|") if u]

    except subprocess.TimeoutExpired:
        log.error("  AppleScript time-out — reageert Agenda.app?")
        return None
    except Exception as exc:
        log.error(f"  Onverwachte fout bij Calendar-schrijven: {exc}")
        return None


# =============================================================================
# SECTIE 10 — MACROS MELDING
# =============================================================================

def bundled_notifier_app() -> Optional[Path]:
    """Geef het pad naar de native notificatie-helper terug als die is meegebundeld."""
    if not getattr(sys, "frozen", False):
        return None

    app_path = Path(sys.executable).resolve().parents[1] / "Resources" / "MacRoosterNotifier.app"
    return app_path if app_path.exists() else None


def send_macos_notification(title: str, message: str, subtitle: str = "") -> None:
    """Stuur een macOS-melding (verschijnt rechtsboven in beeld)."""
    notifier_app = bundled_notifier_app()
    if notifier_app is not None:
        try:
            subprocess.Popen(
                [
                    "open",
                    "-gj",
                    str(notifier_app),
                    "--args",
                    "--notify",
                    title,
                    message,
                    subtitle,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception as exc:
            log.warning(f"Native melding kon niet worden gestart ({exc}); terugval naar AppleScript.")

    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
    escaped_message = message.replace("\\", "\\\\").replace('"', '\\"')
    escaped_subtitle = subtitle.replace("\\", "\\\\").replace('"', '\\"')
    sub = f'subtitle "{escaped_subtitle}" ' if subtitle else ""
    script = f'display notification "{escaped_message}" with title "{escaped_title}" {sub}'
    subprocess.run(["osascript", "-e", script], capture_output=True)


# =============================================================================
# SECTIE 11 — HOOFD LOGICA (orchestrator)
# =============================================================================

def run_check(config: dict) -> int:
    """
    Controleer e-mails, parseer roosters en voeg diensten toe aan Calendar.
    Geeft het aantal nieuw toegevoegde diensten terug.
    """
    log.info("=" * 55)
    log.info(f"MacRooster — {datetime.now():%d-%m-%Y %H:%M}")
    log.info(f"Zoeken naar diensten van: {config['employee_name']}")
    log.info("=" * 55)

    # Controleer of pdfplumber aanwezig is
    if not PDFPLUMBER_OK:
        log.error("pdfplumber niet geïnstalleerd! Voer uit: pip3 install pdfplumber")
        return 0

    state             = load_state()
    total_new_events  = 0

    # ── Verbinding maken ──────────────────────────────────────────────────────
    try:
        mail = connect_imap(config)
    except imaplib.IMAP4.error as exc:
        log.error(f"Inloggen mislukt: {exc}")
        log.error("Controleer je e-mailadres en wachtwoord in ~/.macrooster/config.json")
        log.error("Gmail-gebruiker? Gebruik een App-wachtwoord (niet je gewone wachtwoord).")
        return 0
    except Exception as exc:
        log.error(f"Verbindingsfout: {exc}")
        return 0

    try:
        uids = search_roster_emails(mail, config)

        for uid_bytes in uids:
            # ── Headers ophalen (goedkoop: geen body download) ────────────
            message_id, subject = fetch_email_headers(mail, uid_bytes)
            message_id = message_id or f"imap-uid-{uid_bytes.decode()}"
            already_processed = is_email_processed(message_id, state)

            # ── Sla e-mails over waarvan de roosterperiode al voorbij is ──
            end_date = parse_end_date_from_subject(subject)
            if end_date is not None and end_date < datetime.now().date():
                if already_processed:
                    log.debug(f"E-mail al eerder verwerkt en periode voorbij ({end_date:%d-%m-%Y}), overgeslagen.")
                else:
                    log.info(f"Overgeslagen (periode voorbij: {end_date:%d-%m-%Y}): {subject[:70]}")
                    mark_email_processed(message_id, state)
                    save_state(state)
                continue

            if already_processed:
                log.debug(
                    "E-mail al eerder verwerkt (%s…), maar wordt opnieuw gecontroleerd op ontbrekende diensten.",
                    message_id[:40],
                )

            # ── Volledige e-mail ophalen (alleen als periode relevant is) ─
            msg = fetch_email_message(mail, uid_bytes)
            if msg is None:
                continue

            log.info(f"\nVerwerken: {subject[:70]}")

            # ── Tekst extraheren ──────────────────────────────────────────
            roster_text = ""

            # Probeer eerst PDF-bijlage(n)
            for pdf_bytes in extract_pdf_attachments(msg):
                candidate = extract_text_from_pdf(pdf_bytes)
                # Controleer of de tekst onze medewerker bevat
                first_name = config["employee_name"].split()[0]
                if candidate and first_name.lower() in candidate.lower():
                    roster_text = candidate
                    log.debug("  Rostertekst succesvol uit PDF gehaald.")
                    break

            # Terugval: e-maillichaam
            if not roster_text:
                body = get_email_body_text(msg)
                if body and "rooster" in body.lower():
                    roster_text = body
                    log.debug("  Rostertekst uit e-maillichaam gehaald.")

            if not roster_text:
                log.warning("  Geen rostertekst gevonden in deze e-mail. Overgeslagen.")
                mark_email_processed(message_id, state)
                save_state(state)
                continue

            # ── Diensten parseren ─────────────────────────────────────────
            shifts = parse_roster_for_employee(roster_text, config["employee_name"])

            if not shifts:
                log.info(f"  Geen diensten gevonden voor '{config['employee_name']}' in dit rooster.")
                mark_email_processed(message_id, state)
                save_state(state)
                continue

            log.info(f"  {len(shifts)} dienst(en) gevonden:")
            for shift in shifts:
                log.info(
                    "    • %s %s–%s",
                    shift["start"].strftime("%d-%m-%Y"),
                    shift["start"].strftime("%H:%M"),
                    shift["end"].strftime("%H:%M"),
                )

            # ── Toevoegen aan Apple Calendar (in één batch) ───────────────
            pending = sorted(shifts, key=lambda s: s["start"])

            added_uids = add_events_to_calendar_batch(pending, config)
            if added_uids is None:
                log.warning("  Toevoegen aan Agenda mislukt; deze e-mail blijft onverwerkt zodat je later opnieuw kunt proberen.")
                continue

            new_in_this_email = 0
            for uid in added_uids:
                mark_event_added(uid, state)
                new_in_this_email += 1
                total_new_events  += 1
                shift = next((s for s in pending if s["uid"] == uid), None)
                if shift:
                    log.info(
                        f"  ✓ {shift['summary']}  "
                        f"{shift['start']:%a %d-%m %H:%M} – {shift['end']:%H:%M}"
                        + (" (+1 dag)" if shift['end'].date() > shift['date'] else "")
                    )

            mark_email_processed(message_id, state)
            save_state(state)
            log.info(f"  → {new_in_this_email} nieuwe dienst(en) toegevoegd uit deze e-mail.")

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    # ── macOS-melding ─────────────────────────────────────────────────────────
    if total_new_events > 0 and config.get("notify_on_new_shifts", True):
        send_macos_notification(
            title    = "MacRooster",
            message  = f"{total_new_events} nieuwe dienst(en) in je agenda gezet.",
            subtitle = "McDonald's Lemmer",
        )

    log.info(f"\nKlaar. Totaal {total_new_events} nieuwe dienst(en) toegevoegd.")
    log.info("=" * 55)
    return total_new_events


# =============================================================================
# SECTIE 12 — SETUP WIZARD (eerste keer instellen)
# =============================================================================

def launch_setup_gui() -> bool:
    """Start de grafische setup-wizard als die beschikbaar is."""
    gui_script = Path(__file__).with_name("macrooster_setup.py")
    if not gui_script.exists():
        return False

    result = subprocess.run([sys.executable, str(gui_script)])
    return result.returncode == 0

def setup_wizard() -> None:
    """
    Interactieve configuratiewizard.
    Vraagt om alle benodigde gegevens en test de verbinding.
    """
    print()
    print("╔═══════════════════════════════════════════════════╗")
    print("║       MacRooster — Eerste keer instellen          ║")
    print("╚═══════════════════════════════════════════════════╝")
    print()

    config = load_config()

    # ── Naam ─────────────────────────────────────────────────────────────────
    name = input(f"Jouw naam in het rooster [{config['employee_name']}]: ").strip()
    if name:
        config["employee_name"] = name

    # ── E-mailprovider ────────────────────────────────────────────────────────
    print()
    print("Kies je e-mailprovider:")
    print("  1  Gmail")
    print("  2  iCloud (Apple Mail)")
    print("  3  Outlook / Microsoft 365")
    print("  4  Andere (handmatige IMAP-instelling)")
    choice = input("Keuze [1]: ").strip() or "1"

    provider_map = {
        "1": ("imap.gmail.com",           993, "Gmail"),
        "2": ("imap.mail.me.com",         993, "iCloud"),
        "3": ("outlook.office365.com",    993, "Outlook"),
    }
    if choice in provider_map:
        server, port, provider_name = provider_map[choice]
        config["imap_server"] = server
        config["imap_port"]   = port
        if choice == "1":
            print()
            print("  ℹ  Gmail vereist een 'App-wachtwoord'.")
            print("     Jouw gewone Gmail-wachtwoord werkt NIET.")
            print("     Stap voor stap:")
            print("       1. Ga naar myaccount.google.com")
            print("       2. Beveiliging → 2-stapsverificatie (moet aan staan)")
            print("       3. Zoek naar 'App-wachtwoorden'")
            print("       4. Maak een nieuw App-wachtwoord aan voor 'Mail'")
            print("       5. Kopieer de 16-cijferige code (spaties weglaten)")
    else:
        server = input(f"IMAP-server [{config['imap_server']}]: ").strip()
        port   = input(f"IMAP-poort [{config['imap_port']}]: ").strip()
        if server: config["imap_server"] = server
        if port:   config["imap_port"]   = int(port)

    # ── E-mailgegevens ────────────────────────────────────────────────────────
    print()
    addr = input(f"E-mailadres [{config['email_address']}]: ").strip()
    if addr:
        config["email_address"] = addr

    pwd = getpass.getpass("Wachtwoord / App-wachtwoord (verborgen): ")
    if pwd:
        config["email_password"] = pwd

    # ── Zoekfilters ───────────────────────────────────────────────────────────
    print()
    print("Hoe herken je een rooster-e-mail?")
    sender_kw = input(
        f"  Deel van naam/e-mail afzender [{config['search_sender']}]: "
    ).strip()
    if sender_kw:
        config["search_sender"] = sender_kw

    subj_kw = input(
        f"  Trefwoord in onderwerp [{config['search_subject']}]: "
    ).strip()
    if subj_kw:
        config["search_subject"] = subj_kw

    # ── Agenda ────────────────────────────────────────────────────────────────
    print()
    cal = input(f"Naam van de agenda in Agenda.app [{config['calendar_name']}]: ").strip()
    if cal:
        config["calendar_name"] = cal

    print("Kies een agendakleur:")
    print("  1  Rood (McDonald's rood)  ← standaard")
    print("  2  Oranje")
    print("  3  Geel")
    print("  4  Groen")
    print("  5  Blauw")
    print("  6  Paars")
    print("  7  Bruin")
    print("  8  Grijs")
    color_map = {"1": "red", "2": "orange", "3": "yellow", "4": "green",
                 "5": "blue", "6": "purple", "7": "brown", "8": "gray"}
    color_choice = input("Keuze [1]: ").strip() or "1"
    config["calendar_color"] = color_map.get(color_choice, "red")

    alarm = input(f"Herinnering X minuten voor dienst [{config['alarm_minutes_before']}]: ").strip()
    if alarm.isdigit():
        config["alarm_minutes_before"] = int(alarm)

    interval = input(f"Hoe vaak e-mail controleren (in uren) [{config['check_interval_hours']}]: ").strip()
    if interval.isdigit() and int(interval) > 0:
        config["check_interval_hours"] = int(interval)

    # ── Opslaan ───────────────────────────────────────────────────────────────
    save_config(config)
    print()
    print(f"  ✓ Configuratie opgeslagen in {CONFIG_FILE}")
    print(f"    (chmod 600 — alleen jij kunt dit bestand lezen)")

    # ── Verbindingstest ───────────────────────────────────────────────────────
    print()
    do_test = input("Verbinding nu testen? [y/N]: ").strip().lower()
    if do_test == "y":
        print()
        print("Verbinding testen…")
        try:
            test_mail = connect_imap(config)
            uids      = search_roster_emails(test_mail, config)
            print(f"  ✓ Ingelogd bij {config['imap_server']}")
            print(f"  ✓ {len(uids)} rooster-e-mail(s) gevonden")
            test_mail.logout()
        except Exception as exc:
            print(f"  ✗ Test mislukt: {exc}")
            print("    Controleer je gegevens en probeer opnieuw.")
            return

    # ── Kalender toegang ──────────────────────────────────────────────────────
    print()
    print("Kalender-toegang controleren…")
    print("  (macOS vraagt mogelijk om toestemming — klik op 'OK')")
    test_script = 'tell application "Calendar" to name of every calendar'
    result = subprocess.run(["osascript", "-e", test_script], capture_output=True, text=True)
    if result.returncode == 0:
        calendars = result.stdout.strip()
        print(f"  ✓ Toegang tot Agenda.app: {calendars[:80]}")
    else:
        print(f"  ⚠  Geen toegang: {result.stderr.strip()}")
        print("     Ga naar Systeeminstellingen → Privacy & Beveiliging → Agenda")
        print("     en geef Terminal (of je Python-app) toegang.")

    print()
    print("═" * 55)
    print("Setup klaar! Volgende stappen:")
    print()
    print("  Testen (nu één keer uitvoeren):")
    print("    python3 ~/.macrooster/macrooster_core.py")
    print()
    print("  Open MacRooster vanuit Programma's om de setup opnieuw te starten.")
    print("═" * 55)
    print()


# =============================================================================
# SECTIE 13 — STATUS COMMANDO
# =============================================================================

def show_status() -> None:
    config = load_config()
    state  = load_state()

    print()
    print("╔═══════════════════════════════════════════════════╗")
    print("║               MacRooster — Status                 ║")
    print("╚═══════════════════════════════════════════════════╝")
    print()
    print(f"  Medewerker       : {config['employee_name']}")
    print(f"  E-mail server    : {config['imap_server']}")
    print(f"  E-mailadres      : {config['email_address']}")
    print(f"  Agenda           : {config['calendar_name']}")
    print(f"  Zoek afzender    : {config['search_sender']}")
    print(f"  Zoek onderwerp   : {config['search_subject']}")
    print()
    print(f"  Verwerkte e-mails   : {len(state.get('processed_message_ids', []))}")
    print(f"  Toegevoegde diensten: {len(state.get('added_event_uids', []))}")
    print()
    print(f"  Logbestand       : {LOG_FILE}")

    # Toon de laatste 15 logregels
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            print()
            print("  Laatste logregels:")
            print("  " + "─" * 50)
            for line in lines[-15:]:
                print(f"  {line}")
    print()


# =============================================================================
# SECTIE 14 — COMMAND-LINE INTERFACE
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        prog        = "macrooster",
        description = "Automatisch McDonald's roosters uit e-mail naar Apple Calendar",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = (
            "Voorbeelden:\n"
            "  python3 macrooster_core.py --setup     # Eerste keer instellen\n"
            "  python3 macrooster_core.py              # E-mails controleren\n"
            "  python3 macrooster_core.py --status     # Status bekijken\n"
            "  python3 macrooster_core.py --reset      # Geheugen wissen\n"
        ),
    )
    parser.add_argument("--setup",  action="store_true", help="Eerste keer instellen (wizard)")
    parser.add_argument("--status", action="store_true", help="Status en statistieken tonen")
    parser.add_argument("--reset",  action="store_true", help="Verwerkte staat wissen (start opnieuw)")
    args = parser.parse_args()

    if args.setup:
        if launch_setup_gui():
            return
        setup_wizard()
        return

    if args.status:
        show_status()
        return

    if args.reset:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
            print("✓ Staat gewist. Alle e-mails worden bij de volgende run opnieuw verwerkt.")
        else:
            print("Geen staatbestand gevonden — er valt niets te wissen.")
        return

    # Standaard: e-mails controleren
    config = load_config()
    if not config.get("email_address") or not config.get("email_password"):
        print()
        print("⚠  Nog niet ingesteld. Voer dit eerst uit:")
        print("     python3 macrooster_core.py --setup")
        print()
        sys.exit(1)

    run_check(config)


if __name__ == "__main__":
    main()


# =============================================================================
# HOE HET FORMAAT AANPASSEN ALS HET ROOSTER VERANDERT
# =============================================================================
#
# Het rooster heeft twee niveaus van tekst:
#
#   Niveau 1 — naam-rij:           "Jort Verbeek"
#   Niveau 2 — dienst-rij:         "donderdag (02-04-2026) 14:00 22:00 DRI 8,00"
#
# Als het formaat wijzigt, pas dan SHIFT_ROW_RE aan:
#
#   Datum anders (bijv. "2026-04-02")?
#     Wijzig (?P<date>\d{2}-\d{2}-\d{4})
#         → (?P<date>\d{4}-\d{2}-\d{2})
#     En pas strptime-format aan: "%d-%m-%Y" → "%Y-%m-%d"
#
#   Extra kolom ertussen?
#     Voeg \s+\S+ toe op de juiste plek in SHIFT_ROW_RE.
#
#   Testen van de regex:
#     python3 -c "
#     import re, sys
#     sys.path.insert(0, '.')
#     from macrooster_core import SHIFT_ROW_RE
#     print(SHIFT_ROW_RE.search('jouw testregel hier'))
#     "
#
# =============================================================================
