;;;; agent-waiting — which Claude Code sessions wait for you, and what for.
;;;;
;;;; Claude's hooks (added by this plugin's setup) run agent-waiting, which
;;;; leaves a file per terminal window in ~/.local/state/vikix/agents/. Its
;;;; first line is the state and the time: "ask" (a dialog is open: a
;;;; permission, a question), "reply" (it finished, and its last words ask
;;;; something of you) or "done" (it finished); then the folder it works
;;;; in; then a line of what it said or wants. Here: the bar names the
;;;; session and its workspace, one that asks in the accent colour; a
;;;; notification says the same with that line, once a note; Super+Alt+w
;;;; (or a click on the bar) goes to the window, or lists them when several
;;;; wait, asking ones first, oldest first; and looking at a window clears
;;;; its note. A note whose window has closed is dropped. The hook tells
;;;; StumpWM when a note changes (agent-waiting-changed), so none of this
;;;; waits for the bar's next redraw.

(in-package :stumpwm)

(defparameter *agent-waiting-dir*
  (merge-pathnames ".local/state/vikix/agents/" (user-homedir-pathname)))

(defvar *agent-waiting-notify* :asks
  "Which notes come as a notification too: :asks (a session wants something
of you), :all (one that finished as well), or nil (the bar only). Yours to
set in user.lisp: (setf *agent-waiting-notify* :all).")

