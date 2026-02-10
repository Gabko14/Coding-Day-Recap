---
name: day-summary
description: Generate a visual HTML summary of a day's Claude Code sessions. Requires a date argument (e.g., "today", "yesterday", "2026-02-09"). Gathers CASS session data, reads key sessions, and produces a stunning dark-themed dashboard saved to the Desktop and opened in the browser.
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Task, WebFetch, WebSearch, TeamCreate, TeamDelete, SendMessage, TaskCreate, TaskUpdate, TaskList, TaskGet
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

### Phase 1: Gather Quantitative Data

1. **Resolve the date** to ISO format `YYYY-MM-DD`. For `today`/`yesterday`, compute from the current system date. **Always verify the day of the week** — never guess it:
   ```powershell
   powershell -Command "(Get-Date 'YYYY-MM-DD').DayOfWeek"
   ```

2. **Run CASS index** to ensure fresh data:
   ```bash
   cass index
   ```

3. **Run the stats gatherer script**:
   ```powershell
   powershell -File "~/.claude/skills/day-summary/scripts/gather-stats.ps1" -Date "YYYY-MM-DD"
   ```
   Returns JSON with: total sessions, unique sessions, total messages, hourly distribution, workspace breakdown, agent breakdown.

   **If the script fails**, gather stats manually with these cass commands:
   ```bash
   # Total sessions (from timeline footer)
   cass timeline --since YYYY-MM-DD --until YYYY-MM-DDT23:59:59 --agent claude_code
   # Workspace breakdown
   cass search "query" --since YYYY-MM-DD --until YYYY-MM-DDT23:59:59 --agent claude_code --limit 500 --json --aggregate workspace --max-tokens 2000
   # Agent breakdown
   cass search "query" --since YYYY-MM-DD --until YYYY-MM-DDT23:59:59 --limit 500 --json --aggregate agent --max-tokens 2000
   ```
   Use any non-empty search term (e.g., "the") instead of `*` — CASS rejects bare `*` in some modes.

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

#### Session Reading Strategy — Agent Team (Recommended)

Use an **agent team** so readers can cross-reference findings across time blocks. Isolated subagents can't tell each other "the review I see at 14:00 is the same thread you saw at 10:00" — teams can.

**1. Create a team** named `day-summary-YYYY-MM-DD`.

**2. Create tasks** from the timeline. Split the day into time blocks (e.g., morning, early afternoon, late afternoon, evening). Also create a `git-history` task. Each task should include:
- The time range to cover
- The list of significant user-driven sessions in that block (ignore subagent/teammate sessions with `<teammate-message` prefixes)
- Instructions to use `cass expand --line N -C 5 "PATH"` at START, MIDDLE, and END of each session
- Instructions to report: what happened, was this new work or review, key outcomes, and **which activity threads connect to other time blocks**

**3. Spawn teammates** (one per time block + one for git history). Use `general-purpose` subagent type. Each teammate should:
- Read their assigned sessions deeply
- Message the team lead with findings
- Flag any activity that clearly continues from or into another time block (e.g., "review started here, continues into afternoon")

**4. Synthesize as team lead.** After all teammates report back:
- **Merge cross-block threads** into single timeline items with time ranges spanning the full duration
- **Deduplicate** — if morning and afternoon agents both report "reviewed the same feature", that's one timeline item with a wide time range, not two separate items
- **Resolve conflicts** — if agents disagree on what happened, re-read the session yourself to break the tie

**5. Shut down the team** after synthesis is complete.

#### Session Reading Strategy — Independent Subagents (Fallback)

If agent teams are unavailable, launch independent subagents (one per time block + one for git history) using the Task tool. Each subagent should:
- Read their assigned sessions deeply using `cass expand`
- Return findings as text (what happened, work type, key outcomes)
- Flag any cross-block thread they notice

**You (the main agent) are responsible for synthesis**: merging cross-block threads, deduplicating, and resolving conflicts. This produces less accurate results than teams since subagents can't communicate, but still works.

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

**IMPORTANT: Do NOT start Phase 3 until Phase 2 is fully complete** — all teammates have reported back, threads are merged, and the final timeline is decided. Writing the JSON based on timeline titles before deep reading is done will produce inaccurate descriptions that need to be regenerated.

1. **Create a data JSON file** at `~/Desktop/day-data-YYYY-MM-DD.json` following the schema documented at the top of `scripts/generate-html.ps1`. The schema includes: dateLong, dateDisplay, headline, subtitle, stats array, timeline array (with time ranges for the Day Map swimlane visualization), workspaces array, agents array, heroNumber, heroLabel.

2. **Run the generator script**:
   ```powershell
   powershell -File "~/.claude/skills/day-summary/scripts/generate-html.ps1" -DataFile "~/Desktop/day-data-YYYY-MM-DD.json" -OutputFile "~/Desktop/day-summary-YYYY-MM-DD.html"
   ```

3. **Open in browser**:
   ```powershell
   powershell -Command "Start-Process '~/Desktop/day-summary-YYYY-MM-DD.html'"
   ```

4. **Present a text summary** as well — key stats and activity list.

### Headline Guidelines

Be creative and specific to the day. The headline should capture the day's essence, not be generic. Examples:
- "One Commit,<br><em>Infinite Review</em>" — for a day where one commit required massive review
- "Building the<br><em>Toolchain</em>" — for a tooling-focused day
- "Quiet<br><em>Refinement</em>" — for a day of small fixes and polish
- "The Migration<br><em>Sprint</em>" — for a day of heavy coding

The hero number at the bottom should be the most striking stat. "1 commit, 16,000 messages to get there" is more memorable than "279 sessions."
