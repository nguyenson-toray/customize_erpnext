"""Automatic pull of attendance logs: machines -> Employee Checkin.

Replaces the biometric-attendance-sync-tool service (01.sync_log_from_device_to_erpnext.py)
from 23/10/2026. README.md in this folder has the decisions and traps.

- hooks cron */3 -> enqueue_device_log_sync -> queue "biometric" (own worker; falls back
  to "long" while that worker is not configured).
- Switch + options: Attendance Machine Setting (Auto Log Sync / Error Email sections).
- Machines: every ENABLED attendance machine of the Setting (door controllers excluded).
- Cursor per machine = MAX(Employee Checkin.time) of that device_id (no state file).
  Punches with time >= cursor are re-sent; _add_checkin skips the ones already there.
- An unexpected insert error stops that machine for this cycle so the cursor can
  never move past a punch that failed (same rule as the old tool).
- Machines are read IN PARALLEL (threads, pure pyzk) and inserted one by one in the
  main thread: the read phase lasts as long as the slowest machine (~22 s) instead
  of the sum (~90 s).
- Peak Times (Setting): reading locks a machine 8–22 s, so no read starts inside a
  peak window or less than PEAK_START_MARGIN before one. Punches stay on the machine.
- Catch-up after a peak (~950 punches at 08:00) is inserted in ONE cycle: inserting
  enqueues nothing (Attendance Calculation Setting.recalc_attendance_on_checkin_change
  is 0; attendance is computed hourly + by the 08:20 daily email). Guards kept for
  safety: MAX_INSERTS_PER_MACHINE bounds one cycle (e.g. a machine clock gone wrong),
  the cycle stops while queue "short" holds more than RECALC_QUEUE_GUARD jobs (in case
  per-checkin recalc is switched on), and QueueOverloaded defers instead of failing.
  Stopping early never loses a punch.
"""

import logging
import time as _time
from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime

from customize_erpnext.network.biometric.machines import get_machines
from customize_erpnext.network.biometric.resync import QUEUE_OVERLOADED_MARK, _add_checkin
from customize_erpnext.network.biometric.zk_device import bulk_read_cfg, read_attendance

SETTING = "Attendance Machine Setting"
QUEUE = "biometric"
JOB_ID = "biometric_device_log_sync"
JOB_TIMEOUT_S = 900
FUTURE_TOLERANCE = timedelta(minutes=10)   # device clock a little ahead is fine
OFFLINE_ALERT_AFTER = 3                    # consecutive failed cycles before it counts as an error
FAIL_KEY = "biometric_device_log_sync:fail:{}"
LAST_EMAIL_KEY = "biometric_device_log_sync:last_email"
# "biometric_device_log_sync:" keys survive bench clear-cache (hooks persistent_cache_keys)
HEARTBEAT_KEY = "biometric_device_log_sync:last_cycle"       # end of the last cycle that READ the machines
HEARTBEAT_ALERT_KEY = "biometric_device_log_sync:stalled"
LAST_REPORT_KEY = "biometric_device_log_sync:last_report"   # rows of that cycle -> Log Viewer status table
STALE_AFTER = timedelta(minutes=15)                         # peak windows not counted
DEFAULT_PEAK_TIMES = "07:30,07:45,17:00,18:00"   # measured rush 01–22/10/2026 (README)
DEFAULT_PEAK_WINDOW = 15
RECALC_QUEUE = "short"                     # employee_checkin._recalculate_attendance
RECALC_QUEUE_GUARD = 400                   # Frappe limit is 550 per queue
MAX_INSERTS_PER_MACHINE = 1000             # morning peak backlog: max 331/machine (Machine 7)
PEAK_START_MARGIN = timedelta(seconds=60)   # no read may start < 60 s before a peak (slowest read ~22–35 s)


def _logger():
    logger = frappe.logger("biometric_device_sync", allow_site=True)
    logger.setLevel(logging.INFO)  # frappe default is ERROR outside dev server
    return logger


def enqueue_device_log_sync():
    """Scheduler entry (hooks cron */3). No-op while Auto Pull is off or inside a peak window."""
    settings = frappe.get_cached_doc(SETTING)
    if not cint(settings.auto_sync_logs):
        return
    if in_peak(settings, now_datetime()):
        _logger().info("Skipped: peak window")
        return
    from frappe.utils.background_jobs import get_queues_timeout

    queue = QUEUE if QUEUE in get_queues_timeout() else "long"
    frappe.enqueue(
        "customize_erpnext.network.biometric.device_log_sync._run_device_log_sync",
        queue=queue,
        timeout=JOB_TIMEOUT_S,
        job_id=JOB_ID,
        deduplicate=True,
    )


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in test_device_log_sync.py)
# ---------------------------------------------------------------------------

