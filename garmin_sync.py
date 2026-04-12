#!/usr/bin/env python3
"""
garmin_sync.py — synchronisiert Garmin Connect Aktivitäten in imports/

Setup:
    pip install garminconnect
    export GARMIN_EMAIL="deine@email.de"
    export GARMIN_PASSWORD="deinPasswort"

Verwendung:
    python3 garmin_sync.py              # letzte 7 Tage
    python3 garmin_sync.py --days 30    # letzte 30 Tage
    python3 garmin_sync.py --all        # alle noch nicht gesyncten
"""

import os
import json
import sys
import argparse
import zipfile
import io
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

try:
    from garminconnect import Garmin, GarminConnectAuthenticationError
except ImportError:
    print("Fehler: garminconnect nicht installiert.")
    print("Bitte ausführen: pip install garminconnect")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

BASE_DIR    = Path(__file__).parent
IMPORTS_DIR = BASE_DIR / "imports"
STATE_FILE  = BASE_DIR / ".garmin_sync_state.json"

# Aktivitätstypen die übersprungen werden (manuell getrackt)
SKIP_TYPES = {"other"}

# Garmin Aktivitätstyp → Zielordner in imports/
ACTIVITY_FOLDER_MAP = {
    "running":              "laufen",
    "trail_running":        "laufen",
    "treadmill_running":    "laufen",
    "indoor_running":       "laufen",
    "swimming":             "sonstiges",
    "lap_swimming":         "sonstiges",
    "open_water_swimming":  "sonstiges",
    "strength_training":    "gym",
    "fitness_equipment":    "gym",
    "indoor_rowing":        "gym",
    "weight_training":      "gym",
    "armwrestling":         "sonstiges",
}
DEFAULT_FOLDER = "sonstiges"

# Aktivitätstyp → lesbares Kürzel für Dateiname
ACTIVITY_LABEL_MAP = {
    "running":              "lauf",
    "trail_running":        "trail",
    "treadmill_running":    "laufband",
    "indoor_running":       "lauf-indoor",
    "swimming":             "schwimmen",
    "lap_swimming":         "schwimmen",
    "open_water_swimming":  "freiwasser",
    "strength_training":    "gym",
    "fitness_equipment":    "gym",
    "indoor_rowing":        "rudern",
    "weight_training":      "gym",
}

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """Lädt den Sync-Status (bereits heruntergeladene Aktivitäts-IDs)."""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"downloaded_ids": []}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_folder(activity_type: str) -> Path:
    folder_name = ACTIVITY_FOLDER_MAP.get(activity_type.lower(), DEFAULT_FOLDER)
    folder = IMPORTS_DIR / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_label(activity_type: str) -> str:
    return ACTIVITY_LABEL_MAP.get(activity_type.lower(), activity_type.lower().replace(" ", "-"))


def build_filename(activity: dict) -> str:
    """Erstellt Dateiname im Format YYYY-MM-DD_typ_ID.fit"""
    raw_date = activity.get("startTimeLocal", "")[:10]  # "2026-04-12"
    activity_type = activity.get("activityType", {}).get("typeKey", "aktivitaet")
    label = get_label(activity_type)
    activity_id = activity.get("activityId", "unknown")
    return f"{raw_date}_{label}_{activity_id}.fit"


def extract_fit_from_zip(zip_bytes: bytes) -> Optional[bytes]:
    """Extrahiert die .fit-Datei aus dem Garmin-ZIP."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".fit"):
                    return zf.read(name)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------------------------

def sync(days: int = 7, sync_all: bool = False):
    email    = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")

    if not email or not password:
        print("Fehler: Umgebungsvariablen fehlen.")
        print("  export GARMIN_EMAIL='deine@email.de'")
        print("  export GARMIN_PASSWORD='deinPasswort'")
        sys.exit(1)

    print("Verbinde mit Garmin Connect...")
    try:
        api = Garmin(email, password)
        api.login()
    except GarminConnectAuthenticationError:
        print("Fehler: Login fehlgeschlagen — E-Mail oder Passwort prüfen.")
        sys.exit(1)
    except Exception as e:
        print(f"Fehler beim Login: {e}")
        sys.exit(1)

    print("Login erfolgreich.")

    state = load_state()
    already_downloaded = set(str(i) for i in state.get("downloaded_ids", []))

    # Aktivitäten abrufen
    limit = 100 if sync_all else min(days * 2, 50)  # großzügiger Puffer
    print(f"Lade Aktivitätsliste (max. {limit} Einträge)...")
    activities = api.get_activities(0, limit)

    # Datumsfilter
    if not sync_all:
        cutoff = date.today() - timedelta(days=days)
        activities = [
            a for a in activities
            if a.get("startTimeLocal", "")[:10] >= cutoff.isoformat()
        ]

    # Nur neue Aktivitäten
    new_activities = [
        a for a in activities
        if str(a.get("activityId")) not in already_downloaded
    ]

    if not new_activities:
        print("Keine neuen Aktivitäten gefunden.")
        return

    print(f"{len(new_activities)} neue Aktivität(en) gefunden.\n")

    downloaded = 0
    for activity in new_activities:
        activity_id   = activity.get("activityId")
        activity_type = activity.get("activityType", {}).get("typeKey", "other")
        raw_date      = activity.get("startTimeLocal", "")[:10]
        name          = activity.get("activityName", "Unbekannt")
        duration_s    = int(activity.get("duration", 0))
        duration_min  = duration_s // 60

        if activity_type in SKIP_TYPES:
            print(f"  [{raw_date}] {name} ({activity_type}) — übersprungen (manuell getrackt)")
            already_downloaded.add(str(activity_id))
            continue

        folder   = get_folder(activity_type)
        filename = build_filename(activity)
        dest     = folder / filename

        print(f"  [{raw_date}] {name} ({activity_type}, {duration_min} min)")

        try:
            zip_data = api.download_activity(
                activity_id,
                dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
            )
            fit_data = extract_fit_from_zip(zip_data)

            if fit_data:
                dest.write_bytes(fit_data)
                print(f"    → gespeichert: {dest.relative_to(BASE_DIR)}")
            else:
                # Fallback: ZIP direkt speichern
                dest_zip = dest.with_suffix(".zip")
                dest_zip.write_bytes(zip_data)
                print(f"    → als ZIP gespeichert: {dest_zip.relative_to(BASE_DIR)}")

            already_downloaded.add(str(activity_id))
            downloaded += 1

        except Exception as e:
            print(f"    Fehler beim Download: {e}")

    # State speichern
    state["downloaded_ids"] = list(already_downloaded)
    state["last_sync"] = datetime.now().isoformat()
    save_state(state)

    print(f"\nFertig: {downloaded}/{len(new_activities)} Aktivitäten heruntergeladen.")
    print(f"Dateien liegen in: {IMPORTS_DIR.relative_to(BASE_DIR.parent)}/")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Garmin → imports/ Sync")
    parser.add_argument("--days", type=int, default=7,
                        help="Aktivitäten der letzten N Tage (Standard: 7)")
    parser.add_argument("--all", dest="sync_all", action="store_true",
                        help="Alle noch nicht gesyncten Aktivitäten herunterladen")
    args = parser.parse_args()

    sync(days=args.days, sync_all=args.sync_all)
