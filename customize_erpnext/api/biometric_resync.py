#!/usr/bin/env python3
"""
Manual re-sync operations for the /biometric_sync page ("Manual Re-sync" tab).

Ported from the standalone biometric-attendance-sync-tool manual menu
(erpnext_re_sync_all.py). Running inside Frappe replaces the tool's REST +
API-key calls with direct function/ORM calls, and does NOT touch the tool's
own state files (status.json cursors, MongoDB watermark) — duplicates are
rejected by ERPNext so the two can coexist.

Jobs reuse the biometric_sync cache format (biometric_sync:{job_id}) so the
page polls them through the existing get_sync_job_status + pollJobStatus().
"""

import json
import time
import uuid
from datetime import datetime, timezone

import frappe
from customize_erpnext.api.biometric_auth import check_biometric_access

MONGO_TIMEOUT_MS = 10000
CONNECT_RETRIES = 3          # device may be briefly locked by the auto sync service
CONNECT_RETRY_DELAY_S = 5


# ---------------------------------------------------------------------------
# Shared job helpers (cache format identical to biometric_sync._run_sync_job)
# ---------------------------------------------------------------------------

def _new_job(prefix, total_count=0):
    job_id = f"{prefix}_{uuid.uuid4().hex[:12]}"
    cache_key = f"biometric_sync:{job_id}"
    frappe.cache().set_value(cache_key, {
        "status": "queued",
        "phase": "Queued...",
        "progress_pct": 0,
        "results": [],
        "done_count": 0,
        "total_count": total_count,
        "error": None,
    }, expires_in_sec=3600)
    return job_id, cache_key


def _update_cache(cache_key, patch):
    state = frappe.cache().get_value(cache_key)
    if state:
        state.update(patch)
        frappe.cache().set_value(cache_key, state, expires_in_sec=3600)


def _append_result(cache_key, success, label, machine, message):
    state = frappe.cache().get_value(cache_key)
    if state:
        state["results"].append({
            "success": success,
            "user_id": label,
            "machine": machine,
            "message": message,
        })
        frappe.cache().set_value(cache_key, state, expires_in_sec=3600)


def _parse_date(value, param):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        frappe.throw(f"Invalid {param}: {value} (expected YYYY-MM-DD)")


def _add_checkin(employee_field_value, timestamp, device_id):
    """Insert one Employee Checkin via the hrms function the tool used over REST.

    Returns (status, message): processed | skipped (duplicate) |
    skipped_no_employee | error. Commits on success, rolls back on failure so
    each punch behaves like the tool's one-REST-call-per-punch transactions.

    IMPORTANT: hrms validate_duplicate_log matches employee+time+log_type, and
    log_type is assigned by overrides AFTER that check — re-inserting an old
    punch can get a different log_type and slip past it (verified in prod).
    So we check employee+time ourselves first to make re-sync truly idempotent.
    """
    from hrms.hr.doctype.employee_checkin.employee_checkin import add_log_based_on_employee_field

    employee = frappe.db.get_value(
        "Employee", {"attendance_device_id": str(employee_field_value)}, "name")
    if not employee:
        return "skipped_no_employee", f"No Employee for attendance_device_id {employee_field_value}"
    if frappe.db.exists("Employee Checkin", {"employee": employee, "time": timestamp}):
        return "skipped", None

    try:
        add_log_based_on_employee_field(
            employee_field_value=str(employee_field_value),
            timestamp=timestamp,
            device_id=device_id,
            log_type=None,
        )
        frappe.db.commit()
        return "processed", None
    except Exception as e:
        frappe.db.rollback()
        msg = str(e)
        if "already has a log with the same timestamp" in msg:
            return "skipped", None
        if "No Employee found" in msg or "Inactive Employee" in msg:
            return "skipped_no_employee", msg
        return "error", msg


# ---------------------------------------------------------------------------
# 1. Re-sync Device -> ERPNext (date range)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def resync_device_logs(machine_names_json, from_date, to_date):
    """Enqueue re-sync of attendance logs from selected machines for a date range."""
    check_biometric_access()
    try:
        machine_names = json.loads(machine_names_json)
        if not machine_names:
            frappe.throw("No machines selected")
        d_from = _parse_date(from_date, "from_date")
        d_to = _parse_date(to_date, "to_date")
        if d_from > d_to:
            frappe.throw("from_date is after to_date")

        job_id, cache_key = _new_job("dev_resync", total_count=len(machine_names))
        frappe.enqueue(
            "customize_erpnext.api.biometric_resync._run_device_resync_job",
            queue="default",
            timeout=3600,
            machine_names=machine_names,
            from_date=str(d_from),
            to_date=str(d_to),
            cache_key=cache_key,
        )
        return {"status": "success", "job_id": job_id}
    except Exception as e:
        frappe.log_error(f"resync_device_logs error: {e}")
        return {"status": "error", "message": str(e)}


