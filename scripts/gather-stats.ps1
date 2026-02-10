# gather-stats.ps1 — Collect CASS session stats for a given date
# Usage: gather-stats.ps1 -Date "2026-02-09"
# Output: JSON object with hourly distribution, session count, workspace breakdown, agent breakdown
param(
    [Parameter(Mandatory=$true)]
    [string]$Date
)

# cass writes info/debug messages to stderr on nearly every command.
# Using "Stop" would treat all stderr output as terminating errors.
$ErrorActionPreference = "Continue"

# Run CASS index to ensure fresh data
cass index *>$null

# Get hourly message distribution
$data = cass search '*' --since $Date --until "$($Date)T23:59:59" --agent claude_code --limit 1000 --robot-format jsonl --fields created_at --max-tokens 10000 2>$null
$lines = $data | Where-Object { $_ -match 'created_at' }
$hours = @{}
$totalMessages = 0
foreach ($line in $lines) {
    if ($line -match '"created_at":(\d+)') {
        $ts = [long]$matches[1]
        $dt = [DateTimeOffset]::FromUnixTimeMilliseconds($ts).LocalDateTime
        $h = $dt.Hour
        if (-not $hours.ContainsKey($h)) { $hours[$h] = 0 }
        $hours[$h]++
        $totalMessages++
    }
}

# Get unique session count
$sessions = cass search '*' --since $Date --until "$($Date)T23:59:59" --agent claude_code --limit 500 --robot-format sessions 2>$null
$sessionCount = ($sessions | Where-Object { $_ -ne '' } | Measure-Object -Line).Lines

# Get timeline total (includes subagents)
$timeline = cass timeline --since $Date --until "$($Date)T23:59:59" --agent claude_code 2>$null
$totalLine = $timeline | Where-Object { $_ -match 'Total:' }
$totalSessions = 0
if ($totalLine -match 'Total:\s*(\d+)') { $totalSessions = [int]$matches[1] }

# Get workspace aggregation
$wsRaw = cass search '*' --since $Date --until "$($Date)T23:59:59" --agent claude_code --limit 500 --json --aggregate workspace --max-tokens 1000 2>$null
$wsJson = $wsRaw | ConvertFrom-Json
$workspaces = @()
if ($wsJson.aggregations -and $wsJson.aggregations.workspace) {
    foreach ($bucket in $wsJson.aggregations.workspace.buckets) {
        $workspaces += @{ name = $bucket.key; count = $bucket.count }
    }
}

# Get agent aggregation
$agRaw = cass search '*' --since $Date --until "$($Date)T23:59:59" --limit 500 --json --aggregate agent --max-tokens 1000 2>$null
$agJson = $agRaw | ConvertFrom-Json
$agents = @()
if ($agJson.aggregations -and $agJson.aggregations.agent) {
    foreach ($bucket in $agJson.aggregations.agent.buckets) {
        $agents += @{ name = $bucket.key; count = $bucket.count }
    }
}

# Compute time range
$sortedHours = $hours.Keys | Sort-Object
$startHour = if ($sortedHours.Count -gt 0) { $sortedHours[0] } else { 0 }
$endHour = if ($sortedHours.Count -gt 0) { $sortedHours[-1] } else { 23 }

# Build hourly data as simple object
$hourlyObj = @{}
foreach ($k in $hours.Keys) { $hourlyObj["$k"] = $hours[$k] }

# Output as JSON
$result = @{
    date = $Date
    totalSessions = $totalSessions
    uniqueSessions = $sessionCount
    totalMessages = $totalMessages
    startHour = $startHour
    endHour = $endHour
    hourly = $hourlyObj
    workspaces = $workspaces
    agents = $agents
}

$result | ConvertTo-Json -Depth 5
