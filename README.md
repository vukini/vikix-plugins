# Vikix plugins

Small additions to [Vikix](https://vikix.dev), each one a folder here: a few words in the bar, entries in the Super+m menu, keys, or a program started with the desktop. They aren't part of Vikix's core; you add the ones you want:

```sh
vikix plugin list              # the plugins there are, and yours
vikix plugin add agent-waiting # shows what it runs and needs, asks, then adds it
vikix plugin remove agent-waiting
vikix plugin off NAME          # stop loading one (works from a text console too)
vikix plugin safe              # the next login loads none: for a plugin that hangs the desktop
```

Vikix uses this repository at a pinned commit, one it has checked: an update can't swap a plugin's code in silently. Every plugin here is Vid's own, for now.

## The plugins

| Plugin | What it does |
|---|---|
| [agent-waiting](agent-waiting/) | The bar says `agent asks` when a Claude Code session in another window waits for your answer, and `agents done N` when sessions have finished; Super+Alt+w goes to the window |
| [ai-usage](ai-usage/) | How much of your Claude plan you've used, the 5-hour window and the week (`plan 24% 41%`), from what Claude Code gives its status line; Super+Alt+u says when each resets; a record of it every 15 minutes |
| [next-meeting](next-meeting/) | Your next meeting in the bar (`Standup 14:30 in 12m`, `now: Standup`), from your calendars' private links (Microsoft 365, Google, Todoist), a notification 5 minutes before; Super+Alt+j joins it (Teams in the Teams web app), Super+Alt+c lists the week; each meeting joined is a record |
| [flights](flights/) | Search flights from a line (`DXB LHR 12 Nov, back 20th`): cheapest first, the quickest marked, Enter opens the search on Google Flights to book there; watch a route and get a notification (and `flight cheaper` in the bar) when it drops; Super+Alt+f. Prices from Google Flights through fast-flights (no account; unofficial); each search and each price checked is a record; it never books |
| [repos](repos/) | Which git projects in `~/src` (and `~/.emacs.d`, `~/.dotfiles`) need pushing, pulling or committing: `git 2` in the bar; Super+Alt+g opens a terminal with the details and the commands that do it, a shell ready, the commands one Up away. Asks GitHub every 30 minutes over HTTPS (gh's login), never needing your key's passphrase; never pushes or pulls by itself |
| [inbox](inbox/) | Notes from anywhere: Super+Alt+i opens a small box over what you're doing (write, or Super+F9 to speak), Super+Alt+Shift+i quotes the selection; each note lands in your Org inbox, `~/Dropbox/notes/inbox.org` (the phones see it through Dropbox), with when and the window it came from. `inbox add TEXT` from a terminal |

## What a plugin is

A folder named after it, with a `manifest` and its code:

```
agent-waiting/
  manifest           what it is, what it needs (below)
  plugin.lisp        loaded into StumpWM at login and on Reload config
  bin/               its programs; on your PATH while it's added
  setup, remove      run once by add and remove, after showing you what they do
```

The `manifest` is lines of `key: value`:

| Key | |
|---|---|
| `name` | the folder's name: small letters, digits and `-` |
| `about` | one line, for `vikix plugin list` |
| `kinds` | any of `bar`, `menu`, `key`, `service` |
| `vikix` | the oldest Vikix it works with (`0.71.41`) |
| `packages` | Void packages it needs, installed by `add` (space-separated; optional) |
| `lisp` | its Lisp file, loaded into StumpWM (optional) |
| `service` | a command started with the desktop, and by `add` (optional) |
| `setup` | what `add` runs once, in a line for people, then the script (optional) |
| `changes` | in words, what `setup` changes outside the plugin, shown before you agree |

### Its Lisp

`plugin.lisp` runs inside StumpWM, with all of its power: so a plugin is code you trust, like your `user.lisp`. It's loaded a form at a time, as Vikix's own files are: a mistake costs only that form, and a menu asks what to do. Vikix gives it a few calls:

```lisp
(vikix-plugin-bar "agent-waiting" 'my-function)   ; a few words in the bar, from the function (nil: nothing)
(vikix-plugin-key "s-M-w" "my-command" "What it does" "agent-waiting")   ; a key, in the key card
(vikix-plugin-menu "Agents: go to the waiting one" '(my-command))        ; an entry in Super+m
```

A bar function is called at every redraw of the bar (each second or so): it reads what it needs, quickly, and never waits on a program or the network. A timer does the slow work and leaves the result where the function finds it.

### What it found

What a plugin finds that's worth looking back on goes in Vikix's record store, not a file of its own: one SQLite file, searchable (`vikix records search`, `list`, `get`, `export`) and readable by agents. Write with `vikix records add`, JSON on stdin, one record or a list:

```sh
echo '{"plugin": "flights", "kind": "search", "key": "DXB SIN 2026-10-03",
       "title": "DXB → SIN, Sat 3 Oct: from USD 364", "body": "…",
       "data": {"cheapest": 364}, "link": "https://…"}' | vikix records add
```

`plugin`, `kind` and `title` are needed; the same plugin, kind and key updates the record rather than adding one (no key: always a new one). Ignore its errors: an older Vikix has no record store, and a plugin should work without it.

### Settings

A plugin's code is Vikix's: it's replaced when the pin moves. Its settings are yours: `~/.config/vikix/plugins/NAME/`, copied once from the plugin's `settings/` folder, never overwritten.

## Checks

`tests/check.sh` (and GitHub, on every push): every manifest has its keys and a known kind, every Lisp file reads, every shell script passes shellcheck, and each plugin's own `test` runs.

## Licence

MIT.
