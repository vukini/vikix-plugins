#!/usr/bin/env bash
# tests/check.sh — every plugin is well made: a manifest with its keys and
# known kinds, named as its folder; the files it names are there (scripts
# executable); its Lisp reads (sbcl, with StumpWM's packages made up, since
# this runs without StumpWM); its shell passes shellcheck; its own test
# passes.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
bad() { echo "FAIL $1: $2"; fail=1; }
field() { sed -n "s/^$2: *//p" "$1/manifest" | head -1; }

for dir in */; do
  p=${dir%/}
  [ "$p" = tests ] && continue
  [ -f "$p/manifest" ] || { bad "$p" "no manifest"; continue; }
  [ "$(field "$p" name)" = "$p" ] || bad "$p" "name: isn't the folder's name"
  [[ $p =~ ^[a-z][a-z0-9-]*$ ]] || bad "$p" "a name is small letters, digits and -"
  for key in about kinds vikix; do
    [ -n "$(field "$p" "$key")" ] || bad "$p" "no $key:"
  done
  for kind in $(field "$p" kinds); do
    case $kind in bar|menu|key|service) ;; *) bad "$p" "unknown kind $kind" ;; esac
  done
  [[ $(field "$p" vikix) =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || bad "$p" "vikix: isn't a version"
  for key in lisp setup remove; do
    f=$(field "$p" "$key")
    [ -z "$f" ] || [ -e "$p/$f" ] || bad "$p" "$key: names $f, which isn't there"
  done
  for f in setup remove test; do
    [ ! -e "$p/$f" ] || [ -x "$p/$f" ] || bad "$p" "$f isn't executable"
  done
  [ -n "$(field "$p" setup)" ] && [ -z "$(field "$p" changes)" ] && bad "$p" "setup: without changes: (say what it changes)"
  for f in "$p"/bin/*; do
    [ -e "$f" ] || continue
    [ -x "$f" ] || bad "$p" "$f isn't executable"
  done
  # Vikix's rule for keys: a plugin's keys are on Super+Alt (s-M-...).
  lisp=$(field "$p" lisp)
  if [ -n "$lisp" ] && [ -f "$p/$lisp" ]; then
    for k in $(grep -oE '\(vikix-plugin-key +"[^"]+"' "$p/$lisp" | grep -oE '"[^"]+"' | tr -d '"'); do
      [[ $k =~ ^s-M-([A-Za-z0-9]|F[0-9]{1,2})$ ]] || bad "$p" "its key $k isn't on Super+Alt (s-M- and a letter, digit or F-key)"
    done
  fi
  # The Lisp reads: every form, in a package like StumpWM's.
  lisp=$(field "$p" lisp)
  if [ -n "$lisp" ] && command -v sbcl >/dev/null; then
    sbcl --script /dev/stdin "$p/$lisp" <<'LISP' || bad "$p" "$lisp doesn't read"
(defpackage :stumpwm (:use :cl))
(defpackage :xlib (:use :cl) (:export #:window-id))
(let ((*package* (find-package :cl-user)))
  (handler-case
      (with-open-file (in (second sb-ext:*posix-argv*))
        (loop for form = (read in nil in) until (eq form in)
              when (and (consp form) (eq (first form) 'in-package))
                do (setf *package* (find-package (second form)))))
    (error (e) (format t "~a~%" e) (sb-ext:exit :code 1))))
LISP
  fi
  # The shell passes shellcheck.
  if command -v shellcheck >/dev/null; then
    for f in "$p"/setup "$p"/remove "$p"/test "$p"/bin/*; do
      [ -f "$f" ] && head -1 "$f" | grep -q 'sh$' || continue
      shellcheck -S warning "$f" || bad "$p" "shellcheck: $f"
    done
  fi
  [ -x "$p/test" ] && { "$p/test" || bad "$p" "its test failed"; }
done
[ "$fail" = 0 ] && echo "check: every plugin well made"
exit "$fail"
