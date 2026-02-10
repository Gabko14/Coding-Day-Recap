# generate-html.ps1 — Generate day-summary HTML from a JSON data file
# Usage: generate-html.ps1 -DataFile "data.json" -OutputFile "summary.html"
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
#       "timeEnd": "11:00",          // optional — omit for point events
#       "messages": 127,             // optional — shown as badge
#       "shortName": "Calendar fix", // short label for daymap lane (<=15 chars)
#       "title": "Statusline Bug Fix",
#       "description": "Fixed the next-meeting countdown...",
#       "color": "warm",
#       "tags": [ { "text": "bugfix", "color": "warm" } ],
#       "isCommit": false            // optional — true for the gold commit marker
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

param(
    [Parameter(Mandatory=$true)][string]$DataFile,
    [Parameter(Mandatory=$true)][string]$OutputFile
)

$ErrorActionPreference = "Stop"

# --- Helpers ---

function ParseTime([string]$timeStr) {
    $parts = $timeStr.TrimEnd('+') -split ':'
    return [double]$parts[0] + [double]$parts[1] / 60
}

function FormatDuration([double]$hours) {
    if ($hours -ge 10) { return "all day" }
    if ($hours -ge 1) {
        $h = [Math]::Floor($hours)
        $m = [Math]::Round(($hours - $h) * 60 / 15) * 15
        if ($m -eq 0) { return "~${h}h" }
        if ($m -eq 60) { return "~$($h+1)h" }
        $frac = if ($m -eq 15) { ".25" } elseif ($m -eq 30) { ".5" } else { ".75" }
        return "~${h}${frac}h"
    }
    $mins = [Math]::Round($hours * 60)
    return "~${mins}min"
}

# --- Unicode chars (avoid `u{} escapes that break in pipelines) ---

$arrow = [char]0x2192   # →
$dot   = [char]0x00B7   # ·

# --- Color maps ---

$colorMap = @{
    "accent"="var(--accent)"; "accent-dim"="var(--accent-dim)"
    "warm"="var(--warm)"; "warm-dim"="var(--warm-dim)"
    "success"="var(--success)"; "danger"="var(--danger)"
    "blue"="var(--blue)"; "cyan"="var(--cyan)"
    "gold"="var(--gold)"; "gold-dim"="var(--gold-dim)"
    "text-muted"="var(--text-muted)"
}
$borderMap = @{
    "accent"="var(--accent-dim)"; "warm"="var(--warm-dim)"
    "success"="rgba(94,194,149,0.3)"; "danger"="rgba(224,84,105,0.3)"
    "blue"="rgba(91,155,232,0.3)"; "cyan"="rgba(92,206,196,0.3)"
    "gold"="var(--gold-dim)"; "text-muted"="var(--border)"
}

function ResolveColor([string]$key) {
    if ($colorMap[$key]) { return $colorMap[$key] }
    return "var(--$key)"
}

function ResolveBorder([string]$key) {
    if ($borderMap[$key]) { return $borderMap[$key] }
    return "var(--border)"
}

# --- Read data ---

$data = Get-Content $DataFile -Raw | ConvertFrom-Json
$templatePath = Join-Path $PSScriptRoot "..\assets\template.html"
$html = Get-Content $templatePath -Raw

# --- Compute time axis range ---

$allStarts = @()
$allEnds = @()
foreach ($t in $data.timeline) {
    $s = ParseTime $t.time
    $allStarts += $s
    if ($t.timeEnd) {
        $allEnds += (ParseTime $t.timeEnd)
    } else {
        $allEnds += ($s + 0.25)
    }
}
$axisStart = [Math]::Floor(($allStarts | Measure-Object -Minimum).Minimum)
$axisEnd = [Math]::Ceiling(($allEnds | Measure-Object -Maximum).Maximum)
$axisSpan = $axisEnd - $axisStart

# --- Build inline stats ---

$statsHtml = ""
$statIndex = 0
foreach ($s in $data.stats) {
    if ($statIndex -gt 0) {
        $statsHtml += '<span class="stat-sep">&middot;</span>'
    }
    $cls = if ($s.isHighlight) { ' class="gold"' } else { "" }
    $unitText = if ($s.unit) { " $($s.unit)" } else { "" }
    $statsHtml += "<span><strong$cls>$($s.value)</strong>$unitText $($s.label)</span>"
    $statIndex++
}

# --- Build daymap lanes ---

