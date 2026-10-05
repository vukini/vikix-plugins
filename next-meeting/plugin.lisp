;;;; next-meeting — your next meeting, in the bar.
;;;;
;;;; next-meeting watch (started with the desktop) reads your calendars every
;;;; 5 minutes into ~/.local/state/vikix/next-meeting, a line a meeting:
;;;; start, end (Unix times), the calendar's label, the title and its link,
;;;; split by tabs. Here: the bar shows the one on now ("now: Standup"), or
;;;; the next within 4 hours ("Standup 14:30 in 12m"), in the accent colour
;;;; from 10 minutes before. Super+Alt+j (or a click) joins it; Super+Alt+c
;;;; lists the week.

(in-package :stumpwm)

(defparameter *next-meeting-file*
  (merge-pathnames ".local/state/vikix/next-meeting" (user-homedir-pathname)))

(defun next-meeting-now () (- (get-universal-time) (encode-universal-time 0 0 0 1 1 1970 0)))

(defun next-meeting-rows ()
  "The meetings not over yet: ((START END LABEL TITLE LINK) ...), in order."
  (let ((now (next-meeting-now)))
    (with-open-file (in *next-meeting-file* :if-does-not-exist nil :external-format :utf-8)
      (when in
        (loop for line = (read-line in nil)
              while line
              for f = (split-string line (string #\Tab))
              for start = (ignore-errors (parse-integer (first f)))
              for end = (ignore-errors (parse-integer (second f)))
              when (and start end (= (length f) 5) (> end now))
                collect (list start end (third f) (fourth f) (fifth f)))))))

(defun next-meeting-short (title)
  (if (> (length title) 28) (concatenate 'string (subseq title 0 27) "…") title))

(defun next-meeting-clock (unix)
  (multiple-value-bind (s m h) (decode-universal-time (+ unix (encode-universal-time 0 0 0 1 1 1970 0)))
    (declare (ignore s))
    (format nil "~2,'0d:~2,'0d" h m)))

(defun next-meeting-bar ()
  (let* ((now (next-meeting-now))
         (rows (next-meeting-rows))
         (on (find-if (lambda (r) (<= (first r) now)) rows))
         (next (find-if (lambda (r) (> (first r) now)) rows)))
    (cond (on (values (format nil "now: ~a" (next-meeting-short (fourth on))) :accent))
          ((and next (<= (- (first next) now) (* 4 3600)))
           (let ((minutes (ceiling (- (first next) now) 60)))
             (values (format nil "~a ~a in ~a" (next-meeting-short (fourth next))
                             (next-meeting-clock (first next))
                             (if (< minutes 60) (format nil "~dm" minutes)
                                 (format nil "~dh~2,'0dm" (floor minutes 60) (mod minutes 60))))
                     (if (<= minutes 10) :accent :subtle)))))))

(defcommand next-meeting-join () ()
  "Join the meeting on now, or the next one (its Teams, Meet or Zoom link)."
  (run-shell-command "next-meeting join"))

(defcommand next-meeting-week () ()
  "The coming week's meetings; Enter joins the one picked."
  (run-shell-command "next-meeting pick"))

(vikix-plugin-bar "next-meeting" 'next-meeting-bar :click "next-meeting-join")
(vikix-plugin-key "s-M-j" "next-meeting-join" "Meetings: join the one on now, or the next" "Meetings")
(vikix-plugin-key "s-M-c" "next-meeting-week" "Meetings: the coming week; Enter joins one" "Meetings")
(vikix-plugin-menu "Meetings: the coming week" '(next-meeting-week) "Work")