def _fetch_device_attendance(machine_name):
    """Read all attendance logs from one machine (device re-enabled in finally)."""
    from customize_erpnext.api.biometric_sync import _get_machine_doc, _build_zk_device, _connect_zk

    doc = _get_machine_doc(machine_name)
    cfg = _build_zk_device(doc)

    conn = None
    last_err = None
    for _attempt in range(CONNECT_RETRIES):
        try:
            conn = _connect_zk(cfg)
            break
        except Exception as e:
            # the auto sync service polls devices every few minutes and may hold them briefly
            last_err = e
            time.sleep(CONNECT_RETRY_DELAY_S)
    if conn is None:
        raise ConnectionError(f"Cannot connect to {machine_name} after {CONNECT_RETRIES} attempts: {last_err}")

    try:
        conn.disable_device()
        return conn.get_attendance()
    finally:
        try:
            conn.enable_device()
        except Exception:
            frappe.log_error(f"Failed to re-enable device {machine_name}")
        conn.disconnect()


def _run_device_resync_job(machine_names, from_date, to_date, cache_key):
    d_from = datetime.strptime(from_date, "%Y-%m-%d").date()
    d_to = datetime.strptime(to_date, "%Y-%m-%d").date()

    counts = {"processed": 0, "skipped": 0, "skipped_no_employee": 0, "error": 0}
    done_machines = 0
    try:
        for machine_name in machine_names:
            _update_cache(cache_key, {
                "status": "running",
                "phase": f"Reading logs from {machine_name}...",
            })
            try:
                attendances = _fetch_device_attendance(machine_name)
            except Exception as e:
                _append_result(cache_key, False, "-", machine_name, f"Device read failed: {e}")
                counts["error"] += 1
                done_machines += 1
                continue

            in_range = [a for a in attendances if d_from <= a.timestamp.date() <= d_to]
            _append_result(cache_key, True, "-", machine_name,
                           f"Fetched {len(attendances)} logs, {len(in_range)} in range {from_date}..{to_date}")

            for i, att in enumerate(in_range):
                status, msg = _add_checkin(att.user_id, att.timestamp, machine_name)
                counts[status] += 1
                if status == "error":
                    _append_result(cache_key, False, str(att.user_id), machine_name,
                                   f"{att.timestamp}: {msg}")
                if i % 50 == 0:
                    machine_pct = int(i / max(len(in_range), 1) * 100)
                    overall = int((done_machines + i / max(len(in_range), 1)) / len(machine_names) * 100)
                    _update_cache(cache_key, {
                        "phase": f"{machine_name}: {i}/{len(in_range)} punches ({machine_pct}%)",
                        "progress_pct": overall,
                    })

            done_machines += 1
            _append_result(cache_key, True, "-", machine_name,
                           f"Done: {counts['processed']} new, {counts['skipped']} duplicate, "
                           f"{counts['skipped_no_employee']} no-employee, {counts['error']} errors (running totals)")
            _update_cache(cache_key, {
                "done_count": done_machines,
                "progress_pct": int(done_machines / len(machine_names) * 100),
            })

        _update_cache(cache_key, {
            "status": "done",
            "progress_pct": 100,
            "phase": f"Complete: {counts['processed']} new checkins, {counts['skipped']} duplicates, "
                     f"{counts['skipped_no_employee']} no-employee, {counts['error']} errors",
        })
    except Exception as e:
        frappe.log_error(f"_run_device_resync_job failed: {e}")
        _update_cache(cache_key, {"status": "error", "error": str(e), "phase": f"Error: {e}"})


# ---------------------------------------------------------------------------
# 2. Re-sync MongoDB -> ERPNext (date range)
# ---------------------------------------------------------------------------

def _get_mongo():
    from pymongo import MongoClient
    host = frappe.conf.get("biometric_mongodb_host", "10.0.1.4")
    port = int(frappe.conf.get("biometric_mongodb_port", 27017))
    dbname = frappe.conf.get("biometric_mongodb_database", "tiqn")
    client = MongoClient(host=host, port=port, serverSelectionTimeoutMS=MONGO_TIMEOUT_MS)
    client.admin.command("ping")
    return client, client[dbname]


