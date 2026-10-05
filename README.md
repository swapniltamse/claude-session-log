# claude-session-log

Which Claude Code session was I in last Tuesday, and how do I get back into it?

`/resume` shows a list of sessions for the folder you're in. That's fine for yesterday. It's not much help two weeks later when you remember the day but not the folder, the title, or the session ID.

This script reads the session files Claude Code already keeps on your machine and writes one static HTML page, organized by day. Every session shows up under each day you typed into it, with what you asked first and last that day and a resume command you can copy.

```
Tue Mar 3, 2026                                         3 sessions
  14:10–15:42  fix-login-redirect   6 prompts · my-app
               the login page loops back to itself after signup
               Last: add a test for the expired token case
               cd "C:\Users\me\code\my-app"; claude --resume 1a2b3c4d-...      [Copy]
```

## Run it

Python 3.8 or newer. No packages to install.

```
python claude_session_log.py
```

Then open `~/claude-session-log/index.html` in a browser. Bookmark it, or put a shortcut on your desktop.

To keep it current, run it on a schedule (cron, launchd, or Windows Task Scheduler). On a few hundred sessions it takes a minute or two.

## Options

| Flag | What it does |
|------|--------------|
| `--out DIR` | Output folder. Default `~/claude-session-log` |
| `--markdown` | Also write `sessions.md`. Point `--out` at an Obsidian vault folder and it becomes a note |
| `--shell powershell\|bash` | Resume command syntax. Default is PowerShell on Windows, bash everywhere else |
| `--day-start-hour N` | When a day starts. Default 6, so 1 AM work counts toward the night before |
| `--skip-prefix TEXT` | Hide sessions whose first prompt starts with TEXT, for sessions your own scripts start. Repeatable |
| `--projects-dir DIR` | Where sessions live. Default `~/.claude/projects`, or `$CLAUDE_CONFIG_DIR/projects` |
| `--open-days N` | How many recent days start expanded. Default 7 |

## Why the resume command includes `cd`

`claude --resume <id>` only finds a session when you run it from the folder the session started in. Each command changes into that folder first, so it works from anywhere.

## How dates are worked out

From the timestamp on each prompt you sent, not the file's modified time. Backup and sync tools touch session files, so weeks-old sessions can look like they're from today if you go by modified time.

## What's on the page

- The name you gave the session with `/rename`, or Claude's auto title
- First and last prompt that day, prompt count, the folder
- Search across titles, prompts and folders
- Sessions started by Claude Code's automated security review are left out

## Use it as a Claude Code skill

Copy `skill/SKILL.md` to `~/.claude/skills/session-log/SKILL.md` and set the script path inside it. Then `/session-log` refreshes the page, and you can ask things like "which session was I working on the API refactor in?"

## Privacy

The page contains your prompts. It's written to your machine and nothing is sent anywhere. Don't commit the output folder or publish the page. The `.gitignore` here excludes the default output files in case you run it inside the repo.

## License

MIT
