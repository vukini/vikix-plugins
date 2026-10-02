"""inbox sort — file the inbox's notes where they belong.

  inbox sort            a model suggests, for each note in the inbox, which
                        of your Org files (and which heading in it) it
                        belongs in, and whether it's a to-do; you see the
                        list and change what you like (or delete one); then the notes move
                        and, when you say so, the to-dos go to Todoist
  inbox sort --undo     the files as they were before the last sort (when
                        nothing has changed them since)

Where notes can go: every .org file beside the inbox (~/Dropbox/notes),
at its top or under one of its top headings. The first sort, with no file
but the inbox there, makes starter files: work.org, personal.org,
projects.org (a heading for each git project in ~/src) and someday.org.

Which model: the one Super+i uses (~/.config/vikix/ai: use=local, a model
on this laptop through Ollama; use=claude, Claude, and then the notes'
text goes to Anthropic, as it says before asking). Nothing moves until
you've said yes. Before it does, the files it changes are copied to
~/.local/state/vikix/inbox/sorts/.

To-dos to Todoist need its API token, kept as Vikix's other keys:
vikix ai key set todoist (Todoist: Settings, Integrations, Developer).
A to-do sent gets TODO in front of its title and a TODOIST property with
the task's link.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from typing import NoReturn

HOME = os.path.expanduser("~")
CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
STATE = os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local", "state")
SORTS = os.path.join(STATE, "vikix", "inbox", "sorts")
AI_CONF = os.path.join(CONFIG, "vikix", "ai")
SECRETS = os.path.join(CONFIG, "vikix", "secrets")
OLLAMA = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
OLLAMA = OLLAMA if OLLAMA.startswith("http") else f"http://{OLLAMA}"
ANTHROPIC = os.environ.get("VIKIX_ANTHROPIC_URL", "https://api.anthropic.com")
TODOIST = os.environ.get("VIKIX_TODOIST_URL", "https://api.todoist.com")
CLAUDE_DEFAULT = "claude-sonnet-5"     # as Super+i's (Vikix's bin/vikix-ask)
LOCAL_DEFAULT = "llama3.2:3b"
BODY = 600                             # characters of each note the model reads

def die(msg) -> NoReturn:
    sys.exit(f"inbox sort: {msg}")


def inbox_file():
    """As bin/inbox's: the settings' file =, or ~/Dropbox/notes/inbox.org."""
    path = read_conf(os.path.join(CONFIG, "vikix", "plugins", "inbox", "settings")).get("file") \
        or "~/Dropbox/notes/inbox.org"
    return os.path.abspath(os.path.expanduser(path))


# --- Org, as text ---------------------------------------------------------------------

HEADING = re.compile(r"^(\*+)\s")


def split_entries(text):
    """The text before the first heading, and each top-level heading with
    everything under it."""
    lines = text.splitlines(keepends=True)
    pre, entries, cur = [], [], None
    for line in lines:
        if line.startswith("* "):
            cur = [line]
            entries.append(cur)
        elif cur is None:
            pre.append(line)
        else:
            cur.append(line)
    return "".join(pre), ["".join(e) for e in entries]


def title_of(entry):
    first = entry.splitlines()[0]
    return re.sub(r"^\*+\s+(TODO\s+|DONE\s+)?", "", first).strip()


def body_of(entry):
    lines = entry.splitlines()[1:]
    out, drawer = [], False
    for line in lines:
        if line.strip() == ":PROPERTIES:":
            drawer = True
        elif drawer and line.strip() == ":END:":
            drawer = False
        elif not drawer:
            out.append(line)
    return "\n".join(out).strip()


def demote(entry, by):
    return "".join(("*" * by + line) if HEADING.match(line) else line
                   for line in entry.splitlines(keepends=True))


def as_todo(entry):
    first, _, rest = entry.partition("\n")
    if not re.match(r"^\*+\s+(TODO|DONE)\s", first):
        first = re.sub(r"^(\*+)\s+", r"\1 TODO ", first, count=1)
    return first + "\n" + rest


def put_property(entry, name, value):
    lines = entry.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == ":END:" and i > 0:
            lines.insert(i, f":{name}:  {value}\n")
            return "".join(lines)
        if i > 0 and not line.startswith(":"):
            break
    lines[1:1] = [":PROPERTIES:\n", f":{name}:  {value}\n", ":END:\n"]
    return "".join(lines)


def top_headings(text):
    return [title_of(line) for line in text.splitlines()
            if line.startswith("* ") and not re.match(r"^\*\s+COMMENT\b", line)
            and ":ARCHIVE:" not in line]


def insert(text, heading, entry):
    """TEXT with ENTRY at the end of the top heading titled HEADING (one
    level down), or at the end of the file when HEADING is None."""
    if not text.endswith("\n") and text:
        text += "\n"
    if heading is None:
        return text + entry
    entry = demote(entry, 1)
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines)
                  if line.startswith("* ") and title_of(line) == heading), None)
    if start is None:
        return text + f"* {heading}\n" + entry
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("* ")), len(lines))
    return "".join(lines[:end]) + entry + "".join(lines[end:])


# --- Where notes can go ---------------------------------------------------------------------

def starter_files(folder):
    """The first sort's files, when the inbox is alone in its folder."""
    projects = []
    src = os.path.join(HOME, "src")
    if os.path.isdir(src):
        for name in sorted(os.listdir(src)):
            if os.path.isdir(os.path.join(src, name, ".git")):   # a project, not a worktree of one
                projects.append(name)
    made = []
    for name, title, heads in (("work.org", "Work", []), ("personal.org", "Personal", []),
                               ("projects.org", "Projects", projects), ("someday.org", "Someday", [])):
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(f"#+title: {title}\n\n" + "".join(f"* {h}\n" for h in heads))
            made.append(name)
    return made


