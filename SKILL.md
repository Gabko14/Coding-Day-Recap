---
name: day-summary
description: Generate a visual HTML summary of a day's Claude Code sessions. Requires a date argument (e.g., "today", "yesterday", "2026-02-09"). Gathers CASS session data, reads key sessions, and produces a stunning dark-themed dashboard saved to the Desktop and opened in the browser.
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Task, WebFetch, WebSearch
---

# Day Summary Visualization

Generate a comprehensive visual HTML dashboard summarizing a day's Claude Code activity. The output is a self-contained HTML file saved to the user's Desktop and opened in the browser.

## Required Argument

A date **must** be provided as the skill argument. Accepted formats:
- `today` — resolves to the current date
- `yesterday` — resolves to yesterday's date
- `YYYY-MM-DD` — explicit ISO date (e.g., `2026-02-09`)

If no date argument is provided, **ask the user** which day to visualize. Do not proceed without a date.

## Workflow

### Phase 0: Ensure Haiku Reader Agent Exists

Session readers use a lightweight Haiku-based custom agent for cost efficiency. Run the setup script:

```bash
bash ~/.claude/skills/day-summary/scripts/setup-agent.sh
```

If the agent was just created, tell the user to run `/agents` or restart the session, then re-invoke the skill.

### Phase 1: Gather Quantitative Data

1. **Resolve the date** to ISO format `YYYY-MM-DD`. For `today`/`yesterday`, compute from the current system date. **Always verify the day of the week** — never guess it:
   ```bash
   python3 -c "from datetime import datetime; print(datetime.strptime('YYYY-MM-DD', '%Y-%m-%d').strftime('%A'))"
   ```

2. **Run CASS index** to ensure fresh data:
   ```bash
   cass index
   ```

3. **Gather stats** from CASS. Run these commands and aggregate the results:
   ```bash
   # Total sessions (from timeline footer)
   cass timeline --since YYYY-MM-DD --until YYYY-MM-DDT23:59:59 --agent claude_code
   # Workspace breakdown
   cass search "query" --since YYYY-MM-DD --until YYYY-MM-DDT23:59:59 --agent claude_code --limit 500 --json --aggregate workspace --max-tokens 2000
   # Agent breakdown
   cass search "query" --since YYYY-MM-DD --until YYYY-MM-DDT23:59:59 --limit 500 --json --aggregate agent --max-tokens 2000
   ```
   Use any non-empty search term (e.g., "the") instead of `*` — CASS rejects bare `*` in some modes.
   Collect: total sessions, unique sessions, total messages, hourly distribution, workspace breakdown, agent breakdown.

4. **Get the timeline** for session listing:
   ```bash
   cass timeline --since YYYY-MM-DD --until YYYY-MM-DDT23:59:59 --agent claude_code
   ```

5. **Get session file paths** for deep reading. `cass timeline` doesn't output machine-readable paths. To find actual session files, use:
   ```bash
   cass search "keyword" --since YYYY-MM-DD --until YYYY-MM-DDT23:59:59 --agent claude_code --limit 10 --robot-format sessions
   ```
   Use a keyword relevant to the session (from its title in the timeline). This returns `.jsonl` file paths that can be passed to `cass expand`.

### Phase 2: Build Accurate Narrative (CRITICAL)

This is the most important phase. **Accuracy over speed.** The narrative must reflect what ACTUALLY happened, not what session titles suggest.

#### Accuracy Rules

1. **Check git log** to distinguish "coded today" from "committed today":
   ```bash
   git -C "<repo>" log --format="%h %ai %s" --since="YYYY-MM-DD" --until="YYYY-MM-DD+1" --all
   ```
   Also check the previous few days for context. If today has one commit but the code existed before, the day was about REVIEWING/COMMITTING, not coding.

2. **Trace activities across sessions, not within.** Many activities span multiple sessions. The expert review skill might be used in session A, refined in session B, and validated in session C. Represent these as recurring threads with "spanned all day" tags, not as single-point events.

3. **Read sessions deeply.** Read 10+ sample points across each major session using `cass expand --line N -C 5 "PATH"`. Read the START (what kicked it off), MIDDLE (what it evolved into), and END (what was the outcome). Session titles and openers are often misleading about actual content.

4. **Distinguish work types accurately:**
   - "Coded X" = wrote new code from scratch
   - "Reviewed X" = reviewed existing code (possibly written days ago)
   - "Committed X" = made a git commit (code may have been written weeks ago)
   - "Refined X" = iteratively improved an existing artifact (skill, config, etc.)
   - "Explored X" = researched/investigated without producing code
   - "Attempted X (reverted)" = tried something that didn't work out

5. **Never assign a single timestamp to work that spanned hours.** Use time ranges or "all day" annotations.

6. **Verify the day of the week.** Never assume. Always compute it.

#### Session Reading Strategy — Independent Haiku Subagents

