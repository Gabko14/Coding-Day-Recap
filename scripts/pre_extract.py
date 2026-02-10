#!/usr/bin/env python3
"""Pre-extract CASS session data into text files for haiku subagents.

Instead of subagents running 5-10+ cass expand commands each, this script
pre-extracts session content into a single readable text file per time block.
Subagents then just Read one file (1 tool call instead of 10+).

Usage:
    python scripts/pre_extract.py --from 2026-02-10T08:00 --until 2026-02-10T12:00 --output morning.txt
    python scripts/pre_extract.py --from 2026-02-10 --until 2026-02-10T23:59:59 --output full-day.txt --stats-output stats.json
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Titles starting with these prefixes are filtered as subagent/teammate sessions
SKIP_TITLE_PREFIXES = [
    "<teammate-message",
    "Your task is to create a detailed summar",
]

ASSISTANT_TEXT_MAX = 1000
SAMPLE_SIZE = 5


def run_cass(args):
    """Run a cass CLI command and return stdout as string."""
    result = subprocess.run(
        ["cass"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"Warning: cass {' '.join(args)} failed: {result.stderr.strip()}", file=sys.stderr)
        return None
    return result.stdout


def discover_sessions(from_dt, until_dt):
    """Run cass timeline --json and return filtered session list."""
    # Use date portion for cass --since/--until (it handles datetime too)
    raw = run_cass([
        "timeline", "--json", "--group-by", "none",
        "--since", from_dt,
        "--until", until_dt,
        "--agent", "claude_code",
    ])
    if not raw:
        return [], 0

    data = json.loads(raw)
    all_sessions = data.get("sessions", [])
    total_before_filter = len(all_sessions)

    # Parse the requested time range for filtering
    from_ts = parse_iso_to_epoch_ms(from_dt)
    until_ts = parse_iso_to_epoch_ms(until_dt)

    filtered = []
    for s in all_sessions:
        started = s.get("started_at", 0)
        # Filter to sessions that started within the requested range
        if started < from_ts or started > until_ts:
            continue
        # Filter out subagent sessions by path (subagents live under /subagents/)
        source = s.get("source_path", "")
        if "subagents" in Path(source).parts:
            continue
        # Filter out teammate/subagent sessions by title
        title = s.get("title", "")
        if any(title.startswith(prefix) for prefix in SKIP_TITLE_PREFIXES):
            continue
        filtered.append(s)

    # Sort by start time ascending
    filtered.sort(key=lambda s: s.get("started_at", 0))
    return filtered, total_before_filter - len(filtered)


def parse_iso_to_epoch_ms(dt_str):
    """Convert ISO datetime string to epoch milliseconds. Handles dates and datetimes."""
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(dt_str, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    # Fallback: return 0 so filter is effectively disabled
    print(f"Warning: could not parse datetime '{dt_str}'", file=sys.stderr)
    return 0


def parse_jsonl(path):
    """Read a .jsonl session file, return list of parsed entries."""
    entries = []
    p = Path(path)
    if not p.exists():
        print(f"Warning: session file not found: {path}", file=sys.stderr)
        return entries
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries



def extract_meaningful(entries):
    """Filter to user text messages and assistant text messages.
    Returns list of (role, text, tools_list) tuples."""
    meaningful = []
    for entry in entries:
        etype = entry.get("type")
        msg = entry.get("message", {})
        role = msg.get("role")
        content = msg.get("content")

        if etype == "user" and role == "user":
            # User message with plain text (not tool_result array)
            if isinstance(content, str) and content.strip():
                text = content.strip()
                # Skip system-generated user messages (local commands, hooks, etc.)
                if text.startswith(("<local-command-", "<command-", "<system-reminder>",
                                    "<bash-input>", "<bash-stdout>", "<bash-stderr>",
                                    "<user-prompt-submit-hook>")):
                    continue
                meaningful.append(("user", text, []))

        elif etype == "assistant" and role == "assistant":
            if isinstance(content, list):
                texts = []
                tools = []
                for block in content:
                    if block.get("type") == "text":
                        t = block.get("text", "").strip()
                        if t:
                            texts.append(t)
                    elif block.get("type") == "tool_use":
                        tools.append(block.get("name", "unknown"))
                    # Skip thinking blocks
                if texts:
                    meaningful.append(("assistant", "\n".join(texts), tools))

    return meaningful


def sample_entries(meaningful, sample_size=SAMPLE_SIZE):
    """Pick sample slices from a list of meaningful entries.

    Adaptive: more sample points for bigger sessions.
    - < 20 entries: full session (returned as single list)
    - 20-60: START + END
    - 61-150: START + MIDDLE + END
    - 151+: START + evenly spaced intermediate points + END

    Returns list of (label, entries_list) tuples for flexible formatting.
    """
    n = len(meaningful)

    if n <= 20:
        return [("FULL SESSION", meaningful)]

    # Adaptive sample size: bigger sessions get bigger slices
    ss = min(10, max(sample_size, n // 20))

    if n <= 60:
        return [
            ("START of session", meaningful[:ss]),
            ("END of session", meaningful[-ss:]),
        ]

    if n <= 150:
        mid = n // 2
        mid_start = max(ss, mid - ss // 2)
        return [
            ("START of session", meaningful[:ss]),
            (f"MIDDLE of session - around message {mid}", meaningful[mid_start:mid_start + ss]),
            ("END of session", meaningful[-ss:]),
        ]

    # Very large session: 5 sample points
    # Evenly space 3 intermediate points between start and end
    sections = [("START of session", meaningful[:ss])]
    for i, frac in enumerate([0.25, 0.5, 0.75]):
        idx = int(n * frac)
        label = ["EARLY in session", "MIDDLE of session", "LATE in session"][i]
        sections.append((f"{label} - around message {idx}", meaningful[idx:idx + ss]))
    sections.append(("END of session", meaningful[-ss:]))
    return sections


def truncate(text, max_len=ASSISTANT_TEXT_MAX):
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def format_session(session_meta, meaningful, sample_size=SAMPLE_SIZE):
    """Format one session into text output."""
    lines = []
    title = session_meta.get("title", "Untitled")[:80]
    workspace = session_meta.get("workspace", "unknown")
    msg_count = session_meta.get("message_count", 0)

    started = session_meta.get("started_at", 0)
    ended = session_meta.get("ended_at", 0)
    start_time = format_epoch_ms(started)
    end_time = format_epoch_ms(ended)

    lines.append(f"Title: {title}")
    lines.append(f"Workspace: {workspace}")
    lines.append(f"Time: {start_time} - {end_time} | Messages: {msg_count}")
    lines.append("---")
    lines.append("")

    if not meaningful:
        lines.append("[NO MEANINGFUL CONTENT]")
        return "\n".join(lines)

    sections = sample_entries(meaningful, sample_size)

    for label, entries in sections:
        lines.append(f"[{label}]")
        lines.append("")
        for role, text, tools in entries:
            lines.extend(format_entry(role, text, tools))

    return "\n".join(lines)


def format_entry(role, text, tools):
    """Format a single meaningful entry into output lines."""
    lines = []
    if role == "user":
        lines.append(f"USER: {text}")
    else:
        lines.append(f"ASSISTANT: {truncate(text)}")
        if tools:
            lines.append(f"[used tools: {', '.join(tools)}]")
    lines.append("")
    return lines


def format_epoch_ms(epoch_ms):
    """Convert epoch milliseconds to HH:MM string."""
    if not epoch_ms:
        return "??:??"
    dt = datetime.fromtimestamp(epoch_ms / 1000)
    return dt.strftime("%H:%M")


def get_workspace_from_entries(entries):
    """Extract workspace (cwd) from the first user entry in parsed JSONL."""
    for entry in entries:
        cwd = entry.get("cwd")
        if cwd:
            return cwd
    return "unknown"


def write_output(output_path, sessions, session_contents, filtered_count):
    """Write the formatted text file."""
    lines = []
    lines.append("=" * 50)
    lines.append("PRE-EXTRACTED SESSIONS")
    lines.append(f"Sessions: {len(sessions)} ({filtered_count} filtered as subagent/teammate)")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
    lines.append("=" * 50)
    lines.append("")

    if not sessions:
        lines.append("No sessions found in this time range.")
    else:
        for i, (session, content) in enumerate(zip(sessions, session_contents)):
            lines.append(f"--- SESSION {i + 1} of {len(sessions)} ---")
            lines.append(content)
            lines.append("")

    lines.append("=" * 50)
    lines.append("END OF PRE-EXTRACTED SESSIONS")
    lines.append("=" * 50)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Extracted {len(sessions)} sessions to {output_path}")


def gather_stats(from_dt, until_dt):
    """Run CASS aggregate commands and return stats dict."""
    stats = {"timeRange": {"from": from_dt, "until": until_dt}}

    # Workspace breakdown
    raw = run_cass([
        "search", "the",
        "--since", from_dt, "--until", until_dt,
        "--agent", "claude_code",
        "--limit", "500", "--json",
        "--aggregate", "workspace",
        "--max-tokens", "1000",
    ])
    if raw:
        data = json.loads(raw)
        stats["totalMatches"] = data.get("total_matches", 0)
        buckets = data.get("aggregations", {}).get("workspace", {}).get("buckets", [])
        stats["workspaces"] = [{"name": b["key"], "count": b["count"]} for b in buckets]

    # Agent breakdown (no --agent filter to get all agents)
    raw = run_cass([
        "search", "the",
        "--since", from_dt, "--until", until_dt,
        "--limit", "500", "--json",
        "--aggregate", "agent",
        "--max-tokens", "1000",
    ])
    if raw:
        data = json.loads(raw)
        buckets = data.get("aggregations", {}).get("agent", {}).get("buckets", [])
        stats["agents"] = [{"name": b["key"], "count": b["count"]} for b in buckets]

    # Timeline for session count and hourly distribution
    raw = run_cass([
        "timeline", "--json", "--group-by", "hour",
        "--since", from_dt, "--until", until_dt,
        "--agent", "claude_code",
    ])
    if raw:
        data = json.loads(raw)
        stats["totalSessions"] = data.get("total_sessions", 0)
        # Build hourly distribution from groups (dict: "YYYY-MM-DD HH:00" -> [sessions])
        hourly = {}
        groups = data.get("groups", {})
        if isinstance(groups, dict):
            for label, sessions_in_group in groups.items():
                if " " in label:
                    hour = label.split(" ")[1].split(":")[0]
                    hourly[hour] = len(sessions_in_group)
        stats["hourlyDistribution"] = hourly

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Pre-extract CASS sessions into text files for haiku subagents"
    )
    parser.add_argument("--from", dest="from_dt", required=True,
                        help="Start datetime (ISO format, e.g., 2026-02-10T08:00)")
    parser.add_argument("--until", required=True,
                        help="End datetime (ISO format, e.g., 2026-02-10T12:00)")
    parser.add_argument("--output", required=True,
                        help="Output text file path")
    parser.add_argument("--stats-output",
                        help="Optional: output stats JSON file path")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE,
                        help=f"Messages per sample slice (default: {SAMPLE_SIZE})")
    args = parser.parse_args()

    # Discover sessions
    print(f"Discovering sessions from {args.from_dt} to {args.until}...")
    sessions, filtered_count = discover_sessions(args.from_dt, args.until)
    print(f"Found {len(sessions)} sessions ({filtered_count} filtered)")

    # Extract content from each session, skip empty ones
    kept_sessions = []
    session_contents = []
    skipped_empty = 0
    for s in sessions:
        source_path = s.get("source_path", "")
        entries = parse_jsonl(source_path)
        s["workspace"] = get_workspace_from_entries(entries)
        meaningful = extract_meaningful(entries)
        if not meaningful:
            skipped_empty += 1
            continue
        content = format_session(s, meaningful, args.sample_size)
        kept_sessions.append(s)
        session_contents.append(content)

    if skipped_empty:
        print(f"Skipped {skipped_empty} sessions with no meaningful content")

    # Write output
    write_output(args.output, kept_sessions, session_contents, filtered_count + skipped_empty)

    # Gather stats if requested
    if args.stats_output:
        print("Gathering stats...")
        stats = gather_stats(args.from_dt, args.until)
        Path(args.stats_output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.stats_output, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        print(f"Stats written to {args.stats_output}")


if __name__ == "__main__":
    main()
