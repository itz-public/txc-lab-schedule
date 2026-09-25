#!/usr/bin/env python3
"""
Validates schedule.json before it can reach the lab machines.

Deliberately mirrors the rules in lib/Schedule.ps1 on the consuming side. Two
validators sound redundant, but they fail at different moments and that is the
point: this one fails a pull request, the PowerShell one protects a machine that
has already fetched something unexpected. A feed that only the machines reject
is a feed that has already reached them.

Standard library only, so it runs in CI and on a laptop with nothing installed.

    python3 validate.py            # validates ./schedule.json
    python3 validate.py path.json
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Zones lib/Schedule.ps1 can resolve on Windows PowerShell 5.1. That runtime's
# TimeZoneInfo knows only Windows ids, so the PowerShell side maps these IANA
# names across. An id outside this list validates here and then fails on every
# machine - so it is rejected here instead.
KNOWN_ZONES = {
    "America/Los_Angeles", "America/Vancouver", "America/Denver", "America/Edmonton",
    "America/Phoenix", "America/Chicago", "America/Winnipeg", "America/Mexico_City",
    "America/New_York", "America/Toronto", "America/Sao_Paulo",
    "Europe/London", "Europe/Dublin", "Europe/Lisbon", "Europe/Paris", "Europe/Madrid",
    "Europe/Berlin", "Europe/Amsterdam", "Europe/Zurich", "Europe/Rome", "Europe/Warsaw",
    "Europe/Athens", "Europe/Moscow",
    "Asia/Jerusalem", "Asia/Dubai", "Asia/Kolkata", "Asia/Calcutta", "Asia/Bangkok",
    "Asia/Singapore", "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Tokyo", "Asia/Seoul",
    "Australia/Perth", "Australia/Brisbane", "Australia/Sydney", "Australia/Melbourne",
    "Pacific/Auckland", "UTC", "Etc/UTC",
}

# Anything resembling a person, a room or a session title. The repository is
# public and the schedule is the same for every lab, so none of it belongs here.
BANNED_KEYS = {"room", "rooms", "name", "names", "title", "titles",
               "presenter", "presenters", "speaker", "speakers",
               "attendee", "attendees", "email", "emails", "machine", "machines"}


def check(path: Path):
    errors, warnings = [], []

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return [f"cannot read {path}: {e}"], []

    if raw.startswith("﻿"):
        errors.append("file starts with a UTF-8 BOM; save it as plain UTF-8")

    try:
        feed = json.loads(raw)
    except json.JSONDecodeError as e:
        return [f"not valid JSON: line {e.lineno} column {e.colno}: {e.msg}"], []

    if not isinstance(feed, dict):
        return ["top level must be a JSON object"], []

    if feed.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion must be {SCHEMA_VERSION}, found {feed.get('schemaVersion')!r}")

    if not isinstance(feed.get("scheduleVersion"), int):
        errors.append("scheduleVersion must be an integer, and should increase on every change")

    tz = feed.get("timezone")
    if not tz:
        errors.append("timezone is missing")
    elif tz not in KNOWN_ZONES:
        errors.append(
            f"timezone {tz!r} is not one the lab machines can resolve. "
            f"Add it to IanaToWindows in lib/Schedule.ps1 and to KNOWN_ZONES here, or pick another."
        )

    # --- slots ---
    slots = feed.get("dailyResets")
    if not isinstance(slots, list) or not slots:
        errors.append("dailyResets must be a non-empty list")
        slots = []
    if len(slots) > 24:
        errors.append(f"{len(slots)} resets in one day is implausible")

    seen, times = set(), []
    for i, s in enumerate(slots):
        if not isinstance(s, dict):
            errors.append(f"dailyResets[{i}] is not an object")
            continue
        sid = s.get("id")
        if not sid:
            errors.append(f"dailyResets[{i}] has no id")
        elif sid in seen:
            errors.append(f"duplicate slot id {sid!r}")
        else:
            seen.add(sid)
        t = s.get("time", "")
        if not TIME_RE.match(str(t)):
            errors.append(f"slot {sid!r}: time {t!r} must be HH:MM in 24-hour form")
        else:
            times.append((t, sid))

    # Two resets close together means the second fires while the first is still
    # running, or immediately after - almost always a typo.
    times.sort()
    for (t1, id1), (t2, id2) in zip(times, times[1:]):
        m1 = int(t1[:2]) * 60 + int(t1[3:])
        m2 = int(t2[:2]) * 60 + int(t2[3:])
        if m2 - m1 < 30:
            warnings.append(f"{id1} ({t1}) and {id2} ({t2}) are only {m2 - m1} minutes apart")

    # --- dates ---
    dates = feed.get("activeDates")
    if not isinstance(dates, list) or not dates:
        errors.append("activeDates must be a non-empty list, or the schedule never fires")
        dates = []
    today = dt.date.today()
    parsed = []
    for d in dates:
        if not DATE_RE.match(str(d)):
            errors.append(f"activeDates: {d!r} must be yyyy-MM-dd")
            continue
        try:
            parsed.append(dt.date.fromisoformat(d))
        except ValueError:
            errors.append(f"activeDates: {d!r} is not a real date")
    if parsed and all(p < today for p in parsed):
        warnings.append("every activeDate is in the past; this schedule will never fire")

    # --- guard ---
    g = feed.get("guard", {})
    if not isinstance(g, dict):
        errors.append("guard must be an object")
    else:
        for key, lo, hi in (("warnMinutes", 1, 60), ("postponeMinutes", 1, 120),
                            ("maxPostpones", 0, 10), ("idleMinutes", 1, 240)):
            if key in g:
                v = g[key]
                if not isinstance(v, int) or not (lo <= v <= hi):
                    errors.append(f"guard.{key} must be an integer between {lo} and {hi}, found {v!r}")
        if g.get("warnMinutes", 5) < 2:
            warnings.append("guard.warnMinutes under 2 gives a student almost no time to save work")

    # --- nothing identifying ---
    def scan(node, where=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.lower() in BANNED_KEYS:
                    errors.append(f"{where}{k}: this repository is public; do not publish names, "
                                  f"rooms, titles or machine identifiers")
                scan(v, f"{where}{k}.")
        elif isinstance(node, list):
            for item in node:
                scan(item, where)
    scan(feed)

    return errors, warnings


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "schedule.json")
    errors, warnings = check(path)

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error:   {e}")

    if errors:
        print(f"\n{path.name}: {len(errors)} error(s). Not safe to publish.")
        return 1
    print(f"\n{path.name}: valid{' with ' + str(len(warnings)) + ' warning(s)' if warnings else ''}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
