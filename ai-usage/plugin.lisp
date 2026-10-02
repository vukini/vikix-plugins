;;;; ai-usage — how much of your Claude plan you've used, in the bar.
;;;;
;;;; Claude Code gives its status line the plan's use (with a Pro or Max
;;;; plan, after its first answer in a session); ai-usage-statusline notes it
;;;; in ~/.local/state/vikix/ai-usage, a line a window:
;;;;   five_hour 24 1790946000      used %, and when it resets (Unix time)
;;;;   seven_day 41 1791200000
;;;;   spend_limit 62 1793000000    an extra-usage limit, when there is one
;;;; The bar shows the 5-hour window and the week: "plan 24% 41%"; in the
;;;; accent colour from 75%, the alert colour from 90%. A window whose reset
;;;; has passed isn't shown: it starts again from nothing. Super+Alt+u (or a
;;;; click) says when each resets.

(in-package :stumpwm)

(defparameter *ai-usage-file*
  (merge-pathnames ".local/state/vikix/ai-usage" (user-homedir-pathname)))

(defun ai-usage-now () (- (get-universal-time) (encode-universal-time 0 0 0 1 1 1970 0)))

(defun ai-usage-windows ()
  "The windows still running: ((NAME PERCENT RESETS) ...)."
  (let ((now (ai-usage-now)))
    (with-open-file (in *ai-usage-file* :if-does-not-exist nil)
      (when in
        (loop for line = (read-line in nil)
              while line
              for words = (split-string line " ")
              for percent = (ignore-errors (parse-integer (second words)))
              for resets = (ignore-errors (parse-integer (third words)))
              when (and percent resets (> resets now)
                        (member (first words) '("five_hour" "seven_day" "spend_limit") :test #'string=))
                collect (list (first words) percent resets))))))

(defun ai-usage-percent (windows name)
  (second (find name windows :key #'first :test #'string=)))

(defun ai-usage-bar ()
  (let* ((windows (ai-usage-windows))
         (five (ai-usage-percent windows "five_hour"))
         (week (ai-usage-percent windows "seven_day"))
         (top (reduce #'max (remove nil (list five week 0)))))
    (when (or five week)
      (values (format nil "plan~@[ ~d%~]~@[ ~d%~]" five week)
              (cond ((>= top 90) :alert) ((>= top 75) :accent) (t :subtle))))))

(defun ai-usage-when (unix)
  (multiple-value-bind (s m h day month year weekday)
      (decode-universal-time (+ unix (encode-universal-time 0 0 0 1 1 1970 0)))
    (declare (ignore s month year))
    (let ((hours (/ (- unix (ai-usage-now)) 3600)))
      (if (< hours 20)
          (format nil "~2,'0d:~2,'0d (in ~a)" h m
                  (if (< hours 1) (format nil "~d min" (ceiling (* hours 60))) (format nil "~,1f h" hours)))
          (format nil "~a ~d, ~2,'0d:~2,'0d" (nth weekday '("Mon" "Tue" "Wed" "Thu" "Fri" "Sat" "Sun")) day h m)))))

(defcommand ai-usage () ()
  "How much of the Claude plan is used, and when each window resets."
  (let ((windows (ai-usage-windows)))
    (if (null windows)
        (message "Claude plan: nothing known yet.~%A Claude Code session notes it after its first answer.")
        (message "Claude plan~{~%~a~}"
                 (loop for (name percent resets) in windows
                       collect (format nil "~a: ~d% used, resets ~a"
                                       (cond ((string= name "five_hour") "5 hours")
                                             ((string= name "seven_day") "This week")
                                             (t "Extra usage"))
                                       percent (ai-usage-when resets)))))))

(vikix-plugin-bar "ai-usage" 'ai-usage-bar :click "ai-usage")
(vikix-plugin-key "s-M-u" "ai-usage" "Claude plan: how much is used, when it resets" "AI & voice")
(vikix-plugin-menu "Claude plan: how much is used" '(ai-usage))
