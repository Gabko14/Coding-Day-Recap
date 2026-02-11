#!/usr/bin/env python3
# generate_html.py — Generate day-summary HTML from a JSON data file
# Usage: generate_html.py --data-file "data.json" --output-file "summary.html"
#
# JSON schema:
# {
#   "dateLong": "Monday, February 9, 2026",
#   "dateDisplay": "Feb 9, 2026",
#   "headline": "One Commit,<br><em>Infinite Review</em>",
#   "subtitle": "One-sentence summary",
#   "stats": [
#     { "value": "279", "unit": "", "label": "sessions", "isHighlight": false },
#     { "value": "1", "unit": "", "label": "commit", "isHighlight": true }
#   ],
#   "timeline": [
#     {
#       "time": "09:30",
#       "timeEnd": "11:00",
#       "messages": 127,
#       "shortName": "Calendar fix",
#       "title": "Statusline Bug Fix",
#       "description": "Fixed the next-meeting countdown...",
#       "color": "warm",
#       "tags": [ { "text": "bugfix", "color": "warm" } ],
#       "isCommit": false
#     }
#   ],
#   "workspaces": [
#     { "name": "ppm (root)", "count": 635, "percent": 63.5, "color": "accent", "colorDim": "accent-dim" }
#   ],
#   "agents": [
#     { "icon": "&#9678;", "name": "Claude Code", "count": "914", "label": "messages" }
#   ],
#   "heroNumber": "1",
#   "heroLabel": "Commit. 16,000 messages to get there."
# }

import argparse
import json
import math
import sys
from pathlib import Path

ARROW = "\u2192"  # →
DOT = "\u00b7"  # ·

COLOR_MAP = {
    "accent": "var(--accent)", "accent-dim": "var(--accent-dim)",
    "warm": "var(--warm)", "warm-dim": "var(--warm-dim)",
    "success": "var(--success)", "danger": "var(--danger)",
    "blue": "var(--blue)", "cyan": "var(--cyan)",
    "gold": "var(--gold)", "gold-dim": "var(--gold-dim)",
    "text-muted": "var(--text-muted)",
}

BORDER_MAP = {
    "accent": "var(--accent-dim)", "warm": "var(--warm-dim)",
    "success": "rgba(94,194,149,0.3)", "danger": "rgba(224,84,105,0.3)",
    "blue": "rgba(91,155,232,0.3)", "cyan": "rgba(92,206,196,0.3)",
    "gold": "var(--gold-dim)", "text-muted": "var(--border)",
}


def resolve_color(key):
    return COLOR_MAP.get(key, f"var(--{key})")


def resolve_border(key):
    return BORDER_MAP.get(key, "var(--border)")


def parse_time(time_str):
    parts = time_str.rstrip("+").split(":")
    return float(parts[0]) + float(parts[1]) / 60


def format_duration(hours):
    if hours >= 10:
        return "all day"
    if hours >= 1:
        h = math.floor(hours)
        m = round((hours - h) * 60 / 15) * 15
        if m == 0:
            return f"~{h}h"
        if m == 60:
            return f"~{h + 1}h"
        frac = {15: ".25", 30: ".5", 45: ".75"}[m]
        return f"~{h}{frac}h"
    mins = round(hours * 60)
    return f"~{mins}min"


def build_stats(data):
    parts = []
    for i, s in enumerate(data["stats"]):
        if i > 0:
            parts.append('<span class="stat-sep">&middot;</span>')
        cls = ' class="gold"' if s.get("isHighlight") else ""
        unit = f" {s['unit']}" if s.get("unit") else ""
        parts.append(f"<span><strong{cls}>{s['value']}</strong>{unit} {s['label']}</span>")
    return "".join(parts)


def build_lanes(data, axis_start, axis_span):
    html = ""
    for i, t in enumerate(data["timeline"]):
        start_h = parse_time(t["time"])
        end_h = parse_time(t["timeEnd"]) if t.get("timeEnd") else start_h + 0.25
        left_pct = round((start_h - axis_start) / axis_span * 100, 2)
        width_pct = round((end_h - start_h) / axis_span * 100, 2)
        bar_color = resolve_color(t["color"])
        delay = round(i * 0.05, 2)
        short_name = t.get("shortName") or t["title"][:15]

        tip_time = f"{t['time']} {ARROW} {t['timeEnd']}" if t.get("timeEnd") else t["time"]
        tip_msgs = f" {DOT} {t['messages']} msgs" if t.get("messages") else ""
        tip_text = f"{tip_time}{tip_msgs}"

        commit_class = " commit-marker" if t.get("isCommit") else ""
        width_style = "min-width:14px" if width_pct < 2 else f"width:{width_pct}%"

        html += (
            f'        <div class="lane">\n'
            f'          <div class="lane-label" style="color:{bar_color}">{short_name}</div>\n'
            f'          <div class="lane-track">\n'
            f'            <div class="lane-bar{commit_class}" style="left:{left_pct}%;{width_style};background:{bar_color};animation-delay:{delay}s" data-tip="{tip_text}"></div>\n'
            f'          </div>\n'
            f'        </div>\n'
        )
    return html