def peak_windows(settings):
    """(start times, window minutes). Never set -> defaults; cleared -> no peaks.
    An unparsable value keeps the default peaks (safe side: never lock a machine in a rush)."""
    from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
        parse_peak_times,
    )

    raw = settings.get("peak_times")
    if raw is None:
        raw = DEFAULT_PEAK_TIMES
    try:
        starts = parse_peak_times(raw)
    except Exception:
        starts = parse_peak_times(DEFAULT_PEAK_TIMES)
    window = cint(settings.get("peak_window_minutes")) or DEFAULT_PEAK_WINDOW
    return starts, window


def peak_intervals(settings, day):
    """Peak windows of one day as merged [start, end) datetimes
    (07:30 + 07:45 with 15' -> one 07:30–08:00 window)."""
    starts, window = peak_windows(settings)
    merged = []
    for start_time in sorted(starts):
        start = datetime.combine(day, start_time)
        end = start + timedelta(minutes=window)
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [tuple(w) for w in merged]


def current_peak(settings, now):
    """The merged peak window containing `now`, or None."""
    for start, end in peak_intervals(settings, now.date()):
        if start <= now < end:
            return start, end
    return None


def in_peak(settings, now):
    """True inside [start, start + window) of any peak start time."""
    return current_peak(settings, now) is not None


def peak_overlap(settings, since, until):
    """Time of [since, until) that falls inside peak windows (any day in between)."""
    total = timedelta(0)
    day = since.date()
    while day <= until.date():
        for start, end in peak_intervals(settings, day):
            overlap = min(end, until) - max(start, since)
            if overlap > timedelta(0):
                total += overlap
        day += timedelta(days=1)
    return total


@frappe.whitelist()
def get_peak_status():
    """For the pages: manual actions that lock attendance machines ask before running in a peak."""
    from customize_erpnext.network.biometric.auth import check_biometric_access

    check_biometric_access()
    peak = current_peak(frappe.get_cached_doc(SETTING), now_datetime())
    if not peak:
        return {"in_peak": False}
    return {"in_peak": True, "start": peak[0].strftime("%H:%M"), "end": peak[1].strftime("%H:%M")}


def lower_bound(cursor, import_start_date):
    """Oldest punch time to import: the machine's latest checkin, never before Import Start Date."""
    start = datetime.combine(getdate(import_start_date), time.min) if import_start_date else None
    cursor = get_datetime(cursor) if cursor else None
    if cursor and start:
        return max(cursor, start)
    return cursor or start or datetime.combine(getdate(), time.min)


def select_new_records(records, lower, now):
    """Records to send, oldest first, plus counts of what was dropped.

    Dropped: no uid / empty user_id / no timestamp (device junk such as the
    2000-01-01 rows), before `lower`, and more than FUTURE_TOLERANCE after `now`
    (a wrong device clock must not push the cursor into the future).
    """
    counts = {"junk": 0, "old": 0, "future": 0}
    upper = now + FUTURE_TOLERANCE
    selected = []
    for rec in records:
        uid = getattr(rec, "uid", None)
        user_id = str(getattr(rec, "user_id", "") or "").strip()
        ts = getattr(rec, "timestamp", None)
        if not uid or not user_id or not ts:
            counts["junk"] += 1
        elif ts < lower:
            counts["old"] += 1
        elif ts > upper:
            counts["future"] += 1
        else:
            selected.append(rec)
    selected.sort(key=lambda r: r.timestamp)
    return selected, counts


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

def _cursor(device_name):
    """Latest checkin of this machine (index idx_emp_checkin_device_time)."""
    return frappe.db.sql(
        "SELECT MAX(time) FROM `tabEmployee Checkin` WHERE device_id = %s AND time <= %s",
        (device_name, now_datetime()),
    )[0][0]


def _recalc_queue_busy():
    """Queue "short" too full to take more recalc jobs. Unknown (redis error) = busy."""
    try:
        from frappe.utils.background_jobs import get_queue

        return get_queue(RECALC_QUEUE).count > RECALC_QUEUE_GUARD
    except Exception:
        return True


