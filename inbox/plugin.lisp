;;;; inbox — notes from anywhere, into your Org inbox.
;;;;
;;;; Super+Alt+i opens a small box over whatever you're doing: write, or
;;;; press Super+F9 and speak (dictation types into it). C-c C-c keeps the
;;;; note, C-c C-k drops it. Super+Alt+Shift+i does the same with what you'd
;;;; selected quoted in it. Each note lands in ~/Dropbox/notes/inbox.org as
;;;; a heading, with when and the window it came from. The box is an Emacs
;;;; frame titled "Note to inbox", floated here, in the middle of the screen.
;;;; Super+Alt+Shift+s sorts the inbox (inbox sort, in a terminal): a model
;;;; suggests where each note goes, you change what you like, then they
;;;; move, and to-dos go to Todoist when you say so.

(in-package :stumpwm)

(defparameter *inbox-frame-title* "Note to inbox")

;; The note's box floats over what you're doing, a little above the middle.
;; Emacs can't be told apart by class (every frame is "Emacs"), but a frame
;; given a name keeps it as its title. A rule, not a hook of the plugin's
;; own: Vikix lists it (vikix rules), keeps the guards (the title bar a tile
;; had, floating twice), and takes it away with the plugin.
(when-window (:title *inbox-frame-title*)
  :name "inbox: the note's box floats over what you're doing"
  (float :width 760 :height 360 :y "22%"))

(defcommand inbox-note () ()
  "A note into your Org inbox: write, or Super+F9 to speak."
  (run-shell-command "inbox note"))

(defcommand inbox-quote () ()
  "A note into your Org inbox, with what you've selected quoted."
  (run-shell-command "inbox quote"))

(defcommand inbox-sort () ()
  "File the inbox's notes where they belong: a model suggests, you choose (in a terminal)."
  ;; Vikix's terminal (*vikix-terminal*, Super+Return's), not $TERMINAL.
  (run-shell-command (format nil "VIKIX_TERMINAL='~a' inbox sort --term" *vikix-terminal*)))

(defcommand inbox-sync () ()
  "Your notes up to Dropbox: starts it if needed, a notification when they're up to date."
  (run-shell-command "inbox sync --notify"))

(defcommand inbox-open () ()
  "Your Org inbox, in Emacs."
  (run-shell-command "inbox open"))

(vikix-plugin-key "s-M-i" "inbox-note" "Notes: a note into your inbox (Super+F9 in it to speak)" "Notes")
(vikix-plugin-key "s-M-I" "inbox-quote" "Notes: a note into your inbox, quoting the selection" "Notes")
(vikix-plugin-menu "Notes: a note into your inbox" '(inbox-note) "Work")
(vikix-plugin-key "s-M-S" "inbox-sort" "Notes: sort the inbox into your Org files, to-dos to Todoist" "Notes")
(vikix-plugin-menu "Notes: sort the inbox" '(inbox-sort) "Work")
(vikix-plugin-menu "Notes: open the inbox" '(inbox-open) "Work")
(vikix-plugin-menu "Notes: sync with Dropbox" '(inbox-sync) "Work")
