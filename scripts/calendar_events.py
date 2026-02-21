#!/usr/bin/env python3
"""Extract calendar events for a given date.

On macOS, compiles and runs a Swift EventKit CLI that reads from the system
Calendar app (which syncs Exchange, Google, iCloud, etc.). The compiled binary
is cached next to the source file for subsequent runs.

On other platforms, writes an empty output file and exits cleanly so the
day-summary skill can continue without calendar data.

Usage:
    python scripts/calendar_events.py --date 2026-02-19 --output ~/Desktop/calendar-2026-02-19.txt
"""

import argparse
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SWIFT_SOURCE = SCRIPT_DIR / "calendar_eventkit.swift"
SWIFT_BINARY = SCRIPT_DIR / "calendar_eventkit"


def compile_swift():
    """Compile the Swift EventKit CLI if needed. Returns True on success."""
    if SWIFT_BINARY.exists():
        # Recompile only if source is newer than binary
        if SWIFT_SOURCE.stat().st_mtime <= SWIFT_BINARY.stat().st_mtime:
            return True

    print(f"Compiling {SWIFT_SOURCE.name}...")
    try:
        result = subprocess.run(
            ["swiftc", "-O", str(SWIFT_SOURCE), "-o", str(SWIFT_BINARY),
             "-framework", "EventKit"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"Swift compilation failed: {result.stderr.strip()}", file=sys.stderr)
            return False
        print("Compilation successful.")
        return True
    except FileNotFoundError:
        print("Swift compiler (swiftc) not found. Install Xcode Command Line Tools.", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("Swift compilation timed out.", file=sys.stderr)
        return False


def run_eventkit(date_str):
    """Run the compiled EventKit binary and return its stdout."""
    try:
        result = subprocess.run(
            [str(SWIFT_BINARY), date_str],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        return result.stdout, result.returncode
    except subprocess.TimeoutExpired:
        return "ERROR: EventKit query timed out.\n", 1
    except FileNotFoundError:
        return "ERROR: Compiled binary not found.\n", 1


def write_empty(output_path, date_str, reason):
    """Write an empty output file with a header explaining why."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"CALENDAR EVENTS: {date_str}\n")
        f.write(f"Source: none | {reason}\n")
    print(f"Empty output written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Extract calendar events for a date")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument("--output", required=True, help="Output file path")
    args = parser.parse_args()

    # Validate date
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD.", file=sys.stderr)
        sys.exit(1)

    output_path = os.path.expanduser(args.output)

    # Platform check
    if platform.system() != "Darwin":
        write_empty(output_path, args.date,
                    "Calendar not supported on this platform (macOS only for now)")
        sys.exit(0)

    # Compile Swift binary
    if not compile_swift():
        write_empty(output_path, args.date,
                    "Could not compile Swift EventKit CLI (install Xcode Command Line Tools)")
        sys.exit(0)

    # Run EventKit query
    stdout, returncode = run_eventkit(args.date)

    # Handle access denied
    if "ACCESS_DENIED" in stdout:
        write_empty(output_path, args.date,
                    "Calendar access denied. Enable in System Settings > Privacy & Security > Calendars")
        sys.exit(0)

    # Handle errors
    if stdout.startswith("ERROR:"):
        write_empty(output_path, args.date, stdout.strip())
        sys.exit(0)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(stdout)

    # Count events for summary
    timed = stdout.count(" attendees")
    print(f"Extracted calendar events ({timed} timed) to {output_path}")


if __name__ == "__main__":
    main()
