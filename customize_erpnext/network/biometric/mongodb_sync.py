"""MongoDB (legacy attendance system) -> ERPNext: AttLog punches and OtRegister OT.

Temporary (23/10/2026): kept until OT is registered directly in ERPNext.
- Manual: biometric-sync page, Tab 6 (date range).
- Automatic: hooks cron 0 18 * * * -> run_daily_mongodb_sync (last 30 days).
Re-scanning is safe: duplicates are skipped (_add_checkin / Request number check).
⚠ A record edited in place in MongoDB (same _id, new time) adds the new punch
but never removes the old one already synced.
Connection: site_config keys biometric_mongodb_* and biometric_sync_only_machine0.
"""

import logging
from datetime import datetime, timezone

import frappe

from customize_erpnext.network.biometric.auth import check_biometric_access
from customize_erpnext.network.biometric.resync import (
    _add_checkin,
    _append_result,
    _new_job,
    _parse_date,
    _update_cache,
)

MONGO_TIMEOUT_MS = 10000


# ---------------------------------------------------------------------------
# 1. Re-sync MongoDB -> ERPNext (date range)
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
            "customize_erpnext.network.biometric.mongodb_sync._run_mongodb_resync_job",
            queue="long",   # minutes-long: keep the short worker free for scheduler jobs
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
# 2. Sync OT MongoDB -> ERPNext (from a start date)
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
            "customize_erpnext.network.biometric.mongodb_sync._run_ot_sync_job",
            queue="long",   # minutes-long: keep the short worker free for scheduler jobs
            timeout=3600,
            from_date=str(d_from),
            to_date=str(d_to) if d_to else None,
            cache_key=cache_key,
            fill_missing_rows=True,
        )
        return {"status": "success", "job_id": job_id}
    except Exception as e:
        frappe.log_error(f"sync_ot_from_mongodb error: {e}")
        return {"status": "error", "message": str(e)}


def _normalize_time(value, default):
    value = str(value or default)
    return value + ":00" if len(value) == 5 else value


def _hms(value):
    # DB times come back as timedelta: str() is "7:00:00", not "07:00:00"
    parts = [int(float(p)) for p in str(value).split(":")] + [0, 0]
    return "%02d:%02d:%02d" % tuple(parts[:3])


def _employee_has_ot(emp_id, ot_date, begin_time, end_time):
    """Same conflict rule as the CLI tool: identical employee/date/begin/end."""
    existing = frappe.get_all(
        "Overtime Registration Detail",
        filters={"employee": emp_id, "date": ot_date},
        fields=["begin_time", "end_time"],
    )
    begin_time, end_time = _hms(begin_time), _hms(end_time)
    return any(_hms(row.begin_time) == begin_time and _hms(row.end_time) == end_time for row in existing)


def _existing_ot_keys(date_from, date_to):
    """{(employee, date, begin, end)} already in ERPNext — row-level dedup of fill mode.
    Orphan rows (parent registration gone) do not count."""
    rows = frappe.db.sql("""
        SELECT d.employee, d.date, d.begin_time, d.end_time
        FROM `tabOvertime Registration Detail` d
        JOIN `tabOvertime Registration` p ON p.name = d.parent
        WHERE d.date BETWEEN %(date_from)s AND %(date_to)s
    """, {"date_from": date_from, "date_to": date_to}, as_dict=1)
    return {(r.employee, str(r.date), _hms(r.begin_time), _hms(r.end_time)) for r in rows}


def _registrations_by_request_no():
    """requestNo -> {parent: docstatus} for requests already pulled into ERPNext."""
    marker = "Request number: "
    rows = frappe.db.sql("""
        SELECT DISTINCT d.parent, d.reason, p.docstatus
        FROM `tabOvertime Registration Detail` d
        JOIN `tabOvertime Registration` p ON p.name = d.parent
        WHERE d.reason LIKE %(pattern)s
    """, {"pattern": f"%{marker}%"}, as_dict=1)
    result = {}
    for r in rows:
        request_no = r.reason.split(marker, 1)[1].strip()
        result.setdefault(request_no, {})[r.parent] = r.docstatus
    return result


