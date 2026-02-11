#!/usr/bin/env python3
"""Extract browser history for a given date from Edge or Chrome.

Outputs a chronological list of all page visits with visit duration,
plus gap markers for context switches. No filtering — the AI reader
decides what's meaningful based on visit_duration and title.

Usage:
    python scripts/browser_history.py --date 2026-02-10 --output ~/Desktop/browser-history.txt
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Chromium stores timestamps as microseconds since Jan 1, 1601
CHROMIUM_EPOCH_OFFSET = 11644473600 * 1_000_000

# Insert a gap marker when visits are more than this many seconds apart
GAP_THRESHOLD_SECONDS = 30 * 60  # 30 minutes

# Browser history DB paths (Edge first, Chrome fallback)
BROWSER_PATHS = [
    ("Edge", Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/History"),
    ("Chrome", Path.home() / "AppData/Local/Google/Chrome/User Data/Default/History"),
]


def find_browser_history():
    """Finde die erste verfuegbare Browser-History-Datei."""
    for name, path in BROWSER_PATHS:
        if path.exists():
            return name, path
    return None, None


def chromium_ts(dt):
    """Konvertiere datetime zu Chromium-Timestamp (Mikrosekunden seit 1601)."""
    return int(dt.timestamp() * 1_000_000) + CHROMIUM_EPOCH_OFFSET


def chromium_to_local(ts):
    """Konvertiere Chromium-Timestamp zu lokaler datetime."""
    unix_us = ts - CHROMIUM_EPOCH_OFFSET
    return datetime.fromtimestamp(unix_us / 1_000_000)


def format_duration(microseconds):
    """Formatiere Besuchsdauer als lesbaren String."""
    if not microseconds or microseconds <= 0:
        return "0s"
    seconds = microseconds / 1_000_000
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m{seconds % 60:.0f}s"
    hours = minutes / 60
    return f"{hours:.0f}h{minutes % 60:.0f}m"


def extract_history(db_path, date_str):
    """Extrahiere alle Besuche fuer ein bestimmtes Datum."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    day_start = datetime(date.year, date.month, date.day, tzinfo=timezone.utc)
    day_end = datetime(date.year, date.month, date.day, 23, 59, 59, tzinfo=timezone.utc)

    ts_start = chromium_ts(day_start)
    ts_end = chromium_ts(day_end)

    # Kopie erstellen, da der Browser die DB sperrt
    tmp_path = Path.home() / "Desktop" / "browser_history_tmp.db"
    try:
        shutil.copy2(db_path, tmp_path)
    except (PermissionError, OSError) as e:
        print(f"Warning: Could not copy browser history ({e}). Browser might be locking it.", file=sys.stderr)
        print("Try closing the browser or copying the file manually.", file=sys.stderr)
        return None, 0, 0

    conn = sqlite3.connect(str(tmp_path))
    cur = conn.cursor()

    cur.execute(
        """
        SELECT v.visit_time, v.visit_duration, u.url, u.title
        FROM visits v
        JOIN urls u ON v.url = u.id
        WHERE v.visit_time >= ? AND v.visit_time < ?
        ORDER BY v.visit_time ASC
        """,
        (ts_start, ts_end),
    )
    rows = cur.fetchall()

    # Eindeutige URLs zaehlen
    unique_urls = len(set(r[2] for r in rows))

    conn.close()
    return rows, len(rows), unique_urls


def write_output(rows, total, unique, browser_name, date_str, output_path):
    """Schreibe die extrahierten Daten in eine Textdatei."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"BROWSER HISTORY: {date_str}\n")
        f.write(f"Source: {browser_name} | {total} visits | {unique} unique URLs\n")
        f.write("=" * 90 + "\n\n")

        if not rows:
            f.write(f"No visits found for {date_str}\n")
            return

        prev_time = None
        for visit_time, visit_duration, url, title in rows:
            dt = chromium_to_local(visit_time)
            dur_str = format_duration(visit_duration)

            # Lueckenmarkierung einfuegen
            if prev_time is not None:
                gap_seconds = (visit_time - prev_time) / 1_000_000
                if gap_seconds >= GAP_THRESHOLD_SECONDS:
                    gap_hours = gap_seconds / 3600
                    if gap_hours >= 1:
                        gap_label = f"{gap_hours:.1f} hours"
                    else:
                        gap_label = f"{gap_seconds / 60:.0f} min"
                    f.write(f"\n--- GAP: {gap_label} ---\n\n")

            safe_title = (title or "").replace("\n", " ").replace("\r", "")[:70]
            safe_url = url[:100] if url else ""
            time_str = dt.strftime("%H:%M:%S")

            f.write(f"{time_str} | {dur_str:>8} | {safe_title:<70} | {safe_url}\n")
            prev_time = visit_time


def main():
    parser = argparse.ArgumentParser(description="Extract browser history for a date")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument("--output", required=True, help="Output file path")
    args = parser.parse_args()

    # Datum validieren
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD.", file=sys.stderr)
        sys.exit(1)

    # Browser finden
    browser_name, db_path = find_browser_history()
    if not browser_name:
        print("No browser history found (no Edge/Chrome detected)")
        # Leere Datei mit Header schreiben
        output_path = os.path.expanduser(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"BROWSER HISTORY: {args.date}\n")
            f.write("Source: none | No Edge/Chrome browser history found\n")
        print(f"Empty output written to {output_path}")
        sys.exit(0)

    print(f"Using {browser_name}: {db_path}")

    # Daten extrahieren
    rows, total, unique = extract_history(db_path, args.date)
    if rows is None:
        # Kopie fehlgeschlagen, leere Datei schreiben
        output_path = os.path.expanduser(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"BROWSER HISTORY: {args.date}\n")
            f.write(f"Source: {browser_name} | Could not access history (browser locked?)\n")
        print(f"Empty output written to {output_path}")
        sys.exit(0)

    # Ausgabe schreiben
    output_path = os.path.expanduser(args.output)
    write_output(rows, total, unique, browser_name, args.date, output_path)
    print(f"Extracted {total} visits ({unique} unique URLs) to {output_path}")


if __name__ == "__main__":
    main()
