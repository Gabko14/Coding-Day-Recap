# calendar_outlook.ps1 — Query Outlook calendar via COM for a given date.
# Called by calendar_events.py on Windows. Outputs pipe-delimited events to stdout
# in the same format as the macOS EventKit binary.
#
# Usage: powershell -ExecutionPolicy Bypass -File calendar_outlook.ps1 <YYYY-MM-DD>

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$DateStr
)

$ErrorActionPreference = "Stop"
# Use UTF-8 WITHOUT BOM — .NET Framework's [Encoding]::UTF8 includes BOM which
# can corrupt piped output and break startswith("ERROR:") checks in Python.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

# Parse date
try {
    $targetDate = [datetime]::ParseExact($DateStr, "yyyy-MM-dd", [System.Globalization.CultureInfo]::InvariantCulture)
} catch {
    Write-Output "ERROR: Invalid date format '$DateStr'. Use YYYY-MM-DD."
    exit 1
}

$dayStart = $targetDate.Date
$dayEnd = $dayStart.AddDays(1)

# Connect to Outlook
try {
    $outlook = New-Object -ComObject Outlook.Application
} catch {
    Write-Output "ERROR: Could not connect to Outlook. Is it installed?"
    exit 1
}

$ns = $outlook.GetNamespace("MAPI")

# Locale-safe formatter — .NET's ":" and "/" in format strings are locale-dependent
# placeholders, not literal characters. Must use InvariantCulture everywhere.
$inv = [System.Globalization.CultureInfo]::InvariantCulture

# Map store to friendly type name
function Get-StoreTypeName($store) {
    # ExchangeStoreType: 0=None, 1=Mailbox, 2=PublicFolder, 3=Delegate
    $storeType = $store.ExchangeStoreType
    switch ($storeType) {
        1 { return "Exchange" }
        2 { return "PublicFolder" }
        3 { return "Delegate" }
    }
    # ExchangeStoreType=0 can mean truly local (PST) or cached Exchange (OST).
    # Check if the file path is an OST (cached Exchange) vs PST (local).
    try {
        $path = $store.FilePath
        if ($path -and $path -match '\.ost$') { return "Exchange" }
    } catch {}
    return "Local"
}

# Format duration from minutes
function Format-Duration($minutes) {
    $h = [math]::Floor($minutes / 60)
    $m = $minutes % 60
    if ($h -gt 0 -and $m -gt 0) { return "${h}h${m}m" }
    if ($h -gt 0) { return "${h}h" }
    return "${m}m"
}

# Collect calendar folders from all stores
$calendarFolders = @()
$seenCalKeys = @{}  # track unique calendar keys to avoid duplicates
foreach ($store in $ns.Stores) {
    try {
        $calFolder = $store.GetDefaultFolder(9)  # olFolderCalendar = 9
        $storeTypeName = Get-StoreTypeName $store
        $uniqueKey = "$($calFolder.Name)|$storeTypeName|$($store.DisplayName)"
        if (-not $seenCalKeys.ContainsKey($uniqueKey)) {
            $seenCalKeys[$uniqueKey] = $true
            $calendarFolders += @{
                Folder = $calFolder
                Name = $calFolder.Name
                StoreName = $store.DisplayName
                StoreType = $storeTypeName
            }
        }

        # Check sub-folders of the calendar (shared calendars, team calendars)
        if ($calFolder.Folders.Count -gt 0) {
            foreach ($subFolder in $calFolder.Folders) {
                $subKey = "$($subFolder.Name)|$storeTypeName|$($store.DisplayName)"
                if (-not $seenCalKeys.ContainsKey($subKey)) {
                    $seenCalKeys[$subKey] = $true
                    $calendarFolders += @{
                        Folder = $subFolder
                        Name = $subFolder.Name
                        StoreName = $store.DisplayName
                        StoreType = $storeTypeName
                    }
                }
            }
        }
    } catch {
        # Store might not have a calendar folder — skip it
    }
}

if ($calendarFolders.Count -eq 0) {
    Write-Output "ERROR: No calendar folders found in Outlook."
    exit 1
}

# Collect all events from all calendar folders
$timedEvents = @()
$allDayEvents = @()

# Track which calendars have events (use store name for uniqueness)
$calTimedCounts = @{}
$calAllDayCounts = @{}

