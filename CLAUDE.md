# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An [Agent Skill](https://agentskills.io) that generates a visual HTML dashboard summarizing a day's AI coding sessions. It mines session data from [CASS](https://github.com/Dicklesworthstone/coding_agent_session_search), reads sessions deeply via a subagent, and produces a self-contained dark-themed HTML dashboard. The skill is invoked via `/day-summary <date>`.

## Architecture

The skill runs in three phases, orchestrated by `SKILL.md`:

1. **Phase 1 — Data Gathering**: Runs `scripts/pre_extract.py` to call CASS CLI and produce per-time-block text files (morning/midday/afternoon/evening) plus a stats JSON. Also runs `scripts/browser_history.py` for non-coding activity and `scripts/calendar_events.py` for calendar events (meetings, routines).

2. **Phase 2 — Narrative Building**: A single subagent reads all extracted files + git history to build a timeline of activities. This is the accuracy-critical phase — the subagent must distinguish "coded today" vs "committed today" using git history.

3. **Phase 3 — HTML Generation**: The main agent writes a data JSON conforming to the schema at the top of `scripts/generate_html.py`, then runs the generator which injects data into `assets/template.html` via `{{PLACEHOLDER}}` replacement.

**Key design decision**: One subagent reads all time blocks (not one per block). This avoids cross-block merge conflicts and produces more consistent narratives for activities spanning multiple sessions.

## Running the Scripts

All scripts use Python 3 standard library only (no pip install needed). CASS must be installed separately (`pip install cass`).

```bash
# Pre-extract sessions for a time block (run 4x per day: morning/midday/afternoon/evening)
python3 scripts/pre_extract.py --from 2026-02-10T08:00 --until 2026-02-10T12:00 --output morning.txt --stats-output stats.json

# Extract browser history
python3 scripts/browser_history.py --date 2026-02-10 --output browser.txt

# Extract calendar events (macOS only — compiles Swift EventKit CLI on first run)
python3 scripts/calendar_events.py --date 2026-02-10 --output calendar.txt

# Generate HTML from data JSON
python3 scripts/generate_html.py --data-file data.json --output-file summary.html
```

## Data JSON Schema

The data JSON passed to `generate_html.py` must include: `dateLong`, `dateDisplay`, `headline`, `subtitle`, `stats[]`, `timeline[]` (with `time`, `timeEnd`, `shortName`, `title`, `description`, `color`, `tags[]`, `isCommit`, `isMeeting`), `workspaces[]`, `agents[]`, `heroNumber`, `heroLabel`. Full schema is documented in the comment block at lines 3-37 of `scripts/generate_html.py`.

## Template System

`assets/template.html` contains the full HTML/CSS/JS. The generator replaces `{{PLACEHOLDER}}` tokens (e.g., `{{HEADLINE}}`, `{{DAYMAP_LANES}}`, `{{JOURNAL_ITEMS}}`). The template uses Fraunces (serif) and Azeret Mono (monospace) from Google Fonts. CSS color variables (`--accent`, `--warm`, `--success`, `--danger`, `--blue`, `--cyan`, `--gold`, `--meeting`) map to timeline item colors.

## Naming Rules

Timeline `shortName` and `title` must describe **what was done**, never session metadata ("Mega session"), tool names ("deep-explore"), or vague labels ("Exploration"). Test: if someone reads only the name, can they tell what was accomplished?

## Issue Tracking

This project uses `bd` (beads) for issue tracking. See @AGENTS.md for the `bd` quick reference and mandatory session-close checklist (sync + push).
