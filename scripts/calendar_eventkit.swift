#!/usr/bin/swift
// calendar_eventkit.swift — Query macOS Calendar via EventKit for a given date.
// Called by calendar_events.py. Outputs pipe-delimited events to stdout.
//
// Usage: ./calendar_eventkit <YYYY-MM-DD>
// Output: structured text with timed events, all-day events, and calendar summary.

import EventKit
import Foundation

// Parse date argument
guard CommandLine.arguments.count >= 2 else {
    print("ERROR: Usage: calendar_eventkit <YYYY-MM-DD>")
    exit(1)
}

let dateStr = CommandLine.arguments[1]
let dateFmt = DateFormatter()
dateFmt.dateFormat = "yyyy-MM-dd"
dateFmt.locale = Locale(identifier: "en_US_POSIX")

guard let targetDate = dateFmt.date(from: dateStr) else {
    print("ERROR: Invalid date format '\(dateStr)'. Use YYYY-MM-DD.")
    exit(1)
}

let store = EKEventStore()
let semaphore = DispatchSemaphore(value: 0)

store.requestFullAccessToEvents { granted, error in
    guard granted else {
        print("ACCESS_DENIED")
        semaphore.signal()
        return
    }

    let cal = Calendar.current
    let dayStart = cal.startOfDay(for: targetDate)
    let dayEnd = cal.date(byAdding: .day, value: 1, to: dayStart)!

    let calendars = store.calendars(for: .event)
    let predicate = store.predicateForEvents(withStart: dayStart, end: dayEnd, calendars: nil)
    let events = store.events(matching: predicate)

    let timeFmt = DateFormatter()
    timeFmt.dateFormat = "HH:mm"

    // Separate timed vs all-day events
    var timedEvents: [EKEvent] = []
    var allDayEvents: [EKEvent] = []
    for event in events {
        if event.isAllDay {
            allDayEvents.append(event)
        } else {
            timedEvents.append(event)
        }
    }

    // Sort timed events by start time
    timedEvents.sort { $0.startDate < $1.startDate }

    // Calculate total meeting time for timed events
    var totalMeetingMinutes = 0
    for event in timedEvents {
        let mins = Int(event.endDate.timeIntervalSince(event.startDate) / 60)
        totalMeetingMinutes += mins
    }
    let meetingHours = totalMeetingMinutes / 60
    let meetingMins = totalMeetingMinutes % 60
    var meetingTimeStr: String
    if meetingHours > 0 && meetingMins > 0 {
        meetingTimeStr = "\(meetingHours)h\(meetingMins)m"
    } else if meetingHours > 0 {
        meetingTimeStr = "\(meetingHours)h"
    } else {
        meetingTimeStr = "\(meetingMins)m"
    }

    // Source type names
    let typeNames = ["Local", "Exchange", "CalDAV", "MobileMe", "Subscribed", "Birthdays"]

    func sourceTypeName(_ source: EKSource) -> String {
        let raw = Int(source.sourceType.rawValue)
        return raw < typeNames.count ? typeNames[raw] : "Unknown(\(raw))"
    }

    func formatDuration(_ minutes: Int) -> String {
        let h = minutes / 60
        let m = minutes % 60
        if h > 0 && m > 0 { return "\(h)h\(m)m" }
        if h > 0 { return "\(h)h" }
        return "\(m)m"
    }

    // Header
    print("CALENDAR EVENTS: \(dateStr)")
    print("Source: macOS Calendar (EventKit) | \(calendars.count) calendars | \(timedEvents.count) timed events | \(allDayEvents.count) all-day events | \(meetingTimeStr) meeting time")
    print("==========================")
    print("")

    // Timed events
    print("--- TIMED EVENTS (sorted by start time) ---")
    print("")
    if timedEvents.isEmpty {
        print("(none)")
    } else {
        for event in timedEvents {
            let startStr = timeFmt.string(from: event.startDate)
            let endStr = timeFmt.string(from: event.endDate)
            let durationMin = Int(event.endDate.timeIntervalSince(event.startDate) / 60)
            let durStr = formatDuration(durationMin)
            let title = (event.title ?? "?").replacingOccurrences(of: "|", with: "/")
                .replacingOccurrences(of: "\n", with: " ")
            let calName = event.calendar.title
            let srcType = sourceTypeName(event.calendar.source)
            let attendees = event.attendees?.count ?? 0
            let location = (event.location ?? "")
                .replacingOccurrences(of: "|", with: "/")
                .replacingOccurrences(of: "\n", with: " ")

            print("\(startStr)-\(endStr) | \(durStr.padding(toLength: 5, withPad: " ", startingAt: 0)) | \(title) | \(calName) (\(srcType)) | \(attendees) attendees | \(location)")
        }
    }
    print("")

    // All-day events
    print("--- ALL-DAY EVENTS ---")
    print("")
    if allDayEvents.isEmpty {
        print("(none)")
    } else {
        for event in allDayEvents {
            let title = (event.title ?? "?").replacingOccurrences(of: "|", with: "/")
                .replacingOccurrences(of: "\n", with: " ")
            let calName = event.calendar.title
            print("\(title) (\(calName))")
        }
    }
    print("")

    // Calendar summary
    print("--- CALENDARS FOUND ---")
    print("")

    // Count events per calendar
    var calTimedCounts: [String: Int] = [:]
    var calAllDayCounts: [String: Int] = [:]
    for event in timedEvents {
        calTimedCounts[event.calendar.calendarIdentifier, default: 0] += 1
    }
    for event in allDayEvents {
        calAllDayCounts[event.calendar.calendarIdentifier, default: 0] += 1
    }

    for calendar in calendars.sorted(by: { $0.title < $1.title }) {
        let timed = calTimedCounts[calendar.calendarIdentifier] ?? 0
        let allDay = calAllDayCounts[calendar.calendarIdentifier] ?? 0
        let srcType = sourceTypeName(calendar.source)

        var parts: [String] = []
        if timed > 0 { parts.append("\(timed) timed event\(timed == 1 ? "" : "s")") }
        if allDay > 0 { parts.append("\(allDay) all-day event\(allDay == 1 ? "" : "s")") }
        let countStr = parts.isEmpty ? "0 events" : parts.joined(separator: ", ")

        print("\(calendar.title) | \(srcType) | \(countStr)")
    }

    semaphore.signal()
}

semaphore.wait()
