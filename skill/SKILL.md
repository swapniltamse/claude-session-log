---
name: session-log
description: Refresh a day-by-day log of Claude Code sessions, or find a past session and give the command to resume it. Use when the user says "/session-log", "refresh my session log", "which session was I in last Tuesday", "find the session where I worked on X", or wants to get back to work from days or weeks ago.
---

# Session Log

Builds a static HTML page (and optionally Markdown) listing every Claude Code
session under each day the user typed into it, with a copyable resume command.

## Step 1: Run the script

```bash
python /path/to/claude_session_log.py --markdown
```

Set the path above to where you cloned the repo. Output goes to
`~/claude-session-log/` (`index.html` and `sessions.md`) unless the user
passes `--out`.

## Step 2: Answer

- If the user only asked to refresh, report the count line the script prints
  and the path to `index.html`.
- If the user is looking for a specific session, read `sessions.md`, find the
  matching rows by day, title or prompt text, and give them the resume command
  from the Resume column exactly as written.

Never paste the log's contents anywhere outside the user's machine. It
contains their prompts.
