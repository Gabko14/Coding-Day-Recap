# day-summary

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill that generates a visual HTML dashboard summarizing your daily AI coding sessions. It mines session data from [CASS](https://github.com/Dicklesworthstone/coding_agent_session_search), reads sessions deeply to build an accurate narrative, and produces a self-contained dark-themed dashboard.

![Day Summary Dashboard](examples/screenshot.png)

## What it does

1. **Gathers quantitative data** — session counts, hourly activity distribution, workspace breakdown, agent breakdown
2. **Reads sessions deeply** — uses agent teams to read the START, MIDDLE, and END of each significant session, cross-referencing findings across time blocks
3. **Builds an accurate narrative** — distinguishes "coded" from "reviewed" from "committed", traces activity threads across sessions, checks git history for ground truth
4. **Generates an HTML dashboard** — dark-themed, self-contained, with a Day Map swimlane visualization, journal feed, workspace breakdown, and a hero stat

## Prerequisites

- **[Claude Code](https://docs.anthropic.com/en/docs/claude-code)** — the CLI tool by Anthropic
- **[CASS](https://github.com/Dicklesworthstone/coding_agent_session_search)** — Coding Agent Session Search. Indexes sessions from Claude Code, Cursor, Codex, Gemini, and more
- **PowerShell** — scripts are written in PowerShell (ships with Windows)

## Platform

**Windows** (PowerShell). macOS/Linux support is planned but not yet implemented.

## Installation

1. Clone this repo:
   ```bash
   git clone https://github.com/YOUR_USERNAME/day-summary.git
   ```

2. Copy or symlink to your Claude Code skills directory:
   ```powershell
   # Option A: Symlink (recommended — stays in sync with git pulls)
   New-Item -ItemType Junction -Path "$HOME\.claude\skills\day-summary" -Target "C:\path\to\day-summary"

   # Option B: Copy
   Copy-Item -Recurse "C:\path\to\day-summary" "$HOME\.claude\skills\day-summary"
   ```

3. Verify the skill appears in Claude Code:
   ```
   /day-summary today
   ```

## Usage

In Claude Code, invoke the skill with a date:

```
/day-summary today
/day-summary yesterday
/day-summary 2026-02-09
```

The skill will:
1. Index your CASS data
2. Spawn an agent team to deeply read your sessions
3. Synthesize findings into a coherent timeline
4. Generate an HTML dashboard on your Desktop
5. Open it in your browser

## Agent Teams

This skill works best with **Claude Code agent teams** enabled. The team-based approach lets time-block readers communicate with each other — so when the morning reader sees "started reviewing feature X" and the afternoon reader sees "continued reviewing feature X", the team lead can merge them into one timeline item.

If agent teams are not available, the skill falls back to independent subagents. The main agent handles synthesis manually. This still works but may produce less accurate cross-session thread tracking.

## How it works

### Phase 1: Quantitative Data
Runs CASS queries to gather session counts, hourly distribution, workspace/agent breakdowns. Uses `gather-stats.ps1` with manual fallback commands.

### Phase 2: Narrative Building
The critical phase. Spawns an agent team with one reader per time block (morning, afternoon, evening) plus a git history checker. Each reader uses `cass expand` to deeply read sessions at multiple points. The team lead synthesizes findings — merging cross-block threads, deduplicating overlapping activities, resolving conflicts.

Key accuracy rules:
- **Check git history** to distinguish "coded today" from "committed code written last week"
- **Trace activities across sessions**, not within — many activities span multiple sessions
- **Name activities by what was done**, never by session size or tools used

### Phase 3: HTML Generation
Writes a data JSON file following the schema in `scripts/generate-html.ps1`, then generates a self-contained HTML dashboard with:
- **Day Map** — swimlane visualization showing activity bands across the day
- **Journal Feed** — detailed cards for each activity with descriptions and tags
- **Workspace Breakdown** — which repos got the most activity
- **Hero Stat** — the most striking number of the day

## File Structure

```
day-summary/
├── SKILL.md              # Claude Code skill definition
├── scripts/
│   ├── gather-stats.ps1  # CASS stats gatherer (PowerShell)
│   └── generate-html.ps1 # JSON → HTML generator (PowerShell)
├── assets/
│   └── template.html     # HTML/CSS template
├── examples/
│   └── screenshot.png    # Example dashboard
├── LICENSE
└── README.md
```

## License

MIT