def _map_machine_no(machine_no):
    return f"Machine {machine_no}" if isinstance(machine_no, int) and 1 <= machine_no <= 7 else None


@frappe.whitelist()
def resync_mongodb_logs(from_date, to_date):
    """Enqueue re-sync of attendance checkins from MongoDB AttLog for a date range."""
    check_biometric_access()
    try:
        d_from = _parse_date(from_date, "from_date")
        d_to = _parse_date(to_date, "to_date")
        if d_from > d_to:
            frappe.throw("from_date is after to_date")

        job_id, cache_key = _new_job("mongo_resync")
        frappe.enqueue(
            "customize_erpnext.api.biometric_resync._run_mongodb_resync_job",
            queue="default",
            timeout=3600,
            from_date=str(d_from),
            to_date=str(d_to),
            cache_key=cache_key,
        )
        return {"status": "success", "job_id": job_id}
    except Exception as e:
        frappe.log_error(f"resync_mongodb_logs error: {e}")
        return {"status": "error", "message": str(e)}


def _run_mongodb_resync_job(from_date, to_date, cache_key):
    try:
        _update_cache(cache_key, {"status": "running", "phase": "Connecting to MongoDB..."})
        client, db = _get_mongo()
        collection = db[frappe.conf.get("biometric_mongodb_attlog_collection", "AttLog")]

        # NOTE: this MongoDB stores local wall-clock time labeled as UTC, so UTC
        # boundaries align with local days — do NOT convert to +07 here.
        start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

        query = {"timestamp": {"$gte": start, "$lte": end}}
        if int(frappe.conf.get("biometric_sync_only_machine0", 1)):
            query["machineNo"] = 0

        records = list(collection.find(query, {"attFingerId": 1, "timestamp": 1, "machineNo": 1}))
        client.close()
        total = len(records)
        _update_cache(cache_key, {"total_count": total, "phase": f"Processing {total} records..."})

        counts = {"processed": 0, "skipped": 0, "skipped_no_employee": 0, "error": 0}
        for i, rec in enumerate(records):
            att_id = rec.get("attFingerId")
            ts = rec.get("timestamp")
            if not att_id or not ts:
                counts["skipped"] += 1
                continue
            status, msg = _add_checkin(att_id, ts, _map_machine_no(rec.get("machineNo", 0)))
            counts[status] += 1
            if status == "error":
                _append_result(cache_key, False, str(att_id), "MongoDB", f"{ts}: {msg}")
            if i % 50 == 0:
                _update_cache(cache_key, {
                    "done_count": i,
                    "progress_pct": int(i / max(total, 1) * 100),
                    "phase": f"Processing {i}/{total} records...",
                })

        _update_cache(cache_key, {
            "status": "done",
            "done_count": total,
            "progress_pct": 100,
            "phase": f"Complete: {counts['processed']} new checkins, {counts['skipped']} duplicates, "
                     f"{counts['skipped_no_employee']} no-employee, {counts['error']} errors",
        })
    except Exception as e:
        frappe.log_error(f"_run_mongodb_resync_job failed: {e}")
        _update_cache(cache_key, {"status": "error", "error": str(e), "phase": f"Error: {e}"})


# ---------------------------------------------------------------------------
# 3. Sync OT MongoDB -> ERPNext (from a start date)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def sync_ot_from_mongodb(from_date, to_date=None):
    """Enqueue OT sync from MongoDB OtRegister (from_date <= otDate <= to_date).

    to_date is optional for backward compatibility: empty means no upper bound
    (same behaviour as the original "start date only" mode).
    """
    check_biometric_access()
    try:
        d_from = _parse_date(from_date, "from_date")
        d_to = _parse_date(to_date, "to_date") if to_date else None
        if d_to and d_from > d_to:
            frappe.throw("from_date is after to_date")

        job_id, cache_key = _new_job("ot_sync")
        frappe.enqueue(
            "customize_erpnext.api.biometric_resync._run_ot_sync_job",
            queue="default",
            timeout=3600,
            from_date=str(d_from),
            to_date=str(d_to) if d_to else None,
            cache_key=cache_key,
        )
        return {"status": "success", "job_id": job_id}
    except Exception as e:
        frappe.log_error(f"sync_ot_from_mongodb error: {e}")
        return {"status": "error", "message": str(e)}


def _normalize_time(value, default):
    value = str(value or default)
    return value + ":00" if len(value) == 5 else value


