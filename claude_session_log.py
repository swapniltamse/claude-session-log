#!/usr/bin/env python3
"""
claude-session-log: a day-by-day log of your Claude Code sessions.

Reads the session files Claude Code keeps in ~/.claude/projects/ and writes a
static HTML page (plus an optional Markdown note) that answers "which session
was I in last Tuesday, and how do I get back into it?"

Each session is listed under every day you typed into it, with the first and
last thing you asked that day and a copyable resume command that cd's into the
folder the session was started from (claude --resume only finds a session from
its own folder).

Dates come from the timestamp on each prompt, not the file's modified time,
which backups and sync tools bump.

Nothing leaves your machine. No dependencies beyond Python 3.8+.

Usage:
    python claude_session_log.py
    python claude_session_log.py --out ~/Documents/sessions --markdown
    python claude_session_log.py --shell bash --skip-prefix "Run the nightly"
"""

import argparse
import datetime
import glob
import html
import json
import os
import shlex
import sys

# User text that is harness noise, not something you typed.
NOISE_PREFIXES = (
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<command-name>",
    "<command-message>",
    "<system-reminder>",
    "<task-notification>",
    "Caveat:",
    "Base directory for this skill:",
    "[Request interrupted",
)

# Sessions whose first prompt starts like this were started by a tool, not you.
DEFAULT_SKIP_PREFIXES = ("Review this change for security vulnerabilities",)


def default_projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "projects")


def parse_args():
    p = argparse.ArgumentParser(description="Day-by-day log of Claude Code sessions.")
    p.add_argument("--projects-dir", default=default_projects_dir(),
                   help="where Claude Code keeps sessions (default: ~/.claude/projects)")
    p.add_argument("--out", default=os.path.expanduser("~/claude-session-log"),
                   help="output folder (default: ~/claude-session-log)")
    p.add_argument("--markdown", action="store_true",
                   help="also write sessions.md (works as an Obsidian note)")
    p.add_argument("--shell", choices=("auto", "powershell", "bash"), default="auto",
                   help="syntax for the resume command (default: powershell on Windows, else bash)")
    p.add_argument("--day-start-hour", type=int, default=6,
                   help="hour a day starts, so late-night work counts toward the evening (default: 6)")
    p.add_argument("--skip-prefix", action="append", default=[],
                   help="skip sessions whose first prompt starts with this text (repeatable)")
    p.add_argument("--open-days", type=int, default=7,
                   help="how many recent days start expanded in the HTML (default: 7)")
    return p.parse_args()


def prompt_text(o):
    """Return the human-typed text of a user entry, or None for tool results and noise."""
    if o.get("isMeta"):
        return None
    c = o.get("message", {}).get("content")
    if isinstance(c, list):
        if any(isinstance(part, dict) and part.get("type") == "tool_result" for part in c):
            return None
        c = " ".join(part.get("text", "") for part in c if isinstance(part, dict))
    if not isinstance(c, str):
        return None
    t = c.strip()
    if not t or t.startswith(NOISE_PREFIXES):
        return None
    return t


def clean(text, limit):
    t = text.strip()
    if t.startswith("<pasted_content"):
        t = "[pasted text] " + t.split(">", 1)[-1]
    t = " ".join(t.split())
    if len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return t


def scan(path, skip_prefixes):
    title = custom = cwd = None
    prompts = []  # (local naive datetime, text)
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            # Cheap prefilter. Session files can be tens of MB.
            if ('"type":"user"' not in line and '"ai-title"' not in line
                    and '"custom-title"' not in line and '"cwd"' not in line):
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if not cwd and o.get("cwd"):
                cwd = o["cwd"]
            typ = o.get("type")
            if typ == "custom-title" and o.get("customTitle"):
                custom = o["customTitle"]  # set with /rename
            elif typ == "ai-title" and o.get("aiTitle"):
                title = o["aiTitle"]
            elif typ == "user":
                t = prompt_text(o)
                ts = o.get("timestamp")
                if not t or not ts:
                    continue
                try:
                    utc = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                prompts.append((utc.astimezone().replace(tzinfo=None), t))
    if prompts and prompts[0][1].startswith(skip_prefixes):
        prompts = []
    return custom or title, cwd, prompts


def resume_command(shell, cwd, sid):
    if shell == "powershell":
        return f"cd \"{cwd}\"; claude --resume {sid}"
    return f"cd {shlex.quote(cwd)} && claude --resume {sid}"