(defvar *agent-waiting-told* (make-hash-table :test 'eql)
  "Each window id, and the note of its (state and time) that was last told.")

(defun agent-waiting-window (id)
  (find id (all-windows) :key (lambda (w) (xlib:window-id (window-xwin w)))))

(defun agent-waiting-read (file)
  "FILE's note as (STATE TIME FOLDER LINE), or nil when it isn't one."
  (ignore-errors
   (with-open-file (in file :external-format :utf-8)
     (let* ((words (split-string (or (read-line in nil) "") " "))
            (folder (read-line in nil))
            (line (read-line in nil)))
       (when (member (first words) '("ask" "reply" "done") :test #'string=)
         (list (first words)
               (or (ignore-errors (parse-integer (second words))) 0)
               (or folder "")
               (or line "")))))))

(defun agent-waiting-asks-p (note)
  "True when NOTE's session wants something of you (a dialog, or its last words)."
  (and (member (second note) '("ask" "reply") :test #'string=) t))

(defun agent-waiting-notes ()
  "The notes, as (WINDOW STATE TIME FOLDER LINE): those with a dialog open
first, then those whose last words ask something, then the finished, the
oldest first in each. The focused window's, and those of windows that are gone, are cleared."
  (let ((notes '()))
    (dolist (file (ignore-errors (directory (merge-pathnames "*" *agent-waiting-dir*))))
      (let* ((id (and (null (pathname-type file))    ; not a note being written (.new)
                      (ignore-errors (parse-integer (pathname-name file)))))
             (window (and id (agent-waiting-window id)))
             (note (and window (agent-waiting-read file))))
        (cond ((null id))
              ((or (null window) (eq window (current-window)))
               (remhash id *agent-waiting-told*)
               (ignore-errors (delete-file file)))
              (note (push (cons window note) notes)))))
    (flet ((rank (note) (or (position (second note) '("ask" "reply") :test #'string=) 2)))
      (sort notes (lambda (a b)
                    (if (= (rank a) (rank b))
                        (< (third a) (third b))
                        (< (rank a) (rank b))))))))

(defun agent-waiting-short (text most)
  (if (> (length text) most)
      (concatenate 'string (string-right-trim " " (subseq text 0 (1- most))) "…")
      text))

(defun agent-waiting-name (note)
  "What to call NOTE's session: its window's title without Claude's mark in
front, or, where the title names nothing, the folder it works in."
  (let* ((title (or (ignore-errors (window-title (first note))) ""))
         (start (position-if #'alphanumericp title))
         (title (if start (subseq title start) ""))
         (folder (fourth note)))
    (cond ((and (plusp (length title))
                (not (member title '("Alacritty" "Claude Code" "claude") :test #'string-equal)))
           title)
          ((plusp (length folder)) folder)
          (t "an agent"))))

(defun agent-waiting-where (note)
  "The name of the workspace NOTE's window is on."
  (or (ignore-errors (group-name (window-group (first note)))) "?"))

(defun agent-waiting-age (note)
  "How long ago NOTE was left, in words."
  (let ((seconds (- (get-universal-time) 2208988800 (third note))))   ; its time counts from 1970
    (cond ((or (zerop (third note)) (< seconds 60)) "now")
          ((< seconds 3600) (format nil "~d min" (floor seconds 60)))
          (t (format nil "~d h" (floor seconds 3600))))))

(defun agent-waiting-tell (notes)
  "A notification for each of NOTES not told yet, as *agent-waiting-notify* has it."
  (dolist (note notes)
    (let ((id (xlib:window-id (window-xwin (first note))))
          (stamp (format nil "~a ~a" (second note) (third note))))
      (unless (equal (gethash id *agent-waiting-told*) stamp)
        (setf (gethash id *agent-waiting-told*) stamp)
        (when (or (eq *agent-waiting-notify* :all)
                  (and (eq *agent-waiting-notify* :asks) (agent-waiting-asks-p note)))
          (ignore-errors
           (run-shell-command
            (format nil "notify-send -a Vikix -- ~a ~a"
                    (vikix-shell-quote (format nil "~a ~a (workspace ~a)"
                                               (agent-waiting-name note)
                                               (if (agent-waiting-asks-p note) "asks" "is done")
                                               (agent-waiting-where note)))
                    (vikix-shell-quote (fifth note))))))))))

(defun agent-waiting-bar ()
  "asks: NAME (WORKSPACE), in the accent colour, with +N for more and how
many are done; or done: NAME (WORKSPACE) +N, subtle; or nothing."
  (let* ((notes (agent-waiting-notes))
         (asks (remove-if-not #'agent-waiting-asks-p notes))
         (done (remove-if #'agent-waiting-asks-p notes)))
    (agent-waiting-tell notes)
    (flet ((named (word list)
             (format nil "~a: ~a (~a)~@[ +~d~]" word
                     (agent-waiting-short (agent-waiting-name (first list)) 26)
                     (agent-waiting-where (first list))
                     (and (rest list) (length (rest list))))))
      (cond (asks (values (format nil "~a~@[, done ~d~]" (named "asks" asks) (and done (length done)))
                          :accent))
            (done (values (named "done" done) :subtle))))))

(defun agent-waiting-changed ()
  "A note changed (the hook says so): the bar is redrawn now, not at its next turn."
  (update-all-mode-lines)
  t)

(defun agent-waiting-clear (window &rest ignore)
  (declare (ignore ignore))
  (when window
    (ignore-errors
     (delete-file (merge-pathnames (princ-to-string (xlib:window-id (window-xwin window)))
                                   *agent-waiting-dir*)))))

(defun agent-waiting-line (note)
  "NOTE as a line of the list: workspace, name, state and age, what it said."
  (format nil "~a  ~a  ~a, ~a~@[: ~a~]"
          (agent-waiting-where note)
          (agent-waiting-short (agent-waiting-name note) 34)
          (if (agent-waiting-asks-p note) "asks" "done")
          (agent-waiting-age note)
          (and (plusp (length (fifth note))) (agent-waiting-short (fifth note) 90))))

(defun agent-waiting-visit (note)
  (focus-all (first note))
  (agent-waiting-clear (first note))
  (update-all-mode-lines))

(defcommand agent-waiting-go () ()
  "Go to the agent that waits for you; when several do, pick from the list:
asking ones first, the oldest first."
  (let ((notes (agent-waiting-notes)))
    (cond ((null notes) (message "No agent waits for you."))
          ((null (rest notes)) (agent-waiting-visit (first notes)))
          (t (let ((choice (select-from-menu (current-screen)
                                             (mapcar (lambda (note) (list (agent-waiting-line note) note))
                                                     notes)
                                             "Agents waiting for you:")))
               (when choice
                 (agent-waiting-visit (second choice))))))))

;; Looking at a window is seeing its note: a rule for every window, when
;; it gets the focus (Vikix lists it, and takes it away with the plugin).
(when-window () :on :focus
  :name "agent-waiting: looking at a window is seeing its note"
  (agent-waiting-clear (window)))

(vikix-plugin-bar "agent-waiting" 'agent-waiting-bar :click "agent-waiting-go")
(vikix-plugin-key "s-M-w" "agent-waiting-go" "Go to the agent waiting for you, or pick among several" "Agents")
(vikix-plugin-menu "Agents: go to the one waiting for you" '(agent-waiting-go) "AI")
