"""flights — search flights from a line of text, and watch routes for a cheaper price.

  flights "DXB LHR 12 Nov, back 20th"   the cheapest and quickest, in the terminal
  flights pick                 asks the line in rofi, then lists the flights;
                               Enter opens that search on Google Flights
  flights watch "DXB LHR 12 Nov"   check it every 6 hours; a notification
                               when the cheapest price drops
  flights watching             what's watched, with the cheapest seen
  flights unwatch N            stop watching the Nth
  flights check                check the watched ones now (the watcher does
                               it every 6 hours: flights daemon)

The line: two airports (their three-letter codes; one is enough when home is
set), a date, and "back DATE" (or "return DATE") for a round trip. Also:
business, premium, first; direct; "2 adults", "1 child". Dates as you'd write
them: 12 Nov, Nov 12, 2026-11-12, and "back 20th" in the same month.

Prices come from Google Flights, through the fast-flights library (no
account, no key): unofficial, so a change on Google's side can break it until
the library catches up. This only searches: booking happens in the browser,
on the site you choose, never here.

Settings: ~/.config/vikix/plugins/flights/settings (currency, home airport).
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime

HOME = os.path.expanduser("~")
CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
STATE = os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local", "state")
SETTINGS = os.path.join(CONFIG, "vikix", "plugins", "flights", "settings")
WATCHED = os.path.join(CONFIG, "vikix", "plugins", "flights", "watched")
SEEN = os.path.join(STATE, "vikix", "flights", "seen.json")
DROPS = os.path.join(STATE, "vikix", "flights-drops")
MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
NOT_AIRPORTS = set(MONTHS) | {"the", "and", "for", "out", "ret", "via", "one", "two", "way",
                              "mon", "tue", "wed", "thu", "fri", "sat", "sun"}


class Problem(Exception):
    pass


def settings():
    s = {"currency": "USD", "home": "", "language": "en"}
    try:
        with open(SETTINGS) as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    s[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return s


# --- The line --------------------------------------------------------------------

def parse_date(text, after):
    """A date in TEXT ("12 Nov", "Nov 12", "2026-11-12", "20th"), not before AFTER."""
    t = text.lower().strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    day = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", t)
    month = next((MONTHS[w[:3]] for w in re.findall(r"[a-z]+", t) if w[:3] in MONTHS), None)
    if not day:
        raise Problem(f"which day? ({text.strip()})")
    d = int(day.group(1))
    if month is None:                       # "20th": the month of AFTER, or the next
        month, year = after.month, after.year
        found = date(year, month, d) if d <= 31 else None
        if found is None or found < after:
            month, year = (1, year + 1) if month == 12 else (month + 1, year)
            found = date(year, month, d)
        return found
    found = date(after.year, month, d)
    return found if found >= after else date(after.year + 1, month, d)


def parse(line, home=""):
    """The line as a search: {'from', 'to', 'out', 'back', 'seat', 'direct', 'adults', 'children'}."""
    text = " " + line.strip() + " "
    q = {"seat": "economy", "direct": False, "adults": 1, "children": 0, "back": None}
    low = text.lower()
    for seat in ("premium", "business", "first"):
        if re.search(rf"\b{seat}\b", low):
            q["seat"] = "premium-economy" if seat == "premium" else seat
    q["direct"] = bool(re.search(r"\b(direct|non-?stop)\b", low))
    m = re.search(r"\b(\d)\s*adults?\b", low)
    if m:
        q["adults"] = int(m.group(1))
    m = re.search(r"\b(\d)\s*(?:child|children|kids?)\b", low)
    if m:
        q["children"] = int(m.group(1))
    # Airports: three-letter words before the first number (dxb lhr 12 nov),
    # or in capitals anywhere (12 Nov DXB to LHR).
    digit = re.search(r"\d", text)
    head, rest = (text[:digit.start()], text[digit.start():]) if digit else (text, "")
    airports = []
    for w in re.findall(r"\b[A-Za-z]{3}\b", head) + re.findall(r"\b[A-Z]{3}\b", rest):
        if w.lower() not in NOT_AIRPORTS and w.upper() not in airports:
            airports.append(w.upper())
    if len(airports) == 1 and home:
        airports = [home.upper()] + airports
    if len(airports) < 2:
        raise Problem("two airports, by their codes: DXB LHR (or set home in the settings)")
    q["from"], q["to"] = airports[0], airports[1]
    # Dates: what's after "back"/"return" is the way home.
    parts = re.split(r"\b(?:back|return|returning|ret)\b", low, maxsplit=1)
    strip = lambda s: re.sub(r"\b(\d)\s*(adults?|child(?:ren)?|kids?)\b", " ", s)
    today = date.today()
    q["out"] = parse_date(strip(parts[0]).replace(q["from"].lower(), " ").replace(q["to"].lower(), " "), today)
    if len(parts) > 1:
        q["back"] = parse_date(strip(parts[1]), q["out"])
    return q


def describe(q):
    s = f"{q['from']} → {q['to']}, {q['out']:%a %d %b}"
    if q["back"]:
        s += f", back {q['back']:%a %d %b}"
    extra = [q["seat"]] if q["seat"] != "economy" else []
    if q["direct"]:
        extra.append("direct")
    if q["adults"] != 1 or q["children"]:
        extra.append(f"{q['adults']} adult{'s' if q['adults'] != 1 else ''}"
                     + (f", {q['children']} child{'ren' if q['children'] != 1 else ''}" if q["children"] else ""))
    return s + (f" ({', '.join(extra)})" if extra else "")


# --- Searching ----------------------------------------------------------------------

def search(q, s):
    """(flights, link): flights as dicts, cheapest first; link the same search on Google Flights."""
    fake = os.environ.get("FLIGHTS_FAKE")    # tests: results from a file, no network
    if fake:
        with open(fake) as f:
            data = json.load(f)
        return data["flights"], data["link"]
    from fast_flights import FlightQuery, Passengers, create_query, get_flights

    def query_for(direct):
        legs = [FlightQuery(date=q["out"].isoformat(), from_airport=q["from"], to_airport=q["to"],
                            max_stops=0 if direct else None)]
        if q["back"]:
            legs.append(FlightQuery(date=q["back"].isoformat(), from_airport=q["to"], to_airport=q["from"],
                                    max_stops=0 if direct else None))
        return create_query(flights=legs, seat=q["seat"], trip="round-trip" if q["back"] else "one-way",
                            passengers=Passengers(adults=q["adults"], children=q["children"]),
                            language=s.get("language", "en"), currency=s["currency"])

    query = query_for(q["direct"])
    try:
        results = list(get_flights(query))
    except Exception as e:
        raise Problem(f"the search didn't work ({type(e).__name__}): Google Flights may have changed; "
                      f"try the link instead: {query.url()}")
    # Google's answer to a plain search is a short list of "best" flights,
    # which can leave out every direct one (Dubai-Singapore: four flights,
    # all with a stop). So direct flights are asked for as well.
    if not q["direct"]:
        try:
            results += list(get_flights(query_for(True)))
        except Exception:
            pass
    flights, keys = [], set()
    for r in results:
        legs = r.flights
        if not legs:
            continue
        minutes = sum(l.duration for l in legs)
        for a, b in zip(legs, legs[1:]):            # layovers: both times local to the same airport
            arr = datetime(*a.arrival.date, *a.arrival.time)
            dep = datetime(*b.departure.date, *b.departure.time)
            minutes += max(0, int((dep - arr).total_seconds() // 60))
        f = {
            "price": r.price, "airlines": list(dict.fromkeys(r.airlines)),
            "depart": "%02d:%02d" % legs[0].departure.time, "arrive": "%02d:%02d" % legs[-1].arrival.time,
            "arrive_day": (date(*legs[-1].arrival.date) - date(*legs[0].departure.date)).days,
            "stops": len(legs) - 1, "via": [l.to_airport.code for l in legs[:-1]], "minutes": minutes,
        }
        key = (f["price"], f["depart"], f["arrive"], tuple(f["airlines"]), f["stops"])
        if key not in keys:                         # the same flight from both searches, once
            keys.add(key)
            flights.append(f)
    flights.sort(key=lambda f: (f["price"], f["minutes"]))
    return flights, query.url()


def hours(minutes):
    return f"{minutes // 60}h{minutes % 60:02d}"


def row(f, currency, quickest):
    stops = "direct" if f["stops"] == 0 else f"{f['stops']} stop{'s' if f['stops'] > 1 else ''} ({', '.join(f['via'])})"
    marks = []
    if quickest:
        marks.append("quickest")
    times = f"{f['depart']}-{f['arrive']}" + (f"+{f['arrive_day']}" if f['arrive_day'] else "")
    return (f"{currency} {f['price']:>6}  {times:<13}  {hours(f['minutes']):>6}  {stops:<16}  {', '.join(f['airlines'])}"
            + (f"  [{', '.join(marks)}]" if marks else ""))


def rows(flights, currency):
    quick = min(flights, key=lambda f: f["minutes"]) if flights else None
    return [row(f, currency, f is quick) for f in flights]


# --- Watching ---------------------------------------------------------------------------

def watched():
    try:
        with open(WATCHED) as f:
            return [l.strip() for l in f if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        return []


def save_watched(lines):
    os.makedirs(os.path.dirname(WATCHED), exist_ok=True)
    with open(WATCHED, "w") as f:
        f.write("# Routes flights watches (flights watch LINE; flights unwatch N).\n")
        f.writelines(l + "\n" for l in lines)


def load_seen():
    try:
        with open(SEEN) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    with open(SEEN + ".new", "w") as f:
        json.dump(seen, f, indent=1)
    os.replace(SEEN + ".new", SEEN)


def notify(title, body):
    subprocess.run(["notify-send", "-a", "Vikix", title, body], check=False)


def check(quiet=False):
    """Search every watched route; a drop below the cheapest seen is notified
    and noted for the bar. Routes whose date has passed stop being watched."""
    s = settings()
    seen = load_seen()
    keep = []
    for line in watched():
        try:
            q = parse(line, s["home"])
        except Problem:
            keep.append(line)
            continue
        if q["out"] < date.today():
            if not quiet:
                print(f"{line}: its date has passed; not watched any more")
            continue
        keep.append(line)
        try:
            flights, link = search(q, s)
        except Problem as e:
            print(f"{line}: {e}", file=sys.stderr)
            continue
        if not flights:
            continue
        cheapest = flights[0]["price"]
        before = seen.get(line, {}).get("price")
        seen[line] = {"price": cheapest, "lowest": min(cheapest, seen.get(line, {}).get("lowest", cheapest)),
                      "checked": int(time.time()), "link": link}
        if before is not None and cheapest < before:
            what = f"{describe(q)}: {s['currency']} {cheapest} (was {before})"
            notify("A flight is cheaper", what)
            with open(DROPS, "a") as f:
                f.write(f"{line}\t{s['currency']} {cheapest}\t{before}\t{link}\n")
        if not quiet:
            print(f"{describe(q)}: {s['currency']} {cheapest}" + (f" (was {before})" if before else ""))
    save_seen(seen)
    if keep != watched():
        save_watched(keep)


# --- The commands --------------------------------------------------------------------------

def run(line):
    s = settings()
    q = parse(line, s["home"])
    flights, link = search(q, s)
    print(describe(q) + (f", cheapest {s['currency']} {flights[0]['price']}" if flights else ": no flights found"))
    for r in rows(flights, s["currency"])[:15]:
        print("  " + r)
    print(f"  On Google Flights (to book there, or on the airline's site): {link}")


def rofi(prompt, lines=(), mesg=None):
    args = ["rofi", "-dmenu", "-i", "-p", prompt, "-format", "i:s",
            "-theme-str", "window { width: 72%; }"]
    if mesg:
        args += ["-mesg", mesg]
    r = subprocess.run(args, input="\n".join(lines), capture_output=True, text=True)
    if r.returncode != 0:
        return None, None
    i, _, text = r.stdout.rstrip("\n").partition(":")
    return (int(i) if i.lstrip("-").isdigit() else -1), text


def browse(link):
    subprocess.Popen(["setsid", "-f", "xdg-open", link], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pick():
    s = settings()
    examples = ["DXB LHR 12 Nov, back 20th", "LHR JFK 3 Dec business", "DXB BEY 5 Jan direct 2 adults"]
    if s["home"]:
        examples.insert(0, "LHR 12 Nov (from your home airport)")
    _, line = rofi("Flights", examples + [f"watched: {w}" for w in watched()],
                   mesg="Two airports and a date; back DATE for a round trip")
    if not line:
        return
    line = line.removeprefix("watched: ").removesuffix(" (from your home airport)")
    try:
        q = parse(line, s["home"])
        flights, link = search(q, s)
    except Problem as e:
        notify("Flights", str(e))
        return
    if not flights:
        notify("Flights", f"{describe(q)}: nothing found")
        return
    entries = rows(flights, s["currency"]) + [f"Watch this route: a notification when it gets cheaper"]
    i, _ = rofi("Flights", entries, mesg=f"{describe(q)}: Enter opens it on Google Flights, to book there")
    if i is None:
        return
    if i == len(entries) - 1:
        if line not in watched():
            save_watched(watched() + [line])
        notify("Flights", f"Watching {describe(q)} (cheapest now {s['currency']} {flights[0]['price']})")
        seen = load_seen()
        seen[line] = {"price": flights[0]["price"], "lowest": flights[0]["price"], "checked": int(time.time()), "link": link}
        save_seen(seen)
    else:
        browse(link)


def drops():
    """The drops noted, in rofi; Enter opens one; then they're cleared."""
    try:
        with open(DROPS) as f:
            rows_ = [l.rstrip("\n").split("\t") for l in f if l.strip()]
    except FileNotFoundError:
        rows_ = []
    if not rows_:
        notify("Flights", "No price drops")
        return
    s = settings()
    shown = []
    for line, now, before, link in rows_:
        try:
            shown.append(f"{describe(parse(line, s['home']))}: {now} (was {before})")
        except Problem:
            shown.append(f"{line}: {now} (was {before})")
    i, _ = rofi("Cheaper", shown, mesg="Enter opens it on Google Flights")
    os.remove(DROPS)
    if i is not None and 0 <= i < len(rows_):
        browse(rows_[i][3])


