;;;; inbox — notes from anywhere, into your Org inbox.
;;;;
;;;; Super+Alt+i opens a small box over whatever you're doing: write, or
;;;; press Super+F9 and speak (dictation types into it). C-c C-c keeps the
;;;; note, C-c C-k drops it. Super+Alt+Shift+i does the same with what you'd
;;;; selected quoted in it. Each note lands in ~/Dropbox/notes/inbox.org as
;;;; a heading, with when and the window it came from. The box is an Emacs
;;;; frame titled "Note to inbox", floated here, in the middle of the screen.

(in-package :stumpwm)

(defparameter *inbox-frame-title* "Note to inbox")

(defun inbox-float-box (win)
  ;; Emacs can't be told apart by class (every frame is "Emacs"), but a
  ;; frame given a name keeps it as its title.
  (when (and (equal (window-title win) *inbox-frame-title*)
             (not (typep win 'float-window)))
    (let ((head (window-head win)))
      (float-window win (window-group win))
      ;; Tiled first, it got a Vikix title bar, which floating leaves over
      ;; the box's top line.
      (when (fboundp 'vikix-titlebar-remove)
        (funcall 'vikix-titlebar-remove win))
      (when head
        (let ((w (min 760 (- (head-width head) 40)))
              (h (min 360 (- (head-height head) 40))))
          (float-window-move-resize
           win :width w :height h
           :x (+ (head-x head) (floor (- (head-width head) w) 2))
           :y (+ (head-y head) (floor (- (head-height head) h) 3))))))))

(add-hook *new-window-hook* 'inbox-float-box)

(defcommand inbox-note () ()
  "A note into your Org inbox: write, or Super+F9 to speak."
  (run-shell-command "inbox note"))

(defcommand inbox-quote () ()
  "A note into your Org inbox, with what you've selected quoted."
  (run-shell-command "inbox quote"))

(defcommand inbox-open () ()
  "Your Org inbox, in Emacs."
  (run-shell-command "inbox open"))

(vikix-plugin-key "s-M-i" "inbox-note" "Notes: a note into your inbox (Super+F9 in it to speak)" "Notes")
(vikix-plugin-key "s-M-I" "inbox-quote" "Notes: a note into your inbox, quoting the selection" "Notes")
(vikix-plugin-menu "Notes: a note into your inbox" '(inbox-note))
(vikix-plugin-menu "Notes: open the inbox" '(inbox-open))
