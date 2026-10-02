;;; inbox.el --- the inbox plugin's box: org-capture in a frame of its own  -*- lexical-binding: t -*-

;; bin/inbox opens a frame titled "Note to inbox" (plugin.lisp floats it by
;; that title) and calls `vikix-inbox-capture' with a file it wrote: the
;; inbox, the window the note comes from, what was selected. The capture
;; uses a template of its own, let-bound, so your org-capture-templates are
;; left as they are. C-c C-c keeps the note, C-c C-k drops it; either
;; closes the frame, and so does closing the window.

(require 'org)
(require 'org-capture)
(require 'json)
(require 'subr-x)

(defconst vikix-inbox-frame "Note to inbox")

(defvar-local vikix-inbox--info nil
  "The note's file, source and time, in its capture buffer.")

(defvar vikix-inbox--closing nil)

(defun vikix-inbox--read (ask)
  (prog1 (with-temp-buffer
           (insert-file-contents ask)
           (json-parse-buffer :object-type 'alist :null-object nil))
    (ignore-errors (delete-file ask))))

(defun vikix-inbox--escape (text)
  "TEXT safe inside an Org entry: a line starting * or #+ gets Org's comma."
  (replace-regexp-in-string "^\\(,*\\(?:\\*\\|#\\+\\)\\)" ",\\1" text))

(defun vikix-inbox-capture (ask)
  "Open a capture of a note into the inbox, as the file ASK describes."
  (let* ((info (vikix-inbox--read ask))
         (file (alist-get 'file info))
         (quote (string-trim (or (alist-get 'quote info) ""))))
    (make-directory (file-name-directory file) t)
    (unless (and (file-exists-p file) (> (file-attribute-size (file-attributes file)) 0))
      (with-temp-file file (insert "#+title: Inbox\n\n")))
    (let ((org-capture-templates `(("i" "Inbox" entry (file ,file) "* %?"
                                    ;; Not left open: the phones change the file
                                    ;; too, through Dropbox.
                                    :kill-buffer t))))
      (org-capture nil "i"))
    ;; Capture splits the window it's in; this frame is the note's alone.
    (delete-other-windows)
    (setq vikix-inbox--info info)
    (unless (string-empty-p quote)
      (save-excursion
        (goto-char (point-max))
        (insert "\n#+begin_quote\n" (vikix-inbox--escape quote) "\n#+end_quote")))
    (setq header-line-format
          (concat " "
                  (let ((src (alist-get 'source info)))
                    (if (and src (not (string-empty-p src))) (concat "From " src "  ·  ") ""))
                  "C-c C-c keeps it  ·  C-c C-k drops it  ·  Super+F9 speaks"))
    (select-frame-set-input-focus (selected-frame))
    ;; Over emacsclient's "When done with this frame, type C-x 5 0".
    (run-at-time 0.2 nil #'message "The first line is the note's title")))

(defun vikix-inbox--finish ()
  "Before the note is kept: a title if it has none, when and where from."
  (when vikix-inbox--info
    (save-excursion
      (goto-char (point-min))
      (when (string-blank-p (or (org-get-heading t t t t) ""))
        (end-of-line)
        (insert "Note"))
      (goto-char (point-min))
      (org-entry-put (point) "CREATED" (alist-get 'created vikix-inbox--info))
      (let ((src (alist-get 'source vikix-inbox--info)))
        (when (and src (not (string-empty-p src)))
          (org-entry-put (point) "SOURCE" src))))))

(defun vikix-inbox--close ()
  "After the note is kept or dropped: the frame goes."
  (let ((frame (selected-frame)))
    (when (and (not vikix-inbox--closing)
               (equal (frame-parameter frame 'name) vikix-inbox-frame))
      (let ((vikix-inbox--closing t))
        (delete-frame frame)))))

(defun vikix-inbox--frame-closed (frame)
  "The window closed without C-c C-c or C-c C-k: drop the note, so no
half-made heading is left in the inbox's buffer."
  (when (and (not vikix-inbox--closing)
             (equal (frame-parameter frame 'name) vikix-inbox-frame))
    (let ((vikix-inbox--closing t))
      (dolist (b (buffer-list))
        (when (and (buffer-live-p b) (buffer-local-value 'vikix-inbox--info b))
          (with-current-buffer b
            (ignore-errors (org-capture-kill))))))))

(add-hook 'org-capture-prepare-finalize-hook #'vikix-inbox--finish)
(add-hook 'org-capture-after-finalize-hook #'vikix-inbox--close)
(add-hook 'delete-frame-functions #'vikix-inbox--frame-closed)

(provide 'inbox)
;;; inbox.el ends here
