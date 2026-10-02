"""ai-usage's note: the plan's use Claude Code gave its status line (JSON on
stdin), written to the file named first, for the bar; and, every 15 minutes
at most, a record in Vikix's record store (vikix records), so the plan's use
over days and weeks can be looked back on."""
import json
import os
import subprocess
import sys
import time

path = sys.argv[1]
try:
    data = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
limits = data.get("rate_limits") or {}
names = {"five_hour": "5h", "seven_day": "week", "spend_limit": "extra"}
known = {n: limits[n] for n in names
         if isinstance(limits.get(n), dict) and limits[n].get("used_percentage") is not None}
if not known:
    sys.exit(0)        # nothing known yet (no answer this session): keep the last note
lines = [f"{n} {float(w['used_percentage']):.0f} {int(w.get('resets_at') or 0)}" for n, w in known.items()]
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path + ".new", "w") as f:
    f.write("\n".join(lines + [f"noted {int(time.time())}"]) + "\n")
os.replace(path + ".new", path)

kept = path + "-kept"
try:
    last = os.path.getmtime(kept)
except OSError:
    last = 0
if time.time() - last >= 900:
    open(kept, "w").close()
    title = "Claude plan: " + ", ".join(f"{float(w['used_percentage']):.0f}% {names[n]}" for n, w in known.items())
    try:
        subprocess.run(["vikix", "records", "add"], input=json.dumps(
            {"plugin": "ai-usage", "kind": "usage", "title": title, "data": known}),
            text=True, capture_output=True, timeout=10)
    except Exception:
        pass
