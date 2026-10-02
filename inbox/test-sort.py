"""inbox's sort and page addresses, against stand-ins for Ollama, Claude's
API, Todoist and Nyxt's Swank on 127.0.0.1 (test runs it; nothing leaves
the machine). Run in a made-up home (HOME, XDG_* set by test)."""
import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "lib"))
import pageaddress  # noqa: E402

HOME = os.environ["HOME"]
fail = 0


def ok(cond, what):
    global fail
    if not cond:
        print("FAIL:", what)
        fail = 1


seen = []           # what the stand-ins were asked
answer = {}         # what the model stand-in says


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        seen.append((self.path, dict(self.headers), body))
        if self.path == "/api/chat":
            out = {"message": {"content": json.dumps(answer)}}
        elif self.path == "/v1/messages":
            out = {"content": [{"type": "text", "text": "Here:\n" + json.dumps(answer)}]}
        elif self.path == "/api/v1/tasks":
            out = {"id": "6X7", "content": body["content"]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(data)


server = HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}"
env = dict(os.environ, OLLAMA_HOST=url, VIKIX_ANTHROPIC_URL=url, VIKIX_TODOIST_URL=url)
env.pop("ANTHROPIC_API_KEY", None)
env.pop("TODOIST_API_KEY", None)
notes = os.path.join(HOME, "notes")
inbox = os.path.join(notes, "inbox.org")
conf = os.path.join(os.environ["XDG_CONFIG_HOME"], "vikix")


def sort(keys="", *args, **extra):
    return subprocess.run([os.path.join(here, "bin", "inbox"), "sort", *args], input=keys, text=True,
                          capture_output=True, env=dict(env, **extra), timeout=60)


def read(name):
    with open(os.path.join(notes, name)) as f:
        return f.read()


os.makedirs(notes, exist_ok=True)
for p in ("alpha", "vikix"):
    os.makedirs(os.path.join(HOME, "src", p, ".git"))
os.makedirs(os.path.join(HOME, "src", "vikix-wt"))
open(os.path.join(HOME, "src", "vikix-wt", ".git"), "w").write("gitdir: x\n")   # a worktree: not a project
three = ("#+title: Inbox\n\n* Call the bank\n:PROPERTIES:\n:CREATED:  [2026-10-02 Fri 21:00]\n:END:\nabout the card\n"
         "* Vikix idea: themes\n** a sub point\n* random\n")
open(inbox, "w").write(three)
os.makedirs(conf, exist_ok=True)
open(os.path.join(conf, "ai"), "w").write("use=local\nmodel=\n")

# Places, in order: 1 personal.org, 2 projects.org, 3 projects.org / alpha,
# 4 projects.org / vikix, 5 someday.org, 6 work.org.
answer = {"notes": [{"note": 1, "place": 1, "todo": True}, {"note": 2, "place": 4, "todo": False},
                    {"note": 3, "place": 0, "todo": False}]}
r = sort("\n")
ok(r.returncode == 0, f"sort: {r.stdout} {r.stderr}")
ok("Made starter files" in r.stdout, "the first sort makes starter files")
ok(read("projects.org") .startswith("#+title: Projects\n\n* alpha\n"), "projects.org: a heading a project")
ok("vikix-wt" not in read("projects.org"), "a worktree isn't a project")
chat = [s for s in seen if s[0] == "/api/chat"][-1][2]
ok(chat["model"] == "llama3.2:3b", "use=local: the local model")
ok("4. projects.org / vikix" in chat["messages"][1]["content"], "the model is given the places, numbered")
ok("on this laptop" in r.stdout, "it says where the notes go")
ok("* TODO Call the bank\n" in read("personal.org"), "a to-do gets TODO")
ok("vikix ai key set todoist" in r.stdout, "without a Todoist token: how to add one")
ok("* vikix\n** Vikix idea: themes\n*** a sub point\n" in read("projects.org"), "under a heading, one level down")
ok(read("inbox.org") == "#+title: Inbox\n\n* random\n", "the inbox keeps only what stays")

# Undo.
r = sort("", "--undo")
ok(read("inbox.org") == three, f"--undo puts the inbox back: {r.stdout} {r.stderr}")
ok("Call the bank" not in read("personal.org"), "--undo puts the others back")
r = sort("", "--undo")
ok(r.returncode != 0 and "no sort to undo" in r.stderr, "a second --undo has nothing to undo")

# Changing the suggestions: note 3 to work.org, and a to-do; q stops with nothing moved.
r = sort("q\n")
ok(read("inbox.org") == three and "Nothing moved" in r.stdout, "q moves nothing")
r = sort("3\n6\nt 3\n\n")
ok("* TODO random\n" in read("work.org"), "a note moved by hand, made a to-do by hand")

# d N deletes a note (d again keeps it); --undo brings it back.
open(inbox, "w").write(three)
answer = {"notes": [{"note": 1, "place": 1, "todo": True}, {"note": 2, "place": 0, "todo": False},
                    {"note": 3, "place": 0, "todo": False}]}