def destinations(folder, inbox):
    """[(file, heading or None)], every .org file beside the inbox and its top headings."""
    out = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not name.endswith(".org") or name.startswith(".") or not os.path.isfile(path) \
                or os.path.samefile(path, inbox):
            continue
        out.append((name, None))
        with open(path) as f:
            out += [(name, h) for h in top_headings(f.read())]
    return out


def label(dest):
    if dest is None:
        return "stays in the inbox"
    name, heading = dest
    return name if heading is None else f"{name} / {heading}"


# --- The model ------------------------------------------------------------------------------

def read_conf(path):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return out


def secret(name):
    """A key from the session's environment, or Vikix's secrets folder. Never printed."""
    value = os.environ.get(name, "")
    if not value:
        try:
            with open(os.path.join(SECRETS, name)) as f:
                value = f.read().strip()
        except OSError:
            value = ""
    return value


def who_sorts():
    conf = read_conf(AI_CONF)
    use = conf.get("use") or "local"
    model = conf.get("model", "")
    if use == "claude":
        return "claude", (model if model.startswith("claude") else CLAUDE_DEFAULT)
    return "local", (model if model and not model.startswith("claude") else LOCAL_DEFAULT)


SYSTEM = """You sort notes from the user's Org inbox into their Org files.
You are given the places a note can go, numbered (0 means it stays in the inbox), and the notes, numbered.
For each note choose the one place it fits best; 0 when none fits or the note is unclear.
Also say whether the note is something the user has to do (a task: call, buy, send, fix, book ...): todo true or false.
Answer with JSON only, no other text: {"notes": [{"note": 1, "place": 3, "todo": false}, ...]} with one item per note."""

SCHEMA = {"type": "object", "properties": {"notes": {"type": "array", "items": {
    "type": "object", "properties": {"note": {"type": "integer"}, "place": {"type": "integer"},
                                     "todo": {"type": "boolean"}},
    "required": ["note", "place", "todo"]}}}, "required": ["notes"]}


def prompt(dests, entries):
    places = ["0. stays in the inbox"] + [f"{i}. {label(d)}" for i, d in enumerate(dests, 1)]
    notes = []
    for i, e in enumerate(entries, 1):
        body = body_of(e)[:BODY]
        notes.append(f"{i}. {title_of(e)}" + (f"\n{body}" if body else ""))
    return "Places:\n" + "\n".join(places) + "\n\nNotes:\n" + "\n\n".join(notes)


