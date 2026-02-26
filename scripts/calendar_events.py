#!/usr/bin/env python3
"""Extract calendar events for a given date.

On macOS, compiles and runs a Swift EventKit CLI that reads from the system
Calendar app (which syncs Exchange, Google, iCloud, etc.). The compiled binary
is cached next to the source file for subsequent runs.

On Windows, runs a PowerShell script that queries Outlook via COM automation.
Outlook must be installed (works with desktop Outlook connected to Exchange,
Microsoft 365, or local calendars).

On other platforms, writes an empty output file and exits cleanly so the
day-summary skill can continue without calendar data.

Usage:
    # Step 1: Discover available calendars
    python scripts/calendar_events.py --date 2026-02-19 --list-calendars

    # Step 2: Extract events from selected calendars only
    python scripts/calendar_events.py --date 2026-02-19 --calendars "Kalender (Local)" --output ~/Desktop/calendar-2026-02-19.txt
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
OUTLOOK_SCRIPT = SCRIPT_DIR / "calendar_outlook.ps1"


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


def run_eventkit(date_str, calendars=None):
    """Run the compiled EventKit binary and return its stdout.

    Note: macOS EventKit does not support calendar filtering yet.
    If calendars is specified, a warning is printed — the output will
    contain all calendars unfiltered.
    """
    if calendars:
        print("WARNING: --calendars filtering is not yet implemented for macOS EventKit. "
              "Output will contain all calendars.", file=sys.stderr)
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


def run_outlook(date_str, calendars=None):
    """Run the PowerShell Outlook COM script and return its stdout."""
    try:
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile",
               "-File", str(OUTLOOK_SCRIPT), date_str]
        if calendars:
            cmd.append(calendars)
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        return result.stdout, result.returncode
    except subprocess.TimeoutExpired:
        return "ERROR: Outlook query timed out.\n", 1
    except FileNotFoundError:
        return "ERROR: PowerShell not found.\n", 1


def write_empty(output_path, date_str, reason):
    """Write an empty output file with a header explaining why."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"CALENDAR EVENTS: {date_str}\n")
        f.write(f"Source: none | {reason}\n")
    print(f"Empty output written to {output_path}")


def extract_calendars_found(stdout):
    """Extract and print just the CALENDARS FOUND section from output."""
    in_section = False
    for line in stdout.splitlines():
        if line.startswith("--- CALENDARS FOUND"):
            in_section = True
            print(line)
            continue
        if in_section:
            print(line)


def run_platform_script(system, date_str, calendars=None):
    """Run the appropriate platform script. Returns (stdout, error_reason).

    On success: (stdout_str, None)
    On failure: (None, "reason string")
    """
    if system == "Darwin":
        if not compile_swift():
            return None, "Could not compile Swift EventKit CLI"
        stdout, returncode = run_eventkit(date_str, calendars)
        if "ACCESS_DENIED" in stdout:
            return None, "Calendar access denied (enable in System Settings)"
    elif system == "Windows":
        stdout, returncode = run_outlook(date_str, calendars)
    else:
        return None, "Unsupported platform"

    if not stdout or not stdout.strip():
        hint = "check Outlook is running" if system == "Windows" else "check calendar access"
        return None, f"Calendar script returned no output ({hint})"
    if stdout.startswith("ERROR:"):
        # Pass through the actual error from the platform script
        return None, stdout.strip().removeprefix("ERROR:").strip()

    return stdout, None


def main():
    parser = argparse.ArgumentParser(description="Extract calendar events for a date")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument("--list-calendars", action="store_true",
                        help="Discovery mode: list available calendars and exit")
    parser.add_argument("--calendars",
                        help="Comma-separated calendar identifiers to include, "
                             "e.g. 'Kalender (Local),Christoph Kappeler (Local)'. "
                             "Required when extracting events (with --output).")
    parser.add_argument("--output", help="Output file path (required unless --list-calendars)")
    args = parser.parse_args()

    # Validate date
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD.", file=sys.stderr)
        sys.exit(1)

    # Validate argument combinations
    if args.list_calendars:
        if args.output or args.calendars:
            print("Error: --list-calendars cannot be combined with --output or --calendars.",
                  file=sys.stderr)
            sys.exit(1)
    else:
        if not args.output:
            print("Error: --output is required (or use --list-calendars for discovery).",
                  file=sys.stderr)
            sys.exit(1)
        if not args.calendars:
            print("Error: --calendars is required. Use --list-calendars first to discover "
                  "available calendars, then pass the desired ones via --calendars.",
                  file=sys.stderr)
            sys.exit(1)

    system = platform.system()

    if system not in ("Darwin", "Windows"):
        if args.list_calendars:
            print("Calendar not supported on this platform (macOS and Windows only).")
            sys.exit(0)
        output_path = os.path.expanduser(args.output)
        write_empty(output_path, args.date,
                    "Calendar not supported on this platform (macOS and Windows only)")
        sys.exit(0)

    # --- Discovery mode ---
    if args.list_calendars:
        stdout, error = run_platform_script(system, args.date)
        if error:
            print(f"Could not retrieve calendars: {error}", file=sys.stderr)
            sys.exit(1)
        extract_calendars_found(stdout)
        print()
        print("Use --calendars with identifiers in 'Name (Type)' format, e.g.:")
        print('  --calendars "Kalender (Local)"')
        sys.exit(0)

    # --- Extraction mode (with calendar filter) ---
    output_path = os.path.expanduser(args.output)
    stdout, error = run_platform_script(system, args.date, calendars=args.calendars)

    if error:
        write_empty(output_path, args.date, error)
        sys.exit(0)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(stdout)

    # Count events for summary
    timed = stdout.count(" attendees")
    print(f"Extracted calendar events ({timed} timed) to {output_path}")


if __name__ == "__main__":
    main()