before_personal = read("personal.org")
r = sort("d 1\nd 3\nd 3\n\n")
ok("✗ deleted" in r.stdout and "deleted 1" in r.stdout, f"d N shows and counts a deletion: {r.stdout}")
ok("Call the bank" not in read("inbox.org") and read("personal.org") == before_personal, "a deleted note goes nowhere")
ok("* random\n" in read("inbox.org") and "* Vikix idea: themes\n" in read("inbox.org"), "d twice keeps it")
ok("vikix ai key set todoist" not in r.stdout, "a deleted to-do isn't a to-do")
sort("", "--undo")
ok(read("inbox.org") == three, "--undo brings a deleted note back")
r = sort("3\n6\nt 3\n\n")      # again, for the next check

# --undo refuses when a file changed since.
with open(inbox, "a") as f:
    f.write("* written later\n")
r = sort("", "--undo")
ok(r.returncode != 0 and "changed since the sort" in r.stderr, f"--undo leaves a file changed since alone: {r.stdout} {r.stderr}")

# Claude, its key from the secrets folder; Todoist's token from the environment.
open(inbox, "w").write("#+title: Inbox\n\n* Book the dentist\n")
open(os.path.join(conf, "ai"), "w").write("use=claude\nmodel=\n")
os.makedirs(os.path.join(conf, "secrets"), exist_ok=True)
open(os.path.join(conf, "secrets", "ANTHROPIC_API_KEY"), "w").write("sk-ant-test\n")
answer = {"notes": [{"note": 1, "place": 1, "todo": True}]}
r = sort("\ny\n", TODOIST_API_KEY="todo-token")
msg = [s for s in seen if s[0] == "/v1/messages"][-1]
ok(msg[2]["model"] == "claude-sonnet-5" and msg[1].get("X-Api-Key") == "sk-ant-test", "use=claude: Claude, with the key")
ok("go to Anthropic" in r.stdout, "it says the notes go to Anthropic")
ok("sk-ant-test" not in r.stdout + r.stderr and "todo-token" not in r.stdout + r.stderr, "keys never printed")
task = [s for s in seen if s[0] == "/api/v1/tasks"][-1]
ok(task[2]["content"] == "Book the dentist" and task[1].get("Authorization") == "Bearer todo-token", "the to-do sent to Todoist")
ok(":TODOIST:  https://app.todoist.com/app/task/6X7" in read("personal.org"), "the task's link kept with the note")

# A model answering nonsense: everything stays, nothing breaks.
open(inbox, "w").write("#+title: Inbox\n\n* Odd one\n")
answer = {"notes": "no"}
r = sort("\n")
ok(read("inbox.org") == "#+title: Inbox\n\n* Odd one\n" and "Nothing to move" in r.stdout, "a bad answer: it stays")

# Page addresses: LZ4 (a match too), Firefox's session file, Nyxt's Swank.
ok(pageaddress.lz4_block(bytes([0x35]) + b"abc" + bytes([3, 0, 0x10]) + b"x") == b"abcabcabcabcx", "lz4: a match")


def literals(data):
    """An LZ4 block of literals only (valid LZ4, as a compressor that found nothing would write)."""
    n = len(data)
    if n < 15:
        return bytes([n << 4]) + data
    rest, ext = n - 15, bytearray()
    while rest >= 255:
        ext.append(255)
        rest -= 255
    ext.append(rest)
    return bytes([0xF0]) + bytes(ext) + data


session = {"windows": [{"selected": 2, "tabs": [
    {"index": 1, "entries": [{"title": "Other", "url": "https://other.example/"}]},
    {"index": 2, "entries": [{"title": "Old", "url": "https://old.example/"},
                             {"title": "Void Linux Handbook", "url": "https://docs.voidlinux.org/"}]}]}]}
raw = json.dumps(session).encode()
ff = os.path.join(HOME, ".mozilla", "firefox", "x.default", "sessionstore-backups")
os.makedirs(ff)
with open(os.path.join(ff, "recovery.jsonlz4"), "wb") as f:
    f.write(b"mozLz40\0" + len(raw).to_bytes(4, "little") + literals(raw))
ok(pageaddress.address("firefox", "Void Linux Handbook — Mozilla Firefox") == "https://docs.voidlinux.org/",
   "Firefox: the shown tab's address")
ok(pageaddress.address("firefox", "Not open — Mozilla Firefox") == "", "Firefox: no tab of that title, no address")
ok(pageaddress.address("Alacritty", "~") == "", "not a browser: no address")

open(os.path.join(HOME, ".slime-secret"), "w").write("s3cret\n")
swank = socket.socket()
swank.bind(("127.0.0.1", 0))
swank.listen(1)
got = []


def nyxt_swank():
    c, _ = swank.accept()
    buf = b""
    for _ in range(2):
        while len(buf) < 6 or len(buf) < 6 + int(buf[:6], 16):
            buf += c.recv(4096)
        n = int(buf[:6], 16)
        got.append(buf[6:6 + n].decode())
        buf = buf[6 + n:]
    reply = b'(:return (:ok ("" "\\"https://nyxt.atlas.engineer/\\"")) 1)'
    c.sendall(b"%06x" % len(reply) + reply)
    c.close()


threading.Thread(target=nyxt_swank, daemon=True).start()
os.environ["VIKIX_NYXT_SWANK_PORT"] = str(swank.getsockname()[1])
ok(pageaddress.address("Nyxt", "Nyxt") == "https://nyxt.atlas.engineer/", "Nyxt: asked through its Swank")
ok(got and got[0] == "s3cret", "the Swank password first")

sys.exit(fail)