def post(url, payload, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ask_local(model, text):
    try:
        reply = post(OLLAMA + "/api/chat", {"model": model, "stream": False, "format": SCHEMA,
                                            "options": {"temperature": 0},
                                            "messages": [{"role": "system", "content": SYSTEM},
                                                         {"role": "user", "content": text}]}, {}, 600)
    except urllib.error.URLError:
        die("the local model isn't answering: is Ollama running? (vikix ai status)")
    return reply.get("message", {}).get("content", "")


def ask_claude(model, text):
    key = secret("ANTHROPIC_API_KEY")
    if not key:
        die("no Anthropic key: vikix ai key set anthropic (or vikix ai use local)")
    try:
        reply = post(ANTHROPIC + "/v1/messages", {"model": model, "max_tokens": 4000, "system": SYSTEM,
                                                   "messages": [{"role": "user", "content": text}]},
                     {"x-api-key": key, "anthropic-version": "2023-06-01"}, 120)
    except urllib.error.HTTPError as e:
        die("the key was refused: vikix ai key set anthropic" if e.code == 401
            else f"Anthropic said {e.code}; try again in a minute")
    except urllib.error.URLError:
        die("couldn't reach Anthropic: is the network up?")
    return "".join(b.get("text", "") for b in reply.get("content", []) if b.get("type") == "text")


def suggestions(answer, n, places):
    """[(place index or 0, todo)] for each note, from the model's JSON; 0 for anything unclear."""
    out = [(0, False)] * n
    m = re.search(r"\{.*\}", answer, re.S)
    try:
        items = json.loads(m.group(0))["notes"] if m else []
    except (ValueError, KeyError, TypeError):
        items = []
    for it in items if isinstance(items, list) else []:
        try:
            i, p = int(it["note"]), int(it["place"])
        except (KeyError, TypeError, ValueError):
            continue
        if 1 <= i <= n:
            out[i - 1] = (p if 0 <= p <= places else 0, bool(it.get("todo")))
    return out


# --- Todoist --------------------------------------------------------------------------------

def todoist_task(token, entry):
    task = post(TODOIST + "/api/v1/tasks", {"content": title_of(entry), "description": body_of(entry)[:2000]},
                {"authorization": f"Bearer {token}"}, 30)
    return task.get("url") or f"https://app.todoist.com/app/task/{task['id']}"


# --- Undo -----------------------------------------------------------------------------------

def digest(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def keep_copies(paths):
    # To the microsecond: two sorts in one second (a script, a test) each keep their own.
    folder = os.path.join(SORTS, datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    os.makedirs(folder, mode=0o700)
    before = {}
    for i, p in enumerate(paths):
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(folder, str(i)))
            before[p] = str(i)
        else:
            before[p] = None
    return folder, before


def write(path, text):
    tmp = path + ".inbox-sort"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def undo():
    try:
        last = sorted(d for d in os.listdir(SORTS) if not d.endswith("-undone"))[-1]
    except (FileNotFoundError, IndexError):
        die("no sort to undo")
    folder = os.path.join(SORTS, last)
    with open(os.path.join(folder, "sort.json")) as f:
        rec = json.load(f)
    changed = [p for p, h in rec["after"].items() if digest(p) != h]
    if changed:
        die("changed since the sort, so not put back: " + ", ".join(os.path.basename(p) for p in changed)
            + f"\n  the files from before it are in {folder} (sort.json says which is which)")
    for p, copy in rec["before"].items():
        if copy is None:
            os.remove(p)
        else:
            shutil.copy2(os.path.join(folder, copy), p)
    os.rename(folder, folder + "-undone")
    print(f"Put back as before the sort of {last}: " + ", ".join(os.path.basename(p) for p in rec["before"]))
    if rec.get("todoist"):
        print(f"The {rec['todoist']} task(s) sent to Todoist are still there: delete them there if you like.")


# --- The sort -------------------------------------------------------------------------------

def show(entries, plan, dests, deleted=()):
    width = min(44, max(len(title_of(e)) for e in entries))
    for i, (e, (p, todo)) in enumerate(zip(entries, plan), 1):
        t = title_of(e)
        t = t if len(t) <= width else t[:width - 1] + "…"
        if i - 1 in deleted:
            print(f"  {i:>2}  {t:<{width}}  ✗ deleted")
        else:
            print(f"  {i:>2}  {t:<{width}}  → {label(dests[p - 1] if p else None)}{'   to-do' if todo else ''}")


def choose_place(dests, current):
    print("\n   0  stays in the inbox")
    for i, d in enumerate(dests, 1):
        print(f"  {i:>2}  {label(d)}")
    answer = input(f"Where? (Enter keeps {current}) ").strip()
    if answer.isdigit() and 0 <= int(answer) <= len(dests):
        return int(answer)
    return None


def main(argv):
    if argv[:1] == ["--undo"]:
        return undo()
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__.strip())
        return
    inbox = inbox_file()
    if not os.path.exists(inbox):
        die(f"no inbox yet ({inbox}): Super+Alt+i takes a note")
    folder = os.path.dirname(inbox)
    with open(inbox) as f:
        text = f.read()
    pre, entries = split_entries(text)
    if not entries:
        print("The inbox is empty: nothing to sort.")
        return
    if not destinations(folder, inbox):
        made = starter_files(folder)
        print(f"Made starter files in {folder}: {', '.join(made)}. Rename, add or remove them as you like:\n"
              "the sort offers whatever .org files are there, and their top headings.\n")
    dests = destinations(folder, inbox)
    if not dests:
        die(f"nowhere to sort to: put an .org file beside the inbox, in {folder}")

    kind, model = who_sorts()
    where = "on this laptop" if kind == "local" else "Claude: the notes' titles and text go to Anthropic"
    print(f"Asking {model} ({where}) where {len(entries)} note(s) belong…", flush=True)
    answer = (ask_claude if kind == "claude" else ask_local)(model, prompt(dests, entries))
    plan = suggestions(answer, len(entries), len(dests))

    deleted = set()
    while True:
        print()
        show(entries, plan, dests, deleted)
        print("\nEnter: do it    N: change where note N goes    t N: to-do or not    d N: delete or keep\n"
              "q: stop, nothing moves")
        try:
            a = input("> ").strip().lower()
        except EOFError:
            a = "q"
        if a == "":
            break
        if a == "q":
            print("Nothing moved.")
            return
        m = re.fullmatch(r"d\s*(\d+)", a)
        if m and 1 <= int(m.group(1)) <= len(entries):
            deleted ^= {int(m.group(1)) - 1}       # d again keeps it
            continue
        m = re.fullmatch(r"t\s*(\d+)", a)
        if m and 1 <= int(m.group(1)) <= len(entries):
            i = int(m.group(1)) - 1
            plan[i] = (plan[i][0], not plan[i][1])
        elif a.isdigit() and 1 <= int(a) <= len(entries):
            i = int(a) - 1
            p = choose_place(dests, label(dests[plan[i][0] - 1] if plan[i][0] else None))
            if p is not None:
                plan[i] = (p, plan[i][1])
                deleted.discard(i)

    todos = [i for i, (_, todo) in enumerate(plan) if todo and i not in deleted]
    links = {}
    if todos:
        token = secret("TODOIST_API_KEY")
        if not token:
            print(f"\n({len(todos)} to-do(s) marked TODO. To send them to Todoist too: vikix ai key set todoist)")
        else:
            try:
                yes = input(f"\nSend the {len(todos)} to-do(s) to Todoist too? [Y/n] ").strip().lower() in ("", "y", "yes")
            except EOFError:
                yes = False
            if yes:
                for i in todos:
                    try:
                        links[i] = todoist_task(token, entries[i])
                    except (urllib.error.URLError, KeyError, ValueError) as e:
                        print(f"  Todoist didn't take “{title_of(entries[i])}”: {getattr(e, 'code', '') or e}")
                if links:
                    print(f"  {len(links)} sent to Todoist.")

    # The files after: each note in its place, the inbox without the notes that left.
    texts, stay = {}, []
    for i, (e, (p, todo)) in enumerate(zip(entries, plan)):
        if i in deleted:
            continue
        if todo:
            e = as_todo(e)
        if i in links:
            e = put_property(e, "TODOIST", links[i])
        if not p:
            stay.append(e)
            continue
        name, heading = dests[p - 1]
        path = os.path.join(folder, name)
        if path not in texts:
            with open(path) as f:
                texts[path] = f.read()
        texts[path] = insert(texts[path], heading, e)
    texts[inbox] = pre + "".join(stay)
    if texts[inbox] == text and len(texts) == 1:
        print("Nothing to move.")
        return
    keep, before = keep_copies(list(texts))
    for path, t in texts.items():
        write(path, t)
    with open(os.path.join(keep, "sort.json"), "w") as f:
        json.dump({"before": before, "after": {p: digest(p) for p in texts}, "todoist": len(links)}, f, indent=1)
    moved = sum(1 for i, (p, _) in enumerate(plan) if p and i not in deleted)
    gone = f", deleted {len(deleted)}" if deleted else ""
    print(f"\nMoved {moved} note(s){gone}; {len(stay)} left in the inbox. (inbox sort --undo puts it all back.)")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print("\nStopped: nothing moved.")