def _read_all(machines, clear_after):
    """Phase 2: read every machine IN PARALLEL (one thread per machine).

    🔴 Threads only talk to the devices (zk_device.read_attendance is pure pyzk);
    every frappe.* call (db, cache, log_error) stays in the calling thread.
    Each machine is still locked only for its own read (8–22 s); the whole read
    phase takes as long as the slowest machine instead of the sum (~90 s).
    Returns {device_name: (records | None, warning, error, seconds)}.
    """
    from concurrent.futures import ThreadPoolExecutor

    jobs = [(m.device_name, bulk_read_cfg(m)) for m in machines]

    def work(job):
        name, cfg = job
        started = _time.time()
        try:
            records, warning = read_attendance(cfg, name, clear_after=clear_after)
            return name, (records, warning, None, round(_time.time() - started, 1))
        except Exception as e:
            return name, (None, None, e, round(_time.time() - started, 1))

    if not jobs:
        return {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return dict(pool.map(work, jobs))


def _insert_machine(machine, records, cursor, settings, dry_run):
    """Phase 3 (main thread): pick the new punches of one machine and insert them, oldest first."""
    row = {"machine": machine.device_name, "ok": True, "error": None, "deferred": None,
           "read": len(records), "new": 0, "processed": 0, "skipped": 0, "skipped_no_employee": 0,
           "errors": 0, "cursor": str(cursor) if cursor else None}
    selected, dropped = select_new_records(
        records, lower_bound(cursor, settings.import_start_date), now_datetime())
    row.update(dropped)
    row["new"] = len(selected)
    if dry_run:
        return row

    for rec in selected:
        # guards; the cursor stays at the last inserted punch, the rest come next cycle
        if row["processed"] >= MAX_INSERTS_PER_MACHINE:
            row["deferred"] = "insert cap"
            break
        if row["processed"] and row["processed"] % 25 == 0 and _recalc_queue_busy():
            row["deferred"] = "queue short busy"
            break
        status, msg = _add_checkin(str(rec.user_id).strip(), rec.timestamp, machine.device_name)
        if status == "error" and (msg or "").startswith(QUEUE_OVERLOADED_MARK):
            row["deferred"] = "queue short full"
            break
        if status == "error":
            row["errors"] += 1
            row["ok"] = False
            row["error"] = f"User ID {rec.user_id} at {rec.timestamp}: {msg}"
            break  # retry next cycle; the cursor stays before this punch
        row[status] += 1
    return row


def _run_device_log_sync(dry_run=False, ignore_peak=False):
    """Pull every enabled attendance machine once. `dry_run=1` only reports
    (cursor, logs read, new punches) — nothing inserted, nothing cleared, no email.
    Peak windows apply to dry runs too unless `ignore_peak=1` (reading still locks the machine).

    Phase 1 (main thread): peak / queue checks, cursor of each machine.
    Phase 2 (threads):     read all machines in parallel.
    Phase 3 (main thread): insert, machine by machine.
    """
    dry_run, ignore_peak = cint(dry_run), cint(ignore_peak)
    settings = frappe.get_single(SETTING)
    if not dry_run and not settings.auto_sync_logs:
        return []

    logger = _logger()
    prefix = "[dry-run] " if dry_run else ""
    machines = [frappe._dict(m) for m in get_machines(enabled_only=True)]
    now = now_datetime()

    # Phase 1. Reading locks every machine at once, so do not START a read inside
    # a peak window nor right before one (PEAK_START_MARGIN covers the slowest read).
    stop_reason = None
    if not ignore_peak and (in_peak(settings, now) or in_peak(settings, now + PEAK_START_MARGIN)):
        stop_reason = "peak window"
    elif not dry_run and _recalc_queue_busy():
        stop_reason = "queue short busy"
    if stop_reason:
        report = [{"machine": m.device_name, "ok": True, "skip_reason": stop_reason} for m in machines]
        for row in report:
            logger.info(prefix + _format_row(row))
        return report
    cursors = {m.device_name: _cursor(m.device_name) for m in machines}

    # Phase 2
    reads = _read_all(machines, clear_after=bool(settings.clear_from_device_on_fetch) and not dry_run)

    # Phase 3
    report, errors = [], []
    stop_reason = None
    for machine in machines:
        name = machine.device_name
        records, warning, err, seconds = reads[name]
        fail_key = FAIL_KEY.format(name)
        if err is not None:
            row = {"machine": name, "ok": False, "error": str(err), "seconds": seconds}
            if not dry_run:
                fails = cint(frappe.cache().get_value(fail_key)) + 1
                frappe.cache().set_value(fail_key, fails, expires_in_sec=24 * 3600)
                row["consecutive_failures"] = fails
                if fails >= OFFLINE_ALERT_AFTER:
                    errors.append(row)
                if fails == OFFLINE_ALERT_AFTER:
                    frappe.log_error(title=f"Attendance log pull: {name}",
                                     message=f"{fails} consecutive failures\n\n{err}")
        else:
            if not stop_reason and not dry_run and _recalc_queue_busy():
                stop_reason = "queue short busy"
            if stop_reason:
                row = {"machine": name, "ok": True, "skip_reason": stop_reason}
            else:
                row = _insert_machine(machine, records, cursors[name], settings, dry_run)
                row["seconds"] = seconds
                if not dry_run:
                    frappe.cache().delete_value(fail_key)
                if row["errors"]:
                    errors.append(row)
                    frappe.log_error(title=f"Attendance log pull: {name}", message=row["error"])
            if warning:
                # the machine may stay locked (no punches) until someone restarts it
                row["ok"] = False
                row["error"] = "; ".join(x for x in (row.get("error"), warning) if x)
                errors.append(row)
                frappe.log_error(title=f"Attendance log pull: {name}", message=warning)
        report.append(row)
        logger.info(prefix + _format_row(row))

    if not dry_run:
        finished = str(now_datetime())
        frappe.cache().set_value(HEARTBEAT_KEY, finished)
        frappe.cache().set_value(LAST_REPORT_KEY, {"finished": finished, "rows": report})
    if errors and not dry_run:
        _send_error_email(settings, errors)
    return report


def check_heartbeat():
    """Cron */15: alert when no cycle has READ the machines for STALE_AFTER outside peaks.

    The pull job only reports what it sees; if it never runs (worker "biometric" dead,
    a stuck deduplicated job, queue "short" busy for hours, a crash before reading)
    nobody would know. Not covered: the scheduler itself being down (this cron runs
    on it too). Error Log once per stall, email per Setting cooldown while it lasts.
    """
    settings = frappe.get_cached_doc(SETTING)
    if not cint(settings.auto_sync_logs):
        # off on purpose: forget the last cycle so switching back on is not a "stall"
        frappe.cache().delete_value([HEARTBEAT_KEY, HEARTBEAT_ALERT_KEY])
        return
    now = now_datetime()
    last = frappe.cache().get_value(HEARTBEAT_KEY)
    if not last:
        # just deployed / re-enabled / redis flushed: start counting from now
        frappe.cache().set_value(HEARTBEAT_KEY, str(now))
        return
    last = get_datetime(last)
    idle = (now - last) - peak_overlap(settings, last, now)
    if idle <= STALE_AFTER:
        frappe.cache().delete_value(HEARTBEAT_ALERT_KEY)
        return

    message = _("No automatic log pull has read the machines since {0} ({1} minutes, peak windows "
                "excluded). Check the 'biometric' worker, queue 'short' and the scheduler.").format(
        last.strftime("%d/%m %H:%M"), int(idle.total_seconds() // 60))
    _logger().info(f"STALLED: {message}")
    if not frappe.cache().get_value(HEARTBEAT_ALERT_KEY):
        frappe.log_error(title="Attendance log pull stalled", message=message)
        frappe.cache().set_value(HEARTBEAT_ALERT_KEY, 1)
    _send_error_email(settings, [{"machine": _("All machines"), "error": message}])


def _format_row(row):
    # "skipped" = duplicates count; "skip_reason" = the machine was not processed (peak, queue busy)
    if row.get("skip_reason"):
        return f"{row['machine']}: skipped ({row['skip_reason']})"
    if row.get("read") is None:
        return f"{row['machine']}: FAILED ({row.get('consecutive_failures', 1)}x, {row.get('seconds')}s) {row['error']}"
    return (f"{row['machine']}: cursor={row['cursor']} read={row['read']} new={row['new']} "
            f"inserted={row['processed']} dup={row['skipped']} no_employee={row['skipped_no_employee']} "
            f"errors={row['errors']} junk={row['junk']} future={row['future']} {row['seconds']}s"
            + (f" deferred={row['deferred']}" if row.get("deferred") else "")
            + (f" — {row['error']}" if row.get("error") else ""))


def _send_error_email(settings, errors):
    """Attendance Machine Setting -> Error Email. Off by default, no recipients by default."""
    if not settings.send_error_email:
        return
    recipients = [e.strip(",; ") for e in (settings.error_email_recipients or "").split() if e.strip(",; ")]
    if not recipients:
        return
    cooldown_s = max(cint(settings.error_email_cooldown_minutes) or 30, 1) * 60
    last = frappe.cache().get_value(LAST_EMAIL_KEY)
    if last and _time.time() - float(last) < cooldown_s:
        return

    rows = "".join(
        f"<tr><td>{frappe.utils.escape_html(r['machine'])}</td>"
        f"<td>{frappe.utils.escape_html(r.get('error') or '')}</td></tr>"
        for r in errors
    )
    frappe.sendmail(
        recipients=recipients,
        subject=_("Attendance log pull: {0} machine(s) with errors").format(len(errors)),
        message=(
            f"<p>{_('Time')}: {now_datetime().strftime('%Y-%m-%d %H:%M:%S')}</p>"
            f"<table border='1' cellpadding='4' cellspacing='0'>"
            f"<tr><th>{_('Machine')}</th><th>{_('Error')}</th></tr>{rows}</table>"
            f"<p>{_('Details')}: Error Log, logs/biometric_device_sync.log</p>"
        ),
    )
    frappe.cache().set_value(LAST_EMAIL_KEY, _time.time(), expires_in_sec=cooldown_s)
