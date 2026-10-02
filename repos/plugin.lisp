;;;; repos — what your git projects need, in the bar.
;;;;
;;;; repos watch (started with the desktop) looks at the projects in ~/src
;;;; every 2 minutes and asks GitHub what's new every 30, then leaves one
;;;; line for the bar in ~/.local/state/vikix/repos-bar: commits (and tags)
;;;; to push, commits to pull, projects with changes, projects needing
;;;; something. The bar stays short, "git 2", in the accent colour when
;;;; there's something to push or pull. Super+Alt+g (or a click) opens a
;;;; terminal with the details, the commands that do it (Up brings each
;;;; back), and a shell ready.

(in-package :stumpwm)

(defparameter *repos-bar-file*
  (merge-pathnames ".local/state/vikix/repos-bar" (user-homedir-pathname)))

(defun repos-bar ()
  "git 2: how many projects need something; the accent colour when there's
something to push or pull. The details are a key away (Super+Alt+g)."
  (with-open-file (in *repos-bar-file* :if-does-not-exist nil)
    (let* ((line (and in (read-line in nil)))
           (n (and line (mapcar (lambda (w) (or (ignore-errors (parse-integer w)) 0))
                                (split-string line " ")))))
      (when (and (= (length n) 4) (plusp (fourth n)))
        (destructuring-bind (push pull changed projects) n
          (declare (ignore changed))
          (values (format nil "git ~d" projects)
                  (if (or (plusp push) (plusp pull)) :accent :subtle)))))))

(defcommand repos-term () ()
  "A terminal with what your git projects need, the commands that do it (Up brings
them back), and a shell ready."
  (run-shell-command "repos term"))

(defcommand repos-pick () ()
  "Your git projects: what each needs; push, pull, Magit or a terminal."
  (run-shell-command "repos pick"))

(vikix-plugin-bar "repos" 'repos-bar :click "repos-term")
(vikix-plugin-key "s-M-g" "repos-term" "Projects: what to push, pull or commit, in a terminal ready for it" "Projects")
(vikix-plugin-menu "Projects: what to push, pull or commit (a terminal)" '(repos-term))
(vikix-plugin-menu "Projects: pick one to push, pull or open in Magit" '(repos-pick))