def daemon():
    while True:
        try:
            check(quiet=True)
        except Exception as e:
            print(f"flights: {type(e).__name__}: {e}", file=sys.stderr)
        time.sleep(6 * 3600)


def main(argv):
    try:
        if not argv or argv[0] in ("-h", "--help", "help"):
            print(__doc__.strip())
        elif argv[0] == "pick":
            pick()
        elif argv[0] == "watch" and len(argv) > 1:
            line = " ".join(argv[1:])
            q = parse(line, settings()["home"])
            if line not in watched():
                save_watched(watched() + [line])
            print(f"watching {describe(q)}; checked every 6 hours (flights check: now)")
        elif argv[0] == "watching":
            seen = load_seen()
            s = settings()
            for n, line in enumerate(watched(), 1):
                p = seen.get(line, {})
                print(f"{n}. {line}" + (f"   cheapest {s['currency']} {p['price']} (lowest {p['lowest']})" if p else "   not checked yet"))
        elif argv[0] == "unwatch" and len(argv) == 2 and argv[1].isdigit():
            lines = watched()
            n = int(argv[1])
            if not 1 <= n <= len(lines):
                raise Problem(f"there's no {n} (flights watching)")
            print(f"stopped watching {lines[n - 1]}")
            save_watched(lines[:n - 1] + lines[n:])
        elif argv[0] == "check":
            check()
        elif argv[0] == "drops":
            drops()
        elif argv[0] == "daemon":
            daemon()
        else:
            run(" ".join(argv))
    except Problem as e:
        print(f"flights: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
