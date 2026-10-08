# -*- coding: utf-8 -*-
"""
IT room door access (ZKTeco F21Lite).

The controller speaks the same protocol as the attendance machines, but its
punches are deliberately NOT pushed to Employee Checkin — they are stored in
the "Door Access Log" DocType only, so the attendance engine never sees them.

The device is configured ad hoc from the web UI (IP / port / comm password),
not from Attendance Machine Setting: anything listed there is polled by the
auto-sync service and would turn door punches into attendance.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from customize_erpnext.api.biometric_sync import _build_zk_device
from customize_erpnext.api.biometric_resync import fetch_attendance_from_cfg

DEFAULT_PORT = 4370
DEFAULT_TIMEOUT = 10
DEFAULT_RANGE_DAYS = 30
MAX_ROWS = 5000


def _check_access():
    """Door logs are IT-security data: System Manager only."""
    frappe.only_for("System Manager")


def _door_cfg(ip, port, password):
    """ZK config for the ad-hoc door controller, in the same shape the
    attendance machines use — so the shared connect/fetch helpers apply."""
    return _build_zk_device(frappe._dict({
        "ip_address": (ip or "").strip(),
        "port": port or DEFAULT_PORT,
        "timeout": DEFAULT_TIMEOUT,
        "force_udp": 0,
        "ommit_ping": 1,
        "password": password or 0,
    }))


def _employee_map():
    """attendance_device_id -> (employee, employee_name) for every employee."""
    rows = frappe.get_all(
        "Employee",
        fields=["name", "employee_name", "attendance_device_id"],
        filters={"attendance_device_id": ["is", "set"]},
        limit_page_length=0,
        ignore_permissions=True,
    )
    return {
        str(r.attendance_device_id).strip(): (r.name, r.employee_name)
        for r in rows
        if str(r.attendance_device_id or "").strip()
    }


def _default_range(from_date, to_date):
    to_d = getdate(to_date) if to_date else getdate(now_datetime())
    from_d = getdate(from_date) if from_date else getdate(add_days(to_d, -(DEFAULT_RANGE_DAYS - 1)))
    if from_d > to_d:
        frappe.throw(_("From date is after To date"))
    return from_d, to_d


def store_door_punches(attendances, device_ip, d_from, d_to):
    """Insert the punches in [d_from, d_to] that are not stored yet.

    Shared by the ad-hoc IT door tab (fetch_door_logs) and /door_control.
    Duplicate-safe at three levels: pairs already in the DB, pairs seen earlier
    in this batch, and the (user_id, timestamp) unique index. Never commits.
    """
    in_range = [a for a in attendances if a.timestamp and d_from <= a.timestamp.date() <= d_to]

    # existing (user_id, timestamp) pairs in the range — one query, not one per punch
    existing = {
        (str(r.user_id), get_datetime(r.timestamp))
        for r in frappe.get_all(
            "Door Access Log",
            fields=["user_id", "timestamp"],
            filters={"timestamp": ["between", [f"{d_from} 00:00:00", f"{d_to} 23:59:59"]]},
            limit_page_length=0,
            ignore_permissions=True,
        )
    }
    emp_map = _employee_map()

    counts = {"fetched": len(attendances), "in_range": len(in_range),
              "inserted": 0, "duplicated": 0, "no_employee": 0, "error": 0}
    seen = set()

    for att in in_range:
        user_id = str(att.user_id).strip()
        ts = get_datetime(att.timestamp)
        key = (user_id, ts)
        if key in existing or key in seen:
            counts["duplicated"] += 1
            continue
        seen.add(key)

        employee, employee_name = emp_map.get(user_id, (None, None))
        if not employee:
            counts["no_employee"] += 1

        # savepoint, not a full rollback: a duplicate must not undo the rows
        # already inserted earlier in this same request
        frappe.db.savepoint("door_punch")
        try:
            doc = frappe.get_doc({
                "doctype": "Door Access Log",
                "user_id": user_id,
                "employee": employee,
                "employee_name": employee_name,
                "timestamp": ts,
                "device_ip": device_ip,
            })
            doc.insert(ignore_permissions=True)
            counts["inserted"] += 1
        except frappe.DuplicateEntryError:
            frappe.db.rollback(save_point="door_punch")
            counts["duplicated"] += 1
        except Exception as e:
            frappe.db.rollback(save_point="door_punch")
            counts["error"] += 1
            frappe.log_error(f"Door log insert failed for {user_id} @ {ts}: {e}", "Door Access")

    return counts


@frappe.whitelist()
def fetch_door_logs(ip, port=DEFAULT_PORT, password=0, from_date=None, to_date=None):
    """Read punches from the door controller and store the new ones.

    Duplicate-safe: the device keeps its whole history, so the same range can
    be fetched again and again — rows already stored are skipped.
    """
    _check_access()

    ip = (ip or "").strip()
    if not ip:
        frappe.throw(_("Device IP is required"))
    d_from, d_to = _default_range(from_date, to_date)

    try:
        # same retry + disable/enable/disconnect handling as the machine re-sync
        attendances = fetch_attendance_from_cfg(_door_cfg(ip, port, password), f"door {ip}")
    except Exception as e:
        frappe.log_error(f"fetch_door_logs error: {e}", "Door Access")
        return {"status": "error", "message": str(e)}

    counts = store_door_punches(attendances, ip, d_from, d_to)

    frappe.db.commit()
    counts["status"] = "success"
    counts["from_date"] = str(d_from)
    counts["to_date"] = str(d_to)
    return counts


@frappe.whitelist()
def get_door_logs(from_date=None, to_date=None, keyword=None, limit=500):
    """Stored door logs, newest first. `keyword` matches user id / employee / name."""
    _check_access()

    d_from, d_to = _default_range(from_date, to_date)
    limit = min(int(limit or 500), MAX_ROWS)

    conditions = ["timestamp between %(from)s and %(to)s"]
    values = {"from": f"{d_from} 00:00:00", "to": f"{d_to} 23:59:59", "limit": limit}

    keyword = (keyword or "").strip()
    if keyword:
        conditions.append(
            "(user_id like %(kw)s or ifnull(employee, '') like %(kw)s"
            " or ifnull(employee_name, '') like %(kw)s or ifnull(note, '') like %(kw)s)"
        )
        values["kw"] = f"%{keyword}%"

    where = " and ".join(conditions)

    total = frappe.db.sql(
        f"select count(*) from `tabDoor Access Log` where {where}", values
    )[0][0]

    rows = frappe.db.sql(
        f"""
        select name, user_id, employee, employee_name, timestamp, device_ip, note
        from `tabDoor Access Log`
        where {where}
        order by timestamp desc
        limit %(limit)s
        """,
        values,
        as_dict=True,
    )

    return {
        "status": "success",
        "rows": rows,
        "total": total,
        "shown": len(rows),
        "from_date": str(d_from),
        "to_date": str(d_to),
    }


@frappe.whitelist()
def update_note(name, note=None):
    """Edit the note of one log row from the web page."""
    _check_access()
    frappe.db.set_value("Door Access Log", name, "note", (note or "").strip())
    frappe.db.commit()
    return {"status": "success"}
