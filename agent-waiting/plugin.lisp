;;;; agent-waiting — which Claude Code sessions wait for you.
;;;;
;;;; Claude's hooks (added by this plugin's setup) run agent-waiting, which
;;;; leaves a file per terminal window in ~/.local/state/vikix/agents/:
;;;; "ask" (it wants an answer: a permission, a question) or "done" (it
;;;; finished). Here: the bar says so, asking in the accent colour; Super+Alt+w
;;;; (or a click on it) goes to the window, asking ones first, oldest first;
;;;; and looking at a window clears its note. A note whose window has
;;;; closed is dropped.

(in-package :stumpwm)

(defparameter *agent-waiting-dir*
  (merge-pathnames ".local/state/vikix/agents/" (user-homedir-pathname)))

(defun agent-waiting-window (id)
  (find id (all-windows) :key (lambda (w) (xlib:window-id (window-xwin w)))))

(defun agent-waiting-notes ()
  "The notes, as (WINDOW STATE TIME), asking first, then oldest first. The
focused window's, and those of windows that are gone, are cleared."
  (let ((notes '()))
    (dolist (file (ignore-errors (directory (merge-pathnames "*" *agent-waiting-dir*))))
      (let* ((id (and (null (pathname-type file))    ; not a note being written (.new)
                      (ignore-errors (parse-integer (pathname-name file)))))
             (line (and id (ignore-errors (with-open-file (in file) (read-line in nil)))))
             (words (and line (split-string line " ")))
             (window (and id (agent-waiting-window id))))
        (cond ((or (null window) (eq window (current-window)))
               (ignore-errors (delete-file file)))
              ((member (first words) '("ask" "done") :test #'string=)
               (push (list window (first words)
                           (or (ignore-errors (parse-integer (second words))) 0))
                     notes)))))
    (sort notes (lambda (a b)
                  (if (string= (second a) (second b))
                      (< (third a) (third b))
                      (string= (second a) "ask"))))))

(defun agent-waiting-bar ()
  "agent asks, in the accent colour; or agents done N, subtle; or nothing."
  (let* ((notes (agent-waiting-notes))
         (asks (count "ask" notes :key #'second :test #'string=))
         (done (- (length notes) asks)))
    (cond ((plusp asks)
           (values (if (= asks 1) "agent asks" (format nil "agents ask ~d" asks)) :accent))
          ((plusp done)
           (values (if (= done 1) "agent done" (format nil "agents done ~d" done)) :subtle)))))

(defun agent-waiting-clear (window &rest ignore)
  (declare (ignore ignore))
  (when window
    (ignore-errors
     (delete-file (merge-pathnames (princ-to-string (xlib:window-id (window-xwin window)))
                                   *agent-waiting-dir*)))))

(defcommand agent-waiting-go () ()
  "Go to the agent that waits for you: one asking first, the oldest first."
  (let ((note (first (agent-waiting-notes))))
    (if note
        (progn (focus-all (first note))
               (agent-waiting-clear (first note)))
        (message "No agent waits for you."))))

;; Looking at a window is seeing its note: a rule for every window, when
;; it gets the focus (Vikix lists it, and takes it away with the plugin).
(when-window () :on :focus
  :name "agent-waiting: looking at a window is seeing its note"
  (agent-waiting-clear (window)))

(vikix-plugin-bar "agent-waiting" 'agent-waiting-bar :click "agent-waiting-go")
(vikix-plugin-key "s-M-w" "agent-waiting-go" "Go to the agent waiting for you" "Agents")
(vikix-plugin-menu "Agents: go to the one waiting for you" '(agent-waiting-go))