def _employee_has_ot(emp_id, ot_date, begin_time, end_time):
    """Same conflict rule as the CLI tool: identical employee/date/begin/end."""
    existing = frappe.get_all(
        "Overtime Registration Detail",
        filters={"employee": emp_id, "date": ot_date},
        fields=["begin_time", "end_time"],
    )
    return any(str(row.begin_time) == begin_time and str(row.end_time) == end_time for row in existing)


def _run_ot_sync_job(from_date, cache_key, to_date=None):
    try:
        _update_cache(cache_key, {"status": "running", "phase": "Connecting to MongoDB..."})
        client, db = _get_mongo()
        collection = db[frappe.conf.get("biometric_mongodb_ot_collection", "OtRegister")]

        start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        ot_filter = {"$gte": start}
        if to_date:
            ot_filter["$lte"] = datetime.strptime(to_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc)
        records = list(collection.find({"otDate": ot_filter}))
        client.close()

        # Dedup identical rows then group by requestNo (same as CLI tool)
        seen = set()
        grouped = {}
        for rec in records:
            key = (str(rec.get("otDate")), str(rec.get("empId")),
                   str(rec.get("otTimeBegin")), str(rec.get("otTimeEnd")))
            if key in seen:
                continue
            seen.add(key)
            request_no = rec.get("requestNo")
            if request_no:
                grouped.setdefault(str(request_no), []).append(rec)

        total = len(grouped)
        _update_cache(cache_key, {"total_count": total, "phase": f"Processing {total} OT requests..."})

        created = skipped = failed = 0
        for i, (request_no, recs) in enumerate(sorted(grouped.items())):
            try:
                if frappe.get_all("Overtime Registration",
                                  filters=[["reason_general", "like", f"%Request number: {request_no}%"]],
                                  limit=1):
                    skipped += 1
                    continue

                first = recs[0]
                request_date_raw = first.get("requestDate")
                request_date = (request_date_raw.strftime("%Y-%m-%d")
                                if isinstance(request_date_raw, datetime)
                                else datetime.now().strftime("%Y-%m-%d"))

                ot_employees = []
                for rec in recs:
                    ot_date_raw = rec.get("otDate")
                    emp_id = rec.get("empId")
                    if not isinstance(ot_date_raw, datetime) or not emp_id:
                        continue
                    ot_date = ot_date_raw.strftime("%Y-%m-%d")
                    begin_time = _normalize_time(rec.get("otTimeBegin"), "17:00")
                    end_time = _normalize_time(rec.get("otTimeEnd"), "19:00")
                    if _employee_has_ot(emp_id, ot_date, begin_time, end_time):
                        continue
                    ot_employees.append({
                        "employee": emp_id,
                        "date": ot_date,
                        "begin_time": begin_time,
                        "end_time": end_time,
                    })

                if not ot_employees:
                    skipped += 1
                    _append_result(cache_key, True, request_no, "OT",
                                   "Skipped: all employees already have this OT")
                    continue

                doc = frappe.get_doc({
                    "doctype": "Overtime Registration",
                    "reason_general": f"Sync from MongoDB: Request number: {request_no}",
                    "request_date": request_date,
                    "ot_employees": ot_employees,
                })
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                created += 1
                _append_result(cache_key, True, request_no, "OT",
                               f"Created with {len(ot_employees)} employee(s)")
            except Exception as e:
                frappe.db.rollback()
                failed += 1
                _append_result(cache_key, False, request_no, "OT", str(e))

            if i % 10 == 0:
                _update_cache(cache_key, {
                    "done_count": i,
                    "progress_pct": int(i / max(total, 1) * 100),
                })

        _update_cache(cache_key, {
            "status": "done",
            "done_count": total,
            "progress_pct": 100,
            "phase": f"Complete: {created} created, {skipped} skipped, {failed} failed (of {total} requests)",
        })
    except Exception as e:
        frappe.log_error(f"_run_ot_sync_job failed: {e}")
        _update_cache(cache_key, {"status": "error", "error": str(e), "phase": f"Error: {e}"})


