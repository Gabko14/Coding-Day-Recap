---
name: day-summary
description: Generate a visual HTML summary of a day's AI coding sessions. Requires a date argument (e.g., "today", "yesterday", "2026-02-09"). Gathers CASS session data, reads key sessions, and produces a stunning dark-themed dashboard saved to the Desktop and opened in the browser.
---

# Day Summary Visualization

Generate a comprehensive visual HTML dashboard summarizing a day's AI coding activity. The output is a self-contained HTML file saved to the user's Desktop and opened in the browser.

## Required Argument

A date **must** be provided as the skill argument. Accepted formats:
- `today` — resolves to the current date
- `yesterday` — resolves to yesterday's date
- `YYYY-MM-DD` — explicit ISO date (e.g., `2026-02-09`)

If no date argument is provided, **ask the user** which day to visualize. Do not proceed without a date.

## Workflow

This skill requires [CASS](https://github.com/Dicklesworthstone/coding_agent_session_search) (`pip install cass`).

### Phase 1: Gather Data & Pre-Extract Sessions

1. **Resolve the date** to ISO format `YYYY-MM-DD`. For `today`/`yesterday`, compute from the current system date. **Always verify the day of the week** — never guess it:
   ```bash
   python3 -c "from datetime import datetime; print(datetime.strptime('YYYY-MM-DD', '%Y-%m-%d').strftime('%A'))"
   ```

2. **Run CASS index** to ensure fresh data:
   ```bash
   cass index
   ```

3. **Pre-extract sessions into time-block files** using the pre_extract script. This discovers sessions via `cass timeline --json`, parses `.jsonl` files directly, deduplicates streaming entries, and samples START/MIDDLE/END of each session. Run once per time block:
   ```bash
   # Morning (with stats for the full day)
   python3 scripts/pre_extract.py \
     --from YYYY-MM-DDT00:00:00 --until YYYY-MM-DDT12:00:00 \
     --output ~/Desktop/day-extract-morning.txt \
     --stats-output ~/Desktop/day-stats-YYYY-MM-DD.json

   # Midday
   python3 scripts/pre_extract.py \
     --from YYYY-MM-DDT12:00:00 --until YYYY-MM-DDT15:00:00 \
     --output ~/Desktop/day-extract-midday.txt

   # Afternoon
   python3 scripts/pre_extract.py \
     --from YYYY-MM-DDT15:00:00 --until YYYY-MM-DDT18:00:00 \
     --output ~/Desktop/day-extract-afternoon.txt

   # Evening (extends to 04:00 next day to capture late-night work)
   # Compute the next day's date first:
   # python3 -c "from datetime import datetime,timedelta; print((datetime.strptime('YYYY-MM-DD','%Y-%m-%d')+timedelta(days=1)).strftime('%Y-%m-%d'))"
   python3 scripts/pre_extract.py \
     --from YYYY-MM-DDT18:00:00 --until NEXT-DAYT04:00:00 \
     --output ~/Desktop/day-extract-evening.txt
   ```
   Replace `NEXT-DAY` with the computed next day's date (e.g., for `2026-02-09`, use `2026-02-10T04:00:00`).

   The `--stats-output` flag (only needed once) produces a JSON file with workspace/agent breakdowns, total sessions, and hourly distribution.

4. **Read the stats JSON** (`~/Desktop/day-stats-YYYY-MM-DD.json`) for workspace breakdown, agent breakdown, session totals, and hourly distribution.

5. **Extract browser history** for the target date. This captures work done outside coding sessions (PR reviews, Jira triage, manual testing, Confluence research, DevOps tools):
   ```bash
   python3 scripts/browser_history.py \
     --date YYYY-MM-DD \
     --output ~/Desktop/browser-history-YYYY-MM-DD.txt
   ```
   The script queries the Chromium `visits` table (Edge or Chrome) and outputs every page visit with `visit_duration` — the time spent on each page. Auth redirects show 0s, real work shows 30s+. Gap markers are inserted for 30+ minute gaps. If no browser is found, it writes an empty file and exits cleanly.

6. **Extract calendar events** for the target date. This captures meetings, routines, and all-day events from the system calendar (Exchange, Google, iCloud, etc.):
   ```bash
   python3 scripts/calendar_events.py \
     --date YYYY-MM-DD \
     --output ~/Desktop/calendar-YYYY-MM-DD.txt
   ```
   On macOS, the script compiles a Swift EventKit CLI (cached after first run) that reads from the system Calendar app. It outputs all timed events sorted chronologically, all-day events, and a CALENDARS FOUND summary. On other platforms, it writes an empty file and continues.

7. **Calendar selection.** Read the CALENDARS FOUND section from the calendar output file. Present the user with the list of calendars grouped by type and ask which to include:
   ```
   I found these calendars:
     Work: Kalender (Exchange, 3 events)
     Personal: Current Routine (Google, 5 events), Family (Google, 0 events)
     Holidays: United States holidays (1 all-day), Schweizerische Feiertage (1 all-day)
   Which should I include? [suggest Exchange calendars as default]
   ```
   Use the user's selection when building the Phase 2 subagent prompt — only pass events from the selected calendars. If the agent platform supports persistent memory, save the user's preference so future runs skip this step. If the calendar output is empty or says "none", skip this step entirely — the skill continues without calendar data.

### Phase 2: Build Accurate Narrative (CRITICAL)

This is the most important phase. **Accuracy over speed.** The narrative must reflect what ACTUALLY happened, not what session titles suggest.

#### Accuracy Rules

1. **Check git log** to distinguish "coded today" from "committed today". **Always filter by the user's author name** to exclude teammate/CI commits:
   ```bash
   # Get the user's git author name
   git config user.name
   # Then use it to filter
   git -C "<repo>" log --format="%h %ai %s" --since="YYYY-MM-DD" --until="NEXT-DAY" --all --author="<name>"
   ```
   Also check the previous few days for context. If today has one commit but the code existed before, the day was about REVIEWING/COMMITTING, not coding.

2. **Trace activities across sessions, not within.** Many activities span multiple sessions. The expert review skill might be used in session A, refined in session B, and validated in session C. Represent these as recurring threads with "spanned all day" tags, not as single-point events.

3. **Read sessions deeply.** The pre-extracted files sample the START, MIDDLE, and END of each session. Session titles and openers are often misleading about actual content — focus on what the conversation actually produced.

4. **Distinguish work types accurately:**
   - "Coded X" = wrote new code from scratch
   - "Reviewed X" = reviewed existing code (possibly written days ago)
   - "Committed X" = made a git commit (code may have been written weeks ago)
   - "Refined X" = iteratively improved an existing artifact (skill, config, etc.)
   - "Explored X" = researched/investigated without producing code
   - "Attempted X (reverted)" = tried something that didn't work out

5. **Never assign a single timestamp to work that spanned hours.** Use time ranges or "all day" annotations.

6. **Verify the day of the week.** Never assume. Always compute it.

#### Session Reading Strategy — Single Subagent

Launch **one subagent** (use a fast, cheap model) to read all pre-extracted files, browser history, and git history. Using a single reader produces a more consistent narrative — it sees activities spanning time blocks naturally and doesn't require cross-block merging or conflict resolution.

The subagent prompt should be:
```
You are building a timeline of a developer's day on YYYY-MM-DD.

Read these files (in order):
1. ~/Desktop/day-extract-morning.txt
2. ~/Desktop/day-extract-midday.txt
3. ~/Desktop/day-extract-afternoon.txt
4. ~/Desktop/day-extract-evening.txt
5. ~/Desktop/browser-history-YYYY-MM-DD.txt
6. ~/Desktop/calendar-YYYY-MM-DD.txt

Then run git log for each workspace found in ~/Desktop/day-stats-YYYY-MM-DD.json:
  git config user.name
  git -C "<workspace>" log --format="%h %ai %s" --since="YYYY-MM-DD" --until="NEXT-DAY" --all --author="<name>"

For each activity you identify, report:
- What work was done (coded, reviewed, explored, refined, committed)
- Time range (start and end)
- Workspace
- Key outcomes or artifacts produced
- Whether it spans multiple sessions (mark as "spanned" with full time range)

Use git history to distinguish "coded today" from "committed code written earlier."
Use browser history visit_duration to find work outside coding sessions (30s+ = real work, 0s = noise). Group repeated visits to the same site/PR/issue.

The user selected these calendars for inclusion: [CALENDAR_SELECTION].
Use calendar events from these calendars to explain gaps between coding sessions.
A 2-hour gap with a Sprint Planning meeting is not idle time — it's meeting time.
Report meetings as activities with isMeeting=true. All-day events (holidays) are
background context — note them but don't create timeline items for them.

Report as a flat list of activities sorted by time, with no overlap or duplication.
```

After the subagent returns, the main agent uses its findings to build the timeline. Browser-sourced items should NOT have a `messages` field and should use a subdued color to visually distinguish them.

#### Timeline Item Schema

Group activities into logical threads. For each timeline item, capture:
- **time** — "HH:MM" when it started
- **timeEnd** — "HH:MM" when it ended (omit for point events like a single commit)
- **messages** — number of messages in that activity (optional, shown as badge)
- **shortName** — label for the Day Map swimlane (max 25 chars, e.g., "Fix calendar next-meeting"). Must describe the ACTIVITY, not the session metadata. See naming rules below.
- **title** — full descriptive name (same naming rules as shortName, but can be longer)
- **description** — 2-3 sentences of what ACTUALLY happened (not what the title suggests)
- **color** — CSS variable: `accent` (purple), `warm` (orange), `success` (green), `danger` (red), `blue`, `cyan`, `gold` (for commits), `meeting` (desaturated slate, for calendar meetings)
- **tags** — array of `{ "text": "...", "color": "..." }` — category labels + "spanned all day" where applicable
- **isCommit** — `true` for the commit event (renders with gold glow marker in Day Map)
- **isMeeting** — `true` for calendar meetings (renders as muted background layer in Day Map)

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
   python3 scripts/generate_html.py --data-file ~/Desktop/day-data-YYYY-MM-DD.json --output-file ~/Desktop/day-summary-YYYY-MM-DD.html
   ```

3. **Clean up intermediate files** — remove the temp files from `~/Desktop/` that were created during Phase 1:
   ```bash
   rm -f ~/Desktop/day-extract-morning.txt ~/Desktop/day-extract-midday.txt \
         ~/Desktop/day-extract-afternoon.txt ~/Desktop/day-extract-evening.txt \
         ~/Desktop/day-stats-YYYY-MM-DD.json ~/Desktop/browser-history-YYYY-MM-DD.txt \
         ~/Desktop/calendar-YYYY-MM-DD.txt ~/Desktop/day-data-YYYY-MM-DD.json
   ```

4. **Open in browser** using the platform's default command (`open` on macOS, `xdg-open` on Linux, `Start-Process` on Windows).

5. **Present a text summary** as well — key stats and activity list.

### Headline Guidelines

Be creative and specific to the day. The headline should capture the day's essence, not be generic. Examples:
- "One Commit,<br><em>Infinite Review</em>" — for a day where one commit required massive review
- "Building the<br><em>Toolchain</em>" — for a tooling-focused day
- "Quiet<br><em>Refinement</em>" — for a day of small fixes and polish
- "The Migration<br><em>Sprint</em>" — for a day of heavy coding

The hero number at the bottom should be the most striking stat. "1 commit, 16,000 messages to get there" is more memorable than "279 sessions."