def build_axis(axis_start, axis_end, axis_span):
    html = ""
    for h in range(axis_start, axis_end + 1):
        pct = round((h - axis_start) / axis_span * 100, 2)
        label = f"{h:02d}"
        html += f'        <span style="left:{pct}%">{label}</span>\n'
    return html


def build_journal(data):
    html = ""
    for t in data["timeline"]:
        ev_color = resolve_color(t["color"])

        span_class = ""
        for tag in t.get("tags", []):
            if tag["text"] == "spanned all day":
                span_class = " spanning"
                break

        start_h = parse_time(t["time"])
        end_h = parse_time(t["timeEnd"]) if t.get("timeEnd") else None
        if end_h is not None:
            dur = format_duration(end_h - start_h)
            time_display = f"{t['time']} {ARROW} {t['timeEnd']} {DOT} {dur}"
        else:
            time_display = t["time"]

        msgs_html = ""
        if t.get("messages"):
            hl_class = " highlight" if t.get("isCommit") else ""
            msgs_html = f'<span class="event-msgs{hl_class}">{t["messages"]} msgs</span>'
        elif t.get("isCommit"):
            msgs_html = '<span class="event-msgs highlight">the commit</span>'

        tags_html = ""
        for tag in t.get("tags", []):
            tc = resolve_color(tag["color"])
            tb = resolve_border(tag["color"])
            tags_html += f'          <span class="tag" style="color:{tc};border-color:{tb}">{tag["text"]}</span>\n'

        html += (
            f'      <article class="event{span_class} reveal" style="--ev-color:{ev_color}">\n'
            f'        <div class="event-meta">\n'
            f'          <time class="event-time">{time_display}</time>\n'
            f'          {msgs_html}\n'
            f'        </div>\n'
            f'        <h3 class="event-title">{t["title"]}</h3>\n'
            f'        <p class="event-desc">{t["description"]}</p>\n'
            f'        <div class="event-tags">\n'
            f'{tags_html}        </div>\n'
            f'      </article>\n'
        )
    return html


def build_workspaces(data):
    html = ""
    for w in data["workspaces"]:
        wc = resolve_color(w["color"])
        wd = resolve_color(w["colorDim"])
        html += (
            f'      <div class="ws-row">\n'
            f'        <span class="ws-label">{w["name"]}</span>\n'
            f'        <div class="ws-track"><div class="ws-fill" style="width:{w["percent"]}%;background:linear-gradient(90deg,{wc},{wd})"></div></div>\n'
            f'        <span class="ws-num">{w["count"]}</span>\n'
            f'      </div>\n'
        )
    return html


def build_agents(data):
    html = ""
    for a in data["agents"]:
        html += (
            f'      <div class="agent-item">\n'
            f'        <span class="agent-glyph">{a["icon"]}</span>\n'
            f'        <span class="agent-name">{a["name"]}</span>\n'
            f'        <span class="agent-val">{a["count"]}</span>\n'
            f'        <span class="agent-unit">{a["label"]}</span>\n'
            f'      </div>\n'
        )
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate day-summary HTML from JSON data")
    parser.add_argument("--data-file", required=True, help="Path to JSON data file")
    parser.add_argument("--output-file", required=True, help="Path for output HTML file")
    args = parser.parse_args()

    with open(args.data_file, encoding="utf-8") as f:
        data = json.load(f)

    template_path = Path(__file__).resolve().parent / ".." / "assets" / "template.html"
    with open(template_path, encoding="utf-8") as f:
        html = f.read()

    # Compute time axis range
    all_starts = []
    all_ends = []
    for t in data["timeline"]:
        s = parse_time(t["time"])
        all_starts.append(s)
        all_ends.append(parse_time(t["timeEnd"]) if t.get("timeEnd") else s + 0.25)

    axis_start = math.floor(min(all_starts))
    axis_end = math.ceil(max(all_ends))
    axis_span = axis_end - axis_start

    # Build HTML fragments
    replacements = {
        "DATE_LONG": data["dateLong"],
        "DATE_DISPLAY": data["dateDisplay"],
        "HEADLINE": data["headline"],
        "SUBTITLE": data["subtitle"],
        "STATS_INLINE": build_stats(data),
        "DAYMAP_LANES": build_lanes(data, axis_start, axis_span),
        "DAYMAP_AXIS": build_axis(axis_start, axis_end, axis_span),
        "JOURNAL_ITEMS": build_journal(data),
        "WORKSPACE_ROWS": build_workspaces(data),
        "AGENT_ITEMS": build_agents(data),
        "HERO_NUMBER": data["heroNumber"],
        "HERO_LABEL": data["heroLabel"],
    }

    for key, value in replacements.items():
        html = html.replace(f"{{{{{key}}}}}", value)

    with open(args.output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Generated: {args.output_file}")


if __name__ == "__main__":
    main()