def _run_ot_sync_job(from_date, cache_key, to_date=None, fill_missing_rows=False):
    """fill_missing_rows=False (daily 18:00 job): a request with any row in ERPNext is skipped.
    fill_missing_rows=True (manual sync on the page): rows are compared one by one and the
    missing ones are added to the request's draft registration — so after "Delete OT" cut
    a request spanning the range edge (rows 8-12, deleted 1-10), syncing 1-10 again restores 8-10.
    """
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
            # "OTR-..." = pushed from ERPNext by the form's "Sync to MongoDB"
            # (overtime_registration_mongodb.py) — never pull it back
            if request_no and not str(request_no).startswith("OTR-"):
                grouped.setdefault(str(request_no), []).append(rec)

        total = len(grouped)
        _update_cache(cache_key, {"total_count": total, "phase": f"Processing {total} OT requests..."})

        if fill_missing_rows:
            ot_dates = [r["otDate"].strftime("%Y-%m-%d") for recs in grouped.values()
                        for r in recs if isinstance(r.get("otDate"), datetime)]
            existing_keys = _existing_ot_keys(min(ot_dates), max(ot_dates)) if ot_dates else set()
            request_parents = _registrations_by_request_no()

        created = updated = skipped = failed = 0
        for i, (request_no, recs) in enumerate(sorted(grouped.items())):
            try:
                # The request number lives in the rows' reason (the parent
                # reason_general field was removed 2026-09-24)
                ot_reason = f"Sync from MongoDB: Request number: {request_no}"
                if not fill_missing_rows and frappe.get_all(
                        "Overtime Registration Detail",
                        filters=[["reason", "like", f"%Request number: {request_no}%"]],
                        limit=1):
                    skipped += 1
                    continue

                first = recs[0]
                request_date_raw = first.get("requestDate")
                request_date = (request_date_raw.strftime("%Y-%m-%d")
                                if isinstance(request_date_raw, datetime)
                                else datetime.now().strftime("%Y-%m-%d"))

                ot_employees = []
                zero_rows = 0
                for rec in recs:
                    ot_date_raw = rec.get("otDate")
                    emp_id = rec.get("empId")
                    if not isinstance(ot_date_raw, datetime) or not emp_id:
                        continue
                    ot_date = ot_date_raw.strftime("%Y-%m-%d")
                    begin_time = _normalize_time(rec.get("otTimeBegin"), "17:00")
                    end_time = _normalize_time(rec.get("otTimeEnd"), "19:00")
                    if fill_missing_rows:
                        # legacy "00:00-00:00" = 0-hour OT: validate_time_order would
                        # reject the whole request because of it
                        if _hms(begin_time) >= _hms(end_time):
                            zero_rows += 1
                            continue
                        if (emp_id, ot_date, _hms(begin_time), _hms(end_time)) in existing_keys:
                            continue
                    elif _employee_has_ot(emp_id, ot_date, begin_time, end_time):
                        continue
                    ot_employees.append({
                        "employee": emp_id,
                        "date": ot_date,
                        "begin_time": begin_time,
                        "end_time": end_time,
                        "reason": ot_reason,
                    })

                if not ot_employees:
                    skipped += 1
                    _append_result(cache_key, True, request_no, "OT",
                                   "Skipped: all employees already have this OT")
                    continue

                # Fill mode: add the missing rows to the request's draft registration;
                # a submitted/cancelled one cannot be edited -> new registration
                draft = None
                if fill_missing_rows:
                    draft = next((name for name, docstatus
                                  in sorted(request_parents.get(request_no, {}).items())
                                  if docstatus == 0), None)

                if draft:
                    doc = frappe.get_doc("Overtime Registration", draft)
                    doc.extend("ot_employees", ot_employees)
                    doc.save(ignore_permissions=True)
                    frappe.db.commit()
                    updated += 1
                    _append_result(cache_key, True, request_no, "OT",
                                   f"Added {len(ot_employees)} missing row(s) to {draft}"
                                   + (f" ({zero_rows} invalid-time row(s) skipped)" if zero_rows else ""))
                else:
                    doc = frappe.get_doc({
                        "doctype": "Overtime Registration",
                        "request_date": request_date,
                        "ot_employees": ot_employees,
                    })
                    doc.insert(ignore_permissions=True)
                    frappe.db.commit()
                    created += 1
                    _append_result(cache_key, True, request_no, "OT",
                                   f"Created with {len(ot_employees)} employee(s)"
                                   + (f" ({zero_rows} invalid-time row(s) skipped)" if zero_rows else ""))
                    if fill_missing_rows:
                        request_parents.setdefault(request_no, {})[doc.name] = doc.docstatus

                if fill_missing_rows:
                    existing_keys.update((r["employee"], r["date"], _hms(r["begin_time"]), _hms(r["end_time"]))
                                         for r in ot_employees)
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
            "phase": f"Complete: {created} created, "
                     + (f"{updated} updated, " if fill_missing_rows else "")
                     + f"{skipped} skipped, {failed} failed (of {total} requests)",
        })
    except Exception as e:
        frappe.log_error(f"_run_ot_sync_job failed: {e}")
        _update_cache(cache_key, {"status": "error", "error": str(e), "phase": f"Error: {e}"})


# ---------------------------------------------------------------------------
# 3. Daily auto sync MongoDB -> ERPNext (scheduler, 18:00)
# ---------------------------------------------------------------------------
# Temporary: replaces the tool's auto MongoDB jobs until OT is registered
# directly in ERPNext. Re-scans the last N days every run — duplicates are
# skipped by _add_checkin / the Request number check, so this is idempotent.

MONGODB_DAILY_SYNC_DAYS = 30


def run_daily_mongodb_sync():
    """Scheduler entry (hooks cron 0 18 * * *): enqueue on the long queue."""
    frappe.enqueue(
        "customize_erpnext.network.biometric.mongodb_sync._run_daily_mongodb_sync_job",
        queue="long",
        timeout=3600,
        job_id="biometric_daily_mongodb_sync",
        deduplicate=True,
    )


def _run_daily_mongodb_sync_job():
    from frappe.utils import add_days, getdate, today

    d_to = getdate(today())
    d_from = add_days(d_to, -(MONGODB_DAILY_SYNC_DAYS - 1))
    logger = frappe.logger("biometric_mongodb_sync", allow_site=True)
    logger.setLevel(logging.INFO)  # frappe default is ERROR outside dev server

    steps = [
        ("mongo_daily", "MongoDB logs", lambda key: _run_mongodb_resync_job(str(d_from), str(d_to), key)),
        # No upper bound: OT can be registered ahead of the OT date
        ("ot_daily", "MongoDB OT", lambda key: _run_ot_sync_job(str(d_from), key)),
    ]
    for prefix, label, run in steps:
        _job_id, cache_key = _new_job(prefix)
        run(cache_key)
        state = frappe.cache().get_value(cache_key) or {}
        failures = [r for r in state.get("results", []) if not r.get("success")]
        logger.info(f"{label} {d_from}..{d_to}: {state.get('phase')}")
        if state.get("status") == "error" or failures:
            frappe.log_error(
                title=f"Daily {label} sync",
                message=f"{state.get('phase')}\n\n" + "\n".join(
                    f"{r.get('user_id')}: {r.get('message')}" for r in failures[:200]),
            )
