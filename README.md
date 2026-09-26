# Lab reset schedule

When the TechXchange lab machines reset themselves.

Every lab carries the same schedule, so the timing is identical across the room.
The machines poll this file on a timer, cache what they get, and act on the cache.

Published at **`github.com/itz-public/txc-lab-schedule`**. The machines read:

```
https://raw.githubusercontent.com/itz-public/txc-lab-schedule/main/schedule.json
```

## The only file that matters

[`schedule.json`](schedule.json) — times are local to the `timezone` field.

```json
{
  "schemaVersion": 2,
  "scheduleVersion": 3,
  "timezone": "America/New_York",
  "days": {
    "2026-10-26": [
      { "id": "pre-open", "time": "09:30", "label": "Before doors open" },
      { "id": "s1",       "time": "11:35", "label": "After session 1" }
    ],
    "2026-10-29": [
      { "id": "close",    "time": "12:35", "label": "End of day" }
    ]
  },
  "guard": { "warnMinutes": 5, "postponeMinutes": 5, "maxPostpones": 2, "idleMinutes": 10 },
  "scriptVersion": "1.0.0"
}
```

| Field | Meaning |
|---|---|
| `scheduleVersion` | Increase it on every change. Machines log when it moves. |
| `timezone` | Slot times are wall-clock in this zone. Must be one the machines can resolve — the validator checks. |
| `days` | Keyed by date. **A date not listed here never resets** - a machine left running after the event does nothing. |
| `days.<date>[]` | That day's resets. `id` must be unique *within the day*; `time` is 24-hour `HH:MM`. |
| `guard` | How long a student is warned, how long they can postpone, how often. `warnMinutes + postponeMinutes x maxPostpones` **must fit in the gap between sessions**, or a postponed reset lands in the next one. |
| `scriptVersion` | The reset script version that *should* be installed. Reported, never installed. |

## Why it is keyed by date

Each event day has its own session timetable, so there is no single daily pattern to share.
This file used to carry one list of times applied to every day, and three of its five resets
landed **mid-session** on three of the four days. Per-date slots are what make the feed able
to describe the actual event.

Set a day's resets a few minutes after each session ends, and leave enough room before the
next session for a warned, postponed reset to finish.

## Changing the schedule

1. Edit `schedule.json` and increase `scheduleVersion`.
2. Run `python3 validate.py` — it needs nothing installed.
3. Open a pull request. CI runs the same validator.
4. Merge. Machines pick it up within one poll cycle (about 15 minutes).

### Do not put anything identifying in this file

The repository is public. No names, no room numbers, no session titles, no machine
identifiers. The validator rejects fields that look like any of those, but it can only
catch the obvious cases — the judgement is yours.

## What the machines do with it

They **poll** this file and **cache** it. A failed fetch keeps the last good schedule, so
a network outage costs you schedule *changes*, not resets. Each machine also validates
independently and refuses anything implausible — a wrong timezone, malformed times, or a
feed that has suddenly lost most of its slots.

A reset never arrives unannounced. If someone is using the machine they get a countdown
and the option to postpone; if it has been idle a while it resets straight away. Every
decision is logged on the machine.

**`scriptVersion` never causes an install.** The machines compare it to what they have
and log the difference for an attendant. A public repository that could push running code
to event hardware would be a route onto every machine in the room, so it does not exist.

## Repository settings worth having

- Protect `main`: require a pull request and a passing `Validate schedule` check.
- Keep the history readable. `scheduleVersion` plus the commit log is the audit trail for
  "why did that room reset at 15:15".