def collect(args):
    skip = tuple(DEFAULT_SKIP_PREFIXES) + tuple(args.skip_prefix)
    shift = datetime.timedelta(hours=args.day_start_hour)
    by_day = {}
    sessions = 0
    for f in glob.glob(os.path.join(args.projects_dir, "*", "*.jsonl")):
        try:
            title, cwd, prompts = scan(f, skip)
        except OSError:
            continue  # file rotated mid-scan
        if not prompts:
            continue
        sessions += 1
        sid = os.path.splitext(os.path.basename(f))[0]
        days = {}
        for ts, t in prompts:
            days.setdefault((ts - shift).date(), []).append((ts, t))
        for d, items in days.items():
            items.sort()
            by_day.setdefault(d, []).append({
                "sid": sid,
                "title": title,
                "cwd": cwd or os.path.expanduser("~"),
                "start": items[0][0],
                "end": items[-1][0],
                "n": len(items),
                "first": items[0][1],
                "last": items[-1][1],
            })
    for entries in by_day.values():
        entries.sort(key=lambda e: e["start"])
    return by_day, sessions


def span(e):
    s = e["start"].strftime("%H:%M")
    if e["end"] - e["start"] >= datetime.timedelta(minutes=5):
        s += "–" + e["end"].strftime("%H:%M")
    return s


def day_label(d):
    return f"{d.strftime('%a %b')} {d.day}, {d.year}"


def render_markdown(by_day, sessions, shell, day_start):
    lines = [
        "---",
        "tags: [claude-sessions]",
        f"generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "---",
        "",
        "# Claude Code Session Log",
        "",
        f"{sessions} sessions, listed under every day you typed into them, newest day first. "
        f"A day starts at {day_start:02d}:00. Paste a resume command into your terminal to reopen a session.",
        "",
    ]
    for d in sorted(by_day, reverse=True):
        lines += [f"## {day_label(d)}", "",
                  "| Time | Session | What you asked that day | Prompts | Resume |",
                  "|------|---------|-------------------------|---------|--------|"]
        for e in by_day[d]:
            title = (e["title"] or "*untitled*").replace("|", "\\|")
            asked = clean(e["first"], 90).replace("|", "\\|")
            if e["n"] > 1 and e["last"] != e["first"]:
                asked += "<br>… last: " + clean(e["last"], 90).replace("|", "\\|")
            cmd = resume_command(shell, e["cwd"], e["sid"])
            lines.append(f"| {span(e)} | {title} | {asked} | {e['n']} | `{cmd}` |")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_html(by_day, sessions, shell, day_start, open_days):
    esc = html.escape
    sections = []
    for i, d in enumerate(sorted(by_day, reverse=True)):
        rows = []
        for e in by_day[d]:
            cmd = resume_command(shell, e["cwd"], e["sid"])
            last = ""
            if e["n"] > 1 and e["last"] != e["first"]:
                last = f'<div class="last">Last: {esc(clean(e["last"], 160))}</div>'
            folder = os.path.basename(e["cwd"].rstrip("\\/")) or e["cwd"]
            plural = "s" if e["n"] != 1 else ""
            rows.append(
                f'<li class="row"><div class="time">{span(e)}</div><div class="body">'
                f'<div class="title">{esc(e["title"] or "Untitled")}'
                f' <span class="meta">{e["n"]} prompt{plural} · {esc(folder)}</span></div>'
                f'<div class="first">{esc(clean(e["first"], 160))}</div>{last}'
                f'<div class="cmd"><code>{esc(cmd)}</code>'
                f'<button type="button" data-cmd="{esc(cmd, quote=True)}">Copy</button></div>'
                f"</div></li>"
            )
        n = len(by_day[d])
        sections.append(
            f'<details class="day"{" open" if i < open_days else ""}>'
            f'<summary><span>{day_label(d)}</span>'
            f'<span class="count">{n} session{"s" if n != 1 else ""}</span></summary>'
            f'<ul>{"".join(rows)}</ul></details>'
        )
    return HTML_TEMPLATE.format(
        generated=datetime.datetime.now().strftime("%a %b %d, %Y %H:%M"),
        sessions=sessions,
        days=len(by_day),
        day_start=f"{day_start:02d}:00",
        terminal="PowerShell" if shell == "powershell" else "your terminal",
        sections="\n".join(sections),
    )


HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Session Log</title>
<style>
:root {{ --bg:#f7f6f3; --card:#fff; --ink:#1d1d1f; --muted:#6b6b70; --line:#e3e1dc; --accent:#b4532a; --code:#f1efea; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161616; --card:#1f1f1f; --ink:#ececec; --muted:#9a9a9f; --line:#333; --accent:#e08a5f; --code:#2a2a2a; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width:900px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ font-size:24px; margin:0 0 4px; }}
.sub {{ color:var(--muted); margin:0 0 16px; font-size:14px; }}
#q {{ width:100%; padding:10px 12px; font:inherit; border:1px solid var(--line); border-radius:8px; background:var(--card); color:var(--ink); margin-bottom:16px; }}
.day {{ background:var(--card); border:1px solid var(--line); border-radius:10px; margin-bottom:10px; }}
.day summary {{ display:flex; justify-content:space-between; padding:12px 16px; cursor:pointer; font-weight:600; }}
.count {{ color:var(--muted); font-weight:400; font-size:13px; }}
ul {{ list-style:none; margin:0; padding:0 16px 8px; }}
.row {{ display:flex; gap:14px; padding:12px 0; border-top:1px solid var(--line); }}
.time {{ flex:0 0 92px; color:var(--muted); font-variant-numeric:tabular-nums; font-size:13px; padding-top:2px; }}
.body {{ flex:1; min-width:0; }}
.title {{ font-weight:600; }}
.meta {{ color:var(--muted); font-weight:400; font-size:12px; margin-left:6px; }}
.first, .last {{ color:var(--muted); font-size:14px; overflow-wrap:anywhere; }}
.last {{ font-style:italic; }}
.cmd {{ display:flex; gap:8px; align-items:center; margin-top:6px; }}
.cmd code {{ flex:1; min-width:0; background:var(--code); padding:5px 8px; border-radius:6px; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.cmd button {{ flex:0 0 auto; font:inherit; font-size:13px; padding:5px 12px; border-radius:6px; border:1px solid var(--accent); background:transparent; color:var(--accent); cursor:pointer; }}
.cmd button.done {{ background:var(--accent); color:var(--card); }}
.hidden {{ display:none; }}
@media (max-width:560px) {{ .row {{ flex-direction:column; gap:2px; }} .time {{ flex:none; }} }}
</style></head>
<body><main>
<h1>Claude Session Log</h1>
<p class="sub">{sessions} sessions across {days} days, newest first. A day starts at {day_start}. Generated {generated}. Copy a command, paste it into {terminal}, press Enter.</p>
<input id="q" type="search" placeholder="Search titles, prompts, folders…" autocomplete="off">
{sections}
</main>
<script>
document.addEventListener('click', async (ev) => {{
  const b = ev.target.closest('button[data-cmd]');
  if (!b) return;
  const text = b.dataset.cmd;
  try {{ await navigator.clipboard.writeText(text); }}
  catch (e) {{
    const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t);
    t.select(); document.execCommand('copy'); t.remove();
  }}
  b.textContent = 'Copied'; b.classList.add('done');
  setTimeout(() => {{ b.textContent = 'Copy'; b.classList.remove('done'); }}, 1500);
}});
const q = document.getElementById('q');
q.addEventListener('input', () => {{
  const term = q.value.trim().toLowerCase();
  document.querySelectorAll('.day').forEach(day => {{
    let any = false;
    day.querySelectorAll('.row').forEach(r => {{
      const hit = !term || r.textContent.toLowerCase().includes(term);
      r.classList.toggle('hidden', !hit); if (hit) any = true;
    }});
    day.classList.toggle('hidden', !any);
    if (term && any) day.open = true;
  }});
}});
</script>
</body></html>
"""


def main():
    args = parse_args()
    shell = args.shell
    if shell == "auto":
        shell = "powershell" if sys.platform == "win32" else "bash"
    if not os.path.isdir(args.projects_dir):
        sys.exit(f"No Claude Code sessions found at {args.projects_dir}")

    by_day, sessions = collect(args)
    os.makedirs(args.out, exist_ok=True)

    html_path = os.path.join(args.out, "index.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(by_day, sessions, shell, args.day_start_hour, args.open_days))
    print(f"Wrote {sessions} sessions across {len(by_day)} days to {html_path}")

    if args.markdown:
        md_path = os.path.join(args.out, "sessions.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(by_day, sessions, shell, args.day_start_hour))
        print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()