foreach ($cal in $calendarFolders) {
    $folder = $cal.Folder
    $calKey = "$($cal.Name)|$($cal.StoreType)|$($cal.StoreName)"

    if (-not $calTimedCounts.ContainsKey($calKey)) { $calTimedCounts[$calKey] = 0 }
    if (-not $calAllDayCounts.ContainsKey($calKey)) { $calAllDayCounts[$calKey] = 0 }

    try {
        $items = $folder.Items
        $items.Sort("[Start]")
        $items.IncludeRecurrences = $true

        # Restrict to target date — Outlook Jet filter expects MM/dd/yyyy format.
        $startFilter = $dayStart.ToString("MM/dd/yyyy HH:mm", $inv)
        $endFilter = $dayEnd.ToString("MM/dd/yyyy HH:mm", $inv)
        $filter = "[Start] >= '$startFilter' AND [Start] < '$endFilter'"
        $restricted = $items.Restrict($filter)

        foreach ($item in $restricted) {
            try {
                $startTime = $item.Start
                $endTime = $item.End

                # IncludeRecurrences + Restrict is unreliable in Outlook COM —
                # recurring events from other days can leak through. Manual check.
                if ($startTime -lt $dayStart -or $startTime -ge $dayEnd) { continue }

                $title = ($item.Subject -replace '\|', '/' -replace '[\r\n]+', ' ')
                if (-not $title) { $title = "?" }
                $location = ($item.Location -replace '\|', '/' -replace '[\r\n]+', ' ')
                if (-not $location) { $location = "" }

                $durationMin = [math]::Round(($endTime - $startTime).TotalMinutes)

                # Count attendees (includes organizer — matches EventKit behavior)
                $attendeeCount = 0
                try { $attendeeCount = $item.Recipients.Count } catch {}

                $calName = $cal.Name
                $storeTypeName = $cal.StoreType

                $eventObj = @{
                    Start = $startTime
                    End = $endTime
                    Duration = $durationMin
                    Title = $title
                    Location = $location
                    CalName = $calName
                    StoreType = $storeTypeName
                    Attendees = $attendeeCount
                    AllDay = $item.AllDayEvent
                }

                if ($item.AllDayEvent) {
                    $allDayEvents += $eventObj
                    $calAllDayCounts[$calKey] += 1
                } else {
                    $timedEvents += $eventObj
                    $calTimedCounts[$calKey] += 1
                }
            } catch {
                # Skip items that can't be read
            }
        }
    } catch {
        # Folder access failed — skip
    }
}

# Sort timed events by start time (wrap in @() to ensure array type even if 0-1 items)
$timedEvents = @($timedEvents | Sort-Object { $_.Start })

# Calculate total meeting time
$totalMeetingMinutes = 0
foreach ($ev in $timedEvents) {
    $totalMeetingMinutes += $ev.Duration
}
$meetingTimeStr = Format-Duration $totalMeetingMinutes

# Output in the same format as the Swift EventKit binary
Write-Output "CALENDAR EVENTS: $DateStr"
Write-Output "Source: Outlook (COM) | $($calendarFolders.Count) calendars | $($timedEvents.Count) timed events | $($allDayEvents.Count) all-day events | $meetingTimeStr meeting time"
Write-Output "=========================="
Write-Output ""

# Timed events
Write-Output "--- TIMED EVENTS (sorted by start time) ---"
Write-Output ""
if ($timedEvents.Count -eq 0) {
    Write-Output "(none)"
} else {
    foreach ($ev in $timedEvents) {
        $startStr = $ev.Start.ToString("HH:mm", $inv)
        $endStr = $ev.End.ToString("HH:mm", $inv)
        $durStr = (Format-Duration $ev.Duration).PadRight(5)
        Write-Output "$startStr-$endStr | $durStr | $($ev.Title) | $($ev.CalName) ($($ev.StoreType)) | $($ev.Attendees) attendees | $($ev.Location)"
    }
}
Write-Output ""

# All-day events
Write-Output "--- ALL-DAY EVENTS ---"
Write-Output ""
if ($allDayEvents.Count -eq 0) {
    Write-Output "(none)"
} else {
    foreach ($ev in $allDayEvents) {
        Write-Output "$($ev.Title) ($($ev.CalName))"
    }
}
Write-Output ""

# Calendar summary
Write-Output "--- CALENDARS FOUND ---"
Write-Output ""
foreach ($cal in $calendarFolders) {
    $storeTypeName = $cal.StoreType
    $calKey = "$($cal.Name)|$storeTypeName|$($cal.StoreName)"
    $timed = $calTimedCounts[$calKey]
    $allDay = $calAllDayCounts[$calKey]

    $parts = @()
    if ($timed -gt 0) {
        $s = if ($timed -eq 1) { "" } else { "s" }
        $parts += "$timed timed event$s"
    }
    if ($allDay -gt 0) {
        $s = if ($allDay -eq 1) { "" } else { "s" }
        $parts += "$allDay all-day event$s"
    }
    $countStr = if ($parts.Count -eq 0) { "0 events" } else { $parts -join ", " }

    # Include store name when it differs from calendar name (for disambiguation)
    $storeLabel = $storeTypeName
    if ($cal.StoreName -and $cal.StoreName -ne $cal.Name) {
        $storeLabel = "$storeTypeName, $($cal.StoreName)"
    }
    Write-Output "$($cal.Name) | $storeLabel | $countStr"
}