$lanesHtml = ""
$laneIndex = 0
foreach ($t in $data.timeline) {
    $startH = ParseTime $t.time
    $endH = if ($t.timeEnd) { ParseTime $t.timeEnd } else { $startH + 0.25 }
    $leftPct = [Math]::Round(($startH - $axisStart) / $axisSpan * 100, 2)
    $widthPct = [Math]::Round(($endH - $startH) / $axisSpan * 100, 2)
    $barColor = ResolveColor $t.color
    $delay = [Math]::Round($laneIndex * 0.05, 2)
    $shortName = if ($t.shortName) { $t.shortName } else { $t.title.Substring(0, [Math]::Min(15, $t.title.Length)) }

    # Tooltip
    $tipTime = if ($t.timeEnd) { "$($t.time) $arrow $($t.timeEnd)" } else { $t.time }
    $tipMsgs = if ($t.messages) { " $dot $($t.messages) msgs" } else { "" }
    $tipText = "${tipTime}${tipMsgs}"

    # Commit marker class
    $commitClass = if ($t.isCommit) { " commit-marker" } else { "" }

    # Min-width for tiny bars
    $widthStyle = if ($widthPct -lt 2) { "min-width:14px" } else { "width:${widthPct}%" }

    $lanesHtml += @"
        <div class="lane">
          <div class="lane-label" style="color:$barColor">$shortName</div>
          <div class="lane-track">
            <div class="lane-bar$commitClass" style="left:${leftPct}%;${widthStyle};background:$barColor;animation-delay:${delay}s" data-tip="$tipText"></div>
          </div>
        </div>

"@
    $laneIndex++
}

# --- Build daymap axis ---

$axisHtml = ""
for ($h = $axisStart; $h -le $axisEnd; $h++) {
    $pct = [Math]::Round(($h - $axisStart) / $axisSpan * 100, 2)
    $label = "{0:D2}" -f [int]$h
    $axisHtml += "        <span style=`"left:${pct}%`">$label</span>`n"
}

# --- Build journal items ---

$journalHtml = ""
foreach ($t in $data.timeline) {
    $evColor = ResolveColor $t.color

    # Spanning detection
    $spanClass = ""
    foreach ($tag in $t.tags) {
        if ($tag.text -eq "spanned all day") { $spanClass = " spanning"; break }
    }

    # Time display with duration
    $startH = ParseTime $t.time
    $endH = if ($t.timeEnd) { ParseTime $t.timeEnd } else { $null }
    if ($endH) {
        $dur = FormatDuration ($endH - $startH)
        $timeDisplay = "$($t.time) $arrow $($t.timeEnd) $dot $dur"
    } else {
        $timeDisplay = $t.time
    }

    # Message badge
    $msgsHtml = ""
    if ($t.messages) {
        $hlClass = if ($t.isCommit) { " highlight" } else { "" }
        $msgsHtml = "<span class=`"event-msgs$hlClass`">$($t.messages) msgs</span>"
    } elseif ($t.isCommit) {
        $msgsHtml = "<span class=`"event-msgs highlight`">the commit</span>"
    }

    # Tags
    $tagsHtml = ""
    foreach ($tag in $t.tags) {
        $tc = ResolveColor $tag.color
        $tb = ResolveBorder $tag.color
        $tagsHtml += "          <span class=`"tag`" style=`"color:$tc;border-color:$tb`">$($tag.text)</span>`n"
    }

    $journalHtml += @"
      <article class="event$spanClass reveal" style="--ev-color:$evColor">
        <div class="event-meta">
          <time class="event-time">$timeDisplay</time>
          $msgsHtml
        </div>
        <h3 class="event-title">$($t.title)</h3>
        <p class="event-desc">$($t.description)</p>
        <div class="event-tags">
$tagsHtml        </div>
      </article>

"@
}

# --- Build workspace rows ---

$wsHtml = ""
foreach ($w in $data.workspaces) {
    $wc = ResolveColor $w.color
    $wd = ResolveColor $w.colorDim
    $wsHtml += @"
      <div class="ws-row">
        <span class="ws-label">$($w.name)</span>
        <div class="ws-track"><div class="ws-fill" style="width:$($w.percent)%;background:linear-gradient(90deg,$wc,$wd)"></div></div>
        <span class="ws-num">$($w.count)</span>
      </div>

"@
}

# --- Build agent items ---

$agentsHtml = ""
foreach ($a in $data.agents) {
    $agentsHtml += @"
      <div class="agent-item">
        <span class="agent-glyph">$($a.icon)</span>
        <span class="agent-name">$($a.name)</span>
        <span class="agent-val">$($a.count)</span>
        <span class="agent-unit">$($a.label)</span>
      </div>

"@
}

# --- Replace placeholders ---

$html = $html -replace '\{\{DATE_LONG\}\}', $data.dateLong
$html = $html -replace '\{\{DATE_DISPLAY\}\}', $data.dateDisplay
$html = $html -replace '\{\{HEADLINE\}\}', $data.headline
$html = $html -replace '\{\{SUBTITLE\}\}', $data.subtitle
$html = $html -replace '\{\{STATS_INLINE\}\}', $statsHtml
$html = $html -replace '\{\{DAYMAP_LANES\}\}', $lanesHtml
$html = $html -replace '\{\{DAYMAP_AXIS\}\}', $axisHtml
$html = $html -replace '\{\{JOURNAL_ITEMS\}\}', $journalHtml
$html = $html -replace '\{\{WORKSPACE_ROWS\}\}', $wsHtml
$html = $html -replace '\{\{AGENT_ITEMS\}\}', $agentsHtml
$html = $html -replace '\{\{HERO_NUMBER\}\}', $data.heroNumber
$html = $html -replace '\{\{HERO_LABEL\}\}', $data.heroLabel

# --- Write output ---

$html | Out-File -FilePath $OutputFile -Encoding utf8
Write-Host "Generated: $OutputFile"
