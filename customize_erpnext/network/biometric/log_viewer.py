"""
API for the biometric-sync page, Tab 1 (Log Viewer).

- get_sync_status: status table of the automatic log pull — last cycle per machine
  (stored by device_log_sync at the end of each cycle), latest checkin in ERP,
  peak window, stall state, last MongoDB run. No log parsing except the 2 Mongo lines.
- get_log_files / get_log_content: raw view of the 2 site logs only. The retired
  sync tool's 18 log files stay on disk but are no longer listed (23/10/2026).
  Only names from LOG_FILES can be read — no path from the client.
"""

import os

import frappe
from frappe.utils import get_datetime, now_datetime

from customize_erpnext.network.biometric.auth import check_biometric_access

LOG_FILES = {
    "biometric_device_sync.log": "Device log sync",
    "biometric_mongodb_sync.log": "MongoDB sync",
}
MAX_READ_BYTES = 4 * 1024 * 1024
MAX_LINES = 500


def _log_path(name):
    return os.path.join(frappe.get_site_path("logs"), name)


def _tail_lines(path, max_lines):
    """Last `max_lines` non-empty lines, newest first."""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(max(0, size - MAX_READ_BYTES))
        text = f.read().decode("utf-8", errors="ignore")
    lines = [line for line in text.split("\n") if line.strip()]
    if size > MAX_READ_BYTES and lines:
        lines = lines[1:]  # partial first line
    return lines[-max_lines:][::-1]


def _strip_prefix(line, logger_name):
    """'2026-10-23 18:00:05,123 INFO biometric_mongodb_sync <msg>' -> ('2026-10-23 18:00:05', '<msg>')."""
    head, sep, msg = line.partition(f" {logger_name} ")
    return (head[:19], msg) if sep else (None, line)


@frappe.whitelist()
def get_sync_status():
    check_biometric_access()
    from customize_erpnext.network.biometric import device_log_sync as dls
    from customize_erpnext.network.biometric.machines import get_machines

    settings = frappe.get_cached_doc(dls.SETTING)
    now = now_datetime()

    last = frappe.cache().get_value(dls.HEARTBEAT_KEY)
    idle_minutes, stalled = None, False
    if last:
        last_dt = get_datetime(last)
        idle = (now - last_dt) - dls.peak_overlap(settings, last_dt, now)
        idle_minutes = int(idle.total_seconds() // 60)
        stalled = bool(settings.auto_sync_logs) and idle > dls.STALE_AFTER

    peak = dls.current_peak(settings, now)
    next_peak = next(((s, e) for s, e in dls.peak_intervals(settings, now.date()) if s > now), None)

    report = frappe.cache().get_value(dls.LAST_REPORT_KEY) or {}
    rows = {r["machine"]: r for r in report.get("rows") or []}
    machines = []
    for m in get_machines(enabled_only=True):
        name = m["device_name"]
        r = rows.get(name) or {}
        latest = dls._cursor(name)
        machines.append({
            "machine": name,
            "latest_checkin": str(latest) if latest else None,
            "read": r.get("read"),
            "new": r.get("new"),
            "inserted": r.get("processed"),
            "seconds": r.get("seconds"),
            "ok": r.get("ok"),
            "error": r.get("error"),
            "deferred": r.get("deferred"),
            "duplicates": r.get("skipped") if not isinstance(r.get("skipped"), str) else None,
            # cycles stored before 23/10 12:30 used "skipped" for the reason too
            "skip_reason": r.get("skip_reason") or (r.get("skipped") if isinstance(r.get("skipped"), str) else None),
            "consecutive_failures": r.get("consecutive_failures"),
            "in_last_cycle": bool(r),
        })

    mongo = [dict(zip(("at", "text"), _strip_prefix(line, "biometric_mongodb_sync")))
             for line in _tail_lines(_log_path("biometric_mongodb_sync.log"), 2)]

    return {
        "auto_sync_logs": bool(settings.auto_sync_logs),
        "now": str(now),
        "last_cycle": str(last) if last else None,
        "idle_minutes": idle_minutes,
        "stalled": stalled,
        "peak": {"start": peak[0].strftime("%H:%M"), "end": peak[1].strftime("%H:%M")} if peak else None,
        "next_peak": {"start": next_peak[0].strftime("%H:%M"), "end": next_peak[1].strftime("%H:%M")} if next_peak else None,
        "machines": machines,
        "mongo": mongo,
    }


@frappe.whitelist()
def get_log_files():
    check_biometric_access()
    return [{"file": f, "label": label} for f, label in LOG_FILES.items() if os.path.exists(_log_path(f))]


@frappe.whitelist()
def get_log_content(log_file):
    """Last MAX_LINES lines of one LOG_FILES entry, newest first."""
    check_biometric_access()
    if log_file not in LOG_FILES:
        frappe.throw("Unknown log file")
    return {"file": log_file, "lines": _tail_lines(_log_path(log_file), MAX_LINES)}
