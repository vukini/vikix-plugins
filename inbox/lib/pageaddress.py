"""The address of the page a browser window shows, for a note's source.

Firefox: its session file (sessionstore-backups/recovery.jsonlz4, written
every 15 seconds while it runs), the tab whose title is the window's. A
page opened in the last few seconds may not be there yet: then no address.
Nyxt: asked through its Swank (127.0.0.1:4006, with ~/.slime-secret, as
Vikix sets it up). Chromium (the web apps) keeps no file to read it from:
the window's title only.
"""
import glob
import json
import os
import re
import socket

HOME = os.path.expanduser("~")


def lz4_block(src):
    """LZ4's block format, decompressed (what Firefox's mozLz4 files hold)."""
    dst = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        dst += src[i:i + lit]
        i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        length = token & 15
        if length == 15:
            while True:
                b = src[i]
                i += 1
                length += b
                if b != 255:
                    break
        length += 4
        start = len(dst) - off
        if off >= length:
            dst += dst[start:start + length]
        else:                       # overlapping: a run, copied a byte at a time
            for k in range(length):
                dst.append(dst[start + k])
    return bytes(dst)


def read_mozlz4(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"mozLz40\0":
        raise ValueError("not a mozLz4 file")
    return lz4_block(data[12:])


def firefox_session():
    """The newest session file of any Firefox profile."""
    files = glob.glob(os.path.join(HOME, ".mozilla/firefox/*/sessionstore-backups/recovery.jsonlz4"))
    if not files:
        return None
    return json.loads(read_mozlz4(max(files, key=os.path.getmtime)))


def firefox(title):
    """The address of the tab titled TITLE (the window's title less " — Mozilla Firefox")."""
    page = re.sub(r"\s+[—–-]\s+(Mozilla )?Firefox( Private Browsing)?$", "", title).strip()
    if not page:
        return ""
    session = firefox_session()
    if not session:
        return ""
    found = ""
    for w in session.get("windows", []):
        tabs = w.get("tabs", [])
        selected = w.get("selected", 1) - 1
        for k, tab in enumerate(tabs):
            entries = tab.get("entries") or []
            if not entries:
                continue
            e = entries[max(0, min(len(entries), tab.get("index", len(entries))) - 1)]
            if (e.get("title") or "").strip() == page:
                if k == selected:          # a window's shown tab first
                    return e.get("url", "")
                found = found or e.get("url", "")
    return found


def swank_eval(port, form, timeout=3):
    """FORM's value as Swank prints it, or "" (a Swank with ~/.slime-secret wants it first)."""
    def packet(text):
        body = text.encode()
        return b"%06x" % len(body) + body

    def lisp_string(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            try:
                with open(os.path.join(HOME, ".slime-secret")) as f:
                    s.sendall(packet(f.readline().rstrip("\n")))
            except FileNotFoundError:
                pass
            s.sendall(packet('(:emacs-rex (swank:eval-and-grab-output %s) "COMMON-LISP-USER" t 1)'
                             % lisp_string(form)))
            buf = b""
            while True:
                while len(buf) < 6:
                    chunk = s.recv(65536)
                    if not chunk:
                        return ""
                    buf += chunk
                size = int(buf[:6], 16)
                while len(buf) < 6 + size:
                    chunk = s.recv(65536)
                    if not chunk:
                        return ""
                    buf += chunk
                msg, buf = buf[6:6 + size].decode(errors="replace"), buf[6 + size:]
                if msg.startswith("(:return"):
                    m = re.match(r'\(:return \(:ok \("(?:[^"\\]|\\.)*" "((?:[^"\\]|\\.)*)"\)\)', msg)
                    return m.group(1).replace('\\"', '"').replace("\\\\", "\\") if m else ""
    except (OSError, ValueError):
        return ""


def nyxt():
    value = swank_eval(int(os.environ.get("VIKIX_NYXT_SWANK_PORT", "4006")),
                       "(nyxt:render-url (nyxt:url (nyxt:current-buffer)))")
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else ""


def address(program, title):
    """The page's address for a window of PROGRAM titled TITLE, or ""."""
    try:
        p = program.lower()
        if p in ("firefox", "firefox-esr", "navigator"):
            return firefox(title)
        if p == "nyxt":
            return nyxt()
    except Exception:
        pass
    return ""