# ---------------------------------------------------------------------------
# 4. Delete OT (System Manager only, preview + typed confirmation)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def preview_delete_ot(from_date, to_date):
    """Dry-run: count OT detail rows in range and affected parents. Read-only."""
    check_biometric_access()
    frappe.only_for("System Manager")

    d_from = _parse_date(from_date, "from_date")
    d_to = _parse_date(to_date, "to_date")
    if d_from > d_to:
        frappe.throw("from_date is after to_date")

    filters = {"date": ["between", [str(d_from), str(d_to)]]}
    detail_count = frappe.db.count("Overtime Registration Detail", filters)
    parents = frappe.get_all("Overtime Registration Detail", filters=filters,
                             distinct=True, pluck="parent")
    sample = frappe.get_all("Overtime Registration Detail", filters=filters,
                            fields=["parent", "employee", "employee_name", "date", "begin_time", "end_time"],
                            order_by="date", limit=20)
    for row in sample:
        row["date"] = str(row["date"])
        row["begin_time"] = str(row["begin_time"])
        row["end_time"] = str(row["end_time"])
    return {
        "status": "success",
        "detail_count": detail_count,
        "parent_count": len(parents),
        "sample": sample,
    }


@frappe.whitelist()
def delete_ot(from_date, to_date, confirm_text):
    """Delete OT detail rows in range via the ORM (System Manager + typed DELETE)."""
    check_biometric_access()
    frappe.only_for("System Manager")

    if confirm_text != "DELETE":
        frappe.throw("Confirmation text mismatch — type DELETE (uppercase) to proceed")

    d_from = _parse_date(from_date, "from_date")
    d_to = _parse_date(to_date, "to_date")
    if d_from > d_to:
        frappe.throw("from_date is after to_date")

    try:
        parents = frappe.get_all(
            "Overtime Registration Detail",
            filters={"date": ["between", [str(d_from), str(d_to)]]},
            distinct=True, pluck="parent",
        )
        job_id, cache_key = _new_job("ot_delete", total_count=len(parents))
        frappe.enqueue(
            "customize_erpnext.api.biometric_resync._run_delete_ot_job",
            queue="default",
            timeout=3600,
            from_date=str(d_from),
            to_date=str(d_to),
            cache_key=cache_key,
        )
        return {"status": "success", "job_id": job_id}
    except Exception as e:
        frappe.log_error(f"delete_ot error: {e}")
        return {"status": "error", "message": str(e)}


def _run_delete_ot_job(from_date, to_date, cache_key):
    from frappe.utils import getdate
    d_from, d_to = getdate(from_date), getdate(to_date)

    try:
        parents = frappe.get_all(
            "Overtime Registration Detail",
            filters={"date": ["between", [from_date, to_date]]},
            distinct=True, pluck="parent",
        )
        total = len(parents)
        _update_cache(cache_key, {"status": "running", "total_count": total,
                                  "phase": f"Deleting OT in {total} registrations..."})

        deleted_docs = trimmed_docs = skipped_docs = 0
        removed_rows = 0
        for i, parent in enumerate(parents):
            try:
                doc = frappe.get_doc("Overtime Registration", parent)
                keep = [d for d in doc.ot_employees if not (d_from <= getdate(d.date) <= d_to)]
                remove_count = len(doc.ot_employees) - len(keep)

                if not keep:
                    # whole registration falls in range -> delete the document
                    if doc.docstatus == 1:
                        doc.cancel()
                    frappe.delete_doc("Overtime Registration", parent, ignore_permissions=True)
                    deleted_docs += 1
                    _append_result(cache_key, True, parent, "OT", f"Deleted ({remove_count} rows)")
                elif doc.docstatus == 0:
                    doc.ot_employees = keep
                    doc.save(ignore_permissions=True)
                    trimmed_docs += 1
                    _append_result(cache_key, True, parent, "OT",
                                   f"Removed {remove_count} rows, kept {len(keep)}")
                else:
                    # submitted doc with rows outside the range: partial edit is not
                    # allowed on submitted docs — surface it instead of forcing raw SQL
                    skipped_docs += 1
                    _append_result(cache_key, False, parent, "OT",
                                   f"SKIPPED: submitted doc has {len(keep)} rows outside range — cancel/amend manually")
                    continue
                removed_rows += remove_count
                frappe.db.commit()
            except Exception as e:
                frappe.db.rollback()
                _append_result(cache_key, False, parent, "OT", str(e))

            if i % 10 == 0:
                _update_cache(cache_key, {"done_count": i,
                                          "progress_pct": int(i / max(total, 1) * 100)})

        _update_cache(cache_key, {
            "status": "done",
            "done_count": total,
            "progress_pct": 100,
            "phase": f"Complete: {removed_rows} rows removed — {deleted_docs} registrations deleted, "
                     f"{trimmed_docs} trimmed, {skipped_docs} skipped (submitted)",
        })
    except Exception as e:
        frappe.log_error(f"_run_delete_ot_job failed: {e}")
        _update_cache(cache_key, {"status": "error", "error": str(e), "phase": f"Error: {e}"})
