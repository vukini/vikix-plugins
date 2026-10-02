;;;; flights — search flights from a line, watch routes for a cheaper price.
;;;;
;;;; Super+Alt+f asks the line in rofi ("DXB LHR 12 Nov, back 20th"), lists
;;;; the flights (cheapest first, the quickest marked), and opens the search
;;;; on Google Flights to book there. flights daemon (started with the
;;;; desktop) checks the watched routes every 6 hours; when one gets
;;;; cheaper, a notification, and the bar says "flight cheaper" until you
;;;; look (a click, or Super+Alt+f's list).

(in-package :stumpwm)

(defparameter *flights-drops*
  (merge-pathnames ".local/state/vikix/flights-drops" (user-homedir-pathname)))

(defun flights-bar ()
  (with-open-file (in *flights-drops* :if-does-not-exist nil)
    (when in
      (let ((n (loop for line = (read-line in nil) while line count (plusp (length line)))))
        (when (plusp n)
          (values (if (= n 1) "flight cheaper" (format nil "flights cheaper ~d" n)) :accent))))))

(defcommand flights-search () ()
  "Search flights: a line like DXB LHR 12 Nov, back 20th."
  (run-shell-command "flights pick"))

(defcommand flights-drops () ()
  "The watched flights that got cheaper."
  (run-shell-command "flights drops"))

(vikix-plugin-bar "flights" 'flights-bar :click "flights-drops")
(vikix-plugin-key "s-M-f" "flights-search" "Flights: search (DXB LHR 12 Nov, back 20th)" "Travel")
(vikix-plugin-menu "Flights: search" '(flights-search))
(vikix-plugin-menu "Flights: the watched ones that got cheaper" '(flights-drops))