Launch independent subagents in parallel (one per time block + one for git history) using the Task tool with `haiku-reader` subagent type (set up in Phase 0). This ensures session readers run on Haiku for cost efficiency.

**1. Split the day into time blocks** (e.g., morning, early afternoon, late afternoon, evening). Also create a git-history task.

**2. Launch subagents in parallel** using a single message with multiple Task tool calls. Each subagent prompt should include:
- The time range to cover
- The list of significant user-driven sessions in that block (ignore subagent/teammate sessions with `<teammate-message` prefixes)
- Session file paths (from Phase 1) and instructions to use `cass expand --line N -C 5 "PATH"` at START, MIDDLE, and END of each session
- Instructions to report: what happened, was this new work or review, key outcomes, and any activity that clearly continues into another time block

**3. Synthesize after all subagents return.** You (the main agent) are responsible for:
- **Merging cross-block threads** into single timeline items with time ranges spanning the full duration
- **Deduplicating** — if morning and afternoon subagents both report "reviewed the same feature", that's one timeline item with a wide time range, not two separate items
- **Resolving conflicts** — if subagents disagree on what happened, re-read the session yourself to break the tie

> **Note:** Agent teams (`TeamCreate`) can theoretically improve cross-block communication, but currently do not respect custom agent model overrides — teammates will run on the global model (e.g., Opus) regardless of the `haiku-reader` agent definition. Use independent subagents until this is fixed.

#### Timeline Item Schema

Group activities into logical threads. For each timeline item, capture:
- **time** — "HH:MM" when it started
- **timeEnd** — "HH:MM" when it ended (omit for point events like a single commit)
- **messages** — number of messages in that activity (optional, shown as badge)
- **shortName** — short label for the Day Map swimlane (max 15 chars, e.g., "Calendar fix"). Must describe the ACTIVITY, not the session metadata. See naming rules below.
- **title** — full descriptive name. Must describe the ACTIVITY, not the session metadata. See naming rules below.
- **description** — 2-3 sentences of what ACTUALLY happened (not what the title suggests)
- **color** — CSS variable: `accent` (purple), `warm` (orange), `success` (green), `danger` (red), `blue`, `cyan`, `gold` (for commits)
- **tags** — array of `{ "text": "...", "color": "..." }` — category labels + "spanned all day" where applicable
- **isCommit** — `true` for the commit event (renders with gold glow marker in Day Map)

#### Naming Rules for shortName and title

Names must describe **what was done**, never how big the session was or what tool/agent was involved.

**NEVER use:**
- Session metadata as names: "Mega session", "Long session", "Big refactor session", "Quick fix"
- Tool/agent names as activity labels: "deep-explore", "ppm-explorer", "Ralph Loop run"
- Vague meta-labels: "Skill forge", "Deep review", "Exploration"

**ALWAYS use:**
- The actual work product: "Fix DI registration blocker", "Author SQL migration skill"
- The domain concept: "LoadBoteLaufroute review", "Event subscription wiring"
- The concrete outcome: "Built CASS exploration agent", "Validated skills against git history"

Test: if someone reads only the shortName/title, can they tell what was accomplished? "Mega session" = no. "Fix 2 blockers + author 2 skills" = yes.

### Phase 3: Generate HTML

**IMPORTANT: Do NOT start Phase 3 until Phase 2 is fully complete** — all subagents have returned, threads are merged, and the final timeline is decided. Writing the JSON based on timeline titles before deep reading is done will produce inaccurate descriptions that need to be regenerated.

1. **Create a data JSON file** at `~/Desktop/day-data-YYYY-MM-DD.json` following the schema documented at the top of `scripts/generate_html.py`. The schema includes: dateLong, dateDisplay, headline, subtitle, stats array, timeline array (with time ranges for the Day Map swimlane visualization), workspaces array, agents array, heroNumber, heroLabel.

2. **Run the generator script**:
   ```bash
   python3 ~/.claude/skills/day-summary/scripts/generate_html.py --data-file ~/Desktop/day-data-YYYY-MM-DD.json --output-file ~/Desktop/day-summary-YYYY-MM-DD.html
   ```

3. **Open in browser** using the platform's default command (`open` on macOS, `xdg-open` on Linux, `Start-Process` on Windows).

4. **Present a text summary** as well — key stats and activity list.

### Headline Guidelines

Be creative and specific to the day. The headline should capture the day's essence, not be generic. Examples:
- "One Commit,<br><em>Infinite Review</em>" — for a day where one commit required massive review
- "Building the<br><em>Toolchain</em>" — for a tooling-focused day
- "Quiet<br><em>Refinement</em>" — for a day of small fixes and polish
- "The Migration<br><em>Sprint</em>" — for a day of heavy coding

The hero number at the bottom should be the most striking stat. "1 commit, 16,000 messages to get there" is more memorable than "279 sessions."
